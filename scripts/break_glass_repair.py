#!/usr/bin/env python
"""
Break-glass database repair CLI tool.

Usage:
    python scripts/break_glass_repair.py diagnose
    python scripts/break_glass_repair.py repair
    python scripts/break_glass_repair.py repair --auto-approve

Per BUILD-130 Phase 1: Break-Glass Repair CLI.
"""

import sys
import os
import argparse

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from autopack.break_glass_repair import BreakGlassRepair
from autopack.config import get_database_url
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(
        description="Break-glass database repair tool for schema violations"
    )

    parser.add_argument(
        "command",
        choices=["diagnose", "repair"],
        help="Command to run: diagnose (read-only) or repair (write)",
    )

    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve all repairs without confirmation (use with caution!)",
    )

    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Database URL (default: from DATABASE_URL env var or config)",
    )

    args = parser.parse_args()

    # Get database URL
    database_url = args.database_url or get_database_url()

    if not database_url:
        print(
            "❌ Error: No database URL specified. Set DATABASE_URL environment variable or use --database-url"
        )
        return 1

    print(f"Using database: {database_url}\n")

    # Create repair tool
    repair_tool = BreakGlassRepair(database_url)

    if args.command == "diagnose":
        # Run diagnostics only
        print("Running diagnostic scan (read-only)...\n")
        result = repair_tool.diagnose()

        if result.is_valid:
            print("\n✅ Database schema is valid - no issues found!")
            return 0
        else:
            print(f"\n❌ Found {len(result.errors)} schema violations")
            print("\nTo fix these issues, run:")
            print("  python scripts/break_glass_repair.py repair")
            return 1

    elif args.command == "repair":
        # Run diagnostics first
        print("Running diagnostic scan...\n")
        result = repair_tool.diagnose()

        if result.is_valid:
            print("\n✅ Database schema is valid - no repairs needed!")
            return 0

        # Apply repairs
        print("\n" + "=" * 80)
        print("APPLYING REPAIRS")
        print("=" * 80 + "\n")

        if args.auto_approve:
            print("⚠️  AUTO-APPROVE MODE: All repairs will be applied without confirmation\n")
        else:
            print("You will be asked to confirm each repair.\n")

        success = repair_tool.repair(result, auto_approve=args.auto_approve)

        if success:
            print("\n✅ All repairs completed successfully!")
            print("\nRe-running diagnostics to verify...")
            verify_result = repair_tool.diagnose()

            if verify_result.is_valid:
                print("\n✅ Database schema validated - all issues resolved!")
                return 0
            else:
                print(
                    f"\n⚠️  {len(verify_result.errors)} issues remain - may need manual intervention"
                )
                return 1
        else:
            print("\n❌ Some repairs failed - check logs above")
            return 1


if __name__ == "__main__":
    sys.exit(main())
