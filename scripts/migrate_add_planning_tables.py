#!/usr/bin/env python3
"""
Add Phase 2 planning/decision tables for SQLite deployments.

Tables:
- planning_artifacts (versioned planning files/prompts)
- plan_changes (plan/template revisions with rationale)
- decision_log (doctor/replan decision records)
"""

import os
import sqlite3
from typing import Optional
from urllib.parse import urlparse


def _get_db_path() -> Optional[str]:
    """Resolve SQLite path from DATABASE_URL (defaults to autopack.db)."""
    db_url = os.getenv("DATABASE_URL", "sqlite:///autopack.db")
    parsed = urlparse(db_url)

    if parsed.scheme != "sqlite":
        print(f"[SKIP] Non-sqlite DATABASE_URL={db_url}")
        return None

    db_path = parsed.path.lstrip("/") if parsed.netloc == "" else parsed.path
    return db_path or "autopack.db"


def _table_columns(cur, table: str) -> set[str]:
    """Return existing column names for a table."""
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def _ensure_table(
    cur, table: str, create_sql: str, columns: dict[str, str], indices: list[str]
) -> None:
    """Create table if missing; add any missing columns if table already exists."""
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    exists = cur.fetchone() is not None

    if not exists:
        print(f"[CREATE] {table}")
        cur.execute(create_sql)
    else:
        existing_cols = _table_columns(cur, table)
        for name, coltype in columns.items():
            if name not in existing_cols:
                sql = f"ALTER TABLE {table} ADD COLUMN {name} {coltype}"
                print(f"[ALTER] {sql}")
                cur.execute(sql)

    for idx_sql in indices:
        print(f"[INDEX] {idx_sql}")
        cur.execute(idx_sql)


def main() -> None:
    db_path = _get_db_path()
    if not db_path:
        return

    if not os.path.exists(db_path):
        print(f"[SKIP] DB file not found: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        _ensure_table(
            cur,
            "planning_artifacts",
            """
            CREATE TABLE IF NOT EXISTS planning_artifacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,
                project_id TEXT,
                timestamp TEXT NOT NULL,
                hash TEXT NOT NULL,
                author TEXT,
                reason TEXT,
                status TEXT NOT NULL DEFAULT 'active',
                replaced_by INTEGER,
                vector_id TEXT
            )
            """,
            columns={
                "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                "path": "TEXT NOT NULL",
                "version": "INTEGER NOT NULL DEFAULT 1",
                "project_id": "TEXT",
                "timestamp": "TEXT NOT NULL",
                "hash": "TEXT NOT NULL",
                "author": "TEXT",
                "reason": "TEXT",
                "status": "TEXT NOT NULL DEFAULT 'active'",
                "replaced_by": "INTEGER",
                "vector_id": "TEXT",
            },
            indices=[
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_planning_artifacts_path_version ON planning_artifacts(path, version)",
                "CREATE INDEX IF NOT EXISTS idx_planning_artifacts_project ON planning_artifacts(project_id)",
            ],
        )

        _ensure_table(
            cur,
            "plan_changes",
            """
            CREATE TABLE IF NOT EXISTS plan_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                phase_id TEXT,
                project_id TEXT,
                timestamp TEXT NOT NULL,
                author TEXT,
                summary TEXT NOT NULL,
                rationale TEXT,
                replaces_version INTEGER,
                status TEXT NOT NULL DEFAULT 'active',
                replaced_by INTEGER,
                vector_id TEXT
            )
            """,
            columns={
                "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                "run_id": "TEXT",
                "phase_id": "TEXT",
                "project_id": "TEXT",
                "timestamp": "TEXT NOT NULL",
                "author": "TEXT",
                "summary": "TEXT NOT NULL",
                "rationale": "TEXT",
                "replaces_version": "INTEGER",
                "status": "TEXT NOT NULL DEFAULT 'active'",
                "replaced_by": "INTEGER",
                "vector_id": "TEXT",
            },
            indices=[
                "CREATE INDEX IF NOT EXISTS idx_plan_changes_run ON plan_changes(run_id)",
                "CREATE INDEX IF NOT EXISTS idx_plan_changes_project ON plan_changes(project_id)",
            ],
        )

        _ensure_table(
            cur,
            "decision_log",
            """
            CREATE TABLE IF NOT EXISTS decision_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                phase_id TEXT,
                project_id TEXT,
                timestamp TEXT NOT NULL,
                trigger TEXT,
                alternatives TEXT,
                choice TEXT NOT NULL,
                rationale TEXT,
                vector_id TEXT
            )
            """,
            columns={
                "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                "run_id": "TEXT",
                "phase_id": "TEXT",
                "project_id": "TEXT",
                "timestamp": "TEXT NOT NULL",
                "trigger": "TEXT",
                "alternatives": "TEXT",
                "choice": "TEXT NOT NULL",
                "rationale": "TEXT",
                "vector_id": "TEXT",
            },
            indices=[
                "CREATE INDEX IF NOT EXISTS idx_decision_log_run ON decision_log(run_id)",
                "CREATE INDEX IF NOT EXISTS idx_decision_log_phase ON decision_log(phase_id)",
            ],
        )

        conn.commit()
        print("[OK] Planning/decision tables ensured.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
