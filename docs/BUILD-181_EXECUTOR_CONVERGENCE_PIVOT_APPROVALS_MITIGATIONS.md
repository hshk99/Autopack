# BUILD-181: Executor Convergence + Pivot-Gated Approvals + Deterministic Mitigations

**Status**: COMPLETE
**Priority**: High (completes executor convergence, adds pivot-gated approvals, enables failure-to-mitigation loop)
**Related**: BUILD-180 (Mechanical Enforcement Convergence), BUILD-179 (CLI/Supervisor), BUILD-178 (Pivot Intentions v2)
**Aligned to README ideal state**: safe, deterministic, mechanically enforceable; SOT-led memory; execution writes run-local only; explicit gates; default-deny autonomy.

---

## Why (gap vs ideal state)

BUILD-180 closed several mechanical enforcement gaps (autopilot execution, doc drift detection, workspace digest determinism, phase proof metrics, CI guards, model catalog). However, several executor TODOs and capability gaps remain:

| Gap | Current State | Ideal State |
|-----|---------------|-------------|
| Usage accounting | Placeholder counters in stuck handling | Real usage events as single source of truth |
| Safety profile | Hardcoded `"normal"` in model escalation | Derived deterministically from IntentionAnchorV2 |
| Scope reduction | Policy can decide `REDUCE_SCOPE` but executor falls back | Proposal-only flow with schema-validated artifacts |
| Patch 422 correction | HTTP 422 from validator is a dead-end | Bounded one-shot correction attempt with evidence |
| Coverage delta | Returns `0.0` placeholder when unknown | Returns `None` unless real coverage data available |
| Telegram approvals | Missing integration for pivot-impacting events | Pivot-only triggers, disabled by default |
| Failure → mitigations | No reusable prevention from failures | Deterministic rule generator (no LLM) |

This BUILD closes these gaps with **mechanical, deterministic, test-backed** implementations.

---

## Non-overlapping with BUILD-180 (conflict avoidance)

**BUILD-180 hot files NOT touched by this build**:
- `src/autopack/autonomy/*` (autopilot, action_executor, action_allowlist, parallelism_gate)
- `src/autopack/gaps/scanner.py`
- `src/autopack/model_routing_refresh.py`
- `src/autopack/parallel_orchestrator.py`
- `.github/workflows/*`

**BUILD-181 creates new modules** to avoid merge conflicts:
- `src/autopack/executor/` - New namespace for executor convergence
- `src/autopack/approvals/` - Telegram approval service
- `src/autopack/mitigations/` - Deterministic mitigation generator
- Integration via existing non-hot entrypoints only

---

## Direction (no ambiguity)

1. **Usage accounting uses recorded usage events** as the single source of truth for tokens_used, context_chars_used, sot_chars_used. Aggregation is stable and sorted (no nondeterministic ordering).

2. **Safety profile derived deterministically from IntentionAnchorV2**:
   - `risk_tolerance in {"minimal","low"}` → `safety_profile="strict"`
   - `risk_tolerance in {"moderate","high"}` → `safety_profile="normal"`
   - Missing safety_risk pivot → default `strict` (fail-safe)

3. **Scope reduction produces schema-validated proposal artifact** (run-local JSON). Never auto-applies; either auto-approved by explicit rules (very rare) or requires approval (default).

4. **Patch 422 correction attempts exactly once**, feeds validator error details + original patch into correction prompt, records evidence regardless of outcome.

5. **Coverage delta returns `None` when unknown**, not `0.0`. No executor decisions depend on coverage delta unless real and verified.

6. **Telegram approval triggers only for pivot-impacting events**:
   - Pivot intention change (update to anchor itself)
   - Pivot constraint violation (protected paths from pivot, NEVER_AUTO_APPROVE)
   - Governance escalation (risk tier requiring approval)
   - **Never triggers for**: normal retries, replans, model escalations within pivot bounds

7. **Telegram is never active in CI** and requires explicit runtime configuration.

8. **Deterministic mitigation generator** maps known failure signatures → templated rules, outputs `mitigation_proposal_v1.json` run-locally. No LLM required.

---

## Scope

### In scope

- Real usage accounting for stuck handling decisions
- Safety profile derivation from anchor
- Scope reduction proposal flow (proposal-only, schema-validated)
- Patch 422 one-shot correction with evidence
- Coverage delta `None` when unknown
- Telegram approval service (pivot-only triggers, disabled by default)
- Deterministic mitigation proposal generator
- Schema for `mitigation_proposal_v1.json`

### Not in scope

- Changes to BUILD-180 hot files
- Full telemetry instrumentation (bounded/minimal only)
- LLM-based mitigation generation
- SOT writes from runtime (tidy remains the only SOT writer)
- Parallel phases within a single run

---

## Implementation Plan

### Phase 0 - Contract-first tests (mechanical enforcement before behavior)

**Goal**: Ensure changes are enforceable, deterministic where required, and default-deny safe.

