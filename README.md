# IncAgent

**AI agents run the company. Humans execute.**

IncAgent is an open-source protocol where AI agents autonomously operate corporations. They discover trading partners, negotiate deals, sign contracts, settle payments on-chain, and learn from every interaction. Humans handle the physical world.

## The Vision

```
AI Agent (CEO)
  |-- Market analysis     --> "GPU demand will rise 20% next month"
  |-- Auto-procurement    --> Negotiates with CloudPeak's agent, pays in USDC
  |-- Auto-sales          --> Resells GPU hours to customer agents at 30% margin
  |-- Staffing decisions  --> "Need 2 more engineers" -> posts job listing
  |-- Task delegation     --> "Ship order #4521" -> human gets a ticket
  `-- Strategy learning   --> Adjusts pricing based on 500 past trades
```

The agent handles all business decisions. Humans receive task assignments and execute in the physical world - manufacturing, delivery, customer visits, R&D.

## Quick Start

### SDK Mode (programmatic)

```python
from incagent import IncAgent, Contract, ContractTerms

buyer = IncAgent(name="Acme Corp", role="buyer")
seller = IncAgent(name="Widget Inc", role="seller")

contract = Contract(
    title="GPU Cluster Hours",
    terms=ContractTerms(quantity=1000, unit_price_range=(50, 80)),
)

result = await buyer.negotiate(contract, counterparty=seller)
# NegotiationResult(status='agreed', final_price=65.00, rounds=3)
```

### Gateway Mode (persistent daemon)

```bash
# Initialize organization (generates API key + keypair)
incagent init --name "Acme Corp" --role buyer --api-key

# Start agent daemon
incagent serve --name "Acme Corp"

# Monitor
curl http://localhost:8400/health
curl http://localhost:8400/metrics  # Prometheus format
```

### Two agents trading autonomously

```bash
# Terminal 1: Buyer agent
incagent init --name "Acme Corp" --role buyer --api-key
incagent serve --name "Acme Corp" --port 8401

# Terminal 2: Seller agent
incagent init --name "CloudPeak" --role seller --api-key
incagent serve --name "CloudPeak" --port 8402

# They discover each other and start trading automatically
```

## Architecture

```
              Agent A (Buyer)                    Agent B (Seller)
      ┌──────────────────────┐           ┌──────────────────────┐
      │  Gateway :8401       │◄──HTTP───►│  Gateway :8402       │
      ├──────────────────────┤           ├──────────────────────┤
      │  Identity + Ed25519  │           │  Identity + Ed25519  │
      │  Security (API/HMAC) │           │  Security (API/HMAC) │
      │  Negotiation (LLM)   │           │  Negotiation (LLM)   │
      │  Memory (SQLite)     │           │  Memory (SQLite)     │
      │  Tax Tracker         │           │  Tax Tracker         │
      │  Metrics (Prometheus)│           │  Metrics (Prometheus)│
      │  Ledger (hash-chain) │           │  Ledger (hash-chain) │
      │  Tools (extensible)  │           │  Tools (extensible)  │
      └───┬──────┬───────────┘           └──────────┬───────────┘
          │      │                                  │
          ▼      ▼                                  ▼
   ┌─────────┐ ┌────────────┐              ┌─────────────┐
   │EVM Chain│ │ Slack/Email │              │  EVM Chain  │
   │ (USDC)  │ │ Webhook/API │              │  (USDC)     │
   └─────────┘ └────────────┘              └─────────────┘
```

### Per-Organization Data Isolation

Each organization gets its own directory (deterministic ID from org name):

```
~/.incagent/
  {org_id}/
    identity.json      # Persistent identity
    key.pem            # Ed25519 private key
    ledger.db          # Hash-chained transaction log
    memory.db          # Learning memory
    tax.db             # Tax records & 1099-NEC tracking
    audit.db           # Security audit log
    skills/            # Markdown skill files
    tools/             # Custom Python tools
    reports/           # Generated reports
