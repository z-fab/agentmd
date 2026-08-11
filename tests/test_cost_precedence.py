"""Reported cost beats estimated cost, and the two are never summed.

estimate_cost() recomputes from cumulative totals; reported cost arrives per
response and accumulates. Mixing them yields a number that is neither.
"""

from __future__ import annotations

from agent_md.execution.runner import _resolve_cost


def test_reported_cost_wins_over_estimate():
    assert _resolve_cost(reported=0.0042, estimated=0.0100) == 0.0042


def test_estimate_used_when_nothing_reported():
    assert _resolve_cost(reported=None, estimated=0.0100) == 0.0100


def test_none_when_neither_available():
    assert _resolve_cost(reported=None, estimated=None) is None


def test_zero_reported_is_still_reported():
    """A genuinely free model reports 0.0 — that is data, not absence."""
    assert _resolve_cost(reported=0.0, estimated=0.0100) == 0.0


def test_message_reported_cost_ignores_magicmock():
    """MagicMock.response_metadata.get('cost') is truthy and float()s to 1.0."""
    from unittest.mock import MagicMock

    from agent_md.execution.runner import _message_reported_cost

    msg = MagicMock()
    assert _message_reported_cost(msg) is None


def test_message_reported_cost_reads_dict():
    from types import SimpleNamespace

    from agent_md.execution.runner import _message_reported_cost

    msg = SimpleNamespace(response_metadata={"cost": 0.0042})
    assert _message_reported_cost(msg) == 0.0042
