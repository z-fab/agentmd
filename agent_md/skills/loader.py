"""Skill content processing — variable substitution and dynamic context injection."""

from __future__ import annotations

import re
import subprocess


def apply_substitutions(content: str, arguments: str = "", skill_dir: str = "") -> str:
    """Apply variable substitutions and dynamic context injection to skill content.

    Substitutions (Claude Code compatible):
        $ARGUMENTS      → all arguments as a string
        $ARGUMENTS[N]   → N-th argument (0-indexed)
        $0, $1, ...     → shorthand for $ARGUMENTS[N]
        ${SKILL_DIR}    → absolute path to the skill directory
        !`command`      → run shell command, replace with stdout

    Args:
        content: Raw skill instructions (markdown body).
        arguments: User-provided arguments string.
        skill_dir: Absolute path to the skill directory.

    Returns:
        Processed content with all substitutions applied.
    """
    arg_parts = arguments.split() if arguments else []

    def _get_arg(idx: int) -> str:
        return arg_parts[idx] if idx < len(arg_parts) else ""

    result = content

    # ${SKILL_DIR} → absolute path
    result = result.replace("${SKILL_DIR}", skill_dir)

    # $ARGUMENTS[N] → N-th argument (must come before plain $ARGUMENTS)
    result = re.sub(r"\$ARGUMENTS\[(\d+)\]", lambda m: _get_arg(int(m.group(1))), result)

    # $ARGUMENTS → full arguments string
    result = result.replace("$ARGUMENTS", arguments)

    # $N → shorthand for N-th argument (single digit, not followed by word char)
    result = re.sub(r"\$(\d)(?!\w)", lambda m: _get_arg(int(m.group(1))), result)

    # !`command` → execute shell command, inject stdout
    result = _apply_dynamic_injection(result, skill_dir)

    return result


def _apply_dynamic_injection(content: str, skill_dir: str) -> str:
    """Process !`command` patterns — run shell commands and inject output.

    Commands execute with the skill directory as cwd, with a 10s timeout.
    """

    def _run_command(match: re.Match) -> str:
        cmd = match.group(1)
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=skill_dir,
            )
            output = result.stdout.strip()
            if result.returncode != 0 and result.stderr:
                output += f"\n[stderr: {result.stderr.strip()}]"
            return output
        except subprocess.TimeoutExpired:
            return f"[command timed out: {cmd}]"
        except Exception as e:
            return f"[command error: {e}]"

    return re.sub(r"!`([^`]+)`", _run_command, content)
