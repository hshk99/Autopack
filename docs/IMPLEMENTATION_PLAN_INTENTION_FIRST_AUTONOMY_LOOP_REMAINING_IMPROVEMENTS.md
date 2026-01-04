# Implementation Plan: Intention-First Autonomy Loop — Remaining Improvements (Executor Wiring + Catalog Refresh + Contracts)

**Status**: Ready to implement (incremental, test-driven)

## Direction (chosen; no alternatives)

Implement **one** intention-first autonomy loop aligned with `README.md`:

- **Intention Anchor is authoritative** for goal, success criteria, constraints, scope, budgets.
- **Execution writes only run-local artifacts** (never SOT).
- **Tidy is the only SOT writer**, append-only, mechanically enforced via CI drift checks.
- **Budgets + halting rules are authoritative** (deterministic stuck handling; no thrash).
- **Model routing is “best under budget + safety”** and is **reproducible** via a persisted routing snapshot.
- **CI remains read-only**, but must fail loudly on drift or contract violations.

This plan *does not* introduce “options”; it sets a single convergence path.

---

## Scope

This plan turns the already-implemented building blocks into **wired, end-to-end behavior**:

- `src/autopack/stuck_handling.py` (policy engine; deterministic)
- `src/autopack/scope_reduction.py` (prompt+schema; explicit justification)
- `src/autopack/model_routing_snapshot.py` (snapshot persisted as run-local artifact)
- `src/autopack/phase_proof.py` (proof artifacts; bounded + persisted run-locally)
- `.github/workflows/intention-autonomy-ci.yml` + `scripts/check_sot_write_protection.py` (read-only enforcement)

---

## Ambiguities (resolved in the direction above)

### A1) What is an “iteration” for stuck handling?
**Decision**: One “phase attempt” = Builder attempt + (optional) Auditor/QualityGate evaluation.

- Increment `iterations_used` once per attempt cycle.
- Retries due to infra failures may still increment `consecutive_failures` if they recur in the same phase.

### A2) How to compute `budget_remaining` (fraction 0..1)?
**Decision**: Normalize to a fraction derived from Intention Anchor budgets and observed usage:

- Start at `1.0`.
- Subtract based on measured consumption (tokens/cost/time) already tracked in the run.
- Clamp to `[0.0, 1.0]`.

Implementation should be deterministic and bounded (no network calls required for the calculation).

### A3) How does this interact with existing executor replan/doctor logic?
**Decision**: The intention-first loop is authoritative and *wraps* existing mechanisms:

- If policy returns **REPLAN**: use existing executor replan machinery; set `replan_attempted=True`.
- If **ESCALATE_MODEL**: apply one tier escalation using routing snapshot; increment `escalations_used`; enforce max 1 per phase.
- If **REDUCE_SCOPE**: generate a scope-reduction prompt grounded in the Intention Anchor; require the resulting JSON to validate; reductions are reversible (proposal only).
- If **NEEDS_HUMAN** or **STOP**: executor halts/blocks with a bounded summary; no additional retries.

### A4) Canonical artifact storage path
**Decision**: All new artifacts live under `RunFileLayout.base_dir`:

`.autonomous_runs/<project>/runs/<family>/<run_id>/...`

Never write run artifacts to `.autonomous_runs/<run_id>/...`.

---

## Phase A — Wire the intention-first loop into `autonomous_executor.py` (core)

### Objective
Make the executor *use* the intention-first components during real runs:

- routing snapshot created/loaded at run start and used for escalation decisions
- stuck handling uses deterministic policy decisions
- scope reduction produces explicit, intention-grounded proposals
- phase proof artifacts emitted per phase outcome

### Deliverables
- New glue module:
  - `src/autopack/autonomous/intention_first_loop.py`
  - keeps executor integration small and testable
- Executor wiring:
  - `src/autopack/autonomous_executor.py` updated to call the glue module
- Run-local artifacts (canonical path):
  - routing snapshot: `<run_base>/model_routing_snapshot.json`
  - phase proofs: `<run_base>/proofs/<phase_id>.json` (+ optional markdown)

### Skeleton (expected shape)
Implement a minimal orchestrator class:

