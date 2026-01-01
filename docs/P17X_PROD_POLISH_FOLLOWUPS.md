# P17.x Production Polish Follow-ups (Doc + Ops + Optional Postgres Test)

Audience: **you** (the implementer).

This doc captures a small set of “finish the edges” tasks to keep the repo aligned with the `README.md` ideal-state and to reduce production rollout risk.

**Hard constraint**: Do **not** delete information; only clarify/move/append.

---

## What is already done (verify before changing)

- README drift fixed:
  - “20 tests” → **53 tests**
  - P17.x bullet list present
  - Dashboard DB examples labeled **dev vs production**
- Rollout checklist includes **duplicate-detector SQL**
- Smoke test checks idempotency index and prints the migration command when missing:
  - `python scripts/migrations/add_token_efficiency_idempotency_index_build146_p17x.py upgrade`

If any of the above is missing in your current branch, implement it; otherwise skip.

---

## Remaining tasks (implement)

### A) Make idempotency migration dependency “canonical” everywhere

Goal: An operator should never wonder which migration to run for P17.x.

1) **Smoke test** (`scripts/smoke_autonomy_features.py`)
   - Ensure the “missing index” message includes:
     - the exact migration filename (already does)
     - a short hint that Postgres is production DB and SQLite is dev/test
   - If it doesn’t, update message text only.

2) **Rollout docs** (`docs/PRODUCTION_ROLLOUT_CHECKLIST.md`)
   - Add a short bullet under Stage 0 “Pre-Production Validation”:
     - “Verify P17.x idempotency index present; if missing run migration: …”

Acceptance:
- Operator copy/pastes the migration command from either smoke test output or rollout checklist.

---

### B) Optional: Postgres integration test for the unique index (if infra exists)

Goal: Stronger than mock-based IntegrityError tests; validate **real DB enforcement**.

Create:
- `tests/integration/test_token_efficiency_idempotency_index_postgres.py`

Behavior:
- The test should run **only** when a Postgres DSN is explicitly provided, e.g.:
  - `DATABASE_URL` starts with `postgresql://`
  - or `AUTOPACK_TEST_POSTGRES=1`
- Otherwise: `pytest.skip(...)` (do not fail CI by default).

Test cases:
1) Assert index exists:
   - Query `pg_indexes` for `ux_token_eff_metrics_run_phase_outcome`
2) Assert duplicates are prevented:
   - Insert a row into `token_efficiency_metrics` with `phase_outcome='COMPLETE'`
   - Attempt to insert the same `(run_id, phase_id, phase_outcome)` again
   - Expect unique violation (SQLAlchemy `IntegrityError`) and confirm only one row exists

Notes:
- Use SQLAlchemy engine/session consistent with existing test utilities.
- Ensure migration has been run or create index within test setup if acceptable.

Acceptance:
- With Postgres test env, test passes and proves the index is effective.
- Without Postgres, test is skipped (no noise).

---

### C) Operational monitoring query (already added)

This is already in `docs/PRODUCTION_ROLLOUT_CHECKLIST.md`:
- Duplicate-detector query for `(run_id, phase_id, phase_outcome)` where `phase_outcome IS NOT NULL`.

If missing, add it (but in this repo it should already exist).

---

## Suggested prompt (copy/paste)

> Implement the remaining P17.x production polish follow-ups described in `docs/P17X_PROD_POLISH_FOLLOWUPS.md`.  
> Constraints: don’t delete information; prefer small doc changes; Postgres integration test must be opt-in/skip by default; keep operator guidance copy/pasteable.  
> Deliverables: rollout doc clarification + (optional) Postgres integration test validating index existence and uniqueness enforcement.


