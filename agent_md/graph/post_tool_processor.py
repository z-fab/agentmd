"""Post-tool processor node — injects meta messages after tool execution.

Sits between the 'tools' and 'agent' nodes in the ReAct graph.
Currently handles skill activation; designed to be extended for future
meta message types (e.g., memory directives).
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage, ToolMessage

from agent_md.graph.state import AgentState
from agent_md.tools.skills._resolver import resolve_skill_content


def create_post_tool_processor(agent_config, skills_dir: Path):
    """Create a post_tool_processor node function with agent context.

    Args:
        agent_config: AgentConfig for skill validation.
        skills_dir: Root skills directory.

    Returns:
        A function suitable for use as a LangGraph node.
    """

    def post_tool_processor(state: AgentState) -> dict:
        """Inspect tool results and inject meta messages when needed."""
        messages = state["messages"]
        new_messages: list = []

        # Find the most recent AIMessage with tool_calls to get the args
        last_ai = None
        for msg in reversed(messages):
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                last_ai = msg
                break

        if not last_ai:
            return {"messages": []}

        # Build a map of tool_call_id → tool_call args
        call_map = {tc["id"]: tc for tc in last_ai.tool_calls}

        # Check each recent ToolMessage for skill_use
        for msg in reversed(messages):
            if not isinstance(msg, ToolMessage):
                continue
            # Stop when we hit a ToolMessage not in our current batch
            if msg.tool_call_id not in call_map:
                break

            call = call_map.get(msg.tool_call_id)
            if not call or call["name"] != "skill_use":
                continue

            skill_name = call["args"].get("skill_name", "")
            arguments = call["args"].get("arguments", "")

            content = resolve_skill_content(skill_name, arguments, agent_config, skills_dir)
            if content is None:
                continue

            meta_msg = HumanMessage(
                content=f'<skill-context name="{skill_name}">\n{content}\n</skill-context>',
                additional_kwargs={
                    "meta_type": "skill-context",
                    "skill_name": skill_name,
                },
            )
            new_messages.append(meta_msg)

        return {"messages": new_messages}

    return post_tool_processor
