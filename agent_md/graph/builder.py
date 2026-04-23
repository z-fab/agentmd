from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import AsyncGenerator

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent_md.graph.agent import ReactAgent
from agent_md.graph.state import AgentState

logger = logging.getLogger(__name__)


def create_react_graph(chat_model, tools, checkpointer=None, memory_limit=None, post_tool_processor=None):
    """Create a compiled ReAct graph for a single agent.

    Convenience wrapper around ReactAgent.compile().

    Args:
        chat_model: A LangChain ChatModel instance (already configured).
        tools: List of LangChain tool objects available to this agent.
        checkpointer: Optional LangGraph checkpointer for session memory.
        memory_limit: Optional max number of non-system messages to send to the LLM.
        post_tool_processor: Optional node function to run after tool execution.

    Returns:
        A compiled LangGraph StateGraph ready for ainvoke().
    """
    agent = ReactAgent(chat_model, tools, memory_limit=memory_limit, post_tool_processor=post_tool_processor)
    return agent.compile(checkpointer=checkpointer)


def compute_recursion_limit(max_tool_calls: int | None, has_post_tool_processor: bool) -> int:
    """Derive LangGraph recursion_limit from max_tool_calls.

    Each tool call cycle = 2 graph steps (agent→tools) or 3 with post_tool_processor.
    LangGraph's default of 25 is too low for agents with max_tool_calls=50.
    """
    if max_tool_calls is None:
        return 100
    steps_per_cycle = 3 if has_post_tool_processor else 2
    return max_tool_calls * steps_per_cycle + 5


def _build_file_access_prompt(agent_config, path_context) -> str:
    """Build the file access section of the system prompt.

    Lists alias names (no absolute paths) and explains the path syntax
    accepted by all file tools.
    """
    sections = [
        "## File Access\n",
        "You have four file tools: `file_read`, `file_write`, `file_edit`, and `file_glob`.\n",
    ]

    if agent_config.paths:
        sections.append("### Available paths\n")
        sections.append("You can reference these locations using `{alias}` syntax in any file tool:\n")
        for alias, entry in agent_config.paths.items():
            desc = f" — {entry.description}" if entry.description else ""
            sections.append(f"- `{{{alias}}}`{desc}\n")
        sections.append('Example: `file_read("{' + next(iter(agent_config.paths)) + '}/notes/x.md")`\n')
    else:
        sections.append("### Allowed paths\n")
        sections.append("This agent has no `paths` declared. File access is limited to the workspace root.\n")

    sections.append(
        "### Path rules\n"
        "- Use `{alias}/sub` to reference a declared path location.\n"
        "- Absolute paths (e.g. `/Users/.../x.md`) work if they fall inside a declared path.\n"
        "- Relative paths resolve from the workspace root.\n"
        "- Use `file_glob` to discover files before reading. Never guess filenames.\n"
        "- **Always read a file with `file_read` before modifying it** with `file_edit` or overwriting with `file_write`.\n"
    )
    sections.append(
        "### Tool usage\n"
        "- `file_read(path)`: Read a file. Supports `offset` and `limit` for line ranges.\n"
        "- `file_edit(path, old_text, new_text)`: Targeted text replacement.\n"
        "- `file_write(path, content)`: Create or fully overwrite a file.\n"
        "- `file_glob(pattern)`: Find files matching a glob pattern."
    )

    if agent_config.trigger.type == "watch":
        sections.append(
            "\n### Watch trigger\n"
            "This agent is activated by file changes. The user message contains the event type "
            "and the **absolute path** of the changed file.\n"
            "**You MUST use that exact absolute path** with `file_read` to read the file."
        )

    return "\n".join(sections)


