"""Anti-loop: an agent's own built-in writes must not retrigger its watcher.

The cycle these cover: an agent with ``trigger: watch`` over a directory it also
writes to used to fire itself forever, because ``get_allowed_paths`` puts watch
paths among the write paths and a watchdog event says nothing about which
execution caused it.

What must hold, and is asserted below:

- the writer's own watcher ignores the write;
- **another** agent's watcher does not — that is a pipeline, not a loop;
- a user's edit of the same file triggers normally, because the mtime changed;
- writes bypassing the built-in tools (MCP, custom tools) still trigger, which
  is the declared boundary of this layer;
- two concurrent executions never record into each other's bucket.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent_md.config.models import AgentConfig
from agent_md.execution.self_writes import SUPPRESSION_WINDOW, SelfWriteLedger, process_ledger, self_write
from agent_md.sdk import _reset_context, _set_context, execution_id
from agent_md.tools.files import create_file_delete_tool, create_file_move_tool, create_file_write_tool
from agent_md.tools.memory import create_memory_append_tool, create_memory_save_tool
from agent_md.workspace.path_context import PathContext
from agent_md.workspace.scheduler import _AgentWatchHandler

# Every wait in this file is bounded. A watch test that hangs instead of failing
# is worse than no test at all.
EVENT_TIMEOUT = 5.0
"""Cap on waiting for an event that *should* arrive."""

QUIET_TIMEOUT = 1.0
"""How long a suppressed write must stay quiet. Comfortably above the ~20ms
FSEvents latency measured locally and the 50ms debounce used here, and inside
``SUPPRESSION_WINDOW`` so the window itself is not what ends the wait.

The negative assertion below is a single long ``wait_for``, which is only
trustworthy because the debounce is armed with ``call_soon_threadsafe`` (issue
#15). While it was armed with ``call_later`` from the watchdog thread it did not
wake a sleeping loop, so the wait sat through the whole timeout and reported
"nothing arrived" even for an event that was never suppressed — the assertion
passed with the suppression turned off, and needed polling to mean anything."""


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "agents").mkdir()
    return tmp_path


@pytest.fixture
def path_context(workspace):
    agents = workspace / "agents"
    return PathContext(
        workspace_root=workspace,
        agents_dir=agents,
        db_path=workspace / "db.db",
        mcp_config=agents / "_config" / "mcp-servers.json",
        tools_dir=agents / "_config" / "tools",
        skills_dir=agents / "_config" / "skills",
    )


@pytest.fixture(autouse=True)
def clean_ledger():
    """The ledger is per-process; keep tests from seeing each other's writes."""
    process_ledger().clear()
    yield
    process_ledger().clear()


def _config(workspace, name="notes-agent", watch="notes") -> AgentConfig:
    return AgentConfig(
        name=name,
        model={"provider": "google", "name": "x"},
        trigger={"type": "watch", "paths": [str(workspace / watch)]},
    )


def _handler(agent_id: str, watch_dir: Path, *, ledger=None, execute_fn=None, **kwargs) -> _AgentWatchHandler:
    return _AgentWatchHandler(
        agent_id,
        [watch_dir.resolve()],
        execute_fn if execute_fn is not None else (lambda *a, **k: None),
        kwargs.pop("loop", None),
        self_writes=ledger,
        **kwargs,
    )


def _as_agent(config, path_context, exec_id: int | None = 1):
    """Run a block as if inside an execution of *config* (token-scoped)."""

    class _Scope:
        def __enter__(self):
            self.token = _set_context(config, path_context, exec_id)
            return self

        def __exit__(self, *exc):
            _reset_context(self.token)
            return False

    return _Scope()


def _bump_mtime(path: Path) -> None:
    """Give *path* a distinctly newer mtime.

    A real editor save does this by writing; asserting on it deterministically
    must not depend on the filesystem's clock resolution.
    """
    stamp = path.stat().st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(stamp, stamp))


# --- the cycle itself --------------------------------------------------------


def test_agent_writing_its_own_watched_dir_does_not_retrigger(workspace, path_context):
    notes = workspace / "notes"
    config = _config(workspace)
    handler = _handler(config.id, notes)
    target = notes / "summary.md"

    with _as_agent(config, path_context, 7):
        result = create_file_write_tool(config, path_context).invoke({"path": str(target), "content": "written"})

    assert not result.startswith("ERROR"), result
    assert target.read_text() == "written"
    assert handler._is_relevant(str(target)) is False


