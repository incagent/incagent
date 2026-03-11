"""Tests for transaction management."""


from incagent.ledger import Ledger
from incagent.transaction import Transaction, TransactionManager, TransactionStatus


def test_transaction_creation():
    t = Transaction(
        contract_id="c1",
        buyer_id="buyer",
        seller_id="seller",
        amount=1000.0,
    )
    assert t.status == TransactionStatus.PENDING
    assert t.amount == 1000.0


def test_transaction_lifecycle():
    t = Transaction(
        contract_id="c1",
        buyer_id="buyer",
        seller_id="seller",
        amount=500.0,
    )
    t.execute()
    assert t.status == TransactionStatus.EXECUTING

    t.complete()
    assert t.status == TransactionStatus.COMPLETED
    assert t.completed_at is not None


def test_transaction_failure():
    t = Transaction(
        contract_id="c1",
        buyer_id="buyer",
        seller_id="seller",
        amount=500.0,
    )
    t.execute()
    t.fail("Network error")
    assert t.status == TransactionStatus.FAILED
    assert t.error == "Network error"


def test_transaction_manager(tmp_path):
    ledger = Ledger(tmp_path / "test.db")
    tm = TransactionManager(ledger)

    txn = tm.create("c1", "buyer", "seller", 1000.0)
    assert txn.status == TransactionStatus.PENDING

    tm.execute(txn.transaction_id)
    assert txn.status == TransactionStatus.EXECUTING

    tm.complete(txn.transaction_id)
    assert txn.status == TransactionStatus.COMPLETED

    # Verify ledger recorded the events
    entries = ledger.query(action="transaction_completed")
    assert len(entries) >= 1

    ledger.close()


def test_ledger_chain_integrity(tmp_path):
    ledger = Ledger(tmp_path / "chain.db")

    ledger.append("agent1", "action1", {"key": "val1"})
    ledger.append("agent1", "action2", {"key": "val2"})
    ledger.append("agent2", "action3", {"key": "val3"})

    assert ledger.verify_chain() is True

    ledger.close()


def test_ledger_export(tmp_path):
    ledger = Ledger(tmp_path / "export.db")

    ledger.append("agent1", "test", {"data": 123})
    output = ledger.export_json()
    assert '"agent1"' in output
    assert '"test"' in output

    ledger.close()
