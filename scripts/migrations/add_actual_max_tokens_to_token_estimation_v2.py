"""
Migration: Add actual_max_tokens column to token_estimation_v2_events table

BUILD-142 PARITY: Separate telemetry semantics
- selected_budget: Estimator intent (BEFORE P4 enforcement)
- actual_max_tokens: Final ceiling (AFTER P4 enforcement)

This allows accurate waste calculation using actual_max_tokens / actual_output_tokens
instead of selected_budget / actual_output_tokens.

Usage (from repo root):
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///./telemetry_seed_v5.db" \
        python scripts/migrations/add_actual_max_tokens_to_token_estimation_v2.py
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autopack.database import init_db, engine
from sqlalchemy import text, inspect

def add_actual_max_tokens_column():
    """Add actual_max_tokens column to token_estimation_v2_events table."""

    print("Initializing database...")
    init_db()

    # Check if column already exists
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('token_estimation_v2_events')]

    if 'actual_max_tokens' in columns:
        print("✅ actual_max_tokens column already exists, skipping migration")
        return

    print("Adding actual_max_tokens column to token_estimation_v2_events...")

    # SQLite doesn't support DROP COLUMN, so we use ALTER TABLE ADD COLUMN
    # The column will be nullable initially, then we'll backfill from selected_budget
    with engine.connect() as conn:
        # Add column (nullable, will backfill)
        conn.execute(text(
            "ALTER TABLE token_estimation_v2_events ADD COLUMN actual_max_tokens INTEGER"
        ))
        conn.commit()
        print("✅ Added actual_max_tokens column (nullable)")

        # Backfill: For existing rows, copy selected_budget to actual_max_tokens
        # This preserves historical data semantics (selected_budget was the final value)
        result = conn.execute(text(
            "UPDATE token_estimation_v2_events SET actual_max_tokens = selected_budget WHERE actual_max_tokens IS NULL"
        ))
        conn.commit()
        rows_updated = result.rowcount
        print(f"✅ Backfilled {rows_updated} rows (copied selected_budget → actual_max_tokens)")

    print("\n✅ Migration complete!")
    print("   - actual_max_tokens column added")
    print("   - Existing rows backfilled from selected_budget")
    print("   - New telemetry will store both selected_budget (intent) and actual_max_tokens (ceiling)")

if __name__ == "__main__":
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL must be set explicitly.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Example usage (PowerShell):", file=sys.stderr)
        print("  $env:DATABASE_URL='sqlite:///./telemetry_seed_v5.db'", file=sys.stderr)
        print("  python scripts/migrations/add_actual_max_tokens_to_token_estimation_v2.py", file=sys.stderr)
        sys.exit(1)

    add_actual_max_tokens_column()
