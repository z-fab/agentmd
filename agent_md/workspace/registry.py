from __future__ import annotations

import logging
from typing import Optional

from agent_md.config.models import AgentConfig

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Holds all loaded agent configs in memory.

    The registry is the single source of truth for the current state
    of all agents. The scheduler and runner read from here.

    Agents are keyed by canonical ``config.id`` (filename stem).
    """

    def __init__(self):
        self._agents: dict[str, AgentConfig] = {}
        self._path_to_id: dict[str, str] = {}

    def register(self, config: AgentConfig) -> None:
        """Register or update an agent config."""
        existed = config.id in self._agents

        # Clean up old path mapping if file_path changed
        if existed:
            from pathlib import Path

            old = self._agents[config.id]
            old_path = old.file_path
            if old_path and old_path != config.file_path:
                self._path_to_id.pop(old_path, None)
                # Warn only when both files still exist (true duplicate), not a rename.
                if Path(old_path).exists() and config.file_path and Path(config.file_path).exists():
                    logger.warning(
                        f"Agent id '{config.id}' is shared by multiple files; "
                        f"registering {config.file_path} overwrites {old_path}"
                    )

        self._agents[config.id] = config
        if config.file_path:
            self._path_to_id[config.file_path] = config.id

        action = "Updated" if existed else "Registered"
        logger.info(f"{action} agent: {config.id}")

    def get(self, agent_id: str) -> Optional[AgentConfig]:
        """Get an agent config by canonical id (filename stem)."""
        return self._agents.get(agent_id)

    def get_by_path(self, path: str) -> Optional[AgentConfig]:
        """Look up an agent config by its registered file path without removing it."""
        agent_id = self._path_to_id.get(path)
        if agent_id is None:
            return None
        return self._agents.get(agent_id)

    def remove(self, agent_id: str) -> bool:
        """Remove an agent from the registry. Returns True if it existed."""
        if agent_id in self._agents:
            path = self._agents[agent_id].file_path
            if path:
                self._path_to_id.pop(path, None)
            del self._agents[agent_id]
            logger.info(f"Removed agent: {agent_id}")
            return True
        return False

    def remove_by_path(self, path: str) -> str | None:
        """Look up agent id from file path, remove it, and return the id.

        Returns None if no agent is registered for that path.
        """
        agent_id = self._path_to_id.get(path)
        if agent_id is None:
            return None
        self.remove(agent_id)
        return agent_id

    def all(self) -> list[AgentConfig]:
        """Return all registered agent configs."""
        return list(self._agents.values())

    def enabled(self) -> list[AgentConfig]:
        """Return only enabled agent configs."""
        return [a for a in self._agents.values() if a.enabled]

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._agents
