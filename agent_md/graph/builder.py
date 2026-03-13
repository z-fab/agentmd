from __future__ import annotations

from datetime import datetime
from typing import AsyncGenerator

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent_md.graph.agent import ReactAgent
from agent_md.graph.state import AgentState


def create_react_graph(chat_model, tools):
    """Create a compiled ReAct graph for a single agent.

    Convenience wrapper around ReactAgent.compile().

    Args:
        chat_model: A LangChain ChatModel instance (already configured).
        tools: List of LangChain tool objects available to this agent.

    Returns:
        A compiled LangGraph StateGraph ready for ainvoke().
    """
    agent = ReactAgent(chat_model, tools)
    return agent.compile()


def _build_file_access_prompt(agent_config, path_context) -> str:
    """Build the file access section of the system prompt."""
    read_paths = path_context.get_read_paths(agent_config)
    write_paths = path_context.get_write_paths(agent_config)
    default_write = path_context.get_default_write_dir(agent_config)

    read_list = "\n".join(f"- {p}" for p in read_paths)
    write_list = "\n".join(f"- {p}" for p in write_paths)

    return (
        f"## File Access\n\n"
        f"You have access to file tools with the following permissions:\n\n"
        f"READ (you can read files from):\n{read_list}\n\n"
        f"WRITE (you can create and save files to):\n{write_list}\n\n"
        f"When saving files, use just the filename or a relative sub-path (e.g., 'report.txt', 'data/file.json'). "
        f"Do NOT prefix paths with '{default_write.name}/' — files are automatically saved to: {default_write}\n"
        f"Do not attempt to access files outside these directories."
    )


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

    full_prompt = f"{extra_info}\n\n{system_prompt}"
    return SystemMessage(content=full_prompt)


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


async def _stream_state(graph, state: dict) -> AsyncGenerator[BaseMessage, None]:
    """Stream graph execution from a state dict, yielding each message."""
    async for step in graph.astream(state):
        for _node_name, node_output in step.items():
            for msg in node_output.get("messages", []):
                yield msg


async def stream_agent_graph(
    graph,
    system_prompt: str,
    agent_config=None,
    path_context=None,
    user_input: str = "Execute your task.",
) -> AsyncGenerator[BaseMessage, None]:
    """Stream graph execution, yielding each message as it is produced.

    Args:
        graph: A compiled LangGraph graph.
        system_prompt: The agent's system prompt (from .md body).
        agent_config: AgentConfig for path context injection.
        path_context: PathContext for path resolution.
        user_input: The user/trigger message.

    Yields:
        Individual LangChain BaseMessage objects as they are emitted.
    """
    initial_state = _build_initial_state(system_prompt, agent_config, path_context, user_input)
    async for msg in _stream_state(graph, initial_state):
        yield msg


async def stream_chat_turn(
    graph,
    messages: list[BaseMessage],
) -> AsyncGenerator[BaseMessage, None]:
    """Stream one chat turn from a pre-built messages list.

    Unlike ``stream_agent_graph``, this does not build initial state --
    it takes an existing conversation (system + history + new human message)
    and streams the agent's response.

    Args:
        graph: A compiled LangGraph graph.
        messages: Full conversation history including the latest HumanMessage.

    Yields:
        Individual LangChain BaseMessage objects as they are emitted.
    """
    async for msg in _stream_state(graph, {"messages": messages}):
        yield msg
