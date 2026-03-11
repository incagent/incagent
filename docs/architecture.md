# Architecture

## System Overview

```
┌──────────────────────────────────────────────┐
│                  IncAgent                     │
├──────────────────────────────────────────────┤
│                                              │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐ │
│  │ Identity │  │ Negotiation│  │ Approval │ │
│  │          │  │  Engine    │  │ Gateway  │ │
│  └──────────┘  └────────────┘  └──────────┘ │
│                                              │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐ │
│  │ Contract │  │Transaction │  │ Messaging│ │
│  │ Manager  │  │  Manager   │  │   Bus    │ │
│  └──────────┘  └────────────┘  └──────────┘ │
│                                              │
│  ┌──────────┐  ┌────────────┐               │
│  │  Ledger  │  │ Resilience │               │
│  │ (SQLite) │  │  Executor  │               │
│  └──────────┘  └────────────┘               │
│                                              │
└──────────────────────────────────────────────┘
```

## Module Responsibilities

### `agent.py` — IncAgent
The main orchestrator. Coordinates all subsystems and manages the agent lifecycle.

**States**: `idle` → `negotiating` → `awaiting_approval` → `executing` → `idle`

### `identity.py` — Corporate Identity
Manages cryptographic identity using Ed25519 keys. Each agent has a unique key pair for signing messages and contracts.

### `contract.py` — Contract Management
Defines the contract data model and lifecycle state machine. Tracks history of all state transitions.

### `negotiation.py` — Negotiation Engine
LLM-powered (Claude/OpenAI) negotiation with rule-based fallback. Operates within policy-defined boundaries.

### `transaction.py` — Transaction Manager
Handles transaction lifecycle with ledger integration. Creates, executes, completes, or fails transactions.

### `resilience.py` — Self-Healing
- **RetryWithBackoff**: Exponential backoff retry
- **CircuitBreaker**: Stops calling failing services, auto-recovers
- **FallbackChain**: Try alternatives when primary fails
- **HealthCheck**: Periodic self-diagnosis

### `approval.py` — Human Approval
Optional human-in-the-loop for high-value transactions. Supports CLI, webhook, and Slack.

### `messaging.py` — Communication
In-process message bus for local agents. HTTP transport for remote agents.

### `ledger.py` — Transaction Ledger
Append-only, hash-chained SQLite database. Provides tamper evidence for all agent actions.

## Data Flow

```
1. Buyer creates Contract with Terms
2. Buyer calls negotiate(contract, seller)
3. NegotiationEngine runs LLM-powered rounds
4. If agreed → ApprovalGateway checks threshold
5. If approved → TransactionManager creates + executes
6. All actions → Ledger (hash-chained)
7. Result returned to caller
```

## Security Model

- Ed25519 key pairs for agent identity
- All messages signed by sender
- Hash-chained ledger (SHA-256) for tamper evidence
- No private keys transmitted over the wire
