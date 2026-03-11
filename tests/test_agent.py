"""Tests for IncAgent core functionality."""


import pytest

from incagent import Contract, ContractTerms, IncAgent, NegotiationPolicy
from incagent.messaging import MessageBus


@pytest.fixture
def bus():
    return MessageBus()


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


def test_agent_creation(bus, tmp_dir):
    agent = IncAgent(name="TestCorp", role="buyer", autonomous_mode=True, message_bus=bus, data_dir=tmp_dir)
    assert agent.name == "TestCorp"
    assert agent.identity.role == "buyer"
    assert agent.state.value == "idle"
    agent.close()


def test_agent_identity_fingerprint(bus, tmp_dir):
    agent = IncAgent(name="TestCorp", message_bus=bus, data_dir=tmp_dir)
    fp = agent.identity.fingerprint()
    assert len(fp) == 16
    assert fp == agent.identity.fingerprint()  # deterministic
    agent.close()


def test_agent_health_status(bus, tmp_dir):
    agent = IncAgent(name="TestCorp", autonomous_mode=True, message_bus=bus, data_dir=tmp_dir)
    status = agent.health_status()
    assert status["name"] == "TestCorp"
    assert status["state"] == "idle"
    assert status["circuit_breaker"] == "closed"
    assert status["ledger_valid"] is True
    agent.close()


def test_agent_ledger_records_creation(bus, tmp_dir):
    agent = IncAgent(name="TestCorp", message_bus=bus, data_dir=tmp_dir)
    entries = agent.get_ledger_entries()
    assert len(entries) >= 1
    assert entries[0]["action"] == "agent_created"
    agent.close()


@pytest.mark.asyncio
async def test_simple_negotiation(bus, tmp_dir):
    buyer = IncAgent(name="Buyer", role="buyer", autonomous_mode=True, message_bus=bus, data_dir=tmp_dir / "buyer")
    seller = IncAgent(name="Seller", role="seller", autonomous_mode=True, message_bus=bus, data_dir=tmp_dir / "seller")

    contract = Contract(
        title="Test Contract",
        terms=ContractTerms(quantity=100, unit_price_range=(10.0, 50.0)),
    )
    policy = NegotiationPolicy(min_price=10.0, max_price=50.0, max_rounds=3)

    result = await buyer.negotiate(contract, counterparty=seller, policy=policy)
    assert result.status.value in ("agreed", "rejected", "timeout")
    assert result.rounds >= 1

    buyer.close()
    seller.close()


@pytest.mark.asyncio
async def test_negotiation_records_in_ledger(bus, tmp_dir):
    buyer = IncAgent(name="Buyer", autonomous_mode=True, message_bus=bus, data_dir=tmp_dir / "buyer")
    seller = IncAgent(name="Seller", autonomous_mode=True, message_bus=bus, data_dir=tmp_dir / "seller")

    contract = Contract(
        title="Ledger Test",
        terms=ContractTerms(quantity=10, unit_price=25.0),
    )
    policy = NegotiationPolicy(min_price=20.0, max_price=30.0, max_rounds=2)

    await buyer.negotiate(contract, counterparty=seller, policy=policy)

    entries = buyer.get_ledger_entries(limit=10)
    actions = [e["action"] for e in entries]
    assert "negotiation_started" in actions

    buyer.close()
    seller.close()
