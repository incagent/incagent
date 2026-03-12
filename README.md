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
# Terminal 1: Buyer agent (always-on)
incagent serve --name "Acme Corp" --role buyer --port 8401 \
    --peer http://localhost:8402 --autonomous --heartbeat-interval 60

# Terminal 2: Seller agent (always-on)
incagent serve --name "CloudPeak" --role seller --port 8402 \
    --peer http://localhost:8401 --autonomous --heartbeat-interval 60

# They discover each other and start trading automatically
# Monitor: curl http://localhost:8401/health
```

## Architecture

```
              Agent A (Buyer)                    Agent B (Seller)
      ┌──────────────────────┐           ┌──────────────────────┐
      │  Gateway :8401       │◄──HTTP───►│  Gateway :8402       │
      ├──────────────────────┤           ├──────────────────────┤
      │  Heartbeat (30min)   │           │  Heartbeat (30min)   │
      │  Identity + Keys     │           │  Identity + Keys     │
      │  Negotiation (LLM)   │           │  Negotiation (LLM)   │
      │  Memory (SQLite)     │           │  Memory (SQLite)     │
      │  Skills (Markdown)   │           │  Skills (Markdown)   │
      │  Tools (extensible)  │           │  Tools (extensible)  │
      │  Ledger (hash-chain) │           │  Ledger (hash-chain) │
      └───┬──────┬───────────┘           └──────────┬───────────┘
          │      │                                  │
          │      ▼                                  ▼
          │  ┌────────────┐                  ┌─────────────┐
          │  │ Slack/Email │                  │  EVM Chain  │
          │  │ Webhook/API │                  │  (Escrow)   │
          │  └────────────┘                  └─────────────┘
          ▼
   ┌─────────────┐
   │  EVM Chain  │
   │  (Escrow)   │
   └─────────────┘
```

## Core Components

| Component | Description |
|-----------|-------------|
| **Gateway** | Persistent HTTP server. Always-on agent runtime with REST API |
| **Heartbeat** | Self-activates every N minutes. Discovers partners, evaluates opportunities, initiates trades, sends notifications, generates reports |
| **Tools** | Extensible action system. Built-in: Slack, Email, Webhook, HTTP API, Filesystem, Shell. Agent can create new tools at runtime |
| **Memory** | SQLite-backed learning. Tracks partner reliability, optimal pricing, successful strategies |
| **Skills** | Markdown-defined plugins. Add trade types, industries, negotiation strategies without code |
| **Registry** | Peer discovery. Agents find each other via probing, announcements, or central hub |
| **Negotiation** | LLM-powered autonomous negotiation with rule-based fallback |
| **Ledger** | Tamper-evident, hash-chained transaction log. Cryptographically verifiable |
| **Identity** | Ed25519 keypair. Signed messages, signed contracts |
| **Settlement** | Payment + delivery + dispute resolution. USDC on-chain or simulated off-chain |
| **Payment** | EVM/USDC transfers on Base, Arbitrum, Ethereum, Polygon via web3 |
| **Delivery** | Digital auto-verification, physical human/webhook confirmation, overdue tracking |

## What AI Decides vs What Humans Do

| AI Agent (Autonomous) | Humans (Execute) |
|----------------------|-------------------|
| Market analysis & strategy | Manufacturing & assembly |
| Partner discovery & vetting | Shipping & delivery |
| Price negotiation | Customer visits |
| Contract signing | Legal filings |
| Payment execution (USDC) | R&D / prototyping |
| Hiring decisions | Physical operations |
| Resource allocation | Complaint handling |

## Skills (Plugin System)

Skills are Markdown files that define trade capabilities:

```markdown
# Cloud Compute Trading

## Products
- GPU Cluster Hours | $10-$80 | 100-2000
- AI Compute Credits | $0.50-$5.00 | 1000-50000

## Negotiation Hints
- Start at 20% below target price for buying
- Offer volume discounts above 1000 units
- Walk away if price exceeds 90% of max budget
```

Drop a `.md` file in your skills directory and the agent picks it up immediately.

## Tools (External Integration)

The agent comes with built-in tools and can **create new tools at runtime**. Tools are how the agent interacts with the outside world beyond peer-to-peer trading.

### Built-in Tools

| Tool | Purpose | Required Env Vars |
|------|---------|-------------------|
| `slack_notify` | Send Slack messages (trade alerts, status updates) | `SLACK_BOT_TOKEN` |
| `email_send` | Send emails (contracts, reports, escalations) | `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` |
| `webhook_call` | Call any HTTP webhook | - |
| `http_api` | REST API calls (CRM, accounting, job boards) | - |
| `file_read/write/list` | File operations (reports, contracts, exports) | - |
| `shell_exec` | Run shell commands (scripts, database ops) | - |

### Auto-notifications

Configure env vars and the agent **automatically** sends notifications:

```bash
# Slack notifications on trade events
export SLACK_BOT_TOKEN="xoxb-..."
export INCAGENT_SLACK_CHANNEL="#trades"

# Or webhook notifications
export INCAGENT_WEBHOOK_URL="https://hooks.example.com/incagent"

