## Autonomous Executor Refactor Plan — Next Seams (post PR-128/PR-130)

**Target**: `src/autopack/autonomous_executor.py`

**Assumed baseline already merged**:
- **PR-128**: special phase dispatch registry (`autopack.executor.phase_dispatch`)
- **PR-130**: context-loading policy seam (`autopack.executor.context_loading`) + `_load_repository_context_heuristic`

**Goal**: keep shrinking the “god file” while preserving behavior and keeping CI green.

---

## Direction (explicit, to remove ambiguity)

- Refactor via **small, stacked PRs**; each PR must be reviewable and low-risk.
- “No behavior change” until a seam is extracted + contract-tested.
- Extract **pure functions** first (retry/escalation decisioning).
- Extract **best-effort DB/telemetry reads** into a module so orchestration can be tested without DB.
- When migrating big handler bodies, move **one handler per PR**.
- Favor **unit contract tests** over integration tests for these refactors.

Non-negotiable safeguards:
- Avoid circular imports: new `autopack.executor.*` modules must not import `autonomous_executor.py`.
- Use tracked-file and docs/SOT drift checks before PR (see bottom).

---

## 1) Extract retry/escalation decisioning into pure functions (high ROI, low risk)

### What exists today (verified)
Inside `execute_phase()` there is:
- attempt state (`attempt_index = phase_db.retry_attempt`)
- a special `TOKEN_ESCALATION` path that advances retry_attempt without running diagnosis
- scattered P10 “retry budget escalation” logic inside builder-result processing (sets `phase["_escalated_tokens"]`, `_escalated_once`)
- an “escalate model for next retry” log + state update paths

### Target module
Add `src/autopack/executor/retry_policy.py`

### Proposed API (skeleton)
Use dataclasses so logic is explicit and easy to unit test.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Status = Literal["COMPLETE", "FAILED", "BLOCKED", "TOKEN_ESCALATION", "PATCH_FAILED"]

@dataclass(frozen=True)
class AttemptContext:
    attempt_index: int
    max_attempts: int
    escalation_level: int

@dataclass(frozen=True)
class AttemptDecision:
    # What the executor should do next
    next_retry_attempt: Optional[int]  # None means “no update”
    should_run_diagnostics: bool
    should_escalate_model: bool
    terminal: bool  # stop retry loop at executor level

def should_escalate(status: str) -> bool:
    ...

def choose_model_for_attempt(ctx: AttemptContext) -> str | None:
    \"\"\"Return model id override, or None to defer to ModelRouter.\"\"\"
    ...

def next_attempt_state(ctx: AttemptContext, status: str) -> AttemptDecision:
    ...
```

### PR slicing recommendation
- **PR-A**: introduce `retry_policy.py` + tests only (no production wiring).
- **PR-B**: wire `execute_phase()` to use `next_attempt_state(...)` for decisions currently encoded inline.

### Contract tests to add
Add `tests/unit/test_executor_retry_policy.py` with table-driven cases:
- `TOKEN_ESCALATION` → increments retry attempt, **does not run diagnostics**, not terminal
- “normal failure” → increments retry attempt and may trigger escalation
- exhausted attempts → terminal

### Ambiguity to resolve (explicit decision)
- **Where is the truth for model selection?**
  - Decision: `choose_model_for_attempt()` returns **None by default** (defer to existing ModelRouter).
  - Only encode override logic if it already exists as a deterministic mapping in executor today.

---

## 2) Extract the “single attempt wrapper” around error recovery (small seam)

### What exists today (verified)
`execute_phase()` defines an inner closure `_execute_phase_inner()` and calls:
`self.error_recovery.execute_with_retry(func=_execute_phase_inner, max_retries=1)`

### Target module
Add `src/autopack/executor/attempt_runner.py`

### Proposed API (skeleton)
Keep it intentionally boring; don’t restructure semantics in the first PR.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

@dataclass(frozen=True)
class AttemptRunResult:
    success: bool
    status: str

def run_single_attempt_with_recovery(
    *,
    executor: Any,
    phase: dict,
    attempt_index: int,
    allowed_paths: list[str] | None,
) -> AttemptRunResult:
    def _inner() -> tuple[bool, str]:
        return executor._execute_phase_with_recovery(
            phase,
            attempt_index=attempt_index,
            allowed_paths=allowed_paths,
        )
    success, status = executor.error_recovery.execute_with_retry(
        func=_inner,
        operation_name=f\"Phase execution: {phase.get('phase_id')}\",
        max_retries=1,
    )
    return AttemptRunResult(success=success, status=status)
```

