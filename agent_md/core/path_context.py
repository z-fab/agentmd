from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PathContext:
    """Centralizes path resolution and security validation for agent file access."""

    workspace_root: Path
    agents_dir: Path
    output_dir: Path
    db_path: Path
    mcp_config: Path

    def get_read_paths(self, config) -> list[Path]:
        """Return resolved read paths for an agent.

        Defaults to [workspace_root] if the agent has no 'read' config.
        """
        if config.read:
            return [self._resolve_relative(p) for p in config.read]
        return [self.workspace_root]

    def get_write_paths(self, config) -> list[Path]:
        """Return resolved write paths for an agent.

        Defaults to [output_dir] if the agent has no 'write' config.
        """
        if config.write:
            return [self._resolve_relative(p) for p in config.write]
        return [self.output_dir]

    def get_default_write_dir(self, config) -> Path:
        """Return the default directory for relative write paths.

        Uses the first directory in the agent's write config,
        or falls back to the global output_dir.
        """
        write_paths = self.get_write_paths(config)
        for p in write_paths:
            if p.is_dir() or not p.suffix:
                return p
        # All write paths are files — use parent of the first one
        return write_paths[0].parent if write_paths else self.output_dir

    def validate_read(self, path: str, config) -> tuple[Path | None, str | None]:
        """Resolve and validate a path for reading.

        Relative paths are resolved from workspace_root.
        Returns (resolved_path, None) on success or (None, error_message) on failure.
        """
        resolved = self._resolve_for_read(path)

        # Security checks
        error = self._check_security_read(resolved)
        if error:
            return None, error

        # Check against allowed read paths
        read_paths = self.get_read_paths(config)
        if not self._is_within_any(resolved, read_paths):
            return None, f"Access denied: '{path}' is outside allowed read paths"

        return resolved, None

    def validate_write(self, path: str, config) -> tuple[Path | None, str | None]:
        """Resolve and validate a path for writing.

        Relative paths are resolved from the agent's default write directory.
        Returns (resolved_path, None) on success or (None, error_message) on failure.
        """
        resolved = self._resolve_for_write(path, config)

        # Security checks
        error = self._check_security_write(resolved)
        if error:
            return None, error

        # Check against allowed write paths
        write_paths = self.get_write_paths(config)
        if not self._is_write_allowed(resolved, write_paths):
            return None, f"Access denied: '{path}' is outside allowed write paths"

        return resolved, None

    # --- Private helpers ---

    def _resolve_relative(self, path: str) -> Path:
        """Resolve a path relative to workspace_root."""
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = self.workspace_root / p
        return p.resolve()

    def _resolve_for_read(self, path: str) -> Path:
        """Resolve a read path (relative to workspace root)."""
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = self.workspace_root / p
        return p.resolve()

    def _resolve_for_write(self, path: str, config) -> Path:
        """Resolve a write path (relative to default write dir)."""
        p = Path(path).expanduser()
        if not p.is_absolute():
            default_dir = self.get_default_write_dir(config)
            p = default_dir / p
        return p.resolve()

    def _check_security_read(self, resolved: Path) -> str | None:
        """Check read security restrictions. Returns error message or None."""
        # Cannot read from agents directory
        if self._is_within(resolved, self.agents_dir):
            return "Access denied: cannot read from agents directory"

        # Cannot read .env files
        if resolved.name.startswith(".env"):
            return "Access denied: cannot read .env files"

        return None

    def _check_security_write(self, resolved: Path) -> str | None:
        """Check write security restrictions. Returns error message or None."""
        # Cannot write to agents directory
        if self._is_within(resolved, self.agents_dir):
            return "Access denied: cannot write to agents directory"

        # Cannot write .db files
        if resolved.suffix == ".db":
            return "Access denied: cannot write to .db files"

        # Cannot write .env files
        if resolved.name.startswith(".env"):
            return "Access denied: cannot write .env files"

        return None

    def _is_within(self, path: Path, directory: Path) -> bool:
        """Check if path is within a directory (follows symlinks)."""
        try:
            path.relative_to(directory.resolve())
            return True
        except ValueError:
            return False

    def _is_within_any(self, path: Path, directories: list[Path]) -> bool:
        """Check if path is within any of the given directories/files."""
        for d in directories:
            d_resolved = d.resolve()
            if d_resolved.is_file() or d_resolved.suffix:
                # It's a file path — exact match only
                if path == d_resolved:
                    return True
            else:
                # It's a directory — check containment
                if self._is_within(path, d_resolved):
                    return True
        return False

    def _is_write_allowed(self, path: Path, write_paths: list[Path]) -> bool:
        """Check if path is allowed for writing given the write paths."""
        for wp in write_paths:
            wp_resolved = wp.resolve()
            if wp_resolved.suffix:
                # Write path is a file — exact match only
                if path == wp_resolved:
                    return True
            else:
                # Write path is a directory — allow anything inside
                if self._is_within(path, wp_resolved):
                    return True
        return False
