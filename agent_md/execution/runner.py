from __future__ import annotations

import asyncio
import logging
import sys
import time

from agent_md.execution.logger import ExecutionLogger, _extract_text
from agent_md.sdk import _set_context, _reset_context
from agent_md.workspace.path_context import PathContext
from agent_md.config.pricing import estimate_cost
from agent_md.workspace.registry import AgentConfig
from agent_md.db.database import Database
from agent_md.graph.builder import create_react_graph, stream_agent_graph, stream_chat_turn
from agent_md.mcp.manager import MCPManager
from agent_md.providers.factory import create_chat_model
from agent_md.tools.custom_loader import load_custom_tools
from agent_md.graph.post_tool_processor import create_post_tool_processor
from agent_md.tools.registry import resolve_builtin_tools

logger = logging.getLogger(__name__)

_COMPLETE_SEQ = sys.maxsize  # ensures complete event is never filtered by SSE dedup


class LimitExceeded(Exception):
    """Raised when an execution limit is hit."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _check_limits(settings, tool_call_count: int, total_tokens: int, cost_usd: float | None = None) -> None:
    """Raise LimitExceeded if any hard limit is breached."""
    if settings.max_tool_calls is not None and tool_call_count > settings.max_tool_calls:
        raise LimitExceeded("max_tool_calls", f"{tool_call_count} calls (limit: {settings.max_tool_calls})")

    if settings.max_execution_tokens is not None and total_tokens > settings.max_execution_tokens:
        raise LimitExceeded(
            "max_execution_tokens",
            f"{total_tokens:,} tokens (limit: {settings.max_execution_tokens:,})",
        )

    if settings.max_cost_usd is not None and cost_usd is not None and cost_usd > settings.max_cost_usd:
        raise LimitExceeded("max_cost_usd", f"${cost_usd:.4f} (limit: ${settings.max_cost_usd:.2f})")


def _looks_like_error(msg) -> bool:
    """Return True if a tool response looks like an error."""
    if getattr(msg, "type", "") != "tool":
        return False
    content = str(getattr(msg, "content", ""))
    return content.startswith(("ERROR:", "Error:", "Exception"))


def _normalize_error(content: str) -> str:
    """Extract a stable signature from an error message."""
    first_line = content.strip().split("\n", 1)[0]
    return first_line[:200]


def _is_final_ai_message(msg) -> bool:
    """Return True if *msg* is an AI message without tool calls (i.e. a text response)."""
    return getattr(msg, "type", "") == "ai" and not (hasattr(msg, "tool_calls") and msg.tool_calls)


def _classify_event_type(msg) -> str:
    """Map a LangChain message to an SSE event type.

    Returns one of: ai, tool_call, tool_result, meta, human, system.
    These match the event types used by _print_event in the CLI.
    """
    meta_type = getattr(msg, "additional_kwargs", {}).get("meta_type")
    if meta_type:
        return "meta"
    msg_type = getattr(msg, "type", "unknown")
    if msg_type == "ai" and hasattr(msg, "tool_calls") and msg.tool_calls:
        return "tool_call"
    if msg_type == "tool":
        return "tool_result"
    # Preserve original type (ai, human, system) for correct CLI display
    return msg_type


def _build_event_data(msg, event_type: str, agent_name: str) -> dict:
    """Build structured event data for the EventBus, including tool details."""
    content = _extract_text(getattr(msg, "content", ""))[:500]
    data: dict = {"event_type": event_type, "agent_name": agent_name}

    if event_type == "tool_call" and hasattr(msg, "tool_calls") and msg.tool_calls:
        tools = []
        for tc in msg.tool_calls:
            tools.append(
                {
                    "name": tc.get("name", "unknown"),
                    "args": str(tc.get("args", {}))[:200],
                }
            )
        data["tools"] = tools
        if content:
            data["content"] = content
    elif event_type == "tool_result":
        data["tool_name"] = getattr(msg, "name", "unknown")
        data["content"] = content[:200]
    else:
        data["content"] = content

    return data


class AgentRunner:
    """Executes agents and persists results to the database."""

    def __init__(
        self,
        db: Database,
        mcp_manager: MCPManager,
        path_context: PathContext,
        db_path: str | None = None,
        registry=None,
    ):
        self.db = db
        self.mcp_manager = mcp_manager
        self.path_context = path_context
        self.db_path = db_path  # for creating AsyncSqliteSaver
        self.registry = registry
        self._checkpoint_conns: list = []  # track aiosqlite connections for cleanup

    @property
    def _max_agent_depth(self) -> int:
        try:
            from agent_md.config.settings import settings

            return settings.defaults_max_agent_depth
        except Exception:
            return 3

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
        cost_usd: float | None = None,
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
            cost_usd=cost_usd,
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
        if cost_usd is not None:
            result["cost_usd"] = cost_usd
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
            # Parse the context string to extract event type and path
            parts = trigger_context.split(": ", 1)
            if len(parts) == 2:
                event_type, file_path = parts
                return (
                    f"A file change was detected. Process it now.\n\n"
                    f"- Event: `{event_type}`\n"
                    f"- File: `{file_path}`\n\n"
                    f'Start by calling `file_read("{file_path}")` with the exact absolute path above.'
                )
            return f"A file change was detected. Process it now.\n\n- {trigger_context}"

        if trigger_type == "agent" and trigger_context:
            return f"Execute your task. ({trigger_context})"

        return "Execute your task."

    async def _build_graph(self, config: AgentConfig, **tool_kwargs):
        """Create model, resolve tools, and compile the graph."""
        from agent_md.config.models import HISTORY_LIMITS

        chat_model = create_chat_model(
            provider=config.model.provider,
            model=config.model.name,
            settings=config.settings.model_dump(),
            base_url=config.model.base_url,
        )

        tools = resolve_builtin_tools(config, self.path_context, **tool_kwargs)

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

        # Create post-tool processor for skill meta message injection
        post_processor = None
        if config.skills and self.path_context and self.path_context.skills_dir.exists():
            post_processor = create_post_tool_processor(config, self.path_context.skills_dir)

        return create_react_graph(
            chat_model, tools, checkpointer=checkpointer, memory_limit=memory_limit, post_tool_processor=post_processor
        )

    async def run(
        self,
        config: AgentConfig,
        trigger_type: str = "manual",
        trigger_context: str | None = None,
        on_event=None,
        on_start=None,
        on_complete=None,
        arguments: str = "",
        event_bus=None,
        global_event_bus=None,
        cancel_event: asyncio.Event | None = None,
        execution_id: int | None = None,
        user_message: str | None = None,
        depth: int = 0,
        parent_execution_id: int | None = None,
    ) -> dict:
        """Execute an agent and persist the result.

        Args:
            config: Validated agent configuration.
            trigger_type: What triggered this execution ('manual', 'schedule', 'watch').
            trigger_context: Optional context about what triggered the execution (e.g., file path for watch).
            on_event: Optional callback ``(event_type, data_dict) -> None`` for
                real-time UI updates (Rich console output).
            on_start: Optional callback ``(agent_name, model_info) -> None``
                called before execution begins.
            on_complete: Optional callback ``(agent_name, result_dict) -> None``
                called after execution finishes (success, error, or timeout).

        Returns:
            Dict with 'status', 'output' or 'error', 'duration_ms', and token counts.
        """
        logger.info(f"Starting execution: {config.name} (trigger={trigger_type})")

        if on_start is not None:
            model_info = f"{config.model.provider} / {config.model.name}" if config.model else "default"
            on_start(config.name, model_info)

        # 1. Record execution start
        if execution_id is None:
            execution_id = await self.db.create_execution(
                agent_id=config.name,
                trigger=trigger_type,
                status="running",
                parent_execution_id=parent_execution_id,
            )

        ex_logger = ExecutionLogger(self.db, execution_id, config.name, on_event=on_event)

        if global_event_bus is not None:
            await global_event_bus.publish(
                {
                    "type": "execution_started",
                    "data": {
                        "execution_id": execution_id,
                        "agent_name": config.name,
                        "trigger": trigger_type,
                    },
                }
            )

        start_time = time.monotonic()

        # Token accumulators
        total_input_tokens = 0
        total_output_tokens = 0
        tool_call_count = 0
        cost_usd: float | None = None
        _pricing_warned = False
        last_errors: list[tuple[str, str]] = []  # (tool_name, normalized_error)

        sdk_token = _set_context(config, self.path_context)
        try:
            try:
                # 2. Build model + tools + graph
                graph = await self._build_graph(
                    config,
                    registry=self.registry,
                    runner=self,
                    depth=depth,
                    max_depth=self._max_agent_depth,
                    parent_execution_id=execution_id,
                    event_bus=event_bus,
                    global_event_bus=global_event_bus,
                )

                # 3. Build user input with trigger context
                user_input = self._build_user_input(trigger_type, trigger_context, config)
                if user_message:
                    user_input = user_message

                # 3b. Log the constructed system prompt and user input
                from agent_md.graph.builder import build_system_message

                sys_msg = build_system_message(
                    config.system_prompt,
                    config,
                    self.path_context,
                    arguments=arguments,
                    registry=self.registry,
                )
                await ex_logger.log_message(sys_msg)
                from langchain_core.messages import HumanMessage as _HM

                await ex_logger.log_message(_HM(content=user_input))

                # 4. Stream execution -- log each message in real time
                last_ai_msg = None
                graph_config = {"configurable": {"thread_id": config.name}} if config.history != "off" else None

                async def _stream():
                    nonlocal \
                        last_ai_msg, \
                        total_input_tokens, \
                        total_output_tokens, \
                        tool_call_count, \
                        cost_usd, \
                        _pricing_warned, \
                        last_errors
                    async for msg in stream_agent_graph(
                        graph,
                        config.system_prompt,
                        config,
                        self.path_context,
                        user_input=user_input,
                        config=graph_config,
                        arguments=arguments,
                        registry=self.registry,
                    ):
                        log_id = await ex_logger.log_message(msg)

                        if event_bus is not None:
                            event_type = _classify_event_type(msg)
                            event_data = _build_event_data(msg, event_type, config.name)
                            await event_bus.publish(
                                execution_id,
                                {"type": event_type, "seq": log_id, "data": event_data},
                            )

                        if cancel_event is not None and cancel_event.is_set():
                            raise LimitExceeded("cancelled", "Execution cancelled by user")

                        # Accumulate token usage from every AI message
                        usage = getattr(msg, "usage_metadata", None)
                        if usage:
                            total_input_tokens += usage.get("input_tokens", 0)
                            total_output_tokens += usage.get("output_tokens", 0)

                        # Count tool calls
                        if getattr(msg, "type", "") == "ai" and hasattr(msg, "tool_calls") and msg.tool_calls:
                            tool_call_count += len(msg.tool_calls)

                        # Estimate running cost
                        if usage:
                            cost_usd = estimate_cost(
                                config.model.provider,
                                config.model.name,
                                total_input_tokens,
                                total_output_tokens,
                            )

                        # Warn once if cost limit is set but pricing is unknown
                        if (
                            not _pricing_warned
                            and config.settings.max_cost_usd is not None
                            and cost_usd is None
                            and (total_input_tokens + total_output_tokens) > 0
                        ):
                            logger.warning(
                                f"max_cost_usd configured but no pricing data for "
                                f"{config.model.provider}/{config.model.name}; limit will not be enforced"
                            )
                            _pricing_warned = True

                        _check_limits(
                            config.settings, tool_call_count, total_input_tokens + total_output_tokens, cost_usd
                        )

                        # Loop detection: same tool error 3 consecutive times
                        if config.settings.loop_detection and getattr(msg, "type", "") == "tool":
                            if _looks_like_error(msg):
                                sig = (getattr(msg, "name", ""), _normalize_error(str(getattr(msg, "content", ""))))
                                last_errors.append(sig)
                                if len(last_errors) > 3:
                                    last_errors.pop(0)
                                if len(last_errors) == 3 and len(set(last_errors)) == 1:
                                    raise LimitExceeded(
                                        "loop_detected",
                                        f"{sig[0]} returned the same error 3 times: {sig[1][:100]}",
                                    )
                            else:
                                last_errors.clear()  # Reset on successful tool response

                        if _is_final_ai_message(msg):
                            last_ai_msg = msg

                await asyncio.wait_for(_stream(), timeout=config.settings.timeout)

                duration_ms = int((time.monotonic() - start_time) * 1000)

                # 5. Extract final output
                output = ""
                if last_ai_msg:
                    raw_content = getattr(last_ai_msg, "content", None)
                    output = _extract_text(raw_content) if raw_content is not None else str(last_ai_msg)
                    log_id = await ex_logger.mark_final_answer(last_ai_msg)
                    if event_bus is not None:
                        await event_bus.publish(
                            execution_id,
                            {
                                "type": "final_answer",
                                "seq": log_id,
                                "data": {"content": output, "agent_name": config.name},
                            },
                        )

                # 6. Persist success
                result = await self._finish_execution(
                    execution_id,
                    "success",
                    duration_ms,
                    total_input_tokens,
                    total_output_tokens,
                    output_data=output[:10000],
                    cost_usd=cost_usd,
                )
                result["output"] = output
                if global_event_bus is not None:
                    await global_event_bus.publish(
                        {
                            "type": "execution_completed",
                            "data": {
                                "execution_id": execution_id,
                                "agent_name": config.name,
                                "status": result["status"],
                                "duration_ms": result.get("duration_ms", 0),
                            },
                        }
                    )
                logger.info(
                    f"Execution complete: {config.name} — success in {duration_ms}ms "
                    f"(tokens: {total_input_tokens} in / {total_output_tokens} out / {result['total_tokens']} total)"
                )
                if event_bus is not None:
                    await event_bus.publish(
                        execution_id,
                        {
                            "type": "complete",
                            "seq": _COMPLETE_SEQ,
                            "data": {
                                "status": result["status"],
                                "duration_ms": result.get("duration_ms"),
                                "total_tokens": result.get("total_tokens"),
                                "cost_usd": result.get("cost_usd"),
                                "error": result.get("error"),
                            },
                        },
                    )
                if on_complete is not None:
                    on_complete(config.name, result)
                return result

            except asyncio.TimeoutError:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                error_msg = f"Timeout after {config.settings.timeout}s"
                logger.warning(f"Execution timeout: {config.name} — {error_msg}")
                result = await self._finish_execution(
                    execution_id,
                    "timeout",
                    duration_ms,
                    total_input_tokens,
                    total_output_tokens,
                    error=error_msg,
                    cost_usd=cost_usd,
                )
                if global_event_bus is not None:
                    await global_event_bus.publish(
                        {
                            "type": "execution_completed",
                            "data": {
                                "execution_id": execution_id,
                                "agent_name": config.name,
                                "status": result["status"],
                                "duration_ms": result.get("duration_ms", 0),
                            },
                        }
                    )
                if event_bus is not None:
                    await event_bus.publish(
                        execution_id,
                        {
                            "type": "complete",
                            "seq": _COMPLETE_SEQ,
                            "data": {
                                "status": result["status"],
                                "duration_ms": result.get("duration_ms"),
                                "total_tokens": result.get("total_tokens"),
                                "cost_usd": result.get("cost_usd"),
                                "error": result.get("error"),
                            },
                        },
                    )
                if on_complete is not None:
                    on_complete(config.name, result)
                return result

            except LimitExceeded as e:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                error_msg = f"Aborted: {e.reason}" + (f" ({e.detail})" if e.detail else "")
                logger.warning(f"Execution aborted: {config.name} — {error_msg}")
                result = await self._finish_execution(
                    execution_id,
                    "aborted",
                    duration_ms,
                    total_input_tokens,
                    total_output_tokens,
                    error=error_msg,
                    cost_usd=cost_usd,
                )
                if global_event_bus is not None:
                    await global_event_bus.publish(
                        {
                            "type": "execution_completed",
                            "data": {
                                "execution_id": execution_id,
                                "agent_name": config.name,
                                "status": result["status"],
                                "duration_ms": result.get("duration_ms", 0),
                            },
                        }
                    )
                if event_bus is not None:
                    await event_bus.publish(
                        execution_id,
                        {
                            "type": "complete",
                            "seq": _COMPLETE_SEQ,
                            "data": {
                                "status": result["status"],
                                "duration_ms": result.get("duration_ms"),
                                "total_tokens": result.get("total_tokens"),
                                "cost_usd": result.get("cost_usd"),
                                "error": result.get("error"),
                            },
                        },
                    )
                if on_complete is not None:
                    on_complete(config.name, result)
                return result

            except Exception as e:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                error_msg = f"{type(e).__name__}: {e}"
                logger.error(f"Execution error: {config.name} — {error_msg}")
                result = await self._finish_execution(
                    execution_id,
                    "error",
                    duration_ms,
                    total_input_tokens,
                    total_output_tokens,
                    error=error_msg,
                    cost_usd=cost_usd,
                )
                if global_event_bus is not None:
                    await global_event_bus.publish(
                        {
                            "type": "execution_completed",
                            "data": {
                                "execution_id": execution_id,
                                "agent_name": config.name,
                                "status": result["status"],
                                "duration_ms": result.get("duration_ms", 0),
                            },
                        }
                    )
                if event_bus is not None:
                    await event_bus.publish(
                        execution_id,
                        {
                            "type": "complete",
                            "seq": _COMPLETE_SEQ,
                            "data": {
                                "status": result["status"],
                                "duration_ms": result.get("duration_ms"),
                                "total_tokens": result.get("total_tokens"),
                                "cost_usd": result.get("cost_usd"),
                                "error": result.get("error"),
                            },
                        },
                    )
                if on_complete is not None:
                    on_complete(config.name, result)
                return result

        finally:
            _reset_context(sdk_token)

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
