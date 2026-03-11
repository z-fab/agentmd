"""MCPManager — lazy pool that provides LangChain tools from MCP servers."""

from __future__ import annotations

import logging
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)


class MCPManager:
    """Lazy pool of MCP server connections.

    Servers are only contacted on the first ``get_tools`` call that
    references them.  Discovered tools are cached for the lifetime of
    the manager.

    ``MultiServerMCPClient`` (v0.1.0+) is **not** an async context
    manager — each tool invocation opens its own session internally,
    so there is nothing to close explicitly.
    """

    def __init__(self, server_configs: dict[str, dict[str, Any]]) -> None:
        self._configs = server_configs
        self._clients: dict[str, MultiServerMCPClient] = {}
        self._tools_cache: dict[str, list] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_tools(self, server_names: list[str]) -> list:
        """Return LangChain tools from the requested MCP servers.

        Connects lazily on first access and caches the result.

        Raises:
            ValueError: If a server name is not in the loaded config.
        """
        if not server_names:
            return []

        unknown = [n for n in server_names if n not in self._configs]
        if unknown:
            available = ", ".join(sorted(self._configs)) or "(none)"
            raise ValueError(
                f"Unknown MCP server(s): {', '.join(unknown)}. Available: {available}"
            )

        all_tools: list = []
        for name in server_names:
            if name in self._tools_cache:
                logger.debug(f"MCP '{name}' already connected, reusing")
                all_tools.extend(self._tools_cache[name])
                continue

            tools = await self._connect(name)
            all_tools.extend(tools)

        return all_tools

    def list_servers(self) -> list[str]:
        """Return names of all configured MCP servers."""
        return sorted(self._configs)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _connect(self, name: str) -> list:
        """Connect to *name*, discover tools, and cache them."""
        config = self._configs[name]
        transport = config.get("transport", "?")
        detail = config.get("command", config.get("url", ""))
        logger.info(f"Connecting to MCP server '{name}' ({transport}: {detail})...")

        # Suppress noisy JSONRPC parse errors from npx/uvx install output
        stdio_logger = logging.getLogger("mcp.client.stdio")
        original_level = stdio_logger.level
        stdio_logger.setLevel(logging.CRITICAL)

        client = MultiServerMCPClient({name: config})
        tools = await client.get_tools()

        stdio_logger.setLevel(original_level)

        self._clients[name] = client
        self._tools_cache[name] = tools

        tool_names = [t.name for t in tools]
        logger.info(f"MCP '{name}' ready: {len(tools)} tool(s) ({', '.join(tool_names)})")
        return tools
