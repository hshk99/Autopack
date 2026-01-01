"""Add ab_test_results table - BUILD-146 P12

Creates table for storing A/B test comparison results with strict validity checks.

IMPORTANT: This is a manual migration script, NOT Alembic.

Run with:
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="..." python scripts/migrations/add_ab_test_results.py

Supports both PostgreSQL and SQLite.
"""

import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autopack.database import engine, Base
from autopack.models import ABTestResult


def get_database_url() -> str:
    """Get DATABASE_URL from environment with helpful error."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("\n" + "="*80, file=sys.stderr)
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print("\nSet DATABASE_URL before running:\n", file=sys.stderr)
        print("  # PowerShell (Postgres production):", file=sys.stderr)
        print("  $env:DATABASE_URL=\"postgresql://autopack:autopack@localhost:5432/autopack\"", file=sys.stderr)
        print("  python scripts/migrations/add_ab_test_results.py\n", file=sys.stderr)
        print("  # PowerShell (SQLite dev/test):", file=sys.stderr)
        print("  $env:DATABASE_URL=\"sqlite:///autopack.db\"", file=sys.stderr)
        print("  python scripts/migrations/add_ab_test_results.py\n", file=sys.stderr)
        sys.exit(1)
    return db_url


def table_exists(table_name: str) -> bool:
    """Check if table already exists.

    Args:
        table_name: Name of table to check

    Returns:
        True if table exists, False otherwise
    """
    from sqlalchemy import inspect

    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def migrate():
    """Create ab_test_results table.

    BUILD-146 P12: Stores A/B test comparison results with strict validity checks.
    """
    print("BUILD-146 P12: A/B Test Results Table Migration")
    print("="*80)
    print()

    # Get database connection
    db_url = get_database_url()
    print(f"Database: {db_url}")
    print()

    # Check if table already exists
    if table_exists("ab_test_results"):
        print("✓ Table 'ab_test_results' already exists")
        print()
        print("Migration is idempotent - no changes needed")
        return

    print("Creating table: ab_test_results")
    print()

    # Create table using SQLAlchemy model
    try:
        ABTestResult.__table__.create(engine, checkfirst=True)
        print("✅ Successfully created table: ab_test_results")
        print()

        # Verify table structure
        from sqlalchemy import inspect
        inspector = inspect(engine)
        columns = inspector.get_columns("ab_test_results")

        print("Table columns:")
        for col in columns:
            col_type = str(col["type"])
            nullable = "NULL" if col["nullable"] else "NOT NULL"
            print(f"  - {col['name']}: {col_type} {nullable}")

        print()

        # Check indexes
        indexes = inspector.get_indexes("ab_test_results")
        if indexes:
            print("Table indexes:")
            for idx in indexes:
                print(f"  - {idx['name']}: {idx['column_names']}")
        else:
            print("No indexes created (will be added by add_performance_indexes.py)")

        print()
        print("✅ Migration completed successfully")

    except Exception as e:
        print(f"❌ Error creating table: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    migrate()
