"""MCP server configuration loading and validation."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from agent_md.config.env import resolve_env_vars

logger = logging.getLogger(__name__)


def _infer_transport(name: str, raw: dict) -> dict[str, Any]:
    """Convert a raw server config into the format expected by MultiServerMCPClient.

    Transport is inferred:
      - Has ``command`` → stdio
      - Has ``url``     → http

    Raises:
        ValueError: If transport cannot be inferred.
    """
    has_command = "command" in raw
    has_url = "url" in raw

    if has_command and has_url:
        raise ValueError(f"MCP server '{name}': cannot have both 'command' and 'url'")
    if not has_command and not has_url:
        raise ValueError(f"MCP server '{name}': must have either 'command' (stdio) or 'url' (http)")

    if has_command:
        config: dict[str, Any] = {
            "transport": "stdio",
            "command": raw["command"],
            "args": raw.get("args", []),
        }
        if "env" in raw:
            config["env"] = raw["env"]
        return config

    # http / streamable-http
    config = {
        "transport": "http",
        "url": raw["url"],
    }
    if "headers" in raw:
        config["headers"] = raw["headers"]
    return config


def load_mcp_config(config_path: Path) -> dict[str, dict[str, Any]]:
    """Load and validate MCP server configurations from a JSON file.

    Args:
        config_path: Path to ``mcp-servers.json``.

    Returns:
        Dict mapping server names to configs ready for ``MultiServerMCPClient``.
        Returns empty dict if the file does not exist.

    Raises:
        ValueError: On invalid JSON or schema errors.
    """
    if not config_path.exists():
        logger.debug(f"No MCP config at {config_path}")
        return {}

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"MCP config must be a JSON object, got {type(raw).__name__}")

    # Resolve env vars in all string values, then infer transport
    servers: dict[str, dict[str, Any]] = {}
    for name, server_raw in raw.items():
        if not isinstance(server_raw, dict):
            raise ValueError(f"MCP server '{name}': config must be an object")
        resolved = resolve_env_vars(server_raw)
        servers[name] = _infer_transport(name, resolved)

    if servers:
        logger.info(f"Loaded MCP config: {len(servers)} server(s) ({', '.join(servers)})")

    return servers
