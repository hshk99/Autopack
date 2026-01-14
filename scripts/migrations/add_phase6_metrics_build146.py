"""
BUILD-146 Production Polish: Database Migration - Add phase6_metrics table

Adds Phase 6 True Autonomy feature effectiveness tracking table.

Background:
- BUILD-146 Phase 6 implemented 4 new features: Failure Hardening, Intention Context,
  Plan Normalization, and Parallel Execution
- This migration adds telemetry tracking for measuring feature effectiveness

Schema changes:
- Creates phase6_metrics table with columns for tracking:
  * Failure hardening: pattern detection, mitigation, Doctor call skips, token savings
  * Intention context: injection stats, character counts, source tracking
  * Plan normalization: usage, confidence, warnings, scope metrics

All fields nullable for backward compatibility and graceful degradation.

This migration is idempotent and can be run multiple times safely.

Usage:
    # SQLite (default):
    python scripts/migrations/add_phase6_metrics_build146.py upgrade

    # PostgreSQL:
    DATABASE_URL="postgresql://..." python scripts/migrations/add_phase6_metrics_build146.py upgrade

    # Downgrade (remove table):
    python scripts/migrations/add_phase6_metrics_build146.py downgrade
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
        python scripts/migrations/add_phase6_metrics_build146.py upgrade

        # PowerShell (SQLite dev/test - explicit opt-in):
        $env:DATABASE_URL="sqlite:///autopack.db"
        python scripts/migrations/add_phase6_metrics_build146.py upgrade
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
            "  python scripts/migrations/add_phase6_metrics_build146.py upgrade\n", file=sys.stderr
        )
        print("  # PowerShell (SQLite dev/test - explicit opt-in):", file=sys.stderr)
        print('  $env:DATABASE_URL="sqlite:///autopack.db"', file=sys.stderr)
        print(
            "  python scripts/migrations/add_phase6_metrics_build146.py upgrade\n", file=sys.stderr
        )
        sys.exit(1)
    return db_url


def check_table_exists(engine: Engine, table_name: str) -> bool:
    """Check if a table exists"""
    try:
        inspector = inspect(engine)
        return table_name in inspector.get_table_names()
    except Exception:
        return False


def upgrade(engine: Engine) -> None:
    """Create phase6_metrics table"""
    print("=" * 80)
    print("BUILD-146 Production Polish: Add Phase 6 Metrics Table")
    print("=" * 80)

    # Check if table already exists
    if check_table_exists(engine, "phase6_metrics"):
        print("✓ Table 'phase6_metrics' already exists, skipping")
        print("\nMigration already applied - no changes needed")
        return

    print("\n[1] Creating table: phase6_metrics")
    print("    Purpose: Track Phase 6 True Autonomy feature effectiveness")

    with engine.begin() as conn:
        conn.execute(
            text(
                """
            CREATE TABLE phase6_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id VARCHAR(255) NOT NULL,
                phase_id VARCHAR(255) NOT NULL,

                -- Failure hardening metrics
                failure_hardening_triggered BOOLEAN NOT NULL DEFAULT 0,
                failure_pattern_detected VARCHAR(100) NULL,
                failure_hardening_mitigated BOOLEAN NOT NULL DEFAULT 0,
                doctor_call_skipped BOOLEAN NOT NULL DEFAULT 0,
                tokens_saved_estimate INTEGER NOT NULL DEFAULT 0,

                -- Intention context metrics
                intention_context_injected BOOLEAN NOT NULL DEFAULT 0,
                intention_context_chars INTEGER NOT NULL DEFAULT 0,
                intention_context_source VARCHAR(50) NULL,

                -- Plan normalization metrics
                plan_normalization_used BOOLEAN NOT NULL DEFAULT 0,
                plan_normalization_confidence INTEGER NULL,
                plan_normalization_warnings INTEGER NOT NULL DEFAULT 0,
                plan_deliverables_count INTEGER NULL,
                plan_scope_size_bytes INTEGER NULL,

                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
            )
        )

        # Create indexes for common queries
        conn.execute(
            text(
                """
            CREATE INDEX idx_phase6_metrics_run_id ON phase6_metrics(run_id)
        """
            )
        )
        conn.execute(
            text(
                """
            CREATE INDEX idx_phase6_metrics_phase_id ON phase6_metrics(phase_id)
        """
            )
        )
        conn.execute(
            text(
                """
            CREATE INDEX idx_phase6_metrics_created_at ON phase6_metrics(created_at)
        """
            )
        )

        print("    ✓ Table 'phase6_metrics' created with indexes")

    print("\n" + "=" * 80)
    print("✅ Migration completed successfully!")
    print("=" * 80)
    print("\nNext steps:")
    print("  1. Restart any running executor/backend processes")
    print("  2. Enable telemetry: TELEMETRY_DB_ENABLED=true")
    print("  3. Enable features: AUTOPACK_ENABLE_FAILURE_HARDENING=true")
    print("  4. Run tests: pytest tests/integration/test_phase6_integration.py")
    print("  5. Check metrics: GET /dashboard/runs/{run_id}/phase6-stats")


def downgrade(engine: Engine) -> None:
    """Drop phase6_metrics table"""
    print("=" * 80)
    print("BUILD-146 Production Polish: Remove Phase 6 Metrics Table (Downgrade)")
    print("=" * 80)

    if not check_table_exists(engine, "phase6_metrics"):
        print("✓ Table 'phase6_metrics' does not exist, nothing to downgrade")
        return

    print("\n[1] Dropping table: phase6_metrics")
    print("    ⚠️  This will delete all Phase 6 telemetry data!")

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE phase6_metrics"))
        print("    ✓ Table 'phase6_metrics' dropped")

    print("\n" + "=" * 80)
    print("✅ Downgrade completed!")
    print("=" * 80)


def main():
    """Main entry point"""
    if len(sys.argv) < 2 or sys.argv[1] not in ["upgrade", "downgrade"]:
        print("Usage: python add_phase6_metrics_build146.py [upgrade|downgrade]")
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
