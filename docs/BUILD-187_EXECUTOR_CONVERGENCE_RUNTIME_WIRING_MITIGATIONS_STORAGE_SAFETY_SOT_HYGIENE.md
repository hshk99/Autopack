# BUILD-187: Executor Convergence (Runtime Wiring) + Deterministic Mitigations + Storage Safety Gate + SOT Hygiene

**Status**: READY TO IMPLEMENT (not started)

**Priority**: High (closes remaining gaps to README ideal state: safe, deterministic, mechanically enforceable)

**Related**:
- BUILD-181 (Executor modules + approvals + deterministic mitigations — modules exist)
- BUILD-180 (Mechanical enforcement convergence)
- BUILD-186 (Deterministic console glyph normalization — already implemented separately; out of scope here)
- README.md (Ideal state: run-local execution artifacts; tidy-only SOT writes; CI contracts)

**Current note**: BUILD-178 is in progress. This BUILD MUST NOT assume BUILD-178 completion status or update SOT ledgers directly at runtime.

---

## Why (gap vs README ideal state)

Autopack’s README ideal state is: **safe, deterministic, mechanically enforceable via CI contracts**, with:
- execution writing **run-local artifacts only**
- tidy as **the only SOT writer** (append-only ledgers)
- default-deny governance and explicit approvals for pivot-impacting changes

We already have most “component” implementations in `src/autopack/executor/`, `src/autopack/approvals/`, `src/autopack/mitigations/`, and `src/autopack/storage_optimizer/approval.py`.

However, several runtime paths still behave like placeholders because they **do not consume these components end-to-end** (e.g., `autonomous_executor.py` TODOs: usage accounting, safety profile derivation, scope reduction, deterministic changed-files, bounded patch correction, approvals wiring, report parsing).

BUILD-187 turns the existing building blocks into **mechanically enforced, end-to-end runtime behavior**, and adds minimal SOT hygiene checks to prevent “two truths”.

---

## Direction (no options; chosen to preserve README intentions)

1. **Runtime remains read/write limited to run-local artifacts** under `RunFileLayout.base_dir`. Runtime MUST NOT write to SOT (`README.md`, `docs/**`).
2. **Determinism is mandatory** for any output used in decisions, gating, or CI enforcement:
   - sort sets/lists
   - stable IDs and hashes
   - bounded artifacts with explicit “unknown” semantics (never fake metrics)
3. **Default-deny governance**:
   - approvals trigger only for **pivot-impacting** events
   - approvals are disabled by default and **never active in CI**
4. **Stuck-handling decisions must use real usage events** as the single source of truth (no placeholder counters).
5. **Scope reduction is proposal-only**:
   - schema-validated artifact, written run-locally
   - never auto-applies; requires explicit approval by default
6. **Patch correction is bounded**:
   - at most one correction attempt per HTTP 422 validation failure
   - records evidence run-locally
7. **Coverage is never fabricated**:
   - returns `None` (unknown) unless real coverage data is available and trusted
8. **Deterministic mitigation proposals are produced run-locally**, and only become durable “rules” via tidy consolidation (never runtime SOT writes).
9. **Storage Optimizer destructive actions require an approval artifact** matching `report_id` with a hashed audit trail.
10. **SOT hygiene is enforced mechanically**:
   - detect “build docs exist but not indexed” and “living doc TODO refers to already-implemented code”
   - do not auto-edit SOT in runtime; treat as CI/report-only guardrails

---

## Ambiguities (resolved)

### A1) Where do usage events come from?
**Decision**: usage events are emitted by the runtime boundary that has real usage info (the LLM execution layer, e.g., `LlmService` / router / client wrapper). Executor components aggregate these events deterministically.

### A2) What is an “iteration” for stuck-handling counters?
**Decision**: one “phase attempt cycle” increments `iterations_used` once:
Builder attempt → (optional) Auditor/QualityGate evaluation. Infrastructure-only retries do not create separate “attempt cycles” unless they re-run the phase.

### A3) When does approval trigger?
**Decision**: only on pivot-impacting events, as defined in `autopack.approvals.service.should_trigger_approval()`:
- pivot intention change
- pivot constraint violation / NEVER_AUTO_APPROVE pattern hit
- governance escalation requiring human review
No approvals for normal retries, replans, or model escalation within bounds.

### A4) How do we determine changed files deterministically?
**Decision**: the canonical source is `git diff --name-only` bounded to the workspace root when git is available; otherwise the system records `files_changed=None` with explicit `git_unavailable` evidence. No placeholder empty lists pretending “no changes”.

### A5) What do we do about “build docs not in BUILD_HISTORY.md” while BUILD-178 is in progress?
**Decision**: add a CI/report-only check that flags this condition, but do not auto-fix or auto-update the ledgers. Tidy (or a human) remains the only SOT writer.

---

## Scope

