# tests/test_pricing.py
"""Tests for the pricing registry."""

import pytest
from unittest.mock import patch


def test_load_builtin_pricing():
    """Built-in pricing.yaml loads correctly."""
    from agent_md.core.pricing import load_pricing

    pricing = load_pricing()
    assert "google" in pricing
    assert "gemini-2.0-flash" in pricing["google"]
    assert pricing["google"]["gemini-2.0-flash"]["input"] == 0.10
    assert pricing["google"]["gemini-2.0-flash"]["output"] == 0.40


def test_estimate_cost_known_model():
    """Cost estimation for a known model returns correct value."""
    from agent_md.core.pricing import estimate_cost

    # gemini-2.0-flash: $0.10/1M input, $0.40/1M output
    cost = estimate_cost("google", "gemini-2.0-flash", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost is not None
    assert abs(cost - 0.50) < 0.001  # $0.10 + $0.40


def test_estimate_cost_unknown_model():
    """Cost estimation for an unknown model returns None."""
    from agent_md.core.pricing import estimate_cost

    cost = estimate_cost("google", "nonexistent-model", input_tokens=1000, output_tokens=1000)
    assert cost is None


def test_user_override_merges(tmp_path):
    """User override file merges with built-in pricing."""
    import agent_md.core.pricing as pricing_mod
    from agent_md.core.pricing import load_pricing

    override = tmp_path / "pricing.yaml"
    override.write_text(
        "google:\n  gemini-2.0-flash:\n    input: 0.20\n    output: 0.80\n"
        "  custom-model:\n    input: 1.00\n    output: 2.00\n"
    )

    # Clear cache so override is picked up
    pricing_mod._pricing_cache = None
    with patch("agent_md.core.pricing._get_user_pricing_path", return_value=override):
        pricing = load_pricing()
    pricing_mod._pricing_cache = None  # Reset for other tests

    # Overridden values
    assert pricing["google"]["gemini-2.0-flash"]["input"] == 0.20
    assert pricing["google"]["gemini-2.0-flash"]["output"] == 0.80
    # New model added
    assert pricing["google"]["custom-model"]["input"] == 1.00
    # Other providers still present
    assert "openai" in pricing


def test_estimate_cost_small_numbers():
    """Cost estimation with small token counts."""
    from agent_md.core.pricing import estimate_cost

    # gpt-4o: $2.50/1M input, $10.00/1M output
    cost = estimate_cost("openai", "gpt-4o", input_tokens=1000, output_tokens=500)
    assert cost is not None
    # 1000 * 2.50/1M + 500 * 10.00/1M = 0.0025 + 0.005 = 0.0075
    assert abs(cost - 0.0075) < 0.0001
