"""
BUILD-144 P0.3: Database Migration - Add total_tokens column to llm_usage_events

Adds total_tokens column to llm_usage_events table to fix total-only recording semantics.

Background:
- BUILD-144 P0 eliminated heuristic token splits and introduced total-only recording
- P0.1/P0.2 made prompt_tokens and completion_tokens nullable and added NULL-safe dashboard aggregation
- However, dashboard treated NULL as 0, causing total-only events to under-report totals
- P0.4 adds explicit total_tokens column (always populated) for accurate totals

Schema changes:
- llm_usage_events.total_tokens: INTEGER NOT NULL DEFAULT 0 (always populated)
- Backfills existing rows: total_tokens = COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)

This migration is idempotent and can be run multiple times safely.

Usage:
    # SQLite (default):
    python scripts/migrations/add_total_tokens_build144.py upgrade

    # PostgreSQL:
    DATABASE_URL="postgresql://..." python scripts/migrations/add_total_tokens_build144.py upgrade

    # Downgrade (remove column):
    python scripts/migrations/add_total_tokens_build144.py downgrade
"""

import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


def get_database_url() -> str:
    """Get DATABASE_URL from environment (REQUIRED - no default)

    BUILD-146 P4 Ops: Migration scripts must target explicit DATABASE_URL to prevent
    accidentally running migrations on SQLite when production uses Postgres.

    Set DATABASE_URL before running:
        # PowerShell (Postgres production):
        $env:DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"
        python scripts/migrations/add_total_tokens_build144.py upgrade

        # PowerShell (SQLite dev/test - explicit opt-in):
        $env:DATABASE_URL="sqlite:///autopack.db"
        python scripts/migrations/add_total_tokens_build144.py upgrade
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("\n" + "=" * 80, file=sys.stderr)
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(
            "\nMigration scripts require explicit DATABASE_URL to prevent footguns.",
            file=sys.stderr,
        )
        print("Production uses Postgres; SQLite is only for dev/test.\n", file=sys.stderr)
        print("Set DATABASE_URL before running:\n", file=sys.stderr)
        print("  # PowerShell (Postgres production):", file=sys.stderr)
        print(
            '  $env:DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"',
            file=sys.stderr,
        )
        print("  python scripts/migrations/add_total_tokens_build144.py upgrade\n", file=sys.stderr)
        print("  # PowerShell (SQLite dev/test - explicit opt-in):", file=sys.stderr)
        print('  $env:DATABASE_URL="sqlite:///autopack.db"', file=sys.stderr)
        print("  python scripts/migrations/add_total_tokens_build144.py upgrade\n", file=sys.stderr)
        sys.exit(1)
    return db_url


def check_column_exists(engine: Engine, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    try:
        inspector = inspect(engine)
        columns = [col["name"] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False


def check_table_exists(engine: Engine, table_name: str) -> bool:
    """Check if a table exists"""
    try:
        inspector = inspect(engine)
        return table_name in inspector.get_table_names()
    except Exception:
        return False


def upgrade(engine: Engine) -> None:
    """Add total_tokens column to llm_usage_events table"""
    print("=" * 80)
    print("BUILD-144 P0.3: Add total_tokens Column to llm_usage_events")
    print("=" * 80)

    # Check if table exists
    if not check_table_exists(engine, "llm_usage_events"):
        print("[!]️  Table 'llm_usage_events' does not exist")
        print("    This is expected for fresh databases - ORM will create it with total_tokens")
        return

    with engine.begin() as conn:
        # Check if column already exists
        if check_column_exists(engine, "llm_usage_events", "total_tokens"):
            print("[x] Column 'total_tokens' already exists, skipping column creation")

            # Verify backfill for existing rows with total_tokens=0
            result = conn.execute(
                text("""
                SELECT COUNT(*) as count FROM llm_usage_events
                WHERE total_tokens = 0
                AND (prompt_tokens IS NOT NULL OR completion_tokens IS NOT NULL)
            """)
            )
            row = result.fetchone()
            zero_total_count = row[0] if row else 0

            if zero_total_count > 0:
                print(f"[!]️  Found {zero_total_count} rows with total_tokens=0 but non-NULL splits")
                print("    Running backfill to fix these rows...")
                conn.execute(
                    text("""
                    UPDATE llm_usage_events
                    SET total_tokens = COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)
                    WHERE total_tokens = 0
                    AND (prompt_tokens IS NOT NULL OR completion_tokens IS NOT NULL)
                """)
                )
                print(f"[x] Backfilled {zero_total_count} rows with correct total_tokens")
            else:
                print("[x] All rows have correct total_tokens values")

            return

        print("\n[1/3] Adding column: total_tokens (INTEGER NOT NULL DEFAULT 0)")
        print("      Purpose: Always record total tokens to avoid under-reporting")
        conn.execute(
            text("""
            ALTER TABLE llm_usage_events
            ADD COLUMN total_tokens INTEGER NOT NULL DEFAULT 0
        """)
        )
        print("      [x] Column 'total_tokens' added")

        print("\n[2/3] Backfilling total_tokens for existing rows")
        print(
            "      Formula: total_tokens = COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)"
        )
        result = conn.execute(
            text("""
            UPDATE llm_usage_events
            SET total_tokens = COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)
        """)
        )
        rows_updated = result.rowcount
        print(f"      [x] Backfilled {rows_updated} rows")

        print("\n[3/3] Verification")
        # Count rows by token pattern
        result = conn.execute(
            text("""
            SELECT
                COUNT(*) as total_rows,
                SUM(CASE WHEN prompt_tokens IS NOT NULL AND completion_tokens IS NOT NULL THEN 1 ELSE 0 END) as exact_splits,
                SUM(CASE WHEN prompt_tokens IS NULL AND completion_tokens IS NULL THEN 1 ELSE 0 END) as total_only,
                SUM(total_tokens) as total_tokens_sum
            FROM llm_usage_events
        """)
        )
        row = result.fetchone()
        if row:
            print(f"      Total rows: {row[0]}")
            print(f"      Exact splits (prompt+completion): {row[1]}")
            print(f"      Total-only (NULL splits): {row[2]}")
            print(f"      Sum of all total_tokens: {row[3]}")

    print("\n" + "=" * 80)
    print("[OK] Migration completed successfully!")
    print("=" * 80)
    print("\nNext steps:")
    print("  1. Restart any running executor/backend processes")
    print("  2. Run tests: pytest tests/autopack/test_llm_usage_schema_drift.py")
    print("  3. Verify dashboard: /dashboard/usage should now report correct totals")


def downgrade(engine: Engine) -> None:
    """Remove total_tokens column from llm_usage_events table"""
    print("=" * 80)
    print("BUILD-144 P0.3: Remove total_tokens Column (Downgrade)")
    print("=" * 80)

    if not check_table_exists(engine, "llm_usage_events"):
        print("[!]️  Table 'llm_usage_events' does not exist, nothing to downgrade")
        return

    with engine.begin() as conn:
        if not check_column_exists(engine, "llm_usage_events", "total_tokens"):
            print("[x] Column 'total_tokens' does not exist, nothing to remove")
            return

        print("\n[1/1] Dropping column: total_tokens")

        # SQLite requires special handling for column drops
        db_url = get_database_url()
        if "sqlite" in db_url.lower():
            print("      [!]️  SQLite detected - column drop requires table recreation")
            print("      For safety, manual intervention recommended:")
            print("      1. Backup database")
            print("      2. Recreate table without total_tokens")
            print("      3. Copy data from backup")
            print("\n      Skipping automatic downgrade for SQLite")
            return
        else:
            # PostgreSQL and other databases support DROP COLUMN
            conn.execute(
                text("""
                ALTER TABLE llm_usage_events
                DROP COLUMN total_tokens
            """)
            )
            print("      [x] Column 'total_tokens' dropped")

    print("\n" + "=" * 80)
    print("[OK] Downgrade completed successfully!")
    print("=" * 80)


def main():
    """Main entry point"""
    if len(sys.argv) < 2 or sys.argv[1] not in ["upgrade", "downgrade"]:
        print("Usage: python add_total_tokens_build144.py [upgrade|downgrade]")
        sys.exit(1)

    command = sys.argv[1]
    db_url = get_database_url()

    print(f"\nDatabase URL: {db_url}")
    print(f"Command: {command}\n")

    try:
        engine = create_engine(db_url)

        if command == "upgrade":
            upgrade(engine)
        else:
            downgrade(engine)

    except Exception as e:
        print(f"\n[X] Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
