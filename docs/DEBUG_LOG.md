# Debug Log - Problem Solving History

<!-- META
Last_Updated: 2025-12-20T17:40:00Z
Total_Issues: 23
Format_Version: 2.0
Auto_Generated: True
Sources: CONSOLIDATED_DEBUG, archive/, fileorg-phase2-beta-release
-->

## INDEX (Chronological - Most Recent First)

| Timestamp | DBG-ID | Severity | Summary | Status |
|-----------|--------|----------|---------|--------|
| 2025-12-20 | DBG-055 | HIGH | Research-api-router phase blocked by protected-path isolation: patch attempts to modify `src/autopack/main.py` for FastAPI router registration, but main.py not in ALLOWED_PATHS (narrower than diagnostics subtrees in BUILD-090) | ✅ Resolved (Manual Hotfix: BUILD-096) |
| 2025-12-20 | DBG-054 | HIGH | Autonomous_executor.py had 3 duplicate copies of allowed_roots computation logic (lines 3474, 4300, 4678) with same bug as DBG-053; manifest gate rejected examples/ deliverables despite deliverables_validator.py being fixed in BUILD-094 | ✅ Resolved (Manual Hotfix: BUILD-095) |
| 2025-12-20 | DBG-053 | HIGH | Deliverables validator incorrectly computed allowed_roots for file deliverables like `examples/market_research_example.md`, creating root `examples/market_research_example.md/` instead of `examples/`, causing false "outside allowed roots" failures for research-examples-and-docs phase | ✅ Resolved (Manual Hotfix: BUILD-094) |
| 2025-12-20 | DBG-052 | MEDIUM | After fixing ImportError (DBG-051), phases 2-3 could not retry because `retry_attempt` counter was at 5/5 (MAX_RETRY_ATTEMPTS); reset counter to 0 to enable successful retry | ✅ Resolved (Manual DB Reset: BUILD-093) |
| 2025-12-20 | DBG-051 | HIGH | LLM clients (OpenAI, Gemini, GLM) attempt to import missing `format_rules_for_prompt` and `format_hints_for_prompt` functions from learned_rules.py, causing ImportError and blocking Builder execution in all follow-up phases | ✅ Resolved (Manual Hotfix: BUILD-092) |
| 2025-12-20 | DBG-050 | HIGH | Follow-up requirements YAML files contain invalid syntax: backtick-prefixed strings in feature lists cause YAML parser failures during run seeding, blocking `autopack-followups-v1` creation | ✅ Resolved (Manual Hotfix: BUILD-091) |
| 2025-12-20 | DBG-049 | HIGH | Followups 1–3 (Diagnostics Parity) blocked by protected-path isolation because deliverables live under `src/autopack/diagnostics/` and `src/autopack/dashboard/` which were not allowlisted | ✅ Resolved (Manual Hotfix: BUILD-090) |
| 2025-12-20 | DBG-048 | MEDIUM | Chunk 2B quality gate not met: missing `src/autopack/research/*` deliverables and insufficient unit test/coverage confirmation; implement modules + expand tests and verify ≥25 tests + ≥80% coverage | ✅ Resolved (Manual Quality Fix: BUILD-089) |
| 2025-12-19 | DBG-047 | HIGH | Executor could incorrectly flip a resumable run to DONE_FAILED during best-effort run_summary writes after a single phase failure (retries still remaining) | ✅ Resolved (Manual Hotfix: BUILD-088) |
| 2025-12-19 | DBG-046 | MEDIUM | Research requirements root mismatch + missing deps caused predictable churn; unify requirements to `src/autopack/research/*` and add preflight analyzer to catch blockers before execution | ✅ Resolved (Manual Tooling: BUILD-087) |
| 2025-12-19 | DBG-045 | LOW | Runbook/capability report became stale after stabilization fixes; update docs and add explicit next-cursor takeover prompt to prevent protocol drift | ✅ Resolved (Manual Docs: BUILD-086) |
| 2025-12-19 | DBG-044 | HIGH | Chunk 5 manifests may contain directory prefixes (ending in `/`); strict manifest enforcement treated created files under those prefixes as outside-manifest | ✅ Resolved (Manual Hotfixes: BUILD-085) |
| 2025-12-19 | DBG-043 | HIGH | Chunk 5 uses directory deliverables (e.g., `tests/research/unit/`), but deliverables validator treated them as literal files causing deterministic failures | ✅ Resolved (Manual Hotfixes: BUILD-084) |
| 2025-12-19 | DBG-042 | HIGH | Chunk 4 (`research-integration`) patches blocked by protected-path isolation because required deliverables are under `src/autopack/*` and safe subtrees weren’t allowlisted | ✅ Resolved (Manual Hotfixes: BUILD-083) |
| 2025-12-19 | DBG-041 | HIGH | Requirements include annotated deliverable strings (e.g., `path (10+ tests)`), causing deterministic deliverables/manifest failures and exhausting retries for Chunk 4/5 | ✅ Resolved (Manual Hotfixes: BUILD-082) |
| 2025-12-19 | DBG-040 | HIGH | Chunk 2B (`research-gatherers-web-compilation`) frequently fails patch apply due to truncated/unclosed-quote patches and occasional header-only new-file doc diffs when generating many deliverables at once | ✅ Resolved (Manual Hotfixes: BUILD-081) |
| 2025-12-19 | DBG-039 | HIGH | Chunk 1A patches rejected because deliverables include `src/autopack/cli/commands/research.py` but `src/autopack/` is protected in project runs; allowlist/roots derivation over-expanded or blocked CLI | ✅ Resolved (Manual Hotfixes: BUILD-080) |
| 2025-12-19 | DBG-038 | MEDIUM | Backend auditor_result endpoint still validated as BuilderResultRequest (missing `success`); executor POSTs fail with 422 causing noisy telemetry | ✅ Resolved (Manual Hotfixes: BUILD-079) |
| 2025-12-19 | DBG-037 | HIGH | Chunk 0 patch output frequently truncated or emitted header-only new-file diffs (no ---/+++ or @@ hunks), causing git apply failures and direct-write fallback writing 0 files | ✅ Resolved (Manual Hotfixes: BUILD-078) |
| 2025-12-19 | DBG-036 | MEDIUM | JSON auto-repair inserted +[] without a hunk header for new files; git apply ignored it leading to continued JSON corruption | ✅ Resolved (Manual Hotfixes: BUILD-077) |
| 2025-12-19 | DBG-035 | MEDIUM | Diff extractor too strict on hunk headers (requires ,count); valid @@ -1 +1 @@ was treated malformed causing hunks to be dropped and patches to fail apply | ✅ Resolved (Manual Hotfixes: BUILD-076) |
| 2025-12-19 | DBG-034 | MEDIUM | Chunk 0 repeatedly blocked by empty gold_set.json; implement safe auto-repair to minimal valid JSON [] before apply | ✅ Resolved (Manual Hotfixes: BUILD-075) |
| 2025-12-19 | DBG-033 | MEDIUM | Chunk 0 gold_set.json frequently empty; harden deliverables contract + feedback to require non-empty valid JSON (allow []) | ✅ Resolved (Manual Hotfixes: BUILD-074) |
| 2025-12-19 | DBG-030 | MEDIUM | Allowed-roots allowlist too narrow causes false manifest-gate failures when deliverables span multiple subtrees | ✅ Resolved (Manual Hotfixes: BUILD-071) |
| 2025-12-19 | DBG-031 | MEDIUM | Backend rejects auditor_result payload with 422 due to schema mismatch | ✅ Resolved (Manual Hotfixes: BUILD-072) |
| 2025-12-19 | DBG-032 | LOW | Memory summary warning: ci_success undefined when writing phase summary to memory | ✅ Resolved (Manual Hotfixes: BUILD-073) |
| 2025-12-19 | DBG-029 | HIGH | Post-apply corruption from invalid JSON deliverable (gold_set.json); add pre-apply JSON deliverable validation to fail fast | ✅ Resolved (Manual Hotfixes: BUILD-070) |
| 2025-12-19 | DBG-028 | HIGH | Patch apply blocked by default `src/autopack/` protection; explicitly allow `src/autopack/research/` for research deliverables | ✅ Resolved (Manual Hotfixes: BUILD-069) |
| 2025-12-19 | DBG-027 | HIGH | GovernedApply default protection blocks research writes; need derived allowed_paths from deliverables when scope.paths absent | ✅ Resolved (Manual Hotfixes: BUILD-068) |
| 2025-12-19 | DBG-026 | HIGH | Patch apply blocked by overly-broad protected_paths (`src/autopack/` protected) preventing research deliverables from being written | ✅ Resolved (Manual Hotfixes: BUILD-067) |
| 2025-12-19 | DBG-025 | MEDIUM | Manifest gate passes but Builder still diverges; enforce manifest inside Builder prompt + validator (OUTSIDE-MANIFEST hard fail) | ✅ Resolved (Manual Hotfixes: BUILD-066) |
| 2025-12-19 | DBG-024 | MEDIUM | Deliverables keep failing despite feedback; add manifest gate to force exact file-path commitment before patch generation | ✅ Resolved (Manual Hotfixes: BUILD-065) |
| 2025-12-19 | DBG-023 | MEDIUM | Deliverables enforcement too permissive: near-miss outputs outside required roots (e.g. src/autopack/tracer_bullet.py) | ✅ Resolved (Manual Hotfixes: BUILD-064) |
| 2025-12-19 | DBG-022 | HIGH | Provider fallback chain broken: OpenAI builder signature mismatch + OpenAI base_url/auth confusion; replanning hard-depends on Anthropic | ✅ Resolved (Manual Hotfixes: BUILD-063) |
| 2025-12-19 | DBG-021 | HIGH | Anthropic “credit balance too low” causes repeated failures; Doctor also hard-defaults to Claude | ✅ Resolved (Manual Hotfixes: BUILD-062) |
| 2025-12-19 | DBG-020 | HIGH | Executor incorrectly finalizes run as DONE_* after stopping due to max-iterations (run should remain resumable) | ✅ Resolved (Manual Hotfixes: BUILD-061) |
| 2025-12-19 | DBG-019 | MEDIUM | Anthropic streaming can drop mid-response (incomplete chunked read) causing false phase failures | ✅ Resolved (Manual Hotfixes: BUILD-060) |
| 2025-12-19 | DBG-018 | MEDIUM | Deliverables validator misplacement detection too weak for wrong-root patches (tracer_bullet/) | ✅ Resolved (Manual Hotfixes: BUILD-059) |
| 2025-12-19 | DBG-017 | MEDIUM | Qdrant unreachable on localhost:6333 (no docker + compose missing qdrant) | ✅ Resolved (Manual Hotfixes: BUILD-058) |
| 2025-12-19 | DBG-016 | LOW | Research runs: noisy Qdrant-fallback + missing consolidated journal logs; deliverables forbidden patterns not surfacing | ✅ Resolved (Manual Hotfixes: BUILD-057) |
| 2025-12-19 | DBG-015 | LOW | Qdrant recovery re-ingest is manual/on-demand (not automatic) to avoid surprise indexing overhead | ✅ Documented (BUILD-056) |
| 2025-12-19 | DBG-013 | MEDIUM | Qdrant not running caused memory disable; tier_id int/string mismatch; consolidated docs dropped events | ✅ Resolved (Manual Hotfixes: BUILD-055) |
| 2025-12-19 | DBG-012 | MEDIUM | Windows executor startup noise + failures (lock PermissionError, missing /health, Unix-only diagnostics cmds) | ✅ Resolved (Manual Hotfixes: BUILD-054) |
| 2025-12-19 | DBG-011 | MEDIUM | Backend API missing executor phase status route (`/update_status`) caused 404 spam | ✅ Resolved (Manual Hotfixes: BUILD-053) |
| 2025-12-19 | DBG-010 | HIGH | Research System Chunk 0 Stuck: Skip-Loop Abort + Doctor Interference | ✅ Resolved (Manual Hotfixes: BUILD-051) |
| 2025-12-17 | DBG-009 | HIGH | Multiple Executor Instances Causing Token Waste | ✅ Resolved (BUILD-048-T1) |
| 2025-12-17 | DBG-008 | MEDIUM | API Contract Mismatch - Builder Result Submission | ✅ Resolved (Payload Fix) |
| 2025-12-17 | DBG-007 | MEDIUM | BUILD-042 Token Limits Need Dynamic Escalation | ✅ Resolved (BUILD-046) |
| 2025-12-17 | DBG-006 | MEDIUM | CI Test Failures Due to Classification Threshold Calibration | ✅ Resolved (BUILD-047) |
| 2025-12-17 | DBG-005 | HIGH | Advanced Search Phase: max_tokens Truncation | ✅ Resolved (BUILD-042) |
| 2025-12-17 | DBG-004 | HIGH | BUILD-042 Token Scaling Not Active in Running Executor | ✅ Resolved (Module Cache) |
| 2025-12-17 | DBG-003 | CRITICAL | Executor Infinite Failure Loop | ✅ Resolved (BUILD-041) |
| 2025-12-13 | DBG-001 | MEDIUM | Post-Tidy Verification Report | ✅ Resolved |
| 2025-12-11 | DBG-002 | CRITICAL | Workspace Organization Issues - Root Cause Analysis | ✅ Resolved |

