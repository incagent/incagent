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
      │  Ledger (hash-chain) │           │  Ledger (hash-chain) │
      └──────────┬───────────┘           └──────────┬───────────┘
                 │                                  │
                 ▼                                  ▼
          ┌─────────────┐                    ┌─────────────┐
          │  EVM Chain  │◄───── USDC ───────►│  EVM Chain  │
          │  (Escrow)   │                    │  (Escrow)   │
          └─────────────┘                    └─────────────┘
```

## Core Components

| Component | Description |
|-----------|-------------|
| **Gateway** | Persistent HTTP server. Always-on agent runtime with REST API |
| **Heartbeat** | Self-activates every N minutes. Discovers partners, evaluates opportunities, initiates trades |
| **Memory** | SQLite-backed learning. Tracks partner reliability, optimal pricing, successful strategies |
| **Skills** | Markdown-defined plugins. Add trade types, industries, negotiation strategies without code |
| **Registry** | Peer discovery. Agents find each other via probing, announcements, or central hub |
| **Negotiation** | LLM-powered autonomous negotiation with rule-based fallback |
| **Ledger** | Tamper-evident, hash-chained transaction log. Cryptographically verifiable |
| **Identity** | Ed25519 keypair. Signed messages, signed contracts |

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

## CLI Commands

```bash
incagent serve    # Start agent as persistent daemon
incagent status   # Check running agent's health
incagent peers    # List known peer agents
incagent connect  # Connect a peer to running agent
incagent memory   # View agent's learned memory
```

## Installation

```bash
pip install incagent

# With LLM support (for AI-powered negotiation)
pip install incagent[llm]

# Development
pip install incagent[dev]
```

## License

MIT License. See [LICENSE](LICENSE).

## Links

- Website: [incagent.ai](https://incagent.ai)
- X: [@incagentai](https://x.com/incagentai)
- GitHub: [github.com/incagent/incagent](https://github.com/incagent/incagent)
