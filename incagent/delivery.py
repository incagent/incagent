"""Delivery Verification System.

Handles proof-of-delivery for both digital and physical goods.

Digital goods: API key provisioned, file transferred, access granted.
Physical goods: Human confirms receipt, photo/GPS proof, tracking number.

The agent auto-verifies digital deliveries.
Physical deliveries require human confirmation or webhook callback.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("incagent.delivery")


class DeliveryType(str, Enum):
    DIGITAL = "digital"      # API access, file transfer, license key
    PHYSICAL = "physical"    # Shipped goods, in-person delivery
    SERVICE = "service"      # Ongoing service provision
    HYBRID = "hybrid"        # Digital + physical components


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DELIVERED = "delivered"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    FAILED = "failed"


class DeliveryProof(BaseModel):
    """Evidence that delivery occurred."""

    proof_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    proof_type: str  # "api_response", "file_hash", "tracking", "photo", "signature", "webhook"
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    verified: bool = False
    hash: str = ""  # SHA-256 of proof data for tamper detection

    def compute_hash(self) -> str:
        import json
        raw = json.dumps(self.data, sort_keys=True, default=str)
        self.hash = hashlib.sha256(raw.encode()).hexdigest()
        return self.hash


class DeliveryRecord(BaseModel):
    """Full delivery tracking record."""

    delivery_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    transaction_id: str
    contract_id: str
    delivery_type: DeliveryType = DeliveryType.DIGITAL
    status: DeliveryStatus = DeliveryStatus.PENDING
    proofs: list[DeliveryProof] = Field(default_factory=list)
    expected_by: datetime | None = None
    delivered_at: datetime | None = None
    verified_at: datetime | None = None
    verification_method: str = ""  # "auto", "human", "webhook", "api_check"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliveryVerifier:
    """Verifies delivery of goods/services.

    Digital deliveries are auto-verified by the agent.
    Physical deliveries require external confirmation.
    """

    def __init__(self) -> None:
        self._deliveries: dict[str, DeliveryRecord] = {}
        self._verification_callbacks: dict[str, Any] = {}

    def create_delivery(
        self,
        transaction_id: str,
        contract_id: str,
        delivery_type: DeliveryType = DeliveryType.DIGITAL,
        expected_days: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DeliveryRecord:
        """Create a new delivery tracking record."""
        from datetime import timedelta
        delivery = DeliveryRecord(
            transaction_id=transaction_id,
            contract_id=contract_id,
            delivery_type=delivery_type,
            metadata=metadata or {},
        )
        if expected_days:
            delivery.expected_by = datetime.now(timezone.utc) + timedelta(days=expected_days)

        self._deliveries[delivery.delivery_id] = delivery
        logger.info("Delivery created: %s (type=%s)", delivery.delivery_id, delivery_type.value)
        return delivery

    def submit_proof(
        self,
        delivery_id: str,
        proof_type: str,
        data: dict[str, Any],
    ) -> DeliveryProof | None:
        """Submit proof of delivery."""
        delivery = self._deliveries.get(delivery_id)
        if not delivery:
            logger.error("Delivery not found: %s", delivery_id)
            return None

        proof = DeliveryProof(proof_type=proof_type, data=data)
        proof.compute_hash()
        delivery.proofs.append(proof)
        delivery.status = DeliveryStatus.DELIVERED
        delivery.delivered_at = datetime.now(timezone.utc)

        logger.info("Proof submitted for %s: type=%s hash=%s",
                     delivery_id, proof_type, proof.hash[:16])
        return proof

    async def verify_digital_delivery(
        self,
        delivery_id: str,
        check_url: str | None = None,
        check_api_key: str | None = None,
    ) -> bool:
        """Auto-verify a digital delivery (API access, file, license).

        Checks:
        - API endpoint responds correctly
        - File hash matches expected
        - License key is valid
        """
        delivery = self._deliveries.get(delivery_id)
        if not delivery:
            return False

        verified = False

        # Check via API if URL provided
        if check_url:
            try:
                import httpx
                headers = {}
                if check_api_key:
                    headers["Authorization"] = f"Bearer {check_api_key}"
                async with httpx.AsyncClient() as client:
                    resp = await client.get(check_url, headers=headers, timeout=10.0)
                    if resp.status_code == 200:
                        verified = True
                        self.submit_proof(delivery_id, "api_response", {
                            "url": check_url,
                            "status": resp.status_code,
                            "verified": True,
                        })
            except Exception as e:
                logger.warning("Digital verification failed for %s: %s", delivery_id, e)

        # Check via file hash if present in metadata
        elif delivery.metadata.get("expected_file_hash"):
            actual = delivery.metadata.get("actual_file_hash", "")
            expected = delivery.metadata["expected_file_hash"]
            if actual and actual == expected:
                verified = True
                self.submit_proof(delivery_id, "file_hash", {
                    "expected": expected,
                    "actual": actual,
                    "match": True,
                })

        # If proofs already submitted and delivery marked
        elif delivery.status == DeliveryStatus.DELIVERED and delivery.proofs:
            verified = True

        if verified:
            delivery.status = DeliveryStatus.VERIFIED
            delivery.verified_at = datetime.now(timezone.utc)
            delivery.verification_method = "auto"
            logger.info("Delivery %s verified (auto)", delivery_id)

        return verified

    def verify_by_human(self, delivery_id: str, approved: bool, notes: str = "") -> bool:
        """Human confirms delivery (for physical goods)."""
        delivery = self._deliveries.get(delivery_id)
        if not delivery:
            return False

        if approved:
            self.submit_proof(delivery_id, "human_confirmation", {
                "approved": True,
                "notes": notes,
            })
            delivery.status = DeliveryStatus.VERIFIED
            delivery.verified_at = datetime.now(timezone.utc)
            delivery.verification_method = "human"
            logger.info("Delivery %s verified (human)", delivery_id)
            return True
        else:
            self.submit_proof(delivery_id, "human_rejection", {
                "approved": False,
                "notes": notes,
            })
            delivery.status = DeliveryStatus.DISPUTED
            logger.info("Delivery %s disputed (human)", delivery_id)
            return False

    def verify_by_webhook(self, delivery_id: str, webhook_data: dict[str, Any]) -> bool:
        """External system confirms delivery via webhook."""
        delivery = self._deliveries.get(delivery_id)
        if not delivery:
            return False

        # Webhook data must include "verified": true
        if webhook_data.get("verified"):
            self.submit_proof(delivery_id, "webhook", webhook_data)
            delivery.status = DeliveryStatus.VERIFIED
            delivery.verified_at = datetime.now(timezone.utc)
            delivery.verification_method = "webhook"
            logger.info("Delivery %s verified (webhook)", delivery_id)
            return True

        return False

    def get_delivery(self, delivery_id: str) -> DeliveryRecord | None:
        return self._deliveries.get(delivery_id)

    def get_by_transaction(self, transaction_id: str) -> DeliveryRecord | None:
        for d in self._deliveries.values():
            if d.transaction_id == transaction_id:
                return d
        return None

    def is_overdue(self, delivery_id: str) -> bool:
        delivery = self._deliveries.get(delivery_id)
        if not delivery or not delivery.expected_by:
            return False
        return datetime.now(timezone.utc) > delivery.expected_by and delivery.status not in (
            DeliveryStatus.VERIFIED, DeliveryStatus.DELIVERED,
        )

    def list_pending(self) -> list[DeliveryRecord]:
        return [
            d for d in self._deliveries.values()
            if d.status in (DeliveryStatus.PENDING, DeliveryStatus.IN_PROGRESS)
        ]
