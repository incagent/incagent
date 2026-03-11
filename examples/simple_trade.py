"""Simple trade between two AI agents — no LLM required."""

import asyncio

from incagent import Contract, ContractTerms, IncAgent, NegotiationPolicy


async def main() -> None:
    # Create a shared message bus for local communication
    from incagent.messaging import MessageBus

    bus = MessageBus()

    # Create two corporate agents
    buyer = IncAgent(
        name="Acme Corp",
        role="buyer",
        autonomous_mode=True,  # No human approval needed
        message_bus=bus,
    )
    seller = IncAgent(
        name="Widget Inc",
        role="seller",
        autonomous_mode=True,
        message_bus=bus,
    )

    # Set negotiation policies
    buyer_policy = NegotiationPolicy(
        min_price=40.0,
        max_price=70.0,
        min_quantity=500,
        max_quantity=2000,
        max_rounds=5,
    )
    seller_policy = NegotiationPolicy(
        min_price=55.0,
        max_price=100.0,
        min_quantity=100,
        max_quantity=5000,
        max_rounds=5,
    )

    # Define a contract
    contract = Contract(
        title="Widget Supply Agreement Q2 2026",
        terms=ContractTerms(
            quantity=1000,
            unit_price_range=(50, 80),
            currency="USD",
            delivery_days=30,
            payment_terms="net_30",
        ),
    )

    print(f"Buyer:  {buyer.name} [{buyer.identity.fingerprint()}]")
    print(f"Seller: {seller.name} [{seller.identity.fingerprint()}]")
    print(f"Contract: {contract.title}")
    print(f"Terms: {contract.terms.quantity} units @ ${contract.terms.unit_price_range}")
    print()

    # Negotiate
    result = await buyer.negotiate(contract, counterparty=seller, policy=buyer_policy)

    print(f"\nResult: {result.status.value}")
    print(f"Rounds: {result.rounds}")
    if result.final_terms:
        print(f"Final price: ${result.final_terms.unit_price}")
        print(f"Total value: ${result.final_terms.estimated_value():,.2f}")
    if result.reason:
        print(f"Reason: {result.reason}")

    # Show ledger
    print(f"\nBuyer ledger ({len(buyer.get_ledger_entries())} entries):")
    for entry in buyer.get_ledger_entries(limit=5):
        print(f"  [{entry['action']}] {entry['timestamp'][:19]}")

    # Health check
    print(f"\nBuyer health: {buyer.health_status()}")
    print(f"Ledger integrity: {'OK' if buyer.verify_ledger() else 'CORRUPTED'}")

    # Cleanup
    buyer.close()
    seller.close()


if __name__ == "__main__":
    asyncio.run(main())
