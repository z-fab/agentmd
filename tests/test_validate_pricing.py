"""Tests for pricing warnings in validate."""

from agent_md.workspace.services import validate_agent


def test_validate_warns_cost_limit_no_pricing(tmp_path):
    """validate_agent warns when max_cost_usd is set but model has no pricing."""
    agent_file = tmp_path / "test-agent.md"
    agent_file.write_text(
        "---\n"
        "name: test-agent\n"
        "model:\n"
        "  provider: google\n"
        "  name: unknown-model-xyz\n"
        "settings:\n"
        "  max_cost_usd: 0.50\n"
        "---\n"
        "You are a test agent.\n"
    )

    result = validate_agent(agent_file)
    cost_warnings = [w for w in result.warnings if "max_cost_usd" in w]
    assert len(cost_warnings) == 1
    assert "no pricing data" in cost_warnings[0].lower()


def test_validate_no_warn_when_pricing_exists(tmp_path):
    """No warning when model has pricing data."""
    agent_file = tmp_path / "test-agent.md"
    agent_file.write_text(
        "---\n"
        "name: test-agent\n"
        "model:\n"
        "  provider: google\n"
        "  name: gemini-2.0-flash\n"
        "settings:\n"
        "  max_cost_usd: 0.50\n"
        "---\n"
        "You are a test agent.\n"
    )

    result = validate_agent(agent_file)
    cost_warnings = [w for w in result.warnings if "max_cost_usd" in w]
    assert len(cost_warnings) == 0


def test_validate_no_warn_when_no_cost_limit(tmp_path):
    """No warning when max_cost_usd is not set (even with unknown model)."""
    agent_file = tmp_path / "test-agent.md"
    agent_file.write_text(
        "---\n"
        "name: test-agent\n"
        "model:\n"
        "  provider: google\n"
        "  name: unknown-model-xyz\n"
        "---\n"
        "You are a test agent.\n"
    )

    result = validate_agent(agent_file)
    cost_warnings = [w for w in result.warnings if "max_cost_usd" in w]
    assert len(cost_warnings) == 0
