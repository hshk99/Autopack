## Batch Drain Reliability & Efficiency Plan (Autopack)

**Audience**: “other cursor” implementing drain + telemetry hardening on Windows for the 57-run backlog.  
**Goal**: Make batch draining *reliable*, *diagnosable*, and *fast enough* to generate high-quality telemetry aligned with `README.md` expectations (reduced log hunting, deterministic evidence, token-efficient operation).

---

## Why this plan exists (problem statement)

We observed multiple batches where phases ended `FAILED` with `last_failure_reason=None` and the controller reported `"Unknown error"`. This is not acceptable for large-scale draining because:

- It violates the repo’s stated objective of **reducing log hunting** (collector digest, persisted artifacts, etc.).
- It prevents meaningful telemetry analysis (we can’t distinguish infra failures vs deterministic blocks vs test regressions).
- It risks operational mistakes (e.g., retrying “FAILED” but draining a different phase when multiple phases are `QUEUED`).
- It wastes time and tokens indirectly by forcing manual forensics and repeated retries.

---

## Implementation Plan (with reasons)

### A) Observability hardening (highest priority)

#### A1) Persist subprocess outcome into the session JSON
**Change**
- Extend `DrainResult` (in `scripts/batch_drain_controller.py`) with fields:
  - `subprocess_returncode: int | None`
  - `subprocess_duration_seconds: float | None`
  - `subprocess_stdout_path: str | None`
  - `subprocess_stderr_path: str | None`
  - `subprocess_stdout_excerpt: str | None`
  - `subprocess_stderr_excerpt: str | None`

**Reason**
- When `last_failure_reason` is empty, the *subprocess* is the ground truth.
- Without return code + logs, “Unknown error” is indistinguishable from “didn’t run” vs “crashed immediately”.

**Acceptance**
- Every processed phase has `returncode` + `duration_seconds` recorded in the session JSON.

#### A2) Always write full stdout/stderr to disk (per phase)
**Change**
- For each drain attempt, save logs under:
  - `.autonomous_runs/batch_drain_sessions/<session_id>/logs/<run_id>__<phase_id>.stdout.txt`
  - `.autonomous_runs/batch_drain_sessions/<session_id>/logs/<run_id>__<phase_id>.stderr.txt`
- Include these paths in the session JSON fields above.

**Reason**
- Makes RCA scalable: you can open one file and immediately see what happened.
- Removes dependence on ephemeral temp files that may be cleaned up.

**Acceptance**
- For any failure, there is always a durable stderr log path to inspect.

#### A3) Eliminate “Unknown error” as a default
**Change**
- If `phase.last_failure_reason` is empty:
  - If `returncode != 0`, set `error_message` to include `returncode` + `stderr_path`.
  - Else, set `error_message` to include `stdout_path` (because “exit 0 but not complete” is suspicious and should be investigated).

**Reason**
- “Unknown error” is an anti-feature: it indicates we failed to capture the real signal.

**Acceptance**
- After changes, “Unknown error” should be near-zero; if present, it must include paths to logs and a return code.

---

### B) Environment consistency (Windows-safe)

#### B1) Force UTF-8 environment for subprocess drains
**Change**
- When building the env passed to `subprocess.run`, set:
  - `PYTHONUTF8=1`
  - `PYTHONIOENCODING=utf-8`

**Reason**
- Prevent silent early failures or empty/stunted outputs due to Windows console encoding.

**Acceptance**
- No drain attempt fails due to encoding issues; stderr logs show no UnicodeEncodeError.

#### B2) Make DB identity explicit (avoid mismatched API/DB)
**Change**
- Ensure every drain subprocess inherits the same `DATABASE_URL` as the controller.
- Add a short header print in `drain_one_phase.py`:
  - effective `DATABASE_URL` (or sqlite path)
  - effective `AUTOPACK_API_URL`

**Reason**
- A large class of “nothing happened” issues come from API pointing at a different DB than the controller.

**Acceptance**
- Every per-phase stdout log includes DB + API identity at the top.

---

### C) Correctness & safety (avoid draining the wrong phase)

#### C1) Keep safety default: skip runs that already have queued phases
**Change**
- Use the existing controller default: `--skip-runs-with-queued` ON (do not disable unless explicitly needed).

**Reason**
- The executor always selects the earliest `QUEUED` phase; retrying a `FAILED` phase by requeueing can cause the executor to run a different phase first.

**Acceptance**
- Batch drain never requeues into a run that already has `queued>0` unless operator explicitly overrides.

