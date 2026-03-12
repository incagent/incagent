"""Tests for Settlement, Payment, and Delivery systems."""

import tempfile
from pathlib import Path

import pytest

from incagent import IncAgent
from incagent.delivery import DeliveryProof, DeliveryStatus, DeliveryType, DeliveryVerifier
from incagent.payment import PaymentConfig, PaymentExecutor, PaymentStatus
from incagent.settlement import (
    Dispute,
    DisputeStatus,
    SettlementEngine,
    SettlementMode,
    SettlementRecord,
)


class TestDeliveryVerifier:
    def setup_method(self):
        self.verifier = DeliveryVerifier()

    def test_create_delivery(self):
        d = self.verifier.create_delivery(
            transaction_id="tx1",
            contract_id="c1",
            delivery_type=DeliveryType.DIGITAL,
        )
        assert d.delivery_id
        assert d.status == DeliveryStatus.PENDING
        assert d.delivery_type == DeliveryType.DIGITAL

    def test_create_physical_with_deadline(self):
        d = self.verifier.create_delivery(
            transaction_id="tx2",
            contract_id="c2",
            delivery_type=DeliveryType.PHYSICAL,
            expected_days=14,
        )
        assert d.expected_by is not None

    def test_submit_proof(self):
        d = self.verifier.create_delivery("tx3", "c3")
        proof = self.verifier.submit_proof(
            d.delivery_id,
            proof_type="api_response",
            data={"status": 200, "key": "valid"},
        )
        assert proof is not None
        assert proof.hash  # hash computed
        assert d.status == DeliveryStatus.DELIVERED

    def test_human_verification_approve(self):
        d = self.verifier.create_delivery("tx4", "c4", DeliveryType.PHYSICAL)
        result = self.verifier.verify_by_human(d.delivery_id, approved=True, notes="Received OK")
        assert result is True
        assert d.status == DeliveryStatus.VERIFIED
        assert d.verification_method == "human"

    def test_human_verification_reject(self):
        d = self.verifier.create_delivery("tx5", "c5", DeliveryType.PHYSICAL)
        result = self.verifier.verify_by_human(d.delivery_id, approved=False, notes="Damaged")
        assert result is False
        assert d.status == DeliveryStatus.DISPUTED

    def test_webhook_verification(self):
        d = self.verifier.create_delivery("tx6", "c6")
        result = self.verifier.verify_by_webhook(d.delivery_id, {"verified": True, "tracking": "ABC123"})
        assert result is True
        assert d.status == DeliveryStatus.VERIFIED
        assert d.verification_method == "webhook"

    async def test_digital_verification_with_proof(self):
        d = self.verifier.create_delivery("tx7", "c7")
        self.verifier.submit_proof(d.delivery_id, "file_hash", {"hash": "abc"})
        result = await self.verifier.verify_digital_delivery(d.delivery_id)
        assert result is True
        assert d.status == DeliveryStatus.VERIFIED

    def test_list_pending(self):
        self.verifier.create_delivery("tx8", "c8")
        self.verifier.create_delivery("tx9", "c9")
        d3 = self.verifier.create_delivery("tx10", "c10")
        self.verifier.verify_by_human(d3.delivery_id, approved=True)
        pending = self.verifier.list_pending()
        assert len(pending) == 2

    def test_get_by_transaction(self):
        self.verifier.create_delivery("tx_find", "c_find")
        found = self.verifier.get_by_transaction("tx_find")
        assert found is not None
        assert found.transaction_id == "tx_find"

    def test_proof_hash(self):
        proof = DeliveryProof(proof_type="test", data={"key": "value"})
        h = proof.compute_hash()
        assert len(h) == 64  # SHA-256 hex


class TestPaymentExecutor:
    def test_no_web3_returns_empty(self):
        executor = PaymentExecutor(PaymentConfig())
        assert executor.wallet_address == ""

    async def test_balance_no_config(self):
        executor = PaymentExecutor(PaymentConfig())
        balance = await executor.get_balance()
        assert balance == 0.0

    async def test_transfer_no_config(self):
        executor = PaymentExecutor(PaymentConfig())
        record = await executor.transfer_usdc("0x1234", 100.0, "tx1")
        assert record.status == PaymentStatus.FAILED
        assert "not configured" in record.error


