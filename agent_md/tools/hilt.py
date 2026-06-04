"""HILT request payloads + the ask_user built-in tool."""

from __future__ import annotations

import uuid

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
