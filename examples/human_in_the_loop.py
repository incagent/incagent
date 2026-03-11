"""Human-in-the-loop approval demo.

High-value transactions require human approval via CLI prompt.
"""

import asyncio

from incagent import Contract, ContractTerms, IncAgent, NegotiationPolicy


async def main() -> None:
    from incagent.messaging import MessageBus

    bus = MessageBus()

    # Human approval required for transactions > $5,000
    buyer = IncAgent(
        name="Acme Corp",
        role="buyer",
        approval_threshold=5000.0,
        approval_method="cli",
        message_bus=bus,
    )
    seller = IncAgent(
        name="MegaSupply Co",
        role="seller",
        autonomous_mode=True,
        message_bus=bus,
    )

    policy = NegotiationPolicy(
        min_price=10.0,
        max_price=50.0,
        max_rounds=3,
    )

    # Small contract — auto-approved
    small_contract = Contract(
        title="Office Supplies (Small)",
        terms=ContractTerms(quantity=10, unit_price=25.0),
    )
    print("--- Small Contract ($250) ---")
    result = await buyer.negotiate(small_contract, counterparty=seller, policy=policy)
    print(f"Result: {result.status.value} (should auto-approve)\n")

    # Large contract — requires human approval
    large_contract = Contract(
        title="Server Equipment (Large)",
        terms=ContractTerms(quantity=500, unit_price=40.0),
    )
    print("--- Large Contract ($20,000) ---")
    print("This will prompt for human approval...")
    result = await buyer.negotiate(large_contract, counterparty=seller, policy=policy)
    print(f"Result: {result.status.value}\n")

    buyer.close()
    seller.close()


if __name__ == "__main__":
    asyncio.run(main())
