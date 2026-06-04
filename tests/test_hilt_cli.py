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
    payload = {"request_id": "r1", "kind": "confirm", "message": "Delete?", "tool_name": "file_delete", "tool_args": {"path": "/x"}}
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
