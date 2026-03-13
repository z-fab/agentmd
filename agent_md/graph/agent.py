from agent_md.graph.state import AgentState
from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode


class ReactAgent:
    """Standard ReAct agent: reason → optionally call tools → repeat.

    Usage:
        agent = ReactAgent(chat_model, tools)
        graph = agent.compile()
        result = await graph.ainvoke(initial_state)
    """

    def __init__(self, chat_model: BaseChatModel, tools: list, memory_limit: int | None = None):
        self.model = chat_model.bind_tools(tools) if tools else chat_model
        self.tools = tools
        self.memory_limit = memory_limit

    async def agent(self, state: AgentState) -> dict:
        """LLM node: reasons about the task and decides next action."""
        messages = state["messages"]
        if self.memory_limit is not None:
            # Keep system messages + last N non-system messages
            system_msgs = [m for m in messages if getattr(m, "type", "") == "system"]
            other_msgs = [m for m in messages if getattr(m, "type", "") != "system"]
            messages = system_msgs + other_msgs[-self.memory_limit:]
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
            graph.add_edge("tools", "agent")
        else:
            graph.add_edge("agent", END)

        return graph.compile(checkpointer=checkpointer)
