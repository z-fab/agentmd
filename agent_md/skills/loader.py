"""Skill content processing — re-exports the shared substitutions module.

Kept as a separate import path for backward compatibility with code that
imports `agent_md.skills.loader.apply_substitutions`.
"""

from __future__ import annotations

from agent_md.core.substitutions import apply_substitutions as _apply


def apply_substitutions(content: str, arguments: str = "", skill_dir: str = "") -> str:
    """Backward-compat shim: maps `skill_dir` to `cwd` and `${SKILL_DIR}`."""
    return _apply(
        content,
        arguments=arguments,
        cwd=skill_dir or None,
        extra_vars={"SKILL_DIR": skill_dir} if skill_dir else None,
    )


__all__ = ["apply_substitutions"]
