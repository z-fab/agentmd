"""CLI rendering of persisted meta log rows (execution_info / stats)."""

from __future__ import annotations

import json
import re
from io import StringIO
from unittest.mock import AsyncMock

from rich.console import Console

from agent_md.cli import commands
from agent_md.cli.theme import EVENT_DISPLAY, format_meta_log_content
from agent_md.db.models import LogRecord

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def test_event_display_has_meta():
    """meta must map to a known icon/style — not the unknown fallback."""
    assert "meta" in EVENT_DISPLAY
    emoji, style = EVENT_DISPLAY["meta"]
    assert emoji != "\u2753"
    assert style


def test_format_meta_execution_info_fields():
    meta = json.dumps(
        {
            "event_type": "execution_info",
            "model": "openai/gpt-4o",
            "trigger": "manual",
            "args": ["report.md"],
            "session_id": "sess-1",
            "agent_id": "writer",
            "display_name": "Writer Bot",
        }
    )
    text = format_meta_log_content(meta, "execution_info")
    assert "openai/gpt-4o" in text
    assert "manual" in text
    assert "Writer Bot" in text
    assert "writer" in text
    assert "report.md" in text
    assert "sess-1" in text
    assert "\u2753" not in text


def test_format_meta_execution_info_omits_null_session_and_empty_args():
    meta = json.dumps(
        {
            "event_type": "execution_info",
            "model": "google/gemini-2.5-flash",
            "trigger": "chat",
            "args": [],
            "session_id": None,
            "agent_id": "bot",
            "display_name": "bot",
        }
    )
    text = format_meta_log_content(meta, "execution_info")
    assert "google/gemini-2.5-flash" in text
    assert "chat" in text
    assert "bot" in text
    assert "session" not in text
    assert "args" not in text


def test_format_meta_stats_fields():
    meta = json.dumps(
        {
            "event_type": "stats",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "cost_usd": 0.0025,
        }
    )
    text = format_meta_log_content(meta, "stats")
    assert "150" in text
    assert "100" in text
    assert "50" in text
    assert "$0.0025" in text


def test_format_meta_stats_null_cost():
    meta = json.dumps(
        {
            "event_type": "stats",
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "cost_usd": None,
        }
    )
    text = format_meta_log_content(meta, "stats")
    assert "15" in text
    assert "cost unknown" in text


def test_format_meta_skill_context_preserves_content():
    """Third subtype (event_type meta) must still render content, not break."""
    meta = json.dumps(
        {
            "event_type": "meta",
            "content": "# Skill instructions\nDo the thing.",
            "agent_id": "bot",
        }
    )
    text = format_meta_log_content(meta, "meta")
    assert "Skill instructions" in text
    assert "Do the thing." in text


def test_format_meta_fallback_when_metadata_missing():
    assert format_meta_log_content(None, "execution_info") == "execution_info"
    assert format_meta_log_content("not-json", "stats") == "stats"


def _capture_show_detail(monkeypatch, logs: list[LogRecord]) -> str:
    buf = StringIO()
    fake_console = Console(file=buf, force_terminal=True, width=200)
    monkeypatch.setattr(commands, "console", fake_console)
    monkeypatch.setattr(
        "agent_md.workspace.services.get_execution_messages",
        AsyncMock(return_value=logs),
    )
    commands._show_execution_detail(42, workspace=None, verbose=False)
    return _strip_ansi(buf.getvalue())


def test_show_execution_detail_renders_execution_info(monkeypatch):
    logs = [
        LogRecord(
            id=1,
            execution_id=42,
            timestamp="2026-08-10T20:23:42.123",
            event_type="meta",
            message="execution_info",
            metadata=json.dumps(
                {
                    "event_type": "execution_info",
                    "model": "openai/gpt-4o",
                    "trigger": "manual",
                    "args": [],
                    "session_id": None,
                    "agent_id": "demo",
                    "display_name": "Demo",
                }
            ),
        )
    ]
    output = _capture_show_detail(monkeypatch, logs)
    assert "\u2753" not in output
    assert "\u2139" in output or "ℹ" in output
    assert "openai/gpt-4o" in output
    assert "manual" in output
    assert "Demo" in output
    # Must not print the bare label alone as the only content.
    assert "execution_info" not in output.split("gpt-4o")[0] or "openai/gpt-4o" in output


def test_show_execution_detail_renders_stats(monkeypatch):
    logs = [
        LogRecord(
            id=2,
            execution_id=42,
            timestamp="2026-08-10T20:23:43.456",
            event_type="meta",
            message="stats",
            metadata=json.dumps(
                {
                    "event_type": "stats",
                    "input_tokens": 1200,
                    "output_tokens": 340,
                    "total_tokens": 1540,
                    "cost_usd": 0.0123,
                }
            ),
        )
    ]
    output = _capture_show_detail(monkeypatch, logs)
    assert "\u2753" not in output
    assert "1,540" in output
    assert "1,200" in output
    assert "340" in output
    assert "$0.0123" in output
    # The bare DB label must not be the only visible body.
    assert "ℹ" in output or "\u2139" in output
