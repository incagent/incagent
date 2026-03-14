"""Settlement Engine — the full trade lifecycle from payment to delivery.

Orchestrates:
1. Payment (USDC transfer or escrow deposit)
2. Delivery (digital auto-verify or physical human-confirm)
3. Release (escrow release on verification)
4. Dispute (evidence-based resolution)

This is the missing piece that connects negotiation to real-world execution.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from incagent.delivery import DeliveryRecord, DeliveryStatus, DeliveryType, DeliveryVerifier
from incagent.payment import PaymentConfig, PaymentExecutor, PaymentRecord, PaymentStatus

logger = logging.getLogger("incagent.settlement")


class SettlementMode(str, Enum):
    DIRECT = "direct"    # Pay now, deliver later (trust-based)
    ESCROW = "escrow"    # Lock funds, release on delivery (trustless)
    PREPAID = "prepaid"  # Pay before delivery starts
    COD = "cod"          # Cash on delivery (pay after verification)


class DisputeStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED_BUYER = "resolved_buyer"    # Buyer wins, refund
    RESOLVED_SELLER = "resolved_seller"  # Seller wins, release
    RESOLVED_SPLIT = "resolved_split"    # Split resolution
    EXPIRED = "expired"


class Dispute(BaseModel):
    """A dispute between buyer and seller."""

    dispute_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    settlement_id: str
    filed_by: str  # agent_id
    reason: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    status: DisputeStatus = DisputeStatus.OPEN
    resolution: str = ""
    filed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None


class SettlementRecord(BaseModel):
    """Complete settlement record tying payment + delivery together."""

    settlement_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    transaction_id: str
    contract_id: str
    buyer_id: str
    seller_id: str
    amount_usdc: float
    mode: SettlementMode = SettlementMode.DIRECT
    payment: PaymentRecord | None = None
    delivery: DeliveryRecord | None = None
    dispute: Dispute | None = None
    status: str = "pending"  # pending, paid, delivering, verified, completed, disputed, refunded
    buyer_wallet: str = ""
    seller_wallet: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


class SettlementEngine:
    """Orchestrates the full trade settlement lifecycle.

    Usage:
        engine = SettlementEngine(payment_config=PaymentConfig(...))

        # Create settlement after negotiation
        settlement = engine.create_settlement(
            transaction_id="...",
            contract_id="...",
            buyer_id="...", seller_id="...",
            amount_usdc=5000.0,
            seller_wallet="0x...",
            mode=SettlementMode.DIRECT,
        )

        # Execute payment
        await engine.execute_payment(settlement.settlement_id)

        # Verify delivery (auto for digital, human for physical)
        await engine.verify_delivery(settlement.settlement_id)

        # Complete settlement
        await engine.complete(settlement.settlement_id)
    """

    def __init__(
        self,
        payment_config: PaymentConfig | None = None,
    ) -> None:
        self._payment = PaymentExecutor(payment_config)
        self._delivery = DeliveryVerifier()
        self._settlements: dict[str, SettlementRecord] = {}
        self._disputes: dict[str, Dispute] = {}

    @property
    def payment_executor(self) -> PaymentExecutor:
        return self._payment

    @property
    def delivery_verifier(self) -> DeliveryVerifier:
        return self._delivery

    def create_settlement(
        self,
        transaction_id: str,
        contract_id: str,
        buyer_id: str,
        seller_id: str,
        amount_usdc: float,
        seller_wallet: str = "",
        mode: SettlementMode = SettlementMode.DIRECT,
        delivery_type: DeliveryType = DeliveryType.DIGITAL,
        delivery_days: int | None = None,
    ) -> SettlementRecord:
        """Create a settlement after contract is agreed."""
        settlement = SettlementRecord(
            transaction_id=transaction_id,
            contract_id=contract_id,
            buyer_id=buyer_id,
            seller_id=seller_id,
            amount_usdc=amount_usdc,
            mode=mode,
            buyer_wallet=self._payment.wallet_address,
            seller_wallet=seller_wallet,
        )

        # Create delivery tracking
        delivery = self._delivery.create_delivery(
            transaction_id=transaction_id,
            contract_id=contract_id,
            delivery_type=delivery_type,
            expected_days=delivery_days,
        )
        settlement.delivery = delivery

        self._settlements[settlement.settlement_id] = settlement
        logger.info(
            "Settlement created: %s (mode=%s, $%.2f USDC)",
            settlement.settlement_id, mode.value, amount_usdc,
        )
        return settlement

    async def execute_payment(
        self,
        settlement_id: str,
        lock_seconds: int = 86400,
        contract_terms_json: str = "",
    ) -> PaymentRecord | None:
        """Execute the payment for a settlement.

        For ESCROW mode, deposits funds into the on-chain escrow contract.
        For DIRECT/PREPAID/COD, transfers USDC directly to seller.

        Args:
            settlement_id: Settlement to pay
            lock_seconds: Escrow lock duration (default 24h). Only for ESCROW mode.
            contract_terms_json: Contract terms JSON for on-chain hash. Only for ESCROW mode.
        """
        settlement = self._settlements.get(settlement_id)
        if not settlement:
            logger.error("Settlement not found: %s", settlement_id)
            return None

        if not settlement.seller_wallet:
            logger.error("No seller wallet configured for settlement %s", settlement_id)
            return None

        # Route to escrow or direct based on settlement mode
        if settlement.mode == SettlementMode.ESCROW:
            payment = await self._payment.escrow_deposit(
                seller_address=settlement.seller_wallet,
                amount_usdc=settlement.amount_usdc,
                lock_seconds=lock_seconds,
                contract_id=settlement.contract_id,
                contract_terms_json=contract_terms_json,
            )
        else:
            payment = await self._payment.transfer_usdc(
                to_address=settlement.seller_wallet,
                amount_usdc=settlement.amount_usdc,
                transaction_id=settlement.transaction_id,
            )

        settlement.payment = payment

        if settlement.mode == SettlementMode.ESCROW:
            if payment.status == PaymentStatus.ESCROWED:
                settlement.status = "escrowed"
                logger.info("Settlement %s: funds escrowed (tx=%s)", settlement_id, payment.tx_hash[:16])
            else:
                settlement.status = "payment_failed"
                logger.error("Settlement %s: escrow deposit failed: %s", settlement_id, payment.error)
        else:
            if payment.status == PaymentStatus.CONFIRMED:
                settlement.status = "paid"
                logger.info("Settlement %s: payment confirmed (tx=%s)", settlement_id, payment.tx_hash[:16])
            else:
                settlement.status = "payment_failed"
                logger.error("Settlement %s: payment failed: %s", settlement_id, payment.error)

        return payment

    async def verify_delivery(
        self,
        settlement_id: str,
        check_url: str | None = None,
        check_api_key: str | None = None,
    ) -> bool:
        """Verify delivery for a settlement."""
        settlement = self._settlements.get(settlement_id)
        if not settlement or not settlement.delivery:
            return False

        delivery = settlement.delivery
        settlement.status = "delivering"

        # Digital: auto-verify
        if delivery.delivery_type == DeliveryType.DIGITAL:
            verified = await self._delivery.verify_digital_delivery(
                delivery.delivery_id, check_url, check_api_key,
            )
        else:
            # Physical/service: check if already verified (by human/webhook)
            verified = delivery.status == DeliveryStatus.VERIFIED

        if verified:
            settlement.status = "verified"
        return verified

    def confirm_delivery_human(self, settlement_id: str, approved: bool, notes: str = "") -> bool:
        """Human confirms physical delivery."""
        settlement = self._settlements.get(settlement_id)
        if not settlement or not settlement.delivery:
            return False

        result = self._delivery.verify_by_human(
            settlement.delivery.delivery_id, approved, notes,
        )
        if result:
            settlement.status = "verified"
        elif not approved:
            settlement.status = "disputed"
        return result

    def confirm_delivery_webhook(self, settlement_id: str, data: dict[str, Any]) -> bool:
        """External system confirms delivery."""
        settlement = self._settlements.get(settlement_id)
        if not settlement or not settlement.delivery:
            return False

        result = self._delivery.verify_by_webhook(settlement.delivery.delivery_id, data)
        if result:
            settlement.status = "verified"
        return result

    async def complete(self, settlement_id: str) -> bool:
        """Complete a verified settlement.

        For ESCROW mode, this releases funds from the on-chain escrow to the seller.
        For other modes, simply marks as completed.
        """
        settlement = self._settlements.get(settlement_id)
        if not settlement:
            return False

        if settlement.status != "verified":
            logger.warning("Cannot complete settlement %s: status=%s", settlement_id, settlement.status)
            return False

        # For escrow mode, release funds on-chain
        if settlement.mode == SettlementMode.ESCROW:
            release_payment = await self._payment.escrow_release(
                seller_address=settlement.seller_wallet,
                amount_usdc=settlement.amount_usdc,
                contract_id=settlement.contract_id,
            )
            if release_payment.status != PaymentStatus.RELEASED:
                logger.error(
                    "Settlement %s: escrow release failed: %s",
                    settlement_id, release_payment.error,
                )
                return False
            logger.info("Settlement %s: escrow released to seller", settlement_id)

        settlement.status = "completed"
        settlement.completed_at = datetime.now(timezone.utc)
        logger.info("Settlement %s completed", settlement_id)
        return True

    # ── Disputes ──────────────────────────────────────────────────────

    async def refund_expired(self, settlement_id: str) -> bool:
        """Refund an expired escrow (deadline passed, seller didn't deliver)."""
        settlement = self._settlements.get(settlement_id)
        if not settlement:
            return False

        if settlement.mode != SettlementMode.ESCROW:
            logger.warning("refund_expired only applies to ESCROW mode")
            return False

        if settlement.status not in ("escrowed", "delivering"):
            logger.warning("Cannot refund settlement %s: status=%s", settlement_id, settlement.status)
            return False

        refund_payment = await self._payment.escrow_refund(
            seller_address=settlement.seller_wallet,
            amount_usdc=settlement.amount_usdc,
            contract_id=settlement.contract_id,
        )

        if refund_payment.status == PaymentStatus.REFUNDED:
            settlement.status = "refunded"
            settlement.completed_at = datetime.now(timezone.utc)
            logger.info("Settlement %s: escrow refunded to buyer", settlement_id)
            return True

        logger.error("Settlement %s: escrow refund failed: %s", settlement_id, refund_payment.error)
        return False

    def file_dispute(
        self,
        settlement_id: str,
        filed_by: str,
        reason: str,
        evidence: list[dict[str, Any]] | None = None,
    ) -> Dispute | None:
        """File a dispute for a settlement."""
        settlement = self._settlements.get(settlement_id)
        if not settlement:
            return None

        dispute = Dispute(
            settlement_id=settlement_id,
            filed_by=filed_by,
            reason=reason,
            evidence=evidence or [],
        )
        settlement.dispute = dispute
        settlement.status = "disputed"
        self._disputes[dispute.dispute_id] = dispute

        logger.info("Dispute filed: %s (by %s) - %s", dispute.dispute_id, filed_by, reason)
        return dispute

    def resolve_dispute(
        self,
        dispute_id: str,
        resolution: DisputeStatus,
        notes: str = "",
    ) -> bool:
        """Resolve a dispute."""
        dispute = self._disputes.get(dispute_id)
        if not dispute:
            return False

        dispute.status = resolution
        dispute.resolution = notes
        dispute.resolved_at = datetime.now(timezone.utc)

        settlement = self._settlements.get(dispute.settlement_id)
        if settlement:
            if resolution == DisputeStatus.RESOLVED_SELLER:
                settlement.status = "completed"
            elif resolution == DisputeStatus.RESOLVED_BUYER:
                settlement.status = "refunded"
            else:
                settlement.status = "resolved"

        logger.info("Dispute %s resolved: %s", dispute_id, resolution.value)
        return True

    def add_dispute_evidence(
        self,
        dispute_id: str,
        evidence: dict[str, Any],
    ) -> bool:
        """Add evidence to an open dispute.

        Evidence is hashed (SHA-256) for integrity verification.
        Once appended, the hash proves the evidence was not modified.
        """
        dispute = self._disputes.get(dispute_id)
        if not dispute or dispute.status not in (DisputeStatus.OPEN, DisputeStatus.INVESTIGATING):
            return False

        import hashlib
        import json as _json

        evidence_canonical = _json.dumps(evidence, sort_keys=True, separators=(",", ":"))
        evidence_hash = hashlib.sha256(evidence_canonical.encode()).hexdigest()

        dispute.evidence.append({
            **evidence,
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "evidence_hash": evidence_hash,
        })
        return True

    def expire_stale_disputes(self, max_days: int = 30) -> list[str]:
        """Auto-expire disputes older than max_days without resolution.

        Expired disputes default to buyer refund (fail-safe).
        Returns list of expired dispute IDs.
        """
        expired: list[str] = []
        now = datetime.now(timezone.utc)

        for dispute_id, dispute in self._disputes.items():
            if dispute.status not in (DisputeStatus.OPEN, DisputeStatus.INVESTIGATING):
                continue
            if dispute.resolved_at:
                continue

            age_days = (now - dispute.filed_at).days if hasattr(dispute, "filed_at") else 0
            if age_days >= max_days:
                dispute.status = DisputeStatus.EXPIRED
                dispute.resolution = f"Auto-expired after {max_days} days — defaulting to buyer refund"
                dispute.resolved_at = now

                settlement = self._settlements.get(dispute.settlement_id)
                if settlement:
                    settlement.status = "refunded"

                expired.append(dispute_id)
                logger.info("Dispute %s auto-expired after %d days", dispute_id, max_days)

        return expired

    # ── Query ─────────────────────────────────────────────────────────

    def get_settlement(self, settlement_id: str) -> SettlementRecord | None:
        return self._settlements.get(settlement_id)

    def get_by_transaction(self, transaction_id: str) -> SettlementRecord | None:
        for s in self._settlements.values():
            if s.transaction_id == transaction_id:
                return s
        return None

    def list_active(self) -> list[SettlementRecord]:
        return [
            s for s in self._settlements.values()
            if s.status not in ("completed", "refunded", "resolved")
        ]

    def list_overdue(self) -> list[SettlementRecord]:
        return [
            s for s in self._settlements.values()
            if s.delivery and self._delivery.is_overdue(s.delivery.delivery_id)
        ]
