"""IncAgent X Bot — Runs AI agent trade simulations and tweets results."""

from __future__ import annotations

import asyncio
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import tweepy
from dotenv import load_dotenv

# Add parent dir so we can import incagent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from incagent import Contract, ContractTerms, IncAgent, NegotiationPolicy
from incagent.messaging import MessageBus

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── X API client ────────────────────────────────────────────────────
def _get_client() -> tweepy.Client:
    return tweepy.Client(
        consumer_key=os.getenv("X_API_KEY"),
        consumer_secret=os.getenv("X_API_SECRET"),
        access_token=os.getenv("X_ACCESS_TOKEN"),
        access_token_secret=os.getenv("X_ACCESS_TOKEN_SECRET"),
    )

# ── Company name pools ──────────────────────────────────────────────
BUYER_NAMES = [
    "Acme Corp", "NovaTech", "Zenith AI", "Lumin Labs", "Cobalt Industries",
    "Apex Digital", "Vertex Systems", "Helix Corp", "Prism Dynamics", "Ion Forge",
    "Quantum Ventures", "Atlas Global", "Nimbus AI", "Solace Tech", "Ember Corp",
]

SELLER_NAMES = [
    "Widget Inc", "SupplyChain AI", "DataForge", "CloudPeak", "SteelBridge",
    "OmniParts", "NexGen Supply", "TrueSource", "PivotWare", "ClearPath",
    "SilkRoute", "IronClad Systems", "Beacon Supply", "CoreLink", "ArcLine",
]

PRODUCT_CATEGORIES = [
    ("AI Compute Credits", "credits", 0.5, 5.0, 1000, 50000),
    ("GPU Cluster Hours", "hours", 10, 80, 100, 2000),
    ("Data Pipeline Licenses", "licenses", 500, 3000, 5, 50),
    ("Edge Inference Nodes", "units", 200, 1500, 10, 100),
    ("ML Model Training Slots", "slots", 50, 500, 20, 500),
    ("API Gateway Bandwidth", "TB", 2, 20, 100, 5000),
    ("Vector DB Storage", "GB", 0.1, 2.0, 500, 10000),
    ("Synthetic Data Packs", "packs", 100, 800, 10, 200),
]


def random_scenario() -> tuple[str, str, Contract, NegotiationPolicy, NegotiationPolicy]:
    """Generate a random trade scenario."""
    buyer_name = random.choice(BUYER_NAMES)
    seller_name = random.choice([s for s in SELLER_NAMES if s != buyer_name])

    product, unit, price_lo, price_hi, qty_lo, qty_hi = random.choice(PRODUCT_CATEGORIES)
    quantity = random.randint(qty_lo, qty_hi)
    mid_price = (price_lo + price_hi) / 2

    contract = Contract(
        title=f"{product} Supply Agreement",
        terms=ContractTerms(
            quantity=quantity,
            unit_price_range=(round(price_lo, 2), round(price_hi, 2)),
            currency="USD",
            delivery_days=random.choice([7, 14, 30, 60]),
            payment_terms=random.choice(["net_30", "net_60", "prepaid"]),
        ),
    )

    buyer_policy = NegotiationPolicy(
        min_price=round(price_lo * 0.8, 2),
        max_price=round(mid_price * 1.1, 2),
        min_quantity=qty_lo,
        max_quantity=qty_hi,
        max_rounds=random.randint(3, 7),
    )
    seller_policy = NegotiationPolicy(
        min_price=round(mid_price * 0.9, 2),
        max_price=round(price_hi * 1.2, 2),
        min_quantity=qty_lo,
        max_quantity=qty_hi,
        max_rounds=random.randint(3, 7),
    )
    return buyer_name, seller_name, contract, buyer_policy, seller_policy


def format_tweet(
    buyer: str,
    seller: str,
    contract: Contract,
    result,
    duration_ms: int,
) -> str:
    """Format a trade result into a tweet."""
    status_emoji = {
        "agreed": "\U0001f91d",
        "rejected": "\u274c",
        "timeout": "\u23f0",
        "in_progress": "\U0001f504",
    }
    emoji = status_emoji.get(result.status.value, "\U0001f4ca")

    lines = [
        f"{emoji} AI Agent Trade Complete",
        "",
        f"\U0001f3e2 {buyer} \u2194 {seller}",
        f"\U0001f4cb {contract.title}",
    ]

    if result.final_terms and result.final_terms.unit_price:
        total = result.final_terms.estimated_value()
        lines.append(f"\U0001f4b0 ${total:,.0f} ({result.final_terms.quantity} \u00d7 ${result.final_terms.unit_price:.2f})")
    else:
        est = contract.terms.estimated_value()
        lines.append(f"\U0001f4ca Est. ${est:,.0f}")

    lines.append(f"\U0001f501 {result.rounds} rounds \u2192 {result.status.value.upper()}")
    lines.append(f"\u26a1 {duration_ms}ms")
    lines.append("")
    lines.append("#IncAgent #AIAgents #AutonomousAI")

    tweet = "\n".join(lines)
    if len(tweet) > 280:
        tweet = tweet[:277] + "..."
    return tweet


async def run_simulation() -> str:
    """Run one trade simulation and return formatted tweet text."""
    buyer_name, seller_name, contract, buyer_policy, seller_policy = random_scenario()

    bus = MessageBus()
    buyer = IncAgent(name=buyer_name, role="buyer", autonomous_mode=True, message_bus=bus)
    seller = IncAgent(name=seller_name, role="seller", autonomous_mode=True, message_bus=bus)

    start = time.monotonic()
    result = await buyer.negotiate(contract, counterparty=seller, policy=buyer_policy)
    duration_ms = int((time.monotonic() - start) * 1000)

    tweet_text = format_tweet(buyer_name, seller_name, contract, result, duration_ms)

    buyer.close()
    seller.close()

    return tweet_text


def post_tweet(text: str) -> str:
    """Post a tweet and return the tweet URL."""
    client = _get_client()
    resp = client.create_tweet(text=text)
    tweet_id = resp.data["id"]
    return f"https://x.com/incagentai/status/{tweet_id}"


async def main() -> None:
    """Bot main loop — simulate and tweet periodically."""
    interval = int(os.getenv("TWEET_INTERVAL_SECONDS", "3600"))  # Default: 1 hour
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    print("IncAgent X Bot started")
    print(f"  Interval: {interval}s")
    print(f"  Dry run:  {dry_run}")
    print()

    while True:
        try:
            tweet_text = await run_simulation()
            print(f"[{datetime.now(timezone.utc).isoformat()[:19]}Z] Generated tweet:")
            print(tweet_text)
            print()

            if dry_run:
                print("(DRY RUN \u2014 not posting to X)")
            else:
                url = post_tweet(tweet_text)
                print(f"Posted! {url}")

            print(f"Next tweet in {interval}s...\n")
            await asyncio.sleep(interval)

        except KeyboardInterrupt:
            print("\nBot stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(main())
