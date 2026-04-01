from agent_md.graph.state import AgentState
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

_TOOL_RESULT_TRUNCATE_THRESHOLD = 500


def _compact_messages(messages: list) -> list:
    """Apply semantic compaction to messages before count-based trimming.

    - skill-context meta messages → skill-breadcrumb (short summary)
    - Large ToolMessage content → truncated summary
    """
    compacted = []
    for msg in messages:
        meta_type = getattr(msg, "additional_kwargs", {}).get("meta_type")

        if meta_type == "skill-context":
            skill_name = msg.additional_kwargs.get("skill_name", "unknown")
            compacted.append(
                HumanMessage(
                    content=f'<skill-breadcrumb name="{skill_name}">Skill {skill_name} was activated in a previous run</skill-breadcrumb>',
                    additional_kwargs={
                        "meta_type": "skill-breadcrumb",
                        "skill_name": skill_name,
                    },
                )
            )
        elif (
            isinstance(msg, ToolMessage)
            and len(msg.content) > _TOOL_RESULT_TRUNCATE_THRESHOLD
        ):
            truncated = (
                msg.content[:200]
                + f"\n\n[truncated — {msg.name} result was {len(msg.content)} chars]"
            )
            compacted.append(
                ToolMessage(
                    content=truncated,
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                )
            )
        else:
            compacted.append(msg)

    return compacted


def _trim_messages(messages: list, limit: int) -> list:
    """Compact and trim messages for the next LLM call.

    Two-phase process:
    1. Semantic compaction — skill-context → breadcrumb, large tool results → truncated
    2. Count-based trimming — keep last N non-system messages
    """
    # Phase 1: semantic compaction
    messages = _compact_messages(messages)

    # Phase 2: count-based trimming
    system_msgs = [m for m in messages if getattr(m, "type", "") == "system"]
    other_msgs = [m for m in messages if getattr(m, "type", "") != "system"]

    if len(other_msgs) <= limit:
        return system_msgs + other_msgs

    start = len(other_msgs) - limit
    trimmed = other_msgs[start:]

    # Walk backward until the window starts with a HumanMessage.
    # Providers like Gemini require a user turn before any AI/tool messages.
    while start > 0 and getattr(trimmed[0], "type", "") != "human":
        start -= 1
        trimmed = [other_msgs[start]] + trimmed

    return system_msgs + trimmed


class ReactAgent:
    """Standard ReAct agent: reason → optionally call tools → repeat.

    Usage:
        agent = ReactAgent(chat_model, tools)
        graph = agent.compile()
        result = await graph.ainvoke(initial_state)
    """

    def __init__(
        self,
        chat_model: BaseChatModel,
        tools: list,
        memory_limit: int | None = None,
        post_tool_processor=None,
    ):
        self.model = chat_model.bind_tools(tools) if tools else chat_model
        self.tools = tools
        self.memory_limit = memory_limit
        self.post_tool_processor = post_tool_processor

    async def agent(self, state: AgentState) -> dict:
        """LLM node: reasons about the task and decides next action."""
        messages = state["messages"]
        if self.memory_limit is not None:
            messages = _trim_messages(messages, self.memory_limit)
        response = await self.model.ainvoke(messages)
        return {"messages": [response]}

    @staticmethod
    def should_continue(state: AgentState) -> str:
        """Route: if the LLM wants to use a tool, go to 'tools'. Otherwise END."""
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    def compile(self, checkpointer=None) -> object:
        """Assemble and compile the ReAct graph.

        Args:
            checkpointer: Optional LangGraph checkpointer for session memory.

        Returns:
            A compiled LangGraph StateGraph ready for ainvoke().
        """
        graph = StateGraph(AgentState)

        # Nodes
        graph.add_node("agent", self.agent)
        if self.tools:
            graph.add_node("tools", ToolNode(self.tools))
            if self.post_tool_processor:
                graph.add_node("post_tool_processor", self.post_tool_processor)

        # Edges
        graph.set_entry_point("agent")
        if self.tools:
            graph.add_conditional_edges(
                "agent",
                self.should_continue,
                {
                    "tools": "tools",
                    END: END,
                },
            )
            if self.post_tool_processor:
                graph.add_edge("tools", "post_tool_processor")
                graph.add_edge("post_tool_processor", "agent")
            else:
                graph.add_edge("tools", "agent")
        else:
            graph.add_edge("agent", END)

        return graph.compile(checkpointer=checkpointer)
