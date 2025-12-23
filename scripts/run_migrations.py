#!/usr/bin/env python3
"""Simple migration runner

Following GPT's recommendation: Simple migration scripts (not full Migration Manager yet).
Run SQL files from both:
- migrations/ (root)  [primary schema + telemetry migrations]
- scripts/migrations/ (legacy/utility migrations)

Files are executed in lexicographic order within each directory, with root migrations
running first by default.
"""

import argparse
import sqlite3
import sys
from pathlib import Path


def get_db_path() -> Path:
    """Get database path"""
    # Default to autopack.db in project root
    db_path = Path.cwd() / "autopack.db"

    # Check if DB exists
    if not db_path.exists():
        print(f"Warning: Database not found at {db_path}")
        print("Migrations will run when database is created.")
        return db_path

    return db_path


def get_migration_files(migrations_dir: Path, label: str) -> list[tuple[str, Path]]:
    """Get sorted list of migration files from a single directory."""
    if not migrations_dir.exists():
        print(f"[*] No migrations directory found at {migrations_dir} ({label})")
        return []

    # Get all .sql files, sorted by name
    migration_files = sorted(migrations_dir.glob("*.sql"))

    # Extract version from filename (e.g., "001_..." -> "001")
    migrations = []
    for file_path in migration_files:
        version = file_path.stem.split("_")[0]
        migrations.append((version, file_path))

    return migrations


def run_migration(db_path: Path, migration_file: Path, dry_run: bool = False):
    """Run a single migration file"""
    print(f"[*] Running migration: {migration_file.name}")

    # Read migration SQL
    try:
        sql = migration_file.read_text(encoding='utf-8')
    except Exception as e:
        print(f"[ERROR] Failed to read migration file: {e}")
        return False

    if dry_run:
        print(f"[DRY RUN] Would execute:\n{sql}\n")
        return True

    # Connect to database and run migration
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Execute migration (may contain multiple statements)
        cursor.executescript(sql)

        conn.commit()
        conn.close()

        print(f"[✓] Migration {migration_file.name} completed successfully")
        return True

    except Exception as e:
        print(f"[ERROR] Migration {migration_file.name} failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print migrations without executing them"
    )
    parser.add_argument(
        "--db",
        type=str,
        help="Database path (default: autopack.db in current directory)"
    )

    args = parser.parse_args()

    # Get database path
    db_path = Path(args.db) if args.db else get_db_path()

    print(f"[*] Database: {db_path}")
    root_migrations_dir = Path.cwd() / "migrations"
    scripts_migrations_dir = Path(__file__).parent / "migrations"
    print(f"[*] Root migrations directory: {root_migrations_dir}")
    print(f"[*] Scripts migrations directory: {scripts_migrations_dir}")

    if args.dry_run:
        print("[*] DRY RUN MODE - No changes will be made")

    # Get migration files (root first, then legacy scripts/)
    migrations = []
    migrations.extend(get_migration_files(root_migrations_dir, label="root"))
    migrations.extend(get_migration_files(scripts_migrations_dir, label="scripts"))

    if not migrations:
        print("[*] No migrations found")
        return 0

    print(f"[*] Found {len(migrations)} migration(s)")

    # Run migrations in order
    success_count = 0
    for version, migration_file in migrations:
        if run_migration(db_path, migration_file, dry_run=args.dry_run):
            success_count += 1
        else:
            print(f"[ERROR] Migration failed, stopping at version {version}")
            return 1

    print(f"\n[✓] Successfully ran {success_count}/{len(migrations)} migrations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
