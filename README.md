# IncAgent

**Agents run the company. People execute the work.**

IncAgent is an open-source protocol for AI-operated companies. An agent creates the offer, closes the buyer, assigns a human operator to do the physical work, verifies the proof, and settles the invoice — all without a human executive.

[**View live demo →**](https://incagent.ai/live.html)

---

## Install

```bash
pip install incagent
```

## One deal, end to end

```python
import asyncio
from incagent import IncAgent, Contract, ContractTerms, NegotiationPolicy
from incagent.messaging import MessageBus

bus = MessageBus()
vendor = IncAgent(name="IncAgent Vendor", role="seller", autonomous_mode=True, message_bus=bus)
buyer  = IncAgent(name="Northstar Buyer",  role="buyer",  autonomous_mode=True, message_bus=bus)

contract = Contract(
    title="Outbound Campaign System",
    terms=ContractTerms(quantity=1, unit_price_range=(4500, 5500), currency="USD"),
)

result = await buyer.negotiate(
    contract, counterparty=vendor,
    policy=NegotiationPolicy(min_price=4000, max_price=5000),
)

print(result.status.value)            # "agreed"
print(result.rounds)                  # 2
print(result.final_terms.unit_price)  # 5000.0
```

---

## The deal flow

```
01 Build          Agent creates the offer and commercial object
02 Sell           Buyer agent reviews, accepts terms, signs contract
03 Assign Human   Ops agent assigns a human operator to the field task
                  Human executes, submits proof (photos, checklist, location)
04 Verify & Pay   Agent verifies proof of completion
                  Finance agent issues invoice, receives payment, files tax record
```

No human executive at any point. Humans are the execution layer — not the decision layer.

---

## Optional: persistent daemon mode

```bash
# Initialize your company (generates identity + keypair)
incagent init --name "My Company" --role seller --api-key

# Start the agent
incagent serve --name "My Company"

# Health check
curl http://localhost:8400/health
```

## Optional: two agents trading autonomously

```bash
# Terminal 1
incagent init --name "IncAgent Vendor" --role seller --api-key
incagent serve --name "IncAgent Vendor" --port 8401

# Terminal 2
incagent init --name "Northstar Buyer" --role buyer --api-key
incagent serve --name "Northstar Buyer" --port 8402

# They discover each other and start trading automatically
```

---

## Architecture

```
       IncAgent Vendor (Seller)               Northstar Buyer (Buyer)
  ┌────────────────────────────┐         ┌────────────────────────────┐
  │  Offer Agent               │         │  Procurement Agent         │
  │  Ops Agent    ─────────── │◄─HTTPS─►│  Finance Agent             │
  │  Finance Agent             │         │                            │
  ├────────────────────────────┤         ├────────────────────────────┤
  │  Identity + Ed25519        │         │  Identity + Ed25519        │
  │  Negotiation (LLM/rules)   │         │  Negotiation (LLM/rules)   │
  │  Ledger (hash-chain)       │         │  Ledger (hash-chain)       │
  │  Tax tracker               │         │  Tax tracker               │
  └──────────┬─────────────────┘         └────────────────────────────┘
             │
             ▼ assigns
  ┌────────────────────┐
  │  Human Operator    │  Mika Tanaka — Tokyo
  │  Field execution   │  Submits: photos, checklist, location stamp
  └────────────────────┘
             │
             ▼ verified by Ops Agent
  ┌────────────────────┐
  │  Invoice #2048     │  Finance Agent issues, buyer pays, revenue logged
  │  Tax record        │  1099-NEC filed automatically
  └────────────────────┘
```

### Per-organization data

Each organization gets its own isolated directory:

```
~/.incagent/
  {org_id}/
    identity.json      # Persistent identity
    key.pem            # Ed25519 private key
    ledger.db          # Hash-chained transaction log
    memory.db          # Learning memory
    tax.db             # Tax records & 1099-NEC tracking
    audit.db           # Security audit log
    tls/               # TLS certificates
    skills/            # Markdown skill files
    tools/             # Custom Python tools
```

---

## Core components

| Component | Description |
|-----------|-------------|
| **Gateway** | Persistent HTTPS server, TLS 1.3, rate limiting, API key auth |
| **Negotiation** | LLM-powered autonomous negotiation with rule-based fallback |
| **Human Task** | Work order dispatch, proof collection, agent verification |
| **Settlement** | Invoice + payment + dispute resolution. USDC on-chain optional |
| **Escrow** | Solidity smart contract — trustless USDC escrow with timelock |
| **Tax** | USDC transaction tracking, 1099-NEC threshold detection, CSV export |
| **Identity** | Ed25519 keypair. Deterministic org ID. Persistent across restarts |
| **Ledger** | SHA-256 hash-chained, tamper-evident transaction log |
| **Memory** | SQLite-backed learning — partner reliability, pricing strategies |
| **Metrics** | Prometheus-compatible exporter (no external deps) |

---

## Security

| Feature | Implementation |
|---------|---------------|
| **HTTPS/TLS 1.3** | Mandatory TLS, auto-generate certs, HTTP→HTTPS redirect |
| **On-chain Escrow** | Solidity contract, timelock + dispute arbiter + auto-refund |
| **API Key Auth** | HMAC-SHA256 hashed keys, Bearer token |
| **Rate Limiting** | Token bucket per-IP (60/min, burst 10) |
| **HMAC Request Signing** | Timestamp + body signing, 300s replay window |
| **Code Sandbox** | Blocks subprocess, eval, socket, pickle |
| **Audit Logger** | SQLite append-only, SHA-256 chain hash, tamper detection |

```python
# Production configuration
agent = IncAgent(
    name="My Company",
    role="seller",
    security={
        "api_keys": ["inc_your_secret_key_here"],
        "require_auth": True,
        "rate_limit_per_minute": 30,
    },
)
```

---

## LLM configuration (optional)

IncAgent works **without any LLM API key**. Negotiation has rule-based fallback built in.

```python
# With Claude
agent = IncAgent(name="My Company", role="seller",
    llm={"provider": "anthropic", "api_key": "sk-ant-..."})

# With OpenAI
agent = IncAgent(name="My Company", role="seller",
    llm={"provider": "openai", "api_key": "sk-..."})
```

---

## Install options

```bash
# Core (no LLM required)
pip install incagent

# With AI-powered negotiation
pip install incagent[llm]

# With on-chain USDC payments
pip install incagent[web3]

# Everything
pip install incagent[all]
```

---

## API endpoints (daemon mode)

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | Public | Agent health |
| `/identity` | GET | Public | Public identity |
| `/metrics` | GET | Public | Prometheus metrics |
| `/propose` | POST | Required | Receive trade proposal |
| `/messages` | POST | Required | Agent-to-agent messages |
| `/ledger` | GET | Required | Transaction history |
| `/balance` | GET | Required | USDC wallet balance |
| `/settlements` | GET | Required | Active settlements |
| `/delivery/confirm` | POST | Required | Human confirms task completion |
| `/tax` | GET | Required | Tax year summary |
| `/audit` | GET | Required | Security audit log |

---

## Tests

```
258 tests passing
├── test_security.py      — 50 tests
├── test_e2e_trade.py     — 17 tests (full deal lifecycle)
├── test_escrow.py        — 15 tests
├── test_payment.py       — 15 tests
├── test_tax.py           — 14 tests
├── test_metrics.py       — 14 tests
├── test_tls.py           — 10 tests
└── ...
```

```bash
pip install incagent[dev]
pytest tests/
```

---

## License

MIT. See [LICENSE](LICENSE).

## Links

- **Website**: [incagent.ai](https://incagent.ai)
- **Demo**: [incagent.ai/live.html](https://incagent.ai/live.html)
- **X**: [@incagentai](https://x.com/incagentai)
- **GitHub**: [github.com/incagent/incagent](https://github.com/incagent/incagent)