### Tests
Add `tests/unit/test_executor_attempt_runner.py`:
- fake executor object with an `error_recovery` stub that records calls
- assert it calls `_execute_phase_with_recovery` exactly once via the wrapper

### Ambiguity to resolve
- Should attempt_runner also update DB state?
  - Decision: **No.** attempt_runner is only the “call attempt with recovery” seam.

---

## 3) Extract best-effort DB/telemetry reads/writes (TokenBudgetEscalationEvent) into a module

### What exists today (verified)
`execute_phase()` includes a try/except best-effort block that:
- opens SessionLocal()
- queries `TokenBudgetEscalationEvent` by run_id + phase_id
- if matches, sets `phase["_escalated_tokens"]`

Additionally, there are best-effort DB writes for P10 telemetry later in the file.

### Target module
Add `src/autopack/executor/db_events.py`

### Proposed API (skeleton)

```python
from __future__ import annotations

from typing import Optional

def maybe_apply_retry_max_tokens_from_db(*, run_id: str, phase: dict, attempt_index: int) -> None:
    \"\"\"Best-effort: reads TokenBudgetEscalationEvent and sets phase['_escalated_tokens'] if present.

    Must never raise.
    \"\"\"
    ...

def try_record_token_budget_escalation_event(*, run_id: str, phase_id: str, payload: dict) -> None:
    \"\"\"Best-effort telemetry write; must never raise.\"\"\"
    ...
```

### Tests
Add `tests/unit/test_executor_db_events_best_effort.py`:
- monkeypatch the module’s DB accessor to throw → ensure function returns without raising
- optional: test with a fake in-memory object if the function supports injection

### Ambiguity to resolve
- Should db_events import SQLAlchemy models at module import time?
  - Decision: **No**. import models inside the function to avoid import-time coupling.

---

## 4) Phase handler migration (one handler per PR)

### Goal
After PR-128, phase routing is registry-driven. Next step is to move each big batching handler out.

### Target module tree

```
src/autopack/executor/phase_handlers/
  __init__.py
  batched_research_tracer_bullet.py
  batched_research_gatherers_web_compilation.py
  batched_diagnostics_handoff_bundle.py
  batched_diagnostics_cursor_prompt.py
  batched_diagnostics_second_opinion.py
  batched_diagnostics_deep_retrieval.py
  batched_diagnostics_iteration_loop.py
```

### Migration approach (low conflict)
Per handler PR:
- Move the method body to a top-level function:
  - `def execute(executor: AutonomousExecutorLike, *, phase: dict, attempt_index: int, allowed_paths: list[str] | None) -> tuple[bool, str]`
- Keep `AutonomousExecutor._execute_<...>` as a 1–3 line wrapper calling the module function.
- Keep `phase_dispatch.SPECIAL_PHASE_METHODS` pointing at the wrapper method name (no registry change yet).

### Tests
At minimum, unit test that wrapper calls module function with correct parameters (use monkeypatch).

### Ambiguity to resolve
- Should phase_dispatch map to callables instead of method names?
  - Decision: not initially. Keep method-name mapping until all handlers are migrated; then consider moving to callable registry.

---

## 5) Reduce import-time weight (developer speed)

### Problem
`autonomous_executor.py` imports a lot at module import time, which slows editor tooling and increases cycle risk.

### Direction
- Do not “optimize everything” at once.
- As seams move out, move their imports out with them.
- For remaining optional or heavy dependencies, move imports inside functions where safe (but avoid creating hidden cycles).

### Acceptance
- smaller import section over time
- no runtime regressions

---

## 6) Add “phase dispatch coverage” contract test (strong guardrail)

### Goal
Prevent drift where a special phase id is added/renamed but not routed.

### Test to add
Add `tests/unit/test_executor_phase_dispatch_coverage.py`:
- assert `SPECIAL_PHASE_METHODS` includes the expected phase ids
- optionally instantiate a minimal fake executor with stub methods named in the mapping and assert `getattr` would succeed (string-based existence contract)
- assert unknown `phase_id` returns None from resolver

---

## PR checklist (required drift close-out)
Before opening any PR (and again right before merge), run:
- `python scripts/check_docs_drift.py`
- `python scripts/tidy/sot_summary_refresh.py --check`
- `python scripts/check_doc_links.py`
- `python scripts/tidy/verify_workspace_structure.py`
- `pytest -q tests/docs/`

If drift is detected:
- `python scripts/tidy/sot_summary_refresh.py --execute`
- re-run checks until clean
- include drift-fix commit in the PR

**Critical**: never manually edit the README SOT block; only via `sot_summary_refresh.py`.

