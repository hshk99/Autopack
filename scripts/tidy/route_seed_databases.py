#!/usr/bin/env python3
"""
Route Seed Databases to Archive

Moves telemetry seed databases from repo root to archive/data/databases/telemetry_seeds/.
This keeps the repo root clean while preserving seed data for reference.

Gap Analysis: Section 2.4 (Local workspace hygiene)

Usage:
    python scripts/tidy/route_seed_databases.py          # Dry-run (default)
    python scripts/tidy/route_seed_databases.py --apply  # Actually move files
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Repo root detection
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

# Target directory for seed databases
ARCHIVE_DIR = REPO_ROOT / "archive" / "data" / "databases" / "telemetry_seeds"

# Patterns for seed databases (in repo root only)
SEED_DB_PATTERNS = [
    "telemetry_seed*.db",
    "autopack_telemetry_seed*.db",
]

# Files to keep in root (not moved)
KEEP_IN_ROOT = {
    "autopack.db",  # Main dev database
}


def find_seed_databases() -> list[Path]:
    """Find seed database files in repo root."""
    found = []
    for pattern in SEED_DB_PATTERNS:
        for path in REPO_ROOT.glob(pattern):
            if path.is_file() and path.name not in KEEP_IN_ROOT:
                found.append(path)
    return sorted(set(found))


def route_databases(dry_run: bool = True) -> tuple[int, int]:
    """
    Move seed databases to archive directory.

    Returns:
        Tuple of (moved_count, error_count)
    """
    seed_dbs = find_seed_databases()

    if not seed_dbs:
        print("[OK] No seed databases found in repo root")
        return 0, 0

    print(f"[INFO] Found {len(seed_dbs)} seed database(s) in repo root:")
    for db in seed_dbs:
        print(f"  - {db.name}")

    if dry_run:
        print("\n[DRY-RUN] Would move to:", ARCHIVE_DIR)
        print("[DRY-RUN] Run with --apply to actually move files")
        return len(seed_dbs), 0

    # Ensure archive directory exists
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    moved = 0
    errors = 0

    for db in seed_dbs:
        dest = ARCHIVE_DIR / db.name

        # Handle name conflicts by appending timestamp
        if dest.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stem = db.stem
            dest = ARCHIVE_DIR / f"{stem}_{timestamp}.db"

        try:
            shutil.move(str(db), str(dest))
            print(f"[MOVED] {db.name} -> {dest.relative_to(REPO_ROOT)}")
            moved += 1
        except Exception as e:
            print(f"[ERROR] Failed to move {db.name}: {e}")
            errors += 1

    print(f"\n[DONE] Moved {moved} file(s), {errors} error(s)")
    return moved, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Route seed databases from repo root to archive")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move files (default is dry-run)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit with error if seed databases exist in root (for CI)",
    )
    args = parser.parse_args()

    if args.check:
        seed_dbs = find_seed_databases()
        if seed_dbs:
            print(f"[FAIL] Found {len(seed_dbs)} seed database(s) in repo root:")
            for db in seed_dbs:
                print(f"  - {db.name}")
            print("\nRun: python scripts/tidy/route_seed_databases.py --apply")
            return 1
        print("[OK] No seed databases in repo root")
        return 0

    moved, errors = route_databases(dry_run=not args.apply)
    return 1 if errors > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
