"""IncAgent X Bot — Runs AI agent trade simulations and tweets results."""

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

# Add parent dir so we can import incagent
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from incagent import Contract, ContractTerms, IncAgent, NegotiationPolicy
from incagent.messaging import MessageBus

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── X API credentials ───────────────────────────────────────────────
API_KEY = os.getenv("X_API_KEY", "")
API_SECRET = os.getenv("X_API_SECRET", "")
ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET", "")

TWEET_URL = "https://api.twitter.com/2/tweets"

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


def _create_oauth1_header(method: str, url: str, body: str = "") -> dict[str, str]:
    """Build OAuth 1.0a Authorization header (HMAC-SHA1)."""
    import hashlib
    import hmac
    import urllib.parse
    import uuid

    params = {
        "oauth_consumer_key": API_KEY,
        "oauth_nonce": uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": ACCESS_TOKEN,
        "oauth_version": "1.0",
    }

    # Build signature base string
    param_string = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in sorted(params.items())
    )
    base_string = f"{method.upper()}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(param_string, safe='')}"
    signing_key = f"{urllib.parse.quote(API_SECRET, safe='')}&{urllib.parse.quote(ACCESS_TOKEN_SECRET, safe='')}"

    import base64
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()

    params["oauth_signature"] = signature
    auth_header = "OAuth " + ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
        for k, v in sorted(params.items())
    )
    return {"Authorization": auth_header, "Content-Type": "application/json"}


async def post_tweet(text: str) -> dict:
    """Post a tweet using X API v2."""
    headers = _create_oauth1_header("POST", TWEET_URL)
    async with httpx.AsyncClient() as client:
        resp = await client.post(TWEET_URL, headers=headers, json={"text": text})
        resp.raise_for_status()
        return resp.json()


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
        "agreed": "🤝",
        "rejected": "❌",
        "timeout": "⏰",
        "in_progress": "🔄",
    }
    emoji = status_emoji.get(result.status.value, "📊")

    lines = [
        f"{emoji} AI Agent Trade Complete",
        f"",
        f"🏢 {buyer} ↔ {seller}",
        f"📋 {contract.title}",
    ]

    if result.final_terms and result.final_terms.unit_price:
        total = result.final_terms.estimated_value()
        lines.append(f"💰 ${total:,.0f} ({result.final_terms.quantity} × ${result.final_terms.unit_price:.2f})")
    else:
        est = contract.terms.estimated_value()
        lines.append(f"📊 Est. ${est:,.0f}")

    lines.append(f"🔁 {result.rounds} rounds → {result.status.value.upper()}")
    lines.append(f"⚡ {duration_ms}ms")
    lines.append(f"")
    lines.append(f"#IncAgent #AIAgents #AutonomousAI")

    tweet = "\n".join(lines)
    # X limit: 280 chars
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


async def main() -> None:
    """Bot main loop — simulate and tweet periodically."""
    interval = int(os.getenv("TWEET_INTERVAL_SECONDS", "3600"))  # Default: 1 hour
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    print(f"IncAgent X Bot started")
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
                print("(DRY RUN — not posting to X)")
            else:
                if not API_KEY or API_KEY == "REGENERATE_ME":
                    print("ERROR: X API credentials not configured. Set them in .env")
                else:
                    resp = await post_tweet(tweet_text)
                    tweet_id = resp.get("data", {}).get("id", "unknown")
                    print(f"Posted! https://x.com/incagent/status/{tweet_id}")

            print(f"Next tweet in {interval}s...\n")
            await asyncio.sleep(interval)

        except KeyboardInterrupt:
            print("\nBot stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            await asyncio.sleep(60)  # Wait 1 min on error


if __name__ == "__main__":
    asyncio.run(main())
