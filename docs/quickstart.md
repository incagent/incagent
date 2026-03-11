# Quick Start Guide

## Installation

```bash
pip install incagent
```

For LLM-powered negotiation:

```bash
pip install incagent[llm]
```

## Your First Trade

```python
import asyncio
from incagent import IncAgent, Contract, ContractTerms, NegotiationPolicy
from incagent.messaging import MessageBus

async def main():
    bus = MessageBus()

    # Create two agents
    buyer = IncAgent(
        name="Acme Corp",
        role="buyer",
        autonomous_mode=True,
        message_bus=bus,
    )
    seller = IncAgent(
        name="Widget Inc",
        role="seller",
        autonomous_mode=True,
        message_bus=bus,
    )

    # Define contract terms
    contract = Contract(
        title="Widget Supply Agreement",
        terms=ContractTerms(
            quantity=1000,
            unit_price_range=(50, 80),
        ),
    )

    # Set negotiation boundaries
    policy = NegotiationPolicy(
        min_price=40.0,
        max_price=75.0,
        max_rounds=5,
    )

    # Negotiate!
    result = await buyer.negotiate(contract, counterparty=seller, policy=policy)
    print(f"Result: {result.status.value}, Rounds: {result.rounds}")

    buyer.close()
    seller.close()

asyncio.run(main())
```

## Human Approval Mode

```python
agent = IncAgent(
    name="Acme Corp",
    approval_threshold=10000.0,  # Require approval above $10k
    approval_method="cli",       # cli | webhook | slack
)
```

## Self-Healing Configuration

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

## Check Agent Health

```python
status = agent.health_status()
# {'agent_id': '...', 'state': 'idle', 'circuit_breaker': 'closed', 'ledger_valid': True}
```

## Verify Ledger Integrity

```python
assert agent.verify_ledger()  # True if chain is intact
```

## Next Steps

- Read the [Protocol Specification](protocol-spec.md)
- See [examples/](../examples/) for more demos
- Read the [Architecture Guide](architecture.md)
