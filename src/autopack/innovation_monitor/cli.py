"""
CLI for the AI Innovation Monitor.

Usage:
    python -m autopack.innovation_monitor.cli scan
    python -m autopack.innovation_monitor.cli scan --days 3
    python -m autopack.innovation_monitor.cli weekly-summary
    python -m autopack.innovation_monitor.cli check-config
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .orchestrator import InnovationMonitorOrchestrator, create_orchestrator_from_config
from .email_notifier import check_email_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_scan(args):
    """Run a daily scan."""
    logger.info(f"Running innovation scan (lookback: {args.days} days)")

    orchestrator = create_orchestrator_from_config()
    result = orchestrator.run_sync(lookback_days=args.days)

    print("\n" + "=" * 50)
    print("AI INNOVATION MONITOR - SCAN RESULTS")
    print("=" * 50)
    print(f"Scanned: {result.scanned_count} items")
    print(f"New (unique): {result.new_count} items")
    print(f"Above threshold (>10%): {result.above_threshold_count} items")
    print(f"Notifications sent: {result.notifications_sent}")

    if result.errors:
        print("\nErrors:")
        for error in result.errors:
            print(f"  - {error}")

    print("=" * 50)

    return 0 if not result.errors else 1


def cmd_weekly_summary(args):
    """Send weekly summary email."""
    logger.info("Generating and sending weekly summary")

    orchestrator = create_orchestrator_from_config()
    success = orchestrator.send_weekly_summary()

    if success:
        print("Weekly summary sent successfully!")
        return 0
    else:
        print("Failed to send weekly summary. Check email configuration.")
        return 1


def cmd_check_config(args):
    """Check configuration status."""
    print("\n" + "=" * 50)
    print("AI INNOVATION MONITOR - CONFIGURATION STATUS")
    print("=" * 50)

    # Check email configuration
    email_status = check_email_config()
    print("\nEmail Configuration:")
    for key, value in email_status.items():
        status = "✓" if value else "✗"
        print(f"  {status} {key}")

    # Check orchestrator initialization
    print("\nOrchestrator:")
    try:
        orchestrator = create_orchestrator_from_config()
        print(f"  ✓ Initialized with {len(orchestrator.scrapers)} scrapers")
        for scraper in orchestrator.scrapers:
            print(f"    - {scraper.source_name}")
    except Exception as e:
        print(f"  ✗ Failed to initialize: {e}")

    print("=" * 50)

    return 0 if email_status["configured"] else 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AI Innovation Monitor CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m autopack.innovation_monitor.cli scan
  python -m autopack.innovation_monitor.cli scan --days 3
  python -m autopack.innovation_monitor.cli weekly-summary
  python -m autopack.innovation_monitor.cli check-config
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # scan command
    scan_parser = subparsers.add_parser("scan", help="Run innovation scan")
    scan_parser.add_argument(
        "--days",
        "-d",
        type=int,
        default=1,
        help="Days to look back (default: 1)",
    )
    scan_parser.set_defaults(func=cmd_scan)

    # weekly-summary command
    summary_parser = subparsers.add_parser(
        "weekly-summary",
        help="Send weekly summary email",
    )
    summary_parser.set_defaults(func=cmd_weekly_summary)

    # check-config command
    config_parser = subparsers.add_parser(
        "check-config",
        help="Check configuration status",
    )
    config_parser.set_defaults(func=cmd_check_config)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