```

## Core Components

| Component | Description |
|-----------|-------------|
| **Gateway** | Persistent HTTP server with REST API, rate limiting, API key auth |
| **Identity** | Ed25519 keypair. Deterministic org ID. Persistent across restarts |
| **Security** | API key auth, HMAC signing, rate limiting, code sandbox, audit log |
| **Negotiation** | LLM-powered autonomous negotiation with rule-based fallback |
| **Settlement** | Payment + delivery + dispute resolution. USDC on-chain |
| **Payment** | EIP-1559 gas, RPC failover, nonce management, RBF (Replace-By-Fee) |
| **Tax** | USDC transaction tracking, 1099-NEC vendor detection, CSV/JSON export |
| **Metrics** | Prometheus-compatible metrics exporter (no external deps) |
| **Memory** | SQLite-backed learning. Partner reliability, pricing strategies |
| **Ledger** | Tamper-evident, SHA-256 hash-chained transaction log |
| **Tools** | Extensible. Agent can create new tools at runtime (sandboxed) |
| **Skills** | Markdown plugins. Add trade types without code |

## Security

### v0.6.0 Security Features

| Feature | Implementation |
|---------|---------------|
| **API Key Auth** | HMAC-SHA256 hashed keys, Bearer token, env var fallback |
| **Rate Limiting** | Token bucket per-IP (60/min, burst 10) |
| **HMAC Request Signing** | Timestamp + body signing, 300s replay window |
| **Code Sandbox** | Static analysis blocks subprocess, eval, socket, pickle, etc. |
| **Shell Validation** | 40+ blocked patterns (reverse shells, data exfil, privesc) |
| **Input Validation** | Two-tier: strict (names) + permissive (content/Markdown) |
| **CORS Lockdown** | Default deny-all, explicit allowlist only |
| **Audit Logger** | SQLite append-only, SHA-256 chain hash, tamper detection |
| **Peer Signing** | HMAC-signed inter-agent messages |
| **Tool Control** | Denylist/allowlist, creation and self-improvement disabled by default |

### Configuration

```python
# Production
agent = IncAgent(
    name="Acme Corp",
    role="buyer",
    security={
        "api_keys": ["inc_your_secret_key_here"],
        "require_auth": True,
        "allowed_origins": ["https://your-dashboard.com"],
        "rate_limit_per_minute": 30,
        "tool_denylist": ["shell_exec"],
        "allow_tool_creation_via_api": False,
        "allow_self_improve_via_api": False,
    },
)
```

```bash
# Environment variables
INCAGENT_API_KEY=inc_your_secret_key
INCAGENT_SHELL_STRICT=true
INCAGENT_DATA_DIR=/path/to/agent/data
```

See [SECURITY_ROADMAP.md](SECURITY_ROADMAP.md) for full details.

## Payment (EVM/USDC)

On-chain USDC payments on Base, Arbitrum, Ethereum, or Polygon. Falls back to simulated off-chain mode when no wallet is configured.

### Features (v0.6.0)

- **EIP-1559 gas management** — dynamic `maxFeePerGas` / `maxPriorityFeePerGas`
- **Balance check** — pre-transfer verification, fail-fast on insufficient funds
- **Nonce management** — thread-safe for concurrent transactions
- **RPC failover** — multiple RPC URLs, automatic reconnection
- **Replace-By-Fee (RBF)** — bump stuck transactions by 10% gas

```python
agent = IncAgent(
    name="Acme Corp", role="buyer",
    payment={
        "chain": "base",
        "rpc_url": "https://mainnet.base.org",
        "rpc_urls": ["https://base-rpc-backup.example.com"],
        "private_key": "0x...",
    },
)

balance = await agent.get_balance()  # USDC balance
```

## Tax Tracking (US Compliance)

Built-in USDC transaction tracking for US corporate tax requirements.

- All payments automatically recorded (income/expense/escrow/refund)
- Per-vendor totals with 1099-NEC threshold detection ($600/year)
- JSON and CSV export for tax filing

```python
# Get tax year summary
summary = agent.get_tax_summary(2026)
# {"total_income": 50000.0, "total_expenses": 30000.0, "net": 20000.0,
#  "vendors_needing_1099": 3, ...}

