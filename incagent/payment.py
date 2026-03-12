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
import threading
import uuid
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
    rpc_urls: list[str] = Field(default_factory=list)
    private_key: str = ""  # Agent's wallet private key
    usdc_address: str = ""  # Override default USDC address
    escrow_address: str = ""  # Escrow smart contract address (optional)
    gas_limit: int = 100000
    confirmations: int = 1  # Blocks to wait for confirmation

    def get_usdc_address(self) -> str:
        return self.usdc_address or USDC_ADDRESSES.get(self.chain, "")

    def get_rpc_urls(self) -> list[str]:
        """Return all configured RPC URLs, with rpc_url first for backward compat."""
        urls: list[str] = []
        if self.rpc_url:
            urls.append(self.rpc_url)
        for u in self.rpc_urls:
            if u and u not in urls:
                urls.append(u)
        return urls


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
        self._nonce_lock = threading.Lock()
        self._current_nonce: int | None = None
        # Track submitted transactions for RBF: tx_hash -> signed tx params
        self._pending_txs: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # RPC failover
    # ------------------------------------------------------------------

    def _try_connect(self) -> Any:
        """Try RPC URLs in order until one connects. Returns Web3 instance or None."""
        try:
            from web3 import Web3
        except ImportError:
            logger.warning("web3 not installed. Run: pip install web3")
            return None

        urls = self._config.get_rpc_urls()
        if not urls:
            return None

        for url in urls:
            try:
                w3 = Web3(Web3.HTTPProvider(url))
                # Verify connectivity with a lightweight call
                w3.eth.block_number  # noqa: B018
                logger.debug("Connected to RPC: %s", url[:40])
                return w3
            except Exception as e:
                logger.warning("RPC failed (%s): %s", url[:40], e)
                continue

        logger.error("All RPC endpoints failed")
        return None

    def _get_web3(self) -> Any:
        """Initialize web3 connection (with failover)."""
        if self._web3 is not None:
            # Quick liveness check — if the current connection is dead, reconnect
            try:
                self._web3.eth.block_number  # noqa: B018
                return self._web3
            except Exception:
                logger.warning("Current RPC connection lost, reconnecting...")
                self._web3 = None
                self._account = None

        w3 = self._try_connect()
        if w3 is None:
            return None

        self._web3 = w3
        if self._config.private_key:
            self._account = w3.eth.account.from_key(self._config.private_key)
        return self._web3

    # ------------------------------------------------------------------
    # Nonce management (thread-safe)
    # ------------------------------------------------------------------

    def _get_next_nonce(self, w3: Any) -> int:
        """Get next nonce, thread-safe. Tracks locally to avoid collisions."""
        with self._nonce_lock:
            on_chain = w3.eth.get_transaction_count(self._account.address, "pending")
            if self._current_nonce is None or on_chain > self._current_nonce:
                self._current_nonce = on_chain
            nonce = self._current_nonce
            self._current_nonce += 1
            return nonce

    # ------------------------------------------------------------------
    # EIP-1559 gas
    # ------------------------------------------------------------------

    def get_gas_estimate(self) -> dict[str, Any]:
        """Return current EIP-1559 gas prices in wei.

        Returns dict with keys:
            max_fee_per_gas, max_priority_fee_per_gas, base_fee, gas_limit
        Returns empty dict on failure.
        """
        w3 = self._get_web3()
        if not w3:
            return {}

        try:
            latest = w3.eth.get_block("latest")
            base_fee: int = latest.get("baseFeePerGas", 0)
            # max_priority defaults to 1.5 gwei if the node supports it,
            # otherwise fall back to eth_maxPriorityFeePerGas.
            try:
                max_priority: int = w3.eth.max_priority_fee
            except Exception:
                max_priority = w3.to_wei(1.5, "gwei")

            # maxFeePerGas = 2 * baseFee + maxPriorityFee (safe headroom)
            max_fee = 2 * base_fee + max_priority

            return {
                "max_fee_per_gas": max_fee,
                "max_priority_fee_per_gas": max_priority,
                "base_fee": base_fee,
                "gas_limit": self._config.gas_limit,
            }
        except Exception as e:
            logger.error("Failed to estimate gas: %s", e)
            return {}

    def _build_eip1559_gas_params(self, w3: Any) -> dict[str, int]:
        """Build EIP-1559 gas fields for a transaction dict."""
        estimate = self.get_gas_estimate()
        if estimate:
            return {
                "maxFeePerGas": estimate["max_fee_per_gas"],
                "maxPriorityFeePerGas": estimate["max_priority_fee_per_gas"],
            }
        # Fallback: use legacy gasPrice if EIP-1559 data unavailable
        return {"gasPrice": w3.eth.gas_price}

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def wallet_address(self) -> str:
        """Get agent's wallet address."""
        if self._account:
            return self._account.address
        return ""

    # ------------------------------------------------------------------
    # Core methods
    # ------------------------------------------------------------------

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

            # --- Balance check before transfer ---
            balance_raw = contract.functions.balanceOf(self._account.address).call()
            if balance_raw < amount_raw:
                payment.status = PaymentStatus.FAILED
                balance_human = balance_raw / 1e6
                payment.error = (
                    f"Insufficient USDC balance: have {balance_human:.2f}, "
                    f"need {amount_usdc:.2f}"
                )
                logger.error("Insufficient balance: %s", payment.error)
                return payment

            # --- Thread-safe nonce ---
            nonce = self._get_next_nonce(w3)

            # --- EIP-1559 gas ---
            gas_params = self._build_eip1559_gas_params(w3)

            # Estimate gas dynamically, fall back to configured limit
            try:
                estimated_gas = contract.functions.transfer(
                    w3.to_checksum_address(to_address),
                    amount_raw,
                ).estimate_gas({"from": self._account.address})
                # Add 20% buffer
                gas_limit = int(estimated_gas * 1.2)
            except Exception:
                gas_limit = self._config.gas_limit

            tx_params: dict[str, Any] = {
                "from": self._account.address,
                "nonce": nonce,
                "gas": gas_limit,
                "chainId": w3.eth.chain_id,
                **gas_params,
            }

            tx = contract.functions.transfer(
                w3.to_checksum_address(to_address),
                amount_raw,
            ).build_transaction(tx_params)

            signed = self._account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            payment.tx_hash = tx_hash.hex()
            payment.status = PaymentStatus.SUBMITTED

            # Store for potential RBF bump later
            self._pending_txs[payment.tx_hash] = {
                "nonce": nonce,
                "to_address": to_address,
                "amount_raw": amount_raw,
                "gas": gas_limit,
                "gas_params": gas_params,
            }

            logger.info(
                "USDC transfer submitted: %s -> %s ($%.2f) tx=%s",
                payment.from_address[:10],
                to_address[:10],
                amount_usdc,
                payment.tx_hash[:16],
            )

            # Wait for confirmation
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt.status == 1:
                payment.status = PaymentStatus.CONFIRMED
                payment.block_number = receipt.blockNumber
                # Clean up pending tracker
                self._pending_txs.pop(payment.tx_hash, None)
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

    # ------------------------------------------------------------------
    # Replace-By-Fee (RBF)
    # ------------------------------------------------------------------

    async def bump_transaction(self, tx_hash: str) -> PaymentRecord | None:
        """Bump a stuck transaction by resubmitting with 10% higher gas fees.

        Returns a new PaymentRecord with the replacement tx hash, or None
        if the original transaction is not found / cannot be bumped.
        """
        w3 = self._get_web3()
        if not w3 or not self._account:
            logger.error("Cannot bump: Web3 not configured")
            return None

        # Look up original tx params from our local tracker first
        original = self._pending_txs.get(tx_hash)

        if original is None:
            # Try fetching from chain
            try:
                chain_tx = w3.eth.get_transaction(tx_hash)
            except Exception as e:
                logger.error("Cannot fetch original tx %s: %s", tx_hash[:16], e)
                return None

            # Reconstruct what we need
            original = {
                "nonce": chain_tx.nonce,
                "to_address": chain_tx.to,
                "gas": chain_tx.gas,
                "gas_params": {},
            }
            # Extract gas params from the chain tx
            if hasattr(chain_tx, "maxFeePerGas") and chain_tx.maxFeePerGas:
                original["gas_params"] = {
                    "maxFeePerGas": chain_tx.maxFeePerGas,
                    "maxPriorityFeePerGas": chain_tx.maxPriorityFeePerGas,
                }
            elif hasattr(chain_tx, "gasPrice") and chain_tx.gasPrice:
                original["gas_params"] = {"gasPrice": chain_tx.gasPrice}

        # Bump gas by 10%
        bumped_gas_params: dict[str, int] = {}
        old_params = original["gas_params"]
        if "maxFeePerGas" in old_params:
            bumped_gas_params["maxFeePerGas"] = int(old_params["maxFeePerGas"] * 1.1)
            bumped_gas_params["maxPriorityFeePerGas"] = int(
                old_params["maxPriorityFeePerGas"] * 1.1
            )
        elif "gasPrice" in old_params:
            bumped_gas_params["gasPrice"] = int(old_params["gasPrice"] * 1.1)
        else:
            # No prior gas info — use current estimate bumped 10%
            estimate = self.get_gas_estimate()
            if estimate:
                bumped_gas_params["maxFeePerGas"] = int(
                    estimate["max_fee_per_gas"] * 1.1
                )
                bumped_gas_params["maxPriorityFeePerGas"] = int(
                    estimate["max_priority_fee_per_gas"] * 1.1
                )
            else:
                bumped_gas_params["gasPrice"] = int(w3.eth.gas_price * 1.1)

        payment = PaymentRecord(
            payment_id=str(uuid.uuid4()),
            transaction_id=f"rbf:{tx_hash[:16]}",
            from_address=self.wallet_address,
            to_address=original.get("to_address", ""),
            amount_usdc=0,  # Same transfer, just gas bump
            chain=self._config.chain,
        )

        try:
            usdc_addr = self._config.get_usdc_address()
            contract = w3.eth.contract(
                address=w3.to_checksum_address(usdc_addr),
                abi=ERC20_TRANSFER_ABI,
            )

            # Rebuild the same transfer call with same nonce but higher gas
            to_addr = original.get("to_address", "")
            amount_raw = original.get("amount_raw", 0)

            tx_params: dict[str, Any] = {
                "from": self._account.address,
                "nonce": original["nonce"],
                "gas": original["gas"],
                "chainId": w3.eth.chain_id,
                **bumped_gas_params,
            }

            if amount_raw and to_addr:
                tx = contract.functions.transfer(
                    w3.to_checksum_address(to_addr),
                    amount_raw,
                ).build_transaction(tx_params)
            else:
                # If we don't know the original call data, resend as raw
                # This path handles chain-fetched txs where we lack call info
                try:
                    chain_tx = w3.eth.get_transaction(tx_hash)
                    tx = {
                        "to": chain_tx.to,
                        "data": chain_tx.input,
                        "value": chain_tx.value,
                        "nonce": original["nonce"],
                        "gas": original["gas"],
                        "chainId": w3.eth.chain_id,
                        **bumped_gas_params,
                    }
                except Exception as e:
                    payment.status = PaymentStatus.FAILED
                    payment.error = f"Cannot reconstruct tx: {e}"
                    return payment

            signed = self._account.sign_transaction(tx)
            new_tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            payment.tx_hash = new_tx_hash.hex()
            payment.status = PaymentStatus.SUBMITTED

            # Update pending tracker: remove old, add new
            self._pending_txs.pop(tx_hash, None)
            self._pending_txs[payment.tx_hash] = {
                **original,
                "gas_params": bumped_gas_params,
            }

            logger.info(
                "RBF bump submitted: old=%s new=%s (gas +10%%)",
                tx_hash[:16],
                payment.tx_hash[:16],
            )

        except Exception as e:
            payment.status = PaymentStatus.FAILED
            payment.error = str(e)
            logger.error("RBF bump failed: %s", e)

        return payment
