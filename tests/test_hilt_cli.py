from agent_md.cli import commands


class _FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


class _FakeClient:
    def __init__(self):
        self.posted = []

    def post(self, path, json=None):
        self.posted.append((path, json))
        return _FakeResp(200, {})


def test_prompt_and_respond_confirm(monkeypatch):
    from rich.console import Console
    import typer

    monkeypatch.setattr(typer, "confirm", lambda *a, **k: True)
    client = _FakeClient()
    payload = {
        "request_id": "r1",
        "kind": "confirm",
        "message": "Delete?",
        "tool_name": "file_delete",
        "tool_args": {"path": "/x"},
    }
    commands._prompt_and_respond(client, 7, Console(), payload)
    assert client.posted[0][0] == "/executions/7/respond"
    assert client.posted[0][1] == {"request_id": "r1", "response": {"approved": True}}


def test_prompt_and_respond_input(monkeypatch):
    from rich.console import Console
    import typer

    monkeypatch.setattr(typer, "prompt", lambda *a, **k: "Ana")
    client = _FakeClient()
    payload = {"request_id": "r2", "kind": "input", "message": "Name?"}
    commands._prompt_and_respond(client, 3, Console(), payload)
    assert client.posted[0][1] == {"request_id": "r2", "response": {"text": "Ana"}}


class _FakeSSE:
    def __init__(self, lines):
        self._lines = lines

    def iter_lines(self):
        yield from self._lines


class _StreamClient:
    def __init__(self, lines):
        self._lines = lines

    def stream_sse(self, path):
        import contextlib

        @contextlib.contextmanager
        def _cm():
            yield _FakeSSE(self._lines)

        return _cm()


def test_stream_execution_skips_answered_interrupt():
    from agent_md.cli import commands
    from rich.console import Console

    # an interrupt event for rid 'r1' followed by a complete event
    lines = [
        "event: interrupt",
        'data: {"request_id": "r1", "kind": "confirm", "message": "ok?"}',
        "",
        "event: complete",
        'data: {"status": "success"}',
        "",
    ]
    # when r1 is already answered, the function must NOT return the interrupt;
    # it should reach complete and return None
    res = commands._stream_execution(_StreamClient(lines), 1, Console(), quiet=True, answered={"r1"})
    assert res is None


def test_stream_execution_returns_new_interrupt():
    from agent_md.cli import commands
    from rich.console import Console

    lines = [
        "event: interrupt",
        'data: {"request_id": "r2", "kind": "confirm", "message": "ok?"}',
        "",
    ]
    res = commands._stream_execution(_StreamClient(lines), 1, Console(), quiet=True, answered=set())
    assert res["interrupt"]["request_id"] == "r2"


def test_stream_execution_deduplicates_replayed_events():
    """Events already in `seen` must not be printed on reconnect passes."""
    import io
    from rich.console import Console
    from agent_md.cli import commands

    # SSE lines with id: headers — one tool_call and one final_answer
    lines = [
        "id: 10",
        "event: tool_call",
        'data: {"tools": [{"name": "file_read", "args": "x"}]}',
        "",
        "id: 11",
        "event: final_answer",
        'data: {"content": "Done!"}',
        "",
        "event: complete",
        'data: {"status": "success"}',
        "",
    ]

    # First pass — seen starts empty, everything should be printed
    buf1 = io.StringIO()
    console1 = Console(file=buf1, force_terminal=False)
    seen: set = set()
    commands._stream_execution(_StreamClient(lines), 1, console1, quiet=False, seen=seen)
    out1 = buf1.getvalue()
    assert "file_read" in out1
    assert "Done!" in out1
    assert "10" in seen
    assert "11" in seen

    # Second pass with the same `seen` — replayed events must be skipped
    buf2 = io.StringIO()
    console2 = Console(file=buf2, force_terminal=False)
    commands._stream_execution(_StreamClient(lines), 1, console2, quiet=False, seen=seen)
    out2 = buf2.getvalue()
    assert "file_read" not in out2
    assert "Done!" not in out2


def test_respond_flags_yes(monkeypatch):
    from agent_md.cli import commands

    client = _FakeClient()

    def fake_get(path, params=None):
        return _FakeResp(200, {"request_id": "r1", "kind": "confirm", "message": "ok?"})

    client.get = fake_get
    monkeypatch.setattr("agent_md.cli.spawn.ensure_backend", lambda **k: client)

    commands.respond(execution_id=5, yes=True, no=False, reason="sure", text=None, choice=None, workspace=None)
    assert client.posted[-1][0] == "/executions/5/respond"
    assert client.posted[-1][1]["response"] == {"approved": True, "reason": "sure"}
