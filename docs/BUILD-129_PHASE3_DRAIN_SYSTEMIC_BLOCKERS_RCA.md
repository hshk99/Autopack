## BUILD-129 Phase 3: Drain Systemic Blockers RCA (2025-12-27)

This document records the **root cause analysis (RCA)** for the systemic blockers discovered during representative draining, plus the **fixes** and the **verification evidence** that the blockers are resolved.

### Blocker A: Drain reports queued>0, executor says “No more executable phases”

- **Symptom**: `scripts/drain_queued_phases.py` prints `queued>0`, but the executor prints **“No more executable phases, execution complete”**.
- **Impact**: Draining silently stalls; queue never converges even though there is work to do.
- **Root cause**:
  - `drain_queued_phases.py` uses **SQLite DB queries** to count queued phases.
  - `AutonomousExecutor` selects phases via the **Supervisor API** (BUILD-115).
  - If `AUTOPACK_API_URL` points at a different running service or a Supervisor API using a different `DATABASE_URL`, DB and API are looking at **different datasets**, producing contradictory “queued” vs “none executable” signals.
- **Fix**:
  - `scripts/drain_queued_phases.py`: when `AUTOPACK_API_URL` is not explicitly set, choose an **ephemeral free localhost port** and set `AUTOPACK_API_URL` to it so the executor auto-starts a fresh API instance for that drain session.
  - `src/autopack/main.py`: `/health` reports `service="autopack"` and includes DB health; executor refuses incompatible/non-JSON health responses (prevents wrong-service false positives).
- **Verification**:
  - Representative drain `fileorg-backend-fixes-v4-20251130` now shows:
    - a printed ephemeral API URL (`[drain] AUTOPACK_API_URL not set; using ephemeral ...`)
    - executor selecting a queued phase (`[BUILD-041] Next phase: ...`)
    - queued count decrementing on the next drain status line.

### Blocker B: API returns tiers=[], executor sees no queued phases even though DB has phases

- **Symptom**: `/runs/{run_id}` returns `tiers=[]`, and executor doesn’t see any queued phases.
- **Impact**: Same as Blocker A—drain stalls due to empty phase list from API.
- **Root cause**:
  - Some runs have **Phase rows** but no corresponding **Tier rows** populated (patch-scoped/legacy runs).
  - `RunResponse` did not include a top-level `phases` list; executor phase selection logic expects `run_data["phases"]` (flat structure) or nested tiers.
- **Fix**:
  - `src/autopack/schemas.py`: added `phases: List[PhaseResponse]` to `RunResponse` so the API always includes phases even when tiers are missing.
  - `PhaseResponse` includes `tier_id` and `run_id` so the executor has the fields it expects.
- **Verification**:
  - Direct API call to `/runs/{run_id}` now returns top-level `"phases": [...]` for tierless runs.
  - Executor selection proceeds using the flat structure path in `get_next_queued_phase()`.

### Blocker C: PhaseFinalizer crash (CI report_path was a text log, not JSON)

- **Symptom**: phase fails late with:
  - `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)`
  - stack trace pointing to `TestBaselineTracker.diff()` reading `ci_result["report_path"]`.
- **Impact**:
  - Systemic “can’t complete” failures after otherwise successful CI; drain cannot converge.
  - CI artifacts are not machine-readable for baseline delta computation.
- **Root cause**:
  - `_run_pytest_ci()` persisted a **text log** but stored it as `report_path`.
  - `TestBaselineTracker` assumes `report_path` points to a **pytest-json-report** JSON file.
- **Fix**:
  - `src/autopack/autonomous_executor.py`: pytest CI always emits:
    - `--json-report`
    - `--json-report-file=.autonomous_runs/<run_id>/ci/pytest_<phase_id>.json`
    - Returns JSON path as `report_path` and log as `log_path`.
  - `src/autopack/phase_finalizer.py`: wraps baseline delta computation in try/except so malformed or missing report files cannot crash phase execution (fail-safe).
  - Regression test: `tests/test_phase_finalizer.py::test_assess_completion_ci_report_not_json_does_not_crash`.
