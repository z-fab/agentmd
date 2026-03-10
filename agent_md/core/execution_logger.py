"""ExecutionLogger — structured logging for agent execution steps.

Classifies LangChain messages by event type and persists them to the
database. Also emits concise real-time logs via Python logging.
"""

from __future__ import annotations

import logging

from agent_md.db.database import Database

logger = logging.getLogger(__name__)


def _extract_text(content) -> str:
    """Extract plain text from message content.

    Handles both plain strings and Gemini's structured format:
    [{'type': 'text', 'text': '...', 'extras': {...}}]
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                parts.append(part["text"])
            elif isinstance(part, str):
                parts.append(part)
        return " ".join(parts).strip()
    return str(content).strip() if content else ""


class ExecutionLogger:
    """Processes LangChain messages and persists structured log entries."""

    def __init__(self, db: Database, execution_id: int, agent_name: str):
        self.db = db
        self.execution_id = execution_id
        self.agent_name = agent_name

    async def log_message(self, msg) -> None:
        """Classify a single LangChain message and persist it.

        Event types:
            system        — SystemMessage
            human         — HumanMessage
            ai            — AI reasoning (with no tool calls)
            tool_call     — AI requesting a tool (one entry per call)
            tool_response — Result returned by a tool
            final_answer  — Last AI message (no tool calls)
        """
        msg_type = getattr(msg, "type", "unknown")

        # --- AI message with tool calls ---
        if msg_type == "ai" and hasattr(msg, "tool_calls") and msg.tool_calls:
            reasoning = _extract_text(getattr(msg, "content", ""))
            if reasoning:
                logger.info(f"[{self.agent_name}] 🤖 {reasoning[:200]}")
                await self._persist("ai", reasoning[:500])

            for tc in msg.tool_calls:
                tool_name = tc.get("name", "unknown")
                tool_args = str(tc.get("args", {}))[:300]
                logger.info(f"[{self.agent_name}] 🔧 {tool_name}({tool_args[:80]})")
                await self._persist("tool_call", f"{tool_name} — args: {tool_args}")

        # --- Tool response ---
        elif msg_type == "tool":
            tool_name = getattr(msg, "name", "unknown")
            tool_content = _extract_text(getattr(msg, "content", ""))[:500]
            logger.info(f"[{self.agent_name}] 📎 {tool_name} → {tool_content[:100]}")
            await self._persist("tool_response", f"{tool_name} — {tool_content}")

        # --- AI without tool calls (reasoning or final answer) ---
        elif msg_type == "ai":
            content = _extract_text(getattr(msg, "content", ""))[:500]
            logger.info(f"[{self.agent_name}] 🤖 {content[:200]}")
            await self._persist("ai", content)

        # --- System / Human / other ---
        else:
            content = _extract_text(getattr(msg, "content", ""))[:500]
            await self._persist(msg_type, content)

    async def mark_final_answer(self, msg) -> None:
        """Persist the last AI message as a final_answer event."""
        content = _extract_text(getattr(msg, "content", ""))[:500]
        logger.info(f"[{self.agent_name}] ✅ {content[:200]}")
        await self._persist("final_answer", content)

    async def log_messages(self, messages: list) -> None:
        """Process all messages from a completed execution.

        The last AI message (if it has no tool calls) is tagged as
        final_answer instead of plain ai.
        """
        for i, msg in enumerate(messages):
            is_last_ai = (
                i == len(messages) - 1
                and getattr(msg, "type", "") == "ai"
                and not (hasattr(msg, "tool_calls") and msg.tool_calls)
            )
            if is_last_ai:
                await self.mark_final_answer(msg)
            else:
                await self.log_message(msg)

    async def _persist(self, event_type: str, message: str) -> None:
        """Write a log entry to the database."""
        await self.db.add_log(
            execution_id=self.execution_id,
            event_type=event_type,
            message=message,
        )
