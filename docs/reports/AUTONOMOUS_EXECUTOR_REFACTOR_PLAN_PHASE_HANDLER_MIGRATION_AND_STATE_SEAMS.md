## Autonomous Executor Refactor Plan — Handler Migration + State/Scope Seams (post PR-128/130 + A~F)

**Target**: `src/autopack/autonomous_executor.py`

**Goal**: continue shrinking the “god file” and improving developer iteration speed, while staying safe (no behavior change) and keeping CI green.

This plan is designed for a separate Cursor to implement as a PR stack.

---

## Direction (explicit decisions, to remove ambiguity)

- **One behavior-preserving seam per PR**; no “mega refactor”.
- **One batched handler body migration per PR** (largest win per unit effort).
- For `execute_phase()` refactors, prefer **unit contract tests** with fakes/mocks rather than integration.
- Treat DB/telemetry operations as **best-effort** unless clearly marked otherwise.
- Avoid circular imports: new `autopack.executor.*` modules must not import `autonomous_executor.py`.
- Avoid Ruff E402: prefer **local imports** inside methods for newly extracted seams (matches the repo’s current style for executor seams).

---

## Inventory (verified in code)

### Special batched handler methods remaining in `autonomous_executor.py`

These are large and are the top source of file bulk:
- `_execute_research_tracer_bullet_batched` (line ~7041)
- `_execute_research_gatherers_web_compilation_batched` (line ~7519)
- `_execute_diagnostics_handoff_bundle_batched` (line ~6889)
- `_execute_diagnostics_cursor_prompt_batched` (line ~6945)
- `_execute_diagnostics_second_opinion_batched` (line ~6995)
- `_execute_diagnostics_deep_retrieval_batched` (line ~6807)
- `_execute_diagnostics_iteration_loop_batched` (line ~6848)

### Phase state persistence methods mixed into `execute_phase()`

Candidate seam functions already exist as methods:
- `_get_phase_from_db(self, phase_id: str) -> Optional[Any]`
- `_update_phase_attempts_in_db(...)`
- `_mark_phase_complete_in_db(...)`
- `_mark_phase_failed_in_db(...)`

### BUILD-123v2 scope generation block (inside `execute_phase()`)

When `scope.paths` missing, it calls:
- `self.manifest_generator.generate_manifest(...)`
and mutates `phase["scope"]`.

### P10 DB event write payload duplication

`try_record_token_budget_escalation_event(...)` is called twice with near-identical argument construction.

---

## PR plan (recommended order)

### PR-1: Add minimal `execute_phase` contract test (high confidence guardrail)

**Goal**: lock the most important invariants before moving more code.

Add `tests/unit/test_executor_execute_phase_contract.py`:
- Case A: `status == "TOKEN_ESCALATION"`:
  - increments retry attempt
  - **skips diagnostics/Doctor path**
- Case B: “normal failure” status (e.g., `"PATCH_FAILED"`):
  - increments retry attempt
  - **does** diagnostics path (or at minimum: does not take the “skip diagnostics” branch)

**How to implement test without heavy dependencies**:
- Use a lightweight fake executor class that reuses the *real* `execute_phase()` decision helpers already extracted (A~F), but stubs:
  - `_execute_phase_with_recovery` to return `(False, status)`
  - `_update_phase_attempts_in_db` to record arguments
  - `_record_phase_error`, `_record_learning_hint` to no-op
  - any Doctor/diagnostics calls to raise if invoked (to detect unwanted path)
  - `_get_phase_from_db` to return an object with `retry_attempt`, `revision_epoch`, `escalation_level`
- Keep `phase` dict minimal: `{"phase_id": "...", "scope": {"paths": [...]}}` so BUILD-123v2 scope generation doesn’t trigger in this test.

**Ambiguity resolved**:
- This contract test is “mechanical safety” and should be strict enough to catch regressions, but not so strict it blocks legitimate future changes.

---

