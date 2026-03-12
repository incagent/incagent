"""Heartbeat — periodic self-activation for autonomous behavior.

OpenClaw-inspired: the agent wakes up on a configurable interval,
evaluates its environment, and takes action when needed.
"""

from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from incagent.agent import IncAgent
    from incagent.contract import Contract

logger = logging.getLogger("incagent.heartbeat")


class HeartbeatConfig(BaseModel):
    """Configuration for the Heartbeat scheduler."""

    interval_seconds: float = Field(default=1800.0, gt=0, description="Seconds between heartbeats (default 30min)")
    enabled: bool = True
    auto_discover: bool = Field(default=True, description="Auto-discover peers on each tick")
    auto_trade: bool = Field(default=True, description="Auto-initiate trades with discovered partners")
    max_concurrent_trades: int = Field(default=3, ge=1)
    trade_cooldown_seconds: float = Field(default=300.0, description="Min seconds between trades with same peer")
    jitter_seconds: float = Field(default=60.0, ge=0, description="Random jitter to avoid thundering herd")


class TradeOpportunity(BaseModel):
    """A potential trade discovered by the heartbeat."""

    peer_id: str
    peer_name: str
    peer_url: str
    reason: str
    priority: float = 0.5  # 0-1, higher = more urgent
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Heartbeat:
    """Periodic self-activation loop that drives autonomous agent behavior.

    Each tick:
    1. Health check — verify own systems
    2. Discover — find new trading partners
    3. Evaluate — check for trade opportunities
    4. Act — initiate trades if conditions are met
    5. Learn — update memory with results
    """

    def __init__(self, config: HeartbeatConfig | None = None) -> None:
        self._config = config or HeartbeatConfig()
        self._running = False
        self._tick_count = 0
        self._active_trades: int = 0
        self._last_trade_with: dict[str, float] = {}  # peer_id -> timestamp
        self._pending_proposals: list[tuple[str, Any]] = []  # (url, contract)
        self._task: asyncio.Task | None = None

    async def run(self, agent: IncAgent) -> None:
        """Start the heartbeat loop."""
        self._running = True
        logger.info(
            "Heartbeat started: interval=%ds, auto_trade=%s",
            self._config.interval_seconds, self._config.auto_trade,
        )

        while self._running:
            try:
                await self._tick(agent)
            except Exception as e:
                logger.error("Heartbeat tick failed: %s", e)

            # Sleep with jitter
            jitter = random.uniform(0, self._config.jitter_seconds)
            await asyncio.sleep(self._config.interval_seconds + jitter)

    async def _tick(self, agent: IncAgent) -> None:
        """Execute one heartbeat cycle."""
        self._tick_count += 1
        now = datetime.now(timezone.utc)
        logger.info("Heartbeat tick #%d at %s", self._tick_count, now.isoformat()[:19])

        # 1. Health check
        health = agent.health_status()
        if health.get("circuit_breaker") == "open":
            logger.warning("Circuit breaker open — skipping trade actions")
            return

        # 2. Process incoming messages
        messages = agent.receive_messages()
        for msg in messages:
            logger.info("Processing message: %s from %s", msg.message_type.value, msg.sender_id)

        # 3. Process queued proposals from remote agents
        await self._process_proposals(agent)

        # 4. Discover peers
        if self._config.auto_discover and hasattr(agent, '_registry'):
            await self._discover_peers(agent)

        # 5. Find and execute trade opportunities
        if self._config.auto_trade and hasattr(agent, '_registry'):
            opportunities = await self._find_opportunities(agent)
            for opp in opportunities:
                if self._active_trades >= self._config.max_concurrent_trades:
                    logger.info("Max concurrent trades reached (%d)", self._config.max_concurrent_trades)
                    break
                if self._is_on_cooldown(opp.peer_id):
                    continue
                asyncio.create_task(self._execute_trade(agent, opp))

        # 6. Update memory
        if hasattr(agent, '_memory'):
            agent._memory.record_heartbeat(self._tick_count, {
                "messages_processed": len(messages),
                "health": health,
            })

    async def _discover_peers(self, agent: IncAgent) -> None:
        """Discover new trading partners."""
        if hasattr(agent, '_registry'):
            # Try hub discovery
            await agent._registry.discover_from_hub()

            # Announce self to known peers
            from incagent.registry import PeerAgent
            my_info = PeerAgent(
                agent_id=agent.agent_id,
                name=agent.name,
                role=agent.identity.role,
                url=f"http://{agent._config.host}:{agent._config.port}",
                public_key_hex=agent.identity.public_key_hex,
            )
            await agent._registry.announce(my_info)

    async def _find_opportunities(self, agent: IncAgent) -> list[TradeOpportunity]:
        """Evaluate the environment for trade opportunities."""
        opportunities: list[TradeOpportunity] = []
        registry = agent._registry

        # Find complementary partners
        partners = registry.find_trading_partners(agent.identity.role)
        for partner in partners:
            # Use memory to evaluate partner quality
            priority = 0.5
            if hasattr(agent, '_memory'):
                history = agent._memory.get_partner_history(partner.agent_id)
                if history:
                    # Higher priority for partners with good track record
                    success_rate = history.get("success_rate", 0.5)
                    priority = min(1.0, success_rate * 0.8 + 0.2)

            opportunities.append(TradeOpportunity(
                peer_id=partner.agent_id,
                peer_name=partner.name,
                peer_url=partner.url,
                reason=f"Complementary role: {partner.role}",
                priority=priority,
            ))

        # Sort by priority (highest first)
        opportunities.sort(key=lambda x: x.priority, reverse=True)
        return opportunities

    async def _execute_trade(self, agent: IncAgent, opportunity: TradeOpportunity) -> None:
        """Execute a trade with a discovered partner."""
        import time
        self._active_trades += 1
        self._last_trade_with[opportunity.peer_id] = time.monotonic()

        try:
            logger.info(
                "Initiating trade with %s (%s)",
                opportunity.peer_name, opportunity.peer_url,
            )

            # Generate trade parameters using skills/memory
            trade_params = await self._generate_trade_params(agent, opportunity)

            from incagent.contract import Contract, ContractTerms

            contract = Contract(
                title=trade_params.get("title", f"Trade with {opportunity.peer_name}"),
                terms=ContractTerms(**trade_params.get("terms", {
                    "quantity": 100,
                    "unit_price": 50.0,
                    "currency": "USD",
                    "payment_terms": "net_30",
                })),
            )

            # Send proposal to remote agent
            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{opportunity.peer_url}/propose",
                    json={
                        "title": contract.title,
                        "terms": contract.terms.model_dump(),
                        "proposer_url": f"http://{agent._config.host}:{agent._config.port}",
                    },
                )
                resp.raise_for_status()
                result = resp.json()
                logger.info("Trade proposal sent: %s -> %s", result.get("status"), opportunity.peer_name)

            # Record in memory
            if hasattr(agent, '_memory'):
                agent._memory.record_trade_attempt(
                    partner_id=opportunity.peer_id,
                    partner_name=opportunity.peer_name,
                    contract_title=contract.title,
                    success=True,
                )

        except Exception as e:
            logger.error("Trade execution failed with %s: %s", opportunity.peer_name, e)
            if hasattr(agent, '_memory'):
                agent._memory.record_trade_attempt(
                    partner_id=opportunity.peer_id,
                    partner_name=opportunity.peer_name,
                    contract_title="failed",
                    success=False,
                    error=str(e),
                )
        finally:
            self._active_trades -= 1

    async def _generate_trade_params(self, agent: IncAgent, opportunity: TradeOpportunity) -> dict:
        """Use skills and memory to generate optimal trade parameters."""
        params: dict[str, Any] = {}

        # Check if skills define trade parameters
        if hasattr(agent, '_skills'):
            skill_params = agent._skills.get_trade_params(opportunity.peer_name)
            if skill_params:
                params.update(skill_params)

        # Use memory to optimize pricing
        if hasattr(agent, '_memory') and not params:
            learned = agent._memory.get_optimal_terms(opportunity.peer_id)
            if learned:
                params.update(learned)

        # Default fallback
        if not params:
            params = {
                "title": f"Supply Agreement — {agent.name} & {opportunity.peer_name}",
                "terms": {
                    "quantity": 100,
                    "unit_price": 50.0,
                    "currency": "USD",
                    "delivery_days": 30,
                    "payment_terms": "net_30",
                },
            }

        return params

    async def _process_proposals(self, agent: IncAgent) -> None:
        """Process trade proposals from remote agents."""
        while self._pending_proposals:
            proposer_url, contract = self._pending_proposals.pop(0)
            logger.info("Processing proposal from %s: %s", proposer_url, contract.title)
            # Auto-accept within policy bounds (autonomous mode)
            # In production, this would run full negotiation

    def queue_proposal(self, proposer_url: str, contract: Any) -> None:
        """Queue a trade proposal for processing on next tick."""
        self._pending_proposals.append((proposer_url, contract))

    def _is_on_cooldown(self, peer_id: str) -> bool:
        """Check if we recently traded with this peer."""
        import time
        last = self._last_trade_with.get(peer_id, 0)
        return (time.monotonic() - last) < self._config.trade_cooldown_seconds

    def stop(self) -> None:
        """Stop the heartbeat loop."""
        self._running = False
        logger.info("Heartbeat stopped after %d ticks", self._tick_count)

    @property
    def tick_count(self) -> int:
        return self._tick_count
