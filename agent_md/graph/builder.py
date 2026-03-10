from datetime import datetime
from typing import AsyncGenerator

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent_md.core.settings import settings
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


def _build_initial_state(
    system_prompt: str,
    user_input: str = "Execute your task.",
) -> AgentState:
    """Build the initial state dict for graph execution."""
    extra_info = (
        f"Today is {datetime.now().strftime('%Y-%m-%d')}. "
        f"It is {datetime.now().strftime('%A')}, {datetime.now().strftime('%HH:%MM:%SS %Z')}.\n"
        f"The default output directory is {settings.OUTPUT_DIR}. "
        f"If a path is not specified for saving files, use the default output directory. NEVER save files to the current working directory unless explicitly told to do so."
    )
    full_prompt = f"{extra_info}\n\n{system_prompt}"

    return {
        "messages": [
            SystemMessage(content=full_prompt),
            HumanMessage(content=user_input),
        ]
    }


async def run_agent_graph(
    graph,
    system_prompt: str,
    user_input: str = "Execute your task.",
) -> dict:
    """Execute a compiled graph with the given prompts.

    Args:
        graph: A compiled LangGraph graph.
        system_prompt: The agent's system prompt (from .md body).
        user_input: The user/trigger message.

    Returns:
        The final state dict with all messages.
    """
    initial_state = _build_initial_state(system_prompt, user_input)
    return await graph.ainvoke(initial_state)


async def stream_agent_graph(
    graph,
    system_prompt: str,
    user_input: str = "Execute your task.",
) -> AsyncGenerator[BaseMessage, None]:
    """Stream graph execution, yielding each message as it is produced.

    Args:
        graph: A compiled LangGraph graph.
        system_prompt: The agent's system prompt (from .md body).
        user_input: The user/trigger message.

    Yields:
        Individual LangChain BaseMessage objects as they are emitted.
    """
    initial_state = _build_initial_state(system_prompt, user_input)

    async for step in graph.astream(initial_state):
        for _node_name, node_output in step.items():
            for msg in node_output.get("messages", []):
                yield msg