### In scope
- Wire existing BUILD-181 executor modules into real runtime paths (eliminate TODO placeholder behaviors)
- Emit + persist usage events and consume them for stuck/budget decisions
- Derive safety profile from `IntentionAnchorV2` and use it in escalation/governance
- Scope reduction proposal artifact flow + schema validation (proposal-only)
- HTTP 422 patch correction (single attempt) + evidence artifacts
- Coverage semantics: unknown is `None`, never `0.0`
- Deterministic changed-files extraction and persistence
- Telegram approvals integration (pivot-only triggers, disabled by default, never in CI)
- Auditor/QualityGate report parsing into structured fields where feasible (deterministic)
- Deterministic mitigation proposal generation from failure signatures (proposal-only)
- Storage optimizer execution safety gate (approval artifact + hashed audit trail)
- CI/report-only SOT hygiene checks (no runtime SOT writes)
- Doc-link triage completion artifact (medium/low confidence) as a single durable report (no mass rewrites)

### Not in scope
- Parallel phases within a single run
- Any runtime “auto-apply to repo” behavior without explicit approvals
- Any change that makes CI write to SOT (CI remains read-only)
- Broad refactors of BUILD-178 in-progress work

---

## Implementation Plan

### Phase 0 — Contract-first tests (mechanical enforcement before behavior)

**Goal**: tests must fail on current placeholder/TODO behaviors and enforce the direction above.

**Add/extend tests**:
- usage accounting determinism (same events → same totals)
- safety profile derivation mapping + fail-safe strictness on missing pivots
- scope reduction proposal schema validity + “never auto-apply”
- patch correction: max 1 attempt + evidence written
- coverage info: `None` when unknown; never `0.0` placeholder
- approvals: pivot-only triggers; never active in CI
- mitigation proposals: deterministic output + stable IDs
- changed-files: git vs non-git semantics
- storage optimizer: cannot execute destructive actions without matching approval/report_id
- SOT hygiene check: detects unindexed BUILD docs + stale TODO references (report-only)

---

### Phase 1 — Runtime usage event emission + aggregation (close “placeholder counters”)

**Goal**: the executor consumes real usage events recorded at the LLM execution boundary.

**Work**:
- ensure each LLM call records a `UsageEvent` with stable fields (tokens/context/sot chars)
- persist usage events under `<run_base>/usage/usage_events.json`
- ensure stuck handling uses `aggregate_usage()` + `compute_budget_remaining()` (no local counters)

**Acceptance criteria**:
- same run artifacts → same computed budgets and stuck decisions
- no hidden global state; all inputs explicit

---

### Phase 2 — Safety profile derivation is authoritative

**Goal**: eliminate any hardcoded `"normal"` in escalation/governance decisions.

**Work**:
- route all safety decisions through `derive_safety_profile(anchor)`
- enforce fail-safe defaults (strict when safety pivot missing)

**Acceptance criteria**:
- safety profile used consistently in escalation and governance
- no “silent relax” behavior

---

### Phase 3 — Scope reduction proposal flow (proposal-only, schema-validated)

**Goal**: when policy decides `REDUCE_SCOPE`, produce a validated proposal artifact and halt pending approval.

**Work**:
- build prompt from anchor + phase state
- generate proposal JSON (deterministic ID) + validate against anchor constraints
- write to `<run_base>/proposals/scope_reduction_*.json`

**Acceptance criteria**:
- proposal artifact always written on REDUCE_SCOPE
- proposal is schema-valid and anchor-consistent
- never auto-applies

---

### Phase 4 — Bounded 422 patch correction (one-shot) + evidence

**Goal**: when validator returns HTTP 422, attempt a single correction pass and record evidence regardless of outcome.

**Work**:
- implement/consume `PatchCorrectionTracker`
- ensure “max 1 attempt” is enforced per 422 event
- store evidence under `<run_base>/evidence/patch_correction/*.json`

**Acceptance criteria**:
- exactly one correction attempt max
- deterministic evidence artifact structure

---

### Phase 5 — Coverage semantics: unknown is `None` (never fake 0.0)

**Goal**: remove placeholder metrics and make “unknown” explicit.

**Work**:
- use `compute_coverage_info()` and `should_trust_coverage()`
- ensure any UI/reporting shows “unknown” explicitly

**Acceptance criteria**:
- coverage delta is `None` when not available
- no downstream decisions depend on fabricated values

---

### Phase 6 — Deterministic changed-files extraction and persistence

**Goal**: replace TODO placeholders for changed files extraction.

**Work**:
- compute `files_changed` from git diff when available (bounded list + count)
- persist to run-local artifacts for Builder/Auditor/QualityGate summaries

**Acceptance criteria**:
- stable ordering (sorted)
- explicit `None`/evidence when git unavailable

---

### Phase 7 — Telegram approvals integration (pivot-only, disabled by default)

**Goal**: integrate approvals service into executor/autopilot events without enabling it in CI.

