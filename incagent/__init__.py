"""IncAgent - The open protocol where AI agents do business."""

from incagent.agent import AgentState, IncAgent
from incagent.approval import ApprovalGateway, ApprovalStatus
from incagent.config import AgentConfig, ApprovalConfig, LLMConfig, ResilienceConfig
from incagent.contract import Contract, ContractStatus, ContractTerms
from incagent.gateway import Gateway
from incagent.heartbeat import Heartbeat, HeartbeatConfig
from incagent.identity import CorporateIdentity, KeyPair, create_identity
from incagent.ledger import Ledger
from incagent.memory import Memory
from incagent.messaging import AgentMessage, MessageBus, MessageType
from incagent.negotiation import NegotiationEngine, NegotiationPolicy, NegotiationResult
from incagent.registry import PeerAgent, Registry
from incagent.resilience import CircuitBreaker, FallbackChain, ResilientExecutor, RetryWithBackoff
from incagent.self_improve import SelfImproveEngine
from incagent.skills import Skill, SkillManager
from incagent.tools import BaseTool, ToolRegistry, ToolResult
from incagent.transaction import Transaction, TransactionManager

__version__ = "0.3.0"

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
    "PeerAgent",
    "Registry",
    "ResilientExecutor",
    "ResilienceConfig",
    "RetryWithBackoff",
    "SelfImproveEngine",
    "Skill",
    "SkillManager",
    "BaseTool",
    "ToolRegistry",
    "ToolResult",
    "Transaction",
    "TransactionManager",
    "create_identity",
]
