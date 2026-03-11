from __future__ import annotations

import asyncio
import logging
import time

from agent_md.core.execution_logger import ExecutionLogger
from agent_md.core.path_context import PathContext
from agent_md.core.registry import AgentConfig
from agent_md.db.database import Database
from agent_md.graph.builder import create_react_graph, stream_agent_graph
from agent_md.mcp.manager import MCPManager
from agent_md.providers.factory import create_chat_model
from agent_md.tools.custom_loader import load_custom_tools
from agent_md.tools.registry import resolve_builtin_tools

logger = logging.getLogger(__name__)


class AgentRunner:
    """Executes agents and persists results to the database."""

    def __init__(self, db: Database, mcp_manager: MCPManager, path_context: PathContext):
        self.db = db
        self.mcp_manager = mcp_manager
        self.path_context = path_context

    async def run(self, config: AgentConfig, trigger_type: str = "manual", on_event=None) -> dict:
        """Execute an agent and persist the result.

        Args:
            config: Validated agent configuration.
            trigger_type: What triggered this execution ('manual', 'cron', 'interval').
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
            # 2. Create ChatModel via provider factory
            chat_model = create_chat_model(
                provider=config.model.provider,
                model=config.model.name,
                settings=config.settings.model_dump(),
                base_url=config.model.base_url,
            )

            # 3. Resolve built-in tools (always available)
            tools = resolve_builtin_tools(config, self.path_context)

            # 4. Load custom tools if declared
            if config.custom_tools:
                tools.extend(load_custom_tools(config.custom_tools, self.path_context.tools_dir))

            # 5. Add MCP tools if the agent declares any
            if config.mcp:
                mcp_tools = await self.mcp_manager.get_tools(config.mcp)
                tools.extend(mcp_tools)
                logger.info(
                    f"Resolving tools: {len(tools) - len(mcp_tools)} built-in + "
                    f"{len(mcp_tools)} MCP ({', '.join(config.mcp)})"
                )

            # 6. Build the graph
            graph = create_react_graph(chat_model, tools)

            # 7. Stream execution — log each message in real time
            last_ai_msg = None

            async def _stream():
                nonlocal last_ai_msg, total_input_tokens, total_output_tokens
                async for msg in stream_agent_graph(graph, config.system_prompt, config, self.path_context):
                    await ex_logger.log_message(msg)

                    # Accumulate token usage from every AI message
                    usage = getattr(msg, "usage_metadata", None)
                    if usage:
                        total_input_tokens += usage.get("input_tokens", 0)
                        total_output_tokens += usage.get("output_tokens", 0)

                    if getattr(msg, "type", "") == "ai" and not (hasattr(msg, "tool_calls") and msg.tool_calls):
                        last_ai_msg = msg

            await asyncio.wait_for(_stream(), timeout=config.settings.timeout)

            duration_ms = int((time.monotonic() - start_time) * 1000)
            total_tokens = total_input_tokens + total_output_tokens

            # 7. Extract final output
            output = ""
            if last_ai_msg:
                from agent_md.core.execution_logger import _extract_text

                raw_content = getattr(last_ai_msg, "content", None)
                output = _extract_text(raw_content) if raw_content is not None else str(last_ai_msg)
                # Re-tag the last AI message as final_answer
                await ex_logger.mark_final_answer(last_ai_msg)

            # 8. Persist success
            await self.db.update_execution(
                execution_id=execution_id,
                status="success",
                duration_ms=duration_ms,
                output_data=output[:10000],
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                total_tokens=total_tokens,
            )

            logger.info(
                f"Execution complete: {config.name} — success in {duration_ms}ms "
                f"(tokens: {total_input_tokens} in / {total_output_tokens} out / {total_tokens} total)"
            )

            return {
                "status": "success",
                "output": output,
                "duration_ms": duration_ms,
                "execution_id": execution_id,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_tokens,
            }

        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            total_tokens = total_input_tokens + total_output_tokens
            error_msg = f"Timeout after {config.settings.timeout}s"
            await self.db.update_execution(
                execution_id=execution_id,
                status="timeout",
                duration_ms=duration_ms,
                error=error_msg,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                total_tokens=total_tokens,
            )
            logger.warning(f"Execution timeout: {config.name} — {error_msg}")
            return {
                "status": "timeout",
                "error": error_msg,
                "duration_ms": duration_ms,
                "execution_id": execution_id,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_tokens,
            }

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            total_tokens = total_input_tokens + total_output_tokens
            error_msg = f"{type(e).__name__}: {e}"
            await self.db.update_execution(
                execution_id=execution_id,
                status="error",
                duration_ms=duration_ms,
                error=error_msg,
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens,
                total_tokens=total_tokens,
            )
            logger.error(f"Execution error: {config.name} — {error_msg}")
            return {
                "status": "error",
                "error": error_msg,
                "duration_ms": duration_ms,
                "execution_id": execution_id,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": total_tokens,
            }
