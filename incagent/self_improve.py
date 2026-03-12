"""Self-Improvement Engine - agents that evolve their own strategies.

The agent analyzes its trade history, identifies patterns, and uses LLM
to generate improved skills, negotiation strategies, and operational rules.

This is how the agent "learns to learn":
1. Analyze - Review trade history for patterns (wins, losses, pricing trends)
2. Diagnose - Identify what's working and what's not
3. Generate - Use LLM to write new/improved skill files or strategy updates
4. Apply - Save to skills directory and reload
5. Validate - Track if the change actually improves outcomes
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from incagent.config import LLMConfig
from incagent.memory import Memory
from incagent.skills import Skill, SkillManager
from incagent.tools import ToolRegistry

logger = logging.getLogger("incagent.self_improve")


class SelfImproveEngine:
    """Analyzes performance and generates improvements using LLM."""

    def __init__(
        self,
        memory: Memory,
        skills: SkillManager,
        llm_config: LLMConfig | None = None,
        skills_dir: Path | str | None = None,
        tools: ToolRegistry | None = None,
    ) -> None:
        self._memory = memory
        self._skills = skills
        self._llm_config = llm_config or LLMConfig()
        self._skills_dir = Path(skills_dir) if skills_dir else None
        self._tools = tools
        self._client: Any = None
        self._improvements_applied: int = 0

    def _get_client(self) -> Any:
        """Get or create LLM client."""
        if self._client is not None:
            return self._client
        if self._llm_config.provider == "anthropic":
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self._llm_config.api_key)
            except ImportError:
                return None
        else:
            try:
                import openai
                self._client = openai.OpenAI(api_key=self._llm_config.api_key)
            except ImportError:
                return None
        return self._client

    # ── Analysis ─────────────────────────────────────────────────────

    def analyze_performance(self) -> dict[str, Any]:
        """Analyze trade history and identify areas for improvement."""
        stats = self._memory.stats()
        partners = self._memory.get_all_partners()
        strategies = self._memory.get_strategies()

        analysis: dict[str, Any] = {
            "total_trades": stats["total_trades"],
            "known_partners": stats["known_partners"],
            "learned_strategies": stats["learned_strategies"],
            "issues": [],
            "opportunities": [],
        }

        if stats["total_trades"] == 0:
            analysis["issues"].append("No trades yet - need to find partners")
            return analysis

        # Identify problematic partners
        for p in partners:
            if p["total_trades"] >= 3 and p["success_rate"] < 0.5:
                analysis["issues"].append(
                    f"Low success rate ({p['success_rate']:.0%}) with {p['partner_name']} "
                    f"over {p['total_trades']} trades"
                )

        # Identify high-performing partners
        for p in partners:
            if p["total_trades"] >= 3 and p["success_rate"] >= 0.8:
                analysis["opportunities"].append(
                    f"Strong partner: {p['partner_name']} ({p['success_rate']:.0%} success, "
                    f"avg ${p['avg_price']:.2f})"
                )

        # Check strategy coverage
        existing_skills = self._skills.list_skills()
        if len(existing_skills) < 2:
            analysis["issues"].append(
                f"Only {len(existing_skills)} skills loaded - consider adding more trade types"
            )

        return analysis

    # ── Strategy Generation ──────────────────────────────────────────

    async def generate_improvement(self, analysis: dict[str, Any] | None = None) -> dict[str, Any]:
        """Use LLM to generate an improvement based on analysis."""
        if analysis is None:
            analysis = self.analyze_performance()

        client = self._get_client()

        # If no LLM available, use rule-based improvements
        if client is None:
            return self._rule_based_improvement(analysis)

        prompt = self._build_improvement_prompt(analysis)

        try:
            if self._llm_config.provider == "anthropic":
                response = client.messages.create(
                    model=self._llm_config.model,
                    max_tokens=2048,
                    temperature=0.3,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text
            else:
                response = client.chat.completions.create(
                    model=self._llm_config.model,
                    max_tokens=2048,
                    temperature=0.3,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.choices[0].message.content

            return self._parse_improvement(text)
        except Exception as e:
            logger.error("LLM improvement generation failed: %s", e)
            return self._rule_based_improvement(analysis)

    def _build_improvement_prompt(self, analysis: dict[str, Any]) -> str:
        """Build prompt for LLM to generate improvements."""
        partners = self._memory.get_all_partners()
        strategies = self._memory.get_strategies()
        existing_skills = self._skills.list_skills()

        return f"""You are a self-improving AI trade agent. Analyze your performance and generate improvements.

## Current Performance
- Total trades: {analysis['total_trades']}
- Known partners: {analysis['known_partners']}
- Learned strategies: {analysis['learned_strategies']}

## Issues
{json.dumps(analysis['issues'], indent=2) if analysis['issues'] else 'None'}

## Opportunities
{json.dumps(analysis['opportunities'], indent=2) if analysis['opportunities'] else 'None'}

## Partner History
{json.dumps(partners[:10], indent=2)}

## Current Strategies
{json.dumps(strategies[:10], indent=2)}

## Current Skills
{json.dumps(existing_skills, indent=2)}

## Available Tools
{json.dumps(self._tools.list_names() if self._tools else [], indent=2)}

Based on this data, generate ONE improvement. Respond with JSON:
{{
    "type": "skill" | "strategy" | "policy" | "tool",
    "name": "improvement name",
    "description": "what this improves and why",
    "content": "... the actual content ...",
    "expected_impact": "what should improve"
}}

For type "skill": content should be a valid Markdown skill file.
For type "strategy": content should be a strategy insight to save.
For type "policy": content should be updated negotiation parameters (JSON).
For type "tool": content should be Python code defining a BaseTool subclass with name, description, parameters, and execute() method. The tool extends the agent's capabilities (e.g., API integrations, notifications, file operations).

