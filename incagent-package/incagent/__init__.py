"""
Incagent — Framework for AI-Operated Corporations

Wyoming DAO LLC + OpenClaw integration for autonomous business operations.
"""

__version__ = "0.1.0"
__author__ = "Incagent DAO LLC"

from .dao import DAO
from .mission import Mission
from .governance import Governance, SoulDefinition
from .stripe_integration import PaymentProcessor
from .cli import main as cli_main

__all__ = [
    "DAO",
    "Mission",
    "Governance",
    "SoulDefinition",
    "PaymentProcessor",
    "cli_main",
]
