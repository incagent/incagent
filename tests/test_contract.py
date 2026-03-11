"""Tests for contract lifecycle."""

from incagent import Contract, ContractStatus, ContractTerms


def test_contract_creation():
    c = Contract(
        title="Test Contract",
        terms=ContractTerms(quantity=100, unit_price=50.0),
    )
    assert c.status == ContractStatus.DRAFT
    assert c.title == "Test Contract"
    assert c.terms.quantity == 100


def test_contract_lifecycle():
    c = Contract(
        title="Lifecycle Test",
        terms=ContractTerms(quantity=50, unit_price=25.0),
    )
    c.propose("agent_a", "agent_b")
    assert c.status == ContractStatus.PROPOSED
    assert c.proposer_id == "agent_a"
    assert c.counterparty_id == "agent_b"

    c.start_negotiation()
    assert c.status == ContractStatus.NEGOTIATING

    c.agree()
    assert c.status == ContractStatus.AGREED
    assert c.agreed_at is not None

    c.execute()
    assert c.status == ContractStatus.EXECUTED

    c.complete()
    assert c.status == ContractStatus.COMPLETED


def test_contract_history():
    c = Contract(
        title="History Test",
        terms=ContractTerms(quantity=10, unit_price=10.0),
    )
    c.propose("a", "b")
    c.start_negotiation()
    c.agree()
    assert len(c.history) == 3


def test_contract_signing():
    c = Contract(
        title="Signing Test",
        terms=ContractTerms(quantity=10, unit_price=10.0),
    )
    c.propose("agent_a", "agent_b")
    assert not c.is_fully_signed()

    c.sign("agent_a", "sig_a")
    assert not c.is_fully_signed()

    c.sign("agent_b", "sig_b")
    assert c.is_fully_signed()


def test_contract_estimated_value():
    t1 = ContractTerms(quantity=100, unit_price=50.0)
    assert t1.estimated_value() == 5000.0

    t2 = ContractTerms(quantity=100, unit_price_range=(40.0, 60.0))
    assert t2.estimated_value() == 5000.0

    t3 = ContractTerms(total_value=7500.0)
    assert t3.estimated_value() == 7500.0


def test_contract_cancel():
    c = Contract(
        title="Cancel Test",
        terms=ContractTerms(quantity=10, unit_price=10.0),
    )
    c.propose("a", "b")
    c.cancel("Changed mind")
    assert c.status == ContractStatus.CANCELLED
