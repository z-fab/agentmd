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
    tools_dir: Path

    def get_read_paths(self, config) -> list[Path]:
        """Return resolved read paths for an agent.

        Defaults to [workspace_root] if the agent has no 'read' config.
        Watch paths are automatically included to allow agents to read watched files.
        """
        paths = [self._resolve_relative(p) for p in config.read] if config.read else [self.workspace_root]

        # Include watch paths so agents can read files they're watching
        if config.trigger.type == "watch" and config.trigger.paths:
            watch_paths = [self._resolve_relative(p) for p in config.trigger.paths]
            paths.extend(watch_paths)

        # Deduplicate while preserving order
        seen = set()
        unique_paths = []
        for p in paths:
            if p not in seen:
                seen.add(p)
                unique_paths.append(p)

        return unique_paths

    def get_write_paths(self, config) -> list[Path]:
        """Return resolved write paths for an agent.

        Defaults to [output_dir] if the agent has no 'write' config.
        """
        if config.write:
            return [self._resolve_relative(p) for p in config.write]
        return [self.output_dir]

    def get_memory_file_path(self, config) -> Path:
        """Return the path to the agent's .memory.md file."""
        return self.agents_dir / f"{config.name}.memory.md"

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
        resolved = self._resolve_relative(path)

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
        if not self._is_within_any(resolved, write_paths):
            return None, f"Access denied: '{path}' is outside allowed write paths"

        return resolved, None

    # --- Private helpers ---

    def _resolve_relative(self, path: str) -> Path:
        """Resolve a path relative to workspace_root."""
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = self.workspace_root / p
        return p.resolve()

    def _resolve_for_write(self, path: str, config) -> Path:
        """Resolve a write path (relative to default write dir).

        Detects and strips duplicated directory prefixes — e.g., if the default
        write dir ends with 'output' and path starts with 'output/', the
        redundant prefix is removed to avoid 'output/output/'.
        """
        p = Path(path).expanduser()
        if not p.is_absolute():
            default_dir = self.get_default_write_dir(config)
            parts = p.parts
            if len(parts) > 1 and parts[0] == default_dir.name:
                p = default_dir / Path(*parts[1:])
            else:
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

