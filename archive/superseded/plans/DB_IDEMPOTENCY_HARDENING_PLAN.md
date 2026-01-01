# DB Idempotency Hardening Plan (Beyond README “Ideal State”)

**Scope**: Production-hardening improvements that go beyond the current `README.md` “ideal state”, focused on **PostgreSQL** as the primary DB.  
**Note**: SQLite is used primarily for **tests/dev**; **Qdrant** is used for **semantic retrieval/vector memory** and is not part of this relational-telemetry hardening.

---

## Objective

Make token-efficiency telemetry idempotency **provably correct under concurrency** by enforcing uniqueness at the database level and making the write path race-safe.

Current behavior (app-level guard) prevents most duplicates across retries/crashes, but **can still duplicate under concurrent writers** (classic “check then insert” race). This plan closes that gap.

---

## Target Behavior

- For terminal outcomes (when `phase_outcome` is set), there must be **at most one** row in `token_efficiency_metrics` per:
  - `(run_id, phase_id, phase_outcome)`
- When the code attempts to record the same terminal outcome multiple times (retry, crash recovery, parallel worker, etc.), it should:
  - **Return the existing record** without error
  - **Not create duplicates**
- Backward compatibility:
  - If `phase_outcome` is `NULL`, do **not** enforce uniqueness (older callers / legacy paths).

---

## Work Items (Implementation Plan)

### A) Add a DB-level uniqueness guarantee (PostgreSQL)

Create a migration that adds a **partial unique index**:

- **Index**: `ux_token_eff_metrics_run_phase_outcome`
- **Table**: `token_efficiency_metrics`
- **Columns**: `(run_id, phase_id, phase_outcome)`
- **Predicate**: `WHERE phase_outcome IS NOT NULL`

**Postgres SQL**

```sql
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_token_eff_metrics_run_phase_outcome
ON token_efficiency_metrics (run_id, phase_id, phase_outcome)
WHERE phase_outcome IS NOT NULL;
```

**Why partial?**
- Avoid changing semantics for legacy rows where `phase_outcome` is `NULL`.
- Prevents uniqueness enforcement from accidentally impacting older recording paths.

**Migration considerations**
- `CREATE INDEX CONCURRENTLY` **cannot run inside a transaction**.
- Use SQLAlchemy connection autocommit / non-transactional execution for this statement.

---

### B) Make the application insert path race-safe

Update `src/autopack/usage_recorder.py` → `record_token_efficiency_metrics(...)`:

1) Keep existing fast-path:
   - If `phase_outcome` is set, query for existing `(run_id, phase_id, phase_outcome)` and return it.
2) Attempt insert/commit.
3) If commit fails with `sqlalchemy.exc.IntegrityError`:
   - `rollback()`
   - Re-query for existing record and return it.

This ensures:
- Fast under normal conditions (no extra DB work when existing row already present).
- Correct under concurrency (DB enforces uniqueness; app recovers cleanly).

---

### C) Tests

#### C1) Unit test: IntegrityError fallback

Extend `tests/autopack/test_token_efficiency_observability.py` with a test that:
- Inserts an initial record for `(run_id, phase_id, phase_outcome="COMPLETE")`
- Then forces a second “insert” attempt to raise `IntegrityError` on `commit` (mock)
- Verifies `record_token_efficiency_metrics()` returns the existing row and does not raise.

This gives deterministic coverage without requiring a real concurrent writer.

#### C2) Optional integration test (if Postgres test infra exists)

Validate that the unique index exists and blocks duplicates under actual DB behavior.

---

### D) Upgrade smoke/preflight checks (optional but recommended)

Update `scripts/smoke_autonomy_features.py` to improve operator safety:

- **Schema check**: ensure `token_efficiency_metrics.phase_outcome` exists.
- **Index check (best-effort)**: detect whether `ux_token_eff_metrics_run_phase_outcome` exists.
  - Postgres: query `pg_indexes`
  - SQLite: query `sqlite_master`
- If missing (and running in “production mode”): mark **NO-GO** with an explicit migration command to run.

Also add a config-footgun check:
- If both canonical and legacy env vars are set for the same feature flag but disagree → **NO-GO** (ambiguous).

---

## Skeleton Structure (What to Create / Modify)

### 1) New migration script

Create:
- `scripts/migrations/add_token_efficiency_idempotency_index_build146_p17x.py`

Skeleton (illustrative)

```python
from __future__ import annotations

import os
from sqlalchemy import create_engine, text

def _require_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required (no silent fallback).")
    return url

def _run_autocommit(engine, sql: str) -> None:
    with engine.connect() as conn:
        # Postgres CONCURRENTLY must be non-transactional:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(sql))

def upgrade() -> None:
    engine = create_engine(_require_database_url())
    dialect = engine.dialect.name
    if dialect == "postgresql":
        _run_autocommit(
            engine,
            \"\"\"
            CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS ux_token_eff_metrics_run_phase_outcome
            ON token_efficiency_metrics (run_id, phase_id, phase_outcome)
            WHERE phase_outcome IS NOT NULL
            \"\"\",
        )
    elif dialect == "sqlite":
        # Best-effort (partial indexes may or may not be supported depending on SQLite version).
        with engine.begin() as conn:
            conn.execute(text(
                \"\"\"
                CREATE UNIQUE INDEX IF NOT EXISTS ux_token_eff_metrics_run_phase_outcome
                ON token_efficiency_metrics (run_id, phase_id, phase_outcome)
                WHERE phase_outcome IS NOT NULL
                \"\"\"
            ))
    else:
        raise SystemExit(f"Unsupported dialect: {dialect}")

def downgrade() -> None:
    engine = create_engine(_require_database_url())
    with engine.begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS ux_token_eff_metrics_run_phase_outcome"))
```

### 2) Update usage recorder

Modify:
- `src/autopack/usage_recorder.py`

Add:
- `from sqlalchemy.exc import IntegrityError`
- `try/except IntegrityError` around commit with rollback + re-query.

### 3) Tests

Modify:
- `tests/autopack/test_token_efficiency_observability.py`

Add:
- A new test under `TestTelemetryInvariants` (or adjacent) validating the IntegrityError fallback.

### 4) Smoke test (optional)

Modify:
- `scripts/smoke_autonomy_features.py`

Add:
- Index presence check + env var conflict detection.

---

## Watch-outs / Pitfalls

- **Postgres `CREATE INDEX CONCURRENTLY`**:
  - Must run outside transactions. Ensure autocommit is used.
- **Partial unique index correctness**:
  - Ensure the predicate is exactly `phase_outcome IS NOT NULL`.
  - Do not enforce uniqueness for `NULL` outcomes (backward compatibility).
- **IntegrityError handling**:
  - Must `rollback()` before re-querying.
  - Re-query must use the same `(run_id, phase_id, phase_outcome)` key.
- **Operational doc alignment**:
  - If you add a new migration, update rollout docs to mention it (or have smoke test point to it).

---

## Acceptance Criteria

- Migration adds the Postgres partial unique index successfully.
- `record_token_efficiency_metrics()` is race-safe and returns existing record on uniqueness conflicts.
- Unit tests cover the IntegrityError path.
- (Optional) smoke test can detect missing index/schema and clearly reports GO/NO-GO with next steps.


