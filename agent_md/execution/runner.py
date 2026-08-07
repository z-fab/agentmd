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
from agent_md.graph.builder import create_react_graph, stream_agent_graph, stream_chat_turn, GraphPaused
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


def _agent_identity_fields(config: AgentConfig) -> dict:
    """Canonical identity fields for public SSE / EventBus payloads.

    ``agent_id`` is the filename stem. ``display_name`` is the presentation
    label. ``agent_name`` mirrors ``agent_id`` for schema compatibility with
    existing SSE clients until ticket 03 migrates them.
    """
    return {
        "agent_id": config.id,
        "display_name": config.name,
        "agent_name": config.id,
    }


def _build_event_data(msg, event_type: str, agent: AgentConfig | str) -> dict:
    """Build structured event data for the EventBus, including tool details.

    *agent* may be an ``AgentConfig`` or a plain id string (tests / simple callers).
    """
    content = _extract_text(getattr(msg, "content", ""))[:500]
    if isinstance(agent, str):
        identity = {"agent_id": agent, "display_name": agent, "agent_name": agent}
    else:
        identity = _agent_identity_fields(agent)
    data: dict = {"event_type": event_type, **identity}

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
        self._timeout_tasks: dict[int, asyncio.Task] = {}

    @property
    def _max_agent_depth(self) -> int:
        try:
            from agent_md.config.settings import settings

            return settings.defaults_max_agent_depth
        except Exception:
            return 3

    @property
    def _default_confirm_tools(self) -> list[str]:
        try:
            from agent_md.config.settings import settings
            from agent_md.config.models import DEFAULT_CONFIRM_TOOLS

            return settings.defaults_confirm_tools or DEFAULT_CONFIRM_TOOLS
        except Exception:
            from agent_md.config.models import DEFAULT_CONFIRM_TOOLS

            return DEFAULT_CONFIRM_TOOLS

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

    @staticmethod
    def _parse_timeout_seconds(value: str | None) -> float | None:
        if not value or value == "none":
            return None
        import re

        m = re.match(r"^(\d+)([smhd])$", value)
        if not m:
            return None
        n = int(m.group(1))
        return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]

    async def _enter_waiting(
        self,
        execution_id,
        config,
        request: dict,
        event_bus,
        ex_logger,
        global_event_bus=None,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        child_tokens: int = 0,
        cost_usd: float | None = None,
    ):
        """Persist the pending request, mark execution waiting, emit the interrupt event.

        Parent-model tokens go in ``input_tokens``/``output_tokens``; sub-agent
        tokens are folded only into ``total_tokens`` so resume can reprice the
        parent without discarding real child costs stored in ``cost_usd``.
        ``finished_at`` is intentionally not set (non-terminal status).
        """
        await self.db.set_pending_interrupt(execution_id, request["request_id"], request)
        total = None
        if input_tokens is not None or output_tokens is not None or child_tokens:
            total = (input_tokens or 0) + (output_tokens or 0) + child_tokens
        await self.db.update_execution(
            execution_id=execution_id,
            status="waiting",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            cost_usd=cost_usd,
        )
        log_id = await ex_logger.log_event("interrupt", request.get("message", ""), metadata=request)
        if event_bus is not None:
            await event_bus.publish(
                execution_id,
                {"type": "interrupt", "seq": log_id, "data": {**request, **_agent_identity_fields(config)}},
            )

        secs = self._parse_timeout_seconds(config.confirm_timeout)
        if secs is not None:

            async def _deny_after():
                await asyncio.sleep(secs)
                still = await self.db.get_pending_interrupt(execution_id)
                if still and still.request_id == request["request_id"]:
                    await self.db.clear_pending_interrupt(execution_id)
                    deny = {"approved": False, "reason": "confirm_timeout", "text": "", "selected": []}
                    self._timeout_tasks.pop(execution_id, None)
                    await self.resume(
                        config,
                        execution_id,
                        deny,
                        event_bus=event_bus,
                        global_event_bus=global_event_bus,
                    )

            self._timeout_tasks[execution_id] = asyncio.create_task(_deny_after())

    async def _publish_complete(self, execution_id, result, event_bus, global_event_bus, config):
        if global_event_bus is not None:
            await global_event_bus.publish(
                {
                    "type": "execution_completed",
                    "data": {
                        "execution_id": execution_id,
                        **_agent_identity_fields(config),
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
        """Create model, resolve tools, and compile the graph.

        Returns ``(graph, checkpoint_conn)`` where ``checkpoint_conn`` is the
        aiosqlite connection backing the checkpointer (or ``None`` if no
        checkpointer was created). The caller owns the connection's lifecycle:
        per-execution callers (run/resume) must close it when done; session-
        scoped callers (prepare_agent/chat) must append it to
        ``self._checkpoint_conns`` so it is closed at ``aclose()``.
        """
        chat_model = create_chat_model(
            provider=config.model.provider,
            model=config.model.name,
            settings=config.settings.model_dump(),
            base_url=config.model.base_url,
        )

        from agent_md.config.models import effective_confirm_tools

        confirm_tools = effective_confirm_tools(config, defaults=self._default_confirm_tools)
        tools = resolve_builtin_tools(config, self.path_context, confirm_tools=confirm_tools, **tool_kwargs)

        if config.custom_tools:
            tools.extend(load_custom_tools(config.custom_tools, self.path_context.tools_dir))

        if config.mcp:
            mcp_tools = await self.mcp_manager.get_tools(config.mcp)
            tools.extend(mcp_tools)
            logger.info(
                f"Resolving tools: {len(tools) - len(mcp_tools)} built-in + "
                f"{len(mcp_tools)} MCP ({', '.join(config.mcp)})"
            )

        # Checkpointer is ALWAYS on — it is the durability substrate for HILT.
        # `history` only controls how much prior context we seed (see run()).
        checkpointer = None
        memory_limit = None
        checkpoint_conn = None
        if self.db_path:
            import aiosqlite
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            from agent_md.execution.checkpoint_maint import checkpoint_db_path

            checkpoint_db = str(checkpoint_db_path(self.db_path))
            checkpoint_conn = await aiosqlite.connect(checkpoint_db)
            checkpointer = AsyncSqliteSaver(checkpoint_conn)
            await checkpointer.setup()
            logger.info(f"Checkpointer enabled (history={config.history}, thread per execution)")

        # Create post-tool processor for skill meta message injection
        post_processor = None
        if config.skills and self.path_context and self.path_context.skills_dir.exists():
            post_processor = create_post_tool_processor(config, self.path_context.skills_dir)

        graph = create_react_graph(
            chat_model, tools, checkpointer=checkpointer, memory_limit=memory_limit, post_tool_processor=post_processor
        )
        return graph, checkpoint_conn

    async def _load_history_seed(self, graph, config: AgentConfig, execution_id: int) -> list:
        """Return prior messages to seed a new run, trimmed to the history level.

        Reads the most recent finished execution's checkpoint for this agent and
        returns its non-system messages. Empty when history is off or no prior run.
        """
        from agent_md.graph.agent import _trim_messages
        from agent_md.config.models import HISTORY_LIMITS

        if config.history == "off":
            return []
        prev = await self.db.get_last_finished_execution(config.id, exclude_id=execution_id)
        if prev is None:
            return []
        try:
            snapshot = await graph.aget_state({"configurable": {"thread_id": str(prev.id)}})
        except Exception:
            return []
        prior = list(snapshot.values.get("messages", [])) if snapshot and snapshot.values else []
        non_system = [m for m in prior if getattr(m, "type", "") != "system"]
        limit = HISTORY_LIMITS[config.history]
        trimmed = _trim_messages(non_system, limit)
        return trimmed

    async def run(
        self,
        config: AgentConfig,
        trigger_type: str = "manual",
        trigger_context: str | None = None,
        on_event=None,
        on_start=None,
        on_complete=None,
        arguments: list[str] | str = "",
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
                agent_id=config.id,
                trigger=trigger_type,
                status="running",
                parent_execution_id=parent_execution_id,
            )

        ex_logger = ExecutionLogger(self.db, execution_id, config.id, display_name=config.name, on_event=on_event)

        if global_event_bus is not None:
            await global_event_bus.publish(
                {
                    "type": "execution_started",
                    "data": {
                        "execution_id": execution_id,
                        **_agent_identity_fields(config),
                        "trigger": trigger_type,
                    },
                }
            )

        start_time = time.monotonic()

        # Token accumulators (parent model + folded sub-agent usage)
        total_input_tokens = 0
        total_output_tokens = 0
        child_input_tokens = 0
        child_output_tokens = 0
        tool_call_count = 0
        cost_usd: float | None = None
        child_cost_usd = 0.0
        _pricing_warned = False
        last_errors: list[tuple[str, str]] = []  # (tool_name, normalized_error)
        # Mutable bag filled by run_agent tool so child usage counts toward parent limits.
        sub_agent_usage: dict = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

        sdk_token = _set_context(config, self.path_context)
        checkpoint_conn = None
        try:
            try:
                # 2. Build model + tools + graph
                graph, checkpoint_conn = await self._build_graph(
                    config,
                    registry=self.registry,
                    runner=self,
                    depth=depth,
                    max_depth=self._max_agent_depth,
                    parent_execution_id=execution_id,
                    event_bus=event_bus,
                    global_event_bus=global_event_bus,
                    cancel_event=cancel_event,
                    sub_agent_usage=sub_agent_usage,
                )
                history_seed = await self._load_history_seed(graph, config, execution_id)

                # 3. Build user input with trigger context
                user_input = self._build_user_input(trigger_type, trigger_context, config)
                if user_message:
                    user_input = user_message

                # 3b. Log the constructed system prompt and user input
                from agent_md.graph.builder import build_system_message_async

                sys_msg = await build_system_message_async(
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
                graph_config = {"configurable": {"thread_id": str(execution_id)}}

                # Set recursion_limit high enough for max_tool_calls
                from agent_md.graph.builder import compute_recursion_limit

                has_post_tool = bool(config.skills and self.path_context and self.path_context.skills_dir.exists())
                graph_config["recursion_limit"] = compute_recursion_limit(config.settings.max_tool_calls, has_post_tool)

                async def _stream():
                    nonlocal \
                        last_ai_msg, \
                        total_input_tokens, \
                        total_output_tokens, \
                        child_input_tokens, \
                        child_output_tokens, \
                        tool_call_count, \
                        cost_usd, \
                        child_cost_usd, \
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
                        seed_messages=history_seed,
                    ):
                        log_id = await ex_logger.log_message(msg)

                        if event_bus is not None:
                            event_type = _classify_event_type(msg)
                            event_data = _build_event_data(msg, event_type, config)
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

                        # Fold in sub-agent usage reported by run_agent tool
                        if sub_agent_usage["input_tokens"] or sub_agent_usage["output_tokens"]:
                            child_input_tokens += sub_agent_usage["input_tokens"]
                            child_output_tokens += sub_agent_usage["output_tokens"]
                            sub_agent_usage["input_tokens"] = 0
                            sub_agent_usage["output_tokens"] = 0
                        if sub_agent_usage["cost_usd"]:
                            child_cost_usd += sub_agent_usage["cost_usd"]
                            sub_agent_usage["cost_usd"] = 0.0

                        # Count tool calls
                        if getattr(msg, "type", "") == "ai" and hasattr(msg, "tool_calls") and msg.tool_calls:
                            tool_call_count += len(msg.tool_calls)

                        # Estimate running cost (parent model only) + child costs as reported
                        parent_cost = estimate_cost(
                            config.model.provider,
                            config.model.name,
                            total_input_tokens,
                            total_output_tokens,
                        )
                        if parent_cost is not None or child_cost_usd:
                            cost_usd = (parent_cost or 0.0) + child_cost_usd

                        combined_tokens = (
                            total_input_tokens + total_output_tokens + child_input_tokens + child_output_tokens
                        )

                        # Warn once if cost limit is set but pricing is unknown
                        if (
                            not _pricing_warned
                            and config.settings.max_cost_usd is not None
                            and cost_usd is None
                            and combined_tokens > 0
                        ):
                            logger.warning(
                                f"max_cost_usd configured but no pricing data for "
                                f"{config.model.provider}/{config.model.name}; limit will not be enforced"
                            )
                            _pricing_warned = True

                        _check_limits(config.settings, tool_call_count, combined_tokens, cost_usd)

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
                                "data": {"content": output, **_agent_identity_fields(config)},
                            },
                        )

                # 6. Persist success (include folded sub-agent tokens)
                result = await self._finish_execution(
                    execution_id,
                    "success",
                    duration_ms,
                    total_input_tokens + child_input_tokens,
                    total_output_tokens + child_output_tokens,
                    output_data=output[:10000],
                    cost_usd=cost_usd,
                )
                result["output"] = output
                logger.info(
                    f"Execution complete: {config.name} — success in {duration_ms}ms "
                    f"(tokens: {result['input_tokens']} in / {result['output_tokens']} out / {result['total_tokens']} total)"
                )
                await self._publish_complete(execution_id, result, event_bus, global_event_bus, config)
                if on_complete is not None:
                    on_complete(config.name, result)
                return result

            except GraphPaused as paused:
                await self._enter_waiting(
                    execution_id,
                    config,
                    paused.request,
                    event_bus,
                    ex_logger,
                    global_event_bus=global_event_bus,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    child_tokens=child_input_tokens + child_output_tokens,
                    cost_usd=cost_usd,
                )
                if global_event_bus is not None:
                    await global_event_bus.publish(
                        {
                            "type": "execution_waiting",
                            "data": {"execution_id": execution_id, **_agent_identity_fields(config)},
                        }
                    )
                logger.info(f"Execution {execution_id} paused (HILT {paused.request.get('kind')})")
                return {"status": "waiting", "execution_id": execution_id, "request": paused.request}

            except asyncio.TimeoutError:
                duration_ms = int((time.monotonic() - start_time) * 1000)
                error_msg = f"Timeout after {config.settings.timeout}s"
                logger.warning(f"Execution timeout: {config.name} — {error_msg}")
                result = await self._finish_execution(
                    execution_id,
                    "timeout",
                    duration_ms,
                    total_input_tokens + child_input_tokens,
                    total_output_tokens + child_output_tokens,
                    error=error_msg,
                    cost_usd=cost_usd,
                )
                await self._publish_complete(execution_id, result, event_bus, global_event_bus, config)
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
                    total_input_tokens + child_input_tokens,
                    total_output_tokens + child_output_tokens,
                    error=error_msg,
                    cost_usd=cost_usd,
                )
                await self._publish_complete(execution_id, result, event_bus, global_event_bus, config)
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
                    total_input_tokens + child_input_tokens,
                    total_output_tokens + child_output_tokens,
                    error=error_msg,
                    cost_usd=cost_usd,
                )
                await self._publish_complete(execution_id, result, event_bus, global_event_bus, config)
                if on_complete is not None:
                    on_complete(config.name, result)
                return result

        finally:
            _reset_context(sdk_token)
            if checkpoint_conn is not None:
                try:
                    await checkpoint_conn.close()
                except Exception:
                    pass

    async def resume(
        self,
        config: AgentConfig,
        execution_id: int,
        response,
        *,
        event_bus=None,
        global_event_bus=None,
        cancel_event: asyncio.Event | None = None,
    ) -> dict:
        """Resume a paused execution by injecting *response* into the interrupt."""
        t = self._timeout_tasks.pop(execution_id, None)
        if t:
            t.cancel()

        from langgraph.types import Command
        from agent_md.graph.builder import _stream_state

        logger.info(f"Resuming execution {execution_id}")
        if not await self.db.claim_execution_for_resume(execution_id):
            logger.info(f"Resume skipped for {execution_id}: no longer waiting (already resumed or cancelled)")
            return {"status": "skipped", "execution_id": execution_id}
        ex_logger = ExecutionLogger(self.db, execution_id, config.id, display_name=config.name, on_event=None)
        if global_event_bus is not None:
            await global_event_bus.publish(
                {
                    "type": "execution_started",
                    "data": {
                        "execution_id": execution_id,
                        **_agent_identity_fields(config),
                        "trigger": "resume",
                    },
                }
            )

        # Seed counters from the pre-pause record so limits/cost survive HILT.
        # input/output columns are parent-model only; child tokens live in
        # total_tokens - (input + output); cost_usd is the true combined figure.
        prior = await self.db.get_execution(execution_id)
        base_input = int(prior.input_tokens or 0) if prior else 0
        base_output = int(prior.output_tokens or 0) if prior else 0
        base_cost = float(prior.cost_usd) if prior and prior.cost_usd is not None else None
        prior_total = int(prior.total_tokens or 0) if prior else 0
        sunk_child_tokens = max(0, prior_total - base_input - base_output)
        base_parent_est = estimate_cost(config.model.provider, config.model.name, base_input, base_output)
        sunk_child_cost = 0.0
        if base_cost is not None:
            sunk_child_cost = max(0.0, base_cost - (base_parent_est or 0.0))
        base_tool_calls = await self.db.count_logs(execution_id, event_type="tool_call")

        start_time = time.monotonic()
        total_input_tokens = base_input
        total_output_tokens = base_output
        tool_call_count = base_tool_calls
        cost_usd = base_cost
        child_input_tokens = sunk_child_tokens
        child_output_tokens = 0
        child_cost_usd = 0.0  # only NEW child costs this segment; sunk_child_cost is separate
        sub_agent_usage: dict = {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}
        last_ai_msg = None
        last_errors: list[tuple[str, str]] = []  # (tool_name, normalized_error)
        graph_config = {"configurable": {"thread_id": str(execution_id)}}
        has_post_tool = bool(config.skills and self.path_context and self.path_context.skills_dir.exists())

        from agent_md.graph.builder import compute_recursion_limit

        graph_config["recursion_limit"] = compute_recursion_limit(config.settings.max_tool_calls, has_post_tool)

        sdk_token = _set_context(config, self.path_context)
        checkpoint_conn = None
        try:
            graph, checkpoint_conn = await self._build_graph(
                config,
                registry=self.registry,
                runner=self,
                depth=0,
                max_depth=self._max_agent_depth,
                parent_execution_id=execution_id,
                event_bus=event_bus,
                global_event_bus=global_event_bus,
                cancel_event=cancel_event,
                sub_agent_usage=sub_agent_usage,
            )

            async def _drive():
                nonlocal \
                    last_ai_msg, \
                    total_input_tokens, \
                    total_output_tokens, \
                    child_input_tokens, \
                    child_output_tokens, \
                    tool_call_count, \
                    cost_usd, \
                    child_cost_usd, \
                    last_errors
                async for msg in _stream_state(graph, Command(resume=response), config=graph_config):
                    log_id = await ex_logger.log_message(msg)
                    if event_bus is not None:
                        et = _classify_event_type(msg)
                        await event_bus.publish(
                            execution_id, {"type": et, "seq": log_id, "data": _build_event_data(msg, et, config)}
                        )
                    if cancel_event is not None and cancel_event.is_set():
                        raise LimitExceeded("cancelled", "Execution cancelled by user")
                    usage = getattr(msg, "usage_metadata", None)
                    if usage:
                        total_input_tokens += usage.get("input_tokens", 0)
                        total_output_tokens += usage.get("output_tokens", 0)
                    if sub_agent_usage["input_tokens"] or sub_agent_usage["output_tokens"]:
                        child_input_tokens += sub_agent_usage["input_tokens"]
                        child_output_tokens += sub_agent_usage["output_tokens"]
                        sub_agent_usage["input_tokens"] = 0
                        sub_agent_usage["output_tokens"] = 0
                    if sub_agent_usage["cost_usd"]:
                        child_cost_usd += sub_agent_usage["cost_usd"]
                        sub_agent_usage["cost_usd"] = 0.0
                    parent_cost = estimate_cost(
                        config.model.provider, config.model.name, total_input_tokens, total_output_tokens
                    )
                    if parent_cost is not None or sunk_child_cost or child_cost_usd or base_cost is not None:
                        # Parent tokens priced at parent rate; sunk + new child costs kept as-reported.
                        if parent_cost is not None:
                            cost_usd = parent_cost + sunk_child_cost + child_cost_usd
                        else:
                            cost_usd = (base_cost or 0.0) + child_cost_usd
                    if getattr(msg, "type", "") == "ai" and getattr(msg, "tool_calls", None):
                        tool_call_count += len(msg.tool_calls)

                    combined = total_input_tokens + total_output_tokens + child_input_tokens + child_output_tokens
                    _check_limits(config.settings, tool_call_count, combined, cost_usd)

                    # Loop detection: same tool error 3 consecutive times (parity with run())
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
                            last_errors.clear()

                    if _is_final_ai_message(msg):
                        last_ai_msg = msg

            try:
                await asyncio.wait_for(_drive(), timeout=config.settings.timeout)
            except GraphPaused as paused:
                await self._enter_waiting(
                    execution_id,
                    config,
                    paused.request,
                    event_bus,
                    ex_logger,
                    global_event_bus=global_event_bus,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    child_tokens=child_input_tokens + child_output_tokens,
                    cost_usd=cost_usd,
                )
                return {"status": "waiting", "execution_id": execution_id, "request": paused.request}

            duration_ms = int((time.monotonic() - start_time) * 1000)
            output = ""
            if last_ai_msg:
                raw = getattr(last_ai_msg, "content", None)
                output = _extract_text(raw) if raw is not None else str(last_ai_msg)
                log_id = await ex_logger.mark_final_answer(last_ai_msg)
                if event_bus is not None:
                    await event_bus.publish(
                        execution_id,
                        {
                            "type": "final_answer",
                            "seq": log_id,
                            "data": {"content": output, **_agent_identity_fields(config)},
                        },
                    )
            result = await self._finish_execution(
                execution_id,
                "success",
                duration_ms,
                total_input_tokens + child_input_tokens,
                total_output_tokens + child_output_tokens,
                output_data=output[:10000],
                cost_usd=cost_usd,
            )
            result["output"] = output
            await self._publish_complete(execution_id, result, event_bus, global_event_bus, config)
            return result
        except LimitExceeded as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            result = await self._finish_execution(
                execution_id,
                "aborted",
                duration_ms,
                total_input_tokens + child_input_tokens,
                total_output_tokens + child_output_tokens,
                error=f"Aborted: {e.reason}",
                cost_usd=cost_usd,
            )
            await self._publish_complete(execution_id, result, event_bus, global_event_bus, config)
            return result
        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            error_msg = f"{type(e).__name__}: {e}"
            logger.exception(f"Resume error: {config.name} — {error_msg}")
            result = await self._finish_execution(
                execution_id,
                "error",
                duration_ms,
                total_input_tokens + child_input_tokens,
                total_output_tokens + child_output_tokens,
                error=error_msg,
                cost_usd=cost_usd,
            )
            await self._publish_complete(execution_id, result, event_bus, global_event_bus, config)
            return result
        finally:
            _reset_context(sdk_token)
            if checkpoint_conn is not None:
                try:
                    await checkpoint_conn.close()
                except Exception:
                    pass

    async def prepare_agent(self, config: AgentConfig):
        """Create model, resolve tools, and build graph -- without executing.

        Returns the compiled LangGraph graph, ready for streaming.
        """
        graph, checkpoint_conn = await self._build_graph(config)
        # Chat reuses the graph across turns, so the connection is session-scoped:
        # hand it to aclose() rather than closing it here.
        if checkpoint_conn is not None:
            self._checkpoint_conns.append(checkpoint_conn)
        return graph

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
