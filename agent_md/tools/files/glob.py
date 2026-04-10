"""Tool: file_glob — Find files matching a glob pattern."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool

from agent_md.core.path_context import ALIAS_REF

MAX_RESULTS = 100


def create_file_glob_tool(agent_config, path_context):
    """Create a file_glob tool bound to an agent's path context."""

    @tool
    def file_glob(pattern: str) -> str:
        """Find files matching a glob pattern.

        Patterns may be:
        - relative (resolved from the workspace root)
        - absolute (e.g. /Users/x/vault/**/*.md)
        - alias-prefixed (e.g. {vault}/**/*.md)

        Args:
            pattern: Glob pattern.

        Returns:
            Matching file paths (one per line), or an error message.
        """
        syntax_error = _pattern_syntax_error(pattern)
        if syntax_error:
            return _format_invalid(pattern, syntax_error, agent_config)

        try:
            base, sub_pattern = _split_base_and_pattern(pattern, agent_config, path_context)
        except KeyError as e:
            return _format_invalid(pattern, str(e), agent_config)

        try:
            all_matches = sorted(base.glob(sub_pattern))
        except Exception as e:
            return _format_invalid(pattern, str(e), agent_config)

        matches = []
        for match in all_matches:
            if not match.is_file():
                continue
            resolved, error = path_context.validate_path(str(match), agent_config, quiet=True)
            if error is None:
                matches.append(resolved)

        if not matches:
            return f"No files found matching '{pattern}'"

        total = len(matches)
        capped = matches[:MAX_RESULTS]
        lines = [str(p) for p in capped]
        if total > MAX_RESULTS:
            lines.append(f"\n(showing {MAX_RESULTS} of {total} results, refine your pattern)")
        return "\n".join(lines)

    return file_glob


def _split_base_and_pattern(pattern: str, agent_config, path_context) -> tuple[Path, str]:
    """Split a pattern into (base_dir, sub_pattern) suitable for Path.glob.

    For alias and absolute patterns, the base is the longest non-glob prefix.
    For relative patterns, the base is workspace_root.
    """
    m = ALIAS_REF.match(pattern)
    if m:
        alias = m.group(1)
        remainder = m.group(2).lstrip("/")
        base = path_context.resolve_alias(alias, agent_config)
        return base, remainder or "*"

    if pattern.startswith("/"):
        # Absolute: split off the first segment containing a glob char
        parts = Path(pattern).parts
        base_parts: list[str] = []
        sub_parts: list[str] = []
        seen_glob = False
        for part in parts:
            if seen_glob or any(c in part for c in "*?["):
                seen_glob = True
                sub_parts.append(part)
            else:
                base_parts.append(part)
        base = Path(*base_parts) if base_parts else Path("/")
        sub_pattern = "/".join(sub_parts) if sub_parts else "*"
        return base, sub_pattern

    return path_context.workspace_root, pattern


def _pattern_syntax_error(pattern: str) -> str | None:
    """Return an error message if the glob pattern has obvious syntax errors."""
    depth = 0
    for ch in pattern:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth < 0:
                return "unmatched ']'"
    if depth != 0:
        return "unmatched '['"
    return None


def _format_invalid(pattern: str, err: str, agent_config) -> str:
    aliases = list(agent_config.paths.keys())
    hint = f"\nAvailable aliases for this agent: {', '.join('{' + a + '}' for a in aliases)}" if aliases else ""
    return f"ERROR: Invalid glob pattern '{pattern}': {err}{hint}"
