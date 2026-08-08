"""The generated preamble must not outrank the agent's own prompt.

Regression guard for a real failure: an agent whose entire prompt was
``Responda: ok.`` received ~1150 characters of imperative tool documentation
ahead of it and answered by demonstrating file_write, file_read, file_edit,
file_move and file_delete — then reported that it had "successfully
demonstrated" them. It followed the manual instead of the user.
"""

from __future__ import annotations

from pathlib import Path

from agent_md.config.models import AgentConfig
from agent_md.graph.builder import build_system_message
from agent_md.workspace.path_context import PathContext


def _path_context(tmp_path: Path) -> PathContext:
    agents = tmp_path / "agents"
    agents.mkdir(exist_ok=True)
    return PathContext(
        workspace_root=tmp_path,
        agents_dir=agents,
        db_path=tmp_path / "db.sqlite",
        mcp_config=tmp_path / "mcp.json",
        tools_dir=agents,
        skills_dir=agents,
    )


def _message(tmp_path: Path, prompt: str) -> str:
    cfg = AgentConfig(name="t")
    cfg.system_prompt = prompt
    return build_system_message(
        prompt,
        agent_config=cfg,
        path_context=_path_context(tmp_path),
        arguments="",
    ).content


def test_agent_prompt_comes_last_under_its_own_heading(tmp_path):
    content = _message(tmp_path, "Responda: ok.")

    assert "# Your task" in content
    assert content.rstrip().endswith("Responda: ok.")
    # The reference material must not sit between the heading and the task.
    task_section = content.split("# Your task", 1)[1]
    assert task_section.strip() == "Responda: ok."


def test_preamble_is_framed_as_reference_not_instruction(tmp_path):
    content = _message(tmp_path, "Responda: ok.")
    preamble = content.split("# Your task", 1)[0]

    assert "reference material, not instructions" in preamble
    assert "listing a tool is not a request to use it" in preamble


def test_preamble_does_not_command_tool_use(tmp_path):
    """No unconditional call to action for tools the task may not need."""
    preamble = _message(tmp_path, "Responda: ok.").split("# Your task", 1)[0]

    forbidden = [
        "Use memory_save to start persisting",  # drove unprompted memory writes
        "Never guess filenames",  # absolute order, unrelated to the task
        "**Always read a file",  # same
    ]
    for phrase in forbidden:
        assert phrase not in preamble, f"preamble still commands: {phrase!r}"


def test_file_tool_list_matches_the_tools_actually_attached(tmp_path):
    """The preamble claimed 'four file tools' while six are attached.

    file_move and file_delete were undocumented yet available — the agent used
    both, including the destructive one.
    """
    preamble = _message(tmp_path, "Responda: ok.").split("# Your task", 1)[0]

    assert "four file tools" not in preamble
    for tool in ("file_read", "file_glob", "file_write", "file_edit", "file_move", "file_delete"):
        assert tool in preamble, f"{tool} attached to the agent but absent from the prompt"


def test_empty_agent_prompt_produces_no_task_heading(tmp_path):
    """An agent with an empty body must not get a heading promising a task."""
    content = _message(tmp_path, "   ")
    assert "# Your task" not in content


def test_substitutions_still_apply_to_the_task(tmp_path):
    cfg = AgentConfig(name="t")
    content = build_system_message(
        "Process $0 in mode $1",
        agent_config=cfg,
        path_context=_path_context(tmp_path),
        arguments=["report.md", "verbose"],
    ).content

    assert content.rstrip().endswith("Process report.md in mode verbose")
