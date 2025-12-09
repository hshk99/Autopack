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
    def __init__(self, repo_root: Path, dsn: Optional[str] = None, project_id: Optional[str] = None):
        self.repo_root = repo_root
        self.dsn = dsn or os.getenv("DATABASE_URL")
        self.project_id = project_id
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
                project_id text,
                action text,
                src text,
                dest text,
                reason text,
                src_sha text,
                dest_sha text,
                ts timestamptz not null default now()
            );
            """
        )
        # make sure columns exist
        cur.execute("alter table tidy_activity add column if not exists project_id text;")
        cur.execute("alter table tidy_activity add column if not exists src_sha text;")
        cur.execute("alter table tidy_activity add column if not exists dest_sha text;")
        conn.commit()
        cur.close()
        conn.close()

    def log(self, run_id: str, action: str, src: str, dest: Optional[str], reason: str, src_sha: Optional[str] = None, dest_sha: Optional[str] = None):
        ts = datetime.now(timezone.utc).isoformat()
        if self.pg:
            try:
                conn = self.pg.connect(self.dsn)
                cur = conn.cursor()
                cur.execute(
                    "insert into tidy_activity (run_id, project_id, action, src, dest, reason, src_sha, dest_sha, ts) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (run_id, self.project_id, action, src, dest, reason, src_sha, dest_sha, ts),
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
            f.write(json.dumps({
                "run_id": run_id,
                "project_id": self.project_id,
                "action": action,
                "src": src,
                "dest": dest,
                "reason": reason,
                "src_sha": src_sha,
                "dest_sha": dest_sha,
                "ts": ts
            }) + "\n")

