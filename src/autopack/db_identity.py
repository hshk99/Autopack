"""Database identity and safety utilities.

Provides guardrails to prevent accidental operations on empty/wrong databases:
- Print DB identity banner (URL + file path + mtime + row counts)
- Warn if DB has schema but 0 runs and 0 phases
- Optional --allow-empty-db flag for scripts

Usage in scripts:
    from autopack.db_identity import print_db_identity, check_empty_db_warning

    session = SessionLocal()
    print_db_identity(session)

    # For drain scripts that shouldn't run on empty DB
    if not allow_empty_db:
        check_empty_db_warning(session, script_name="batch_drain_controller")
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from .models import Phase, Run


def _get_sqlite_db_path() -> Optional[Path]:
    """Extract SQLite database file path from DATABASE_URL env var.

    Returns:
        Path to SQLite database file, or None if not using SQLite or no file
    """
    db_url = os.environ.get("DATABASE_URL", "")

    # Handle sqlite:///path/to/file.db
    if db_url.startswith("sqlite:///"):
        file_path = db_url.replace("sqlite:///", "")
        # Handle relative paths
        if not file_path.startswith("/"):
            return Path(file_path).resolve()
        return Path(file_path)

    # Handle sqlite:///:memory:
    if "memory" in db_url:
        return None

    # PostgreSQL or other DB
    return None


def _get_db_file_mtime(db_path: Optional[Path]) -> Optional[str]:
    """Get modification time of database file.

    Returns:
        ISO format timestamp string, or None if file doesn't exist
    """
    if db_path is None or not db_path.exists():
        return None

    mtime = datetime.fromtimestamp(db_path.stat().st_mtime, tz=timezone.utc)
    return mtime.isoformat()


def print_db_identity(session: Session):
    """Print database identity banner for transparency.

    Shows:
    - DATABASE_URL (with sensitive parts masked if needed)
    - SQLite file path (if applicable)
    - File modification time (if applicable)
    - Row counts: runs, phases, llm_usage_events

    Args:
        session: SQLAlchemy database session
    """
    db_url = os.environ.get("DATABASE_URL", "UNKNOWN")
    db_path = _get_sqlite_db_path()
    db_mtime = _get_db_file_mtime(db_path)

    # Count rows
    run_count = session.query(Run).count()
    phase_count = session.query(Phase).count()

    # Try to count llm_usage_events (may not exist in all DBs)
    try:
        from .usage_recorder import LlmUsageEvent

        event_count = session.query(LlmUsageEvent).count()
    except (ImportError, AttributeError, Exception):
        event_count = None

    print("=" * 70)
    print("DATABASE IDENTITY")
    print("=" * 70)
    print(f"DATABASE_URL: {db_url}")

    if db_path:
        print(f"SQLite file: {db_path}")
        if db_mtime:
            print(f"Last modified: {db_mtime}")

    print()
    print("Row counts:")
    print(f"  Runs: {run_count}")
    print(f"  Phases: {phase_count}")

    if event_count is not None:
        print(f"  LLM usage events: {event_count}")

    print("=" * 70)
    print()


def check_empty_db_warning(session: Session, script_name: str, allow_empty: bool = False) -> bool:
    """Check if database is empty and warn/exit if not allowed.

    Args:
        session: SQLAlchemy database session
        script_name: Name of calling script (for error messages)
        allow_empty: If False and DB is empty, exit with error

    Returns:
        True if DB is empty, False if DB has data
    """
    run_count = session.query(Run).count()
    phase_count = session.query(Phase).count()

    is_empty = run_count == 0 and phase_count == 0

    if is_empty:
        print("⚠️  WARNING: DATABASE IS EMPTY")
        print("=" * 70)
        print("The database has schema but no data (0 runs, 0 phases).")
        print()
        print("Possible reasons:")
        print("  1. Fresh database (never seeded)")
        print("  2. Wrong DATABASE_URL environment variable")
        print("  3. Data was deleted or cleared")
        print()
        print("Next steps:")
        print("  1. Check DATABASE_URL is pointing to the correct database")
        print("  2. Seed the database with runs/phases:")
        print("     - Create telemetry run: python scripts/create_telemetry_collection_run.py")
        print("     - Or restore from backup if data was lost")
        print()

        if not allow_empty:
            print(f"ERROR: {script_name} cannot run on an empty database.")
            print()
            print("To bypass this check (if intentional), add --allow-empty-db flag")
            print("=" * 70)
            print()
            sys.exit(1)
        else:
            print(f"Proceeding with {script_name} on empty database (--allow-empty-db flag set)")
            print("=" * 70)
            print()

    return is_empty


def add_empty_db_arg(parser):
    """Add --allow-empty-db argument to argparse parser.

    Convenience function for adding the flag to script argument parsers.

    Args:
        parser: argparse.ArgumentParser instance
    """
    parser.add_argument(
        "--allow-empty-db",
        action="store_true",
        help="Allow operation on empty database (bypass safety check)",
    )
