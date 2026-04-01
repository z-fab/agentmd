"""Dynamic loader for user-defined custom tools from workspace/agents/tools/."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


def load_custom_tools(tool_names: list[str], tools_dir: Path) -> list[BaseTool]:
    """Load custom tools by name from the tools directory.

    Each tool is a Python file with one or more ``@tool``-decorated functions
    (LangChain ``BaseTool`` instances).

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

        # Dynamically import the module
        spec = importlib.util.spec_from_file_location(f"custom_tool_{name}", tool_file)
        if spec is None or spec.loader is None:
            raise ValueError(f"Cannot load module from {tool_file}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find all BaseTool instances in the module
        found = []
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, BaseTool):
                found.append(attr)

        if not found:
            raise ValueError(
                f"Custom tool file '{tool_file.name}' contains no @tool definitions. "
                f"Ensure your functions use the @tool decorator from langchain_core.tools."
            )

        logger.info(f"Loaded {len(found)} tool(s) from {tool_file.name}: {[t.name for t in found]}")
        tools.extend(found)

    return tools
