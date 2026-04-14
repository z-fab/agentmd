from agent_md.config.models import AgentConfig
from agent_md.graph.builder import build_system_message


def test_arguments_substituted_in_system_prompt():
    cfg = AgentConfig(name="t")
    cfg.system_prompt = "Process file $0 with mode $1"
    msg = build_system_message(
        cfg.system_prompt,
        agent_config=cfg,
        path_context=None,
        arguments="report.md\nverbose",
    )
    assert "Process file report.md with mode verbose" in msg.content


def test_command_injection_in_system_prompt(tmp_path):
    cfg = AgentConfig(name="t")
    cfg.system_prompt = "Today: !`echo hello`"
    msg = build_system_message(
        cfg.system_prompt,
        agent_config=cfg,
        path_context=None,
        arguments="",
    )
    assert "Today: hello" in msg.content
