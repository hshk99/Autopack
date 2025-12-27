# AUTOPACK Issue Timeline (Revised)

- Generated: 2025-12-27
- Inputs: `AUTOPACK_ISSUE_TIMELINE_FOR_AI_ANALYSIS.json`, `AUTOPACK_ISSUE_TIMELINE_READABLE.md`, `ref2.md`

## Summary
- Issues tracked: **29** across **12** chronological blocks
- Resolved/systemic fixes landed: **26**
- Persistent by design: **3** (`REAL-001, REAL-002, REAL-003`)

## Chronological Timeline

### Phase 1: NDJSON Parser Convergence (2025-12-27 00:00-02:00)

#### NDJSON-001: Builder failed: ndjson_no_operations - operations list empty despite mo…

**Symptom**: Builder failed: ndjson_no_operations - operations list empty despite model output

**Root Cause**: Model emitting top-level JSON wrapper {"files":[...]} instead of NDJSON lines; parser decoded but treated as single op and dropped

**Impact**: Systemic blocker - phases cannot apply any operations

**Fix**:
- Commit: `b0fe3cc6`
- Files:
  - `src/autopack/ndjson_format.py`
  - `tests/test_ndjson_format.py`
- Changes: Parser now expands {"files":[...]} wrapper into NDJSON operations; truncate-tolerant scan extracts inner file objects even if outer wrapper incomplete

**Verification**: 3 single-batch drains showed ndjson_no_operations: 0 occurrences; operations recovered and applied

**Led To**: DELIV-001

**Persisted**: ❌ RESOLVED

---

### Phase 2: Deliverables & Scope Convergence (2025-12-27 01:00-02:30)

#### DELIV-001: Deliverables validation fails with 'Found in patch: 6/17 files' across…

**Symptom**: Deliverables validation fails with 'Found in patch: 6/17 files' across multiple retry attempts

**Root Cause**: validate_deliverables() only checked current patch text; NDJSON earlier attempts wrote files to disk but later attempts didn't re-emit them in synthetic diff

**Impact**: Multi-attempt convergence impossible; phases stuck in retry loop

**Fix**:
- Commit: `5349a1ae`
- Files:
  - `src/autopack/deliverables_validator.py`
  - `tests/test_deliverables_validator.py`
- Changes: Cumulative validation: existing deliverables on disk now satisfy requirements

**Verification**: Phases could complete across multiple truncated attempts

**Persisted**: ❌ RESOLVED

---
#### SCOPE-001: Writes to src/*, docs/*, tests/* rejected as 'outside scope'

