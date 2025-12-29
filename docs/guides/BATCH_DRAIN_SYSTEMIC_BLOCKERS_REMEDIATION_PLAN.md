# Batch Drain Systemic Blockers Remediation Plan (Post-Triage)

**Date**: 2025-12-28  
**Audience**: Cursor operator implementing fixes in `C:\dev\Autopack`  
**Primary goal**: Remove *systemic* blockers discovered by token-safe triage so backlog draining produces higher completion rates and higher-quality telemetry (per `README.md` “ideal state”: no collection/import hard blocks; less token waste; reliable self-healing signals).

---

## 1) What triage proved (and what it did not)

### 1.1 Proven
- **Telemetry plumbing works** (events are being written; yields are non-zero in some phases).
- Adaptive drain controls are effective at preventing runaway waste (fingerprints + no-yield stop).
- The backlog is dominated by **repeatable systemic failures**, not random flakiness.

### 1.2 Not proven
- That “lenient draining” will improve outcomes. In fact, leniency will amplify waste when the dominant failures are deterministic and systemic.

---

## 2) Observed fingerprints → root causes (from triage session `batch-drain-20251228-064330`)

### 2.1 Dominant fingerprint (9x): `subprocess exit 1 ... SyntaxError ... autonomous_executor.py`
**Symptom**: drain subprocess crashes immediately (duration ~2s) while importing `autopack.autonomous_executor`.  
**Evidence**: session JSON entries show:
- `SyntaxError: expected 'except' or 'finally' block` at `src/autopack/autonomous_executor.py` around line ~4557
- The error is stable across many runs/phases, so draining cannot proceed for large parts of the backlog.

**Root cause**: A malformed `try:` block / indentation error in `src/autopack/autonomous_executor.py` within the “Pre-apply JSON deliverables validation” section. Stray keyword arguments (e.g., `coverage_delta=...`) appear inside a function call where they don’t belong, breaking Python syntax.

**Impact**:
- Hard-blocks any run that imports the executor (most drains).
- Produces **0 telemetry** for those attempts (no Builder call occurs).

---

### 2.2 Systemic fingerprint cluster: `DELIVERABLES_VALIDATION_FAILED` for `fileorg-p2-frontend-build`
**Symptom**: deliverables validation fails with missing `fileorganizer/frontend/package-lock.json` even though the executor logs “Created stub for missing file: fileorganizer/frontend/package-lock.json”.

**Evidence** (from phase stderr):
- Workspace root determined from scope prefix: `C:\dev\Autopack\fileorganizer`
- Missing scope files include `fileorganizer/frontend/package-lock.json`
- Stub creation uses `missing_path = (workspace_root / missing)` which becomes:
  - `C:\dev\Autopack\fileorganizer\fileorganizer\frontend\package-lock.json` (**double `fileorganizer/`**)
- Deliverables validator checks workspace presence using `workspace=Path(self.workspace)` (repo root), so it looks for:
  - `C:\dev\Autopack\fileorganizer\frontend\package-lock.json`
  - which was never created, so it reports `(+0 existing files in workspace)` and fails.

**Root cause**: **Workspace-root mismatch + path joining bug** in scope stub creation:
- `workspace_root` is the “project root” (e.g., `.../fileorganizer`)
- but the scoped path includes the project root prefix again (`fileorganizer/frontend/...`)
- resulting in stubs created in the wrong location.

**Impact**:
- Deterministic failures for `fileorg-p2-*` runs.
- Wasted Builder calls (tokens spent) followed by guaranteed validator failure.

---

### 2.3 Systemic CI collection/import errors (research cluster)
These appear as:
- `ImportError while importing test module 'tests/autopack/workflow/test_research_review.py'`
- “New collection errors (persistent): ['tests/research/gatherers/test_reddit_gatherer.py']”

**Root causes**:

#### 2.3.1 `tests/autopack/workflow/test_research_review.py` fails because `autopack.workflow.research_review` does not match test expectations
The test expects:
- `ReviewCriteria` class
- `ReviewResult` class
- `ReviewDecision` **Enum** with `.APPROVED/.REJECTED/.NEEDS_MORE_RESEARCH`
- `ResearchReviewWorkflow` methods: `submit_for_review`, `_can_auto_review`, `_auto_review`, `manual_review`, `get_review_status`, `list_pending_reviews`, `export_review_to_build_history`

But `src/autopack/workflow/research_review.py` currently provides:
- `ReviewDecision` as a **dataclass** (not enum)
- No `ReviewCriteria` / no `ReviewResult`
- Different API surface (`create_review`, `submit_decision`, etc.)

**Impact**: pytest collection hard-blocks phases (exit code 2), which is an explicit “do not complete” condition in `README.md`.

#### 2.3.2 `tests/research/gatherers/test_reddit_gatherer.py` fails because `praw` is not installed
`src/research/gatherers/reddit_gatherer.py` imports `praw` at module import time. If `praw` is absent, pytest collection fails.

**Impact**: another collection hard-block and deterministic failure.

---

## 3) Recommended strategy (Options A–D)

