"""CLI entry point - incagent serve to run a persistent agent daemon."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="incagent",
        description="IncAgent -autonomous AI-to-AI corporate transaction platform",
    )
    sub = parser.add_subparsers(dest="command")

    # ── serve ─────────────────────────────────────────────────────────
    serve_parser = sub.add_parser("serve", help="Start agent as a persistent Gateway daemon")
    serve_parser.add_argument("--name", required=True, help="Agent/company name")
    serve_parser.add_argument("--role", default="buyer", choices=["buyer", "seller", "broker"])
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8400)
    serve_parser.add_argument("--data-dir", default=None, help="Data directory (default: ~/.incagent)")
    serve_parser.add_argument("--skills-dir", default=None, help="Skills directory")
    serve_parser.add_argument("--hub-url", default=None, help="Central registry hub URL")
    serve_parser.add_argument("--peer", action="append", default=[], help="Peer agent URL (repeatable)")
    serve_parser.add_argument("--heartbeat-interval", type=float, default=1800, help="Heartbeat interval in seconds")
    serve_parser.add_argument("--no-heartbeat", action="store_true", help="Disable heartbeat")
    serve_parser.add_argument("--autonomous", action="store_true", help="Full autonomous mode (no human approval)")
    serve_parser.add_argument("--industry", action="append", default=[], help="Industry tags (repeatable)")
    serve_parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    # ── status ────────────────────────────────────────────────────────
    status_parser = sub.add_parser("status", help="Check a running agent's status")
    status_parser.add_argument("--url", default="http://localhost:8400", help="Agent Gateway URL")

    # ── peers ─────────────────────────────────────────────────────────
    peers_parser = sub.add_parser("peers", help="List known peers")
    peers_parser.add_argument("--url", default="http://localhost:8400", help="Agent Gateway URL")

    # ── connect ───────────────────────────────────────────────────────
    connect_parser = sub.add_parser("connect", help="Connect a peer to a running agent")
    connect_parser.add_argument("--url", default="http://localhost:8400", help="Your agent's Gateway URL")
    connect_parser.add_argument("peer_url", help="Peer agent's Gateway URL")

    # ── memory ────────────────────────────────────────────────────────
    memory_parser = sub.add_parser("memory", help="View agent's learned memory")
    memory_parser.add_argument("--url", default="http://localhost:8400", help="Agent Gateway URL")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "serve":
        _serve(args)
    elif args.command in ("status", "peers", "memory"):
        _query(args)
    elif args.command == "connect":
        _connect(args)
    else:
        parser.print_help()


def _serve(args: argparse.Namespace) -> None:
    """Start the agent daemon."""
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    from incagent.agent import IncAgent
    from incagent.heartbeat import HeartbeatConfig

    heartbeat_config: HeartbeatConfig | bool = False
    if not args.no_heartbeat:
        heartbeat_config = HeartbeatConfig(
            interval_seconds=args.heartbeat_interval,
        )

    print(f"""
╔══════════════════════════════════════════════════════╗
║              IncAgent Gateway v0.2.0                 ║
║       Autonomous AI-to-AI Transaction Platform       ║
╠══════════════════════════════════════════════════════╣
║  Agent:     {args.name:<40s} ║
║  Role:      {args.role:<40s} ║
║  Listen:    {args.host}:{args.port:<34} ║
║  Heartbeat: {"ON" if not args.no_heartbeat else "OFF":<40s} ║
║  Mode:      {"AUTONOMOUS" if args.autonomous else "SUPERVISED":<40s} ║
╚══════════════════════════════════════════════════════╝
""")

    agent = IncAgent(
        name=args.name,
        role=args.role,
        host=args.host,
        port=args.port,
        autonomous_mode=args.autonomous,
        heartbeat=heartbeat_config,
        skills_dir=args.skills_dir,
        hub_url=args.hub_url,
        peers=args.peer if args.peer else None,
        data_dir=args.data_dir,
        industries=args.industry,
    )

    asyncio.run(agent.serve(host=args.host, port=args.port))


def _query(args: argparse.Namespace) -> None:
    """Query a running agent."""
    import httpx

    endpoint = {
        "status": "/health",
        "peers": "/peers",
        "memory": "/memory",
    }[args.command]

    try:
        resp = httpx.get(f"{args.url}{endpoint}", timeout=5.0)
        resp.raise_for_status()
        import json
        print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
    except httpx.ConnectError:
        print(f"Error: Cannot connect to agent at {args.url}")
        print("Is the agent running? Start with: incagent serve --name 'My Corp'")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


def _connect(args: argparse.Namespace) -> None:
    """Connect a peer to a running agent."""
    import httpx

    try:
        # First probe the peer to get identity
        peer_resp = httpx.get(f"{args.peer_url}/identity", timeout=5.0)
        peer_resp.raise_for_status()
        peer_info = peer_resp.json()

        # Register peer with our agent
        payload = {
            "agent_id": peer_info["agent_id"],
            "name": peer_info["name"],
            "role": peer_info["role"],
            "url": args.peer_url,
            "public_key_hex": peer_info.get("public_key", ""),
        }
        resp = httpx.post(f"{args.url}/peers", json=payload, timeout=5.0)
        resp.raise_for_status()
        print(f"Connected: {peer_info['name']} ({peer_info['role']}) at {args.peer_url}")
    except httpx.ConnectError as e:
        print(f"Error: Cannot connect -{e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
