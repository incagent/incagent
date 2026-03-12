"""Tests for Gateway, Registry, Heartbeat, Memory, and Skills."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from incagent import (
    IncAgent,
    HeartbeatConfig,
    Memory,
    Registry,
    PeerAgent,
)
from incagent.heartbeat import Heartbeat, TradeOpportunity
from incagent.skills import Skill, SkillManager


# ── Memory Tests ─────────────────────────────────────────────────────

class TestMemory:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.memory = Memory(Path(self.tmp) / "test_memory.db")

    def teardown_method(self):
        self.memory.close()

    def test_record_trade(self):
        self.memory.record_trade_attempt(
            partner_id="p1", partner_name="TestCorp",
            contract_title="GPU Hours", success=True,
            final_price=50.0, quantity=100, rounds=3, duration_ms=150,
        )
        stats = self.memory.stats()
        assert stats["total_trades"] == 1
        assert stats["known_partners"] == 1

    def test_partner_profile_update(self):
        for i in range(5):
            self.memory.record_trade_attempt(
                partner_id="p1", partner_name="TestCorp",
                contract_title=f"Trade {i}", success=i < 4,  # 4/5 success
                final_price=50.0 + i, rounds=3,
            )
        history = self.memory.get_partner_history("p1")
        assert history is not None
        assert history["total_trades"] == 5
        assert history["successful_trades"] == 4
        assert history["success_rate"] == 0.8

    def test_learn_strategy(self):
        self.memory.learn_strategy("pricing", "gpu_market", "Start at $40", confidence=0.5)
        self.memory.learn_strategy("pricing", "gpu_market", "Start at $42", confidence=0.5)

        strategies = self.memory.get_strategies("pricing")
        assert len(strategies) == 1
        assert strategies[0]["confidence"] == 0.6  # Reinforced
        assert strategies[0]["times_validated"] == 1

    def test_export(self):
        self.memory.record_trade_attempt(
            partner_id="p1", partner_name="TestCorp",
            contract_title="Test", success=True,
        )
        export = self.memory.export()
        assert "stats" in export
        assert "partners" in export
        assert "strategies" in export


# ── Registry Tests ───────────────────────────────────────────────────

class TestRegistry:
    def test_register_and_find(self):
        reg = Registry()
        reg.register(PeerAgent(
            agent_id="a1", name="Buyer Inc", role="buyer",
            url="http://localhost:8401",
        ))
        reg.register(PeerAgent(
            agent_id="a2", name="Seller Corp", role="seller",
            url="http://localhost:8402",
        ))

        buyers = reg.find_by_role("buyer")
        sellers = reg.find_by_role("seller")
        assert len(buyers) == 1
        assert len(sellers) == 1
        assert buyers[0].name == "Buyer Inc"

    def test_find_trading_partners(self):
        reg = Registry()
        reg.register(PeerAgent(
            agent_id="s1", name="Seller A", role="seller",
            url="http://localhost:8402", industries=["tech"],
        ))
        reg.register(PeerAgent(
            agent_id="s2", name="Seller B", role="seller",
            url="http://localhost:8403", industries=["manufacturing"],
        ))

        partners = reg.find_trading_partners("buyer", industry="tech")
        assert len(partners) == 1
        assert partners[0].name == "Seller A"

    def test_unregister(self):
        reg = Registry()
        reg.register(PeerAgent(
            agent_id="a1", name="Test", role="buyer", url="http://localhost:8401",
        ))
        assert len(reg.list_peers()) == 1
        reg.unregister("a1")
        assert len(reg.list_peers()) == 0


# ── Skills Tests ─────────────────────────────────────────────────────

class TestSkills:
    def test_load_skills(self):
        skills_dir = Path(__file__).resolve().parent.parent / "skills"
        sm = SkillManager(skills_dir)
        skills = sm.list_skills()
        assert len(skills) >= 2  # cloud_compute.md and supply_chain.md

    def test_skill_parsing(self):
        skills_dir = Path(__file__).resolve().parent.parent / "skills"
        sm = SkillManager(skills_dir)
        cloud = sm.get("Cloud Compute Trading")
        assert cloud is not None
        assert len(cloud.products) > 0
        assert len(cloud.industries) > 0
        assert len(cloud.negotiation_hints) > 0

    def test_get_trade_params(self):
        skills_dir = Path(__file__).resolve().parent.parent / "skills"
        sm = SkillManager(skills_dir)
        params = sm.get_trade_params("Any Partner")
        assert params is not None
        assert "title" in params
        assert "terms" in params

    def test_add_skill_programmatically(self):
        sm = SkillManager()
        sm.add_skill(Skill(
            name="Custom Skill",
            description="Test",
            products=[{"name": "Widget", "price_min": 10, "price_max": 100}],
        ))
        assert sm.get("Custom Skill") is not None


# ── Heartbeat Tests ──────────────────────────────────────────────────

class TestHeartbeat:
    def test_heartbeat_config(self):
        config = HeartbeatConfig(interval_seconds=60)
        hb = Heartbeat(config)
        assert hb.tick_count == 0
        assert not hb._running

    def test_cooldown(self):
        import time
        hb = Heartbeat(HeartbeatConfig(trade_cooldown_seconds=1.0))
        hb._last_trade_with["peer1"] = time.monotonic()
        assert hb._is_on_cooldown("peer1") is True
        assert hb._is_on_cooldown("peer2") is False

    def test_queue_proposal(self):
        hb = Heartbeat()
        from incagent.contract import Contract, ContractTerms
        c = Contract(title="Test", terms=ContractTerms())
        hb.queue_proposal("http://localhost:8401", c)
        assert len(hb._pending_proposals) == 1


# ── Agent Integration Tests ──────────────────────────────────────────

class TestAgentIntegration:
    def test_agent_with_new_subsystems(self):
        agent = IncAgent(
            name="TestCo",
            role="buyer",
            autonomous_mode=True,
            data_dir=tempfile.mkdtemp(),
        )
        health = agent.health_status()
        assert "memory" in health
        assert "skills" in health
        assert "peers" in health
        agent.close()

    def test_agent_with_heartbeat(self):
        agent = IncAgent(
            name="TestCo",
            role="buyer",
            autonomous_mode=True,
            heartbeat=True,
            data_dir=tempfile.mkdtemp(),
        )
        assert agent._heartbeat is not None
        health = agent.health_status()
        assert health["heartbeat_ticks"] == 0
        agent.close()

    def test_agent_memory_records_trade(self):
        from incagent import Contract, ContractTerms, NegotiationPolicy
        from incagent.messaging import MessageBus

        tmp = tempfile.mkdtemp()
        bus = MessageBus()
        buyer = IncAgent(name="Buyer", role="buyer", autonomous_mode=True, message_bus=bus, data_dir=tmp)
        seller = IncAgent(name="Seller", role="seller", autonomous_mode=True, message_bus=bus, data_dir=tmp)

        contract = Contract(
            title="Test Trade",
            terms=ContractTerms(quantity=100, unit_price_range=(10.0, 50.0)),
        )
        policy = NegotiationPolicy(min_price=10, max_price=50, max_rounds=3)

        result = asyncio.get_event_loop().run_until_complete(
            buyer.negotiate(contract, counterparty=seller, policy=policy)
        )

        # Check memory recorded the trade
        stats = buyer._memory.stats()
        assert stats["total_trades"] >= 1

        buyer.close()
        seller.close()