### Decision
- **Option A (Investigate top fingerprints)**: ✅ Already done; actionable root causes identified above.
- **Option C (Fix specific systematic issues)**: ✅ Next step (do this before large draining).
- **Option B (lenient draining)**: ❌ Not recommended until after the systemic blockers are removed.
- **Option D (run-bucketing + targeted draining)**: ✅ Recommended operationally *after* blockers are fixed.

---

## 4) Implementation workstreams (do in order)

### Workstream 0 — Safety/guardrails before edits
- Create a branch for these fixes.
- Ensure local commands run from repo root.
- Keep changes minimal and add small regression tests to prevent recurrence.

---

### Workstream 1 — Fix SyntaxError in `src/autopack/autonomous_executor.py` (P0)

#### 4.1.1 What to change
- Locate the “Pre-apply JSON deliverables validation” block inside `_execute_phase_with_recovery`.
- Fix the malformed call to `validate_new_json_deliverables_in_patch(...)`:
  - Ensure arguments are syntactically correct.
  - Remove stray `coverage_delta=...` that is currently inserted inside the argument list.
- Ensure the `try:` block has valid structure and indentation.

#### 4.1.2 Validation
Run:
- `python -m py_compile src/autopack/autonomous_executor.py`
- `pytest -q tests/test_autonomous_executor.py -q` (this imports `src.autopack.autonomous_executor`)

#### 4.1.3 Add regression test
Add a minimal test to catch “executor can’t import” early:
- New file: `tests/test_autonomous_executor_import.py`
  - `from autopack.autonomous_executor import AutonomousExecutor` (or `from src.autopack.autonomous_executor import AutonomousExecutor` depending on your import convention; see notes below)

**Import convention note**: This repo currently mixes `autopack.*` and `src.autopack.*`. For draining with `PYTHONPATH=src`, `autopack.*` is the canonical import. For pytest in this repo, `tests/conftest.py` adds both repo root and `src/` to `sys.path`, so both often work. Prefer `autopack.*` for runtime correctness.

---

### Workstream 2 — Fix scope stub creation path bug (P0 for fileorg-p2)

#### 4.2.1 Root cause recap
Scope stub creation currently does:
- `missing_path = (workspace_root / missing).resolve()`
If `workspace_root` is `.../fileorganizer` and `missing` is `fileorganizer/frontend/package-lock.json`, the result is duplicated.

#### 4.2.2 What to change
In `src/autopack/autonomous_executor.py` inside `_load_scoped_context`, update the stub creation logic to **resolve via the same scope resolver used everywhere else**:
- Replace manual join with:
  - `resolved = self._resolve_scope_target(missing, workspace_root, must_exist=False)`
  - If `resolved` returns `(abs_path, rel_key)`:
    - create stub at `abs_path`
    - add file to context using normalized `rel_key`
  - If `resolved` is None, fall back to `base_workspace / missing` only if it stays within `base_workspace`.

Also:
- Ensure stub content is appropriate:
  - For `package-lock.json` a minimal valid placeholder is `{}` (current behavior is fine).

#### 4.2.3 Add test coverage
Add a unit test (temp workspace) that simulates:
- `workspace_root` = `<tmp>/fileorganizer`
- scope includes `fileorganizer/frontend/package-lock.json`
- verify stub is created at `<tmp>/fileorganizer/frontend/package-lock.json` (not `<tmp>/fileorganizer/fileorganizer/...`)

#### 4.2.4 Validation
Run a single targeted drain against one failing fileorg run/phase after fix:
- `python scripts/batch_drain_controller.py --run-id fileorg-p2-20251208 --batch-size 1 --phase-timeout-seconds 600`
Expected:
- deliverables validator should count `(+1 existing files in workspace)` for the stub (or the phase should at least fail for a different reason).

---

### Workstream 3 — Unblock CI collection: make `autopack.workflow.research_review` match tests (P1)

#### 4.3.1 Goal
Eliminate deterministic collection failures from `tests/autopack/workflow/test_research_review.py`.

#### 4.3.2 Approach (compat layer, minimal blast radius)
Update `src/autopack/workflow/research_review.py` to provide the API expected by tests **without removing existing functionality**:

1) Introduce `@dataclass ReviewCriteria` with the fields used by tests:
- `auto_approve_confidence: float = 0.9`
- `auto_reject_confidence: float = 0.3`
- `require_human_review: bool = True`
- `min_findings_required: int = 1`
- `min_recommendations_required: int = 1`

2) Convert `ReviewDecision` into an `Enum` (as tests expect):
- `APPROVED`, `REJECTED`, `NEEDS_MORE_RESEARCH`

3) Introduce `@dataclass ReviewResult` with fields used by tests:
- `decision: ReviewDecision`
- `reviewer: str`
- `comments: str = ""`
- `approved_findings: list[str] = field(default_factory=list)`
- `approved_recommendations: list[str] = field(default_factory=list)`
- `timestamp: datetime = field(default_factory=datetime.now)`

