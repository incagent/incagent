"""EVM Payment Executor — USDC transfers on-chain.

Handles:
- Direct USDC transfers (simple trades)
- Escrow deposits (buyer locks funds)
- Escrow release (on delivery verification)
- Escrow refund (on dispute/timeout)

Works with any EVM chain: Ethereum, Base, Arbitrum, Polygon.
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("incagent.payment")

# Standard USDC contract addresses per chain
USDC_ADDRESSES = {
    "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "polygon": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
}

# ERC-20 transfer ABI (minimal)
ERC20_TRANSFER_ABI = [
    {
        "name": "transfer",
        "type": "function",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "approve",
        "type": "function",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    CONFIRMED = "confirmed"
    ESCROWED = "escrowed"
    RELEASED = "released"
    REFUNDED = "refunded"
    FAILED = "failed"


class PaymentConfig(BaseModel):
    """EVM payment configuration."""

    chain: str = "base"  # ethereum, base, arbitrum, polygon
    rpc_url: str = ""
    private_key: str = ""  # Agent's wallet private key
    usdc_address: str = ""  # Override default USDC address
    escrow_address: str = ""  # Escrow smart contract address (optional)
    gas_limit: int = 100000
    confirmations: int = 1  # Blocks to wait for confirmation

    def get_usdc_address(self) -> str:
        return self.usdc_address or USDC_ADDRESSES.get(self.chain, "")


class PaymentRecord(BaseModel):
    """Record of a payment."""

    payment_id: str
    transaction_id: str
    from_address: str
    to_address: str
    amount_usdc: float
    status: PaymentStatus = PaymentStatus.PENDING
    tx_hash: str = ""
    block_number: int = 0
    chain: str = "base"
    error: str = ""


class PaymentExecutor:
    """Executes USDC payments on EVM chains."""

    def __init__(self, config: PaymentConfig | None = None) -> None:
        self._config = config or PaymentConfig(
            rpc_url=os.environ.get("INCAGENT_RPC_URL", ""),
            private_key=os.environ.get("INCAGENT_PRIVATE_KEY", ""),
            chain=os.environ.get("INCAGENT_CHAIN", "base"),
        )
        self._web3: Any = None
        self._account: Any = None

    def _get_web3(self) -> Any:
        """Initialize web3 connection."""
        if self._web3 is not None:
            return self._web3

        if not self._config.rpc_url:
            return None

        try:
            from web3 import Web3
            self._web3 = Web3(Web3.HTTPProvider(self._config.rpc_url))
            if self._config.private_key:
                self._account = self._web3.eth.account.from_key(self._config.private_key)
            return self._web3
        except ImportError:
            logger.warning("web3 not installed. Run: pip install web3")
            return None

    @property
    def wallet_address(self) -> str:
        """Get agent's wallet address."""
        if self._account:
            return self._account.address
        return ""

    async def get_balance(self) -> float:
        """Get USDC balance of agent's wallet."""
        w3 = self._get_web3()
        if not w3 or not self._account:
            return 0.0

        usdc_addr = self._config.get_usdc_address()
        if not usdc_addr:
            return 0.0

        try:
            contract = w3.eth.contract(
                address=w3.to_checksum_address(usdc_addr),
                abi=ERC20_TRANSFER_ABI,
            )
            balance = contract.functions.balanceOf(self._account.address).call()
            return balance / 1e6  # USDC has 6 decimals
        except Exception as e:
            logger.error("Failed to get balance: %s", e)
            return 0.0

    async def transfer_usdc(
        self,
        to_address: str,
        amount_usdc: float,
        transaction_id: str = "",
    ) -> PaymentRecord:
        """Transfer USDC to another address."""
        import uuid
        payment = PaymentRecord(
            payment_id=str(uuid.uuid4()),
            transaction_id=transaction_id,
            from_address=self.wallet_address,
            to_address=to_address,
            amount_usdc=amount_usdc,
            chain=self._config.chain,
        )

        w3 = self._get_web3()
        if not w3 or not self._account:
            payment.status = PaymentStatus.FAILED
            payment.error = "Web3 not configured (set INCAGENT_RPC_URL and INCAGENT_PRIVATE_KEY)"
            return payment

        try:
            usdc_addr = self._config.get_usdc_address()
            contract = w3.eth.contract(
                address=w3.to_checksum_address(usdc_addr),
                abi=ERC20_TRANSFER_ABI,
            )

            amount_raw = int(amount_usdc * 1e6)  # USDC 6 decimals
            nonce = w3.eth.get_transaction_count(self._account.address)

            tx = contract.functions.transfer(
                w3.to_checksum_address(to_address),
                amount_raw,
            ).build_transaction({
                "from": self._account.address,
                "nonce": nonce,
                "gas": self._config.gas_limit,
                "gasPrice": w3.eth.gas_price,
            })

            signed = self._account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            payment.tx_hash = tx_hash.hex()
            payment.status = PaymentStatus.SUBMITTED

            logger.info("USDC transfer submitted: %s -> %s ($%.2f) tx=%s",
                        payment.from_address[:10], to_address[:10], amount_usdc, payment.tx_hash[:16])

            # Wait for confirmation
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status == 1:
                payment.status = PaymentStatus.CONFIRMED
                payment.block_number = receipt.blockNumber
                logger.info("Payment confirmed at block %d", payment.block_number)
            else:
                payment.status = PaymentStatus.FAILED
                payment.error = "Transaction reverted"

        except Exception as e:
            payment.status = PaymentStatus.FAILED
            payment.error = str(e)
            logger.error("Payment failed: %s", e)

        return payment

    async def verify_payment(self, tx_hash: str) -> dict[str, Any]:
        """Verify a payment transaction on-chain."""
        w3 = self._get_web3()
        if not w3:
            return {"verified": False, "error": "Web3 not configured"}

        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            return {
                "verified": receipt.status == 1,
                "block_number": receipt.blockNumber,
                "gas_used": receipt.gasUsed,
                "confirmations": w3.eth.block_number - receipt.blockNumber,
            }
        except Exception as e:
            return {"verified": False, "error": str(e)}