### PR-2: Migrate one batched handler body (start with tracer bullet)

**Goal**: start shrinking the file with the biggest, safest win.

**Module**:
- Add `src/autopack/executor/phase_handlers/batched_research_tracer_bullet.py`

**Function signature**:
```python
def execute(
    executor,
    *,
    phase: dict,
    attempt_index: int,
    allowed_paths: list[str] | None,
) -> tuple[bool, str]:
    ...
```

**Executor wrapper**:
- Keep `AutonomousExecutor._execute_research_tracer_bullet_batched(...)` as a thin wrapper calling the module function.
- Do **not** change `phase_dispatch.SPECIAL_PHASE_METHODS` yet; keep mapping to the wrapper method name (lowest risk).

**Unit test**:
- `tests/unit/test_executor_phase_handler_tracer_bullet_wrapper.py`
  - monkeypatch module `execute` to record args and return sentinel
  - assert wrapper returns sentinel and passes correct args

**Ambiguity resolved**:
- Don’t attempt to refactor internal logic of the batched handler; this PR is a pure move + wrapper.

---

### PR-3..PR-N: Migrate remaining batched handlers one-by-one (same pattern)

Recommended order:
1) `batched_research_gatherers_web_compilation`
2) `batched_diagnostics_handoff_bundle`
3) `batched_diagnostics_cursor_prompt`
4) `batched_diagnostics_second_opinion`
5) `batched_diagnostics_deep_retrieval`
6) `batched_diagnostics_iteration_loop`

Each PR contains:
- one new `executor/phase_handlers/batched_*.py`
- a thin wrapper in `AutonomousExecutor`
- one wrapper delegation unit test

---

### PR-(state): Extract phase state persistence seam out of `execute_phase()`

**Goal**: make `execute_phase()` readable by separating:
- state fetch / defaulting (BUILD-115 fallback)
- state updates (attempt increment, complete/failed marking)

**Option A (preferred)**: extend existing `src/autopack/executor/state_persistence.py`
- It already exists and is a natural home.

**Option B**: add new `src/autopack/executor/state.py`

**Proposed API**:
```python
from dataclasses import dataclass

@dataclass
class PhaseRuntimeState:
    retry_attempt: int
    revision_epoch: int
    escalation_level: int

def get_phase_state_or_defaults(*, executor, phase_id: str) -> PhaseRuntimeState:
    ...

def persist_attempt_update(*, executor, phase_id: str, next_retry_attempt: int, reason: str) -> None:
    ...
```

**Implementation notes**:
- `get_phase_state_or_defaults` encapsulates the current “PhaseDefaults” fallback when DB state absent.
- `persist_attempt_update` is a thin wrapper over `_update_phase_attempts_in_db` (no behavior change).

**Unit tests**:
- assert fallback defaulting matches current behavior (retry_attempt=0 etc.)
- assert persist_attempt_update calls underlying `_update_phase_attempts_in_db` with expected args

**Ambiguity resolved**:
- This seam is about readability, not changing DB behavior. Keep current behavior exactly.

---

### PR-(scope): Extract BUILD-123v2 scope generation block into `executor/scope_generation.py`

**Goal**: remove the large scope generation block from `execute_phase()` so it becomes “attempt logic only”.

**Module**:
- `src/autopack/executor/scope_generation.py`

**API**:
```python
def ensure_phase_scope(
    *,
    executor,
    phase: dict,
) -> dict:
    \"\"\"Return updated scope_config; may mutate phase['scope'] as today.\"\"\"
    ...
```

**Contract test**:
- If `phase["scope"]["paths"]` missing:
  - `executor.manifest_generator.generate_manifest(...)` is called
  - `phase["scope"]` becomes non-empty when result.success
- If paths exist:
  - generator is not called

**Ambiguity resolved**:
- Keep mutation behavior (phase dict updated) because downstream code expects it.

---

### PR-(p10): Consolidate P10 escalation payload building into `executor/token_budget_events.py`