4) Implement a test-oriented in-memory workflow inside `ResearchReviewWorkflow`:
- Maintain `self._pending_reviews: dict[str, dict]`
- Add methods:
  - `submit_for_review(research_phase_result) -> str`
  - `_can_auto_review(result) -> bool`
  - `_auto_review(result) -> ReviewResult`
  - `manual_review(review_id, decision, reviewer, comments="") -> ReviewResult`
  - `get_review_status(review_id) -> dict`
  - `list_pending_reviews() -> list`
  - `export_review_to_build_history(review_id) -> str`

**Important**: Keep existing file-backed review objects intact by renaming the current dataclass `ReviewDecision` (the record) to something like `ReviewDecisionRecord` so you can introduce the Enum name expected by tests.

#### 4.3.3 Validation
- `pytest -q tests/autopack/workflow/test_research_review.py`
- Run a small drain on a research phase that previously failed due to collection error.

---

### Workstream 4 — Unblock CI collection: handle optional dependency `praw` (P1)

#### 4.4.1 Goal
Eliminate deterministic collection failures from `tests/research/gatherers/test_reddit_gatherer.py` when `praw` is not installed.

#### 4.4.2 Options
- **Preferred** (minimal): in `tests/research/gatherers/test_reddit_gatherer.py`, add:
  - `praw = pytest.importorskip("praw")` near top (before importing the module that requires it), or
  - skip module-level with a clear message if `praw` missing.
- Alternative: make `src/research/gatherers/reddit_gatherer.py` import `praw` lazily (`try/except ImportError`) and raise a runtime error only when instantiated.
- Alternative: add `praw` to `requirements.txt` (bigger footprint; avoid unless desired).

#### 4.4.3 Validation
- `pytest -q tests/research/gatherers/test_reddit_gatherer.py`
- Ensure pytest collection succeeds even without `praw` installed.

---

## 5) Operational plan after fixes (Option D)

After Workstreams 1–4:

### 5.0 IMPORTANT: `--skip-runs-with-queued` is a safety feature (not a “design flaw”)
The batch drain controller intentionally defaults to skipping runs that already have **any** `QUEUED` phases.

Why this exists:
- The controller drains a FAILED phase by **re-queueing it**.
- If a run already has a queued phase, re-queueing another phase creates **multiple QUEUED phases**.
- The executor then drains the *earliest* queued phase, which may not be the one you intended to retry.

This means: if your backlog (or a specific `--run-id`) has *any* queued phases, **`batch_drain_controller.py` may process 0 phases by design**.

**Correct workflow** (matches `README.md` and existing tooling):
- Drain **QUEUED** phases first (safe), then retry FAILED phases.
- Use `scripts/drain_queued_phases.py` for the queued portion.

### 5.1 Resume draining in “strict triage” mode
Use strict parameters to avoid re-burning tokens:
- `--phase-timeout-seconds 600`
- `--max-attempts-per-phase 1`
- `--max-fingerprint-repeats 2`
- `--max-timeouts-per-run 1`

### 5.1.1 Mandatory pre-step: drain QUEUED phases first
For a specific run:

```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
python scripts/drain_queued_phases.py \
  --run-id <RUN_ID> \
  --batch-size 5 \
  --stop-on-first-failure
```

Then, once `queued=0`, run failed-phase draining:

```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
python scripts/batch_drain_controller.py \
  --run-id <RUN_ID> \
  --batch-size 30 \
  --phase-timeout-seconds 600 \
  --max-total-minutes 45 \
  --max-fingerprint-repeats 2 \
  --max-timeouts-per-run 1 \
  --max-attempts-per-phase 1
```

### 5.1.2 Optional (riskier): override queued-run safety
Only if you fully understand the risk and you’ve verified nothing else is draining that run:

```bash
python scripts/batch_drain_controller.py --no-skip-runs-with-queued ...
```

This can cause the executor to drain a different queued phase than the FAILED phase you intended.

### 5.2 Run bucketing
- Bucket runs by dominant failure fingerprint:
  - “import-time crash” (should become 0 after Workstream 1)
  - “deliverables_validation_failed” (should drop after Workstream 2)
  - “collection/import error” (should drop after Workstreams 3–4)
  - remaining “patch_failed/ci_failed/etc.” (legit phase-level issues)

### 5.3 Go/No-Go criteria for scaling batch sizes
Scale from batch 30 → 100 only if:
- Import-time failures are **0**
- Collection/import errors are rare (e.g., <5% of attempts)
- Telemetry “phases with events” rises above ~60% (indicates phases are reaching Builder)

---

## 6) Concrete checklist (copy/paste)

1) Fix `autonomous_executor.py` SyntaxError and add import regression test.
2) Fix scope stub creation to use `_resolve_scope_target` (no double-prefix).
3) Add compatibility layer in `workflow/research_review.py` to satisfy `tests/autopack/workflow/test_research_review.py`.
4) Make `tests/research/gatherers/test_reddit_gatherer.py` skip cleanly when `praw` missing.
5) Run:
   - `python -m py_compile src/autopack/autonomous_executor.py`
   - `pytest -q tests/test_autonomous_executor.py tests/autopack/workflow/test_research_review.py tests/research/gatherers/test_reddit_gatherer.py`
6) Resume draining (batch 30) with strict settings; review fingerprint distribution; then scale.


