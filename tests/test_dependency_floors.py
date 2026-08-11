"""Declared dependency floors must not drift below what the lock proves.

`langchain-openai>=0.3.0` was declared long after 0.3.x became unselectable:
0.3.35 requires langchain-core<1, while langchain-google-genai 4.2.1 requires
core>=1.2.5. A floor that no resolver can honour is metadata that lies.

Parse each requirement with packaging.requirements.Requirement so exact pins,
extras markers, and per-extra declarations cannot silently overwrite each other.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

EXPECTED_FLOORS = {
    "openai": [("langchain-openai", "1.1.11")],
    "anthropic": [("langchain-anthropic", "1.3.4")],
    "ollama": [("langchain-ollama", "1.0.1")],
    "openrouter": [("langchain-openrouter", "0.2.7")],
    "local": [("langchain-openai", "1.1.11")],
}


def _parse_requirement(spec: str) -> Requirement:
    return Requirement(spec)


def _assert_exact_gte_floor(req: Requirement, package: str, version: str) -> None:
    assert req.name == package, f"expected package {package!r}, got {req.name!r}"
    assert not req.extras, f"{package} must not carry extras markers, got {sorted(req.extras)!r}"
    expected = SpecifierSet(f">={version}")
    assert req.specifier == expected, f"{package} specifier is {str(req.specifier)!r}, expected {str(expected)!r}"
    specs = list(req.specifier)
    assert len(specs) == 1, f"{package} must declare exactly one specifier, got {req.specifier!r}"
    assert specs[0].operator == ">=", f"{package} operator must be '>=', got {specs[0].operator!r}"
    assert specs[0].version == version, f"{package} floor is {specs[0].version!r}, expected {version!r}"


def _extra_requirements(extras: dict[str, list[str]], name: str) -> list[Requirement]:
    assert name in extras, f"extra {name!r} is missing"
    return [_parse_requirement(spec) for spec in extras[name]]


def test_extra_floors_match_expected():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]

    for extra, expected_reqs in EXPECTED_FLOORS.items():
        declared = _extra_requirements(extras, extra)
        assert len(declared) == len(expected_reqs), (
            f"extra {extra!r} has {len(declared)} requirements, expected {len(expected_reqs)}"
        )
        for req, (package, version) in zip(declared, expected_reqs, strict=True):
            _assert_exact_gte_floor(req, package, version)


def test_all_is_union_of_other_extras():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]

    other_names = [name for name in extras if name != "all"]
    seen: dict[str, Requirement] = {}
    for name in other_names:
        for req in _extra_requirements(extras, name):
            key = str(req)
            # Distinct requirement strings only — openai and local share the same pin.
            if key not in seen:
                seen[key] = req

    all_reqs = _extra_requirements(extras, "all")
    all_keys = {str(req) for req in all_reqs}
    expected_keys = set(seen)
    assert all_keys == expected_keys, (
        f"'all' must be the union of distinct requirements from other extras; "
        f"got {sorted(all_keys)}, expected {sorted(expected_keys)}"
    )


def test_openrouter_extra_exists_and_is_in_all():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    assert "openrouter" in extras
    assert any(Requirement(spec).name == "langchain-openrouter" for spec in extras["all"])