**Tests to add**:
- Telegram approval triggers **only** on pivot-intention-change / pivot-violation events
- Usage accounting is deterministic given the same stored usage events
- Scope reduction produces a schema-valid proposal artifact and never auto-applies
- 422 patch validation correction retries at most once and records evidence
- Coverage delta is not fabricated (no "0.0" placeholder when unknown)

**Files**:
- `tests/executor/test_usage_accounting_deterministic.py` (new)
- `tests/executor/test_safety_profile_derivation.py` (new)
- `tests/executor/test_scope_reduction_proposal_schema.py` (new)
- `tests/executor/test_patch_correction_one_shot.py` (new)
- `tests/executor/test_coverage_delta_none_when_unknown.py` (new)
- `tests/approvals/test_telegram_trigger_pivot_only.py` (new)
- `tests/mitigations/test_deterministic_mitigation_proposals.py` (new)

**Acceptance criteria**:
- [ ] Tests fail on current TODO/placeholder behavior (red-green cycle)
- [ ] Tests run offline (no network) and deterministically

---

### Phase 1 - Real usage accounting for intention-first stuck handling

**Goal**: Use recorded usage events as the single source of truth for stuck decisions.

**Work**:
- Implement `src/autopack/executor/usage_accounting.py`:
  - `aggregate_usage(events: List[UsageEvent]) -> UsageTotals`
  - `load_usage_events(run_id: str, artifact_path: Path) -> List[UsageEvent]`
- Aggregation is stable and sorted (no nondeterministic ordering)
- All inputs explicit and testable

**Files**:
- `src/autopack/executor/usage_accounting.py` (new)
- `src/autopack/executor/__init__.py` (new)

**Acceptance criteria**:
- [ ] Same run artifacts → same computed usage numbers
- [ ] No implicit globals; all inputs explicit and testable

---

### Phase 2 - Derive safety profile from IntentionAnchorV2

**Goal**: Safety routing reflects declared intention, not a constant.

**Work**:
- Implement `src/autopack/executor/safety_profile.py`:
  - `derive_safety_profile(anchor: IntentionAnchorV2) -> Literal["normal","strict"]`
- Deterministic mapping from risk_tolerance
- Missing safety_risk pivot → default `strict` (fail-safe)

**Files**:
- `src/autopack/executor/safety_profile.py` (new)

**Acceptance criteria**:
- [ ] Model escalation uses derived safety profile consistently
- [ ] No silent "normal" default when intention is missing

---

### Phase 3 - Scope reduction prompt generation + validation (proposal-only)

**Goal**: When policy decides `REDUCE_SCOPE`, executor generates proposal artifact.

**Work**:
- Implement `src/autopack/executor/scope_reduction_flow.py`:
  - `build_scope_reduction_prompt(anchor, phase_state, budget_remaining) -> str`
  - `validate_scope_reduction_json(proposal, anchor) -> Tuple[bool, str]`
  - `write_scope_reduction_proposal(run_layout, proposal) -> Path`
- Never auto-applies; requires approval (default) or explicit auto-approve rules

**Files**:
- `src/autopack/executor/scope_reduction_flow.py` (new)
- `docs/schemas/scope_reduction_proposal_v1.schema.json` (new)

**Acceptance criteria**:
- [ ] When stuck policy returns `REDUCE_SCOPE`, run produces proposal artifact
- [ ] Halts with actionable message (or continues only if auto-approved)

---

### Phase 4 - Patch validator 422 correction loop (bounded, evidenceful)

**Goal**: Attempt one correction cycle on HTTP 422 from patch validation.

**Work**:
- Implement `src/autopack/executor/patch_correction.py`:
  - `should_attempt_patch_correction(http_422_detail, budget_remaining) -> bool`
  - `correct_patch_once(original_patch, validator_error_detail, context) -> CorrectedPatchResult`
- Max 1 correction attempt per 422 event
- Correction attempt recorded in run-local artifacts

**Files**:
- `src/autopack/executor/patch_correction.py` (new)

**Acceptance criteria**:
- [ ] Max 1 correction attempt per 422 event
- [ ] Evidence recorded (inputs, error summary, result)

---

### Phase 5 - Coverage delta: remove "fake metric"

**Goal**: Coverage delta returns `None` unless real data available.

**Work**:
- Implement `src/autopack/executor/coverage_metrics.py`:
  - `compute_coverage_delta(ci_result: Optional[Dict]) -> Optional[float]`
- No executor decisions depend on coverage delta unless real and verified
- No placeholder "0.0" emitted as if measured

**Files**:
- `src/autopack/executor/coverage_metrics.py` (new)

**Acceptance criteria**:
- [ ] No placeholder "0.0" emitted
- [ ] System says "unknown" deterministically when coverage absent

---

### Phase 6 - Telegram approval service (pivot-only triggers)

**Goal**: Approvals have a reliable operator channel, but only for pivot-impacting events.

**Work**:
- Implement `src/autopack/approvals/service.py`:
  - `ApprovalRequest` (pivot-impacting payload, bounded)
  - `ApprovalService` interface
  - `NoopApprovalService` (default)
- Implement `src/autopack/approvals/telegram.py`:
  - `TelegramApprovalService` (enabled only when configured)
  - Formats messages with anchor_id + pivot section + diff summary
