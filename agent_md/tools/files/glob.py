"""Tool: file_glob — Find files matching a glob pattern."""

from __future__ import annotations

from langchain_core.tools import tool

MAX_RESULTS = 100


def create_file_glob_tool(agent_config, path_context):
    """Create a file_glob tool bound to an agent's path context."""

    @tool
    def file_glob(pattern: str) -> str:
        """Find files matching a glob pattern from the workspace root.

        Args:
            pattern: Glob pattern (e.g., '**/*.py', 'src/**/*.md', '*.json').

        Returns:
            Matching file paths (one per line), or an error message.
        """
        workspace = path_context.workspace_root
        allowed = path_context.get_allowed_paths(agent_config)

        try:
            all_matches = sorted(workspace.glob(pattern))
        except Exception as e:
            return f"ERROR: Invalid glob pattern: {e}"

        # Filter to only files (not directories) within allowed paths
        matches = []
        for match in all_matches:
            if not match.is_file():
                continue
            resolved = match.resolve()
            if path_context._is_within_any(resolved, allowed):
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