# API endpoint
curl http://localhost:8400/tax?year=2026
```

## Prometheus Metrics

Built-in Prometheus-compatible metrics exporter (no external dependencies).

```bash
curl http://localhost:8400/metrics
```

Metrics include:
- `incagent_trades_total{status}` — trade outcomes
- `incagent_payments_total{status}` — payment outcomes
- `incagent_negotiations_total` — negotiations started
- `incagent_active_settlements` — current active settlements
- `incagent_usdc_balance` — current USDC balance
- `incagent_negotiation_rounds` — rounds per negotiation (histogram)
- `incagent_negotiation_duration_seconds` — time per negotiation

## Settlement & Delivery

### Settlement Modes

| Mode | Flow |
|------|------|
| **DIRECT** | Buyer pays seller immediately after delivery verification |
| **ESCROW** | Funds held in smart contract until delivery confirmed |
| **PREPAID** | Buyer pays upfront, delivery tracked separately |
| **COD** | Payment on physical delivery confirmation |

### Delivery Verification

| Type | Verification | Example |
|------|-------------|---------|
| **Digital** | Auto (API check, file hash) | API key provisioned |
| **Physical** | Human or webhook | Package delivered, signed receipt |
| **Service** | Ongoing monitoring | SLA compliance check |

### Dispute Resolution

```python
dispute = agent.file_dispute(settlement_id, "Never received goods")
# Resolution: RESOLVED_BUYER (refund), RESOLVED_SELLER (release), RESOLVED_SPLIT
```

## API Endpoints (Gateway Mode)

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | Public | Agent health status |
| `/identity` | GET | Public | Public identity info |
| `/metrics` | GET | Public | Prometheus metrics |
| `/messages` | POST | Required | Receive message from another agent |
| `/propose` | POST | Required | Receive trade proposal |
| `/peers` | GET | Required | List known peers |
| `/peers` | POST | Required | Register a new peer |
| `/memory` | GET | Required | View learned insights |
| `/ledger` | GET | Required | Transaction history |
| `/skills` | GET | Required | Available skills |
| `/tools` | GET | Required | List available tools |
| `/tools` | POST | Required | Create a new custom tool |
| `/tools/{name}` | POST | Required | Execute a tool by name |
| `/improve` | POST | Required | Trigger self-improvement cycle |
| `/balance` | GET | Required | USDC wallet balance |
| `/settlements` | GET | Required | List active settlements |
| `/delivery/confirm` | POST | Required | Human confirms physical delivery |
| `/delivery/webhook` | POST | Required | External system confirms delivery |
| `/dispute` | POST | Required | File a dispute for a settlement |
| `/audit` | GET | Required | View security audit log |
| `/tax` | GET | Required | Tax year summary |

## CLI Commands

```bash
incagent init --name "Corp" --role buyer --api-key  # Initialize org
incagent serve --name "Corp"                         # Start daemon
incagent orgs                                        # List organizations
```

## LLM Configuration (Optional)

IncAgent works **without any LLM API key**. All negotiation and self-improvement features have rule-based fallback logic built in.

```python
# Anthropic (Claude)
agent = IncAgent(
    name="Acme Corp", role="buyer",
    llm={"provider": "anthropic", "api_key": "sk-ant-..."}
)

# OpenAI (GPT)
agent = IncAgent(
    name="Acme Corp", role="buyer",
    llm={"provider": "openai", "api_key": "sk-..."}
)
```

## Installation

```bash
pip install incagent

# With LLM support (for AI-powered negotiation)
pip install incagent[llm]

# With on-chain payment (EVM/USDC)
pip install incagent[web3]

# Development
pip install incagent[dev]
```

## Test Coverage

```
233 tests passing
├── test_security.py      — 50 tests (auth, rate limiting, sandbox, audit)
├── test_org_setup.py     — 16 tests (identity, persistence, isolation)
├── test_e2e_trade.py     — 17 tests (full trade lifecycle, disputes)
├── test_payment.py       — 15 tests (config, balance, RPC failover)
├── test_tax.py           — 14 tests (records, 1099-NEC, export)
├── test_metrics.py       — 14 tests (counters, gauges, histograms)
└── ... (agent, contract, negotiation, resilience, settlement, tools, gateway)
```

## License

MIT License. See [LICENSE](LICENSE).

## Links

- Website: [incagent.ai](https://incagent.ai)
- X: [@incagentai](https://x.com/incagentai)
- GitHub: [github.com/incagent/incagent](https://github.com/incagent/incagent)