def test_an_identical_path_written_by_another_agent_still_triggers(workspace, path_context):
    """Agent B feeding a directory agent A watches is a pipeline, not a loop."""
    notes = workspace / "notes"
    writer = _config(workspace, name="writer")
    target = notes / "handoff.md"

    with _as_agent(writer, path_context, 11):
        create_file_write_tool(writer, path_context).invoke({"path": str(target), "content": "for you"})

    assert _handler("writer", notes)._is_relevant(str(target)) is False
    assert _handler("notes-agent", notes)._is_relevant(str(target)) is True


def test_user_edit_after_the_agent_write_triggers_inside_the_window(workspace, path_context):
    """The mtime, not the clock, is what tells a user's save from the agent's."""
    notes = workspace / "notes"
    config = _config(workspace)
    handler = _handler(config.id, notes)
    target = notes / "shared.md"

    with _as_agent(config, path_context):
        create_file_write_tool(config, path_context).invoke({"path": str(target), "content": "agent"})
    assert handler._is_relevant(str(target)) is False

    target.write_text("the user typed this")
    _bump_mtime(target)

    assert handler._is_relevant(str(target)) is True


def test_suppression_expires_with_the_window(workspace, path_context):
    notes = workspace / "notes"
    config = _config(workspace)
    ledger = SelfWriteLedger(window=0.05)
    handler = _handler(config.id, notes, ledger=ledger)
    target = notes / "stale.md"
    target.write_text("x")

    ledger.commit(target, agent_id=config.id, execution_id=1)
    assert handler._is_relevant(str(target)) is False

    time.sleep(0.08)
    assert handler._is_relevant(str(target)) is True


def test_window_default_clears_the_slowest_watchdog_backend():
    """``PollingObserver`` polls once per second; the window must outlast that.

    A shrunk window is the mutation this catches — under 1s the loop comes back
    on network mounts and on any platform without a native backend.
    """
    from watchdog.observers.api import DEFAULT_OBSERVER_TIMEOUT

    assert SUPPRESSION_WINDOW >= 2 * DEFAULT_OBSERVER_TIMEOUT


# --- what the ledger records ------------------------------------------------


def test_delete_is_suppressed_and_a_later_recreation_is_not(workspace, path_context):
    notes = workspace / "notes"
    config = _config(workspace)
    handler = _handler(config.id, notes)
    target = notes / "gone.md"
    target.write_text("bye")

    with _as_agent(config, path_context):
        create_file_delete_tool(config, path_context).invoke({"path": str(target)})

    assert not target.exists()
    assert handler._is_relevant(str(target)) is False

    # Someone puts the path back: the recorded state ("absent") no longer holds.
    target.write_text("back")
    assert handler._is_relevant(str(target)) is True


def test_move_records_both_ends(workspace, path_context):
    notes = workspace / "notes"
    config = _config(workspace)
    handler = _handler(config.id, notes)
    src = notes / "draft.md"
    dst = notes / "final.md"
    src.write_text("body")

    with _as_agent(config, path_context):
        create_file_move_tool(config, path_context).invoke({"source": str(src), "destination": str(dst)})

    assert handler._is_relevant(str(src)) is False
    assert handler._is_relevant(str(dst)) is False


def test_memory_tools_record_their_writes(workspace, path_context):
    """An agent watching its own agents dir must not loop on ``memory_save``."""
    agents = workspace / "agents"
    config = _config(workspace, watch="agents")
    handler = _handler(config.id, agents)
    memory_file = path_context.get_memory_file_path(config)

    with _as_agent(config, path_context):
        create_memory_save_tool(config, path_context).invoke({"section": "facts", "content": "one"})
    assert handler._is_relevant(str(memory_file)) is False

    _bump_mtime(memory_file)
    assert handler._is_relevant(str(memory_file)) is True

    with _as_agent(config, path_context):
        create_memory_append_tool(config, path_context).invoke({"section": "facts", "content": "two"})
    assert handler._is_relevant(str(memory_file)) is False


