"""Skills — Markdown-defined plugin system (OpenClaw-inspired).

Skills are loaded from Markdown files in the skills directory.
Each skill defines:
- Name and description
- Trade parameters (product, price ranges, quantities)
- Negotiation strategy hints
- Custom actions
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("incagent.skills")


class Skill(BaseModel):
    """A loaded skill definition."""

    name: str
    description: str = ""
    version: str = "1.0"
    industries: list[str] = Field(default_factory=list)
    products: list[dict[str, Any]] = Field(default_factory=list)
    negotiation_hints: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    raw_content: str = ""
    source_path: str = ""


class SkillManager:
    """Loads and manages skills from Markdown files."""

    def __init__(self, skills_dir: Path | str | None = None) -> None:
        self._skills_dir = Path(skills_dir) if skills_dir else None
        self._skills: dict[str, Skill] = {}
        if self._skills_dir and self._skills_dir.exists():
            self._load_all()

    def _load_all(self) -> None:
        """Load all skill files from the skills directory."""
        if not self._skills_dir:
            return
        for path in self._skills_dir.glob("*.md"):
            try:
                skill = self._parse_skill(path)
                self._skills[skill.name] = skill
                logger.info("Loaded skill: %s (%s)", skill.name, path.name)
            except Exception as e:
                logger.warning("Failed to load skill %s: %s", path.name, e)

    def _parse_skill(self, path: Path) -> Skill:
        """Parse a Markdown skill file into a Skill object."""
        content = path.read_text(encoding="utf-8")
        lines = content.split("\n")

        name = path.stem
        description = ""
        version = "1.0"
        industries: list[str] = []
        products: list[dict[str, Any]] = []
        negotiation_hints: list[str] = []
        actions: list[str] = []

        current_section = ""

        for line in lines:
            stripped = line.strip()

            # Parse header
            if stripped.startswith("# "):
                name = stripped[2:].strip()
                continue

            # Parse sections
            if stripped.startswith("## "):
                current_section = stripped[3:].strip().lower()
                continue

            # Parse metadata
            if stripped.startswith("- **") or stripped.startswith("- "):
                item = stripped.lstrip("- ").strip()

                if current_section == "metadata":
                    if item.startswith("**version"):
                        version = re.sub(r"\*\*.*?\*\*:?\s*", "", item).strip()
                    elif item.startswith("**description"):
                        description = re.sub(r"\*\*.*?\*\*:?\s*", "", item).strip()

                elif current_section == "industries":
                    industries.append(item.strip("*").strip())

                elif current_section == "products":
                    # Parse product: "Name | $min-$max | qty_min-qty_max"
                    product = self._parse_product_line(item)
                    if product:
                        products.append(product)

                elif current_section in ("negotiation", "strategy", "negotiation hints"):
                    negotiation_hints.append(item.strip("*").strip())

                elif current_section == "actions":
                    actions.append(item.strip("*").strip())

            # Parse description from first paragraph
            if not current_section and stripped and not stripped.startswith("#"):
                if not description:
                    description = stripped

        return Skill(
            name=name,
            description=description,
            version=version,
            industries=industries,
            products=products,
            negotiation_hints=negotiation_hints,
            actions=actions,
            raw_content=content,
            source_path=str(path),
        )

    def _parse_product_line(self, line: str) -> dict[str, Any] | None:
        """Parse a product line like 'GPU Hours | $10-$80 | 100-2000'."""
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            return None

        product: dict[str, Any] = {"name": parts[0].strip("*").strip()}

        # Parse price range
        if len(parts) >= 2:
            price_match = re.findall(r"[\d.]+", parts[1])
            if len(price_match) >= 2:
                product["price_min"] = float(price_match[0])
                product["price_max"] = float(price_match[1])
            elif len(price_match) == 1:
                product["price_min"] = float(price_match[0])
                product["price_max"] = float(price_match[0])

        # Parse quantity range
        if len(parts) >= 3:
            qty_match = re.findall(r"\d+", parts[2])
            if len(qty_match) >= 2:
                product["qty_min"] = int(qty_match[0])
                product["qty_max"] = int(qty_match[1])

        return product

    # ── Skill access ─────────────────────────────────────────────────

    def get(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[dict[str, Any]]:
        """List all loaded skills."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "industries": s.industries,
                "products": len(s.products),
                "source": s.source_path,
            }
            for s in self._skills.values()
        ]

    def get_trade_params(self, partner_name: str) -> dict[str, Any] | None:
        """Get trade parameters from skills for a given partner."""
        # Find a skill that matches
        for skill in self._skills.values():
            if skill.products:
                import random
                product = random.choice(skill.products)
                price = (product.get("price_min", 10) + product.get("price_max", 100)) / 2
                qty = (product.get("qty_min", 10) + product.get("qty_max", 100)) // 2
                return {
                    "title": f"{product['name']} Supply Agreement",
                    "terms": {
                        "quantity": qty,
                        "unit_price": round(price, 2),
                        "currency": "USD",
                        "delivery_days": 30,
                        "payment_terms": "net_30",
                    },
                }
        return None

    def add_skill(self, skill: Skill) -> None:
        """Add a skill programmatically."""
        self._skills[skill.name] = skill

    def reload(self) -> None:
        """Reload all skills from disk."""
        self._skills.clear()
        self._load_all()
