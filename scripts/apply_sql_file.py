"""
Apply a single SQL file to a SQLite database (no migration manager).

Why:
- scripts/run_migrations.py runs *all* root migrations, but some older DBs have drifted
  views/tables that can cause earlier migrations to fail.
- For BUILD-129 Phase 3 P10 validation we only need to apply ONE additive migration:
  migrations/005_add_p10_escalation_events.sql

Usage (PowerShell):
  python scripts/apply_sql_file.py --db autopack.db --sql migrations/005_add_p10_escalation_events.sql
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="autopack.db", help="SQLite DB path (default: autopack.db)")
    p.add_argument("--sql", required=True, help="Path to .sql file to execute")
    args = p.parse_args()

    db_path = Path(args.db)
    sql_path = Path(args.sql)

    if not sql_path.exists():
        print(f"[ERROR] SQL file not found: {sql_path}")
        return 2

    sql = sql_path.read_text(encoding="utf-8")

    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.executescript(sql)
        conn.commit()
        conn.close()
        print(f"[OK] Applied SQL file: {sql_path}")
        print(f"[OK] DB: {db_path}")
        return 0
    except Exception as e:
        print(f"[ERROR] Failed applying {sql_path} to {db_path}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