- **Verification**:
  - The regression test above passes locally.
  - In a real drain, CI now produces `.json` report artifacts under `.autonomous_runs/<run_id>/ci/`.

### Blocker D: “Blocked execute_fix” events not durably recorded

- **Symptom**: A blocked action (e.g., Doctor `execute_fix` of type `git` for `project_build`) may not appear in consolidated debug output.
- **Impact**: “Drastic actions” lack traceability; auditing and forensic review lose key evidence.
- **Root cause**:
  - `ArchiveConsolidator._append_to_issue()` only appended when an issue header already existed.
  - `log_fix_applied()` did not include run/phase/outcome fields, limiting traceability.
- **Fix**:
  - `src/autopack/archive_consolidator.py`:
    - auto-creates an issue entry when missing before appending a fix
    - includes `run_id`, `phase_id`, `outcome` in fix entries
- **Verification**:
  - Grep evidence confirms blocked execute_fix entries appear in:
    - `.autonomous_runs/file-organizer-app-v1/docs/CONSOLIDATED_DEBUG.md`
    - including `Run ID` and `Outcome=BLOCKED_GIT_EXECUTE_FIX`.

### Blocker E: PhaseFinalizer treated quality gate BLOCKED as a hard-fail even after human approval

- **Symptom**: Drain logs show `✅ Approval GRANTED (auto-approved)` but the phase still finalizes as `FAILED` solely because `quality_report.is_blocked=True`.
- **Impact**: Systemic convergence deadlock for any phase where QualityGate is conservative and requires human override; phases cannot reach `COMPLETE` even when CI delta indicates no new regressions.
- **Root cause**:
  - Executor computed `approval_granted` but did not pass it through to PhaseFinalizer.
  - PhaseFinalizer treated `quality_report.is_blocked` as always terminal, with no override semantics.
- **Fix**:
  - `src/autopack/autonomous_executor.py`: include `human_approved` in the `quality_report` dict sent to PhaseFinalizer.
  - `src/autopack/phase_finalizer.py`: allow completion when `quality_report.is_blocked=True` **and** `human_approved=True`, while still blocking on critical regressions and collection errors.
- **Verification**:
  - Real drains (`research-system-v17`, `research-system-v11`) now show:
    - `WARN: Quality gate blocked (BLOCKED) but human-approved override present`
    - `✅ Phase ... can complete`

### Blocker F: Full-file local diff generator emitted `new file mode` for existing files

- **Symptom**: `governed_apply` rejected patches with: `Unsafe patch: attempts to create existing file as new: <path>`.
- **Impact**: Phase fails before CI/gates for full-file mode outputs when the executor lacks `old_content` and incorrectly treats changes as file creation.
- **Root cause**:
  - Local diff generation used `is_new_file = not old_content and bool(new_content)` without checking whether the path already exists on disk.
- **Fix**:
  - `src/autopack/anthropic_clients.py`: if a diff is about to be emitted as “new file” but the path exists, read disk content and emit a modify diff instead.
- **Verification**:
  - Subsequent drains show warnings like: `Diff generation: <path> exists but old_content empty; treating as modify`, and the “unsafe new file mode” error no longer occurs.

### Blocker G: Executor POSTed invalid phase state `BLOCKED` to `/update_status` (400)

- **Symptom**: `Failed to update phase <id> status: 400 Client Error ... /update_status` in governance-blocked phases.
- **Impact**: Status updates become noisy/unreliable; phase summary and run summary writes become inconsistent.
- **Root cause**:
  - API accepts only `models.PhaseState` values; there is no `BLOCKED` PhaseState. `BLOCKED` is a QualityGate outcome, not a PhaseState.
  - Executor used `"BLOCKED"` as a status value during governance request creation.
- **Fix**:
  - `src/autopack/autonomous_executor.py`: map `"BLOCKED"` to `"FAILED"` when updating phase status via API.
- **Verification**:
  - Subsequent governance-blocked drains no longer log 400 errors from `/update_status`.

### Blocker H: research-system-v12 CI collection ImportErrors (legacy exports missing)

