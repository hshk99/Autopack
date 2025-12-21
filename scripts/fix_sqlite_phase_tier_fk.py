"""
Fix common SQLite FK mistakes for Autopack runs/tiers/phases.

Primary fix:
  - If a Phase row has `phases.tier_id` containing the *string* tier identifier
    (e.g. "research-t1") instead of the integer `tiers.id`, the executor's
    join (Phase -> Tier) will return no executable phases.

This script rewrites phases.tier_id to the correct tiers.id when it can infer it.

Usage (PowerShell):
  python scripts\\fix_sqlite_phase_tier_fk.py --db .\\autopack.db --dry-run
  python scripts\\fix_sqlite_phase_tier_fk.py --db .\\autopack.db
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def _connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("autopack.db"), help="Path to SQLite DB file")
    parser.add_argument("--dry-run", action="store_true", help="Print planned updates, don't write")
    args = parser.parse_args()

    db_path: Path = args.db
    if not db_path.exists():
        print(f"[ERROR] DB not found: {db_path.resolve()}")
        return 2

    con = _connect(db_path)
    cur = con.cursor()

    # Find phases where tier_id doesn't match any tiers.id for the same run
    rows = cur.execute(
        """
        SELECT
          p.id               AS phase_row_id,
          p.phase_id         AS phase_id,
          p.run_id           AS run_id,
          p.tier_id          AS phase_tier_id,
          typeof(p.tier_id)  AS tier_id_type
        FROM phases p
        LEFT JOIN tiers t
          ON t.id = p.tier_id
         AND t.run_id = p.run_id
        WHERE t.id IS NULL
        ORDER BY p.run_id, p.phase_index
        """
    ).fetchall()

    if not rows:
        print("[OK] No mismatched phase->tier foreign keys detected.")
        return 0

    planned = []
    for r in rows:
        phase_row_id = r["phase_row_id"]
        run_id = r["run_id"]
        phase_id = r["phase_id"]
        phase_tier_id = r["phase_tier_id"]

        # Try to interpret phases.tier_id as the *string* tiers.tier_id.
        tier_match = cur.execute(
            """
            SELECT id, tier_id
            FROM tiers
            WHERE run_id = ? AND tier_id = ?
            LIMIT 1
            """,
            (run_id, str(phase_tier_id)),
        ).fetchone()

        if tier_match:
            planned.append(
                {
                    "phase_row_id": phase_row_id,
                    "run_id": run_id,
                    "phase_id": phase_id,
                    "from": phase_tier_id,
                    "to": tier_match["id"],
                    "tier_id": tier_match["tier_id"],
                }
            )

    if not planned:
        print("[WARN] Found phases with mismatched tier_id, but couldn't infer fixes automatically.")
        print("       This usually means phases.tier_id is wrong *and* doesn't match tiers.tier_id.")
        return 1

    print(f"[INFO] Planned fixes: {len(planned)}")
    for p in planned:
        print(
            f"  - run={p['run_id']} phase={p['phase_id']} phases.tier_id {p['from']!r} -> {p['to']} (tiers.tier_id={p['tier_id']})"
        )

    if args.dry_run:
        print("[DRY-RUN] No changes written.")
        return 0

    cur.execute("BEGIN")
    try:
        for p in planned:
            cur.execute(
                "UPDATE phases SET tier_id = ? WHERE id = ?",
                (int(p["to"]), int(p["phase_row_id"])),
            )
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    print("[OK] Updates committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


