from __future__ import annotations

import logging
from typing import Optional

from agent_md.config.models import AgentConfig

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Holds all loaded agent configs in memory.

    The registry is the single source of truth for the current state
    of all agents. The scheduler and runner read from here.
    """

    def __init__(self):
        self._agents: dict[str, AgentConfig] = {}
        self._path_to_name: dict[str, str] = {}

    def register(self, config: AgentConfig) -> None:
        """Register or update an agent config."""
        existed = config.name in self._agents

        # Clean up old path mapping if file_path changed
        if existed:
            old_path = self._agents[config.name].file_path
            if old_path and old_path != config.file_path:
                self._path_to_name.pop(old_path, None)

        self._agents[config.name] = config
        if config.file_path:
            self._path_to_name[config.file_path] = config.name

        action = "Updated" if existed else "Registered"
        logger.info(f"{action} agent: {config.name}")

    def get(self, name: str) -> Optional[AgentConfig]:
        """Get an agent config by name."""
        return self._agents.get(name)

    def remove(self, name: str) -> bool:
        """Remove an agent from the registry. Returns True if it existed."""
        if name in self._agents:
            path = self._agents[name].file_path
            if path:
                self._path_to_name.pop(path, None)
            del self._agents[name]
            logger.info(f"Removed agent: {name}")
            return True
        return False

    def remove_by_path(self, path: str) -> str | None:
        """Look up agent name from file path, remove it, and return the name.

        Returns None if no agent is registered for that path.
        """
        name = self._path_to_name.get(path)
        if name is None:
            return None
        self.remove(name)
        return name

    def all(self) -> list[AgentConfig]:
        """Return all registered agent configs."""
        return list(self._agents.values())

    def enabled(self) -> list[AgentConfig]:
        """Return only enabled agent configs."""
        return [a for a in self._agents.values() if a.enabled]

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, name: str) -> bool:
        return name in self._agents