#### C2) Operational workflow: “queued first, then failed retries”
**Change**
- Runs with `queued>0` should be processed with `scripts/drain_queued_phases.py`.
- Batch controller should primarily process `FAILED` phases for runs with `queued=0`.

**Reason**
- Keeps phase selection deterministic and avoids “we retried X but drained Y”.

**Acceptance**
- In reports, runs processed via batch drain show `queued=0` at the moment of retry.

---

### D) Throughput improvements (reduce wasted time; indirectly token-efficient)

#### D1) Reduce repeated baseline capture costs
**Change options (choose one)**
- Option 1 (preferred): Cache T0 baseline by commit hash across runs/processes.
- Option 2: Add a drain-mode knob (`AUTOPACK_SKIP_BASELINE=1`) if acceptable for telemetry-focused drains.

**Reason**
- Re-capturing baselines per phase dramatically slows draining and reduces the number of telemetry samples you can collect per hour.

**Acceptance**
- Over a 10-phase batch, baseline capture should happen at most once per unique commit (or be intentionally disabled in drain-mode with justification).

#### D2) Reuse a single API server
**Change**
- For controller runs, pass `--api-url http://127.0.0.1:8000` (or other stable port) and ensure it points to the same DB.

**Reason**
- Prevents spawning dozens of detached uvicorn processes on Windows (ephemeral port per drain).

**Acceptance**
- During a long drain session, uvicorn process count remains stable (no runaway process spawning).

---

### E) SOT + tidy alignment (repo hygiene)

#### E1) Confirm tidy “protected/exclusive” file behavior and keep it consistent
**Current protected example**
- `.autonomous_runs` root cleanup protects `api_server.log` so tidy won’t move/delete an active API log.

**Reason**
- Prevents tidy from breaking active operations.

**Acceptance**
- Running tidy/cleanup in dry-run mode shows protected items are not moved/deleted.

---

## Operator prompt for the other cursor (copy/paste)

Use this prompt exactly:

> Implement the plan in `docs/guides/BATCH_DRAIN_RELIABILITY_AND_EFFICIENCY_PLAN.md` (Sections A–E).  
> After implementing, run at least:
> - one small targeted batch (`--batch-size 3`) and
> - one medium batch (`--batch-size 10`)
> and report back with evidence that the run is healthy using the “Acceptance Criteria” block in that file.  
>
> During the run, monitor:
> - count of phases where `FAILED` and `last_failure_reason=None`
> - subprocess `returncode` distribution and per-phase duration
> - existence of per-phase stdout/stderr logs for every attempt
> - DB/API identity consistency (DATABASE_URL and AUTOPACK_API_URL printed at top of per-phase logs)
> - telemetry growth (`token_estimation_v2_events` row count increase; `token_budget_escalation_events` if applicable)
> - uvicorn process count stability (no runaway server spawning)

---

## Final Report — Acceptance Criteria (paste this into the report)

**Batch Drain Health Acceptance Criteria (must all pass)**

1. **No Silent Failures**
   - For every processed phase, the session JSON includes `subprocess_returncode` and `subprocess_duration_seconds`.
   - For every processed phase, there are durable per-phase log files:
     - `stdout_path` exists and is non-empty OR `stderr_path` exists and is non-empty.

2. **No “Unknown error” without evidence**
   - Any failure with `last_failure_reason=None` includes:
     - subprocess `returncode`, and
     - a pointer to `stderr_path` (or `stdout_path` if stderr is empty).
   - “Unknown error” count is **0**, or if non-zero: each instance includes log file paths and a return code.

3. **Correct Phase Selection Safety**
   - Controller does not retry FAILED phases in runs that already have `queued>0` (unless explicitly overridden).
   - For each retried phase, report the run’s `queued/failed/complete` counts before and after.

4. **Environment/Identity Consistency**
   - Each per-phase stdout log begins with effective `DATABASE_URL` and `AUTOPACK_API_URL`.
   - No evidence of API/DB mismatch (e.g., controller DB shows work but executor reports no executable phases).

5. **Throughput / Stability**
   - Over a 10-phase batch, median per-phase duration is stable (no unexplained “instant completes”).
   - API server processes do not grow unbounded (uvicorn process count stable when using `--api-url`).
   - If baseline caching/skip mode is implemented: baseline capture is not repeated unnecessarily (report observed baseline captures).

6. **Telemetry Viability**
   - `token_estimation_v2_events` row count increases for successful phases (report delta).
   - If truncation/escalation occurs, `token_budget_escalation_events` row count increases appropriately (report delta).


