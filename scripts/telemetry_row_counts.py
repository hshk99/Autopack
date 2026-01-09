"""
Telemetry Row Count Helper

Purpose:
- Print row counts for key telemetry tables (SQLite/Postgres).
- Optionally record snapshots to a JSONL log to make before/after deltas trivial.

Usage (PowerShell):
  # Snapshot "before" (and log it)
  python scripts/telemetry_row_counts.py --label before

  # ... run drain batches ...

  # Snapshot "after" and show delta vs "before"
  python scripts/telemetry_row_counts.py --label after --compare-to before

Optional:
  # Limit counts to a specific run_id (if table has run_id column)
  python scripts/telemetry_row_counts.py --run-id research-system-v4 --label after --compare-to before
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import create_engine, inspect, text


DEFAULT_TABLES = [
    "token_estimation_v2_events",
    "token_budget_escalation_events",
]


@dataclass(frozen=True)
class Snapshot:
    timestamp: str
    database_url: str
    run_id: Optional[str]
    label: Optional[str]
    counts: Dict[str, Optional[int]]


def _default_database_url() -> Optional[str]:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    db_path = Path("autopack.db")
    if db_path.exists():
        return "sqlite:///autopack.db"
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_has_column(engine, table: str, column: str) -> bool:
    try:
        insp = inspect(engine)
        cols = insp.get_columns(table)
        return any(c.get("name") == column for c in cols)
    except Exception:
        return False


def _count_rows(engine, table: str, run_id: Optional[str]) -> Optional[int]:
    insp = inspect(engine)
    if table not in insp.get_table_names():
        return None

    if run_id and _table_has_column(engine, table, "run_id"):
        q = text(f"SELECT COUNT(*) AS c FROM {table} WHERE run_id = :run_id")
        with engine.connect() as conn:
            return int(conn.execute(q, {"run_id": run_id}).scalar_one())

    q = text(f"SELECT COUNT(*) AS c FROM {table}")
    with engine.connect() as conn:
        return int(conn.execute(q).scalar_one())


def _load_last_snapshot(log_path: Path, compare_to: str, database_url: str, run_id: Optional[str]) -> Optional[Snapshot]:
    if not log_path.exists():
        return None
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except Exception:
            continue
        if data.get("label") != compare_to:
            continue
        if data.get("database_url") != database_url:
            continue
        if data.get("run_id") != run_id:
            continue
        try:
            return Snapshot(
                timestamp=str(data["timestamp"]),
                database_url=str(data["database_url"]),
                run_id=data.get("run_id"),
                label=data.get("label"),
                counts=dict(data.get("counts", {})),
            )
        except Exception:
            return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Print telemetry table row counts (optionally log snapshots for deltas).")
    ap.add_argument("--run-id", default=None, help="Optional: count only rows for this run_id when table supports it.")
    ap.add_argument("--label", default=None, help="Optional label (e.g., before/after). If set, snapshot is logged.")
    ap.add_argument("--compare-to", default=None, help="If set, compute delta vs the most recent snapshot with this label.")
    ap.add_argument(
        "--log-path",
        default=str(Path(".autonomous_runs") / "telemetry_counts.jsonl"),
        help="Where to append snapshot JSONL entries (default: .autonomous_runs/telemetry_counts.jsonl).",
    )
    ap.add_argument(
        "--tables",
        nargs="*",
        default=DEFAULT_TABLES,
        help=f"Table names to count (default: {', '.join(DEFAULT_TABLES)})",
    )
    args = ap.parse_args()

    db_url = _default_database_url()
    if not db_url:
        print("[telemetry_counts] ERROR: DATABASE_URL not set and autopack.db not found in cwd.")
        return 2

    engine = create_engine(db_url)

    counts: Dict[str, Optional[int]] = {}
    for t in args.tables:
        try:
            counts[t] = _count_rows(engine, t, args.run_id)
        except Exception as e:
            print(f"[telemetry_counts] WARN: failed to count table={t}: {e}")
            counts[t] = None

    snap = Snapshot(
        timestamp=_now_iso(),
        database_url=db_url,
        run_id=args.run_id,
        label=args.label,
        counts=counts,
    )

    # Print summary
    print("[telemetry_counts] Database:", db_url)
    if args.run_id:
        print("[telemetry_counts] Run ID:", args.run_id)
    if args.label:
        print("[telemetry_counts] Label:", args.label)
    print()
    for t in args.tables:
        v = counts.get(t)
        if v is None:
            print(f"- {t}: (missing table or error)")
        else:
            print(f"- {t}: {v}")

    # Compare delta
    if args.compare_to:
        log_path = Path(args.log_path)
        prev = _load_last_snapshot(log_path, args.compare_to, db_url, args.run_id)
        print()
        if not prev:
            print(f"[telemetry_counts] No prior snapshot found for compare-to='{args.compare_to}' (same DB + run-id).")
        else:
            print(f"[telemetry_counts] Delta vs '{args.compare_to}' ({prev.timestamp}):")
            for t in args.tables:
                before = prev.counts.get(t)
                after = counts.get(t)
                if before is None or after is None:
                    print(f"- {t}: (delta unavailable)")
                else:
                    print(f"- {t}: +{after - before} (from {before} → {after})")

    # Persist snapshot
    if args.label:
        log_path = Path(args.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "timestamp": snap.timestamp,
                        "database_url": snap.database_url,
                        "run_id": snap.run_id,
                        "label": snap.label,
                        "counts": snap.counts,
                    },
                    ensure_ascii=True,
                )
                + "\n"
            )
        print(f"\n[telemetry_counts] Logged snapshot → {log_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


