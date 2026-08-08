"""CLI chat owns a session_id for the life of the process (Fase 3.2)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from rich.console import Console

from agent_md.cli import commands


class _Resp:
    def __init__(self, status=200, body=None, text=""):
        self.status_code = status
        self._body = body or {}
        self.text = text or str(body)

    def json(self):
        return self._body


class _ChatClient:
    """Records POST /run bodies; stream is stubbed out of band."""

    def __init__(self):
        self.posts: list[tuple[str, dict]] = []
        self._next_execution_id = 1

    def get(self, path):
        if path.endswith("/pending"):
            return _Resp(200, {})
        return _Resp(200, {"model_provider": "google", "model_name": "gemini-2.5-flash"})

    def post(self, path, json=None):
        self.posts.append((path, json or {}))
        eid = self._next_execution_id
        self._next_execution_id += 1
        return _Resp(200, {"execution_id": eid})

    def delete(self, path):
        return _Resp(200)


def _drive_chat(monkeypatch, client: _ChatClient, lines: list[str]) -> None:
    """Run ``commands.chat`` with a scripted prompt sequence."""
    prompts = iter(lines)

    monkeypatch.setattr("agent_md.cli.spawn.ensure_backend", lambda **k: client)
    monkeypatch.setattr(commands, "_pick_or_resolve_agent", lambda agent, workspace: "talker")
    monkeypatch.setattr(
        commands,
        "_lookup_agent",
        lambda agent, workspace: SimpleNamespace(name="Talker", id="talker"),
    )
    monkeypatch.setattr(
        commands,
        "_stream_chat_turn",
        lambda *a, **k: {"status": "success", "total_tokens": 0, "cost_usd": 0, "duration_ms": 0},
    )
    monkeypatch.setattr(Console, "input", lambda self, *a, **k: next(prompts))

    commands.chat(agent="talker", workspace=None)


def test_chat_reuses_one_session_id_on_every_turn(monkeypatch):
    client = _ChatClient()
    _drive_chat(monkeypatch, client, ["alpha", "beta", "/exit"])

    assert len(client.posts) == 2
    bodies = [body for _, body in client.posts]
    assert bodies[0]["message"] == "alpha"
    assert bodies[1]["message"] == "beta"
    session = bodies[0]["session_id"]
    assert session == bodies[1]["session_id"]
    # Valid UUID — the server accepts any short string, but the CLI must generate one.
    uuid.UUID(session)
    assert all(path == "/agents/talker/run" for path, _ in client.posts)


def test_two_chats_get_distinct_session_ids(monkeypatch):
    """Two terminals (two chat processes) must not share a conversation id."""
    first = _ChatClient()
    _drive_chat(monkeypatch, first, ["hello", "/exit"])
    second = _ChatClient()
    _drive_chat(monkeypatch, second, ["hello", "/exit"])

    s1 = first.posts[0][1]["session_id"]
    s2 = second.posts[0][1]["session_id"]
    assert s1 != s2
    uuid.UUID(s1)
    uuid.UUID(s2)


async def test_two_cli_sessions_stay_isolated_through_seed(tmp_path, monkeypatch):
    """Behavioral: UUID session_ids (as the CLI generates) never cross-seed on a clean DB."""
    from langchain_core.messages import AIMessage

    from agent_md.config.models import AgentConfig
    from agent_md.db.database import Database
    from agent_md.execution.runner import AgentRunner
    from agent_md.workspace.path_context import PathContext

    class _NoMCP:
        async def get_tools(self, names):
            return []

    class _SpyModel:
        def __init__(self):
            self.seen = []
            self.n = 0

        def bind_tools(self, tools):
            return self

        async def ainvoke(self, messages):
            self.seen.append(list(messages))
            self.n += 1
            return AIMessage(content=f"answer {self.n}")

    db_path = tmp_path / "chat-sessions.db"
    db = Database(db_path)
    await db.connect()
    pc = PathContext(
        workspace_root=tmp_path,
        agents_dir=tmp_path,
        db_path=db_path,
        mcp_config=tmp_path / "m.json",
        tools_dir=tmp_path,
        skills_dir=tmp_path,
    )
    runner = AgentRunner(db, mcp_manager=_NoMCP(), path_context=pc, db_path=str(db_path))
    config = AgentConfig(name="talker", model={"provider": "google", "name": "x"}, history="low")
    spy = _SpyModel()
    monkeypatch.setattr("agent_md.execution.runner.create_chat_model", lambda **kw: spy)

    # Same contract the CLI posts: message + session_id (UUID) → trigger chat.
    sess_a = str(uuid.uuid4())
    sess_b = str(uuid.uuid4())
    try:
        for session, message in [
            (sess_a, "alpha one"),
            (sess_b, "beta one"),
            (sess_a, "alpha two"),
            (sess_b, "beta two"),
        ]:
            res = await runner.run(
                config,
                trigger_type="chat",
                session_id=session,
                user_message=message,
            )
            assert res["status"] == "success", res
    finally:
        await runner.aclose()

    def _texts(messages):
        return [
            getattr(m, "content", "") if isinstance(getattr(m, "content", ""), str) else str(getattr(m, "content", ""))
            for m in messages
        ]

    a2 = " ".join(_texts(spy.seen[2]))
    b2 = " ".join(_texts(spy.seen[3]))
    assert "alpha one" in a2 and "beta one" not in a2
    assert "beta one" in b2 and "alpha one" not in b2
    assert "answer 2" not in a2  # B's first answer
    assert "alpha two" not in b2

    rows = await db.list_executions(agent_id="talker", limit=10)
    assert {r.session_id for r in rows} == {sess_a, sess_b}
    assert {r.trigger for r in rows} == {"chat"}
    await db.close()


def test_chat_hilt_waiting_fallback_still_polls_pending(monkeypatch):
    """Regressão: waiting → GET /pending com dedup por request_id não pode sumir."""
    client = _ChatClient()
    pending_hits: list[str] = []

    def get(path):
        if path.endswith("/pending"):
            pending_hits.append(path)
            return _Resp(
                200,
                {
                    "request_id": "r-wait",
                    "kind": "confirm",
                    "message": "ok?",
                    "tool_name": "file_delete",
                    "tool_args": {},
                },
            )
        return _Resp(200, {"model_provider": "google", "model_name": "gemini-2.5-flash"})

    client.get = get

    # First stream pass reports waiting; after respond, stream completes.
    stream_calls = {"n": 0}

    def fake_stream(*a, **k):
        stream_calls["n"] += 1
        if stream_calls["n"] == 1:
            return {"waiting": True}
        return {"status": "success"}

    responded: list[dict] = []

    def fake_prompt(client_, execution_id, console, data):
        responded.append(data)

    prompts = iter(["need approval", "/exit"])
    monkeypatch.setattr("agent_md.cli.spawn.ensure_backend", lambda **k: client)
    monkeypatch.setattr(commands, "_pick_or_resolve_agent", lambda agent, workspace: "talker")
    monkeypatch.setattr(
        commands,
        "_lookup_agent",
        lambda agent, workspace: SimpleNamespace(name="Talker", id="talker"),
    )
    monkeypatch.setattr(commands, "_stream_chat_turn", fake_stream)
    monkeypatch.setattr(commands, "_prompt_and_respond", fake_prompt)
    monkeypatch.setattr(Console, "input", lambda self, *a, **k: next(prompts))

    commands.chat(agent="talker", workspace=None)

    assert client.posts[0][1]["session_id"]
    assert pending_hits == ["/executions/1/pending"]
    assert responded[0]["request_id"] == "r-wait"
    assert stream_calls["n"] == 2


@pytest.mark.parametrize("bye", ["/exit", "/quit"])
def test_chat_exit_commands(monkeypatch, bye):
    client = _ChatClient()
    _drive_chat(monkeypatch, client, [bye])
    assert client.posts == []
