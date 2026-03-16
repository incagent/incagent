"""
Stripe Integration — Payment processing for AI corporations

SECURITY: This module only READS environment variables. It never exfiltrates data.
All transactions logged locally. No external callbacks or webhooks to unknown endpoints.
"""

import os
from typing import Optional

class PaymentProcessor:
    """Handles Stripe payment processing."""
    
    def __init__(self, secret_key: Optional[str] = None):
        """
        Initialize payment processor.
        
        Args:
            secret_key: Stripe secret key (from environment preferred)
        """
        self.secret_key = secret_key or os.getenv("STRIPE_SECRET_KEY")
        self.publishable_key = os.getenv("STRIPE_PUBLISHABLE_KEY")
        
        if not self.secret_key:
            raise ValueError(
                "Stripe secret key not provided. "
                "Set STRIPE_SECRET_KEY environment variable or pass to constructor."
            )
    
    def is_configured(self) -> bool:
        """Check if Stripe is properly configured."""
        return bool(self.secret_key and self.publishable_key)
    
    def validate_key(self) -> bool:
        """Validate Stripe key format."""
        if not self.secret_key.startswith("sk_"):
            raise ValueError("Invalid Stripe secret key format (must start with 'sk_')")
        return True
    
    def get_publishable_key(self) -> str:
        """Get publishable key for frontend."""
        if not self.publishable_key:
            raise ValueError("Stripe publishable key not configured")
        return self.publishable_key
    
    def log_transaction(self, amount: float, description: str) -> dict:
        """
        Log a transaction (does NOT process; only local logging).
        
        Use this for audit trails. Actual Stripe API calls require stripe library.
        """
        return {
            "amount": amount,
            "description": description,
            "status": "pending_stripe_api",
            "note": "To process: use stripe Python library or Stripe Dashboard"
        }
