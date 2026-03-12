"""CLI entry point — incagent init / serve / status / peers / connect."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="incagent",
        description="IncAgent — autonomous AI-to-AI corporate transaction platform",
    )
    sub = parser.add_subparsers(dest="command")

    # ── init ───────────────────────────────────────────────────────────
    init_parser = sub.add_parser("init", help="Initialize a new organization")
    init_parser.add_argument("--name", required=True, help="Organization name")
    init_parser.add_argument("--role", default="buyer", choices=["buyer", "seller", "broker"])
    init_parser.add_argument("--jurisdiction", default="US-DE", help="Legal jurisdiction (e.g. US-DE)")
    init_parser.add_argument("--data-dir", default=None, help="Base data directory (default: ~/.incagent)")
    init_parser.add_argument("--api-key", action="store_true", help="Generate API key during init")

    # ── serve ──────────────────────────────────────────────────────────
    serve_parser = sub.add_parser("serve", help="Start agent as a persistent Gateway daemon")
    serve_parser.add_argument("--name", required=True, help="Organization name (must match init)")
    serve_parser.add_argument("--role", default="buyer", choices=["buyer", "seller", "broker"])
    serve_parser.add_argument("--host", default="0.0.0.0")
    serve_parser.add_argument("--port", type=int, default=8400)
    serve_parser.add_argument("--data-dir", default=None, help="Base data directory (default: ~/.incagent)")
    serve_parser.add_argument("--skills-dir", default=None, help="Skills directory")
    serve_parser.add_argument("--hub-url", default=None, help="Central registry hub URL")
    serve_parser.add_argument("--peer", action="append", default=[], help="Peer agent URL (repeatable)")
    serve_parser.add_argument("--heartbeat-interval", type=float, default=1800, help="Heartbeat interval in seconds")
    serve_parser.add_argument("--no-heartbeat", action="store_true", help="Disable heartbeat")
    serve_parser.add_argument("--autonomous", action="store_true", help="Full autonomous mode (no human approval)")
    serve_parser.add_argument("--industry", action="append", default=[], help="Industry tags (repeatable)")
    serve_parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    # ── status ─────────────────────────────────────────────────────────
    status_parser = sub.add_parser("status", help="Check a running agent's status")
    status_parser.add_argument("--url", default="http://localhost:8400", help="Agent Gateway URL")

    # ── peers ──────────────────────────────────────────────────────────
    peers_parser = sub.add_parser("peers", help="List known peers")
    peers_parser.add_argument("--url", default="http://localhost:8400", help="Agent Gateway URL")

    # ── connect ────────────────────────────────────────────────────────
    connect_parser = sub.add_parser("connect", help="Connect a peer to a running agent")
    connect_parser.add_argument("--url", default="http://localhost:8400", help="Your agent's Gateway URL")
    connect_parser.add_argument("peer_url", help="Peer agent's Gateway URL")

    # ── memory ─────────────────────────────────────────────────────────
    memory_parser = sub.add_parser("memory", help="View agent's learned memory")
    memory_parser.add_argument("--url", default="http://localhost:8400", help="Agent Gateway URL")

    # ── orgs ───────────────────────────────────────────────────────────
    orgs_parser = sub.add_parser("orgs", help="List initialized organizations")
    orgs_parser.add_argument("--data-dir", default=None, help="Base data directory")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "init":
        _init_org(args)
    elif args.command == "serve":
        _serve(args)
    elif args.command == "orgs":
        _list_orgs(args)
    elif args.command in ("status", "peers", "memory"):
        _query(args)
    elif args.command == "connect":
        _connect(args)
    else:
        parser.print_help()


def _init_org(args: argparse.Namespace) -> None:
    """Initialize a new organization."""
    from incagent.identity import init_org

    base_dir = Path(args.data_dir) if args.data_dir else Path.home() / ".incagent"
    identity, kp, data_dir = init_org(
        base_dir, args.name, args.role, args.jurisdiction,
    )

    print(f"""
