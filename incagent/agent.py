"""IncAgent - the autonomous corporate AI agent."""

from __future__ import annotations

import asyncio
import logging
from enum import Enum
from pathlib import Path
from typing import Any

from incagent.approval import ApprovalGateway, ApprovalStatus
from incagent.config import AgentConfig, ApprovalConfig, LLMConfig, ResilienceConfig
from incagent.contract import Contract
from incagent.heartbeat import Heartbeat, HeartbeatConfig
from incagent.identity import create_identity
from incagent.ledger import Ledger
from incagent.memory import Memory
from incagent.messaging import AgentMessage, MessageBus, MessageType
from incagent.negotiation import NegotiationEngine, NegotiationPolicy, NegotiationResult, NegotiationStatus
from incagent.registry import Registry
from incagent.resilience import ResilientExecutor
from incagent.delivery import DeliveryType
from incagent.payment import PaymentConfig
from incagent.self_improve import SelfImproveEngine
from incagent.settlement import SettlementEngine, SettlementMode
from incagent.skills import SkillManager
from incagent.tools import ToolRegistry, ToolResult
from incagent.transaction import TransactionManager

logger = logging.getLogger("incagent")


class AgentState(str, Enum):
    IDLE = "idle"
    NEGOTIATING = "negotiating"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    ERROR = "error"


