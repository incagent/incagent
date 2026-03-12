"""Payment module tests — config, balance checks, RPC failover, nonce management."""

from __future__ import annotations

import pytest

from incagent.payment import (
    ERC20_TRANSFER_ABI,
    USDC_ADDRESSES,
    PaymentConfig,
    PaymentExecutor,
    PaymentRecord,
    PaymentStatus,
)


class TestPaymentConfig:
    def test_default_chain(self):
        config = PaymentConfig()
        assert config.chain == "base"

    def test_usdc_address_lookup(self):
        for chain in ("ethereum", "base", "arbitrum", "polygon"):
            config = PaymentConfig(chain=chain)
            addr = config.get_usdc_address()
            assert addr.startswith("0x")
            assert len(addr) == 42

    def test_custom_usdc_address(self):
        config = PaymentConfig(usdc_address="0x1234567890abcdef1234567890abcdef12345678")
        assert config.get_usdc_address() == "0x1234567890abcdef1234567890abcdef12345678"

    def test_rpc_urls_list(self):
        config = PaymentConfig(rpc_urls=["https://rpc1.example.com", "https://rpc2.example.com"])
        assert len(config.rpc_urls) == 2

    def test_backward_compat_single_rpc(self):
        config = PaymentConfig(rpc_url="https://single.example.com")
        assert config.rpc_url == "https://single.example.com"

    def test_gas_config(self):
        config = PaymentConfig(gas_limit=200000)
        assert config.gas_limit == 200000

    def test_get_rpc_urls(self):
        config = PaymentConfig(rpc_url="https://a.com", rpc_urls=["https://b.com", "https://c.com"])
        urls = config.get_rpc_urls()
        assert urls[0] == "https://a.com"
        assert len(urls) == 3

    def test_get_rpc_urls_dedup(self):
        config = PaymentConfig(rpc_url="https://a.com", rpc_urls=["https://a.com", "https://b.com"])
        urls = config.get_rpc_urls()
        assert len(urls) == 2


class TestPaymentExecutor:
    def test_no_web3_returns_none(self):
        executor = PaymentExecutor(PaymentConfig())
        # No RPC URL configured
        assert executor.wallet_address == ""

    async def test_transfer_fails_without_config(self):
        executor = PaymentExecutor(PaymentConfig())
        result = await executor.transfer_usdc("0x1234", 100.0, "tx_001")
        assert result.status == PaymentStatus.FAILED
        assert "not configured" in result.error.lower() or "Web3" in result.error

    async def test_balance_returns_zero_without_config(self):
        executor = PaymentExecutor(PaymentConfig())
        balance = await executor.get_balance()
        assert balance == 0.0

    async def test_verify_payment_without_config(self):
        executor = PaymentExecutor(PaymentConfig())
        result = await executor.verify_payment("0xfake")
        assert result["verified"] is False

    def test_gas_estimate_without_config(self):
        executor = PaymentExecutor(PaymentConfig())
        estimate = executor.get_gas_estimate()
        # Should return empty/default when no web3
        assert isinstance(estimate, dict)


class TestPaymentRecord:
    def test_record_fields(self):
        record = PaymentRecord(
            payment_id="pay_001",
            transaction_id="tx_001",
            from_address="0xaaaa",
            to_address="0xbbbb",
            amount_usdc=1000.0,
        )
        assert record.status == PaymentStatus.PENDING
        assert record.amount_usdc == 1000.0
        assert record.chain == "base"

    def test_failed_record(self):
        record = PaymentRecord(
            payment_id="pay_002",
            transaction_id="tx_002",
            from_address="0xaaaa",
            to_address="0xbbbb",
            amount_usdc=500.0,
            status=PaymentStatus.FAILED,
            error="Insufficient balance",
        )
        assert record.status == PaymentStatus.FAILED
        assert record.error == "Insufficient balance"


class TestUSDCAddresses:
    def test_known_chains(self):
        assert "ethereum" in USDC_ADDRESSES
        assert "base" in USDC_ADDRESSES
        assert "arbitrum" in USDC_ADDRESSES
        assert "polygon" in USDC_ADDRESSES

    def test_address_format(self):
        for chain, addr in USDC_ADDRESSES.items():
            assert addr.startswith("0x"), f"{chain} address doesn't start with 0x"
            assert len(addr) == 42, f"{chain} address wrong length"


class TestERC20ABI:
    def test_abi_functions(self):
        names = {entry["name"] for entry in ERC20_TRANSFER_ABI}
        assert "transfer" in names
        assert "approve" in names
        assert "balanceOf" in names
        assert "allowance" in names