- `IntentionFirstLoop.on_run_start(run_id, project_id) -> RunLoopState`
- `IntentionFirstLoop.decide_when_stuck(reason, phase_state, budget_remaining) -> StuckResolutionDecision`
- `IntentionFirstLoop.escalate_model(run_state, phase_state, current_tier, safety_profile) -> ModelRoutingEntry | None`
- `IntentionFirstLoop.build_scope_reduction_prompt(anchor, current_plan, budget_remaining) -> str`
- `IntentionFirstLoop.validate_scope_reduction(proposal, anchor) -> (bool, str)`
- `IntentionFirstLoop.write_phase_proof(proof) -> None`

### Acceptance criteria (mechanical)
- Deterministic stuck decisions for identical inputs.
- Enforce: re-plan before escalation; max 1 escalation per phase; needs-human only for ambiguity/approval.
- For every phase completion (success or failure), a bounded `PhaseProof` is written to canonical run path.
- Routing snapshot persisted once per run and reused (freshness policy respected).
- No SOT writes from executor code (CI check stays green).

### Tests
Add tests targeting executor integration behavior (keep tests small and local):

- New tests (suggested):
  - `tests/autopack/test_intention_first_loop_wiring.py`
  - `tests/autopack/test_executor_intention_first_stuck_dispatch.py`
- Ensure tests do not require network calls; mock LLM/service boundaries.

---

## Phase B — Catalog-backed routing snapshot refresh (replace “default-only” with real refresh)

### Objective
Make snapshot refresh pull from the repo’s existing model catalog/pricing intelligence rather than hardcoded defaults, while preserving:

- determinism
- safety filtering
- budget constraints
- graceful fallback to default snapshot

### Deliverables
- New module:
  - `src/autopack/model_routing_refresh.py`
- New catalog source adapter that reads from the repo’s authoritative model system (e.g. model registry/intelligence).
- Deterministic selector: “best expected success per cost under constraints”.

### Deterministic selection contract
Selection must be stable and reproducible. Use a stable sort key, e.g.:

1) safety compatible (strict profile requires true)
2) cost (input+output) ascending
3) context capacity descending
4) max tokens descending
5) model_id ascending (tie-breaker)

### Acceptance criteria
- Snapshot refresh produces entries for required tiers (haiku/sonnet/opus or the system’s canonical tiers).
- Strict safety profile never selects `safety_compatible=False`.
- If catalog source is unavailable, refresh falls back to `create_default_snapshot()` and still persists a snapshot.

### Tests
- `tests/autopack/test_model_routing_refresh.py`
  - deterministic selection
  - safety filtering
  - fallback path

---

## Phase C — Tighten contracts (scope reduction + warning cleanup)

### C1) Scope reduction validation is “all must constraints acknowledged”
**Change**: In `validate_scope_reduction()`, require:

- If `anchor.constraints.must` is non-empty:
  - `set(anchor.constraints.must)` is a subset of `set(proposal.diff.rationale.constraints_still_met)`

Add tests that fail if only a partial intersection is provided.

### C2) Remove Pydantic warning about `model_id`
**Change**: In `ModelRoutingEntry.model_config`, set:

- `protected_namespaces=()`

This preserves the schema field name and removes warning spam in tests/CI.

---

## Follow-up D — Make the “catalog refresh” the only routing entrypoint (no bypass)

### Objective
Ensure callers cannot accidentally bypass catalog-backed routing by calling the legacy
`model_routing_snapshot.refresh_or_load_snapshot()` code path.

### Direction
`src/autopack/model_routing_snapshot.refresh_or_load_snapshot()` must delegate internally to the
catalog-backed implementation (with a safe fallback to `create_default_snapshot()`).

### Deliverables
- Update `src/autopack/model_routing_snapshot.py`:
  - `refresh_or_load_snapshot(...)` becomes the canonical entrypoint and delegates to
    `autopack.model_routing_refresh.refresh_or_load_snapshot_with_catalog(...)`.
  - Use a lazy import inside the function to avoid circular imports.
  - Preserve the current “load if fresh else create default + save” behavior as a fallback
    if the catalog module fails for any reason.

