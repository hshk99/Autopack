## Drain Report (to takeover prompt author)

**Date**: 2025-12-28 (local)

### Session goal

Drain queued phases in tiny batches with telemetry enabled, only fixing **systemic drain blockers** (parser/apply/scope/API/DB/CI harness/finalizer). Treat run-specific failures as **real gates** unless the same failure signature blocks draining broadly.

### Selection policy used

- **Run selection**: P10-first (truncation-risk-biased) when possible, falling back to highest queued count.
- **Implementation**: `scripts/pick_next_run.py` (commit `cf80358c`).

### Drains executed (this session)

- **`research-system-v20`** (`project_build`)
  - Result: **queued 1 → 0** (phase completed).
  - Notes: Observed **100% token utilization + truncation** and NDJSON partial parse, but apply/validation succeeded and phase finalized.
  - References:
    - CI log: `.autonomous_runs/research-system-v20/ci/pytest_research-foundation-intent-discovery.log`
    - CI report: `.autonomous_runs/research-system-v20/ci/pytest_research-foundation-intent-discovery.json`
    - Phase summary: `.autonomous_runs/autopack/runs/research-system-v20/phases/phase_01_research-foundation-intent-discovery.md`

- **`research-system-v26`** (`project_build`)
  - Result: **queued 1 → 0** (phase `research-testing-polish` completed).
  - Notes: Similar truncation/NDJSON partial parse pattern; CI failed but phase finalized via existing policy (no systemic blocker).
  - References:
    - CI log: `.autonomous_runs/research-system-v26/ci/pytest_research-testing-polish.log`
    - CI report: `.autonomous_runs/research-system-v26/ci/pytest_research-testing-polish.json`
    - Phase summary: `.autonomous_runs/autopack/runs/research-system-v26/phases/phase_00_research-testing-polish.md`

- **`research-system-v29`** (`project_build`)
  - Result: **queued 1 → 0**.
  - Outcome: **real gate** – PhaseFinalizer correctly blocked on **pytest collection/import errors** (exit code 2, failed collectors / ImportError). No systemic fix applied.
  - References:
    - CI log (shows “10 errors during collection”): `.autonomous_runs/research-system-v29/ci/pytest_research-testing-polish.log`
    - CI report: `.autonomous_runs/research-system-v29/ci/pytest_research-testing-polish.json`

- **`build112-completion`** (`autopack_maintenance` by heuristic)
  - Result: **queued 1 → 0** (phase `build112-phase5-dashboard-pause-resume` completed).
  - Notes: Builder emitted a JSON `{"files":[...]}` blob (not a diff), then structured-edit fallback produced **no operations** (no-op). This did not block draining under the current finalization/override policy; treated as run-specific behavior, not systemic.
  - References:
    - CI log: `.autonomous_runs/build112-completion/ci/pytest_build112-phase5-dashboard-pause-resume.log`
    - CI report: `.autonomous_runs/build112-completion/ci/pytest_build112-phase5-dashboard-pause-resume.json`
    - Phase summary: `.autonomous_runs/autopack/runs/build112-completion/phases/phase_03_build112-phase5-dashboard-pause-resume.md`

- **`scope-smoke-20251206184302`** (`project_build`)
  - Result: **queued 1 → 0** (P1 completed).
  - Notes: Extremely large context; structured edit used on `README.md`. CI failed but finalized via existing policy.
  - References:
    - CI log: `.autonomous_runs/scope-smoke-20251206184302/ci/pytest_P1.log`
    - CI report: `.autonomous_runs/scope-smoke-20251206184302/ci/pytest_P1.json`

- **`research-system-v1`** (`project_build`)
  - Initial attempt: **systemic drain blocker** – executor could not fetch run status because the Supervisor API returned **500** for `GET /runs/research-system-v1`.
  - **Systemic fix applied** (commit `5a29b35c`):
    - Root cause: legacy runs can persist `Phase.scope` as a **string** (JSON string or plain string). API `response_model=RunResponse` nests `PhaseResponse.scope: Dict` → Pydantic validation/serialization failure → 500.
    - Fix: normalize `PhaseResponse.scope` to coerce non-dict inputs into a dict (parse JSON-string dicts when possible; otherwise store under `_legacy_text` / `_legacy_value`).
    - Tests: `tests/test_api_schema_scope_normalization.py`.
    - SOT updates: `BUILD_LOG.md`, `docs/BUILD_HISTORY.md`, `docs/BUILD-129_PHASE3_DRAIN_SYSTEMIC_BLOCKERS_RCA.md` (Blocker Q), plus DB export sync.
  - Post-fix re-run: `research-system-v1` drained to **queued 1 → 0** (phase executed; ended with `REPLAN_REQUESTED` but no queued phases remained).
  - References:
    - CI log: `.autonomous_runs/research-system-v1/ci/pytest_research-tracer-bullet.log`
    - CI report: `.autonomous_runs/research-system-v1/ci/pytest_research-tracer-bullet.json`
    - API-500 fix commit: `5a29b35c`

### Systemic changes delivered this session

- **P10-first “next run” selector**: `scripts/pick_next_run.py` + unit tests + README mention (commit `cf80358c`).
- **API robustness for legacy string phase scopes**: `PhaseResponse.scope` normalization + tests + SOT/DB sync (commit `5a29b35c`).

### SOT recording policy followed

- For **systemic fixes**: added tests + updated SOT docs + ran DB/SOT sync scripts, then committed.
- For **drain-only / real gate** outcomes: did not modify SOT beyond what the executor already records (DB state, `.autonomous_runs` artifacts). The final report aggregates those drains and references the relevant systemic commits.

### End state

At end of session, `scripts/list_run_counts.py` reported **queued=0 for all runs**.


