from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

ALIAS_REF = re.compile(r"^\{([a-z][a-z0-9_]*)\}(.*)$")


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
        """Return absolute paths the agent can read from and write to.

        If the agent declares no `paths`, defaults to [workspace_root].
        Watch trigger paths are included automatically.
        """
        if config.paths:
            paths = [self._resolve_relative(entry.path) for entry in config.paths.values()]
        else:
            paths = [self.workspace_root]

        if config.trigger.type == "watch" and config.trigger.paths:
            watch_paths = [self._resolve_relative(p) for p in config.trigger.paths]
            paths.extend(watch_paths)

        return list(dict.fromkeys(paths))

    def get_memory_file_path(self, config) -> Path:
        """Return the path to the agent's .memory.md file."""
        return self.agents_dir / f"{config.name}.memory.md"

    def resolve_alias(self, name: str, config) -> Path:
        """Return the absolute Path for a declared alias.

        Raises KeyError if the alias is not declared on this agent.
        """
        if name not in config.paths:
            raise KeyError(f"path alias '{name}' is not declared on agent '{config.name}'")
        return self._resolve_relative(config.paths[name].path)

    def expand(self, value: str, config) -> Path:
        """Resolve a path string to an absolute Path, without sandbox validation.

        Handles three forms:
            - "{alias}" or "{alias}/sub"  — alias expansion
            - "/abs/path"                 — used as-is
            - "rel/path" or "./rel"       — resolved against workspace_root

        Raises KeyError if the alias is not declared.
        """
        m = ALIAS_REF.match(value)
        if m:
            alias_name = m.group(1)
            remainder = m.group(2)
            base = self.resolve_alias(alias_name, config)
            if remainder.startswith("/"):
                remainder = remainder[1:]
            return (base / remainder).resolve() if remainder else base
        return self._resolve_relative(value)

    def validate_path(self, path: str, config, *, quiet: bool = False) -> tuple[Path | None, str | None]:
        """Resolve and sandbox-check a path.

        Returns (resolved_path, None) on success or (None, error_message).
        When *quiet* is True, validation errors are not logged (used by
        file_glob to silently filter results).
        """
        try:
            resolved = self.expand(path, config)
        except KeyError as e:
            return None, f"Access denied: {e}"

        error = self._check_security(resolved)
        if error:
            if not quiet:
                logger.warning("Security check failed for '%s': %s", path, error)
            return None, error

        allowed = self.get_allowed_paths(config)
        if not self._is_within_any(resolved, allowed):
            if not quiet:
                logger.warning("Path '%s' is outside allowed paths: %s", path, [str(p) for p in allowed])
            return None, f"Access denied: '{path}' is outside allowed paths"

        return resolved, None

    # --- Private helpers ---

    def _resolve_relative(self, path: str) -> Path:
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = self.workspace_root / p
        return p.resolve()

    def _check_security(self, resolved: Path) -> str | None:
        if self._is_within(resolved, self.agents_dir):
            return "Access denied: cannot access agents directory"
        if resolved.name.startswith(".env"):
            return "Access denied: cannot access .env files"
        if resolved.suffix == ".db":
            return "Access denied: cannot access .db files"
        return None

    def _is_within(self, path: Path, directory: Path) -> bool:
        try:
            path.relative_to(directory)
            return True
        except ValueError:
            return False

    def _is_within_any(self, path: Path, directories: list[Path]) -> bool:
        for d in directories:
            if d.is_file() or d.suffix:
                if path == d:
                    return True
            else:
                if self._is_within(path, d):
                    return True
        return False
