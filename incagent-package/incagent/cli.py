"""
CLI — Command-line interface for Incagent

Usage: incagent [command] [options]
"""

import sys
import argparse
from . import __version__
from .dao import DAO
from .mission import Mission
from .governance import SoulDefinition, Governance

def main():
    parser = argparse.ArgumentParser(
        description="Incagent — AI-Operated Corporation Framework"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"incagent {__version__}"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # init command
    init_parser = subparsers.add_parser("init", help="Initialize a new AI corporation")
    init_parser.add_argument("--name", required=True, help="Corporation name")
    init_parser.add_argument("--state", default="Wyoming", help="State of incorporation")
    init_parser.add_argument("--registered-agent", help="Registered agent name/email")
    init_parser.add_argument("--stripe-key", help="Stripe secret key (or use env var)")
    
    # validate command
    validate_parser = subparsers.add_parser("validate", help="Validate DAO configuration")
    validate_parser.add_argument("--config", default="dao.json", help="Config file")
    
    # launch command
    launch_parser = subparsers.add_parser("launch", help="Launch AI corporation")
    launch_parser.add_argument("--name", required=True, help="Corporation name")
    launch_parser.add_argument("--product", required=True, help="First product/service")
    launch_parser.add_argument("--price", type=float, default=29.00, help="Product price")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    if args.command == "init":
        try:
            dao = DAO(
                name=args.name,
                state=args.state,
                stripe_key=args.stripe_key,
                registered_agent=args.registered_agent,
            )
            dao.validate()
            print(f"✓ DAO created: {dao.name}")
            print(f"  State: {dao.state}")
            print(f"  Formed: {dao.formed_date.strftime('%Y-%m-%d')}")
            print("\n" + dao.governance_doc())
        except Exception as e:
            print(f"✗ Error: {e}", file=sys.stderr)
            sys.exit(1)
    
    elif args.command == "launch":
        try:
            dao = DAO(name=args.name)
            mission = Mission(
                description=f"Sell {args.product}",
                first_product=args.product,
                price=args.price,
            )
            mission.validate()
            dao.launch(mission)
            print(f"✓ Launched successfully")
        except Exception as e:
            print(f"✗ Error: {e}", file=sys.stderr)
            sys.exit(1)
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
