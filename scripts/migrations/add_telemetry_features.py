"""
BUILD-129 Phase 3: Database Migration - Add Feature Tracking to Token Telemetry

Adds feature tracking columns to token_estimation_v2_events table:
- is_truncated_output: Flag for censored data (actual tokens is lower bound)
- api_reference_required: Boolean for API doc detection
- examples_required: Boolean for code examples detection
- research_required: Boolean for investigation needed detection
- usage_guide_required: Boolean for usage docs detection
- context_quality: String ("none", "some", "strong") for context availability

These fields enable:
1. Proper handling of truncated outputs in calibration
2. DOC_SYNTHESIS feature analysis
3. Improved documentation token estimation

Usage:
    python scripts/migrations/add_telemetry_features.py upgrade
    python scripts/migrations/add_telemetry_features.py downgrade
"""

import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


def get_database_url() -> str:
    """Get DATABASE_URL from environment"""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return db_url


def check_column_exists(engine: Engine, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade(engine: Engine) -> None:
    """Add feature tracking columns to token_estimation_v2_events table"""
    print("=" * 70)
    print("BUILD-129 Phase 3: Add Telemetry Feature Tracking Columns")
    print("=" * 70)

    with engine.begin() as conn:
        # Check if columns already exist
        if check_column_exists(engine, "token_estimation_v2_events", "is_truncated_output"):
            print("✓ Feature tracking columns already exist, skipping migration")
            return

        print("\n[1/6] Adding column: is_truncated_output (Boolean, default=False)")
        print("      Purpose: Flag censored data where actual_tokens is lower bound")
        conn.execute(text("""
            ALTER TABLE token_estimation_v2_events
            ADD COLUMN is_truncated_output BOOLEAN NOT NULL DEFAULT FALSE
        """))
        print("      ✓ Column 'is_truncated_output' added")

        print("\n[2/6] Adding column: api_reference_required (Boolean, nullable)")
        print("      Purpose: Detect tasks requiring API documentation")
        conn.execute(text("""
            ALTER TABLE token_estimation_v2_events
            ADD COLUMN api_reference_required BOOLEAN
        """))
        print("      ✓ Column 'api_reference_required' added")

        print("\n[3/6] Adding column: examples_required (Boolean, nullable)")
        print("      Purpose: Detect tasks requiring code examples")
        conn.execute(text("""
            ALTER TABLE token_estimation_v2_events
            ADD COLUMN examples_required BOOLEAN
        """))
        print("      ✓ Column 'examples_required' added")

        print("\n[4/6] Adding column: research_required (Boolean, nullable)")
        print("      Purpose: Detect tasks requiring codebase investigation")
        conn.execute(text("""
            ALTER TABLE token_estimation_v2_events
            ADD COLUMN research_required BOOLEAN
        """))
        print("      ✓ Column 'research_required' added")

        print("\n[5/6] Adding column: usage_guide_required (Boolean, nullable)")
        print("      Purpose: Detect tasks requiring usage documentation")
        conn.execute(text("""
            ALTER TABLE token_estimation_v2_events
            ADD COLUMN usage_guide_required BOOLEAN
        """))
        print("      ✓ Column 'usage_guide_required' added")

        print("\n[6/6] Adding column: context_quality (String, nullable)")
        print("      Purpose: Track context availability (none/some/strong)")
        conn.execute(text("""
            ALTER TABLE token_estimation_v2_events
            ADD COLUMN context_quality VARCHAR
        """))
        print("      ✓ Column 'context_quality' added")

        # Create index on is_truncated_output for efficient filtering
        print("\n[Index] Creating index: idx_telemetry_truncated")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_telemetry_truncated
            ON token_estimation_v2_events (is_truncated_output, category)
        """))
        print("      ✓ Index 'idx_telemetry_truncated' created")

        # Verify existing events
        result = conn.execute(text("SELECT COUNT(*) FROM token_estimation_v2_events"))
        event_count = result.scalar() or 0

        print("\n✓ Migration complete!")
        print(f"  - {event_count} existing telemetry events updated with defaults:")
        print("    - is_truncated_output = FALSE")
        print("    - api_reference_required = NULL")
        print("    - examples_required = NULL")
        print("    - research_required = NULL")
        print("    - usage_guide_required = NULL")
        print("    - context_quality = NULL")

    print("\n" + "=" * 70)
    print("BUILD-129 Phase 3 Migration: SUCCESS")
    print("=" * 70)


def downgrade(engine: Engine) -> None:
    """Remove feature tracking columns from token_estimation_v2_events table"""
    print("=" * 70)
    print("BUILD-129 Phase 3 Rollback: Remove Telemetry Feature Tracking")
    print("=" * 70)

    with engine.begin() as conn:
        # Check if columns exist before trying to drop
        if not check_column_exists(engine, "token_estimation_v2_events", "is_truncated_output"):
            print("✓ Feature tracking columns already removed, nothing to rollback")
            return

        print("\n[1/7] Dropping index: idx_telemetry_truncated")
        conn.execute(text("DROP INDEX IF EXISTS idx_telemetry_truncated"))
        print("      ✓ Index 'idx_telemetry_truncated' dropped")

        print("\n[2/7] Dropping column: context_quality")
        conn.execute(text("ALTER TABLE token_estimation_v2_events DROP COLUMN IF EXISTS context_quality"))
        print("      ✓ Column 'context_quality' dropped")

        print("\n[3/7] Dropping column: usage_guide_required")
        conn.execute(text("ALTER TABLE token_estimation_v2_events DROP COLUMN IF EXISTS usage_guide_required"))
        print("      ✓ Column 'usage_guide_required' dropped")

        print("\n[4/7] Dropping column: research_required")
        conn.execute(text("ALTER TABLE token_estimation_v2_events DROP COLUMN IF EXISTS research_required"))
        print("      ✓ Column 'research_required' dropped")

        print("\n[5/7] Dropping column: examples_required")
        conn.execute(text("ALTER TABLE token_estimation_v2_events DROP COLUMN IF EXISTS examples_required"))
        print("      ✓ Column 'examples_required' dropped")

        print("\n[6/7] Dropping column: api_reference_required")
        conn.execute(text("ALTER TABLE token_estimation_v2_events DROP COLUMN IF EXISTS api_reference_required"))
        print("      ✓ Column 'api_reference_required' dropped")

        print("\n[7/7] Dropping column: is_truncated_output")
        conn.execute(text("ALTER TABLE token_estimation_v2_events DROP COLUMN IF EXISTS is_truncated_output"))
        print("      ✓ Column 'is_truncated_output' dropped")

    print("\n" + "=" * 70)
    print("BUILD-129 Phase 3 Rollback: SUCCESS")
    print("=" * 70)


def main():
    """Main entry point for migration script"""
    if len(sys.argv) < 2:
        print("Usage: python add_telemetry_features.py [upgrade|downgrade]")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command not in ["upgrade", "downgrade"]:
        print(f"Error: Invalid command '{command}'")
        print("Usage: python add_telemetry_features.py [upgrade|downgrade]")
        sys.exit(1)

    try:
        db_url = get_database_url()
        print(f"\nConnecting to database: {db_url.split('@')[1] if '@' in db_url else 'local'}")

        engine = create_engine(db_url)

        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()

        print("✓ Database connection successful\n")

        if command == "upgrade":
            upgrade(engine)
        else:
            downgrade(engine)

        print("\n✓ Migration script completed successfully")

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
