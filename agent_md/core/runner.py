from __future__ import annotations

import asyncio
import logging
import time

from agent_md.core.execution_logger import ExecutionLogger
from agent_md.core.path_context import PathContext
from agent_md.core.registry import AgentConfig
from agent_md.db.database import Database
from agent_md.graph.builder import create_react_graph, stream_agent_graph, stream_chat_turn
from agent_md.mcp.manager import MCPManager
from agent_md.providers.factory import create_chat_model
from agent_md.tools.custom_loader import load_custom_tools
from agent_md.tools.registry import resolve_builtin_tools

logger = logging.getLogger(__name__)


def _is_final_ai_message(msg) -> bool:
    """Return True if *msg* is an AI message without tool calls (i.e. a text response)."""
    return getattr(msg, "type", "") == "ai" and not (hasattr(msg, "tool_calls") and msg.tool_calls)


class AgentRunner:
    """Executes agents and persists results to the database."""

    def __init__(self, db: Database, mcp_manager: MCPManager, path_context: PathContext, db_path: str | None = None):
        self.db = db
        self.mcp_manager = mcp_manager
        self.path_context = path_context
        self.db_path = db_path  # for creating AsyncSqliteSaver
        self._checkpoint_conns: list = []  # track aiosqlite connections for cleanup

    async def aclose(self):
        """Close any open checkpoint database connections."""
        for conn in self._checkpoint_conns:
            try:
                await conn.close()
            except Exception:
                pass
        self._checkpoint_conns.clear()

    async def _finish_execution(
        self,
        execution_id: int,
        status: str,
        duration_ms: int,
        input_tokens: int,
        output_tokens: int,
        *,
        output_data: str | None = None,
        error: str | None = None,
    ) -> dict:
        """Persist execution result and return a standard result dict."""
        total_tokens = input_tokens + output_tokens
        await self.db.update_execution(
            execution_id=execution_id,
            status=status,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            **({"output_data": output_data} if output_data else {}),
            **({"error": error} if error else {}),
        )
        result = {
            "status": status,
            "duration_ms": duration_ms,
            "execution_id": execution_id,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
        if error:
            result["error"] = error
        return result

    def _build_user_input(self, trigger_type: str, trigger_context: str | None, config: AgentConfig) -> str:
        """Build user input message with trigger context."""
        if trigger_type == "manual":
            return "Execute your task."

        if trigger_type == "schedule":
            if config.trigger.every:
                return f"Execute your task. (scheduled: every {config.trigger.every})"
            elif config.trigger.cron:
                return f"Execute your task. (scheduled: cron {config.trigger.cron})"
            return "Execute your task."

        if trigger_type == "watch" and trigger_context:
            return f"Execute your task.\n\nFile change detected:\n- {trigger_context}"

        return "Execute your task."

    async def _build_graph(self, config: AgentConfig):
        """Create model, resolve tools, and compile the graph."""
        from agent_md.core.models import HISTORY_LIMITS

        chat_model = create_chat_model(
            provider=config.model.provider,
            model=config.model.name,
            settings=config.settings.model_dump(),
            base_url=config.model.base_url,
        )

        tools = resolve_builtin_tools(config, self.path_context)

        if config.custom_tools:
            tools.extend(load_custom_tools(config.custom_tools, self.path_context.tools_dir))

        if config.mcp:
            mcp_tools = await self.mcp_manager.get_tools(config.mcp)
            tools.extend(mcp_tools)
            logger.info(
                f"Resolving tools: {len(tools) - len(mcp_tools)} built-in + "
                f"{len(mcp_tools)} MCP ({', '.join(config.mcp)})"
            )

        # Session memory: create checkpointer if memory level is set
        checkpointer = None
        memory_limit = None
        if config.history != "off" and self.db_path:
            import aiosqlite
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            checkpoint_db = str(self.db_path).replace(".db", "_checkpoints.db")
            conn = await aiosqlite.connect(checkpoint_db)
            checkpointer = AsyncSqliteSaver(conn)
            await checkpointer.setup()
            self._checkpoint_conns.append(conn)
            memory_limit = HISTORY_LIMITS[config.history]
            logger.info(f"Session history enabled: level={config.history}, limit={memory_limit}")

        return create_react_graph(chat_model, tools, checkpointer=checkpointer, memory_limit=memory_limit)

    async def run(self, config: AgentConfig, trigger_type: str = "manual", trigger_context: str | None = None, on_event=None) -> dict:
        """Execute an agent and persist the result.

        Args:
            config: Validated agent configuration.
            trigger_type: What triggered this execution ('manual', 'schedule', 'watch').
            trigger_context: Optional context about what triggered the execution (e.g., file path for watch).
            on_event: Optional callback ``(event_type, data_dict) -> None`` for
                real-time UI updates (Rich console output).

        Returns:
            Dict with 'status', 'output' or 'error', 'duration_ms', and token counts.
        """
        logger.info(f"Starting execution: {config.name} (trigger={trigger_type})")

        # 1. Record execution start
        execution_id = await self.db.create_execution(
            agent_id=config.name,
            trigger=trigger_type,
            status="running",
        )

        ex_logger = ExecutionLogger(self.db, execution_id, config.name, on_event=on_event)
        start_time = time.monotonic()

        # Token accumulators
        total_input_tokens = 0
        total_output_tokens = 0

        try:
            # 2. Build model + tools + graph
            graph = await self._build_graph(config)

            # 3. Build user input with trigger context
            user_input = self._build_user_input(trigger_type, trigger_context, config)

            # 4. Stream execution -- log each message in real time
            last_ai_msg = None
            graph_config = {"configurable": {"thread_id": config.name}} if config.history != "off" else None

            async def _stream():
                nonlocal last_ai_msg, total_input_tokens, total_output_tokens
                async for msg in stream_agent_graph(graph, config.system_prompt, config, self.path_context, user_input=user_input, config=graph_config):
                    await ex_logger.log_message(msg)

                    # Accumulate token usage from every AI message
                    usage = getattr(msg, "usage_metadata", None)
                    if usage:
                        total_input_tokens += usage.get("input_tokens", 0)
                        total_output_tokens += usage.get("output_tokens", 0)

                    if _is_final_ai_message(msg):
                        last_ai_msg = msg

            await asyncio.wait_for(_stream(), timeout=config.settings.timeout)

            duration_ms = int((time.monotonic() - start_time) * 1000)

            # 5. Extract final output
            output = ""
            if last_ai_msg:
                from agent_md.core.execution_logger import _extract_text

                raw_content = getattr(last_ai_msg, "content", None)
                output = _extract_text(raw_content) if raw_content is not None else str(last_ai_msg)
                await ex_logger.mark_final_answer(last_ai_msg)

            # 6. Persist success
            result = await self._finish_execution(
                execution_id, "success", duration_ms,
                total_input_tokens, total_output_tokens,
                output_data=output[:10000],
            )
            result["output"] = output
            logger.info(
                f"Execution complete: {config.name} — success in {duration_ms}ms "
                f"(tokens: {total_input_tokens} in / {total_output_tokens} out / {result['total_tokens']} total)"
            )
            return result

        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            error_msg = f"Timeout after {config.settings.timeout}s"
            logger.warning(f"Execution timeout: {config.name} — {error_msg}")
            return await self._finish_execution(
                execution_id, "timeout", duration_ms,
                total_input_tokens, total_output_tokens,
                error=error_msg,
            )

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            error_msg = f"{type(e).__name__}: {e}"
            logger.error(f"Execution error: {config.name} — {error_msg}")
            return await self._finish_execution(
                execution_id, "error", duration_ms,
                total_input_tokens, total_output_tokens,
                error=error_msg,
            )

    async def prepare_agent(self, config: AgentConfig):
        """Create model, resolve tools, and build graph -- without executing.

        Returns the compiled LangGraph graph, ready for streaming.
        """
        return await self._build_graph(config)

    async def chat_turn(self, graph, messages, ex_logger, timeout, graph_config=None):
        """Stream one chat turn and return (new_messages, input_tokens, output_tokens).

        Args:
            graph: Compiled LangGraph graph from prepare_agent().
            messages: Full conversation history including latest HumanMessage.
            ex_logger: ExecutionLogger for persisting messages.
            timeout: Timeout in seconds.
            graph_config: Optional LangGraph config dict (e.g. thread_id for checkpointing).

        Returns:
            Tuple of (new_messages, input_tokens, output_tokens).
        """
        new_messages = []
        input_tokens = 0
        output_tokens = 0
        last_ai_msg = None

        async def _stream():
            nonlocal input_tokens, output_tokens, last_ai_msg
            async for msg in stream_chat_turn(graph, messages, config=graph_config):
                new_messages.append(msg)
                await ex_logger.log_message(msg)

                usage = getattr(msg, "usage_metadata", None)
                if usage:
                    input_tokens += usage.get("input_tokens", 0)
                    output_tokens += usage.get("output_tokens", 0)

                if _is_final_ai_message(msg):
                    last_ai_msg = msg

        await asyncio.wait_for(_stream(), timeout=timeout)

        if last_ai_msg:
            await ex_logger.mark_final_answer(last_ai_msg)

        return new_messages, input_tokens, output_tokens
