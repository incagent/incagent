"""Contract definition, lifecycle, and management."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ContractStatus(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    NEGOTIATING = "negotiating"
    AGREED = "agreed"
    EXECUTED = "executed"
    COMPLETED = "completed"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"


class ContractTerms(BaseModel):
    """The negotiable terms of a contract."""

    quantity: int | None = None
    unit_price: float | None = None
    unit_price_range: tuple[float, float] | None = None
    total_value: float | None = None
    currency: str = "USD"
    delivery_days: int | None = None
    payment_terms: str = "net_30"
    custom: dict[str, Any] = Field(default_factory=dict)

    def estimated_value(self) -> float:
        """Calculate estimated contract value."""
        if self.total_value is not None:
            return self.total_value
        if self.quantity and self.unit_price:
            return self.quantity * self.unit_price
        if self.quantity and self.unit_price_range:
            mid = (self.unit_price_range[0] + self.unit_price_range[1]) / 2
            return self.quantity * mid
        return 0.0


class Contract(BaseModel):
    """A contract between two AI agents."""

    contract_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    terms: ContractTerms
    status: ContractStatus = ContractStatus.DRAFT
    proposer_id: str = ""
    counterparty_id: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agreed_at: datetime | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)
    signatures: dict[str, str] = Field(default_factory=dict)

    def propose(self, proposer_id: str, counterparty_id: str) -> None:
        """Propose this contract to a counterparty."""
        self.proposer_id = proposer_id
        self.counterparty_id = counterparty_id
        self._transition(ContractStatus.PROPOSED)

    def start_negotiation(self) -> None:
        self._transition(ContractStatus.NEGOTIATING)

    def agree(self) -> None:
        self._transition(ContractStatus.AGREED)
        self.agreed_at = datetime.now(timezone.utc)

    def execute(self) -> None:
        self._transition(ContractStatus.EXECUTED)

    def complete(self) -> None:
        self._transition(ContractStatus.COMPLETED)

    def dispute(self, reason: str = "") -> None:
        self._transition(ContractStatus.DISPUTED, note=reason)

    def cancel(self, reason: str = "") -> None:
        self._transition(ContractStatus.CANCELLED, note=reason)

    def sign(self, agent_id: str, signature: str) -> None:
        """Add a cryptographic signature from an agent."""
        self.signatures[agent_id] = signature
        self._add_history("signed", agent_id=agent_id)

    def is_fully_signed(self) -> bool:
        return (
            self.proposer_id in self.signatures
            and self.counterparty_id in self.signatures
        )

    def _transition(self, new_status: ContractStatus, note: str = "") -> None:
        old = self.status
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc)
        self._add_history(
            f"status_change:{old.value}->{new_status.value}",
            note=note,
        )

    def _add_history(self, action: str, **kwargs: Any) -> None:
        entry = {
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **kwargs,
        }
        self.history.append(entry)
