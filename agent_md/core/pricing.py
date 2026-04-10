# agent_md/core/pricing.py
"""Pricing registry — built-in + user override for cost estimation."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_BUILTIN_PATH = Path(__file__).parent / "pricing.yaml"


def _get_user_pricing_path() -> Path:
    """Return ~/.config/agentmd/pricing.yaml."""
    return Path.home() / ".config" / "agentmd" / "pricing.yaml"


def load_pricing() -> dict:
    """Load built-in pricing + user override, returning merged dict."""
    with open(_BUILTIN_PATH) as f:
        pricing = yaml.safe_load(f) or {}

    user_path = _get_user_pricing_path()
    if user_path.is_file():
        with open(user_path) as f:
            user = yaml.safe_load(f) or {}
        # Deep merge: provider → model level
        for provider, models in user.items():
            if provider not in pricing:
                pricing[provider] = {}
            if isinstance(models, dict):
                pricing[provider].update(models)

    return pricing


def estimate_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float | None:
    """Return estimated USD cost, or None if pricing unknown for this model."""
    pricing = load_pricing()
    provider_pricing = pricing.get(provider, {})
    model_pricing = provider_pricing.get(model)

    if model_pricing is None:
        return None

    input_price = model_pricing.get("input")
    output_price = model_pricing.get("output")

    if input_price is None or output_price is None:
        return None

    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000
