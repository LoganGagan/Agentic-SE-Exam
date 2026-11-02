from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version


PYTHON_VERSION = Version("3.11")
PINNED_REQUIREMENT = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([^\s;#]+)"
)


def fetch_json(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def check_dependency(
    name: str, version: str
) -> tuple[str, str, bool, bool, str | None]:
    name = quote(name, safe="")
    version = quote(version, safe="")
    try:
        fetch_json(f"https://pypi.org/pypi/{name}/json")
    except HTTPError as error:
        if error.code == 404:
            return name, version, False, False, None
        raise
    try:
        data = fetch_json(f"https://pypi.org/pypi/{name}/{version}/json")
    except HTTPError as error:
        if error.code == 404:
            return name, version, False, False, None
        raise

    requires_python = data.get("info", {}).get("requires_python") or None
    compatible = (
        requires_python is None
        or PYTHON_VERSION in SpecifierSet(requires_python)
    )
    return name, version, True, compatible, requires_python


def parse_dependencies(lines: list[str]) -> list[tuple[str, str]]:
    dependencies = []
    for line in lines:
        match = PINNED_REQUIREMENT.match(line.split("#", 1)[0])
        if match:
            dependencies.append((match.group(1), match.group(2)))
    return dependencies


def minimum_python_version(specifier_text: str) -> Version | None:
    minimum: Version | None = None
    for specifier in SpecifierSet(specifier_text):
        if specifier.operator not in {">=", ">"}:
            continue
        try:
            candidate = Version(specifier.version)
        except InvalidVersion:
            continue
        if minimum is None or candidate > minimum:
            minimum = candidate
    return minimum


def highest_requirement(results: list[tuple[str, str, bool, bool, str | None]]):
    candidates: list[
        tuple[tuple[str, str, bool, bool, str | None], Version]
    ] = []
    for name, version, found, _, requires_python in results:
        if found and requires_python:
            minimum = minimum_python_version(requires_python)
            if minimum is not None:
                candidates.append(
                    ((name, version, True, True, requires_python), minimum)
                )
    return max(candidates, key=lambda candidate: candidate[1], default=None)


def print_report(results: list[tuple[str, str, bool, bool, str | None]]) -> None:
    not_found = sum(not found for _, _, found, _, _ in results)
    incompatible = sum(
        found and not compatible for _, _, found, compatible, _ in results
    )
    print(f"Dependencies checked: {len(results)}")
    print(f"Not found on PyPI: {not_found}")
    print(f"Incompatible with Python 3.11: {incompatible}")

    highest = highest_requirement(results)
    if highest is None:
        print("Highest requirement: none")
    else:
        (name, version, _, _, _), minimum = highest
        print(
            f"Highest requirement: {name}=={version} (>={minimum})"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check pinned requirements against PyPI for Python 3.11."
    )
    parser.add_argument(
        "requirements_file",
        nargs="?",
        default="requirements.txt",
        type=Path,
        help="requirements file (default: requirements.txt)",
    )
    args = parser.parse_args()
    dependencies = parse_dependencies(
        args.requirements_file.read_text(encoding="utf-8").splitlines()
    )
    print_report([check_dependency(name, version) for name, version in dependencies])


if __name__ == "__main__":
    main()