- **Symptom**: pytest collection fails with ImportErrors like:
  - `cannot import name 'ResearchHookManager' from autopack.autonomous.research_hooks`
  - `cannot import name 'ResearchPhaseConfig' from autopack.phases.research_phase`
  - `cannot import name 'ReviewConfig' from autopack.workflow.research_review`
  - plus legacy helper expectations in `BuildHistoryIntegrator` (e.g. `load_history()`).
- **Impact**: CI returns code 2; PhaseFinalizer treats as CI failure and phases cannot complete even when the underlying phase work is correct.
- **Root cause**: Newer APIs replaced older surfaces, but test suite / historical runs still import legacy names and call legacy helper methods.
- **Fix**:
  - `src/autopack/autonomous/research_hooks.py`: add legacy `ResearchHookManager`, `ResearchTrigger`, `ResearchHookResult`; extend `ResearchTriggerConfig` to accept legacy fields; add `ResearchHooks.should_research/pre_planning_hook/post_planning_hook`.
  - `src/autopack/phases/research_phase.py`: add `ResearchPhaseConfig`, `ResearchPhaseResult`, patchable `ResearchSession`, and executable `ResearchPhase` wrapper while preserving storage model as `ResearchPhaseRecord`.
  - `src/autopack/workflow/research_review.py`: add legacy `ReviewConfig`, `ReviewResult` and compat `ResearchReviewWorkflow` wrapper; retain store implementation as `ResearchReviewStore`.
  - `src/autopack/integrations/build_history_integrator.py`: add `load_history`, `analyze_patterns`, `get_research_recommendations` and adjust `should_trigger_research` signature for legacy call sites.
- **Verification**:
  - `python -m pytest -q tests/autopack/autonomous/test_research_hooks.py tests/autopack/integration/test_research_end_to_end.py tests/autopack/workflow/test_research_review.py --maxfail=1`
  - Result: `28 passed`.

### Blocker I: Legacy trigger ordering bug (`unknown_category` preempted `high_risk`)

- **Symptom**: `test_high_risk_trigger` failed because legacy `unknown_category` fired first when `category/known_categories` were absent.
- **Impact**: Research trigger behavior becomes inconsistent and masks real trigger conditions.
- **Root cause**: `unknown_category` condition treated missing values as “unknown”, matching too broadly.
- **Fix**: `unknown_category` trigger now only evaluates when both `category` and `known_categories` are present.
- **Verification**: `tests/autopack/autonomous/test_research_hooks.py` passes.

### Blocker J: Windows DB sync crash (UnicodeEncodeError in `scripts/tidy/db_sync.py`)

- **Symptom**: Running `python scripts/tidy/db_sync.py --project autopack` crashed with:
  - `UnicodeEncodeError: 'charmap' codec can't encode characters ...`
- **Impact**: SOT/DB synchronization cannot run reliably on Windows consoles unless users remember to set `PYTHONUTF8=1`.
- **Root cause**: `db_sync.py` printed non-ASCII emoji (e.g., `⚠️`, `✅`) to a console using a non-UTF8 code page.
- **Fix**: Replace emoji output with ASCII-safe `[OK]` / `[WARN]` messages and keep behavior unchanged.
- **Verification**:
  - `python scripts/tidy/db_sync.py --project autopack` completes successfully (Qdrant may still be unavailable and is handled as a warning).

### Blocker K: Patch apply fails with `patch fragment without header` for locally-generated multi-file diffs

- **Symptom**: `git apply --check` fails with errors like:
  - `patch fragment without header at line N: @@ ...`
- **Impact**: Phase fails at apply step even though the Builder output was full-file content and Autopack generated diffs locally.
- **Root cause**: Multi-file patch assembly was not strict about diff boundaries / trailing newline, which can cause `git apply` to misparse later hunks as “floating” fragments in some cases.
- **Fix**: `src/autopack/anthropic_clients.py` now joins locally-generated diffs with a blank line separator and guarantees the patch ends with a newline.
- **Verification**: Observed this failure mode during `research-system-v12` drain; fix prevents boundary-related parse errors for concatenated diffs.


