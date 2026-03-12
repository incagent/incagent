"""Demo: Autonomous Agent Network

Starts 3 agents as Gateway daemons, they discover each other
and autonomously negotiate trades via Heartbeat.

Usage:
    # Terminal 1 (Buyer):
    incagent serve --name "Acme Corp" --role buyer --port 8401 \
        --peer http://localhost:8402 --peer http://localhost:8403 \
        --autonomous --heartbeat-interval 30 --industry "Cloud Computing"

    # Terminal 2 (Seller 1):
    incagent serve --name "CloudPeak" --role seller --port 8402 \
        --peer http://localhost:8401 \
        --autonomous --heartbeat-interval 30 --industry "Cloud Computing"

    # Terminal 3 (Seller 2):
    incagent serve --name "DataForge" --role seller --port 8403 \
        --peer http://localhost:8401 \
        --autonomous --heartbeat-interval 30 --industry "AI/ML Infrastructure"

The agents will:
1. Discover each other via peer probing
2. Heartbeat every 30s to check for trade opportunities
3. Auto-negotiate contracts with complementary partners
4. Learn from each trade to optimize future pricing
5. Record everything in tamper-evident ledger

Monitor via API:
    curl http://localhost:8401/health
    curl http://localhost:8401/peers
    curl http://localhost:8401/memory
    curl http://localhost:8401/ledger
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from incagent import IncAgent, HeartbeatConfig


async def main():
    """Run a local multi-agent network for testing."""
    print("Starting 3-agent autonomous network...\n")

    # Shared skills directory
    skills_dir = Path(__file__).resolve().parent.parent / "skills"

    # Create agents with fast heartbeat for demo
    buyer = IncAgent(
        name="Acme Corp",
        role="buyer",
        port=8401,
        autonomous_mode=True,
        heartbeat=HeartbeatConfig(interval_seconds=15, jitter_seconds=5),
        skills_dir=skills_dir,
        industries=["Cloud Computing", "AI/ML Infrastructure"],
        data_dir=Path("/tmp/incagent-demo/acme"),
    )

    seller1 = IncAgent(
        name="CloudPeak",
        role="seller",
        port=8402,
        autonomous_mode=True,
        heartbeat=HeartbeatConfig(interval_seconds=15, jitter_seconds=5),
        skills_dir=skills_dir,
        industries=["Cloud Computing"],
        data_dir=Path("/tmp/incagent-demo/cloudpeak"),
    )

    seller2 = IncAgent(
        name="DataForge",
        role="seller",
        port=8403,
        autonomous_mode=True,
        heartbeat=HeartbeatConfig(interval_seconds=15, jitter_seconds=5),
        skills_dir=skills_dir,
        industries=["AI/ML Infrastructure"],
        data_dir=Path("/tmp/incagent-demo/dataforge"),
    )

    # Start all agents as Gateway daemons
    try:
        await asyncio.gather(
            buyer.serve(port=8401),
            seller1.serve(port=8402),
            seller2.serve(port=8403),
        )
    except KeyboardInterrupt:
        print("\nShutting down agents...")
        buyer.close()
        seller1.close()
        seller2.close()


if __name__ == "__main__":
    asyncio.run(main())
