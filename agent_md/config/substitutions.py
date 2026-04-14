"""Variable substitution and dynamic command injection.

Shared between skills and agent prompts. Supports:
    $ARGUMENTS, $ARGUMENTS[N], $0..$9   — positional arguments
    ${NAME}                              — named variables from extra_vars
    !`command`                           — shell command, replaced with stdout
"""

from __future__ import annotations

import re
import subprocess


def apply_substitutions(
    content: str,
    arguments: list[str] | str = "",
    cwd: str | None = None,
    extra_vars: dict[str, str] | None = None,
) -> str:
    """Apply variable substitutions and dynamic context injection.

    Args:
        content: Raw text to process.
        arguments: Positional arguments as a list or a single string.
        cwd: Working directory for `!`cmd`` execution. Defaults to "." if None.
        extra_vars: Dict of named variables substituted via ${NAME}.

    Returns:
        Processed content with all substitutions applied.
    """
    if isinstance(arguments, list):
        arg_parts = arguments
        arguments_str = "\n".join(arguments)
    else:
        arg_parts = [arguments] if arguments else []
        arguments_str = arguments

    def _get_arg(idx: int) -> str:
        return arg_parts[idx] if idx < len(arg_parts) else ""

    result = content

    # ${NAME} from extra_vars (run before $ARGUMENTS so ${SKILL_DIR} works)
    if extra_vars:
        for name, value in extra_vars.items():
            result = result.replace("${" + name + "}", value)

    # $ARGUMENTS[N] (must come before plain $ARGUMENTS)
    result = re.sub(r"\$ARGUMENTS\[(\d+)\]", lambda m: _get_arg(int(m.group(1))), result)

    # $ARGUMENTS — full string (joined by newline when from list)
    result = result.replace("$ARGUMENTS", arguments_str)

    # $0..$9 — single digit shorthand, not followed by word char
    result = re.sub(r"\$(\d)(?!\w)", lambda m: _get_arg(int(m.group(1))), result)

    # !`command` → stdout
    result = _apply_dynamic_injection(result, cwd or ".")

    return result


def _apply_dynamic_injection(content: str, cwd: str) -> str:
    """Process !`command` patterns, executing each in `cwd` with a 10s timeout."""

    def _run_command(match: re.Match) -> str:
        cmd = match.group(1)
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=cwd,
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
