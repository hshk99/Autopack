"""
BUILD-145 P1 Hardening: Database Migration - Add phase_outcome column to token_efficiency_metrics

Adds phase_outcome column to token_efficiency_metrics table to track terminal phase states.

Background:
- BUILD-145 P1.1 implemented token efficiency observability infrastructure
- P1 hardening extends telemetry to capture terminal outcomes (COMPLETE, FAILED, BLOCKED)
- Makes failures visible in metrics (not just success)
- Enables analysis of efficiency metrics across all phase outcomes

Schema changes:
- token_efficiency_metrics.phase_outcome: VARCHAR(50) NULL (nullable for backward compatibility)
- Stores terminal phase state: COMPLETE, FAILED, BLOCKED, etc.
- Indexed for efficient filtering by outcome

This migration is idempotent and can be run multiple times safely.

Usage:
    # SQLite (default):
    python scripts/migrations/add_phase_outcome_build145_p1.py upgrade

    # PostgreSQL:
    DATABASE_URL="postgresql://..." python scripts/migrations/add_phase_outcome_build145_p1.py upgrade

    # Downgrade (remove column):
    python scripts/migrations/add_phase_outcome_build145_p1.py downgrade
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
        python scripts/migrations/add_phase_outcome_build145_p1.py upgrade

        # PowerShell (SQLite dev/test - explicit opt-in):
        $env:DATABASE_URL="sqlite:///autopack.db"
        python scripts/migrations/add_phase_outcome_build145_p1.py upgrade
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
        print(
            "  python scripts/migrations/add_phase_outcome_build145_p1.py upgrade\n",
            file=sys.stderr,
        )
        print("  # PowerShell (SQLite dev/test - explicit opt-in):", file=sys.stderr)
        print('  $env:DATABASE_URL="sqlite:///autopack.db"', file=sys.stderr)
        print(
            "  python scripts/migrations/add_phase_outcome_build145_p1.py upgrade\n",
            file=sys.stderr,
        )
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
    """Add phase_outcome column to token_efficiency_metrics table"""
    print("=" * 80)
    print("BUILD-145 P1 Hardening: Add phase_outcome Column to token_efficiency_metrics")
    print("=" * 80)

    # Check if table exists
    if not check_table_exists(engine, "token_efficiency_metrics"):
        print("⚠️  Table 'token_efficiency_metrics' does not exist")
        print("    This is expected for fresh databases - ORM will create it with phase_outcome")
        return

    with engine.begin() as conn:
        # Check if column already exists
        if check_column_exists(engine, "token_efficiency_metrics", "phase_outcome"):
            print("✓ Column 'phase_outcome' already exists, skipping column creation")

            # Verify existing data
            result = conn.execute(
                text("""
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN phase_outcome IS NULL THEN 1 ELSE 0 END) as null_count,
                       SUM(CASE WHEN phase_outcome = 'COMPLETE' THEN 1 ELSE 0 END) as complete_count,
                       SUM(CASE WHEN phase_outcome = 'FAILED' THEN 1 ELSE 0 END) as failed_count
                FROM token_efficiency_metrics
            """)
            )
            row = result.fetchone()
            if row:
                print("✓ Existing metrics breakdown:")
                print(f"    Total rows: {row[0]}")
                print(f"    NULL (legacy): {row[1]}")
                print(f"    COMPLETE: {row[2]}")
                print(f"    FAILED: {row[3]}")

            return

        print("\n[1/2] Adding column: phase_outcome (VARCHAR(50) NULL)")
        print("      Purpose: Track terminal phase outcomes (COMPLETE, FAILED, BLOCKED)")
        print("      Nullable: TRUE (backward compatible with existing rows)")

        # SQLite and PostgreSQL both support this syntax
        conn.execute(
            text("""
            ALTER TABLE token_efficiency_metrics
            ADD COLUMN phase_outcome VARCHAR(50) NULL
        """)
        )
        print("      ✓ Column 'phase_outcome' added")

        print("\n[2/2] Creating index on phase_outcome for efficient filtering")
        try:
            conn.execute(
                text("""
                CREATE INDEX idx_token_efficiency_metrics_phase_outcome
                ON token_efficiency_metrics(phase_outcome)
            """)
            )
            print("      ✓ Index 'idx_token_efficiency_metrics_phase_outcome' created")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("      ✓ Index already exists, skipping")
            else:
                raise

        print("\n[3/3] Verification")
        result = conn.execute(
            text("""
            SELECT COUNT(*) as total_rows
            FROM token_efficiency_metrics
        """)
        )
        row = result.fetchone()
        if row:
            print(f"      Total rows: {row[0]}")
            print("      All existing rows have phase_outcome=NULL (expected)")

    print("\n" + "=" * 80)
    print("✅ Migration completed successfully!")
    print("=" * 80)
    print("\nNext steps:")
    print("  1. Restart any running executor/backend processes")
    print("  2. Run tests: pytest tests/autopack/test_token_efficiency_observability.py")
    print("  3. New telemetry will include phase_outcome (COMPLETE/FAILED/BLOCKED)")


def downgrade(engine: Engine) -> None:
    """Remove phase_outcome column from token_efficiency_metrics table"""
    print("=" * 80)
    print("BUILD-145 P1: Remove phase_outcome Column (Downgrade)")
    print("=" * 80)

    if not check_table_exists(engine, "token_efficiency_metrics"):
        print("⚠️  Table 'token_efficiency_metrics' does not exist, nothing to downgrade")
        return

    with engine.begin() as conn:
        if not check_column_exists(engine, "token_efficiency_metrics", "phase_outcome"):
            print("✓ Column 'phase_outcome' does not exist, nothing to remove")
            return

        print("\n[1/2] Dropping index: idx_token_efficiency_metrics_phase_outcome")
        try:
            conn.execute(
                text("""
                DROP INDEX idx_token_efficiency_metrics_phase_outcome
            """)
            )
            print("      ✓ Index dropped")
        except Exception as e:
            if "no such index" in str(e).lower() or "does not exist" in str(e).lower():
                print("      ✓ Index does not exist, skipping")
            else:
                print(f"      ⚠️  Warning: {e}")

        print("\n[2/2] Dropping column: phase_outcome")

        # SQLite requires special handling for column drops
        db_url = get_database_url()
        if "sqlite" in db_url.lower():
            print("      ⚠️  SQLite detected - column drop requires table recreation")
            print("      For safety, manual intervention recommended:")
            print("      1. Backup database")
            print("      2. Recreate table without phase_outcome")
            print("      3. Copy data from backup")
            print("\n      Skipping automatic downgrade for SQLite")
            return
        else:
            # PostgreSQL and other databases support DROP COLUMN
            conn.execute(
                text("""
                ALTER TABLE token_efficiency_metrics
                DROP COLUMN phase_outcome
            """)
            )
            print("      ✓ Column 'phase_outcome' dropped")

    print("\n" + "=" * 80)
    print("✅ Downgrade completed successfully!")
    print("=" * 80)


def main():
    """Main entry point"""
    if len(sys.argv) < 2 or sys.argv[1] not in ["upgrade", "downgrade"]:
        print("Usage: python add_phase_outcome_build145_p1.py [upgrade|downgrade]")
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
        print(f"\n❌ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