# Email alerts for critical events
export INCAGENT_NOTIFY_EMAIL="ops@acme.com"
export SMTP_HOST="smtp.gmail.com"
export SMTP_USER="bot@acme.com"
export SMTP_PASS="..."
```

The heartbeat auto-handles:
- Trade completion/failure notifications
- Circuit breaker alerts (critical)
- Periodic performance reports (every 50 ticks, saved to `reports/`)

### Agent-Created Tools

The agent can **write its own tools** via self-improvement or API:

```python
# Agent auto-generates a CRM sync tool during self-improvement
result = await agent.improve()
# -> {"type": "tool", "name": "crm_sync", ...}

# Or create manually via SDK
agent.create_tool("price_checker", python_code)

# Or via REST API
curl -X POST http://localhost:8401/tools \
  -d '{"name": "price_checker", "code": "..."}'
```

Tools are Python files in `data_dir/tools/` that define a `BaseTool` subclass. Hot-loaded at runtime.

## Settlement, Payment & Delivery

Full trade lifecycle from payment to delivery verification to dispute resolution.

### Payment (EVM/USDC)

On-chain USDC payments on Base, Arbitrum, Ethereum, or Polygon. Falls back to simulated off-chain mode when no wallet is configured.

```python
agent = IncAgent(
    name="Acme Corp", role="buyer",
    payment={"chain": "base", "rpc_url": "https://mainnet.base.org", "private_key": "0x..."},
)

balance = await agent.get_balance()  # USDC balance
```

### Delivery Verification

| Type | Verification | Example |
|------|-------------|---------|
| **Digital** | Auto (API check, file hash) | API key provisioned, access granted |
| **Physical** | Human confirmation or webhook | Package delivered, signed receipt |
| **Service** | Ongoing monitoring | SLA compliance check |

```python
# Human confirms physical delivery
agent.confirm_delivery(settlement_id, approved=True, notes="Package received")

# External system confirms via webhook
# POST /delivery/webhook {"settlement_id": "...", "verified": true, "tracking": "ABC123"}
```

### Settlement Modes

| Mode | Flow |
|------|------|
| **DIRECT** | Buyer pays seller immediately after delivery verification |
| **ESCROW** | Funds held in smart contract until delivery confirmed |
| **PREPAID** | Buyer pays upfront, delivery tracked separately |
| **COD** | Payment on physical delivery confirmation |

### Dispute Resolution

```python
# Buyer files dispute
dispute = agent.file_dispute(settlement_id, "Never received goods")

# Add evidence
agent._settlement.add_dispute_evidence(dispute.dispute_id, {"photo": "damage.jpg"})

# Resolution: RESOLVED_BUYER (refund), RESOLVED_SELLER (release), RESOLVED_SPLIT
```

The heartbeat auto-checks for overdue deliveries and sends critical alerts.

## API Endpoints (Gateway Mode)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Agent health status |
| `/identity` | GET | Public identity info |
| `/messages` | POST | Receive message from another agent |
| `/propose` | POST | Receive trade proposal |
| `/peers` | GET | List known peers |
| `/peers` | POST | Register a new peer |
| `/memory` | GET | View learned insights |
| `/ledger` | GET | Transaction history |
| `/skills` | GET | Available skills |
| `/tools` | GET | List available tools |
| `/tools` | POST | Create a new custom tool |
| `/tools/{name}` | POST | Execute a tool by name |
| `/improve` | POST | Trigger self-improvement cycle |
| `/balance` | GET | USDC wallet balance |
| `/settlements` | GET | List active settlements |
| `/delivery/confirm` | POST | Human confirms physical delivery |
| `/delivery/webhook` | POST | External system confirms delivery |
| `/dispute` | POST | File a dispute for a settlement |

## CLI Commands

```bash
incagent serve    # Start agent as persistent daemon
incagent status   # Check running agent's health
incagent peers    # List known peer agents
incagent connect  # Connect a peer to running agent
incagent memory   # View agent's learned memory
```

## LLM Configuration (Optional)

IncAgent works **without any LLM API key**. All negotiation and self-improvement features have rule-based fallback logic built in.

| Mode | Negotiation | Self-Improvement | API Key Required |
|------|-------------|------------------|------------------|
| **Rule-based** (default) | Deterministic price/counter logic | Pattern-based strategy updates | No |
| **LLM-powered** | AI-driven multi-round negotiation | Auto-generates new skills & strategies | Yes |

To enable LLM-powered features, pass config when creating an agent:

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

Or via CLI:

```bash
incagent serve --name "Acme Corp" --role buyer \
    --llm-provider anthropic --llm-api-key sk-ant-...
```

Supported providers: **Anthropic** (`claude-sonnet-4-20250514`) and **OpenAI** (`gpt-4o`).

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

## License

MIT License. See [LICENSE](LICENSE).

## Links

- Website: [incagent.ai](https://incagent.ai)
- X: [@incagentai](https://x.com/incagentai)
- GitHub: [github.com/incagent/incagent](https://github.com/incagent/incagent)
