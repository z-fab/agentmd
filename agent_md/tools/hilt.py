"""HILT request payloads + the ask_user built-in tool."""

from __future__ import annotations

import uuid

from langchain_core.tools import tool

REQUEST_KINDS = ("confirm", "input", "choice")


def build_request(
    kind: str,
    message: str,
    *,
    tool_name: str | None = None,
    tool_args: dict | None = None,
    options: list[str] | None = None,
    multi: bool = False,
) -> dict:
    """Build a structured HILT request payload (the value passed to interrupt())."""
    if kind not in REQUEST_KINDS:
        raise ValueError(f"kind must be one of {REQUEST_KINDS}, got '{kind}'")
    return {
        "request_id": uuid.uuid4().hex,
        "kind": kind,
        "message": message,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "options": options,
        "multi": multi,
    }


def create_ask_user_tool():
    """Built-in tool the agent calls to ask the user (confirm/input/choice)."""

    @tool
    def ask_user(question: str, kind: str = "input", options: list[str] | None = None) -> str:
        """Ask the human user a question and wait for their answer.

        Use when you need confirmation or information only the user can provide.

        Args:
            question: The question to show the user.
            kind: 'input' (free text), 'confirm' (yes/no), or 'choice' (pick from options).
            options: The choices, required when kind='choice'.

        Returns:
            The user's answer as text.
        """
        from langgraph.types import interrupt

        k = kind if kind in REQUEST_KINDS else "input"
        answer = interrupt(build_request(k, question, options=options, multi=False))
        if not isinstance(answer, dict):
            return str(answer or "")
        if k == "confirm":
            return "yes" if answer.get("approved") else "no"
        if k == "choice":
            sel = answer.get("selected", [])
            return sel[0] if sel else ""
        return str(answer.get("text", ""))

    return ask_user
