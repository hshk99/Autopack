# BUILD-179 (PLAN): Autonomy CLI + Supervisor Consolidation (Library-First, Safe Parallelism)

**Status**: PLANNED
**Priority**: High (operator UX + governance consistency)
**Related**: BUILD-178 (Pivot Intentions v2 + Gap/Plan/Autopilot/Parallelism Gate), `docs/GOVERNANCE.md`, `docs/PARALLEL_RUNS.md`, `scripts/autopack_supervisor.py`
**Aligned to README ideal state**: safe, deterministic, mechanically enforceable; SOT-led memory; execution writes run-local; explicit gates; parallelism only under Four-Layer model.

---

## Why (gap vs ideal state)

BUILD-178 delivered the **core autonomy artifacts and gates**, but daily usage still requires mixing:
- `python -m autopack.gaps ...`
- `python -m autopack.planning ...`
- `python -m autopack.autonomy ...`
- plus a separate parallel-run entrypoint (`scripts/autopack_supervisor.py`)

This increases the chance of:
- duplicated/competing policy logic
- operator confusion (which entrypoint is canonical?)
- governance drift (default-deny in one tool, missing in another)

**Ideal state per README** is “mechanically enforceable contracts + one stream flow,” which is best served by a **library-first core** with **thin, canonical CLI wrappers** and a **single concurrency orchestration surface** that respects intention gates.

---

## Direction (no ambiguity)

1. **Library-first**: All behavior lives in importable, unit-testable modules; CLIs are thin wrappers.
2. **One canonical operator CLI**: `python -m autopack.cli ...` becomes the primary entrypoint for autonomy loop operations.
3. **Parallel execution remains process-isolated** for workers (subprocess per run) to preserve safety and reduce cross-run contamination.
4. **Parallelism is gated by intention**: multi-run concurrency is allowed only if `IntentionAnchorV2.pivot_intentions.parallelism_isolation.allowed == true` and Four-Layer isolation is used.
5. **No autonomous SOT writes**: all new tooling writes run-local artifacts only; tidy remains the consolidator with `--execute` gates.

---

## Scope

### In scope
- Add CLI commands under Autopack’s CLI package for:
  - gap scanning
  - plan proposing
  - autopilot sessions (single-run)
  - supervised parallel runs (multi-run)
- Move “supervisor” orchestration logic into a library module (keep `scripts/autopack_supervisor.py` as a thin wrapper).
- Enforce parallelism policy gate **before** spawning workers.
- Add/refresh docs so operators can run the loop safely without reading source code.

### Not in scope
- Parallel phases within a single run (still “not recommended” per `docs/PARALLEL_RUNS.md`).
- Changing the executor core (`src/autopack/autonomous_executor.py`) behavior.
- Making tidy run concurrently with autopilot by default (requires per-subsystem lock ordering; defer unless scheduled concurrency is needed).

---

## Proposed skeleton structure (target layout)

```text
src/autopack/
  autonomy/
    api.py                      # NEW: library façade used by CLI (no subprocess)

  gaps/
    api.py                      # NEW: scan_gaps(...) wrapper around scanner

  planning/
    api.py                      # NEW: propose_plan(...) wrapper around proposer

  supervisor/
    __init__.py                 # NEW
    parallel_run_supervisor.py  # NEW: library port of scripts/autopack_supervisor.py
    models.py                   # NEW: typed results for run outcomes

  cli/
    commands/
      autonomy.py               # NEW: autopilot run + supervise wrappers
      gaps.py                   # NEW: gaps scan wrapper
      planning.py               # NEW: plan propose wrapper
      supervisor.py             # NEW: supervise wrapper (multi-run)
```

```text
scripts/
  autopack_supervisor.py        # refactor to call src/autopack/supervisor/parallel_run_supervisor.py
```

```text
docs/
  AUTOPILOT_OPERATIONS.md       # NEW operator runbook (minimal, high-signal)
  GOVERNANCE.md                 # UPDATE: map new artifacts + gates, refresh last-updated
  INDEX.md                      # UPDATE: link this BUILD-179 plan and ops doc
  FUTURE_PLAN.md                # UPDATE: mark BUILD-178 complete; add BUILD-179 planned
```

---

## Implementation steps (ordered)

### Step 1 — Add library façades (no new behavior)
- `src/autopack/gaps/api.py`: `scan_gaps(run_id, project_id, *, write: bool, ...) -> GapReportV1`
- `src/autopack/planning/api.py`: `propose_plan(anchor, gap_report, *, write: bool, ...) -> PlanProposalV1`
- `src/autopack/autonomy/api.py`: `run_autopilot_session(..., enable: bool, write: bool, ...) -> AutopilotSessionV1`

**Acceptance criteria**
- Pure wrappers, no duplicated logic.
- Easy to unit test without subprocess.

### Step 2 — Promote supervisor to library + enforce parallelism policy
- Create `src/autopack/supervisor/parallel_run_supervisor.py` by porting `scripts/autopack_supervisor.py`.
- Add an explicit gate in the supervisor path:
  - load/require `IntentionAnchorV2` (explicit `--anchor-path` or deterministic run-local path)
  - call `ParallelismPolicyGate.check_parallel_allowed(requested_runs=workers)` when `workers > 1`
  - fail-fast with actionable guidance if blocked.

**Acceptance criteria**
- `workers > 1` cannot run unless the intention explicitly allows parallelism.
- Four-Layer isolation remains unchanged (worktrees + leases + per-run locks + run-scoped artifacts).

### Step 3 — Add canonical CLI commands
- Extend `src/autopack/cli/` to include the new subcommands (thin wrappers).
- Ensure all commands support:
  - report-only default (no writes unless `--write` / `--execute` where applicable)
  - explicit `--enable` for autopilot execution.

**Acceptance criteria**
- Operators can run the full loop via one CLI surface.
- CLI help text is safe-by-default and explicit about risk.

### Step 4 — Documentation wiring (SOT-aligned)
- Add `docs/AUTOPILOT_OPERATIONS.md` with copy/paste commands and “what happens / what gets written where”.
- Update `docs/GOVERNANCE.md` to explicitly reference:
  - `GapReportV1` → `PlanProposalV1` → gated execution or approval request
  - default-deny posture remains authoritative.

---

## Testing / Verification plan (mechanical)

### Must-pass (CI-blocking)
- CLI parsing + dry-run behavior:
  - `autopack gaps scan` returns stable JSON, no writes without `--write`
  - `autopack plan propose` default-deny behavior unchanged
  - `autopack autopilot run` refuses execution without `--enable`
  - `autopack autopilot supervise --workers >1` fails unless parallelism allowed
- Existing schema contract tests remain green.
- Existing governance + parallelism tests remain green.

### Informational
- “Supervisor integration smoke” test that runs in a temp workspace (skip if git worktree unavailable).

---

## Failure modes (how it must fail)
- If parallelism policy is absent/disabled: fail fast before spawning workers.
- If anchor is missing: refuse to guess; print bounded instructions to generate/locate it.
- If write flags are missing: remain read-only and succeed (report-only).

---

## Rollback strategy
- Keep `scripts/autopack_supervisor.py` as the stable entrypoint initially; refactor it to call the library.
- If issues appear, revert the wrapper change and keep the old script behavior while retaining library modules for testing.
