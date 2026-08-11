"""Declared dependency floors must not drift below what the lock proves.

`langchain-openai>=0.3.0` was declared long after 0.3.x became unselectable:
0.3.35 requires langchain-core<1, while langchain-google-genai 4.2.1 requires
core>=1.2.5. A floor that no resolver can honour is metadata that lies.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

EXPECTED_FLOORS = {
    "langchain-openai": "1.1.11",
    "langchain-anthropic": "1.3.4",
    "langchain-ollama": "1.0.1",
    "langchain-openrouter": "0.2.7",
}


def _declared_floors() -> dict[str, str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    floors: dict[str, str] = {}
    for specs in data["project"]["optional-dependencies"].values():
        for spec in specs:
            name, _, floor = spec.partition(">=")
            floors[name.strip()] = floor.strip()
    return floors


def test_extra_floors_match_expected():
    declared = _declared_floors()
    for package, floor in EXPECTED_FLOORS.items():
        assert declared.get(package) == floor, f"{package} floor is {declared.get(package)!r}, expected {floor!r}"


def test_openrouter_extra_exists_and_is_in_all():
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    extras = data["project"]["optional-dependencies"]
    assert "openrouter" in extras
    assert any(spec.startswith("langchain-openrouter") for spec in extras["all"])