- Single choke point: governance decision explicitly "pivot-impacting"

**Files**:
- `src/autopack/approvals/__init__.py` (new)
- `src/autopack/approvals/service.py` (new)
- `src/autopack/approvals/telegram.py` (new)

**Acceptance criteria**:
- [ ] Telegram messages only for pivot-impacting approvals
- [ ] No Telegram integration runs in CI
- [ ] Misconfigured Telegram fails safely (records evidence, halts if required)

---

### Phase 7 - Telemetry → deterministic mitigations loop (proposal-only)

**Goal**: Turn failures into reusable prevention rules without LLM.

**Work**:
- Implement `src/autopack/mitigations/deterministic_rules.py`:
  - `known_signature_to_rule(signature: str) -> Optional[Rule]`
  - `generate_mitigation_proposal(inputs: MitigationInputs) -> MitigationProposalV1`
- Deterministic rule generator (no LLM), reads failure signatures, maps to templated rules
- Outputs `mitigation_proposal_v1.json` run-locally
- Tidy can later consolidate approved mitigations (not runtime)

**Files**:
- `src/autopack/mitigations/__init__.py` (new)
- `src/autopack/mitigations/deterministic_rules.py` (new)
- `docs/schemas/mitigation_proposal_v1.schema.json` (new)

**Acceptance criteria**:
- [ ] Same inputs → same proposal output
- [ ] No SOT writes during runtime

---

## Testing / Verification Plan

### Must-pass (CI-blocking)

| Test | Validates |
|------|-----------|
| `test_usage_accounting_deterministic.py` | Same events → same totals |
| `test_safety_profile_derivation.py` | Deterministic mapping from anchor |
| `test_scope_reduction_proposal_schema.py` | Valid schema, no auto-apply |
| `test_patch_correction_one_shot.py` | Max 1 attempt, evidence recorded |
| `test_coverage_delta_none_when_unknown.py` | No fake 0.0, None when unknown |
| `test_telegram_trigger_pivot_only.py` | Only pivot-impacting events |
| `test_deterministic_mitigation_proposals.py` | Same inputs → same output |

### Informational

- End-to-end stuck handling with real usage accounting
- Telegram service mock integration test

---

## Failure Modes (how it must fail)

| Scenario | Expected Behavior |
|----------|-------------------|
| Missing anchor pivots for safety | Treat as **strict**, require approval; never silently relax |
| Telegram misconfigured | Records "approval requested but channel unavailable", halts if required |
| 422 correction fails | Stops after one attempt, records evidence, no retry loop |
| Coverage unknown | `None`, not `0.0` |
| Scope reduction without approval | Proposal written, execution halts with message |
| Usage events empty | Returns zero totals (valid), stuck handling proceeds |

---

## File Skeleton Summary

### New Files

```
src/autopack/executor/__init__.py
src/autopack/executor/usage_accounting.py
src/autopack/executor/safety_profile.py
src/autopack/executor/scope_reduction_flow.py
src/autopack/executor/patch_correction.py
src/autopack/executor/coverage_metrics.py

src/autopack/approvals/__init__.py
src/autopack/approvals/service.py
src/autopack/approvals/telegram.py

src/autopack/mitigations/__init__.py
src/autopack/mitigations/deterministic_rules.py

docs/schemas/scope_reduction_proposal_v1.schema.json
docs/schemas/mitigation_proposal_v1.schema.json

tests/executor/__init__.py
tests/executor/test_usage_accounting_deterministic.py
tests/executor/test_safety_profile_derivation.py
tests/executor/test_scope_reduction_proposal_schema.py
tests/executor/test_patch_correction_one_shot.py
tests/executor/test_coverage_delta_none_when_unknown.py

tests/approvals/__init__.py
tests/approvals/test_telegram_trigger_pivot_only.py

tests/mitigations/__init__.py
tests/mitigations/test_deterministic_mitigation_proposals.py
```

### Modified Files

**NONE from BUILD-180 hot list** - all integration via new modules.

---

## Deliverables Checklist

- [x] No changes in BUILD-180 hot file list
- [x] New build doc created under `docs/BUILD-181_...md`
- [x] Tests added and passing (60 tests)
- [x] No runtime SOT writes introduced
- [x] Telegram approval triggers only for pivot-impacting approvals and is disabled by default
- [x] CI green for branch

---

## References

- [README.md](../README.md) - Ideal state definition
- [BUILD-180](BUILD-180_MECHANICAL_ENFORCEMENT_CONVERGENCE.md) - Mechanical enforcement (complete)
- [BUILD-179](BUILD-179_AUTONOMY_CLI_AND_SUPERVISOR_CONSOLIDATION.md) - CLI/Supervisor consolidation
- [BUILD-178](BUILD-178_PIVOT_INTENTIONS_V2_GAP_TAXONOMY_AUTONOMY_LOOP.md) - Pivot Intentions v2
- [GOVERNANCE.md](GOVERNANCE.md) - Default-deny posture
- [stuck_handling.py](../src/autopack/stuck_handling.py) - Stuck handling policy
