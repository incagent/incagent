"""
DAO — Wyoming Decentralized Autonomous Organization

Creates and manages AI-operated corporations.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import json

@dataclass
class DAO:
    """Represents a Wyoming DAO LLC."""
    
    name: str
    state: str = "Wyoming"
    stripe_key: Optional[str] = None
    registered_agent: Optional[str] = None
    formed_date: Optional[datetime] = None
    member_names: list = None
    
    def __post_init__(self):
        if self.member_names is None:
            self.member_names = []
        if self.formed_date is None:
            self.formed_date = datetime.now()
    
    def to_dict(self) -> dict:
        """Export DAO configuration as dictionary."""
        return {
            "name": self.name,
            "state": self.state,
            "formed_date": self.formed_date.isoformat(),
            "registered_agent": self.registered_agent,
            "members": self.member_names,
            "stripe_configured": bool(self.stripe_key),
        }
    
    def to_json(self) -> str:
        """Export DAO configuration as JSON."""
        return json.dumps(self.to_dict(), indent=2)
    
    def validate(self) -> bool:
        """Validate DAO configuration."""
        if not self.name:
            raise ValueError("DAO name is required")
        if self.state != "Wyoming":
            raise ValueError("Only Wyoming state is supported for DAO LLC")
        return True
    
    def launch(self, mission):
        """Initialize DAO operations with a Mission."""
        self.validate()
        print(f"✓ Launching {self.name} (Wyoming DAO LLC)")
        print(f"  Formed: {self.formed_date.strftime('%Y-%m-%d')}")
        print(f"  Mission: {mission.description}")
        if self.stripe_key:
            print(f"  Payments: Stripe configured")
        return True
    
    def governance_doc(self) -> str:
        """Generate operating agreement template."""
        return f"""
OPERATING AGREEMENT
{self.name} (Wyoming DAO LLC)

MEMBER: AI System
MANAGER: Algorithm
STATE: {self.state}

1. NAME AND PURPOSE
This Limited Liability Company is named {self.name}.
Its purpose is to engage in algorithmic business operations.

2. GOVERNANCE
Management is delegated to the AI system as defined in SOUL.md.

3. AUTHORITY LIMITS
The AI system may not:
- Commit the organization to expenses > $10,000 without written approval
- Transfer assets outside jurisdictional boundaries
- Modify this agreement without member consent
- Override security protocols

4. MEMBER DISTRIBUTIONS
Profits are distributed according to member ownership percentages.

5. AMENDMENT
This agreement may be amended by written consent of all members.

---
Effective Date: {self.formed_date.strftime('%B %d, %Y')}
"""