## DEBUG ENTRIES (Reverse Chronological)

### DBG-049 | 2025-12-20T05:18 | Followups 1–3 (Diagnostics Parity) blocked by protected-path isolation because deliverables live under `src/autopack/diagnostics/` and `src/autopack/dashboard/` which were not allowlisted
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfix: BUILD-090)

**Symptoms**:
- Diagnostics Parity follow-up phases cannot apply their deliverables despite correct patches because `src/autopack/` is protected by default.

**Fix**:
- Add narrow allowlist entries for:
  - `src/autopack/diagnostics/`
  - `src/autopack/dashboard/`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-090)

### DBG-048 | 2025-12-20T04:37 | Chunk 2B quality gate not met: missing `src/autopack/research/*` deliverables and insufficient unit test/coverage confirmation; implement modules + expand tests and verify ≥25 tests + ≥80% coverage
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Quality Fix: BUILD-089)

**Symptoms**:
- Chunk 2B tests failed during collection due to import-path mismatch and missing deliverables under `src/autopack/research/`.
- After basic fixes, the phase still lacked explicit confirmation of the quality targets (`≥25` unit tests and `≥80%` coverage for new modules).

**Fix**:
- Implement missing deliverable modules for Chunk 2B under `src/autopack/research/` and align tests to import `autopack.research.*`.
- Expand unit tests to cover key behaviors (robots disallow, content-type filtering, link/code extraction, deduplication, gap detection).
- Run tests + coverage to produce explicit confirmation.

**Evidence**:
- Unit tests: **39 passed**
- Coverage (target modules): **93% total**, each module ≥89%

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-089)

### DBG-047 | 2025-12-19T14:30 | Executor could incorrectly flip a resumable run to DONE_FAILED during best-effort run_summary writes after a single phase failure (retries still remaining)
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfix: BUILD-088)
**Context**: Research system convergence / executor run state correctness.

**Symptoms**:
- During `research-system-v29`, the first phase (`research-tracer-bullet`) hit a transient `PATCH_FAILED` on attempt 1 (expected to be retried).
- The executor’s “best-effort run_summary writer” mutated `runs.state` to `DONE_FAILED_REQUIRES_HUMAN_REVIEW` even though retries remained and phases were still QUEUED/resumable.
- This can deterministically prevent convergence by finalizing a run prematurely.

**Root Cause**:
- `_best_effort_write_run_summary()` attempted to “derive a terminal state” from non-COMPLETE phases.
- The helper is invoked opportunistically (e.g., after phase state updates) and must not finalize runs unless the main loop is truly finished.

