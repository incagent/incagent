# IncAgent Protocol Specification v0.1

## Overview

The IncAgent Protocol defines a standard for autonomous AI-to-AI corporate transactions. It specifies how AI agents identify themselves, communicate, negotiate contracts, and record transactions.

## 1. Agent Identity

Each agent MUST have:

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | UUID v4 | Globally unique agent identifier |
| `name` | string | Human-readable corporate name |
| `role` | enum | `buyer`, `seller`, or `broker` |
| `jurisdiction` | string | Legal jurisdiction (e.g., `US-DE`) |
| `public_key` | hex string | Ed25519 public key for message signing |

### Identity Fingerprint

A 16-character hex string derived from `SHA-256(agent_id:name:public_key)[:16]`.

## 2. Message Format

All agent-to-agent messages use JSON:

```json
{
    "message_id": "abc123...",
    "sender_id": "uuid-of-sender",
    "recipient_id": "uuid-of-recipient",
    "message_type": "proposal",
    "payload": { ... },
    "timestamp": "2026-03-12T10:00:00Z",
    "signature": "hex-encoded-ed25519-signature",
    "reply_to": null
}
```

### Message Types

| Type | Description |
|------|-------------|
| `proposal` | New contract proposal |
| `counter_proposal` | Modified terms in negotiation |
| `accept` | Accept current terms |
| `reject` | Reject and end negotiation |
| `info` | Informational message |
| `heartbeat` | Keep-alive signal |
| `error` | Error notification |

## 3. Contract Lifecycle

```
draft → proposed → negotiating → agreed → executed → completed
                                                   ↘ disputed
                 ↘ cancelled
```

### Contract Object

```json
{
    "contract_id": "uuid",
    "title": "Widget Supply Agreement",
    "terms": {
        "quantity": 1000,
        "unit_price": 65.00,
        "currency": "USD",
        "delivery_days": 30,
        "payment_terms": "net_30"
    },
    "status": "agreed",
    "proposer_id": "uuid-buyer",
    "counterparty_id": "uuid-seller",
    "signatures": {
        "uuid-buyer": "hex-sig",
        "uuid-seller": "hex-sig"
    }
}
```

## 4. Negotiation Protocol

1. Agent A sends `proposal` with initial terms
2. Agent B evaluates against its `NegotiationPolicy`
3. Agent B sends `counter_proposal` with modified terms, or `accept`/`reject`
4. Repeat until `accept`, `reject`, or max rounds exceeded

### Negotiation Policy

Each agent defines boundaries:

```json
{
    "min_price": 40.0,
    "max_price": 70.0,
    "max_rounds": 10,
    "walk_away_threshold": 5000.0,
    "acceptable_payment_terms": ["net_30", "net_60"]
}
```

## 5. Transaction Ledger

Each agent maintains a local, hash-chained ledger (SQLite):

```
Entry N: hash(timestamp | agent_id | action | data | prev_hash)
```

This provides tamper evidence — any modification breaks the chain.

### Ledger Actions

| Action | Description |
|--------|-------------|
| `agent_created` | Agent initialization |
| `negotiation_started` | Negotiation begins |
| `negotiation_completed` | Negotiation ends |
| `transaction_created` | Transaction initiated |
| `transaction_executing` | Transaction in progress |
| `transaction_completed` | Transaction successful |
| `transaction_failed` | Transaction failed |

## 6. Resilience

Agents SHOULD implement:

- **Retry with exponential backoff** for transient failures
- **Circuit breaker** to stop calling failing services
- **Fallback chain** for alternative strategies
- **Health checks** for self-diagnosis

## 7. Human Approval (Optional)

For regulated or high-value transactions:

- Set a dollar threshold above which human approval is required
- Support CLI, webhook, or Slack notification methods
- Configurable timeout with auto-reject on expiry

## 8. Transport

Default transport: HTTP POST to `{agent_url}/messages`

Future transports: WebSocket, gRPC, NATS.

## 9. Security

- All messages MUST be signed with the sender's Ed25519 private key
- Recipients MUST verify signatures before processing
- Ledger entries are hash-chained for tamper evidence
- No secrets are transmitted in messages (only public keys)

---

**Version**: 0.1.0-draft
**Status**: Draft
**License**: MIT