class IncAgent:
    """An autonomous AI agent that transacts on behalf of a corporation.

    Usage (SDK mode):
        agent = IncAgent(name="Acme Corp", role="buyer")
        result = await agent.negotiate(contract, counterparty=other_agent)

    Usage (Gateway mode — persistent daemon):
        agent = IncAgent(name="Acme Corp", role="buyer", heartbeat=True)
        await agent.serve()  # starts Gateway + Heartbeat
    """

    def __init__(
        self,
        name: str,
        role: str = "buyer",
        *,
        approval_threshold: float = 10000.0,
        approval_method: str = "cli",
        autonomous_mode: bool = False,
        resilience: dict[str, Any] | ResilienceConfig | None = None,
        llm: dict[str, Any] | LLMConfig | None = None,
        data_dir: str | Path | None = None,
        message_bus: MessageBus | None = None,
        # New: OpenClaw-inspired options
        heartbeat: bool | dict[str, Any] | HeartbeatConfig | None = None,
        skills_dir: str | Path | None = None,
        hub_url: str | None = None,
        peers: list[str] | None = None,
        host: str = "0.0.0.0",
        port: int = 8400,
        industries: list[str] | None = None,
        capabilities: list[str] | None = None,
        # EVM payment
        payment: dict[str, Any] | PaymentConfig | None = None,
        wallet_address: str = "",
    ) -> None:
        # Identity
        self.identity, self._keypair = create_identity(name, role)

        # Config
        res_config = (
            ResilienceConfig(**resilience) if isinstance(resilience, dict)
            else resilience or ResilienceConfig()
        )
        llm_config = (
            LLMConfig(**llm) if isinstance(llm, dict)
            else llm or LLMConfig()
        )
        approval_config = ApprovalConfig(
            threshold=approval_threshold,
            method=approval_method,
            enabled=not autonomous_mode,
        )
        self._config = AgentConfig(
            name=name,
            role=role,
            host=host,
            port=port,
            resilience=res_config,
            approval=approval_config,
            llm=llm_config,
            autonomous_mode=autonomous_mode,
            data_dir=Path(data_dir) if data_dir else Path.home() / ".incagent",
        )

        # State
        self.state = AgentState.IDLE
        self._contracts: dict[str, Contract] = {}
        self._policies: dict[str, NegotiationPolicy] = {}

        # Core subsystems
        self._ledger = Ledger(self._config.data_dir / f"{self.identity.agent_id}.db")
        self._executor = ResilientExecutor(res_config)
        self._negotiation = NegotiationEngine(llm_config)
        self._approval = ApprovalGateway(approval_config)
        self._transactions = TransactionManager(self._ledger)
        self._bus = message_bus or MessageBus()
        self._bus.register(self.identity.agent_id)

        # New subsystems
        self._memory = Memory(self._config.data_dir / f"{self.identity.agent_id}_memory.db")
        self._registry = Registry(hub_url=hub_url)
        self._skills = SkillManager(
            skills_dir=skills_dir or self._config.data_dir / "skills"
        )

        # Tool system (external integrations + agent-extensible)
        self._tools = ToolRegistry(
            custom_tools_dir=self._config.data_dir / "tools",
        )

        # Settlement engine (EVM payment + delivery verification)
        pay_config = (
            PaymentConfig(**payment) if isinstance(payment, dict)
            else payment or PaymentConfig()
        )
        self._settlement = SettlementEngine(payment_config=pay_config)
        self._wallet_address = wallet_address

        # Self-improvement engine
        self._self_improve = SelfImproveEngine(
            memory=self._memory,
            skills=self._skills,
            llm_config=llm_config,
            skills_dir=skills_dir or self._config.data_dir / "skills",
            tools=self._tools,
        )

        # Store metadata
        self._industries = industries or []
        self._capabilities = capabilities or []

        # Heartbeat (autonomous mode)
        if heartbeat:
            hb_config = (
                HeartbeatConfig(**heartbeat) if isinstance(heartbeat, dict)
                else heartbeat if isinstance(heartbeat, HeartbeatConfig) else HeartbeatConfig()
            )
            self._heartbeat: Heartbeat | None = Heartbeat(hb_config)
        else:
            self._heartbeat = None

        # Auto-register initial peers
        if peers:
            asyncio.get_event_loop().create_task(self._connect_peers(peers))

        # Log creation
        self._ledger.append(self.identity.agent_id, "agent_created", self.identity.to_public_dict())
        logger.info("IncAgent '%s' created [%s]", name, self.identity.fingerprint())

    async def _connect_peers(self, peer_urls: list[str]) -> None:
        """Probe and register initial peer agents."""
        for url in peer_urls:
            await self._registry.probe_peer(url)

    @property
    def agent_id(self) -> str:
        return self.identity.agent_id

    @property
    def name(self) -> str:
        return self.identity.name

    # ── Gateway mode ─────────────────────────────────────────────────

    async def serve(self, *, host: str | None = None, port: int | None = None) -> None:
        """Start the agent as a persistent Gateway daemon.

        This is the OpenClaw-inspired "always-on" mode:
        - HTTP API for inter-agent communication
        - Heartbeat loop for autonomous behavior
        - Auto-discovery of peers
        - Learning from every interaction
        """
        from incagent.gateway import Gateway

        gw = Gateway(
            self,
            host=host or self._config.host,
            port=port or self._config.port,
        )
        try:
            await gw.start()
        except KeyboardInterrupt:
            await gw.stop()

    # ── SDK mode (existing API) ──────────────────────────────────────

    def set_policy(self, contract_id: str, policy: NegotiationPolicy) -> None:
        """Set negotiation policy for a specific contract."""
        self._policies[contract_id] = policy

    async def negotiate(
        self,
        contract: Contract,
        counterparty: IncAgent,
        policy: NegotiationPolicy | None = None,
    ) -> NegotiationResult:
        """Negotiate a contract with a counterparty agent."""
        self.state = AgentState.NEGOTIATING

        # Set up contract
        contract.propose(self.agent_id, counterparty.agent_id)
        self._contracts[contract.contract_id] = contract
        neg_policy = policy or self._policies.get(contract.contract_id, NegotiationPolicy())

        self._ledger.append(self.agent_id, "negotiation_started", {
            "contract_id": contract.contract_id,
            "counterparty": counterparty.agent_id,
        })

        # Notify counterparty
        self._bus.send(AgentMessage(
            sender_id=self.agent_id,
            recipient_id=counterparty.agent_id,
            message_type=MessageType.PROPOSAL,
            payload={"contract_id": contract.contract_id, "title": contract.title},
        ))

        # Run negotiation with resilience
        import time
        start = time.monotonic()

        async def _do_negotiate() -> NegotiationResult:
            return await self._negotiation.negotiate(contract, neg_policy)

        try:
            result = await self._executor.execute(_do_negotiate)
        except Exception as e:
            self.state = AgentState.ERROR
            self._ledger.append(self.agent_id, "negotiation_error", {"error": str(e)})
            logger.error("Negotiation failed: %s", e)
            return NegotiationResult(
                status=NegotiationStatus.REJECTED,
                reason=f"Error: {e}",
            )

        duration_ms = int((time.monotonic() - start) * 1000)

        self._ledger.append(self.agent_id, "negotiation_completed", {
            "contract_id": contract.contract_id,
            "status": result.status.value,
            "rounds": result.rounds,
        })

        # Record in memory
        self._memory.record_trade_attempt(
            partner_id=counterparty.agent_id,
            partner_name=counterparty.name,
            contract_title=contract.title,
            success=result.status == NegotiationStatus.AGREED,
            final_price=result.final_terms.unit_price if result.final_terms else None,
            quantity=result.final_terms.quantity if result.final_terms else None,
            rounds=result.rounds,
            duration_ms=duration_ms,
        )

        # Learn from result
        if result.status == NegotiationStatus.AGREED and result.final_terms:
            self._memory.learn_strategy(
                strategy_type="pricing",
                context=f"trade_with_{counterparty.name}",
                insight=f"Agreed at ${result.final_terms.unit_price} after {result.rounds} rounds",
                confidence=0.6,
            )

        if result.status == NegotiationStatus.AGREED and result.final_terms:
            contract.terms = result.final_terms
            contract.agree()

            # Check if human approval is needed
            amount = result.final_terms.estimated_value()
            if self._approval.needs_approval(amount):
                self.state = AgentState.AWAITING_APPROVAL
                approval = await self._approval.request_approval(contract)
                if approval.status != ApprovalStatus.APPROVED and approval.status != ApprovalStatus.SKIPPED:
                    contract.cancel("Human rejected")
                    self.state = AgentState.IDLE
                    return NegotiationResult(
                        status=NegotiationStatus.REJECTED,
                        rounds=result.rounds,
                        reason=f"Human approval: {approval.status.value}",
                    )

            # Sign the contract
            sig = self._keypair.sign_json(contract.terms.model_dump())
            contract.sign(self.agent_id, sig)

            # Execute transaction
            await self._execute_transaction(contract, counterparty)

        self.state = AgentState.IDLE
        return result

    async def _execute_transaction(self, contract: Contract, counterparty: IncAgent) -> None:
        """Execute the agreed transaction with real settlement.

        Flow:
        1. Create transaction record
        2. Create settlement (payment + delivery tracking)
        3. Execute USDC payment (if configured, otherwise simulate)
        4. Track delivery
        5. Complete on verification
        """
        self.state = AgentState.EXECUTING
        amount = contract.terms.estimated_value()
        is_buyer = self._config.role == "buyer"

        txn = self._transactions.create(
            contract_id=contract.contract_id,
            buyer_id=self.agent_id if is_buyer else counterparty.agent_id,
            seller_id=counterparty.agent_id if is_buyer else self.agent_id,
            amount=amount,
        )

        try:
            self._transactions.execute(txn.transaction_id)
            contract.execute()

            # Determine delivery type from contract terms
            delivery_type = DeliveryType.DIGITAL
            if contract.terms.delivery_days and contract.terms.delivery_days > 0:
                delivery_type = DeliveryType.PHYSICAL

            # Determine settlement mode
            mode = SettlementMode.DIRECT
            if contract.terms.payment_terms == "prepaid":
                mode = SettlementMode.PREPAID
            elif contract.terms.payment_terms == "escrow":
                mode = SettlementMode.ESCROW

            # Get counterparty wallet address
            seller_wallet = ""
            if hasattr(counterparty, '_wallet_address'):
                seller_wallet = counterparty._wallet_address

            # Create settlement
            settlement = self._settlement.create_settlement(
                transaction_id=txn.transaction_id,
                contract_id=contract.contract_id,
                buyer_id=txn.buyer_id,
                seller_id=txn.seller_id,
                amount_usdc=amount,
                seller_wallet=seller_wallet,
                mode=mode,
                delivery_type=delivery_type,
                delivery_days=contract.terms.delivery_days,
            )

            # Execute payment (USDC if configured, otherwise record only)
            if is_buyer and self._settlement.payment_executor.wallet_address:
                payment = await self._settlement.execute_payment(settlement.settlement_id)
                if payment and payment.status.value == "failed":
                    raise RuntimeError(f"Payment failed: {payment.error}")
                self._ledger.append(self.agent_id, "payment_executed", {
                    "settlement_id": settlement.settlement_id,
                    "tx_hash": payment.tx_hash if payment else "",
                    "amount_usdc": amount,
                })
            else:
                # No wallet configured - mark as paid (simulated/off-chain)
                settlement.status = "paid"
                self._ledger.append(self.agent_id, "payment_simulated", {
                    "settlement_id": settlement.settlement_id,
                    "amount": amount,
                    "note": "No EVM wallet configured - payment recorded off-chain",
                })

            # For digital goods, auto-verify delivery
            if delivery_type == DeliveryType.DIGITAL:
                await self._settlement.verify_delivery(settlement.settlement_id)
                await self._settlement.complete(settlement.settlement_id)

            self._transactions.complete(txn.transaction_id)
            contract.complete()

            self._bus.send(AgentMessage(
                sender_id=self.agent_id,
                recipient_id=counterparty.agent_id,
                message_type=MessageType.ACCEPT,
                payload={
                    "contract_id": contract.contract_id,
                    "transaction_id": txn.transaction_id,
                    "settlement_id": settlement.settlement_id,
                },
            ))
            logger.info(
                "Transaction completed: %s ($%.2f) settlement=%s",
                txn.transaction_id, amount, settlement.settlement_id,
            )

        except Exception as e:
            self._transactions.fail(txn.transaction_id, str(e))
            contract.dispute(str(e))
            logger.error("Transaction failed: %s", e)

    def receive_messages(self) -> list[AgentMessage]:
        """Process incoming messages."""
        return self._bus.receive(self.agent_id)

    def get_ledger_entries(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get recent ledger entries for this agent."""
        return self._ledger.query(agent_id=self.agent_id, limit=limit)

    def verify_ledger(self) -> bool:
        """Verify the integrity of this agent's ledger."""
        return self._ledger.verify_chain()

    # ── Tool system ────────────────────────────────────────────────

    async def use_tool(self, tool_name: str, **kwargs: Any) -> ToolResult:
        """Execute a tool by name. The agent can call any registered tool
        to interact with external systems (Slack, email, APIs, filesystem, shell)."""
        result = await self._tools.execute(tool_name, **kwargs)
        self._ledger.append(self.agent_id, "tool_used", {
            "tool": tool_name,
            "success": result.success,
            "error": result.error,
        })
        return result

    def create_tool(self, name: str, code: str) -> bool:
        """Create a new tool at runtime. The agent writes a Python file
        that defines a BaseTool subclass, then hot-loads it.
        This is how the agent extends its own capabilities."""
        success = self._tools.create_tool(name, code)
        if success:
            self._ledger.append(self.agent_id, "tool_created", {"tool": name})
            logger.info("Agent created new tool: %s", name)
        return success

    def list_tools(self) -> list[dict[str, Any]]:
        """List all available tools."""
        return self._tools.list_tools()

    # ── Settlement ──────────────────────────────────────────────────

    async def get_balance(self) -> float:
        """Get agent's USDC balance."""
        return await self._settlement.payment_executor.get_balance()

    def confirm_delivery(self, settlement_id: str, approved: bool = True, notes: str = "") -> bool:
        """Human confirms physical delivery for a settlement."""
        return self._settlement.confirm_delivery_human(settlement_id, approved, notes)

    def file_dispute(self, settlement_id: str, reason: str, evidence: list[dict[str, Any]] | None = None) -> Any:
        """File a dispute for a settlement."""
        return self._settlement.file_dispute(settlement_id, self.agent_id, reason, evidence)

    def list_active_settlements(self) -> list[Any]:
        """List settlements awaiting completion."""
        return self._settlement.list_active()

    async def improve(self) -> dict[str, Any]:
        """Run one self-improvement cycle. The agent analyzes its performance
        and generates strategy/skill/tool improvements using LLM (or rules)."""
        return await self._self_improve.improve()

    def health_status(self) -> dict[str, Any]:
        """Get agent health status."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "state": self.state.value,
            "role": self.identity.role,
            "circuit_breaker": self._executor.circuit.state.value,
            "ledger_valid": self.verify_ledger(),
            "pending_messages": self._bus.peek(self.agent_id),
            "memory": self._memory.stats(),
            "skills": len(self._skills.list_skills()),
            "peers": len(self._registry.list_peers()),
            "heartbeat_ticks": self._heartbeat.tick_count if self._heartbeat else 0,
            "improvements_applied": self._self_improve.improvements_count,
            "tools": self._tools.count,
        }

    def close(self) -> None:
        """Clean up resources."""
        if self._heartbeat:
            self._heartbeat.stop()
        self._memory.close()
        self._ledger.close()