### Acceptance criteria
- Any call to `refresh_or_load_snapshot()` results in a snapshot that is:
  - catalog-backed when available,
  - otherwise default-backed,
  - and always persisted run-locally.

### Tests
- Add/extend tests to ensure `refresh_or_load_snapshot()` uses the catalog path (mock the catalog function).

---

## Follow-up E — Ensure routing snapshot decisions are consumed by real model selection

### Objective
Avoid “unused artifact” risk: a routing snapshot must actually influence which model is used.

### Direction
Use the existing per-run override plumbing in `ModelRouter` (via `run_context["model_overrides"]`)
as the minimal integration mechanism. This avoids a refactor of `LlmService` and keeps wiring localized.

### Chosen mapping (deterministic)
Map snapshot tier → existing complexity lanes:
- `haiku` → `low`
- `sonnet` → `medium`
- `opus` → `high`

### Deliverables
- In the executor wiring (Phase A), when a snapshot is created/loaded:
  - Build a `run_context` that can carry overrides.
  - Apply overrides for builder and auditor using the key format already used by `ModelRouter`:
    - `"{task_category}:{complexity}"`
  - On a tier escalation decision, update overrides for the phase’s next attempt.

### Acceptance criteria
- A tier escalation decision results in a different `resolved_model` being used on the next attempt.
- Max 1 escalation per phase remains enforced.

### Tests
- Add a small integration-style unit test that:
  - sets `run_context` overrides,
  - calls `LlmService.execute_builder_phase(..., run_context=...)` with a stubbed router/client,
  - asserts that the chosen model matches the override.

---

## Follow-up F — Strengthen SOT write protection (static/read-only)

### Objective
Prevent accidental runtime writes to SOT ledgers (`README.md`, `docs/*`) from *any* runtime-reachable code path,
not just the executor file itself.

### Direction
Expand the static SOT write protection script (read-only) to scan a curated set of runtime modules
that are commonly imported during execution.

### Deliverables
- Update `scripts/check_sot_write_protection.py` to scan:
  - `src/autopack/autonomous_executor.py`
  - `src/autopack/llm_service.py`
  - `src/autopack/archive_consolidator.py`
  - `src/autopack/debug_journal.py`
  - `src/autopack/intention_wiring.py`
  - `src/autopack/autonomous/intention_first_loop.py`
- Extend pattern matching to catch common write APIs even when paths are constructed.

### Acceptance criteria
- CI fails if any of those modules contain likely write calls targeting protected SOT paths.
- Script remains conservative (low false positives) and does not execute code.

---

## Follow-up G — Deterministic budget semantics + policy enforcement tests

### Objective
Make `budget_remaining` a deterministic, intention-anchored input to stuck handling (no guessing),
and enforce “replan-before-escalate” and “max 1 escalation per phase” under budget pressure.

### Direction (chosen)
Compute `budget_remaining` as a deterministic fraction `0..1` derived from:
- Intention Anchor budgets (`anchor.budgets.max_context_chars`, `anchor.budgets.max_sot_chars`)
- deterministic run token cap (`settings.run_token_cap`)
- measured usage (usage events already recorded by `LlmService`)

Then take the minimum of token/context/SOT remaining fractions and clamp to `[0,1]`.

### Deliverables
- New helper module: `src/autopack/autonomous/budgeting.py`
  - `compute_budget_remaining(...) -> float`
  - inputs must be explicit and testable (no implicit global state)
- Executor wiring uses this helper to feed `IntentionFirstLoop.decide_when_stuck(...)`.

### Tests
- `tests/autopack/test_budgeting.py` (pure function tests: clamping, determinism, edge cases)
- `tests/autopack/test_intention_first_loop_budget_policy.py`:
  - verifies “replan before escalate”
  - verifies “max 1 escalation per phase”
  - verifies low budget drives `REDUCE_SCOPE` rather than escalation

---

## CI / Read-only posture (must remain true)

The following must remain mechanically enforced:

- Docs integrity:
  - `pytest -q tests/docs`
  - `python scripts/tidy/sot_summary_refresh.py --check`
- SOT write protection:
  - `python scripts/check_sot_write_protection.py`
- CI must not run apply; it must be read-only.