def build_system_message(
    system_prompt: str,
    agent_config=None,
    path_context=None,
    arguments: list[str] | str = "",
    **kwargs,
) -> SystemMessage:
    """Build the system message for an agent, shared by run and chat modes."""
    from agent_md.config.substitutions import apply_substitutions

    now = datetime.now()
    extra_info = f"Today is {now.strftime('%Y-%m-%d')}. It is {now.strftime('%A')}, {now.strftime('%H:%M:%S %Z')}.\n"

    if agent_config and path_context:
        extra_info += "\n" + _build_file_access_prompt(agent_config, path_context)
        memory_prompt = _build_memory_prompt(agent_config, path_context)
        if memory_prompt:
            extra_info += "\n\n" + memory_prompt
        skills_prompt = _build_skills_prompt(agent_config, path_context)
        if skills_prompt:
            extra_info += "\n\n" + skills_prompt
        if agent_config.skills:
            extra_info += "\n\n" + _build_meta_messages_prompt()

        agents_prompt = _build_agents_prompt(agent_config, kwargs.get("registry"))
        if agents_prompt:
            extra_info += "\n\n" + agents_prompt

    full_prompt = f"{extra_info}\n\n{system_prompt}"

    cwd = str(path_context.workspace_root) if path_context else None
    full_prompt = apply_substitutions(full_prompt, arguments=arguments, cwd=cwd)

    if arguments and not re.search(r"\$(?:ARGUMENTS|\d)", system_prompt):
        logger.warning(
            "Arguments passed to agent '%s' but prompt contains no $ARGUMENTS or $0..$9 placeholders",
            agent_config.name if agent_config else "unknown",
        )

    return SystemMessage(content=full_prompt)


def _build_memory_prompt(agent_config, path_context) -> str:
    """Build the long-term memory section of the system prompt.

    Lists available memory sections so the agent knows what it can retrieve.
    """
    memory_path = path_context.get_memory_file_path(agent_config)

    if not memory_path.exists():
        return (
            "## Long-term Memory\n\n"
            "You have access to long-term memory tools (memory_save, memory_append, memory_retrieve). "
            "No memory file exists yet. Use memory_save to start persisting information across sessions."
        )

    try:
        content = memory_path.read_text(encoding="utf-8")
    except Exception:
        return ""

    # Extract section names from headers
    sections = [line[2:].strip() for line in content.split("\n") if line.startswith("# ")]

    if not sections:
        return (
            "## Long-term Memory\n\n"
            "You have a memory file but it has no sections yet. "
            "Use memory_save to start persisting information."
        )

    section_list = "\n".join(f"- {s}" for s in sections)
    return (
        "## Long-term Memory\n\n"
        "You have the following memory sections available. "
        "Use memory_retrieve to read their contents, memory_save to replace, and memory_append to add.\n\n"
        f"Available sections:\n{section_list}"
    )


def _build_skills_prompt(agent_config, path_context) -> str:
    """Build the skills section of the system prompt (tier 1 — descriptions only).

    Lists available skills so the agent knows what it can load via skill_use.
    """
    if not agent_config.skills:
        return ""

    skills_dir = path_context.skills_dir
    if not skills_dir.exists():
        return ""

    from agent_md.skills.parser import parse_skill_metadata

    skill_entries = []
    for skill_name in agent_config.skills:
        skill_file = skills_dir / skill_name / "SKILL.md"
        if not skill_file.exists():
            continue
        try:
            config = parse_skill_metadata(skill_file)
            hint = f" {config.argument_hint}" if config.argument_hint else ""
            desc = config.description or "No description"
            skill_entries.append(f"- **{config.name}**{hint}: {desc}")
        except Exception:
            skill_entries.append(f"- **{skill_name}**: [error loading skill]")

    if not skill_entries:
        return ""

    skill_list = "\n".join(skill_entries)
    return (
        "## Available Skills\n\n"
        "You have access to the following skills. "
        "Use the `skill_use` tool to load a skill's full instructions when needed.\n\n"
        f"{skill_list}"
    )


