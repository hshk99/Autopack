from __future__ import annotations

import sqlite3
from pathlib import Path


def main() -> int:
    db_path = Path("autopack.db")
    if not db_path.exists():
        print("autopack.db not found")
        return 1

    db = sqlite3.connect(str(db_path))
    try:
        cur = db.cursor()
        cur.execute(
            """
            select
              run_id,
              sum(case when state='QUEUED' then 1 else 0 end) as queued,
              sum(case when state='FAILED' then 1 else 0 end) as failed,
              sum(case when state='COMPLETE' then 1 else 0 end) as complete
            from phases
            group by run_id
            order by queued desc, failed desc
            """
        )
        rows = cur.fetchall()
    finally:
        db.close()

    print("run_id\tqueued\tfailed\tcomplete")
    for run_id, queued, failed, complete in rows:
        print(f"{run_id}\t{queued}\t{failed}\t{complete}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


