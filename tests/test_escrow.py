"""Escrow module tests — on-chain escrow integration, escrow ID generation, settlement escrow flow."""

from __future__ import annotations

import pytest

from incagent.payment import (
    ESCROW_ABI,
    PaymentConfig,
    PaymentExecutor,
    PaymentStatus,
)
from incagent.settlement import SettlementEngine, SettlementMode


class TestEscrowABI:
    def test_abi_functions(self):
        names = {entry["name"] for entry in ESCROW_ABI}
        assert "deposit" in names
        assert "release" in names
        assert "refund" in names
        assert "dispute" in names
        assert "resolveDispute" in names
        assert "getEscrow" in names
        assert "isExpired" in names

    def test_deposit_inputs(self):
        deposit = next(e for e in ESCROW_ABI if e["name"] == "deposit")
        input_names = [i["name"] for i in deposit["inputs"]]
        assert "escrowId" in input_names
        assert "seller" in input_names
        assert "amount" in input_names
        assert "lockSeconds" in input_names
        assert "contractHash" in input_names


class TestEscrowIdGeneration:
    def test_deterministic(self):
        id1 = PaymentExecutor.compute_escrow_id("0xAAA", "0xBBB", "c_001", 1000.0)
        id2 = PaymentExecutor.compute_escrow_id("0xAAA", "0xBBB", "c_001", 1000.0)
        assert id1 == id2
        assert len(id1) == 32  # SHA-256 = 32 bytes

    def test_different_params_different_id(self):
        id1 = PaymentExecutor.compute_escrow_id("0xAAA", "0xBBB", "c_001", 1000.0)
        id2 = PaymentExecutor.compute_escrow_id("0xAAA", "0xBBB", "c_002", 1000.0)
        assert id1 != id2

    def test_contract_hash(self):
        h1 = PaymentExecutor.compute_contract_hash('{"price": 100}')
        h2 = PaymentExecutor.compute_contract_hash('{"price": 100}')
        h3 = PaymentExecutor.compute_contract_hash('{"price": 200}')
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 32


class TestEscrowDeposit:
    @pytest.mark.asyncio
    async def test_deposit_fails_without_web3(self):
        executor = PaymentExecutor(PaymentConfig())
        result = await executor.escrow_deposit(
            seller_address="0x1234",
            amount_usdc=500.0,
            lock_seconds=86400,
            contract_id="c_001",
        )
        assert result.status == PaymentStatus.FAILED
        assert "not configured" in result.error.lower() or "Web3" in result.error

    @pytest.mark.asyncio
    async def test_deposit_fails_without_escrow_address(self):
        executor = PaymentExecutor(PaymentConfig(
            rpc_url="https://fake.rpc.example.com",
            private_key="0x" + "ab" * 32,
        ))
        result = await executor.escrow_deposit(
            seller_address="0x1234",
            amount_usdc=500.0,
            lock_seconds=86400,
        )
        # Should fail because either no web3 connection or no escrow address
        assert result.status == PaymentStatus.FAILED


class TestEscrowRelease:
    @pytest.mark.asyncio
    async def test_release_fails_without_web3(self):
        executor = PaymentExecutor(PaymentConfig())
        result = await executor.escrow_release(
            seller_address="0x1234",
            amount_usdc=500.0,
            contract_id="c_001",
        )
        assert result.status == PaymentStatus.FAILED

    @pytest.mark.asyncio
    async def test_release_fails_without_escrow_contract(self):
        executor = PaymentExecutor(PaymentConfig(escrow_address=""))
        result = await executor.escrow_release("0x1234", 500.0, "c_001")
        assert result.status == PaymentStatus.FAILED


class TestEscrowRefund:
    @pytest.mark.asyncio
    async def test_refund_fails_without_web3(self):
        executor = PaymentExecutor(PaymentConfig())
        result = await executor.escrow_refund("0x1234", 500.0, "c_001")
        assert result.status == PaymentStatus.FAILED


class TestEscrowDispute:
    @pytest.mark.asyncio
    async def test_dispute_fails_without_web3(self):
        executor = PaymentExecutor(PaymentConfig())
        result = await executor.escrow_dispute("0x1234", 500.0, "c_001")
        assert result is False


class TestEscrowStatus:
    @pytest.mark.asyncio
    async def test_status_fails_without_web3(self):
        executor = PaymentExecutor(PaymentConfig())
        result = await executor.escrow_status("0x1234", 500.0, "c_001")
        assert "error" in result


class TestSettlementEscrowMode:
    def test_create_escrow_settlement(self):
        engine = SettlementEngine()
        settlement = engine.create_settlement(
            transaction_id="tx_001",
            contract_id="c_001",
            buyer_id="buyer_1",
            seller_id="seller_1",
            amount_usdc=1000.0,
            seller_wallet="0xSeller",
            mode=SettlementMode.ESCROW,
        )
        assert settlement.mode == SettlementMode.ESCROW
        assert settlement.status == "pending"

    def test_create_direct_settlement(self):
        engine = SettlementEngine()
        settlement = engine.create_settlement(
            transaction_id="tx_002",
            contract_id="c_002",
            buyer_id="buyer_1",
            seller_id="seller_1",
            amount_usdc=500.0,
            seller_wallet="0xSeller",
            mode=SettlementMode.DIRECT,
        )
        assert settlement.mode == SettlementMode.DIRECT

    @pytest.mark.asyncio
    async def test_refund_expired_non_escrow(self):
        engine = SettlementEngine()
        settlement = engine.create_settlement(
            transaction_id="tx_003",
            contract_id="c_003",
            buyer_id="buyer_1",
            seller_id="seller_1",
            amount_usdc=500.0,
            mode=SettlementMode.DIRECT,
        )
        result = await engine.refund_expired(settlement.settlement_id)
        assert result is False  # Can't refund non-escrow
