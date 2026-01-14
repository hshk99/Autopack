"""
BUILD-146 P3: Database Migration - Rename and add Phase 6 estimation fields

Renames `tokens_saved_estimate` to `doctor_tokens_avoided_estimate` and adds
coverage tracking fields for defensible ROI measurement.

Schema changes:
- Rename: tokens_saved_estimate -> doctor_tokens_avoided_estimate
- Add: estimate_coverage_n (INTEGER, nullable) - sample size for baseline
- Add: estimate_source (VARCHAR, nullable) - baseline source ("run_local", "global", "fallback")

Rationale (BUILD-146 P3):
- Old name was misleading (not actual savings, just counterfactual estimate)
- New fields track estimation quality and allow user to judge confidence
- Keeps actual_tokens_saved separate for future A/B validation

This migration is idempotent and can be run multiple times safely.

Usage:
    # SQLite (default):
    python scripts/migrations/add_phase6_p3_fields.py upgrade

    # PostgreSQL:
    DATABASE_URL="postgresql://..." python scripts/migrations/add_phase6_p3_fields.py upgrade

    # Downgrade (revert changes):
    python scripts/migrations/add_phase6_p3_fields.py downgrade
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
        python scripts/migrations/add_phase6_p3_fields.py upgrade

        # PowerShell (SQLite dev/test - explicit opt-in):
        $env:DATABASE_URL="sqlite:///autopack.db"
        python scripts/migrations/add_phase6_p3_fields.py upgrade
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
        print("  python scripts/migrations/add_phase6_p3_fields.py upgrade\n", file=sys.stderr)
        print("  # PowerShell (SQLite dev/test - explicit opt-in):", file=sys.stderr)
        print('  $env:DATABASE_URL="sqlite:///autopack.db"', file=sys.stderr)
        print("  python scripts/migrations/add_phase6_p3_fields.py upgrade\n", file=sys.stderr)
        sys.exit(1)
    return db_url


def check_table_exists(engine: Engine, table_name: str) -> bool:
    """Check if a table exists"""
    try:
        inspector = inspect(engine)
        return table_name in inspector.get_table_names()
    except Exception:
        return False


def check_column_exists(engine: Engine, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    try:
        inspector = inspect(engine)
        columns = [col["name"] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False


def upgrade(engine: Engine) -> None:
    """Add new fields and rename tokens_saved_estimate"""
    print("=" * 80)
    print("BUILD-146 P3: Update Phase 6 Metrics - Rename and Add Coverage Fields")
    print("=" * 80)

    if not check_table_exists(engine, "phase6_metrics"):
        print("❌ Table 'phase6_metrics' does not exist.")
        print("   Run add_phase6_metrics_build146.py upgrade first")
        sys.exit(1)

    # Check if migration already applied
    if check_column_exists(engine, "phase6_metrics", "doctor_tokens_avoided_estimate"):
        print("✓ Column 'doctor_tokens_avoided_estimate' already exists")
        print("\nMigration already applied - no changes needed")
        return

    print("\n[1] Adding new coverage tracking fields")
    with engine.begin() as conn:
        # Add new fields first
        conn.execute(
            text(
                """
            ALTER TABLE phase6_metrics
            ADD COLUMN estimate_coverage_n INTEGER NULL
        """
            )
        )
        print("    ✓ Added estimate_coverage_n")

        conn.execute(
            text(
                """
            ALTER TABLE phase6_metrics
            ADD COLUMN estimate_source VARCHAR(50) NULL
        """
            )
        )
        print("    ✓ Added estimate_source")

    print("\n[2] Renaming tokens_saved_estimate -> doctor_tokens_avoided_estimate")

    # SQLite doesn't support column rename directly, need to use different approach
    db_url = get_database_url()
    if db_url.startswith("sqlite"):
        print("    (Using SQLite-compatible rename strategy)")
        with engine.begin() as conn:
            # Add new column
            conn.execute(
                text(
                    """
                ALTER TABLE phase6_metrics
                ADD COLUMN doctor_tokens_avoided_estimate INTEGER NOT NULL DEFAULT 0
            """
                )
            )

            # Copy data from old column
            conn.execute(
                text(
                    """
                UPDATE phase6_metrics
                SET doctor_tokens_avoided_estimate = tokens_saved_estimate
            """
                )
            )

            # Note: SQLite doesn't allow dropping columns easily
            # We'll leave tokens_saved_estimate in place but document it as deprecated
            print("    ✓ Added doctor_tokens_avoided_estimate (copied from tokens_saved_estimate)")
            print("    ⚠️  Note: tokens_saved_estimate column remains (deprecated, ignore it)")
    else:
        # PostgreSQL supports direct rename
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                ALTER TABLE phase6_metrics
                RENAME COLUMN tokens_saved_estimate TO doctor_tokens_avoided_estimate
            """
                )
            )
            print("    ✓ Renamed column")

    print("\n" + "=" * 80)
    print("✅ Migration completed successfully!")
    print("=" * 80)
    print("\nChanges:")
    print("  - Added: estimate_coverage_n (sample size for baseline)")
    print("  - Added: estimate_source (run_local/global/fallback)")
    print("  - Renamed: tokens_saved_estimate -> doctor_tokens_avoided_estimate")
    print("\nNext steps:")
    print("  1. Restart executor/backend processes")
    print("  2. New estimates will use median baseline with coverage tracking")
    print("  3. Check dashboard: GET /dashboard/runs/{run_id}/phase6-stats")


def downgrade(engine: Engine) -> None:
    """Revert changes (not fully reversible for SQLite)"""
    print("=" * 80)
    print("BUILD-146 P3: Downgrade Phase 6 Metrics Changes")
    print("=" * 80)

    if not check_table_exists(engine, "phase6_metrics"):
        print("✓ Table 'phase6_metrics' does not exist, nothing to downgrade")
        return

    print("\n⚠️  Warning: Downgrade may not be fully reversible on SQLite")

    db_url = get_database_url()
    if db_url.startswith("sqlite"):
        print("\nSQLite limitations:")
        print("  - Cannot drop columns (doctor_tokens_avoided_estimate will remain)")
        print("  - Can drop coverage fields")
        # Just drop the coverage fields
        with engine.begin() as conn:
            # SQLite doesn't support DROP COLUMN, would need table rebuild
            print("    ⚠️  Manual intervention required to fully revert SQLite schema")
    else:
        # PostgreSQL can do full revert
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                ALTER TABLE phase6_metrics
                RENAME COLUMN doctor_tokens_avoided_estimate TO tokens_saved_estimate
            """
                )
            )

            conn.execute(text("ALTER TABLE phase6_metrics DROP COLUMN estimate_coverage_n"))
            conn.execute(text("ALTER TABLE phase6_metrics DROP COLUMN estimate_source"))
            print("    ✓ Reverted all changes")

    print("\n" + "=" * 80)
    print("✅ Downgrade completed!")
    print("=" * 80)


def main():
    """Main entry point"""
    if len(sys.argv) < 2 or sys.argv[1] not in ["upgrade", "downgrade"]:
        print("Usage: python add_phase6_p3_fields.py [upgrade|downgrade]")
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
