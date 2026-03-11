"""Tests for negotiation engine (rule-based fallback only, no LLM needed)."""

import pytest

from incagent import Contract, ContractTerms
from incagent.negotiation import NegotiationEngine, NegotiationPolicy


@pytest.mark.asyncio
async def test_rule_based_negotiation():
    """Test that negotiation works without LLM (falls back to rule-based)."""
    engine = NegotiationEngine()

    contract = Contract(
        title="Test Negotiation",
        terms=ContractTerms(quantity=100, unit_price=50.0),
    )
    contract.propose("buyer_1", "seller_1")

    policy = NegotiationPolicy(
        min_price=40.0,
        max_price=60.0,
        max_rounds=5,
    )

    result = await engine.negotiate(contract, policy)
    assert result.status.value in ("agreed", "rejected", "timeout")
    assert result.rounds >= 1


@pytest.mark.asyncio
async def test_walk_away():
    """Agent should walk away if value is below threshold."""
    engine = NegotiationEngine()

    contract = Contract(
        title="Low Value Deal",
        terms=ContractTerms(quantity=1, unit_price=5.0),
    )
    contract.propose("buyer_1", "seller_1")

    policy = NegotiationPolicy(
        min_price=10.0,
        max_price=100.0,
        max_rounds=3,
        walk_away_threshold=1000.0,
    )

    result = await engine.negotiate(contract, policy)
    assert result.status.value in ("rejected", "timeout")


@pytest.mark.asyncio
async def test_max_rounds_respected():
    engine = NegotiationEngine()

    contract = Contract(
        title="Long Negotiation",
        terms=ContractTerms(quantity=100, unit_price_range=(1.0, 1000.0)),
    )
    contract.propose("a", "b")

    policy = NegotiationPolicy(max_rounds=3)

    result = await engine.negotiate(contract, policy)
    assert result.rounds <= 3