**Goal**: remove duplication where `try_record_token_budget_escalation_event(...)` is called twice with nearly identical args.

**Module**:
- `src/autopack/executor/token_budget_events.py`

**API** (pure helper):
```python
def build_token_budget_escalation_payload(
    *,
    run_id: str,
    phase_id: str,
    attempt_index: int,
    reason: str,
    was_truncated: bool,
    output_utilization: float | None,
    escalation_factor: float,
    base_value: int,
    base_source: str,
    retry_max_tokens: int,
    selected_budget: int | None,
    actual_max_tokens: int | None,
    tokens_used: int | None,
) -> dict:
    ...
```

Then in executor code:
- build payload once
- pass payload fields into `try_record_token_budget_escalation_event(...)` (or evolve db_events to accept payload dict if desired)

**Tests**:
- table-driven: confirm selected_budget conversion behavior (None vs int)
- ensure payload keys stable

**Ambiguity resolved**:
- Keep `db_events.try_record_*` signature stable unless you choose a follow-up PR to accept payload dicts.

---

### PR-(imports): Convert more inline imports to leaf helpers (reduce import churn)

**Goal**: stop adding more inline imports inside `autonomous_executor.py` by pushing logic into leaf modules.

Candidates:
- `executor/doctor_wiring.py`: build DoctorRequest/context, dispatch Doctor, interpret response
- `executor/failure_hardening.py`: wrapper around `detect_and_mitigate_failure` call pattern
- `executor/provider_disable.py`: model/provider disable logic based on infra errors

**Direction**:
- Each helper module should be “leafy”: imports its own dependencies, executor calls it.
- Add a tiny unit test per helper (smoke test with fakes), so you can move code safely.

---

## Additional recommended seams (post above; improve dev speed further)

These are larger extractions that become low-risk once the handler/state/scope seams above are in place.

### PR-(builder): Extract “builder invocation + parsing mode selection” seam

**Problem**: the executor contains significant logic for:
- choosing full-file vs structured edits
- handling truncation/utilization and format fallbacks

**Module**:
- `src/autopack/executor/builder_pipeline.py`

**Shape**:
- create a small orchestrator function that takes `(executor, phase, attempt_index, file_context, allowed_paths)` and returns `(builder_result, status)`
- keep any heavy dependencies imported inside the function (avoid import-time weight/cycles)

**Contract tests**:
- `tests/unit/test_executor_builder_pipeline_contract.py` with table-driven fakes that assert the pipeline returns expected statuses for:
  - `COMPLETE`
  - `TOKEN_ESCALATION`
  - `PATCH_FAILED`

**Ambiguity resolved**:
- This PR should not change model selection policy; it only relocates the “mode selection + fallback” logic.

---

### PR-(apply): Extract “governed apply + validation preflight” seam

**Problem**: patch apply path mixes:
- YAML / docker-compose validation
- drift checks
- governed apply construction

**Module**:
- `src/autopack/executor/patch_apply_pipeline.py`

**Signature**:
```python
def apply_builder_result_patch(
    executor,
    *,
    builder_result,
    phase: dict,
    allowed_paths: list[str] | None,
) -> tuple[bool, str]:
    ...
```

**Tests**:
- contract tests that (with fakes) assert:
  - validation failure → returns `(False, "PATCH_FAILED")` (or current canonical status)
  - drift-block path returns expected status
  - successful apply returns `(True, "COMPLETE")` (or current canonical status)

---

### PR-(ci): Extract “CI execution + result normalization” seam

**Module**:
- `src/autopack/executor/ci_runner.py`

**Dataclass**:
- `CiResult` normalized fields (pass/fail, summary, raw stdout/stderr pointers if needed)

**Direction**:
- Keep `_run_ci_checks(...)` as a wrapper initially; move implementation into `ci_runner.run_ci(...)`.

---

### PR-(governance): Split notifications / approvals / governance out of the hot path