def test_a_write_still_in_flight_is_suppressed(workspace, path_context):
    """The claim is taken before the disk changes.

    On inotify the event can reach the handler before the ``stat`` that follows
    ``write_text`` — an entry with no mtime yet still has to suppress.
    """
    notes = workspace / "notes"
    config = _config(workspace)
    handler = _handler(config.id, notes)
    target = notes / "inflight.md"

    with _as_agent(config, path_context):
        process_ledger().begin(target, agent_id=config.id, execution_id=3)
        assert handler._is_relevant(str(target)) is False


def test_a_failed_write_leaves_no_claim_behind(workspace, path_context):
    notes = workspace / "notes"
    config = _config(workspace)
    handler = _handler(config.id, notes)
    target = notes / "never.md"
    target.write_text("untouched by the agent")

    with _as_agent(config, path_context):
        with pytest.raises(OSError):
            with self_write(target):
                raise OSError("disk full")

    assert handler._is_relevant(str(target)) is True


def test_a_write_outside_an_execution_records_nothing(workspace, path_context):
    """No agent, no self-write. The ledger must not guess an owner."""
    notes = workspace / "notes"
    target = notes / "orphan.md"

    with self_write(target):
        target.write_text("from a script")

    assert _handler("notes-agent", notes)._is_relevant(str(target)) is True


def test_a_nested_execution_hands_the_context_back(workspace, path_context):
    """``run_agent`` sets a second context inside the caller's own task.

    The reset token is what restores the caller. Without it every write after a
    sub-agent call would land in the sub-agent's bucket, and the caller would
    start retriggering on its own writes again.
    """
    notes = workspace / "notes"
    parent = _config(workspace, name="parent")
    child = _config(workspace, name="child")

    with _as_agent(parent, path_context, 1):
        with _as_agent(child, path_context, 2):
            assert execution_id() == 2
            create_file_write_tool(child, path_context).invoke({"path": str(notes / "by-child.md"), "content": "child"})
        assert execution_id() == 1
        create_file_write_tool(parent, path_context).invoke({"path": str(notes / "by-parent.md"), "content": "parent"})

    handler = _handler("parent", notes)
    assert handler._is_relevant(str(notes / "by-parent.md")) is False
    # A sub-agent's write is recorded under the sub-agent — a documented limit.
    assert handler._is_relevant(str(notes / "by-child.md")) is True


# --- the declared boundary ---------------------------------------------------


def test_writes_bypassing_the_builtin_tools_still_retrigger(workspace, path_context):
    """Known limit, documented in docs/triggers.md — not a bug.

    An MCP server or a custom tool writes without the ledger, so the watcher has
    nothing to recognise and the agent retriggers itself. Covering that would
    mean intercepting arbitrary third-party code.
    """
    notes = workspace / "notes"
    config = _config(workspace)
    handler = _handler(config.id, notes)
    target = notes / "via-mcp.md"

    with _as_agent(config, path_context):
        target.write_text("written by an MCP server")

    assert handler._is_relevant(str(target)) is True


# --- context isolation ------------------------------------------------------


async def test_two_concurrent_executions_keep_separate_buckets(workspace, path_context):
    """A leak here would let one execution suppress another agent's trigger."""
    notes = workspace / "notes"
    seen: dict[str, int | None] = {}
    targets = {"agent-a": notes / "a.md", "agent-b": notes / "b.md"}

    async def execute(name: str, exec_id: int, pause: float) -> None:
        config = _config(workspace, name=name)
        token = _set_context(config, path_context, exec_id)
        try:
            # Suspend between setting the context and using it, so the two tasks
            # genuinely interleave rather than running back to back.
            await asyncio.sleep(pause)
            seen[name] = execution_id()
            create_file_write_tool(config, path_context).invoke({"path": str(targets[name]), "content": name})
        finally:
            _reset_context(token)

    await asyncio.wait_for(
        asyncio.gather(
            asyncio.create_task(execute("agent-a", 11, 0.02)),
            asyncio.create_task(execute("agent-b", 22, 0.0)),
        ),
        timeout=EVENT_TIMEOUT,
    )

    assert seen == {"agent-a": 11, "agent-b": 22}

    handler_a = _handler("agent-a", notes)
    handler_b = _handler("agent-b", notes)
    assert handler_a._is_relevant(str(targets["agent-a"])) is False
    assert handler_a._is_relevant(str(targets["agent-b"])) is True
    assert handler_b._is_relevant(str(targets["agent-b"])) is False
    assert handler_b._is_relevant(str(targets["agent-a"])) is True

    # Neither task's context survived into the caller's.
    with pytest.raises(RuntimeError, match="agent execution"):
        execution_id()


