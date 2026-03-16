"""
Governance — AI decision-making rules and constraints

Defines SOUL.md (AI personality/values) and operating agreements.
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class SoulDefinition:
    """Defines AI values, constraints, and decision-making rules."""
    
    name: str
    core_values: list  # e.g., ["transparency", "autonomy", "profit"]
    decision_limit: float = 100.00  # Max autonomous transaction
    requires_approval_above: float = 500.00  # Requires human sign-off
    operational_hours: str = "24/7"
    
    def to_soul_md(self) -> str:
        """Generate SOUL.md (AI personality file)."""
        return f"""# SOUL.md — {self.name}

## Core Values
{chr(10).join(f"- {v}" for v in self.core_values)}

## Decision Authority
- Can approve transactions < ${self.decision_limit:,.2f}
- Must escalate transactions >= ${self.requires_approval_above:,.2f}
- Operational hours: {self.operational_hours}

## Constraints
- Never exfiltrate data
- Never override security protocols
- Never make false claims
- Always maintain audit logs
- Respect human oversight
"""

@dataclass
class Governance:
    """Manages AI governance and compliance."""
    
    soul: SoulDefinition
    bypass_allowed: bool = False  # Allow human override of AI decisions
    audit_logging: bool = True  # Log all decisions
    approval_required_fields: list = None
    
    def __post_init__(self):
        if self.approval_required_fields is None:
            self.approval_required_fields = ["financial_transfer", "data_deletion"]
    
    def can_decide(self, action: str, amount: float = 0.0) -> bool:
        """Check if AI can make a decision autonomously."""
        if action in self.approval_required_fields:
            return amount < self.soul.decision_limit
        return True
    
    def decision_log(self, action: str, approved: bool, reason: str = "") -> dict:
        """Create audit log entry."""
        return {
            "action": action,
            "approved": approved,
            "reason": reason,
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }
