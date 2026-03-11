# IncAgent

**The open protocol where AI agents do business.**

IncAgent is an open-source framework for building autonomous AI agents that can negotiate, contract, and transact on behalf of corporations — without human intervention.

## Features

- **Autonomous Negotiation** — AI agents negotiate contract terms using LLMs, within policy-defined boundaries
- **Self-Healing** — Built-in retry, circuit breaker, and fallback mechanisms. Agents recover from errors without human intervention
- **Corporate Identity** — Each agent carries a cryptographically signed corporate identity
- **Transaction Ledger** — Tamper-evident local ledger records every action
- **Human-in-the-Loop** — Optional approval workflows for high-value transactions (configurable thresholds)
- **Open Protocol** — JSON-based messaging spec for agent-to-agent communication

## Quick Start

```bash
pip install incagent
```

```python
from incagent import IncAgent, Contract

# Create two corporate agents
buyer = IncAgent(name="Acme Corp", role="buyer")
seller = IncAgent(name="Widget Inc", role="seller")

# Define a contract
contract = Contract(
    title="Widget Supply Agreement",
    terms={"quantity": 1000, "unit_price_range": (50, 80)},
)

# Agents negotiate autonomously
result = await buyer.negotiate(contract, counterparty=seller)
print(result)
# NegotiationResult(status='agreed', final_price=65, rounds=3)
```

## Architecture

```
┌─────────────┐         ┌─────────────┐
│   Agent A    │◄──JSON──►│   Agent B    │
│  (Buyer)     │         │  (Seller)    │
├─────────────┤         ├─────────────┤
│ Identity     │         │ Identity     │
│ Negotiation  │         │ Negotiation  │
│ Contracts    │         │ Contracts    │
│ Ledger       │         │ Ledger       │
│ Resilience   │         │ Resilience   │
└──────┬──────┘         └──────┬──────┘
       │                       │
       ▼                       ▼
  ┌─────────┐            ┌─────────┐
  │ SQLite  │            │ SQLite  │
  │ Ledger  │            │ Ledger  │
  └─────────┘            └─────────┘
```

## Human Approval Mode

For high-value or sensitive transactions, enable human-in-the-loop:

```python
agent = IncAgent(
    name="Acme Corp",
    approval_threshold=10000,  # Require human approval above $10,000
    approval_method="cli",     # cli | webhook | slack
)
```

## Self-Healing

Agents automatically recover from failures:

```python
agent = IncAgent(
    name="Acme Corp",
    resilience={
        "max_retries": 5,
        "backoff_base": 2.0,
        "circuit_breaker_threshold": 3,
        "fallback_strategy": "cache",
    },
)
```

## Documentation

- [Protocol Specification](docs/protocol-spec.md)
- [Architecture](docs/architecture.md)
- [Quick Start Guide](docs/quickstart.md)

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

## License

MIT License. See [LICENSE](LICENSE) for details.

## Links

- Website: [incagent.ai](https://incagent.ai)
- Twitter/X: [@incagent](https://x.com/incagent)
- GitHub: [github.com/incagent/incagent](https://github.com/incagent/incagent)
