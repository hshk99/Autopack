#!/usr/bin/env python3
"""
Lightweight tidy activity logger.
Logs to Postgres if DATABASE_URL is set, otherwise to a JSONL file in .autonomous_runs/tidy_activity.log
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any


class TidyLogger:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.dsn = os.getenv("DATABASE_URL")
        self.pg = None
        if self.dsn and self.dsn.startswith("postgres"):
            try:
                import psycopg2  # type: ignore
                self.pg = psycopg2
                self._ensure_table()
            except Exception:
                self.pg = None
        self.fallback = repo_root / ".autonomous_runs" / "tidy_activity.log"

    def _ensure_table(self):
        conn = self.pg.connect(self.dsn)
        cur = conn.cursor()
        cur.execute(
            """
            create table if not exists tidy_activity (
                id serial primary key,
                run_id text,
                action text,
                src text,
                dest text,
                reason text,
                ts timestamptz not null default now()
            );
            """
        )
        conn.commit()
        cur.close()
        conn.close()

    def log(self, run_id: str, action: str, src: str, dest: Optional[str], reason: str):
        ts = datetime.now(timezone.utc).isoformat()
        if self.pg:
            try:
                conn = self.pg.connect(self.dsn)
                cur = conn.cursor()
                cur.execute(
                    "insert into tidy_activity (run_id, action, src, dest, reason, ts) values (%s,%s,%s,%s,%s,%s)",
                    (run_id, action, src, dest, reason, ts),
                )
                conn.commit()
                cur.close()
                conn.close()
                return
            except Exception:
                pass
        # fallback JSONL
        self.fallback.parent.mkdir(parents=True, exist_ok=True)
        with self.fallback.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"run_id": run_id, "action": action, "src": src, "dest": dest, "reason": reason, "ts": ts}) + "\n")

