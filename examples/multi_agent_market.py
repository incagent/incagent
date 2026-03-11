"""Multi-agent marketplace demo.

Multiple buyers and sellers compete in an open market.
"""

import asyncio
import random

from incagent import Contract, ContractTerms, IncAgent, NegotiationPolicy
from incagent.messaging import MessageBus


async def main() -> None:
    bus = MessageBus()

    # Create multiple agents
    buyers = [
        IncAgent(name=f"Buyer-{i}", role="buyer", autonomous_mode=True, message_bus=bus)
        for i in range(3)
    ]
    sellers = [
        IncAgent(name=f"Seller-{i}", role="seller", autonomous_mode=True, message_bus=bus)
        for i in range(2)
    ]

    print(f"Market: {len(buyers)} buyers, {len(sellers)} sellers")
    print("=" * 60)

    # Each buyer tries to negotiate with a random seller
    tasks = []
    for buyer in buyers:
        seller = random.choice(sellers)
        contract = Contract(
            title=f"Supply Agreement ({buyer.name} <-> {seller.name})",
            terms=ContractTerms(
                quantity=random.randint(100, 1000),
                unit_price_range=(30.0, 80.0),
                currency="USD",
            ),
        )
        policy = NegotiationPolicy(
            min_price=25.0,
            max_price=75.0,
            max_rounds=5,
        )
        tasks.append((buyer, seller, contract, policy))

    # Run negotiations concurrently
    results = await asyncio.gather(*[
        buyer.negotiate(contract, counterparty=seller, policy=policy)
        for buyer, seller, contract, policy in tasks
    ])

    # Report results
    print("\nResults:")
    for (buyer, seller, contract, _), result in zip(tasks, results):
        status = result.status.value.upper()
        value = f"${result.final_terms.estimated_value():,.2f}" if result.final_terms else "N/A"
        print(f"  {buyer.name} <-> {seller.name}: {status} ({value})")

    # Aggregate stats
    agreed = sum(1 for r in results if r.status.value == "agreed")
    print(f"\nDeals closed: {agreed}/{len(results)}")

    # Cleanup
    for agent in buyers + sellers:
        agent.close()


if __name__ == "__main__":
    asyncio.run(main())
