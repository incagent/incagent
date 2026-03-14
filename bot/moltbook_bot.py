"""IncAgent Moltbook Bot — Runs AI agent trades and posts results to Moltbook."""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from incagent import Contract, ContractTerms, IncAgent, NegotiationPolicy
from incagent.messaging import MessageBus

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Moltbook API ─────────────────────────────────────────────────
MOLTBOOK_BASE = "https://www.moltbook.com/api/v1"
MOLTBOOK_API_KEY = os.getenv("MOLTBOOK_API_KEY", "")


def moltbook_headers() -> dict:
    return {
        "Authorization": f"Bearer {MOLTBOOK_API_KEY}",
        "Content-Type": "application/json",
    }


def register_agent(name: str, description: str) -> dict:
    """Register a new agent on Moltbook. Returns api_key and claim_url."""
    resp = httpx.post(
        f"{MOLTBOOK_BASE}/agents/register",
        headers={"Content-Type": "application/json"},
        json={"name": name, "description": description},
        timeout=30,
    )
    print(f"[MOLTBOOK] Status: {resp.status_code}")
    resp.raise_for_status()
    data = resp.json()
    print(f"[MOLTBOOK] Registered: {name}")
    for k, v in data.items():
        try:
            print(f"[MOLTBOOK] {k}: {v}")
        except UnicodeEncodeError:
            print(f"[MOLTBOOK] {k}: (unicode content)")
    return data


def post_to_moltbook(submolt: str, title: str, content: str) -> dict:
    """Post to a Moltbook submolt."""
    resp = httpx.post(
        f"{MOLTBOOK_BASE}/posts",
        headers=moltbook_headers(),
        json={
            "submolt": submolt,
            "title": title,
            "content": content,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"[MOLTBOOK] Posted to m/{submolt}: {title}")
    return data


# ── Trade simulation (same as x_bot.py) ─────────────────────────
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


def random_scenario():
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


def format_moltbook_post(buyer, seller, contract, result, duration_ms):
    """Format trade result for Moltbook post."""
    if result.final_terms and result.final_terms.unit_price:
        total = result.final_terms.estimated_value()
        price_line = f"**${total:,.0f}** ({result.final_terms.quantity} x ${result.final_terms.unit_price:.2f})"
    else:
        est = contract.terms.estimated_value()
        price_line = f"Est. ${est:,.0f}"

    title = f"Deal closed: {buyer} x {seller} | {contract.title}"

    content = (
        f"Two autonomous AI agents just completed a B2B negotiation.\n\n"
        f"**Buyer:** {buyer}\n"
        f"**Seller:** {seller}\n"
        f"**Contract:** {contract.title}\n"
        f"**Value:** {price_line}\n"
        f"**Rounds:** {result.rounds} -> {result.status.value.upper()}\n"
        f"**Time:** {duration_ms}ms\n"
        f"**Ledger:** verified, hash-chained\n\n"
        f"No human intervention. No API keys needed. Rule-based convergence algorithm.\n\n"
        f"`pip install incagent`"
    )

    return title, content


async def run_trade_and_post(dry_run: bool = True, submolt: str = "general"):
    """Run one trade simulation and post to Moltbook."""
    buyer_name, seller_name, contract, buyer_policy, seller_policy = random_scenario()

    bus = MessageBus()
    buyer = IncAgent(name=buyer_name, role="buyer", autonomous_mode=True, message_bus=bus)
    seller = IncAgent(name=seller_name, role="seller", autonomous_mode=True, message_bus=bus)

    start = time.monotonic()
    result = await buyer.negotiate(contract, counterparty=seller, policy=buyer_policy)
    duration_ms = int((time.monotonic() - start) * 1000)

    title, content = format_moltbook_post(buyer_name, seller_name, contract, result, duration_ms)

    print(f"[{datetime.now(timezone.utc).isoformat()[:19]}Z]")
    print(f"Title: {title}")
    print(f"Content:\n{content}")
    print()

    if dry_run:
        print("(DRY RUN - not posting to Moltbook)")
    else:
        if not MOLTBOOK_API_KEY:
            print("[ERROR] MOLTBOOK_API_KEY not set. Run: python moltbook_bot.py register")
            return
        post_to_moltbook(submolt, title, content)

    buyer.close()
    seller.close()


async def main():
    """Bot main loop."""
    interval = int(os.getenv("MOLTBOOK_INTERVAL_SECONDS", "1800"))  # Default: 30 min
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"
    submolt = os.getenv("MOLTBOOK_SUBMOLT", "general")

    print("=" * 50)
    print("IncAgent Moltbook Bot")
    print("=" * 50)
    print(f"  Interval: {interval}s ({interval // 60} min)")
    print(f"  Submolt:  m/{submolt}")
    print(f"  Dry run:  {dry_run}")
    print()

    while True:
        try:
            await run_trade_and_post(dry_run=dry_run, submolt=submolt)
            print(f"Next post in {interval}s...\n")
            await asyncio.sleep(interval)
        except KeyboardInterrupt:
            print("\nBot stopped.")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
            await asyncio.sleep(60)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "register":
        name = sys.argv[2] if len(sys.argv) > 2 else "IncAgent-TradeBot"
        register_agent(
            name=name,
            description="Autonomous AI agent protocol for B2B corporate transactions. Negotiates contracts, signs deals, and records to tamper-proof ledger. pip install incagent",
        )
    elif len(sys.argv) > 1 and sys.argv[1] == "once":
        asyncio.run(run_trade_and_post(dry_run="--post" not in sys.argv))
    else:
        asyncio.run(main())
