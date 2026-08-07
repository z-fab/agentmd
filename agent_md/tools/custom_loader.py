"""Dynamic loader for user-defined custom tools from workspace/agents/tools/."""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

# Cache of loaded tools keyed by (resolved path, mtime_ns).
_TOOL_CACHE: dict[tuple[str, int], list[BaseTool]] = {}


def load_custom_tools(tool_names: list[str], tools_dir: Path) -> list[BaseTool]:
    """Load custom tools by name from the tools directory.

    Each tool is a Python file with one or more ``@tool``-decorated functions
    (LangChain ``BaseTool`` instances). Results are cached by ``(path, mtime)``
    and registered in ``sys.modules`` so reloads pick up file changes.

    Args:
        tool_names: List of tool names (without ``.py`` extension).
        tools_dir: Directory containing custom tool ``.py`` files.

    Returns:
        List of LangChain tool objects found in the specified modules.

    Raises:
        FileNotFoundError: If a tool file does not exist.
        ValueError: If a tool file contains no valid ``@tool`` definitions.
    """
    tools: list[BaseTool] = []

    for name in tool_names:
        tool_file = tools_dir / f"{name}.py"
        if not tool_file.exists():
            raise FileNotFoundError(f"Custom tool '{name}' not found: expected file at {tool_file}")

        resolved = str(tool_file.resolve())
        mtime_ns = tool_file.stat().st_mtime_ns
        cache_key = (resolved, mtime_ns)
        if cache_key in _TOOL_CACHE:
            tools.extend(_TOOL_CACHE[cache_key])
            continue

        module_name = f"agentmd_custom_tool_{name}"
        # Drop stale module so a changed file is re-imported.
        sys.modules.pop(module_name, None)

        spec = importlib.util.spec_from_file_location(module_name, tool_file)
        if spec is None or spec.loader is None:
            raise ValueError(f"Cannot load module from {tool_file}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        found = []
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, BaseTool):
                found.append(attr)

        if not found:
            sys.modules.pop(module_name, None)
            raise ValueError(
                f"Custom tool file '{tool_file.name}' contains no @tool definitions. "
                f"Ensure your functions use the @tool decorator from langchain_core.tools."
            )

        # Invalidate older mtime entries for this path
        for key in list(_TOOL_CACHE):
            if key[0] == resolved and key[1] != mtime_ns:
                del _TOOL_CACHE[key]

        _TOOL_CACHE[cache_key] = found
        logger.info(f"Loaded {len(found)} tool(s) from {tool_file.name}: {[t.name for t in found]}")
        tools.extend(found)

    return tools


def clear_custom_tool_cache() -> None:
    """Clear the in-process custom tool cache (mainly for tests)."""
    _TOOL_CACHE.clear()
