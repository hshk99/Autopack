#!/usr/bin/env python3
"""
Add missing doctor usage columns to llm_usage_events for SQLite DBs.

Columns:
- is_doctor_call BOOLEAN NOT NULL DEFAULT 0
- doctor_model TEXT NULL
- doctor_action TEXT NULL
"""

import os
import sqlite3
from urllib.parse import urlparse


def main():
    db_url = os.getenv("DATABASE_URL", "sqlite:///autopack.db")
    parsed = urlparse(db_url)

    if parsed.scheme != "sqlite":
        print(f"[SKIP] Non-sqlite DATABASE_URL={db_url}")
        return

    db_path = parsed.path.lstrip("/") if parsed.netloc == "" else parsed.path
    if not db_path:
        db_path = "autopack.db"

    if not os.path.exists(db_path):
        print(f"[SKIP] DB file not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(llm_usage_events)")
        cols = {row[1] for row in cur.fetchall()}

        missing = []
        if "is_doctor_call" not in cols:
            missing.append(("is_doctor_call", "BOOLEAN NOT NULL DEFAULT 0"))
        if "doctor_model" not in cols:
            missing.append(("doctor_model", "TEXT"))
        if "doctor_action" not in cols:
            missing.append(("doctor_action", "TEXT"))

        if not missing:
            print("[OK] llm_usage_events already has doctor columns.")
            return

        for name, coltype in missing:
            sql = f"ALTER TABLE llm_usage_events ADD COLUMN {name} {coltype}"
            print(f"[MIGRATE] {sql}")
            cur.execute(sql)

        conn.commit()
        print("[OK] Migration complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

