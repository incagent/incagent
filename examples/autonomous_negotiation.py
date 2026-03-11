"""Autonomous negotiation demo using LLM.

Requires: pip install incagent[llm]
Set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.
"""

import asyncio
import os

from incagent import Contract, ContractTerms, IncAgent, LLMConfig, NegotiationPolicy


async def main() -> None:
    from incagent.messaging import MessageBus

    bus = MessageBus()

    # Configure LLM (defaults to Anthropic Claude)
    llm_config = LLMConfig(
        provider="anthropic",
        model="claude-sonnet-4-20250514",
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )

    buyer = IncAgent(
        name="TechFlow Inc",
        role="buyer",
        autonomous_mode=True,
        llm=llm_config,
        message_bus=bus,
    )
    seller = IncAgent(
        name="DataPipe Corp",
        role="seller",
        autonomous_mode=True,
        llm=llm_config,
        message_bus=bus,
    )

    # Aggressive buyer vs premium seller
    buyer_policy = NegotiationPolicy(
        min_price=100.0,
        max_price=250.0,
        max_rounds=8,
        walk_away_threshold=50000,
    )

    contract = Contract(
        title="Enterprise Data Pipeline License",
        terms=ContractTerms(
            quantity=500,
            unit_price_range=(150, 400),
            currency="USD",
            delivery_days=14,
            payment_terms="net_30",
            custom={"support_tier": "premium", "sla": "99.9%"},
        ),
    )

    print("=" * 60)
    print("AUTONOMOUS NEGOTIATION")
    print("=" * 60)
    print(f"Buyer:  {buyer.name}")
    print(f"Seller: {seller.name}")
    print(f"Contract: {contract.title}")
    print(f"Budget: ${buyer_policy.min_price}-${buyer_policy.max_price}/unit")
    print()

    result = await buyer.negotiate(contract, counterparty=seller, policy=buyer_policy)

    print(f"\nOutcome: {result.status.value.upper()}")
    print(f"Rounds:  {result.rounds}")

    if result.history:
        print("\nNegotiation History:")
        for r in result.history:
            print(f"  Round {r.round_number}: {r.response[:80]}...")

    if result.final_terms:
        print(f"\nAgreed Terms:")
        print(f"  Price: ${result.final_terms.unit_price}/unit")
        print(f"  Quantity: {result.final_terms.quantity}")
        print(f"  Total: ${result.final_terms.estimated_value():,.2f}")
        print(f"  Payment: {result.final_terms.payment_terms}")

    buyer.close()
    seller.close()


if __name__ == "__main__":
    asyncio.run(main())