╔══════════════════════════════════════════════════════╗
║            IncAgent Organization Setup                ║
╠══════════════════════════════════════════════════════╣
║  Organization:  {args.name:<36s} ║
║  Org ID:        {identity.agent_id:<36s} ║
║  Role:          {args.role:<36s} ║
║  Jurisdiction:  {args.jurisdiction:<36s} ║
║  Data Dir:      {str(data_dir):<36s} ║
║  Public Key:    {kp.public_key_hex[:36]:<36s} ║
╚══════════════════════════════════════════════════════╝
""")

    # Directory structure
    print("Directory structure:")
    print(f"  {data_dir}/")
    print(f"    identity.json   ← org identity (persistent)")
    print(f"    key.pem         ← Ed25519 signing key")
    print(f"    ledger.db       ← transaction ledger")
    print(f"    memory.db       ← learning memory")
    print(f"    audit.db        ← security audit log")
    print(f"    skills/         ← skill files")
    print(f"    tools/          ← custom tools")
    print(f"    reports/        ← generated reports")

    # Optionally generate API key
    if args.api_key:
        from incagent.security import generate_api_key
        key = generate_api_key()
        config_file = data_dir / "config.json"
        config = {}
        if config_file.exists():
            config = json.loads(config_file.read_text(encoding="utf-8"))
        config.setdefault("api_keys", []).append(key)
        config_file.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print(f"\n  API Key: {key}")
        print(f"  (saved to {config_file})")
        print(f"  Use: Authorization: Bearer {key}")

    print(f"\nStart the agent:")
    print(f"  incagent serve --name '{args.name}'")


def _serve(args: argparse.Namespace) -> None:
    """Start the agent daemon."""
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    from incagent.agent import IncAgent
    from incagent.heartbeat import HeartbeatConfig
    from incagent.identity import org_data_dir

    base_dir = Path(args.data_dir) if args.data_dir else Path.home() / ".incagent"
    org_dir = org_data_dir(base_dir, args.name)

    # Check if org is initialized
    if not (org_dir / "identity.json").exists():
        print(f"Error: Organization '{args.name}' not initialized.")
        print(f"Run first: incagent init --name '{args.name}'")
        sys.exit(1)

    # Load API keys from org config if available
    security_config: dict = {}
    config_file = org_dir / "config.json"
    if config_file.exists():
        org_config = json.loads(config_file.read_text(encoding="utf-8"))
        if "api_keys" in org_config:
            security_config["api_keys"] = org_config["api_keys"]

    heartbeat_config: HeartbeatConfig | bool = False
    if not args.no_heartbeat:
        heartbeat_config = HeartbeatConfig(
            interval_seconds=args.heartbeat_interval,
        )

    from incagent.identity import _org_id
    oid = _org_id(args.name)

    print(f"""
╔══════════════════════════════════════════════════════╗
║              IncAgent Gateway v0.5.0                  ║
║       Autonomous AI-to-AI Transaction Platform        ║
╠══════════════════════════════════════════════════════╣
║  Agent:     {args.name:<40s} ║
║  Org ID:    {oid:<40s} ║
║  Role:      {args.role:<40s} ║
║  Listen:    {args.host}:{args.port:<34} ║
║  Heartbeat: {"ON" if not args.no_heartbeat else "OFF":<40s} ║
║  Mode:      {"AUTONOMOUS" if args.autonomous else "SUPERVISED":<40s} ║
║  Auth:      {"API KEY" if security_config.get("api_keys") else "DISABLED":<40s} ║
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
        data_dir=base_dir,  # pass base_dir, agent.py handles per-org
        industries=args.industry,
        security=security_config if security_config else None,
    )

    asyncio.run(agent.serve(host=args.host, port=args.port))


def _list_orgs(args: argparse.Namespace) -> None:
    """List all initialized organizations."""
    base_dir = Path(args.data_dir) if args.data_dir else Path.home() / ".incagent"

    if not base_dir.exists():
        print(f"No organizations found at {base_dir}")
        return

    orgs = []
    for d in sorted(base_dir.iterdir()):
        identity_file = d / "identity.json"
        if d.is_dir() and identity_file.exists():
            data = json.loads(identity_file.read_text(encoding="utf-8"))
            # Count DB files
            dbs = list(d.glob("*.db"))
            skills = list((d / "skills").glob("*.md")) if (d / "skills").exists() else []
            tools = list((d / "tools").glob("*.py")) if (d / "tools").exists() else []
            orgs.append({
                "name": data.get("name", "?"),
                "org_id": data.get("agent_id", "?"),
                "role": data.get("role", "?"),
                "jurisdiction": data.get("jurisdiction", "?"),
                "created": data.get("created_at", "?"),
                "databases": len(dbs),
                "skills": len(skills),
                "tools": len(tools),
                "path": str(d),
            })

    if not orgs:
        print(f"No organizations found at {base_dir}")
        print(f"Initialize with: incagent init --name 'My Corp'")
        return

    print(f"Organizations ({len(orgs)}):\n")
    for org in orgs:
        print(f"  {org['name']}")
        print(f"    ID:           {org['org_id']}")
        print(f"    Role:         {org['role']}")
        print(f"    Jurisdiction: {org['jurisdiction']}")
        print(f"    Created:      {org['created']}")
        print(f"    Databases:    {org['databases']}")
        print(f"    Skills:       {org['skills']}")
        print(f"    Tools:        {org['tools']}")
        print(f"    Path:         {org['path']}")
        print()


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
        print(f"Error: Cannot connect — {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
