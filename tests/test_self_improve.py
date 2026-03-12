"""Tests for the Self-Improvement Engine."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from incagent import IncAgent
from incagent.memory import Memory
from incagent.self_improve import SelfImproveEngine
from incagent.skills import SkillManager


class TestSelfImproveEngine:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.memory = Memory(Path(self.tmp) / "test_memory.db")
        self.skills_dir = Path(self.tmp) / "skills"
        self.skills_dir.mkdir()
        self.skills = SkillManager(self.skills_dir)
        self.engine = SelfImproveEngine(
            memory=self.memory,
            skills=self.skills,
            skills_dir=self.skills_dir,
        )

    def teardown_method(self):
        self.memory.close()

    def test_analyze_empty(self):
        """Analysis with no trades identifies the issue."""
        analysis = self.engine.analyze_performance()
        assert analysis["total_trades"] == 0
        assert len(analysis["issues"]) > 0
        assert "No trades" in analysis["issues"][0]

    def test_analyze_with_trades(self):
        """Analysis with trade history identifies patterns."""
        # Record some trades with a problematic partner
        for i in range(5):
            self.memory.record_trade_attempt(
                partner_id="bad_partner", partner_name="BadCorp",
                contract_title=f"Trade {i}",
                success=i < 1,  # Only 1/5 success = 20%
            )

        # Record trades with a good partner
        for i in range(5):
            self.memory.record_trade_attempt(
                partner_id="good_partner", partner_name="GoodCorp",
                contract_title=f"Trade {i}",
                success=True,
                final_price=50.0 + i,
            )

        analysis = self.engine.analyze_performance()
        assert analysis["total_trades"] == 10

        # Should flag low success rate partner
        issue_texts = " ".join(analysis["issues"])
        assert "BadCorp" in issue_texts or "Low success" in issue_texts

        # Should flag high-performing partner
        opp_texts = " ".join(analysis["opportunities"])
        assert "GoodCorp" in opp_texts

    async def test_rule_based_improvement(self):
        """Without LLM, generates rule-based improvements."""
        # Add some successful trades
        for i in range(5):
            self.memory.record_trade_attempt(
                partner_id="partner1", partner_name="TestCorp",
                contract_title=f"Trade {i}",
                success=True,
                final_price=45.0,
            )

        improvement = await self.engine.generate_improvement()
        assert improvement["type"] in ("strategy", "none")

        if improvement["type"] == "strategy":
            assert "TestCorp" in improvement.get("description", "")

    async def test_apply_strategy(self):
        """Apply a strategy improvement to memory."""
        improvement = {
            "type": "strategy",
            "name": "test_strategy",
            "description": "Test improvement",
            "content": '{"strategy_type": "pricing", "context": "test", "insight": "Price at $50", "confidence": 0.7}',
        }

        applied = await self.engine.apply_improvement(improvement)
        assert applied is True
        assert self.engine.improvements_count == 1

        # Verify in memory
        strategies = self.memory.get_strategies("pricing")
        assert len(strategies) == 1
        assert strategies[0]["insight"] == "Price at $50"

    async def test_apply_skill(self):
        """Apply a skill improvement by writing a file."""
        skill_content = """# Auto-Generated Skill

## Products
- Widget | $10-$50 | 100-1000

## Negotiation Hints
- Start low
"""
        improvement = {
            "type": "skill",
            "name": "auto_widget_trading",
            "description": "Auto-generated widget trading skill",
            "content": skill_content,
        }

        applied = await self.engine.apply_improvement(improvement)
        assert applied is True

        # Verify file exists
        assert (self.skills_dir / "auto_widget_trading.md").exists()

        # Verify skill loaded
        skills = self.skills.list_skills()
        assert len(skills) >= 1

    async def test_full_improve_cycle(self):
        """Full cycle: analyze -> generate -> apply."""
        # Seed some data
        for i in range(5):
            self.memory.record_trade_attempt(
                partner_id="p1", partner_name="Corp A",
                contract_title=f"Trade {i}",
                success=True,
                final_price=30.0 + i,
            )

        result = await self.engine.improve()
        assert "type" in result
        assert "applied" in result


class TestAgentSelfImprove:
    async def test_agent_has_self_improve(self):
        """Agent has self-improvement engine."""
        agent = IncAgent(
            name="TestCo", role="buyer",
            autonomous_mode=True,
            data_dir=tempfile.mkdtemp(),
        )
        assert hasattr(agent, '_self_improve')
        health = agent.health_status()
        assert "improvements_applied" in health
        agent.close()

    async def test_agent_improve(self):
        """Agent can run self-improvement."""
        tmp = tempfile.mkdtemp()
        agent = IncAgent(
            name="TestCo", role="buyer",
            autonomous_mode=True,
            data_dir=tmp,
        )

        # Seed trade data
        for i in range(5):
            agent._memory.record_trade_attempt(
                partner_id="p1", partner_name="Partner",
                contract_title=f"Trade {i}",
                success=True,
                final_price=50.0,
            )

        result = await agent.improve()
        assert "type" in result
        agent.close()