**Work**:
- unify event emission so pivot-impacting events call `get_approval_service()` + `request_approval()`
- ensure CI returns `NoopApprovalService` always

**Acceptance criteria**:
- pivot-only triggers
- safe failure mode on misconfiguration (evidence + halt if required)

---

### Phase 8 — Auditor/QualityGate parsing improvements (deterministic)

**Goal**: replace “empty placeholders” for confidence/suggested patches/files where the data is available in messages/artifacts.

**Work**:
- parse structured sections from auditor output (deterministic regex, bounded)
- never guess; only populate when parse succeeds with high confidence

**Acceptance criteria**:
- deterministic parsing
- fallback remains explicit (“unknown / not parsed”)

---

### Phase 9 — Telemetry → deterministic mitigations loop (proposal-only)

**Goal**: produce `mitigation_proposal_v1.json` run-locally from failure signatures, then let tidy consolidate approved rules later.

**Work**:
- generate failure signatures deterministically (from known exceptions / HTTP codes / phase outcomes)
- call `generate_mitigation_proposal()` and write artifact to `<run_base>/proposals/mitigation_*.json`

**Acceptance criteria**:
- same inputs → same proposal output
- no runtime SOT writes

---

### Phase 10 — Storage optimizer execution safety gate (approval + hashed audit)

**Goal**: destructive storage optimizer actions require explicit approval artifact tied to report_id.

**Work**:
- ensure report generation emits deterministic report_id
- executor refuses destructive actions unless `verify_approval()` succeeds
- append audit entries to `<run_base>/storage/audit.jsonl`

**Acceptance criteria**:
- destructive actions blocked without valid approval
- hashed audit trail exists for each action

---

### Phase 11 — SOT hygiene + doc-link triage completion (mechanical, report-only)

**Goal**: prevent “two truths” and close the remaining doc triage gap without weakening enforcement.

**Work**:
- CI/report-only checker:
  - flags `docs/BUILD-*.md` present but not indexed in `docs/BUILD_HISTORY.md`
  - flags living docs with stale “TODO implement X” when X exists (e.g., `SECURITY_BURNDOWN.md` referencing `check_production_config.py`)
- finalize medium/low-confidence doc-link triage into a single durable report artifact (no mass edits)

**Acceptance criteria**:
- CI surfaces drift as failures or warnings per policy (chosen in implementation, but must be deterministic)
- no runtime writes to SOT

---

## File Skeleton Summary (expected shape)

### Runtime wiring / executor convergence

- `src/autopack/autonomous_executor.py` (modify)
  - remove/replace remaining TODO placeholders by consuming BUILD-181 modules
- `src/autopack/autonomy/executor_integration.py` (modify as needed)
  - ensure it is the single “glue” point for executor concerns

### Usage events (emit + persist + aggregate)

- `src/autopack/llm_service.py` (modify) OR the closest boundary that sees real usage
  - emit `UsageEvent`s deterministically
- `src/autopack/executor/usage_accounting.py` (already exists; extend if needed)

### Approvals (pivot-only)

- `src/autopack/approvals/service.py` (already exists; extend if needed)
- `src/autopack/approvals/telegram.py` (already exists)

### Mitigations (proposal-only)

- `src/autopack/mitigations/deterministic_rules.py` (already exists; extend signature mapping if needed)
- `src/autopack/schemas/mitigation_proposal_v1.schema.json` (already exists)

### Storage safety gate

- `src/autopack/storage_optimizer/approval.py` (already exists)
- `src/autopack/storage_optimizer/executor.py` (modify) to enforce approval gating for destructive operations

### SOT hygiene checks (CI/report-only)

- `scripts/ci/check_sot_hygiene.py` (new)
  - detect unindexed build docs; detect stale TODO references
- `.github/workflows/ci.yml` (modify) to run this checker (read-only)

### Doc-link triage

- `docs/reports/DOC_LINK_TRIAGE.md` (new, single durable triage report)

---

## Test Skeleton Summary (expected shape)

- `tests/executor/test_usage_accounting_deterministic.py`
- `tests/executor/test_safety_profile_derivation.py`
- `tests/executor/test_scope_reduction_proposal_schema.py`
- `tests/executor/test_patch_correction_one_shot.py`
- `tests/executor/test_coverage_delta_none_when_unknown.py`
- `tests/approvals/test_telegram_trigger_pivot_only.py`
- `tests/mitigations/test_deterministic_mitigation_proposals.py`
- `tests/storage_optimizer/test_execution_gate.py`
- `tests/ci/test_sot_hygiene_checks.py`

All tests must be offline, deterministic, and bounded.

---

## Verification / Mechanical Contracts (must remain true)

- CI remains read-only:
  - docs integrity tests
  - SOT summary drift checks
  - SOT write protection checks
- Runtime writes run-local only
- Approval gates are explicit, pivot-only, and disabled by default