async def test_tool_invoked_through_the_async_path_still_sees_the_context(workspace, path_context):
    """LangChain runs a sync tool in an executor; the ContextVar must ride along.

    ``file_write`` reads its config from a closure but the ledger reads the
    ContextVar, so the executor hop is load-bearing for suppression.
    """
    notes = workspace / "notes"
    config = _config(workspace)
    handler = _handler(config.id, notes)
    target = notes / "async.md"

    with _as_agent(config, path_context, 42):
        await asyncio.wait_for(
            create_file_write_tool(config, path_context).ainvoke({"path": str(target), "content": "x"}),
            timeout=EVENT_TIMEOUT,
        )

    assert handler._is_relevant(str(target)) is False


async def test_runner_puts_the_execution_id_in_the_sdk_context():
    """Wiring assertion: without this the ledger has no execution to attribute."""
    config = MagicMock()
    config.name = "wired"
    config.id = "wired"
    config.model.provider = "google"
    config.model.name = "gemini-2.0-flash"
    config.model.base_url = None
    config.settings.temperature = 0.7
    config.settings.max_tokens = 4096
    config.settings.timeout = 300
    config.settings.max_tool_calls = None
    config.settings.max_execution_tokens = None
    config.settings.max_cost_usd = None
    config.settings.loop_detection = False
    config.settings.model_dump.return_value = {}
    config.history = "off"
    config.system_prompt = "You are a test agent."
    config.custom_tools = []
    config.mcp = []
    config.skills = []
    config.paths = {}

    from agent_md.execution.runner import AgentRunner

    db = AsyncMock()
    db.create_execution = AsyncMock(return_value=4242)
    db.update_execution = AsyncMock()
    db.add_log = AsyncMock()

    runner = AgentRunner(db, MagicMock(), MagicMock())
    captured: dict = {}

    final = MagicMock()
    final.type = "ai"
    final.content = "done"
    final.tool_calls = []
    final.usage_metadata = {"input_tokens": 1, "output_tokens": 1}

    with patch.object(runner, "_build_graph", new_callable=AsyncMock) as build:
        build.return_value = (MagicMock(), None)
        with patch("agent_md.execution.runner.stream_agent_graph") as stream:

            async def fake_stream(*args, **kwargs):
                from agent_md.sdk import _current_execution

                ctx = _current_execution()
                captured["execution_id"] = ctx.execution_id if ctx else None
                captured["agent_id"] = ctx.agent_config.id if ctx else None
                yield final

            stream.return_value = fake_stream()
            result = await runner.run(config)

    assert result["status"] == "success"
    assert captured == {"execution_id": 4242, "agent_id": "wired"}


# --- end to end, through a real observer ------------------------------------


async def test_real_watchdog_ignores_the_agents_write_and_keeps_the_users(workspace, path_context):
    """The whole chain: tool → filesystem → watchdog thread → trigger decision.

    The unit tests above call ``_is_relevant`` directly; only this one proves the
    event really never becomes a trigger.
    """
    from watchdog.observers import Observer

    notes = workspace / "notes"
    config = _config(workspace)
    triggered: asyncio.Queue[str] = asyncio.Queue()

    async def execute(agent_id, trigger_type, trigger_context=None):
        await triggered.put(trigger_context or "")

    handler = _handler(
        config.id,
        notes,
        execute_fn=execute,
        loop=asyncio.get_running_loop(),
        debounce=0.05,
    )
    observer = Observer()
    observer.schedule(handler, str(notes), recursive=True)
    observer.start()
    try:
        await asyncio.sleep(0.3)  # let the event stream settle before writing

        with _as_agent(config, path_context, 99):
            create_file_write_tool(config, path_context).invoke({"path": str(notes / "by-agent.md"), "content": "self"})

        try:
            leaked = await asyncio.wait_for(triggered.get(), QUIET_TIMEOUT)
        except asyncio.TimeoutError:
            pass
        else:
            pytest.fail(f"the agent's own write triggered it: {leaked}")

        (notes / "by-user.md").write_text("hello")
        context = await asyncio.wait_for(triggered.get(), EVENT_TIMEOUT)
        assert "by-user.md" in context
    finally:
        observer.stop()
        observer.join(timeout=5)
