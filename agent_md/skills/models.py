"""Pydantic models for skill configuration and metadata."""

import re

from pydantic import BaseModel, field_validator


class SkillConfig(BaseModel):
    """Minimal metadata for skill discovery (tier 1 loading).

    Only name + description are loaded at bootstrap time to keep
    the system prompt lightweight.
    """

    name: str
    description: str = ""
    user_invocable: bool = True
    argument_hint: str = ""

    # Computed (not from YAML)
    skill_dir: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(f"Skill name must contain only alphanumeric, hyphens, and underscores. Got: '{v}'")
        return v


class SkillDefinition(SkillConfig):
    """Full skill definition with instructions (tier 2 loading).

    Extends SkillConfig with the markdown body and supporting file detection.
    Loaded on-demand when an agent calls the skill_use tool.
    """

    instructions: str = ""
    has_scripts: bool = False
    has_references: bool = False
