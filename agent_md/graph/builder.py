from __future__ import annotations

from datetime import datetime
from typing import AsyncGenerator

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent_md.graph.agent import ReactAgent
from agent_md.graph.state import AgentState


def create_react_graph(chat_model, tools, checkpointer=None, memory_limit=None):
    """Create a compiled ReAct graph for a single agent.

    Convenience wrapper around ReactAgent.compile().

    Args:
        chat_model: A LangChain ChatModel instance (already configured).
        tools: List of LangChain tool objects available to this agent.
        checkpointer: Optional LangGraph checkpointer for session memory.
        memory_limit: Optional max number of non-system messages to send to the LLM.

    Returns:
        A compiled LangGraph StateGraph ready for ainvoke().
    """
    agent = ReactAgent(chat_model, tools, memory_limit=memory_limit)
    return agent.compile(checkpointer=checkpointer)


def _build_file_access_prompt(agent_config, path_context) -> str:
    """Build the file access section of the system prompt."""
    allowed_paths = path_context.get_allowed_paths(agent_config)
    write_target = path_context.get_default_write_dir(agent_config)
    workspace = path_context.workspace_root

    path_list = "\n".join(f"- `{p}`" for p in allowed_paths)

    sections = [
        "## File Access\n",
        "You have three file tools: `file_read`, `file_write`, and `file_list`.\n",
        "### Allowed paths\n",
        "You can ONLY access files within these paths:\n",
        f"{path_list}\n",
        "Any path outside these boundaries will be denied.\n",
        "### Path Resolution Rules\n",
        f"- **Workspace root**: `{workspace}` — all relative paths are resolved from here.\n",
        "- **Absolute paths** (e.g., `/data/file.txt`): Used as-is, but must be within allowed paths above.\n",
        f"- **Relative paths** (e.g., `file.txt`, `data/file.txt`): Always resolve from workspace root: `{workspace}`\n",
        f"- **Write target for `file_write`**: Relative paths default to: `{write_target}`\n",
        "  - This is the first directory in your allowed paths (or workspace if no paths defined).\n",
        f"  - Do NOT prefix with `{write_target.name}/` unless you want a subdirectory — it is added automatically.\n",
        "- **Best practice**: Use `file_list` first to discover the correct paths. Never guess filenames.\n",
    ]

    if agent_config.trigger.type == "watch":
        sections.append(
            "\n### Watch Trigger\n"
            "This agent is activated by file changes. The user message contains "
            "the **absolute path** of the changed file.\n"
            "**You MUST use that exact absolute path** with `file_read` to read the file. "
            "Do not extract just the filename — always use the full path provided."
        )

    return "\n".join(sections)


def build_system_message(
    system_prompt: str,
    agent_config=None,
    path_context=None,
) -> SystemMessage:
    """Build the system message for an agent, shared by run and chat modes.

    Args:
        system_prompt: The agent's system prompt (from .md body).
        agent_config: AgentConfig for path context injection.
        path_context: PathContext for path resolution.

    Returns:
        A SystemMessage with date/time info, file access context, and system prompt.
    """
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

    full_prompt = f"{extra_info}\n\n{system_prompt}"
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


def _build_initial_state(
    system_prompt: str,
    agent_config=None,
    path_context=None,
    user_input: str = "Execute your task.",
) -> AgentState:
    """Build the initial state dict for graph execution."""
    system_msg = build_system_message(system_prompt, agent_config, path_context)
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
    initial_state = _build_initial_state(system_prompt, agent_config, path_context, user_input)
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
    initial_state = _build_initial_state(system_prompt, agent_config, path_context, user_input)
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