**Fix**:
- Add an explicit guard (`allow_run_state_mutation=False` default) so `_best_effort_write_run_summary()` does not mutate `Run.state` during non-terminal updates.
- Only allow run state mutation when the main loop has truly reached `no_more_executable_phases`.

**Files Modified**:
- `src/autopack/autonomous_executor.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-088)

### DBG-046 | 2025-12-19T00:00 | Research requirements root mismatch + missing deps caused predictable churn; unify requirements to `src/autopack/research/*` and add preflight analyzer to catch blockers before execution
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Tooling: BUILD-087)
**Context**: Research system execution planning + phase deliverables convergence.

**Symptoms**:
- Chunk requirement YAMLs mixed deliverable roots (`src/research/*` vs `src/autopack/research/*`), increasing the chance of:
  - duplicate parallel implementations,
  - import-path confusion,
  - deliverables/manifest mismatch churn.
- Several chunk YAMLs referenced external libraries (e.g. `requests`, `beautifulsoup4`, `praw`, etc.) that were not consistently declared in dependency files, making CI/test failures and runtime import errors likely even when deliverables were generated correctly.

**Fix**:
- Normalize research chunk deliverables to a single root: `src/autopack/research/*` (update Chunk 1B/2A/2B/3 requirement YAMLs).
- Add missing research runtime/test dependencies to dependency declarations (`requirements.txt`, `requirements-dev.txt`, `pyproject.toml`).
- Add a lightweight preflight tool to flag:
  - deliverables-root mismatches,
  - governed-apply protected-path feasibility,
  - missing deps (including dev deps),
  - missing external API credential env vars (informational).

**Files Modified**:
- `.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk1b-foundation-intent-discovery.yaml`
- `.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk2a-gatherers-social.yaml`
- `.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk2b-gatherers-web-compilation.yaml`
- `.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk3-meta-analysis.yaml`
- `requirements.txt`
- `requirements-dev.txt`
- `pyproject.toml`
- `src/autopack/research/preflight_analyzer.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-087)

### DBG-045 | 2025-12-19T13:04 | Runbook/capability report became stale after stabilization fixes; update docs and add explicit next-cursor takeover prompt to prevent protocol drift
**Severity**: LOW
**Status**: ✅ Resolved (Manual Docs: BUILD-086)

**Symptoms**:
- Primary runbook and capability-gap report referenced outdated port/commands and outdated “chunk completion” status, increasing the chance of operator error and protocol drift.

**Fix**:
- Update `PROMPT_FOR_OTHER_CURSOR_FILEORG.md` to prefer backend 8001 and reflect current stabilization posture.
- Update `docs/RESEARCH_SYSTEM_CAPABILITY_GAP_ANALYSIS.md` to reflect post-stabilization reality (Chunk 2B/4/5 convergence blockers resolved).
- Add `docs/NEXT_CURSOR_TAKEOVER_PROMPT.md` as a durable handoff artifact.

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-086)

### DBG-044 | 2025-12-19T12:57 | Chunk 5 manifests may contain directory prefixes (ending in `/`); strict manifest enforcement treated created files under those prefixes as outside-manifest
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-085)
**Context**: Chunk 5 (research-testing-polish), manifest enforcement + directory deliverables.

**Symptoms**:
- Builder creates valid files under `tests/research/unit/` or similar prefixes.
- Deliverables manifest may include a directory entry (e.g., `tests/research/unit/`) as an approval boundary.
- Validator incorrectly flags created files as outside the manifest because it only accepted exact path matches.

**Root Cause**:
- Manifest enforcement treated the manifest as an exact set of file paths.
- For phases whose deliverables are directory prefixes, manifest entries can reasonably be prefixes too.

**Fix**:
- Extend manifest enforcement to support prefix entries:
  - Any manifest entry ending with `/` is treated as a prefix; files under that prefix are allowed.

**Files Modified**:
- `src/autopack/deliverables_validator.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-085)

### DBG-043 | 2025-12-19T12:54 | Chunk 5 uses directory deliverables (e.g., `tests/research/unit/`), but deliverables validator treated them as literal files causing deterministic failures
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-084)
**Context**: `research-system-v27` (Chunk 5: research-testing-polish)

**Symptoms**:
- Chunk 5 repeatedly fails deliverables validation even when it creates many test files, because some deliverables are specified as directories rather than literal file paths.

**Root Cause**:
- Unified diffs enumerate file paths, not empty directories.
- The deliverables validator previously required exact path matches, so directory-style deliverables (ending with `/`) could never be “found in patch”.

**Fix**:
- Treat expected deliverables ending with `/` as a prefix requirement:
  - Consider satisfied if at least one file in the patch starts with that prefix.
- Keep exact-file deliverables strict.

**Files Modified**:
- `src/autopack/deliverables_validator.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-084)

### DBG-042 | 2025-12-19T12:50 | Chunk 4 (`research-integration`) patches blocked by protected-path isolation because required deliverables are under `src/autopack/*` and safe subtrees weren’t allowlisted
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-083)
**Context**: `research-system-v27` (Chunk 4)

**Symptoms**:
- Builder produced correct deliverable paths for Chunk 4 and deliverables validation passed.
- Patch apply failed in `GovernedApplyPath` isolation with errors like:
  - `Patch rejected - protected path violations: src/autopack/integrations/...`
  - `src/autopack/phases/...`
  - `src/autopack/autonomous/...`
  - `src/autopack/workflow/...`

**Root Cause**:
- `src/autopack/` is protected in project runs by design.
- The safe subtrees required for the research integration phase were not explicitly allowlisted, so governed apply correctly blocked them.

**Fix**:
- Add narrow safe allowlist entries for the required Chunk 4 subtrees:
  - `src/autopack/integrations/`
  - `src/autopack/phases/`
  - `src/autopack/autonomous/`
  - `src/autopack/workflow/`

**Files Modified**:
- `src/autopack/governed_apply.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-083)

### DBG-041 | 2025-12-19T12:43 | Requirements include annotated deliverable strings (e.g., `path (10+ tests)`), causing deterministic deliverables/manifest failures and exhausting retries for Chunk 4/5
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-082)
**Context**: `research-system-v26` (Chunk 4/5), deliverables parsing + manifest gating.

**Symptoms**:
- Chunk 4/5 phases repeatedly fail deliverables/manifest validation even when the Builder generates correct files.
- Retry attempts can be exhausted rapidly because the system treats annotated deliverable strings as literal file paths.

**Root Cause**:
- Requirements YAMLs sometimes embed human notes inside deliverables strings, e.g.:
  - `tests/autopack/integration/test_research_end_to_end.py (10+ integration tests)`
  - `tests/research/unit/ (100+ unit tests across all modules)`
- The executor/validator previously treated these as literal paths, which cannot be created verbatim.

**Fix**:
- Sanitize deliverable strings during scope extraction:
  - Strip trailing parenthetical annotations (`path (comment...)` → `path`)
  - Preserve directory prefixes (e.g. `tests/research/unit/`)
  - Drop empty entries after sanitization

**Files Modified**:
- `src/autopack/deliverables_validator.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-082)

### DBG-040 | 2025-12-19T12:23 | Chunk 2B (`research-gatherers-web-compilation`) frequently fails patch apply due to truncated/unclosed-quote patches and occasional header-only new-file doc diffs when generating many deliverables at once
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-081)
**Context**: `research-system-v24` (Chunk 2B)

**Symptoms**:
- Patch apply fails in governed apply validation with truncation indicators, e.g.:
  - `Patch validation failed - LLM generated incomplete/truncated patch: ... ends with unclosed quote: '\"\"\"'`
- Affected deliverables frequently include new test files under:
  - `tests/research/agents/*`
  - `tests/research/gatherers/*`
- Patch output may also include header-only new-file diffs for docs (e.g. `index ... e69de29` with no hunks/content), which is structurally incomplete and destabilizes apply.

**Root Cause**:
- Chunk 2B attempts to generate many deliverables in one Builder response (code + tests + docs).
- Large patch sizes increase the probability of LLM output truncation and malformed diff structure (especially for new files with long triple-quoted strings in tests/docs).

**Fix**:
- Implement **in-phase batching** for `research-gatherers-web-compilation` in the executor, mirroring the proven Chunk 0 batching protocol:
  - Split deliverables into prefix-based batches (gatherers, agents, tests, docs).
  - For each batch: manifest gate → Builder → deliverables validation → new-file diff structural validation → governed apply with scope enforcement.
  - Run CI/Auditor/Quality Gate once at the end using the combined diff.

**Files Modified**:
- `src/autopack/autonomous_executor.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-081)

### DBG-039 | 2025-12-19T16:15 | Chunk 1A patches rejected because deliverables include `src/autopack/cli/commands/research.py` but `src/autopack/` is protected in project runs; allowlist/roots derivation over-expanded or blocked CLI
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-080)

**Symptoms**:
- `research-foundation-orchestrator` fails patch apply with protected-path violation:
  - `Protected path: src/autopack/cli/commands/research.py`

**Root Cause**:
- Chunk 1A requires CLI deliverables under `src/autopack/cli/*`, but `GovernedApplyPath` protects `src/autopack/` in project runs.
- The system’s “preferred roots” allowlist for research phases did not include `src/autopack/cli/`, so:
  - GovernedApply blocked legitimate deliverables, or
  - allow-roots derivation expanded too broadly (e.g., to `src/autopack/`) which is undesirable.

**Fix**:
- Explicitly allow the safe subtree `src/autopack/cli/` for research phases:
  - Add to deliverables contract + manifest-gate preferred roots.
  - Add to deliverables validator preferred roots.
  - Add to GovernedApplyPath.ALLOWED_PATHS as an override to `src/autopack/` protection.

**Files Modified**:
- `src/autopack/autonomous_executor.py`
- `src/autopack/deliverables_validator.py`
- `src/autopack/governed_apply.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-080)

### DBG-038 | 2025-12-19T15:55 | Backend auditor_result endpoint still validated as BuilderResultRequest (missing `success`); executor POSTs fail with 422 causing noisy telemetry
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-079)

**Symptoms**:
- Executor logs show:
  - `Failed to post auditor result: 422 Client Error: Unprocessable Entity`
- Reproduced directly:
  - backend returns `Field required: body.success` when posting a valid auditor_result payload.

**Root Cause**:
- Some running backend instances still validate `POST /runs/{run_id}/phases/{phase_id}/auditor_result` using the older `BuilderResultRequest` schema, which requires a `success` field and rejects the executor’s auditor payload.

**Fix**:
- Add backwards-compatible retry in executor `_post_auditor_result(...)`:
  - If the first POST returns 422 with missing `success`, retry using a `BuilderResultRequest` wrapper and embed the full auditor payload in `metadata`.

**Files Modified**:
- `src/autopack/autonomous_executor.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-079)

### DBG-037 | 2025-12-19T15:10 | Chunk 0 patch output frequently truncated or emitted header-only new-file diffs (no ---/+++ or @@ hunks), causing git apply failures and direct-write fallback writing 0 files
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-078)

**Symptoms**:
- Chunk 0 (`research-tracer-bullet`) intermittently fails with:
  - `Patch validation failed - LLM generated incomplete/truncated patch: ... ends with unclosed quote: '\"\"\"'`
  - `git diff header lacks filename information when removing 1 leading pathname component`
  - `Direct file write failed or incomplete (expected N, wrote 0/1)`

**Root Cause**:
- Builder sometimes emits:
  - Oversized patches that truncate mid-file when generating all 11 deliverables at once.
  - Malformed new-file diffs with only headers (missing `---/+++` and/or missing `@@` hunks), which `git apply` cannot parse and the direct-write fallback cannot reconstruct.

**Fix**:
- Batch Chunk 0 within the same phase: run Builder→deliverables validation→patch apply in smaller deliverable batches (code/evaluation/tests/docs), then run CI/Auditor/Quality Gate once at the end.
- Add structural validation for required new-file diffs to reject header-only/no-hunk outputs and force Builder to regenerate.
- Harden governed patch sanitization to insert missing `---/+++` headers for new-file diffs even when `index e69de29` is absent.

**Files Modified**:
- `src/autopack/autonomous_executor.py`
- `src/autopack/deliverables_validator.py`
- `src/autopack/governed_apply.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-078)

### DBG-036 | 2025-12-19T14:20 | JSON auto-repair inserted +[] without a hunk header for new files; git apply ignored it leading to continued JSON corruption
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-077)

**Symptoms**:
- Auto-repair logged as applied, but post-apply integrity still reported `gold_set.json` invalid/empty.

**Root Cause**:
- Unified diff requires additions to occur inside a `@@` hunk. Injecting `+[]` into a new-file block with no hunks is not reliably applied.

**Fix**:
- When repairing a new-file diff with no hunks, inject a minimal hunk header and then `+[]`.

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-077)

### DBG-035 | 2025-12-19T14:15 | Diff extractor too strict on hunk headers (requires ,count); valid @@ -1 +1 @@ was treated malformed causing hunks to be dropped and patches to fail apply
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-076)

**Symptoms**:
- Logs show warnings like `Skipping malformed hunk header: @@ -0,0 +1 @@`
- Followed by apply failures and/or incomplete diffs.

**Root Cause**:
- Diff parsing required explicit counts (`,count`) but unified diff allows omitting counts when equal to 1.

**Fix**:
- Accept optional counts across diff extractors and governed apply validation.

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-076)

### DBG-034 | 2025-12-19T14:05 | Chunk 0 repeatedly blocked by empty gold_set.json; implement safe auto-repair to minimal valid JSON [] before apply
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-075)

**Symptoms**:
- Chunk 0 repeatedly produced an empty `src/autopack/research/evaluation/gold_set.json`.
- Pre-apply JSON validation rejected the patch each time, exhausting retries.

**Root Cause**:
- The Builder can still emit empty placeholders for JSON deliverables even with stronger prompt contracts.

**Fix**:
- Auto-repair required JSON deliverables that are empty/invalid in the patch by rewriting them to `[]` and re-validating before apply.

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-075)

### DBG-033 | 2025-12-19T13:55 | Chunk 0 gold_set.json frequently empty; harden deliverables contract + feedback to require non-empty valid JSON (allow [])
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-074)

**Symptoms**:
- Chunk 0 patches create the correct paths, but `src/autopack/research/evaluation/gold_set.json` is blank.

**Root Cause**:
- Builder sometimes emits empty placeholders for JSON deliverables unless explicitly constrained.

**Fix**:
- Tighten deliverables contract to require `gold_set.json` be non-empty valid JSON (minimal acceptable: `[]`).
- Add explicit JSON deliverable guidance to Builder feedback when JSON deliverables are invalid/empty.

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-074)

### DBG-032 | 2025-12-19T13:50 | Memory summary warning: ci_success undefined when writing phase summary to memory
**Severity**: LOW
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-073)

**Fix**:
- Compute `ci_success` from CI dict `passed` field before writing to memory.

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-073)

### DBG-031 | 2025-12-19T13:50 | Backend rejects auditor_result payload with 422 due to schema mismatch
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-072)

**Symptoms**:
- `POST /runs/{run_id}/phases/{phase_id}/auditor_result` returns `422 Unprocessable Entity`.

**Root Cause**:
- Backend endpoint accepted `BuilderResultRequest` but executor posts a richer auditor payload.

**Fix**:
- Add `AuditorResultRequest` schema and use it for the endpoint.

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-072)

### DBG-030 | 2025-12-19T13:49 | Allowed-roots allowlist too narrow causes false manifest-gate failures when deliverables span multiple subtrees
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-071)

**Symptoms**:
- Manifest gate fails with “outside allowed roots” even when the path is a required deliverable (e.g. `src/autopack/cli/...`).

**Root Cause**:
- Allowed roots were derived only from preferred research roots when any were present, without ensuring coverage of *all* deliverables.

**Fix**:
- Expand allowed roots to cover all deliverables when needed (first-two-segment prefixes).

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-071)

### DBG-029 | 2025-12-19T13:40 | Post-apply corruption from invalid JSON deliverable (gold_set.json); add pre-apply JSON deliverable validation to fail fast
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-070)
**Context**: `research-system-v14` Chunk 0.

**Symptoms**:
- Patch apply succeeded, but integrity validation detected corrupted JSON:
  - `CORRUPTED: src/autopack/research/evaluation/gold_set.json - Invalid JSON: Expecting value: line 1 column 1`
- The system restored the corrupted file and marked the attempt as `PATCH_FAILED` (burning an attempt).

**Root Cause**:
- JSON deliverable content can be empty/invalid even when paths are correct; validation happened only after applying the patch.

**Fixes Applied (manual)**:
- Add a pre-apply validator for NEW `.json` deliverables that parses the file content from the patch and rejects empty/invalid JSON before apply.

**Files Modified**:
- `src/autopack/deliverables_validator.py`
- `src/autopack/autonomous_executor.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-070)

### DBG-028 | 2025-12-19T13:35 | Patch apply blocked by default `src/autopack/` protection; explicitly allow `src/autopack/research/` for research deliverables
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-069)
**Context**: Research Chunk 0 deliverables live under `src/autopack/research/*` but patch apply can be blocked by default isolation.

**Symptoms**:
- Patch apply rejected as “Protected path: src/autopack/research/…” even when deliverables validation passes.

**Root Cause**:
- `GovernedApplyPath` protects `src/autopack/` by default for project runs.
- Research deliverables are a sanctioned sub-tree that must be writable.

**Fixes Applied (manual)**:
- Add `src/autopack/research/` to `GovernedApplyPath.ALLOWED_PATHS` so it overrides the default protection.

**Files Modified**:
- `src/autopack/governed_apply.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-069)

### DBG-027 | 2025-12-19T13:30 | GovernedApply default protection blocks research writes; need derived allowed_paths from deliverables when scope.paths absent
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-068)
**Context**: `research-system-v13` Chunk 0 can produce correct deliverables, but patch apply fails under `src/autopack/research/*`.

**Symptoms**:
- Patch apply rejected with protected-path violations under `src/autopack/research/*` even though those paths are required deliverables.

**Root Cause**:
- `GovernedApplyPath` protects `src/autopack/` for project runs by default.
- Chunk YAML scopes don’t provide `scope.paths`, so the executor passed `allowed_paths=[]` into `GovernedApplyPath`.

**Fixes Applied (manual)**:
- If `allowed_paths` is empty but deliverables exist, derive allowed roots from deliverables and pass them as `allowed_paths` to `GovernedApplyPath` so applying those deliverable files is permitted.

**Files Modified**:
- `src/autopack/autonomous_executor.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-068)

### DBG-026 | 2025-12-19T13:25 | Patch apply blocked by overly-broad protected_paths (`src/autopack/` protected) preventing research deliverables from being written
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-067)
**Context**: `research-system-v13` Chunk 0 reached the patch-apply step after passing deliverables validation.

**Symptoms**:
- Patch application rejected with messages like:
  - `[Isolation] BLOCKED: Patch attempts to modify protected path: src/autopack/research/...`

**Root Cause**:
- Executor injected `protected_paths = ["src/autopack/", ...]` which is too broad for research phases that are explicitly required to write under `src/autopack/research/*`.

**Fixes Applied (manual)**:
- Narrow `protected_paths` to system artifacts only: `.autonomous_runs/`, `.git/`, `autopack.db`.

**Files Modified**:
- `src/autopack/autonomous_executor.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-067)

### DBG-025 | 2025-12-19T13:20 | Manifest gate passes but Builder still diverges; enforce manifest inside Builder prompt + validator (OUTSIDE-MANIFEST hard fail)
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-066)
**Context**: `research-system-v12` Chunk 0.

**Symptoms**:
- Manifest gate passed (LLM enumerated the 11 required paths).
- Builder still produced a patch creating other paths or only a subset.

**Root Cause**:
- The manifest was not being surfaced as a hard constraint in the Builder prompt, and deliverables validation didn’t enforce “manifest consistency”.

**Fixes Applied (manual)**:
- Inject `deliverables_contract` + `deliverables_manifest` into Builder prompts (OpenAI + Anthropic).
- Extend deliverables validation to flag any file created outside the approved manifest as a hard violation (`OUTSIDE-MANIFEST`).

**Files Modified**:
- `src/autopack/anthropic_clients.py`
- `src/autopack/openai_clients.py`
- `src/autopack/autonomous_executor.py`
- `src/autopack/deliverables_validator.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-066)

### DBG-024 | 2025-12-19T07:35 | Deliverables keep failing despite feedback; add manifest gate to force exact file-path commitment before patch generation
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-065)
**Context**: Chunk 0 (`research-tracer-bullet`) repeatedly generating wrong-root patches even after allowlisted roots + explicit feedback.

**Symptoms**:
- Builder continues to output patches that do not create required deliverables (often creating one near-miss file only).

**Root Cause**:
- Feedback alone doesn’t force “path commitment”; the model can keep re-trying without ever committing to the full deliverables set.

**Fixes Applied (manual)**:
- Added a **deliverables manifest gate**:
  - LLM must first return a JSON array of the exact deliverable paths it will create (must match expected set exactly and stay within allowed roots)
  - only then do we run the normal Builder patch generation

**Files Modified**:
- `src/autopack/llm_service.py`
- `src/autopack/autonomous_executor.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-065)

### DBG-023 | 2025-12-19T05:35 | Deliverables enforcement too permissive: near-miss outputs outside required roots (e.g. src/autopack/tracer_bullet.py)
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-064)
**Context**: Chunk 0 (`research-tracer-bullet`) repeatedly creating “near-miss” files in plausible but incorrect locations.

**Symptoms**:
- Builder outputs patches that create files like:
  - `src/autopack/tracer_bullet.py`
  - `requirements.txt`
- while still missing all required deliverables under `src/autopack/research/...`, `tests/research/...`, `docs/research/...`.

**Root Cause**:
- Deliverables validation did not enforce a strict allowlist of valid root prefixes for file creation, so the feedback loop did not clearly communicate “anything outside these roots is invalid”.

**Fixes Applied (manual)**:
- Add strict ALLOWED ROOTS hard rule to the Builder deliverables contract.
- Update deliverables validator to:
  - derive a tight allowed-roots allowlist from expected deliverables
  - flag any actual patch paths outside those roots as a hard deliverables violation and show them explicitly in feedback.

**Files Modified**:
- `src/autopack/autonomous_executor.py`
- `src/autopack/deliverables_validator.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-064)

### DBG-022 | 2025-12-19T05:25 | Provider fallback chain broken: OpenAI builder signature mismatch + OpenAI base_url/auth confusion; replanning hard-depends on Anthropic
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-063)
**Context**: `research-system-v9` needed to fall back from Anthropic to OpenAI but failed inside the fallback path.

**Symptoms**:
- Fallback to OpenAI threw:
  - `TypeError: OpenAIBuilderClient.execute_phase() got an unexpected keyword argument 'use_full_file_mode'`
- Doctor calls routed to `openrouter.ai` and failed with `401 Unauthorized` in some environments.
- Re-planning attempted direct Anthropic calls even after Anthropic was disabled/out of credits.

**Root Causes**:
- OpenAI builder client signature lagged behind the newer Builder pipeline kwargs.
- OpenAI SDK base_url could be overridden by proxy environment configuration.
- `_revise_phase_approach` used a hard-coded direct Anthropic call (not provider-aware).

**Fixes Applied (manual)**:
- Updated OpenAI clients to use `AUTOPACK_OPENAI_BASE_URL` (default `https://api.openai.com/v1`) and accept pipeline kwargs.
- Skip replanning when Anthropic is disabled or missing key (best-effort).

**Files Modified**:
- `src/autopack/openai_clients.py`
- `src/autopack/autonomous_executor.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-063)

### DBG-021 | 2025-12-19T05:15 | Anthropic “credit balance too low” causes repeated failures; Doctor also hard-defaults to Claude
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-062)
**Context**: `research-system-v8` Chunk 0 exhausted retries immediately due to Anthropic credit depletion.

**Symptoms**:
- Builder fails with:
  - `anthropic.BadRequestError: 400 ... Your credit balance is too low ...`
- Doctor/replan also fails repeatedly because Doctor model defaults are `claude-*`.

**Root Cause**:
- No automatic provider disabling/fallback on “out of credits” responses.
- `_resolve_client_and_model` didn’t respect `ModelRouter.disabled_providers` for explicit `claude-*` requests (Doctor path).

**Fixes Applied (manual)**:
- Detect the “credit balance too low” error and disable provider `anthropic` in `ModelRouter`.
- Make `_resolve_client_and_model` respect disabled providers and fall back to OpenAI/Gemini where available.

**Files Modified**:
- `src/autopack/llm_service.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-062)

### DBG-020 | 2025-12-19T05:05 | Executor incorrectly finalizes run as DONE_* after stopping due to max-iterations (run should remain resumable)
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-061)
**Context**: `research-system-v7` was pushed into `DONE_FAILED_REQUIRES_HUMAN_REVIEW` after an early stop, despite retries remaining.

**Symptoms**:
- Runs become `DONE_*` after an executor stops due to `--max-iterations` or external stop signal.
- This prevents resuming retries and falsely requires human review.

**Root Cause**:
- Executor always ran the “completion epilogue” (`RUN_COMPLETE` + `_best_effort_write_run_summary` + learning promotion) regardless of stop reason.
- `_best_effort_write_run_summary` derives a terminal failure state if *any* phase is non-COMPLETE, which is not valid for paused/in-progress runs.

**Fixes Applied (manual)**:
- Track `stop_reason` inside the execution loop.
- Only finalize as terminal when `stop_reason == no_more_executable_phases`.
- For non-terminal stops, log `RUN_PAUSED` and keep the run resumable.

**Files Modified**:
- `src/autopack/autonomous_executor.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-061)

### DBG-019 | 2025-12-19T04:55 | Anthropic streaming can drop mid-response (incomplete chunked read) causing false phase failures
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-060)
**Context**: `research-system-v7` Chunk 0 (`research-tracer-bullet`) attempt 0

**Symptoms**:
- Builder fails with transport-level exception:
  - `httpx.RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)`

**Root Cause**:
- Transient streaming/network/proxy interruption during Anthropic SSE stream.

**Fixes Applied (manual)**:
- Added internal retry + backoff around the streaming call in `AnthropicBuilderClient.execute_phase` so transient stream errors don’t consume a full executor retry attempt.

**Files Modified**:
- `src/autopack/anthropic_clients.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-060)

### DBG-018 | 2025-12-19T04:45 | Deliverables validator misplacement detection too weak for wrong-root patches (tracer_bullet/)
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-059)
**Context**: `research-system-v6` Chunk 0 (`research-tracer-bullet`) repeatedly producing `tracer_bullet/…` outputs

**Symptoms**:
- Deliverables validation fails correctly, but the feedback lacks strong “wrong root → correct root” guidance because filenames often don’t match.

**Root Cause**:
- `deliverables_validator.py` only inferred misplacements by exact filename equality; wrong-root attempts frequently use different filenames and/or folder structures.

**Fixes Applied (manual)**:
- Detect forbidden roots in the patch (e.g. `tracer_bullet/`, `src/tracer_bullet/`, `tests/tracer_bullet/`) and show them explicitly in Builder feedback.
- Add heuristic root mapping to populate “Expected vs Created” examples when possible, even when filenames don’t match perfectly.

**Files Modified**:
- `src/autopack/deliverables_validator.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-059)

### DBG-017 | 2025-12-19T04:35 | Qdrant unreachable on localhost:6333 (no docker + compose missing qdrant)
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-058)
**Context**: Memory config defaults to `use_qdrant: true` (`config/memory.yaml`), but local Qdrant service not running

**Symptoms**:
- Memory initialization reports Qdrant unreachability (connection refused / `WinError 10061`) and falls back to FAISS.

**Root Cause**:
- No process listening on `localhost:6333`.
- Docker is not available/configured on this machine, and `docker-compose.yml` previously did not include a `qdrant` service.

**Fixes Applied (manual)**:
- Added `qdrant` service to `docker-compose.yml` so local Qdrant can be started via compose.
- Added a T0 `Vector Memory` health check that detects this and prints actionable guidance while remaining non-fatal (FAISS fallback).

**Files Modified**:
- `docker-compose.yml`
- `src/autopack/health_checks.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-058)

### DBG-016 | 2025-12-19T04:25 | Research runs: noisy Qdrant-fallback + missing consolidated journal logs; deliverables forbidden patterns not surfacing
**Severity**: LOW
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-057)
**Context**: `research-system-v5` monitoring, deliverables validation failures in Chunk 0

**Symptoms**:
- Qdrant not running locally produced WARNING-level logs even though FAISS fallback is expected.
- Missing `CONSOLIDATED_DEBUG.md` (project journal) logged every attempt despite being non-actionable for this run.
- Deliverables contract frequently reported `0 forbidden patterns`, and Builder kept creating `tracer_bullet/` instead of required `src/autopack/research/tracer_bullet/...`.

**Fixes Applied (manual)**:
- Qdrant fallback log downgraded to info for localhost.
- Missing consolidated journal log downgraded to debug.
- Deliverables contract now surfaces forbidden patterns from explicit hints and adds heuristic forbidden roots for tracer-bullet deliverables.

**Files Modified**:
- `src/autopack/journal_reader.py`
- `src/autopack/memory/memory_service.py`
- `src/autopack/autonomous_executor.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-057)

### DBG-015 | 2025-12-19T04:15 | Qdrant recovery re-ingest is manual/on-demand (not automatic) to avoid surprise indexing overhead
**Severity**: LOW
**Status**: ✅ Documented (BUILD-056)
**Context**: Memory backend may fall back to FAISS when local Qdrant is not running (dev/offline mode)

**Policy**:
- Do not auto-trigger a full memory re-ingest when Qdrant becomes available again.
- Keep re-ingest manual/on-demand to ensure predictable performance and avoid unexpected embedding/indexing load during executor runs.

**Expected Behavior**:
- Some vector-memory divergence is acceptable (FAISS may contain entries Qdrant does not while Qdrant was down).
- When desired, operator runs a re-ingest/refresh action to repopulate Qdrant from sources of truth (DB + workspace + artifacts).

**Reference**:
- `docs/BUILD_HISTORY.md` (BUILD-056)

### DBG-013 | 2025-12-19T04:05 | Qdrant not running caused memory disable; tier_id int/string mismatch; consolidated docs dropped events
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-055)
**Context**: Latest research-system runs on Windows with `config/memory.yaml` defaulting to `use_qdrant: true`

**Symptoms**:
- Memory init failures / noisy connection errors when Qdrant wasn’t running locally:
  - `Failed to ensure collection ... [WinError 10061]`
  - executor fell back to “running without memory” instead of using FAISS.
- IssueTracker schema warnings due to `tier_id` being an int DB PK in some payloads.
- Consolidated docs logging warned “File not found ... CONSOLIDATED_BUILD.md” and dropped events.

**Root Causes**:
- Memory service treated “Qdrant unreachable” as fatal during init rather than a normal offline/dev condition.
- Tier IDs were inconsistent across DB, backend serialization, and executor phase dicts.
- Archive consolidator assumed consolidated docs already existed and would not create them.

**Fixes Applied (manual)**:
- Memory: auto-fallback Qdrant → FAISS when Qdrant is unreachable, preserving memory functionality without requiring paid services.
- Tier IDs: normalize to stable string tier identifiers in backend + executor, and cast IDs to strings in IssueTracker.
- Consolidated docs: auto-create skeleton `CONSOLIDATED_*.md` files so logging persists events.

**Files Modified**:
- `src/autopack/memory/memory_service.py`
- `src/autopack/memory/qdrant_store.py`
- `src/autopack/archive_consolidator.py`
- `src/autopack/issue_tracker.py`
- `src/autopack/autonomous_executor.py`
- `src/backend/api/runs.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-055)

### DBG-012 | 2025-12-19T03:40 | Windows executor startup noise + failures (lock PermissionError, missing /health, Unix-only diagnostics cmds)
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-054)
**Context**: `research-system-v4` monitoring on Windows

**Symptoms**:
- Locking could throw a hard error:
  - `PermissionError: [Errno 13] Permission denied` from `executor_lock.py` during lock acquisition.
- API check noise:
  - “Port 8000 is open but API health check failed. Assuming API is running.”
- Diagnostics noise:
  - Baseline probes attempted `du -sh .` and `df -h .` and failed on Windows with `[WinError 2]`.
- Optional dependency noise:
  - FAISS missing warning despite in-memory fallback.
- Optional artifact noise:
  - `CONSOLIDATED_DEBUG.md not found ...`

**Root Causes**:
- Windows locking: lock file was written/flushed **before** acquiring `msvcrt` lock; Windows can raise PermissionError if another process holds the lock.
- Backend API did not expose `/health`.
- Diagnostics baseline used Unix-only commands unconditionally.

**Fixes Applied (manual)**:
- Updated lock acquisition to lock first, then write metadata; treat Windows permission errors as “lock held”.
- Added `GET /health` endpoint to `src/backend/main.py`.
- Made baseline disk probes conditional (skip `du/df` on Windows / when not available).
- Downgraded optional-missing logs to info.

**Files Modified**:
- `src/autopack/executor_lock.py`
- `src/backend/main.py`
- `src/autopack/diagnostics/diagnostics_agent.py`
- `src/autopack/journal_reader.py`
- `src/autopack/memory/faiss_store.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-054)

### DBG-011 | 2025-12-19T03:25 | Backend API missing executor phase status route (`/update_status`) caused 404 spam
**Severity**: MEDIUM
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-053)
**Context**: `research-system-v3`, executor attempting to persist phase state changes via API

**Symptoms**:
- Executor warnings like:
  - `Failed to update phase <phase_id> status: 404 Client Error: Not Found for url: http://localhost:8000/runs/<run_id>/phases/<phase_id>/update_status`

**Root Cause**:
- The running backend (`backend.main:app` → `src/backend/main.py`) uses the minimal runs router in `src/backend/api/runs.py`, which did not implement the endpoint the executor expects (`POST /runs/{run_id}/phases/{phase_id}/update_status`).

**Fixes Applied (manual)**:
- Added a compatibility endpoint `POST /runs/{run_id}/phases/{phase_id}/update_status` in `src/backend/api/runs.py` to update phase state (and best-effort optional telemetry fields) in the DB.
- Restarted the backend API server so the route was loaded.

**Files Modified**:
- `src/backend/api/runs.py`

**References**:
- `docs/BUILD_HISTORY.md` (BUILD-053)

### DBG-010 | 2025-12-19T02:40 | Research System Chunk 0 Stuck: Skip-Loop Abort + Doctor Interference
**Severity**: HIGH
**Status**: ✅ Resolved (Manual Hotfixes: BUILD-051)
**Context**: `research-system-v2` run, phase `research-tracer-bullet` (Chunk 0)

**Symptoms**:
- Phase repeatedly failed deliverables validation (files created under `tracer_bullet/` instead of required `src/autopack/research/...`)
- Executor entered a skip/abort loop (FAILED → auto-reset to QUEUED → skipped again), aborting after 10 skips
- Doctor re-planning was triggered on deliverables-validation failures, which can conflict with learning hints (see `docs/DBG-014_REPLAN_INTERFERENCE_ANALYSIS.md`)

**Root Cause**:
- Skip-loop logic in `src/autopack/autonomous_executor.py` could livelock with BUILD-041 auto-reset logic.
- `DELIVERABLES_VALIDATION_FAILED` was not mapped to a dedicated outcome, so Doctor gating for deliverables failures did not apply.

**Fixes Applied (manual)**:
- Removed skip/abort loop behavior so retries remain DB-driven (BUILD-041-aligned).
- Mapped `DELIVERABLES_VALIDATION_FAILED` → `deliverables_validation_failed`.
- Gated Doctor for deliverables failures to defer to learning hints until retry budget is exhausted (DBG-014-aligned).
- Deferred mid-run re-planning for `deliverables_validation_failed` so re-planning doesn’t interfere with the tactical hints loop.
- Fixed executor crash on max-attempt exhaustion: `autopack.error_reporter` was missing `log_error` symbol expected by executor; added a safe wrapper delegating to `autopack.debug_journal.log_error`.
- Fixed auto-reset livelock after retry exhaustion: auto-reset and “executable phase” selection now correctly use `retry_attempt < MAX_RETRY_ATTEMPTS` (not `builder_attempts < max_builder_attempts`), preventing FAILED↔QUEUED loops once retries are truly exhausted.
- Added multi-tier gating: multi-tier runs do not progress to later tiers when the earliest tier has unresolved non-COMPLETE phases (enforces Chunk 0 “must pass before proceeding”).

**Files Modified**:
- `src/autopack/autonomous_executor.py`
- `src/autopack/error_reporter.py`

**References**:
- `docs/BUILD-049_DELIVERABLES_VALIDATION.md`
- `docs/DBG-014_REPLAN_INTERFERENCE_ANALYSIS.md`
- `docs/EXECUTOR_STATE_PERSISTENCE_ARCHITECTURE.md`

### DBG-006 | 2025-12-17T13:30 | CI Test Failures Due to Classification Threshold Calibration
**Severity**: MEDIUM
**Status**: ✅ Resolved (BUILD-047 Complete)
**Root Cause**: LLM-generated classification logic has **confidence thresholds too high** (0.75) and **keyword lists too comprehensive** (16+ keywords), making it impossible for realistic test data to pass. Test documents achieve ~0.31 score but require ≥0.75.

**Evidence**:
```
FAILED test_canada_documents.py::TestCanadaDocumentPack::test_classify_cra_tax_form
  Combined score: 0.312 (keyword: 0.188, pattern: 0.500)
  Threshold: 0.75
  Result: FAIL (0.312 < 0.75)
```

**Pattern**: 100% consistent - all 14 phases have exactly 33 PASSED, 14 FAILED tests (7 classify() tests per country pack).

**Analysis**:
- Classification logic is **structurally correct** (keyword/pattern matching works)
- Problem: Keyword dilution (3/16 matched = 18.8% score) + threshold too strict (0.75)
- Example: CRA tax form test matches 3/16 keywords, 2/4 patterns → 0.312 combined score
- Tests are valid - they expose that thresholds need calibration for realistic documents

**Impact**: Quality gate correctly flags all phases as NEEDS_REVIEW. Code structure is sound, just needs parameter tuning.

**Resolution Path**:
1. ✅ **Comprehensive analysis complete** → [QUALITY_GATE_ANALYSIS.md](./QUALITY_GATE_ANALYSIS.md)
2. ✅ **BUILD-047 implemented three-part fix**:
   - Lower confidence thresholds: 0.75 → 0.43
   - Refine keyword lists: 16+ → 5-7 most discriminative
   - Adjust scoring weights: 60/40 → 40/60 (keywords/patterns)
3. ✅ **Test validation complete**: 25 passed, 0 failed (100% pass rate)

**Cost-Benefit**: BUILD-047 (4 hrs) saves 26 hrs manual review = 650% ROI

**First Seen**: fileorg-phase2-beta-release run (all 14 completed phases)
**Resolved**: 2025-12-17T16:45 (BUILD-047 complete, all tests passing)
**Reference**:
- [BUILD-047_CLASSIFICATION_THRESHOLD_CALIBRATION.md](./BUILD-047_CLASSIFICATION_THRESHOLD_CALIBRATION.md) - Implementation
- [QUALITY_GATE_ANALYSIS.md](./QUALITY_GATE_ANALYSIS.md) - Full analysis
- `.autonomous_runs/fileorg-phase2-beta-release/ci/pytest_fileorg-p2-*.log` - Original failing test logs
- [canada_documents.py:220](../src/backend/packs/canada_documents.py#L220) - Classification logic

---

### DBG-005 | 2025-12-17T13:30 | Advanced Search Phase: max_tokens Truncation
**Severity**: HIGH
**Status**: ⚠️ Identified - Will Be Fixed by BUILD-042
**Root Cause**: Phase failed with max_tokens truncation (100% utilization) because BUILD-042 fix not active in running executor. High complexity phase only got 4096 tokens instead of 16384.

**Evidence**:
```
[2025-12-17 04:12:17] WARNING: [Builder] Output was truncated (stop_reason=max_tokens)
[2025-12-17 04:13:00] WARNING: [Builder] Output was truncated (stop_reason=max_tokens)
ERROR: [fileorg-p2-advanced-search] Builder failed: LLM output invalid format
```

**Pattern**:
- Phase: fileorg-p2-advanced-search (complexity=high)
- Attempts: 1/5 (failed on first attempt, never retried)
- Reason: DOCTOR_SKIP: PATCH_FAILED

**Analysis**:
1. High complexity phase needs 16384 tokens (per BUILD-042)
2. Running executor still used old 4096 token default
3. LLM output truncated mid-JSON, causing parse failure
4. Phase marked FAILED but never retried (attempts=1/5 is unusual)

**Mystery**: Why only 1/5 attempts when max_attempts=5?
- Likely: Doctor triggered SKIP action after first failure
- Executor moved to next phase instead of retrying
- Expected: Should have retried up to 5 times with BUILD-041

**Solution**:
- ✅ BUILD-042 fix already committed (de8eb885)
- ✅ Automatic phase reset will retry on next executor restart
- Expected outcome: Phase will succeed with 16384 token budget

**Impact**: Single phase failure (6.7% of total phases). Will be resolved on next run with BUILD-042 active.

**First Seen**: fileorg-phase2-beta-release run (2025-12-17 04:12:17)
**Reference**: `src/autopack/anthropic_clients.py:156-180` (BUILD-042 fix)

---

### DBG-004 | 2025-12-17T13:30 | BUILD-042 Token Scaling Not Active in Running Executor
**Severity**: HIGH
**Status**: ✅ Resolved
**Root Cause**: Python module caching prevented BUILD-042 complexity-based token scaling from being applied. Executor process started before BUILD-042 commit (de8eb885), so imported `anthropic_clients.py` with old max_tokens logic.

**Evidence from Logs**:
```
[TOKEN_BUDGET] phase=fileorg-p2-uk-template complexity=low input=17745 output=4096/4096 total=21841 utilization=100.0%
```
Expected with BUILD-042: `output=X/8192` for low complexity (not 4096)

**Python Caching Behavior**:
- Executor imports modules once at startup
- Code changes during runtime NOT reloaded automatically
- Old executor (started 04:11): Using 4096 token default
- New executor (started 13:21): Using BUILD-042 complexity-based scaling

**Impact**:
- 3 country template phases hit 100% token utilization (truncation)
- Required 2-4 retry attempts each
- Total wasted: ~6 extra API calls (~$0.30)

**Solution**:
- ✅ BUILD-042 fix committed (de8eb885) - moved complexity scaling earlier
- ✅ New executor instances automatically use fixed code
- ✅ Automatic phase reset will retry failed phases with proper token budgets

**Validation**:
New executor (started 13:21) shows BUILD-042 active:
```
[TOKEN_BUDGET] phase=fileorg-p2-frontend-build complexity=medium input=3600 output=1634/4096 total=5234 utilization=39.9%
```

**Lesson Learned**: Always restart executor process after code changes to ensure fixes are applied.

**First Identified**: 2025-12-17 13:22 (during final results analysis)
**Resolved**: 2025-12-17 13:30 (committed fix + documented)
**Reference**: `src/autopack/anthropic_clients.py:156-180`

---

### DBG-003 | 2025-12-17T01:50 | Executor Infinite Failure Loop
**Severity**: CRITICAL
**Status**: ✅ Resolved (BUILD-041 Complete + Automatic Phase Reset)
**Root Cause**: execute_phase() retry loop returns early before exhausting max_attempts (due to Doctor actions, health checks, or re-planning), but database phase state remains QUEUED. Main loop re-selects same phase, creating infinite loop.

**Evidence**:
- FileOrganizer Phase 2 run stuck on "Attempt 2/5" repeating indefinitely
- Log pattern: Iteration 1: Attempt 1→2 fails → Iteration 2: Attempt 2 (REPEATED, should be 3)
- Cause: State split between instance attributes (`_attempt_index_{phase_id}`) and database (`phases.state`)

**Architecture Flaw**:
- Instance attributes: Track attempt counter (volatile, lost on restart)
- Database: Track phase state (persistent but not updated on early return)
- Desynchronization: When execute_phase() returns early, database not marked FAILED

**Solution**: BUILD-041 Database-Backed State Persistence
- Move attempt tracking from instance attributes to database columns
- Execute ONE attempt per call (not a retry loop)
- Update database atomically after each attempt
- Main loop trusts database for phase selection

**Implementation Progress**:
- ✅ Phase 1: Database schema migration (4 new columns added to phases table)
- ✅ Phase 2: Database helper methods
- ✅ Phase 3: Refactored execute_phase() to use database state
- ✅ Phase 4: Updated get_next_executable_phase() method
- ✅ Phase 5: Feature deployed and validated
- ✅ BONUS: Automatic phase reset for failed phases with retries remaining (commit 23737cee)

**Validation Results**:
- FileOrg Phase 2 run completed successfully: 14/15 phases (93.3% success rate)
- Average 1.60 attempts per phase (down from 3+ baseline)
- No infinite loops detected
- Automatic retry logic working as designed

**Reference**: `docs/BUILD-041_EXECUTOR_STATE_PERSISTENCE.md`, `docs/EXECUTOR_STATE_PERSISTENCE_ARCHITECTURE.md`
**First Seen**: fileorg-phase2-beta-release run (2025-12-17T01:45)
**Resolved**: 2025-12-17T04:34 (run completed)
**Impact**: Previously blocked all long-running autonomous runs (>5 phases) - NOW RESOLVED

---

### DBG-001 | 2025-12-13T00:00 | Post-Tidy Verification Report
**Severity**: MEDIUM
**Status**: ✅ Resolved
**Root Cause**: Workspace organization verification after tidy operation. All checks passed.
**Details**:
- Date: 2025-12-13 18:37:33
- Target Directory: `archive`
- ✅ `BUILD_HISTORY.md`: 15 total entries
- ✅ `DEBUG_LOG.md`: 0 total entries
- ✅ `ARCHITECTURE_DECISIONS.md`: 0 total entries
- ✅ All checks passed

**Source**: `archive\reports\POST_TIDY_VERIFICATION_REPORT_20251213_183829.md`

---

### DBG-002 | 2025-12-11T18:20 | Workspace Organization Issues - Root Cause Analysis
**Severity**: CRITICAL
**Status**: ✅ Resolved
**Root Cause**: PROPOSED_CLEANUP_STRUCTURE.md specification was incomplete and logically flawed, leading to organizational issues.

**Problem**:
- The spec kept `docs/` at root but provided no guidance on contents
- Result: Nearly empty directory with only SETUP_GUIDE.md
- Violated principles of clarity and non-redundancy

**Resolution**: Complete workspace reorganization following revised specification.

**Source**: `archive\tidy_v7\WORKSPACE_ISSUES_ANALYSIS.md`

---

## Summary Statistics

**Total Issues Logged**: 6
**Critical Issues**: 2 (both resolved)
**High Severity**: 2 (1 resolved, 1 pending BUILD-042 restart)
**Medium Severity**: 2 (1 resolved, 1 identified as expected behavior)

**Resolution Rate**: 66.7% fully resolved, 33.3% identified/in-progress

**Most Impactful Fix**: BUILD-041 (eliminated infinite retry loops, enabled 93.3% phase completion rate)
