#!/usr/bin/env python3
"""
Sync Database Information - Export DB state to docs/

This script exports database information to JSON files in docs/ folder
to keep database state synchronized with other SOT files.

Usage:
  python scripts/tidy/sync_database.py              # Sync all databases
  python scripts/tidy/sync_database.py --dry-run    # Show what would be synced
  python scripts/tidy/sync_database.py --db autopack.db  # Sync specific DB

Exports:
  - Database schema to docs/database_schema.json
  - Key statistics to docs/database_stats.json
  - Recent activity summary to docs/database_activity.json
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

REPO_ROOT = Path(__file__).parent.parent.parent


def get_database_schema(db_path: Path) -> Dict[str, Any]:
    """Extract database schema information."""
    if not db_path.exists():
        return {"error": f"Database not found: {db_path}"}

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        schema = {
            "database": str(db_path.name),
            "exported_at": datetime.now().isoformat(),
            "tables": {},
        }

        for table in tables:
            # Get table info
            cursor.execute(f"PRAGMA table_info({table})")
            columns = []
            for col in cursor.fetchall():
                columns.append(
                    {
                        "name": col[1],
                        "type": col[2],
                        "not_null": bool(col[3]),
                        "primary_key": bool(col[5]),
                    }
                )

            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            row_count = cursor.fetchone()[0]

            schema["tables"][table] = {"columns": columns, "row_count": row_count}

        conn.close()
        return schema

    except Exception as e:
        return {"error": f"Failed to read schema: {e}"}


def get_database_stats(db_path: Path) -> Dict[str, Any]:
    """Get database statistics."""
    if not db_path.exists():
        return {"error": f"Database not found: {db_path}"}

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        stats = {
            "database": str(db_path.name),
            "exported_at": datetime.now().isoformat(),
            "file_size_kb": db_path.stat().st_size // 1024,
            "tables": {},
        }

        # Get table statistics
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            stats["tables"][table] = {"row_count": count}

        conn.close()
        return stats

    except Exception as e:
        return {"error": f"Failed to get stats: {e}"}


def sync_database_to_docs(db_path: Path, docs_dir: Path, dry_run: bool = False) -> bool:
    """Sync database information to docs/ folder."""
    print(f"\n=== Syncing {db_path.name} ===")

    if not db_path.exists():
        print(f"[SKIP] Database not found: {db_path}")
        return False

    # Generate schema export
    schema = get_database_schema(db_path)
    schema_file = docs_dir / f"database_schema_{db_path.stem}.json"

    # Generate stats export
    stats = get_database_stats(db_path)
    stats_file = docs_dir / f"database_stats_{db_path.stem}.json"

    if "error" in schema or "error" in stats:
        print(f"[ERROR] Failed to read database: {schema.get('error', stats.get('error'))}")
        return False

    if dry_run:
        print(f"[DRY-RUN] Would export schema to {schema_file.name}")
        print(f"[DRY-RUN] Would export stats to {stats_file.name}")
        print(f"  Tables: {', '.join(schema['tables'].keys())}")
        print(f"  Total rows: {sum(t['row_count'] for t in schema['tables'].values())}")
        return True

    # Write schema
    schema_file.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"[OK] Exported schema to {schema_file.name}")

    # Write stats
    stats_file.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    print(f"[OK] Exported stats to {stats_file.name}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Sync database information to docs/ folder")
    parser.add_argument("--db", help="Specific database file to sync (e.g., autopack.db)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be synced without making changes"
    )
    parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Sync databases from all projects including file-organizer",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("DATABASE SYNCHRONIZATION TO DOCS/")
    print("=" * 80)

    success = True

    # Autopack main database
    autopack_db = REPO_ROOT / "autopack.db"
    autopack_docs = REPO_ROOT / "docs"
    autopack_docs.mkdir(parents=True, exist_ok=True)

    if args.db:
        # Sync specific database
        db_path = REPO_ROOT / args.db
        if not sync_database_to_docs(db_path, autopack_docs, args.dry_run):
            success = False
    else:
        # Sync Autopack database
        if autopack_db.exists():
            if not sync_database_to_docs(autopack_db, autopack_docs, args.dry_run):
                success = False
        else:
            print(f"[SKIP] {autopack_db.name} not found")

        # Sync file-organizer databases if requested
        if args.all_projects:
            fo_project = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1"
            fo_docs = fo_project / "docs"

            if fo_project.exists():
                fo_docs.mkdir(parents=True, exist_ok=True)

                # Sync main file-organizer DB
                fo_db = fo_project / "autopack.db"
                if fo_db.exists():
                    if not sync_database_to_docs(fo_db, fo_docs, args.dry_run):
                        success = False

                # Sync backend DB if it exists
                backend_db = fo_project / "src" / "backend" / "fileorganizer.db"
                if backend_db.exists():
                    if not sync_database_to_docs(backend_db, fo_docs, args.dry_run):
                        success = False

    print("\n" + "=" * 80)
    if success:
        print("DATABASE SYNC COMPLETE")
        if not args.dry_run:
            print("\nDatabase schema and stats exported to docs/")
            print("Remember to commit changes:")
            print("  git add docs/database_*.json")
            print('  git commit -m "sync: update database exports"')
    else:
        print("DATABASE SYNC FAILED - see errors above")
    print("=" * 80)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