class TestSettlementEngine:
    def setup_method(self):
        self.engine = SettlementEngine()

    def test_create_settlement(self):
        s = self.engine.create_settlement(
            transaction_id="tx1",
            contract_id="c1",
            buyer_id="buyer1",
            seller_id="seller1",
            amount_usdc=5000.0,
            mode=SettlementMode.DIRECT,
        )
        assert s.settlement_id
        assert s.amount_usdc == 5000.0
        assert s.delivery is not None
        assert s.status == "pending"

    def test_file_dispute(self):
        s = self.engine.create_settlement(
            "tx2", "c2", "buyer2", "seller2", 1000.0,
        )
        dispute = self.engine.file_dispute(
            s.settlement_id, "buyer2", "Never received goods",
            [{"type": "screenshot", "url": "https://..."}],
        )
        assert dispute is not None
        assert dispute.reason == "Never received goods"
        assert s.status == "disputed"

    def test_resolve_dispute_buyer_wins(self):
        s = self.engine.create_settlement(
            "tx3", "c3", "buyer3", "seller3", 2000.0,
        )
        dispute = self.engine.file_dispute(s.settlement_id, "buyer3", "Bad quality")
        self.engine.resolve_dispute(dispute.dispute_id, DisputeStatus.RESOLVED_BUYER, "Refund issued")
        assert dispute.status == DisputeStatus.RESOLVED_BUYER
        assert s.status == "refunded"

    def test_resolve_dispute_seller_wins(self):
        s = self.engine.create_settlement(
            "tx4", "c4", "buyer4", "seller4", 3000.0,
        )
        dispute = self.engine.file_dispute(s.settlement_id, "buyer4", "Late delivery")
        self.engine.resolve_dispute(dispute.dispute_id, DisputeStatus.RESOLVED_SELLER, "Delivered within SLA")
        assert dispute.status == DisputeStatus.RESOLVED_SELLER
        assert s.status == "completed"

    def test_add_dispute_evidence(self):
        s = self.engine.create_settlement(
            "tx5", "c5", "buyer5", "seller5", 500.0,
        )
        dispute = self.engine.file_dispute(s.settlement_id, "buyer5", "Wrong item")
        result = self.engine.add_dispute_evidence(dispute.dispute_id, {"photo": "img.jpg"})
        assert result is True
        assert len(dispute.evidence) == 1

    def test_list_active(self):
        self.engine.create_settlement("tx6", "c6", "b", "s", 100.0)
        self.engine.create_settlement("tx7", "c7", "b", "s", 200.0)
        active = self.engine.list_active()
        assert len(active) == 2

    def test_human_delivery_confirmation(self):
        s = self.engine.create_settlement(
            "tx8", "c8", "b", "s", 100.0,
            delivery_type=DeliveryType.PHYSICAL,
        )
        result = self.engine.confirm_delivery_human(s.settlement_id, True, "Got it")
        assert result is True
        assert s.status == "verified"

    async def test_complete_verified_settlement(self):
        s = self.engine.create_settlement(
            "tx9", "c9", "b", "s", 100.0,
        )
        self.engine.confirm_delivery_human(s.settlement_id, True)
        result = await self.engine.complete(s.settlement_id)
        assert result is True
        assert s.status == "completed"

    async def test_cannot_complete_unverified(self):
        s = self.engine.create_settlement(
            "tx10", "c10", "b", "s", 100.0,
        )
        result = await self.engine.complete(s.settlement_id)
        assert result is False


class TestAgentSettlement:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()

    async def test_agent_has_settlement(self):
        agent = IncAgent(
            name="SettleCo", role="buyer",
            autonomous_mode=True,
            data_dir=self.tmp,
        )
        assert hasattr(agent, '_settlement')
        health = agent.health_status()
        assert "tools" in health
        agent.close()

    async def test_agent_balance(self):
        agent = IncAgent(
            name="SettleCo", role="buyer",
            autonomous_mode=True,
            data_dir=self.tmp,
        )
        balance = await agent.get_balance()
        assert balance == 0.0  # No wallet configured
        agent.close()

    async def test_agent_file_dispute(self):
        agent = IncAgent(
            name="DisputeCo", role="buyer",
            autonomous_mode=True,
            data_dir=self.tmp,
        )
        # Create a settlement directly
        s = agent._settlement.create_settlement(
            "tx1", "c1", agent.agent_id, "seller1", 500.0,
        )
        dispute = agent.file_dispute(s.settlement_id, "Never delivered")
        assert dispute is not None
        assert dispute.reason == "Never delivered"
        agent.close()

    async def test_agent_confirm_delivery(self):
        agent = IncAgent(
            name="DeliveryCo", role="buyer",
            autonomous_mode=True,
            data_dir=self.tmp,
        )
        s = agent._settlement.create_settlement(
            "tx2", "c2", agent.agent_id, "seller2", 1000.0,
            delivery_type=DeliveryType.PHYSICAL,
        )
        result = agent.confirm_delivery(s.settlement_id, True, "Looks good")
        assert result is True
        agent.close()

    async def test_agent_with_payment_config(self):
        agent = IncAgent(
            name="PayCo", role="buyer",
            autonomous_mode=True,
            data_dir=self.tmp,
            payment={"chain": "base", "rpc_url": ""},
        )
        assert agent._settlement.payment_executor._config.chain == "base"
        agent.close()
