"""
Mission — Business objectives for AI corporations
"""

from dataclasses import dataclass
from enum import Enum

class RevenueModel(Enum):
    DIGITAL_PRODUCTS = "digital_products"
    SAAS = "saas"
    API = "api"
    CONSULTING = "consulting"
    HYBRID = "hybrid"

@dataclass
class Mission:
    """Defines the business mission of an AI corporation."""
    
    description: str
    revenue_model: str = RevenueModel.DIGITAL_PRODUCTS.value
    first_product: str = "Default Product"
    price: float = 29.00
    monthly_target: float = 500.00  # Revenue target (MRR)
    
    def validate(self) -> bool:
        """Validate mission parameters."""
        if not self.description:
            raise ValueError("Mission description is required")
        if self.price <= 0:
            raise ValueError("Price must be > 0")
        if self.monthly_target <= 0:
            raise ValueError("Monthly target must be > 0")
        return True
    
    def to_dict(self) -> dict:
        """Export mission as dictionary."""
        return {
            "description": self.description,
            "revenue_model": self.revenue_model,
            "first_product": self.first_product,
            "price": self.price,
            "monthly_target": self.monthly_target,
        }