def _build_agents_prompt(agent_config, registry) -> str:
    """Build the available agents section of the system prompt."""
    if not agent_config.agents:
        return ""
    if registry is None:
        return ""

    entries = []
    for name in agent_config.agents:
        config = registry.get(name)
        if config and config.enabled:
            desc = config.description or "No description"
            entries.append(f"- **{name}**: {desc}")

    if not entries:
        return ""

    agents_list = "\n".join(entries)
    return (
        "## Available Agents\n\n"
        "You can call other agents using the `run_agent` tool. "
        "Pass the agent name and optional arguments.\n\n"
        f"{agents_list}"
    )


def _build_meta_messages_prompt() -> str:
    """Build the meta messages section of the system prompt."""
    return (
        "## Meta Messages\n\n"
        "During this session, you may receive messages wrapped in special tags. "
        "These are system-injected directives — treat them as instructions to follow, "
        "not as user conversation.\n\n"
        '- `<skill-context name="...">`: A skill has been activated. '
        "Follow the instructions inside exactly.\n"
        '- `<skill-breadcrumb name="...">`: A skill was activated in a previous run. '
        "Noted for context only."
    )


def _build_initial_state(
    system_prompt: str,
    agent_config=None,
    path_context=None,
    user_input: str = "Execute your task.",
    arguments: list[str] | str = "",
    **kwargs,
) -> AgentState:
    """Build the initial state dict for graph execution."""
    system_msg = build_system_message(system_prompt, agent_config, path_context, arguments=arguments, **kwargs)
    return {
        "messages": [
            system_msg,
            HumanMessage(content=user_input),
        ]
    }


async def run_agent_graph(
    graph,
    system_prompt: str,
    agent_config=None,
    path_context=None,
    user_input: str = "Execute your task.",
    arguments: list[str] | str = "",
    **kwargs,
) -> dict:
    """Execute a compiled graph with the given prompts.

    Args:
        graph: A compiled LangGraph graph.
        system_prompt: The agent's system prompt (from .md body).
        agent_config: AgentConfig for path context injection.
        path_context: PathContext for path resolution.
        user_input: The user/trigger message.

    Returns:
        The final state dict with all messages.
    """
    initial_state = _build_initial_state(system_prompt, agent_config, path_context, user_input, arguments, **kwargs)
    return await graph.ainvoke(initial_state)


async def _stream_state(graph, state: dict, config: dict | None = None) -> AsyncGenerator[BaseMessage, None]:
    """Stream graph execution from a state dict, yielding each message."""
    async for step in graph.astream(state, config=config or {}):
        for _node_name, node_output in step.items():
            for msg in node_output.get("messages", []):
                yield msg


async def stream_agent_graph(
    graph,
    system_prompt: str,
    agent_config=None,
    path_context=None,
    user_input: str = "Execute your task.",
    config: dict | None = None,
    arguments: list[str] | str = "",
    **kwargs,
) -> AsyncGenerator[BaseMessage, None]:
    """Stream graph execution, yielding each message as it is produced.

    Args:
        graph: A compiled LangGraph graph.
        system_prompt: The agent's system prompt (from .md body).
        agent_config: AgentConfig for path context injection.
        path_context: PathContext for path resolution.
        user_input: The user/trigger message.
        config: Optional LangGraph config dict (e.g. thread_id for checkpointing).

    Yields:
        Individual LangChain BaseMessage objects as they are emitted.
    """
    initial_state = _build_initial_state(system_prompt, agent_config, path_context, user_input, arguments, **kwargs)
    async for msg in _stream_state(graph, initial_state, config=config):
        yield msg


async def stream_chat_turn(
    graph,
    messages: list[BaseMessage],
    config: dict | None = None,
) -> AsyncGenerator[BaseMessage, None]:
    """Stream one chat turn from a pre-built messages list.

    Unlike ``stream_agent_graph``, this does not build initial state --
    it takes an existing conversation (system + history + new human message)
    and streams the agent's response.

    Args:
        graph: A compiled LangGraph graph.
        messages: Full conversation history including the latest HumanMessage.
        config: Optional LangGraph config dict (e.g. thread_id for checkpointing).

    Yields:
        Individual LangChain BaseMessage objects as they are emitted.
    """
    async for msg in _stream_state(graph, {"messages": messages}, config=config):
        yield msg
