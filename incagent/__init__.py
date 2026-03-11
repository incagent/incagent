"""IncAgent - The open protocol where AI agents do business."""

from incagent.agent import AgentState, IncAgent
from incagent.approval import ApprovalGateway, ApprovalStatus
from incagent.config import AgentConfig, ApprovalConfig, LLMConfig, ResilienceConfig
from incagent.contract import Contract, ContractStatus, ContractTerms
from incagent.identity import CorporateIdentity, KeyPair, create_identity
from incagent.ledger import Ledger
from incagent.messaging import AgentMessage, MessageBus, MessageType
from incagent.negotiation import NegotiationEngine, NegotiationPolicy, NegotiationResult
from incagent.resilience import CircuitBreaker, FallbackChain, ResilientExecutor, RetryWithBackoff
from incagent.transaction import Transaction, TransactionManager

__version__ = "0.1.0"

__all__ = [
    "IncAgent",
    "AgentState",
    "AgentConfig",
    "ApprovalConfig",
    "ApprovalGateway",
    "ApprovalStatus",
    "CircuitBreaker",
    "Contract",
    "ContractStatus",
    "ContractTerms",
    "CorporateIdentity",
    "FallbackChain",
    "KeyPair",
    "Ledger",
    "LLMConfig",
    "AgentMessage",
    "MessageBus",
    "MessageType",
    "NegotiationEngine",
    "NegotiationPolicy",
    "NegotiationResult",
    "ResilientExecutor",
    "ResilienceConfig",
    "RetryWithBackoff",
    "Transaction",
    "TransactionManager",
    "create_identity",
]
