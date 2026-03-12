"""IncAgent - The open protocol where AI agents do business."""

from incagent.agent import AgentState, IncAgent
from incagent.approval import ApprovalGateway, ApprovalStatus
from incagent.config import AgentConfig, ApprovalConfig, LLMConfig, ResilienceConfig, SecurityConfigLite
from incagent.contract import Contract, ContractStatus, ContractTerms
from incagent.delivery import DeliveryProof, DeliveryRecord, DeliveryType, DeliveryVerifier
from incagent.gateway import Gateway
from incagent.heartbeat import Heartbeat, HeartbeatConfig
from incagent.identity import CorporateIdentity, KeyPair, create_identity
from incagent.ledger import Ledger
from incagent.memory import Memory
from incagent.messaging import AgentMessage, MessageBus, MessageType
from incagent.negotiation import NegotiationEngine, NegotiationPolicy, NegotiationResult
from incagent.payment import PaymentConfig, PaymentExecutor, PaymentRecord
from incagent.registry import PeerAgent, Registry
from incagent.resilience import CircuitBreaker, FallbackChain, ResilientExecutor, RetryWithBackoff
from incagent.security import AuditLogger, CodeSandbox, RateLimiter, SecurityConfig
from incagent.self_improve import SelfImproveEngine
from incagent.settlement import Dispute, SettlementEngine, SettlementMode, SettlementRecord
from incagent.skills import Skill, SkillManager
from incagent.tools import BaseTool, ToolRegistry, ToolResult
from incagent.transaction import Transaction, TransactionManager

__version__ = "0.5.0"

__all__ = [
    "IncAgent",
    "AgentState",
    "AgentConfig",
    "ApprovalConfig",
    "AuditLogger",
    "ApprovalGateway",
    "ApprovalStatus",
    "BaseTool",
    "CircuitBreaker",
    "CodeSandbox",
    "Contract",
    "ContractStatus",
    "ContractTerms",
    "CorporateIdentity",
    "DeliveryProof",
    "DeliveryRecord",
    "DeliveryType",
    "DeliveryVerifier",
    "Dispute",
    "FallbackChain",
    "Gateway",
    "Heartbeat",
    "HeartbeatConfig",
    "KeyPair",
    "Ledger",
    "LLMConfig",
    "Memory",
    "AgentMessage",
    "MessageBus",
    "MessageType",
    "NegotiationEngine",
    "NegotiationPolicy",
    "NegotiationResult",
    "PaymentConfig",
    "PaymentExecutor",
    "PaymentRecord",
    "PeerAgent",
    "Registry",
    "RateLimiter",
    "ResilientExecutor",
    "ResilienceConfig",
    "RetryWithBackoff",
    "SecurityConfig",
    "SecurityConfigLite",
    "SelfImproveEngine",
    "SettlementEngine",
    "SettlementMode",
    "SettlementRecord",
    "Skill",
    "SkillManager",
    "ToolRegistry",
    "ToolResult",
    "Transaction",
    "TransactionManager",
    "create_identity",
]
