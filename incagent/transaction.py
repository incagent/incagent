"""Transaction execution and tracking."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TransactionStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class Transaction(BaseModel):
    """A single transaction between two agents."""

    transaction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    contract_id: str
    buyer_id: str
    seller_id: str
    amount: float
    currency: str = "USD"
    status: TransactionStatus = TransactionStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def execute(self) -> None:
        """Mark transaction as executing."""
        self.status = TransactionStatus.EXECUTING

    def complete(self) -> None:
        """Mark transaction as completed."""
        self.status = TransactionStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)

    def fail(self, error: str) -> None:
        """Mark transaction as failed."""
        self.status = TransactionStatus.FAILED
        self.error = error

    def rollback(self) -> None:
        """Mark transaction as rolled back."""
        self.status = TransactionStatus.ROLLED_BACK

    def to_ledger_entry(self) -> dict[str, Any]:
        """Convert to a dict suitable for ledger recording."""
        return {
            "transaction_id": self.transaction_id,
            "contract_id": self.contract_id,
            "buyer_id": self.buyer_id,
            "seller_id": self.seller_id,
            "amount": self.amount,
            "currency": self.currency,
            "status": self.status.value,
        }


class TransactionManager:
    """Manages transaction lifecycle with ledger integration."""

    def __init__(self, ledger: Any) -> None:
        self._ledger = ledger
        self._transactions: dict[str, Transaction] = {}

    def create(self, contract_id: str, buyer_id: str, seller_id: str, amount: float, currency: str = "USD") -> Transaction:
        txn = Transaction(
            contract_id=contract_id,
            buyer_id=buyer_id,
            seller_id=seller_id,
            amount=amount,
            currency=currency,
        )
        self._transactions[txn.transaction_id] = txn
        self._ledger.append(buyer_id, "transaction_created", txn.to_ledger_entry())
        return txn

    def execute(self, transaction_id: str) -> Transaction:
        txn = self._transactions[transaction_id]
        txn.execute()
        self._ledger.append(txn.buyer_id, "transaction_executing", txn.to_ledger_entry())
        return txn

    def complete(self, transaction_id: str) -> Transaction:
        txn = self._transactions[transaction_id]
        txn.complete()
        self._ledger.append(txn.buyer_id, "transaction_completed", txn.to_ledger_entry())
        return txn

    def fail(self, transaction_id: str, error: str) -> Transaction:
        txn = self._transactions[transaction_id]
        txn.fail(error)
        self._ledger.append(txn.buyer_id, "transaction_failed", {"error": error, **txn.to_ledger_entry()})
        return txn

    def get(self, transaction_id: str) -> Transaction | None:
        return self._transactions.get(transaction_id)