Be specific and data-driven. Base your improvement on the actual patterns in the data."""

    def _parse_improvement(self, text: str) -> dict[str, Any]:
        """Parse LLM improvement response."""
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
        return {"type": "none", "description": "Failed to parse improvement"}

    # ── Rule-based fallback ──────────────────────────────────────────

    def _rule_based_improvement(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Generate improvements without LLM."""
        partners = self._memory.get_all_partners()

        # Find the most successful price point
        best_partner = None
        for p in partners:
            if p["success_rate"] >= 0.7 and p.get("avg_price"):
                if best_partner is None or p["success_rate"] > best_partner["success_rate"]:
                    best_partner = p

        if best_partner:
            optimal_price = best_partner["avg_price"]
            return {
                "type": "strategy",
                "name": f"optimal_pricing_{best_partner['partner_name']}",
                "description": (
                    f"Based on {best_partner['total_trades']} trades with "
                    f"{best_partner['partner_name']} ({best_partner['success_rate']:.0%} success), "
                    f"optimal price point is ${optimal_price:.2f}"
                ),
                "content": json.dumps({
                    "strategy_type": "pricing",
                    "context": f"partner_{best_partner['partner_id']}",
                    "insight": f"Target price ${optimal_price:.2f} for {best_partner['partner_name']}",
                    "confidence": min(0.9, best_partner["success_rate"]),
                }),
                "expected_impact": "Better pricing accuracy with this partner",
            }

        # Default: suggest adding a skill
        if analysis.get("issues"):
            return {
                "type": "strategy",
                "name": "general_improvement",
                "description": f"Address: {analysis['issues'][0]}",
                "content": json.dumps({
                    "strategy_type": "general",
                    "context": "self_improvement",
                    "insight": analysis["issues"][0],
                    "confidence": 0.3,
                }),
                "expected_impact": "Awareness of current issues",
            }

        return {"type": "none", "description": "No improvements needed at this time"}

    # ── Apply Improvements ───────────────────────────────────────────

    async def apply_improvement(self, improvement: dict[str, Any]) -> bool:
        """Apply a generated improvement."""
        imp_type = improvement.get("type", "none")

        if imp_type == "none":
            return False

        if imp_type == "skill":
            return self._apply_skill(improvement)
        elif imp_type == "strategy":
            return self._apply_strategy(improvement)
        elif imp_type == "policy":
            return self._apply_policy(improvement)
        elif imp_type == "tool":
            return self._apply_tool(improvement)

        return False

    def _apply_skill(self, improvement: dict[str, Any]) -> bool:
        """Save a new skill file and reload."""
        if not self._skills_dir:
            logger.warning("No skills directory configured, cannot save skill")
            return False

        self._skills_dir.mkdir(parents=True, exist_ok=True)
        name = improvement.get("name", "auto_generated").replace(" ", "_").lower()
        path = self._skills_dir / f"{name}.md"

        content = improvement.get("content", "")
        if not content:
            return False

        path.write_text(content, encoding="utf-8")
        self._skills.reload()
        self._improvements_applied += 1

        logger.info("Applied skill improvement: %s -> %s", name, path)
        self._memory.learn_strategy(
            "self_improvement", f"skill_{name}",
            improvement.get("description", "Auto-generated skill"),
            confidence=0.4,
        )
        return True

    def _apply_strategy(self, improvement: dict[str, Any]) -> bool:
        """Save a strategy insight to memory."""
        content = improvement.get("content", "")
        if not content:
            return False

        try:
            data = json.loads(content) if isinstance(content, str) else content
            self._memory.learn_strategy(
                strategy_type=data.get("strategy_type", "general"),
                context=data.get("context", "auto"),
                insight=data.get("insight", improvement.get("description", "")),
                confidence=data.get("confidence", 0.5),
            )
            self._improvements_applied += 1
            logger.info("Applied strategy improvement: %s", improvement.get("name"))
            return True
        except Exception as e:
            logger.error("Failed to apply strategy: %s", e)
            return False

    def _apply_policy(self, improvement: dict[str, Any]) -> bool:
        """Record a policy update."""
        self._memory.learn_strategy(
            strategy_type="policy",
            context=improvement.get("name", "auto"),
            insight=improvement.get("content", ""),
            confidence=0.5,
        )
        self._improvements_applied += 1
        logger.info("Applied policy improvement: %s", improvement.get("name"))
        return True

    def _apply_tool(self, improvement: dict[str, Any]) -> bool:
        """Create a new tool from generated Python code."""
        if not self._tools:
            logger.warning("No tool registry configured, cannot create tool")
            return False

        name = improvement.get("name", "auto_tool")
        code = improvement.get("content", "")
        if not code:
            return False

        success = self._tools.create_tool(name, code)
        if success:
            self._improvements_applied += 1
            logger.info("Applied tool improvement: %s", name)
            self._memory.learn_strategy(
                "self_improvement", f"tool_{name}",
                improvement.get("description", "Auto-generated tool"),
                confidence=0.4,
            )
        return success

    # ── Full cycle ───────────────────────────────────────────────────

    async def improve(self) -> dict[str, Any]:
        """Run one full self-improvement cycle: analyze -> generate -> apply."""
        analysis = self.analyze_performance()
        improvement = await self.generate_improvement(analysis)

        if improvement.get("type") != "none":
            applied = await self.apply_improvement(improvement)
            improvement["applied"] = applied
        else:
            improvement["applied"] = False

        logger.info(
            "Self-improvement cycle complete: type=%s, applied=%s",
            improvement.get("type"), improvement.get("applied"),
        )
        return improvement

    @property
    def improvements_count(self) -> int:
        return self._improvements_applied
