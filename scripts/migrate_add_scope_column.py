#!/usr/bin/env python3
"""
Database migration: Add scope column to phases table

This migration adds the scope column to support file path scoping for external projects.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal, engine
from sqlalchemy import text


def migrate():
    """Add scope column to phases table"""

    print("Starting migration: Add scope column to phases table")

    db = SessionLocal()
    try:
        # Check if column already exists (PostgreSQL)
        result = db.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='phases' AND column_name='scope'
        """))

        if result.fetchone():
            print("[OK] Column 'scope' already exists in phases table")
            return

        # Add the column (PostgreSQL uses JSONB for JSON)
        print("Adding 'scope' column to phases table...")
        db.execute(text("ALTER TABLE phases ADD COLUMN scope JSONB"))
        db.commit()

        print("[OK] Migration complete: scope column added")

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
