from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PathContext:
    """Centralizes path resolution and security validation for agent file access."""

    workspace_root: Path
    agents_dir: Path
    db_path: Path
    mcp_config: Path
    tools_dir: Path
    skills_dir: Path

    def get_allowed_paths(self, config) -> list[Path]:
        """Return resolved paths the agent can read from and write to.

        Defaults to [workspace_root] if the agent has no 'paths' config.
        Watch paths are automatically included so agents can access watched files.
        """
        paths = [self._resolve_relative(p) for p in config.paths] if config.paths else [self.workspace_root]

        # Include watch paths so agents can access files they're watching
        if config.trigger.type == "watch" and config.trigger.paths:
            watch_paths = [self._resolve_relative(p) for p in config.trigger.paths]
            paths.extend(watch_paths)

        return list(dict.fromkeys(paths))

    def get_memory_file_path(self, config) -> Path:
        """Return the path to the agent's .memory.md file."""
        return self.agents_dir / f"{config.name}.memory.md"

    def get_default_write_dir(self, config) -> Path:
        """Return the default directory for resolving relative write paths.

        Uses the first directory in the agent's allowed paths.
        """
        allowed = self.get_allowed_paths(config)
        for p in allowed:
            if p.is_dir() or not p.suffix:
                return p
        # All paths are files — use parent of the first one
        return allowed[0].parent if allowed else self.workspace_root

    def validate_path(self, path: str, config, *, resolve_from: str = "workspace") -> tuple[Path | None, str | None]:
        """Resolve and validate a path for access.

        Args:
            path: The path to validate (absolute or relative).
            config: AgentConfig with paths and trigger info.
            resolve_from: How to resolve relative paths:
                - "workspace": relative to workspace_root (default for reads/listing).
                - "write": relative to first allowed path (for file_write).

        Returns:
            (resolved_path, None) on success or (None, error_message) on failure.
        """
        if resolve_from == "write":
            resolved = self._resolve_for_write(path, config)
        else:
            resolved = self._resolve_relative(path)

        # Security checks
        error = self._check_security(resolved)
        if error:
            logger.warning(f"Security violation for agent '{config.name}': {error}")
            return None, error

        # Check against allowed paths
        allowed = self.get_allowed_paths(config)
        if not self._is_within_any(resolved, allowed):
            error_msg = f"Access denied: '{path}' is outside allowed paths"
            logger.warning(f"Path access denied for agent '{config.name}': {path} -> {resolved} (allowed: {allowed})")
            return None, error_msg

        return resolved, None

    # --- Private helpers ---

    def _resolve_relative(self, path: str) -> Path:
        """Resolve a path relative to workspace_root."""
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = self.workspace_root / p
        return p.resolve()

    def _resolve_for_write(self, path: str, config) -> Path:
        """Resolve a write path (relative to first allowed path).

        Relative paths resolve from the first directory in allowed paths (or workspace if none).
        """
        p = Path(path).expanduser()
        if not p.is_absolute():
            default_dir = self.get_default_write_dir(config)
            p = default_dir / p
        return p.resolve()

    def _check_security(self, resolved: Path) -> str | None:
        """Check security restrictions. Returns error message or None."""
        # Cannot access the agents directory
        if self._is_within(resolved, self.agents_dir):
            return "Access denied: cannot access agents directory"

        # Cannot access .env files
        if resolved.name.startswith(".env"):
            return "Access denied: cannot access .env files"

        # Cannot write .db files
        if resolved.suffix == ".db":
            return "Access denied: cannot access .db files"

        return None

    def _is_within(self, path: Path, directory: Path) -> bool:
        """Check if path is within a directory.

        Both arguments should be resolved paths.
        """
        try:
            path.relative_to(directory)
            return True
        except ValueError:
            return False

    def _is_within_any(self, path: Path, directories: list[Path]) -> bool:
        """Check if path is within any of the given directories/files.

        Assumes all paths in directories list are already resolved.
        """
        for d in directories:
            if d.is_file() or d.suffix:
                # It's a file path — exact match only
                if path == d:
                    return True
            else:
                # It's a directory — check containment
                if self._is_within(path, d):
                    return True
        return False