**Symptom**: Writes to src/*, docs/*, tests/* rejected as 'outside scope'

**Root Cause**: Inferred scope paths included bucket roots like 'code/tests/docs'; _determine_workspace_root() picked C:\dev\Autopack\code instead of repo root

**Impact**: False 'outside scope' blocks prevent valid file operations

**Fix**:
- Commit: `0dc08ecc`
- Files:
  - `src/autopack/autonomous_executor.py`
  - `src/autopack/manifest_generator.py`
  - `tests/test_manifest_deliverables_aware.py`
- Changes: Heuristic: if scope starts with src/docs/tests/etc., treat workspace as repo root; flatten bucketed deliverables {code:[...], tests:[...]} to prevent 'code' becoming a scope root

**Persisted**: ❌ RESOLVED

---
#### SCOPE-002: Nonsense scope entries like 'Improved' causing 'outside manifest' viola…

**Symptom**: Nonsense scope entries like 'Improved' causing 'outside manifest' violations

**Root Cause**: Prose deliverables like 'Logging configuration' treated as file paths

**Impact**: Manifest validation fails on non-existent file paths

**Fix**:
- Commit: `de8c9c4d`
- Files:
  - `src/autopack/deliverables_validator.py`
  - `src/autopack/manifest_generator.py`
- Changes: Sanitizer filters out prose bullets (non-path strings) before scope/manifest/validator logic

**Persisted**: ❌ RESOLVED

---
#### APPLY-001: Patch validation failed - incomplete diff structure on NDJSON synthetic…

**Symptom**: Patch validation failed - incomplete diff structure on NDJSON synthetic header

**Root Cause**: Executor called git apply on synthetic 'NDJSON Operations Applied...' header (not a real diff)

**Impact**: Apply phase fails even though operations already applied to disk

**Fix**:
- Commit: `9b53e09f`
- Files:
  - `src/autopack/governed_apply.py`
  - `tests/test_governed_apply_ndjson_synthetic_header.py`
- Changes: GovernedApplyPath.apply_patch() detects NDJSON synthetic header and skips git apply while still enforcing scope/protected-path validation

**Persisted**: ❌ RESOLVED

---

### Phase 3: Doctor & Retry Interference (2025-12-27 01:30-02:30)

#### RETRY-001: Doctor/replan triggered after TOKEN_ESCALATION, resetting state and pre…

**Symptom**: Doctor/replan triggered after TOKEN_ESCALATION, resetting state and preventing P10 retry budget from being applied

**Root Cause**: TOKEN_ESCALATION treated as diagnosable failure instead of control-flow signal

**Impact**: P10 escalation loop never converges; retries don't use escalated token budget

**Fix**:
- Commit: `5349a1ae`
- Files:
  - `src/autopack/autonomous_executor.py`
- Changes: Skip Doctor/diagnostics/replan for TOKEN_ESCALATION; advance retry_attempt deterministically

**Persisted**: ❌ RESOLVED

---
#### SAFETY-001: git reset --hard / git clean -fd could be executed mid-convergence, wip…

**Symptom**: git reset --hard / git clean -fd could be executed mid-convergence, wiping partial deliverables

**Root Cause**: Doctor execute_fix with fix_type=git allowed in project_build runs

**Impact**: Convergence blocked by destructive repo operations; traceability lost

**Fix**:
- Commit: `0dc08ecc`
- Files:
  - `src/autopack/autonomous_executor.py`
- Changes: Block execute_fix with fix_type=git for project_build; record reason in debug journal

**Verification**: log_fix() now auto-creates issue entry if missing; includes run_id/phase_id/outcome

**Persisted**: ❌ RESOLVED

---

### Phase 4: Drain Reliability & API/DB Mismatch (2025-12-27 08:00-12:30)

#### DRAIN-001: Drain reports queued>0 but executor says 'No more executable phases'

**Symptom**: Drain reports queued>0 but executor says 'No more executable phases'

**Root Cause**: Drain script counted queued phases from local SQLite; executor queried API server pointing at different DB (API/DB mismatch)

**Impact**: Drains silently stall; queued phases never execute

**Fix**:
- Commit: `Part of drain_queued_phases.py updates`
- Files:
  - `scripts/drain_queued_phases.py`
- Changes: Default to ephemeral AUTOPACK_API_URL (free localhost port) when not set; ensures API and drain script use same DATABASE_URL

**Persisted**: ❌ RESOLVED

---
#### API-001: GET /runs/{id} returns empty phases list; executor sees no executable w…

**Symptom**: GET /runs/{id} returns empty phases list; executor sees no executable work

**Root Cause**: RunResponse schema missing top-level phases field; only serialized Tier rows (missing for patch-scoped/legacy runs)

**Impact**: Executor cannot select queued phases from tierless runs

**Fix**:
- Commit: `Schema update`
- Files:
  - `src/autopack/schemas.py`
- Changes: RunResponse includes top-level phases list; works for runs with/without Tier rows

**Persisted**: ❌ RESOLVED

---
#### API-002: POST /update_status returns 400 'Invalid phase state: BLOCKED'

**Symptom**: POST /update_status returns 400 'Invalid phase state: BLOCKED'

**Root Cause**: Executor sending 'BLOCKED' status; API only accepts PhaseState enum values (no BLOCKED)

**Impact**: Phase state updates fail; DB state incorrect

**Fix**:
- Commit: `Part of autonomous_executor updates`
- Files:
  - `src/autopack/autonomous_executor.py`
- Changes: Map 'BLOCKED' → 'FAILED' in _update_phase_status and governance handler

**Persisted**: ❌ RESOLVED

---

### Phase 5: CI Artifact & PhaseFinalizer (2025-12-27 09:00-10:30)

#### CI-001: PhaseFinalizer crashes with JSONDecodeError when parsing report_path

**Symptom**: PhaseFinalizer crashes with JSONDecodeError when parsing report_path

**Root Cause**: CI only persisted text log; PhaseFinalizer assumed report_path was pytest-json-report JSON file

**Impact**: Phase finalization fails; cannot compute test baseline delta

**Fix**:
- Commit: `Part of autonomous_executor CI updates`
- Files:
  - `src/autopack/autonomous_executor.py`
  - `src/autopack/phase_finalizer.py`
- Changes: pytest CI now emits JSON report (--json-report); PhaseFinalizer delta computation wrapped to never crash phase execution

**Verification**: CI results include both report_path (JSON) and log_path (text)

**Persisted**: ❌ RESOLVED

---
#### FINALIZER-001: Phases permanently FAILED despite '✅ Approval GRANTED (auto-approved)'…

**Symptom**: Phases permanently FAILED despite '✅ Approval GRANTED (auto-approved)' in logs

**Root Cause**: PhaseFinalizer hard-failed any phase with quality_report.is_blocked=True; didn't consider human_approved override

**Impact**: Quality gate deadlock; phases cannot reach COMPLETE even with no regressions

**Fix**:
- Commit: `Part of autonomous_executor/phase_finalizer updates`
- Files:
  - `src/autopack/autonomous_executor.py`
  - `src/autopack/phase_finalizer.py`
- Changes: Thread human_approved into quality_report; PhaseFinalizer treats blocked-but-human-approved as warning (still blocks on critical regressions)

**Verification**: research-system-v17 phases completed with auto-approval override

**Persisted**: ❌ RESOLVED

---

### Phase 6: Diff Generation & Apply Guards (2025-12-27 10:30-12:30)

#### DIFF-001: governed_apply rejects patch: 'Unsafe patch: attempts to create existin…

**Symptom**: governed_apply rejects patch: 'Unsafe patch: attempts to create existing file as new'

**Root Cause**: Full-file diff generator emitted 'new file mode 100644' for existing files (old_content missing)

**Impact**: Apply blocked for valid patches

**Fix**:
- Commit: `Part of anthropic_clients updates`
- Files:
  - `src/autopack/anthropic_clients.py`
- Changes: If diff about to be emitted as 'new file mode' but path exists on disk, read existing content and emit modify diff

**Persisted**: ❌ RESOLVED

---
#### APPLY-002: governed_apply rejects valid modified files with 'unclosed quote' error

**Symptom**: governed_apply rejects valid modified files with 'unclosed quote' error

**Root Cause**: _detect_truncated_content() collected '+' lines from ALL diffs including modified files; diff hunks don't represent full file content

**Impact**: False positive truncation detection on ordinary modifications

**Fix**:
- Commit: `Part of governed_apply updates`
- Files:
  - `src/autopack/governed_apply.py`
- Changes: Only run unclosed-quote/YAML truncation heuristics for new files (--- /dev/null), not modifications

**Persisted**: ❌ RESOLVED

---
#### NDJSON-002: Builder failed: None (unhelpful error) when modify operation truncated

**Symptom**: Builder failed: None (unhelpful error) when modify operation truncated

**Root Cause**: NDJSON modify operations missing 'operations' list raised ValueError; phase fails with no useful diagnostic

**Impact**: Truncation scenarios produce confusing failures

**Fix**:
- Commit: `Part of ndjson_format updates`
- Files:
  - `src/autopack/ndjson_format.py`
  - `tests/test_ndjson_apply_truncation_tolerant.py`
- Changes: Introduce NDJSONSkipOperation; missing modify operations treated as skipped (non-fatal); result includes skipped list

**Persisted**: ❌ RESOLVED

---
#### NDJSON-003: NDJSON apply: replace_all with empty old_text causes partial apply fail…

**Symptom**: NDJSON apply: replace_all with empty old_text causes partial apply failures

**Root Cause**: Malformed replace_all ops (empty old_text from truncation) raised ValueError; entire apply failed

**Impact**: Partial NDJSON apply blocking convergence

**Fix**:
- Commit: `Part of ndjson_format updates`
- Files:
  - `src/autopack/ndjson_format.py`
- Changes: Treat replace_all with empty old_text as no-op with warning instead of raising exception

**Persisted**: ❌ RESOLVED

---

### Phase 7: Test Collection & Compatibility (2025-12-27 09:00-12:30)

#### PYTEST-001: pytest collection: 14 errors from import failures (SQLAlchemy table red…

**Symptom**: pytest collection: 14 errors from import failures (SQLAlchemy table redefinition, missing CLI commands, diagnostics APIs)

**Root Cause**: Multiple issues: (1) backend models imported via two paths creating duplicate SQLAlchemy Base, (2) tests expected autopack.cli.commands.* package layout, (3) missing compat exports for diagnostics

**Impact**: CI collection failures block all tests; phases fail quality gate

**Fix**:
- Commit: `Multiple commits for pytest collection fixes`
- Files:
  - `src/backend/models/user.py`
  - `src/autopack/cli/__init__.py`
  - `src/autopack/cli/commands/phases.py`
  - `src/autopack/diagnostics/scope_expander.py`
  - `src/autopack/diagnostics/deep_retrieval.py`
  - `src/autopack/diagnostics/diagnostics_agent.py`
  - `src/autopack/diagnostics/package_detector.py`
  - `src/autopack/diagnostics/evidence_requests.py`
  - `src/autopack/diagnostics/cursor_prompt_generator.py`
  - `tracer_bullet/gatherer.py`
  - `tracer_bullet/orchestrator.py`
- Changes: Consolidated SQLAlchemy imports; created CLI commands package; added diagnostics compat shims; created tracer_bullet test-facing package

**Verification**: pytest --collect-only reported 1102 tests collected (down from 14 errors)

**Persisted**: ❌ RESOLVED

---
#### RESEARCH-001: Research test collection failures: missing ResearchHookManager, Researc…

**Symptom**: Research test collection failures: missing ResearchHookManager, ResearchPhaseConfig, ReviewConfig

**Root Cause**: Tests expected legacy API surface that was refactored; new storage-oriented classes didn't match test expectations

**Impact**: CI collection failures; research-system-v12+ drains blocked

**Fix**:
- Commit: `Multiple commits for research compat`
- Files:
  - `src/autopack/autonomous/research_hooks.py`
  - `src/autopack/phases/research_phase.py`
  - `src/autopack/workflow/research_review.py`
  - `src/autopack/integrations/build_history_integrator.py`
  - `src/research/gatherers/github_gatherer.py`
  - `src/research/discovery/web_discovery.py`
  - `src/research/agents/intent_clarifier.py`
- Changes: Added compatibility shims: ResearchHookManager/Trigger/Result, ResearchPhaseConfig/Result, ReviewConfig/Result; restored lifecycle methods (start/complete/fail/cancel); fixed helper methods (pagination, URL check, scope precedence)

**Verification**: research-system-v17 completed 2 phases; newly failing tests reduced from 16 to 0

---
#### TEST-001: src/research/frameworks/market_attractiveness.py: NameError: List is no…

**Symptom**: src/research/frameworks/market_attractiveness.py: NameError: List is not defined

**Root Cause**: Missing 'List' import in type annotations

**Impact**: Collection error blocks research-meta-analysis

**Fix**:
- Commit: `Simple import addition`
- Files:
  - `src/research/frameworks/market_attractiveness.py`
- Changes: Added 'from typing import List'

**Persisted**: ❌ RESOLVED

---

### Phase 8: Production Drain Validation (2025-12-27 12:00-End)

#### REAL-001: suspicious_shrinkage guard blocks >60% deletions

**Symptom**: suspicious_shrinkage guard blocks >60% deletions

**Root Cause**: Intentional safety guard

**Impact**: Phases requiring mass deletions blocked unless allow_mass_deletion=true in spec

**Persisted**: ✅ BY DESIGN

---
#### REAL-002: MAX_ATTEMPTS_EXHAUSTED after 5 retry attempts

**Symptom**: MAX_ATTEMPTS_EXHAUSTED after 5 retry attempts

**Root Cause**: Real convergence failure; repeated truncation/patch failures exhausted retry budget

**Impact**: Phase failed legitimately

**Persisted**: ✅ BY DESIGN

---
#### REAL-003: Protected path modification requires manual approval

**Symptom**: Protected path modification requires manual approval

**Root Cause**: Governance rule: src/autopack/config.py modification blocked

**Impact**: Phase waits for human approval

**Persisted**: ✅ BY DESIGN

---

### Phase 9: CI Collection Error Correctness (pytest-json-report collectors) (2025-12-27 15:00-16:00)

#### FINALIZER-002: CI collection/import errors (pytest exitcode=2) were not treated as det…

**Symptom**: CI collection/import errors (pytest exitcode=2) were not treated as deterministic blockers; errors live under collectors[] while tests[] is empty

**Root Cause**: PhaseFinalizer/TestBaselineTracker read only tests[] and summary; pytest-json-report encodes collection failures as failed collectors entries

**Impact**: Systemic gate hole: phases could be incorrectly treated as complete / overridable despite ImportError during collection

**Fix**:
- Commit: `c0cf9867`
- Files:
  - `src/autopack/phase_finalizer.py`
  - `src/autopack/test_baseline_tracker.py`
  - `tests/test_phase_finalizer.py`
- Changes: Treat failed collectors[] as blocking even when baseline is missing; add regression test simulating exitcode=2 with tests=[]

**Verification**: Unit tests passed; regression test added for failed collectors blocking without baseline

**Led To**: SCOPE-003

**Persisted**: ❌ RESOLVED

---

### Phase 10: Windows Scope/Path Normalization (2025-12-27 15:30-17:00)

#### SCOPE-003: Chunked drains on Windows rejected in-scope patches as 'Outside scope'…

**Symptom**: Chunked drains on Windows rejected in-scope patches as 'Outside scope' due to backslashes/dot-slash variants in scope_paths

**Root Cause**: Scope enforcement compared unnormalized relative paths; scope paths could be '.\\src\\...' while patch paths are 'src/...' (POSIX-style)

**Impact**: Systemic PATCH_FAILED in multi-batch drains despite valid patches

**Fix**:
- Commit: `dad02414`
- Files:
  - `src/autopack/governed_apply.py`
  - `tests/test_governed_apply.py`
- Changes: Normalize scope and patch paths (trim, \\→/, strip ./, collapse slashes) before comparing; add regression test

**Verification**: Regression tests passed; Chunk2B scope issue reported unblocked

**Persisted**: ❌ RESOLVED

---

### Phase 11: Drain Harness Configuration (run_type + structured edits) (2025-12-27 18:30-19:30)

#### DRAIN-002: Autopack-internal drains dead-end with protected_path_violation even wh…

**Symptom**: Autopack-internal drains dead-end with protected_path_violation even when queued phase scope targets src/autopack/*

**Root Cause**: drain_queued_phases.py always instantiated AutonomousExecutor with run_type=project_build, forcing protected-path governance for internal maintenance phases

**Impact**: Systemic drain blocker; requires manual governance approval or cannot drain internal runs

**Fix**:
- Commit: `88f7c21c`
- Files:
  - `scripts/drain_queued_phases.py`
- Changes: Add --run-type (or AUTOPACK_RUN_TYPE) and pass through to AutonomousExecutor so internal phases can run as autopack_maintenance

**Verification**: Verified by re-running drain with --run-type autopack_maintenance and observing phase completion without protected_path dead-end

**Persisted**: ❌ RESOLVED

---
#### DELIV-002: Deliverables validation fails with 'Found in patch: 0 files' when Build…

**Symptom**: Deliverables validation fails with 'Found in patch: 0 files' when Builder returns structured edit plan (patch_content == '')

**Root Cause**: Deliverables validation only inspected patch_content and workspace; structured edit plans communicate touched files via edit_plan.operations not via unified diff

**Impact**: False deliverables gate failures; unnecessary retries / MAX_ATTEMPTS_EXHAUSTED risk

**Fix**:
- Commit: `4ca9545a`
- Files:
  - `src/autopack/deliverables_validator.py`
  - `src/autopack/autonomous_executor.py`
  - `tests/test_deliverables_validator.py`
- Changes: Thread edit_plan.operations[*].file_path as touched_paths into validate_deliverables; merge into actual_paths; add regression test

**Verification**: Unit tests passed; RCA doc updated with Blocker O

**Persisted**: ❌ RESOLVED

---

### Phase 12: Drain Harness Environment + API Autostart Observability (Windows) (2025-12-27 19:30-21:00)

#### DRAIN-003: Drain attempts fail with 'connection refused' to Postgres localhost:543…

**Symptom**: Drain attempts fail with 'connection refused' to Postgres localhost:5432 when DATABASE_URL unset

**Root Cause**: drain_queued_phases.py defaulted DATABASE_URL too late (after SessionLocal import); SessionLocal binds DB URL at import time

**Impact**: Operational drain failures; confusing infra errors; wasted cycles

**Fix**:
- Commit: `2ca3dd01, 505e1fa1`
- Files:
  - `scripts/drain_queued_phases.py`
- Changes: Default DATABASE_URL to sqlite:///autopack.db when autopack.db exists; move logic before importing autopack.database

**Verification**: Subsequent drain runs no longer attempted Postgres when DATABASE_URL was unset

**Persisted**: ❌ RESOLVED

---
#### API-003: Drain aborted with 'API server failed to start within 10 seconds' on Wi…

**Symptom**: Drain aborted with 'API server failed to start within 10 seconds' on Windows/cold starts

**Root Cause**: Hardcoded 10s timeout; uvicorn subprocess stdout/stderr discarded (no visibility); PYTHONPATH adjustments in parent did not propagate to subprocess

**Impact**: Systemic drain abort; no diagnostics to distinguish slow-start vs crash

**Fix**:
- Commit: `5d47afb0`
- Files:
  - `src/autopack/autonomous_executor.py`
- Changes: Configurable AUTOPACK_API_STARTUP_TIMEOUT_SECONDS (default 30s); pass PYTHONPATH=src; write startup logs to .autonomous_runs/<run_id>/diagnostics/api_server_<host>_<port>.log

**Verification**: With AUTOPACK_API_STARTUP_TIMEOUT_SECONDS=30, API started and drain progressed to a real CI collection/import gate

**Persisted**: ❌ RESOLVED

---
#### DRAIN-004: Drain triage costs high due to dual auditor calls for quick systemic di…

**Symptom**: Drain triage costs high due to dual auditor calls for quick systemic diagnosis

**Root Cause**: Drain script always used dual-auditor mode

**Impact**: Slow/expensive triage loops when chasing systemic blockers

**Fix**:
- Commit: `b3bca22f`
- Files:
  - `scripts/drain_queued_phases.py`
- Changes: Add --no-dual-auditor to reduce LLM calls during fast triage

**Persisted**: ❌ RESOLVED

---