**Goal**: reduce `execute_phase()` complexity by moving non-core concerns out.

**Modules** (choose one naming scheme and stick to it):
- `src/autopack/executor/approvals.py`
- `src/autopack/executor/governance_bridge.py`

**Tests**:
- smoke tests with fakes asserting correct calls/arguments (don’t integration-test Telegram here).

---

### PR-(typed-phase) (optional, later): Introduce a typed Phase view at seams

**Problem**: “dict soup” increases mistakes and makes refactors harder.

**Module**:
- `src/autopack/executor/models.py`

**Approach**:
- Add `PhaseSpec` (dataclass or Pydantic) that wraps the dict.
- Use it only at seam boundaries first (builder pipeline / apply pipeline / retry policy wiring).

**Ambiguity resolved**:
- Do not rewrite the entire executor to typed models in one PR; incremental only.

---

### PR-(policy): Add “no side effects at import time” rule for executor modules

**Goal**: keep extracted executor modules leaf-like and fast to import.

**Implementation options**:
- Add a small CI script (similar to existing guardrails) that fails if modules under `src/autopack/executor/` import banned modules like:
  - `autopack.main`
  - `fastapi`
  - other heavyweight app wiring

**Notes**:
- Keep this rule strict but allowlisted for exceptions; document exceptions inline in the checker.

---

### PR-(diagnostics): Extract “diagnostics orchestration” seam

**Goal**: remove “decision hub” logic from `execute_phase()` by isolating:
- Doctor invocation (build request, call Doctor, interpret response)
- deep retrieval triggers
- iteration loop decisioning

**Module**:
- `src/autopack/executor/diagnostics_orchestrator.py`

**Shape**:
- Provide a single function that takes current failure context and returns a structured decision:
  - run diagnostics? run doctor? trigger deep retrieval? trigger iteration loop? skip?

**Tests**:
- unit tests with fakes asserting:
  - TOKEN_ESCALATION path never triggers diagnostics
  - specific failure_outcome types lead to expected decision outputs

**Ambiguity resolved**:
- keep the existing decision policy; this PR is “move + contract test”, not “rethink diagnostics”.

---

### PR-(checkpointing): Extract run/workspace checkpointing + rollback seam

**Goal**: isolate churn-heavy git/workspace operations from the executor core.

**Module**:
- `src/autopack/executor/run_checkpointing.py`

**Move candidates**:
- run checkpoint creation
- rollback-to-checkpoint logic
- rollback audit log writing (currently writes under `.autonomous_runs/.../run_rollback.log`)

**Tests**:
- unit tests with subprocess stubs (do not run real git commands in unit tests).

---

### PR-(perf-guard): Add a tiny import-time performance guard

**Goal**: detect regressions as the refactor progresses (import time should generally improve).

**Implementation options**:
- A script: `scripts/perf/check_import_time.py` that measures:
  - `import autopack.autonomous_executor`
  - `import autopack.executor` (and selected submodules)
  - prints timings and fails if above a threshold.
- Or a pytest marked as non-blocking initially (informational) to avoid flaky CI.

**Direction**:
- Start informational (non-blocking) with baseline numbers logged.
- Once stable, optionally enforce a generous ceiling.

## CI / testing checklist (required)

Per PR:
- `ruff check src/ tests/`
- `black --check src/ tests/`
- run only the new unit tests you added (fast)

Before opening PR (and again before merge), run drift close-out:
- `python scripts/check_docs_drift.py`
- `python scripts/tidy/sot_summary_refresh.py --check`
- `python scripts/check_doc_links.py`
- `python scripts/tidy/verify_workspace_structure.py`
- `pytest -q tests/docs/`

If drift detected:
- `python scripts/tidy/sot_summary_refresh.py --execute`
- re-run checks until clean
- include drift-fix commit in the PR

**Critical**: never manually edit the README SOT block; only via `sot_summary_refresh.py`.

