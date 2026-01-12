# Autopack — Remaining Improvement Areas (Current Scan) — 2026-01-12

**Scope**: “Now” (current `main`, post recent PR streak through `#131` and PR-A…F executor seam refactor commits).  
**Goal**: list *all meaningful remaining* improvement areas vs the README ideal state (**safe, deterministic, mechanically enforceable via CI contracts**) and “beyond README” hardening, without re-creating “two truths”.

> This file is a **snapshot report** (not a canonical planning surface).  
> Canonical backlogs / deep scans already in-repo:
> - `docs/IMPROVEMENTS_GAP_ANALYSIS.md` (P0–P3 backlog + acceptance criteria)
> - `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`
> - `docs/reports/IMPROVEMENT_OPPORTUNITIES_COMPREHENSIVE_2026-01-11.md`
> - `docs/reports/IMPROVEMENT_AUDIT_DELTA_2026-01-11.md`

---

## 0) What the recent PR streak materially improved (so we don’t re-solve closed gaps)

From `git log` on `main`:

- **Executor maintainability (PR1/PR2 + PR-A…F + #131)**: substantial seam extraction under `src/autopack/executor/` and `src/autopack/executor/phase_handlers/`.
- **Docs/CI correctness hardening (PR-110…117)**: canonical-doc drift guards, build-surface guards, Qdrant determinism pin, Windows-first task runner, route shape contract tests.
- **Frontend production hardening (PR-07)**: prod sourcemaps disabled + CI enforcement.

Net: the “ideal state” gaps are no longer dominated by doc/compose two-truths; remaining work is mostly **scale/maintenance**, **hardening last-mile**, and **tightening staged checks**.

---

## 1) Highest-ROI remaining improvements (comprehensive, categorized)

### 1.1 Maintainability scaling: shrink remaining “god files” (P1)

Current top Python files by LOC (mechanical scan):

- `src/autopack/autonomous_executor.py` (~10,401)
- `src/autopack/anthropic_clients.py` (~4,182)
- `src/autopack/main.py` (~165 after PR-API-3 extraction; was ~3,343)
- `src/autopack/governed_apply.py` (~2,397)
- `src/autopack/llm_service.py` (~1,816)

**Why this still matters** (relative to “mechanically enforceable”): large modules are where “implicit contracts” and drift reappear (harder review, harder test isolation, more fragile lint/type posture).

**Concrete next seams** (low-churn, contract-first):

- **`main.py` → routers** (`src/autopack/api/routes/*` + `api/deps.py`), while keeping route shapes stable (your existing route-contract tests make this safer).
- **`autonomous_executor.py` → more extraction**:
  - finish separating orchestration vs pure policy
  - keep phase special-cases isolated to `phase_handlers/` via registry (continuing the PR-A…F direction)
- **`anthropic_clients.py` / provider adapters**:
  - reduce implicit behavior by introducing small typed request/response models and moving prompt construction into prompt modules
- **`governed_apply.py`**:
  - keep it “micro-kernel style”: maximize pure helpers + table-driven tests around enforcement boundaries.

### 1.2 Tighten the "staged" enforcement ladder: types + aspirational checks (P1/P2)

**Mypy Tier-1 Blocking** ✅ IMPLEMENTED (PR #144, merged 2026-01-12)
- **Changed**: Removed `continue-on-error: true` from mypy CI step
- **Impact**: Mypy Tier-1 failures now BLOCK PR merges
- **Scope**: 6 modules must remain type-clean:
  - `src/autopack/version.py`
  - `src/autopack/__version__.py`
  - `src/autopack/safe_print.py`
  - `src/autopack/file_hashing.py`
  - `src/autopack/config.py`
  - `src/autopack/schemas.py`
- **Verification**: All Tier-1 modules pass mypy with 0 errors

**Aspirational tests** are non-blocking by design.

**Remaining work**:
- **Aspirational → core promotions**: establish a small cadence ("each week, promote N tests from aspirational to core once stable") to prevent permanent limbo.

### 1.3 Prevent "gaps reappearing" by codifying recurring drift vectors (P1)

**BUILD-135: Executor HTTP Enforcement** ✅ IMPLEMENTED (PRs #141-143, merged 2026-01-12)
- **Created**: `test_executor_http_enforcement.py` - grep-based test preventing raw `requests.*` usage
- **Phase 1** (PR #141): Enforced on `src/autopack/executor/` package
- **Phase 2** (PR #143): Extended to include `src/autopack/autonomous_executor.py`
- **Impact**: Prevents "executor never talks raw HTTP" contract from drifting
- **Architectural guidance**: Added docstring clarifying SupervisorApiClient is the only allowed HTTP zone

**SOT portability discipline**: `docs/FUTURE_PLAN.md` currently contains legacy path references, but they are already **scoped** as "FileOrganizer repo, NOT Autopack" — keep enforcing that scoping pattern if more legacy paths are referenced in SOT docs.

**"One truth" by construction**: prefer generating operator-facing snippets (compose commands, ports, env template path, auth path prefixes) from one canonical source where feasible (or keep them guarded by narrow doc-contract tests).

### 1.4 Frontend maturity: tests + auth story + operator UX (P2)

Current root Vite UI is clean and CI’d (lint/typecheck/build), but remaining ideal-state gaps are:

- **Testing**: no unit/component test harness is present in `package.json` (only lint/type-check/build). Add minimal tests if UI is meant to be trusted operator surface.
- **Auth posture clarity**: ensure the “production operator UI” story is explicit (JWT browser sessions vs API-key operator access) and tested at the boundary (you already have `/api/auth/` routing constraints in `nginx.conf` + API contract tests; extend if needed).

### 1.5 Health checks correctness and operator trust (P2)

**Health Check Correctness** ✅ ALREADY COMPLETE (Verified 2026-01-12)

**Status**: Investigation confirmed both requirements are already implemented:

1. **Backend-aware DB checks**: ✅ Implemented
   - `HealthChecker.check_database()` detects Postgres vs SQLite via `DATABASE_URL`
   - Postgres: TCP socket probe to host:port
   - SQLite: File existence check
   - **Verified in**: [test_health_checks.py](tests/unit/test_health_checks.py) lines 23-71

2. **"At least one provider" semantics**: ✅ Implemented (PR-05)
   - `HealthChecker.check_api_keys()` checks for ANY valid provider key
   - Does NOT require all providers (Anthropic, OpenAI, Google)
   - **Verified in**: [test_health_checks.py](tests/unit/test_health_checks.py) lines 85-129

**Enforcement tests**: Existing unit tests in `tests/unit/test_health_checks.py` already validate both correctness requirements. Created additional enforcement test file [test_health_check_correctness_enforcement.py](tests/unit/test_health_check_correctness_enforcement.py) documenting the requirements explicitly for future maintainers.

### 1.6 Security “beyond README”: reduce accepted-debt surface area over time (P2/P3)

Security baseline + diff gates are strong; remaining work is mostly “hardening maturity”:

- Turn recurring accepted findings into either:
  - **proved-safe invariants** (tests + docs), or
  - **targeted remediations** where cheap (especially around artifact exposure/redaction and debug-mode constraints).
- Decide whether any security workflows should move from “regression-only, informational” to “blocking” (only after stable baselines + low noise).

### 1.7 Compose/ops end-to-end smoke validation (P2) ✅ COMPLETE

**Status**: Implemented 2026-01-12

**What was delivered**:
- **Created**: `scripts/smoke_test_compose.py` - Comprehensive Python-based smoke test suite
  - nginx health endpoint validation (`/nginx-health`)
  - Proxied backend health validation (`/health`)
  - `/api/auth/*` prefix preservation check
  - Database connectivity (pg_isready)
  - Qdrant connectivity (with graceful degradation)
  - Backend readiness checks (DB + Qdrant status)
- **Created**: `scripts/smoke_test_compose.sh` - Shell wrapper for easy execution
  - Manages compose lifecycle (start, test, cleanup)
  - Supports `--no-cleanup` flag for debugging
- **Created**: `tests/integration/test_compose_smoke.py` - Pytest integration tests
  - 15+ test cases covering all topology validation points
  - Structured test classes by domain (routing, auth, readiness)
  - End-to-end smoke test combining all validations
- **Created**: `tests/integration/README_SMOKE_TESTS.md` - Documentation
- **Updated**: `.github/workflows/compose-smoke.yml` - Enhanced CI workflow
  - Uses new comprehensive smoke test script
  - Runs weekly (Sunday 06:00 UTC) + manual trigger
  - Non-blocking (continue-on-error)

**Verification**:
- All smoke test scripts pass syntax/lint checks (ruff)
- Shell script syntax validated (bash -n)
- Python scripts compile cleanly (py_compile)

**Impact**: Catches "integration drift" issues - services that work in isolation but fail when composed together, nginx routing breaks, prefix preservation failures, and connectivity issues.

---

## 2) Small, concrete nits worth closing (P3)

These are low priority, but they remove lingering "toy" or "shim" surfaces:

**CLI phases.py shim messages** ✅ IMPLEMENTED (2026-01-12)
- **Status**: Complete
- **Changed**: `src/autopack/cli/commands/phases.py`
  - Removed duplicate code (113 lines → 97 lines)
  - Added clear deprecation notices in module docstring
  - Added migration guidance message pointing to Supervisor REST API and Web UI
  - Updated mock output to clearly indicate "test data only"
  - All commands now show deprecation warnings with specific API endpoints
- **Tests updated**: `tests/autopack/cli/test_phase_commands.py`
  - Updated test expectations for new messaging
  - Added `test_deprecation_messages_shown()` to verify guidance is displayed
- **Impact**: Users now receive clear guidance to use production APIs instead of test shim

---

## 3) Suggested next PR stack (sequenced; minimal-churn first)

1. **API refactor**: split `src/autopack/main.py` into routers (no route changes; keep contract tests).
2. **Executor refactor**: continue extracting seams from `autonomous_executor.py` (registry-based phase handlers is already the direction; keep going).
3. **Type ladder**: make a small mypy Tier-1 subset blocking.
4. **Frontend**: add minimal test harness (if UI is a trusted operator surface).
5. **Ops smoke**: add/extend a compose smoke workflow to validate nginx routing + backend readiness end-to-end.

---

## 4) “Where to look next” (if you ask “continue”)

Next pass can add a **file-by-file seam map** for the top 5 largest modules above (what to extract, in what order, and the contract tests to add per seam), including:

- a proposed `api/routes/*` module structure for `main.py`
- a proposed `executor/*` seam list to shrink `autonomous_executor.py` safely
- a list of “new gaps likely to reappear” and the smallest guardrail/test to prevent each one

---

## 5) File-by-file seam map (biggest modules) — extraction order + contract tests

**Goal**: shrink the “gaps keep reappearing” surface area by isolating responsibilities behind stable interfaces, while keeping behavior stable via contract tests.

**Extraction method (low-risk default)**:

- **Step A (wrapper first)**: create a new module and call it from the big file (no behavior changes).
- **Step B (tests)**: add/extend a contract test for the extracted seam.
- **Step C (move code)**: move implementation into the new module, keep the old method as a thin delegator.
- **Step D (clean-up)**: only after tests pass, delete dead/obsolete code and tighten lint/type posture.

### 5.1 `src/autopack/main.py` (API “god file”) → routers + deps

**What’s currently inside (clusters)**:
- **Auth deps**: `verify_api_key()`, `verify_read_access()`
- **Rate limiting keying**: `get_client_ip()` + trusted proxy logic + `Limiter`
- **App wiring**: `lifespan`, CORS, error handling, mounting routers (`/api/auth`, `/research`)
- **Many endpoint domains** in one module:
  - runs + phases
  - artifacts + browser artifacts
  - approvals + telegram webhook
  - governance
  - dashboard
  - storage optimizer
  - upload
  - health

**Seam extraction order** (keep route shapes unchanged):

1) **`api/deps.py` (auth + rate-limit key function)**
   - Move: `verify_api_key`, `verify_read_access`, `_is_trusted_proxy`, `get_client_ip`, `limiter`
   - Keep `main.py` importing these as-is.
   - **Contract tests**:
     - Existing: `tests/api/test_route_contract.py` (ensures endpoints don’t disappear)
     - Add: `tests/api/test_auth_dependency_contract.py`
       - verifies TESTING/production behavior for `verify_api_key` and `verify_read_access`
       - verifies `get_client_ip` respects trusted proxies and ignores spoofed headers

2) **`api/app.py` (app factory + middleware + lifespan)**
   - Move: `lifespan`/startup tasks, CORS wiring, limiter exception handler wiring, global exception handler wiring.
   - Keep `src/autopack/main.py` as a thin shim exporting `app` for the canonical entrypoint (`uvicorn autopack.main:app`).
   - **Contract tests**:
     - Existing: `tests/api/test_route_contract.py`
     - Add: `tests/api/test_openapi_smoke.py` (OpenAPI loads; tags/prefixes consistent)

3) **Routers by domain (one file each)**
   - `api/routes/runs.py` (run start, list, get, progress)
   - `api/routes/phases.py` (update_status, builder_result, auditor_result, issues)
   - `api/routes/artifacts.py` (artifacts index/file, browser artifacts)
   - `api/routes/approvals.py` (approval endpoints + telegram webhook handler)
   - `api/routes/governance.py`
   - `api/routes/dashboard.py`
   - `api/routes/storage.py`
   - `api/routes/files.py` (upload)
   - `api/routes/health.py`
   - **Contract tests**:
     - Existing: `tests/api/test_route_contract.py`
     - Add: `tests/api/test_router_registration_contract.py`
       - asserts each router is mounted (by checking OpenAPI path prefixes)

**Why this closes “reappearing gaps”**:
- It makes “what routes exist” and “what deps guard them” mechanically verifiable as the code grows (route contract test already exists; seam tests prevent policy drift).

### 5.2 `src/autopack/autonomous_executor.py` (executor “god file”) → client + pipelines + legacy removal

**What’s still inside despite PR-A…F seams** (clusters visible in-file):
- **Phase attempt orchestration** (now partially delegated: `attempt_runner`, `retry_policy`, `phase_dispatch`, `context_loading`)
- **Context preflight + retrieval injection** (file-size gates, SOT retrieval budget gating, intention context injection)
- **Patch apply + governance loop glue** (governed apply + protected path governance + allowance retry)
- **CI execution + parsing + log persistence**
- **Supervisor API integration** (post status/results, request approvals, poll approvals)
- **Run checkpoint + rollback** (git subprocess)
- **Large legacy blocks** kept inline (including “obsolete code below” blocks)
- **CLI parsing / entrypoint**

**Seam extraction order** (highest merge-conflict + drift hotspots first):

1) **Supervisor API client**
   - New module: `src/autopack/supervisor/api_client.py` (or `executor/supervisor_client.py`)
   - Move: all `requests.get/post(...)` calls for:
     - `/health`
     - `/runs/{run_id}/*` status updates
     - `/approval/*` request + poll
     - `/governance/*` read/approve paths (where executor touches them)
   - Provide a single interface: `update_phase_status()`, `post_builder_result()`, `post_auditor_result()`, `request_approval()`, `poll_approval()`, `get_next_phase()`.
   - **Contract tests**:
     - Add: `tests/unit/test_supervisor_api_client_contract.py`
       - builds URLs correctly
       - includes `X-API-Key` when configured
       - maps HTTP/network errors into typed outcomes (no raw exceptions escaping the executor loop)

2) **Approval + polling flow consolidation**
   - New module: `src/autopack/executor/approval_flow.py`
   - Move: `_request_human_approval`, `_request_build113_approval`, `_request_build113_clarification`
   - (Keep Telegram webhook logic server-side; executor should only call “approval API”.)
   - **Contract tests**:
     - Add: `tests/executor/test_approval_flow_timeout_behavior.py`
       - deterministic timeout handling
       - ensures polling interval logic is bounded and testable (inject clock/sleep)

3) **CI runner extraction**
   - New module: `src/autopack/executor/ci_runner.py`
   - Move: `_run_ci_checks`, `_run_custom_ci_command`, `_parse_pytest_counts`, `_persist_ci_log`, `_trim_ci_output`
   - **Contract tests**:
     - Add: `tests/executor/test_ci_output_parsing_contract.py`
       - table-driven pytest output → (passed/failed/error) counts
       - ensures parsing is stable for common pytest summary shapes

4) **Run checkpoint + rollback**
   - New module: `src/autopack/executor/run_checkpoint.py`
   - Move: create checkpoint, rollback, audit log writing, git subprocess calls.
   - Prefer to route git interactions through `git_adapter.py` (or a thin wrapper) to reduce scattered subprocess logic.
   - **Contract tests**:
     - Add: `tests/unit/test_run_checkpoint_git_commands.py`
       - monkeypatches subprocess to ensure the exact git commands are invoked
       - verifies “no checkpoint commit” fails fast without destructive commands

5) **Context preflight + injection**
   - New modules:
     - `src/autopack/executor/context_preflight.py` (file-size buckets / read-only enforcement decisions)
     - `src/autopack/executor/retrieval_injection.py` (SOT retrieval gating + telemetry calls)
   - Keep `executor/context_loading.py` as the single entrypoint for “what files do we load”, and keep preflight decisions separate from loading mechanics.
   - **Contract tests**:
     - Add: `tests/executor/test_context_preflight_policy.py` (bucket logic, deterministic output)

6) **Move `_load_repository_context_heuristic` out of the god file**
   - New module: `src/autopack/executor/context_loading_heuristic.py`
   - Keep `context_loading.load_repository_context()` as the orchestrator and call into the heuristic helper as needed.
   - **Contract tests**:
     - Add: `tests/executor/test_context_loading_heuristic_determinism.py`
       - ensures ordering is deterministic (git status first, then mentioned files, then priority files, etc.)
       - ensures max file cap honored

7) **Delete/relocate “obsolete code below” blocks**
   - Goal: remove thousands of lines of dead code and prevent drift from “reference-only” logic.
   - If historical value matters, move to `archive/` as a superseded report, not inside runtime.
   - **Contract tests**:
     - Existing: route/CI/doc contracts already protect the public behavior; this step is mainly churn reduction.

**Existing guardrails to lean on while refactoring**:
- Phase handler registry contract: `tests/unit/test_executor_phase_dispatch_contract.py`
- Route stability contract (API side): `tests/api/test_route_contract.py`

### 5.3 `src/autopack/governed_apply.py` (safety-critical) → “micro-kernel” split

**What’s inside (clusters)**:
- Patch parsing/sanitization/repair (`_sanitize_patch`, hunk repair, empty diff repair)
- Patch validation (quality checks, context checks, truncation heuristics)
- Policy enforcement (protected paths, allowed paths, scope constraints)
- Application engine (git apply + fallback writes; NDJSON synthetic header handling)
- Rollback/savepoint integration

**Seam extraction order** (keep `GovernedApplyPath.apply_patch()` signature stable):

1) **Patch parsing + sanitization helpers**
   - New module: `src/autopack/patching/patch_sanitize.py`
   - Move: `_sanitize_patch`, `_fix_empty_file_diffs`, `_repair_hunk_headers`, file extraction helpers.
   - **Contract tests**:
     - Add: `tests/patching/test_patch_sanitize_contract.py` (table-driven patch inputs → sanitized outputs)

2) **Policy enforcement as a standalone object**
   - New module: `src/autopack/patching/policy.py`
   - Convert “protected + allowed + scope_paths + internal mode” into a `PatchPolicy` object with:
     - `validate_paths(files_touched) -> violations`
   - **Contract tests**:
     - Reuse/extend existing governed-apply tests:
       - `tests/test_governed_apply.py`
       - `tests/test_governed_apply_no_delete_protected_on_new_file_conflict.py`
       - `tests/test_governed_apply_ndjson_synthetic_header.py`

3) **Patch quality validation**
   - New module: `src/autopack/patching/patch_quality.py`
   - Move: `_validate_patch_quality`, `_validate_patch_context`, symbol preservation checks, structural similarity checks.
   - **Contract tests**:
     - Add: `tests/patching/test_patch_quality_contract.py` (truncation markers, malformed hunks, context mismatch)

4) **Apply engine**
   - New module: `src/autopack/patching/apply_engine.py`
   - Own responsibility: apply-to-disk and return structured failure reasons.
   - Keep rollback integration as a wrapper around the engine.
   - **Contract tests**:
     - Add: `tests/patching/test_apply_engine_no_side_effects_on_failure.py`

### 5.4 `src/autopack/anthropic_clients.py` (provider “mega client”) → transport + prompts + parsers

**What’s inside (clusters)**:
- Provider transport (Anthropic SDK usage + streaming)
- Budget enforcement + prompt rebuilding (“PROMPT_BUDGET”)
- Multiple output formats and heavy parsing:
  - full-file JSON output parsing + repair
  - NDJSON parsing
  - structured edit parsing
  - legacy diff parsing
  - continuation recovery
- Diff generation (git-compatible diffs generated locally)
- Prompt construction (large system/user prompts with many modes)

**Seam extraction order** (keep `AnthropicBuilderClient.execute_phase()` stable):

1) **Transport wrapper**
   - New module: `src/autopack/llm/providers/anthropic_transport.py`
   - Responsibility: send request, stream response, return `(content, usage, stop_reason)` with typed exceptions.
   - **Contract tests**:
     - Add: `tests/llm_providers/test_anthropic_transport_contract.py` (mock Anthropic SDK; ensure usage extraction is stable)

2) **Prompt builders**
   - New module: `src/autopack/llm/prompts/anthropic_builder_prompts.py`
   - Move: `_build_system_prompt`, `_build_minimal_system_prompt`, `_build_user_prompt`
   - **Contract tests**:
     - Add: `tests/llm_prompts/test_anthropic_prompt_modes_contract.py`
       - verifies each mode includes the required “output contract” markers
       - verifies deliverables-manifest injection stays bounded (preview limit)

3) **Output parsers**
   - New package: `src/autopack/llm/parsers/anthropic/`
     - `full_file.py` (JSON repair + diff generation integration points)
     - `ndjson.py`
     - `structured_edit.py`
     - `legacy_diff.py` (quarantine; long-term retire if unused)
   - **Contract tests**:
     - Add: `tests/llm_parsers/test_full_file_json_repair_contract.py`
       - bare-newline JSON repair and placeholder decoding
       - bracket balancing behavior on truncation
     - Add: `tests/llm_parsers/test_ndjson_truncation_tolerance_contract.py`

4) **Diff generation helper**
   - New module: `src/autopack/patching/diff_generator.py`
   - Keep it deterministic and testable (avoid shelling out unless necessary).
   - **Contract tests**:
     - Add: `tests/patching/test_diff_generator_contract.py`

### 5.5 `src/autopack/llm_service.py` (central LLM orchestration) → internal submodules, stable facade

**What’s inside (clusters)**:
- Provider initialization + disable-provider behavior
- Model routing + fallback chain (`_resolve_client_and_model`)
- Builder + auditor execution (with escalation + usage recording)
- Deliverables manifest gate (deterministic)
- Usage persistence + “total-only” accounting
- Doctor flow (large internal subsystem)
- Quality gate integration

**Seam extraction order** (keep public `LlmService` API stable):

1) **Client resolution + provider health**
   - New module: `src/autopack/llm/client_resolution.py`
   - Move: `_resolve_client_and_model` and provider-disable policy.
   - **Contract tests**:
     - Add: `tests/llm_service/test_client_resolution_fallbacks.py` (Gemini→Anthropic→OpenAI fallbacks, GLM rejection)

2) **Usage recording**
   - New module: `src/autopack/llm/usage.py`
   - Move: `_record_usage`, `_record_usage_total_only`, `_model_to_provider`
   - **Contract tests**:
     - Add: `tests/llm_service/test_usage_recording_total_only_contract.py`

3) **Doctor subsystem**
   - New module: `src/autopack/llm/doctor.py`
   - Keep `LlmService.execute_doctor(...)` delegating into it (or similar).
   - **Contract tests**:
     - Existing doctor tests likely already cover parts; add a small “JSON-only response” contract test if not present.

4) **Builder/auditor orchestration**
   - After the above extractions, the remaining `execute_builder_phase` / `execute_auditor_review` become thin “select model → call client → record usage → integrate quality gate” methods.
   - **Contract tests**:
     - Reuse existing tests in `tests/llm_service/` and executor integration tests as the safety net.

---

## 6) PR-ready seam checklist (smallest safe cuts, in order)

This section turns Section 5 into a **do-this-next** queue. Each item is intended to fit in one PR.

### 6.1 API split: `src/autopack/main.py` → `src/autopack/api/*`

**PR-API-1: Extract deps (auth + rate limit key function)** — **IMPLEMENTED ✅**
- **Status**: Completed 2026-01-12
- **Created**: `src/autopack/api/deps.py`
- **Delegated from `main.py`**:
  - `verify_api_key`, `verify_read_access`
  - `_is_trusted_proxy`, `get_client_ip`
  - `limiter`
- **Tests added**:
  - `tests/api/test_auth_dependency_contract.py` (19 tests)
    - TESTING mode bypass ✅
    - production mode requires API key ✅
    - dev mode optional behavior preserved ✅
    - forwarded headers trusted only from trusted proxies ✅
- **Verification**:
  - `pytest -q tests/api/test_route_contract.py tests/api/test_auth_dependency_contract.py` — 45 tests pass
  - `ruff check` — clean
  - Drift checks — all pass

**PR-API-2: Extract app wiring (lifespan + middleware + exception handler)** ✅ IMPLEMENTED
- **Create**: `src/autopack/api/app.py`
- **Move**:
  - `lifespan` + startup checks (including `init_db()` guard behavior)
  - CORS wiring
  - rate limit handler wiring
  - global exception handler wiring
  - `approval_timeout_cleanup` background task
  - `create_app()` factory function
- **Keep**: `src/autopack/main.py` as thin shim importing from `api.app`
- **Add tests**:
  - **New** `tests/api/test_app_wiring_contract.py` — 15 contract tests:
    - App metadata (title, version)
    - Rate limiter attached to app.state
    - CORS disabled by default, enabled when configured
    - Auth router included (/api/auth)
    - Research router included (/research)
    - Global exception handler returns error_id
    - Production mode hides error_type
    - Development mode includes error_type
    - Run/phase ID extraction from paths
    - Lifespan skips DB init in testing
    - Lifespan starts timeout cleanup task
- **Verification**:
  - `pytest -q tests/api/test_route_contract.py tests/api/test_app_wiring_contract.py tests/api/test_auth_dependency_contract.py` — 60 tests pass
  - `ruff check` — clean
  - All docs drift checks pass (46 tests)
- **Completed**: 2026-01-12

**PR-API-3a: Extract health router** ✅ IMPLEMENTED
- **Created**: `src/autopack/api/routes/health.py`
- **Move**:
  - `read_root()` - root endpoint returning service info
  - `health_check()` - enhanced health check with DB/Qdrant/kill switches
  - `_get_database_identity()` - database identity hash helper
  - `_check_qdrant_connection()` - Qdrant connection check helper
- **Added tests**:
  - **New** `tests/api/test_health_router_contract.py` — 13 contract tests:
    - Root endpoint returns service info
    - Health check returns required fields
    - Health check returns healthy/degraded based on DB status
    - Qdrant status handling (disabled/connected/unhealthy/error)
    - Kill switches reported correctly
    - Database identity hash behavior (length, masking, path normalization)
- **Verification**:
  - `pytest -q tests/api/test_route_contract.py tests/api/test_health_router_contract.py` — 39 tests pass
  - All 96 API tests pass
  - `ruff check` — clean
- **Completed**: 2026-01-12

**PR-API-3b: Extract files router** ✅ IMPLEMENTED
- **Created**: `src/autopack/api/routes/files.py`
- **Move**:
  - `upload_file()` - file upload with streaming and unique filename generation
- **Added tests**:
  - **New** `tests/api/test_files_router_contract.py` — 9 contract tests:
    - Upload requires file (returns 400 if none)
    - Upload generates unique UUID-based filename
    - Upload returns relative path (never absolute for security)
    - Upload uses chunked streaming (prevents OOM)
    - Upload preserves file extension
    - Upload handles files without extension
    - Upload creates _uploads directory if needed
    - Router uses /files prefix
    - Router tagged as 'files'
- **Verification**:
  - All 105 API tests pass
  - `ruff check` — clean
- **Completed**: 2026-01-12

**PR-API-3c: Extract storage router** ✅ IMPLEMENTED
- **Created**: `src/autopack/api/routes/storage.py`
- **Move**:
  - `trigger_storage_scan()` - POST /storage/scan
  - `list_storage_scans()` - GET /storage/scans
  - `get_storage_scan_detail()` - GET /storage/scans/{scan_id}
  - `approve_cleanup_candidates()` - POST /storage/scans/{scan_id}/approve
  - `execute_approved_cleanup()` - POST /storage/scans/{scan_id}/execute
  - `get_steam_games()` - GET /storage/steam/games
  - `analyze_approval_patterns()` - POST /storage/patterns/analyze
  - `get_learned_rules()` - GET /storage/learned-rules
  - `approve_learned_rule()` - POST /storage/learned-rules/{rule_id}/approve
  - `get_storage_recommendations()` - GET /storage/recommendations
- **Added tests**:
  - **New** `tests/api/test_storage_router_contract.py` — 17 contract tests:
    - Router uses /storage prefix
    - Router tagged as 'storage'
    - Scan rejects invalid scan_type (400)
    - Scan accepts 'directory' type
    - Scan accepts 'drive' type
    - List scans enforces max limit (200)
    - List scans passes filter parameters
    - Scan detail returns 404 for missing
    - Approve returns 404 for missing scan
    - Approve rejects invalid decision (400)
    - Approve accepts valid decisions (approve/reject/defer)
    - Execute returns 404 for missing scan
    - Steam games returns proper response when unavailable
    - Patterns endpoint returns list
    - Learned rules filters by status
    - Approve rule calls analyzer
    - Recommendations returns structured response
- **Verification**:
  - All 122 API tests pass
  - `ruff check` — clean
  - Removed ~640 lines from main.py
- **Completed**: 2026-01-12

**PR-API-3d: Extract dashboard router** ✅ IMPLEMENTED
- **Created**: `src/autopack/api/routes/dashboard.py`
- **Move**:
  - `get_dashboard_run_status()` - GET /dashboard/runs/{run_id}/status
  - `get_dashboard_usage()` - GET /dashboard/usage
  - `get_dashboard_models()` - GET /dashboard/models
  - `add_dashboard_human_note()` - POST /dashboard/human-notes
  - `get_run_token_efficiency()` - GET /dashboard/runs/{run_id}/token-efficiency
  - `get_run_phase6_stats()` - GET /dashboard/runs/{run_id}/phase6-stats
  - `get_dashboard_consolidated_metrics()` - GET /dashboard/runs/{run_id}/consolidated-metrics
  - `add_dashboard_model_override()` - POST /dashboard/models/override
- **Added tests**:
  - **New** `tests/api/test_dashboard_router_contract.py` — 15 contract tests:
    - Router uses /dashboard prefix
    - Router tagged as 'dashboard'
    - Run status returns 404 for missing run
    - Run status calculates token utilization percentage
    - Usage returns empty lists when no events
    - Usage accepts valid periods (day/week/month)
    - Models endpoint returns list
    - Human notes endpoint returns success message
    - Token efficiency returns 404 for missing run
    - Phase6 stats returns 404 for missing run
    - Consolidated metrics requires kill switch
    - Consolidated metrics validates pagination
    - Model override accepts global scope
    - Model override accepts run scope
    - Model override rejects invalid scope
- **Verification**:
  - All 137 API tests pass
  - `ruff check` — clean
  - Removed ~440 lines from main.py
- **Completed**: 2026-01-12

**PR-API-3e: Extract governance router** ✅ IMPLEMENTED
- **Created**: `src/autopack/api/routes/governance.py`
- **Move**:
  - `get_pending_governance_requests()` - GET /governance/pending
  - `approve_governance_request()` - POST /governance/approve/{request_id}
- **Added tests**:
  - **New** `tests/api/test_governance_router_contract.py` — 10 contract tests:
    - Router uses /governance prefix
    - Router tagged as 'governance'
    - Pending returns count and list
    - Pending returns serialized request objects
    - Pending returns 500 on internal error
    - Approve returns approved status
    - Deny returns denied status
    - Approve returns 404 for missing request
    - Approve returns 500 on internal error
    - Approve defaults to 'human' user_id
- **Verification**:
  - All 147 API tests pass
  - `ruff check` — clean
  - Removed ~65 lines from main.py
- **Completed**: 2026-01-12

**PR-API-3f: Extract approvals router** ✅ IMPLEMENTED
- **Created**: `src/autopack/api/routes/approvals.py`
- **Move**:
  - `request_approval()` - POST /approval/request
  - `_handle_pr_callback()` - Helper for PR approval callbacks
  - `_handle_storage_callback()` - Helper for storage optimizer callbacks
  - `telegram_webhook()` - POST /telegram/webhook
  - `get_approval_status()` - GET /approval/status/{approval_id}
  - `get_pending_approvals()` - GET /approval/pending
- **Added tests**:
  - **New** `tests/api/test_approvals_router_contract.py` — 10 contract tests:
    - Router tagged as 'approvals'
    - Request approval returns pending status
    - Request approval returns 500 on error
    - Approval status returns 404 for missing
    - Approval status returns expected fields
    - Pending approvals returns count and list
    - Pending approvals returns 500 on error
    - Webhook returns ok without callback_query
    - Webhook returns ok without callback data
    - Webhook rejects without secret in production
- **Verification**:
  - All 157 API tests pass
  - `ruff check` — clean
  - Removed ~550 lines from main.py
- **Completed**: 2026-01-12

**PR-API-3g: Extract artifacts router** ✅ IMPLEMENTED
- **Created**: `src/autopack/api/routes/artifacts.py`
- **Move**:
  - `get_artifacts_index()` - GET /runs/{run_id}/artifacts/index
  - `get_artifact_file()` - GET /runs/{run_id}/artifacts/file
  - `get_browser_artifacts()` - GET /runs/{run_id}/browser/artifacts
- **Added tests**:
  - **New** `tests/api/test_artifacts_router_contract.py` — 10 contract tests:
    - Router tagged as 'artifacts'
    - Artifacts index returns 404 for missing run
    - Artifacts index returns expected fields
    - Artifact file rejects path traversal
    - Artifact file rejects absolute paths
    - Artifact file rejects Windows drive letters
    - Artifact file returns 404 for missing run
    - Artifact file returns 404 for missing file
    - Browser artifacts returns 404 for missing run
    - Browser artifacts returns expected fields
- **Verification**:
  - All 167 API tests pass
  - `ruff check` — clean
  - Removed ~184 lines from main.py (now ~957 lines)
  - Updated existing `tests/api/test_artifacts.py` mock paths
- **Completed**: 2026-01-12

**PR-API-3h: Extract phases router** ✅ IMPLEMENTED
- **Created**: `src/autopack/api/routes/phases.py`
- **Move**:
  - `update_phase_status()` - POST /runs/{run_id}/phases/{phase_id}/update_status
  - `record_phase_issue()` - POST /runs/{run_id}/phases/{phase_id}/record_issue
  - `submit_builder_result()` - POST /runs/{run_id}/phases/{phase_id}/builder_result
  - `submit_auditor_result()` - POST /runs/{run_id}/phases/{phase_id}/auditor_result
- **Added tests**:
  - **New** `tests/api/test_phases_router_contract.py` — 10 contract tests:
    - Router tagged as 'phases'
    - Update status returns 404 for missing phase
    - Update status rejects invalid state
    - Record issue returns 404 for missing phase
    - Record issue returns 404 for missing tier
    - Builder result returns 404 for missing phase
    - Builder result updates phase tokens
    - Auditor result rejects mismatched IDs
    - Auditor result returns 404 for missing phase
    - Auditor result returns success message
- **Verification**:
  - All 177 API tests pass
  - `ruff check` — clean
  - Removed ~410 lines from main.py (now ~547 lines)
- **Completed**: 2026-01-12

**PR-API-3i: Extract runs router** ✅ IMPLEMENTED
- **Created**: `src/autopack/api/routes/runs.py`
- **Move**:
  - `start_run()` - POST /runs/start
  - `get_run()` - GET /runs/{run_id}
  - `get_run_issue_index()` - GET /runs/{run_id}/issues/index
  - `get_project_backlog()` - GET /project/issues/backlog
  - `get_run_errors()` - GET /runs/{run_id}/errors
  - `get_run_error_summary()` - GET /runs/{run_id}/errors/summary
  - `list_runs()` - GET /runs
  - `get_run_progress()` - GET /runs/{run_id}/progress
- **Added tests**:
  - **New** `tests/api/test_runs_router_contract.py` — 13 contract tests:
    - Router tagged as 'runs'
    - Get run returns 404 for missing run
    - Get run returns run object when found
    - Issue index returns dict
    - Backlog returns dict
    - Errors returns dict with run_id
    - Error summary returns dict with run_id
    - List runs returns pagination fields
    - List runs clamps limit to [1, 100]
    - Progress returns 404 for missing run
    - Progress returns expected fields
    - Start run rejects duplicate run_id
    - Start run rejects invalid tier reference
- **Verification**:
  - All 190 API tests pass
  - `ruff check` — clean
  - Removed ~360 lines from main.py (now ~165 lines)
- **Completed**: 2026-01-12

**PR-API-3 COMPLETE** — All API routes extracted to `src/autopack/api/routes/`
- main.py reduced from ~3,343 lines to ~165 lines
- 9 domain routers created with 106 contract tests
- All route shapes preserved (test_route_contract.py passing)

**PR #132 (refactor/api-router-split-20260112)** ✅ MERGED
- **Merged**: 2026-01-12
- **Impact**: Consolidated all API router refactoring work (PR-API-1, PR-API-2, PR-API-3a-3i)
- **Baseline Update**: CodeQL findings reduced from 57 to 31 (-46% improvement)
- **Verification**: All required CI checks passed

### 6.2 Executor shrink: `src/autopack/autonomous_executor.py`

**PR-EXE-1: Supervisor API client** ✅ COMPLETE
- **Part 1 - PR #141** ✅ MERGED (2026-01-12)
  - **Created**: `src/autopack/supervisor/api_client.py`
    - Pure HTTP wrapper with 9 typed methods: `check_health()`, `get_run()`, `update_phase_status()`, `submit_builder_result()`, `submit_auditor_result()`, `request_approval()`, `poll_approval_status()`, `request_clarification()`, `poll_clarification_status()`
    - Typed exceptions: `SupervisorApiTimeoutError`, `SupervisorApiNetworkError`, `SupervisorApiHttpError`
    - API key support via `X-API-Key` header
    - Configurable timeouts (default 10s)
  - **Added tests**:
    - **New** `tests/unit/test_supervisor_api_client_contract.py` — 28 contract tests
    - **New** `tests/unit/test_executor_http_enforcement.py` — BUILD-135 enforcement (Phase 1: excludes autonomous_executor.py)
  - **Verification**: All 28 client contract tests pass

- **Part 2 - PR #142** ✅ MERGED (2026-01-12)
  - **Migrated**: `src/autopack/autonomous_executor.py` to use SupervisorApiClient
  - **Replaced**: All 15 raw `requests.*` calls with typed client methods
  - **Updated**: Error handling to use typed exceptions
  - **Impact**: -58 lines (net reduction: 127 insertions, 185 deletions)
  - **Verification**: All Core Tests pass, lint clean (after Black formatting)

**BUILD-135 Status**: Phase 1 complete (executor package clean, autonomous_executor.py migrated)
**Next**: Phase 2 - Update enforcement test to include autonomous_executor.py

**PR-EXE-2: Approval flow consolidation**
- **Create**: `src/autopack/executor/approval_flow.py`
- **Move**:
  - `_request_human_approval`
  - `_request_build113_approval`
  - `_request_build113_clarification`
- **Design tweak (for testability)**:
  - inject sleep/clock function (default to `time.sleep`) so tests don’t actually wait
- **Add tests**:
  - **New** `tests/executor/test_approval_flow_timeout_behavior.py`
- **Done when**:
  - Approval logic is fully “data-in/data-out” around the API client and deterministic timeouts

**PR-EXE-3: CI runner extraction**
- **Create**: `src/autopack/executor/ci_runner.py`
- **Move**:
  - `_run_ci_checks`, `_run_custom_ci_command`
  - `_parse_pytest_counts`
  - `_persist_ci_log`, `_trim_ci_output`
- **Add tests**:
  - **New** `tests/executor/test_ci_output_parsing_contract.py` (table-driven)
- **Done when**:
  - CI failure parsing does not drift as pytest output changes

**PR-EXE-4: Run checkpoint + rollback**
- **Create**: `src/autopack/executor/run_checkpoint.py`
- **Move**:
  - checkpoint create/rollback/audit log writing
  - consolidate subprocess git calls (optionally through `git_adapter.py`)
- **Add tests**:
  - **New** `tests/unit/test_run_checkpoint_git_commands.py` (subprocess mocked)

**PR-EXE-5: Context preflight and injection**
- **Create**:
  - `src/autopack/executor/context_preflight.py`
  - `src/autopack/executor/retrieval_injection.py`
- **Move**:
  - large-file bucket logic and “read-only context” decisioning
  - SOT retrieval gating + telemetry recording wrapper
- **Add tests**:
  - **New** `tests/executor/test_context_preflight_policy.py`

**PR-EXE-6: Extract heuristic context loader**
- **Create**: `src/autopack/executor/context_loading_heuristic.py`
- **Move** `_load_repository_context_heuristic` out of `autonomous_executor.py`
- **Add tests**:
  - **New** `tests/executor/test_context_loading_heuristic_determinism.py`

**PR-EXE-7: Delete/relocate dead blocks**
- **Goal**: remove “obsolete code below” chunks from runtime source
- **Approach**: move to `archive/` (if you want to preserve) or delete
- **No new tests required** beyond existing suite; this is churn reduction.

### 6.3 Governed apply micro-kernel split: `src/autopack/governed_apply.py`

**PR-APPLY-1: Extract patch sanitize helpers**
- **Create**: `src/autopack/patching/patch_sanitize.py`
- **Move**: sanitize + repair helpers
- **Add tests**:
  - **New** `tests/patching/test_patch_sanitize_contract.py`

**PR-APPLY-2: Extract patch policy object**
- **Create**: `src/autopack/patching/policy.py`
- **Refactor**: `GovernedApplyPath` uses `PatchPolicy.validate_paths(...)`
- **Add tests**:
  - Extend existing governed apply tests (do not rewrite)

**PR-APPLY-3: Extract patch quality validation**
- **Create**: `src/autopack/patching/patch_quality.py`
- **Add tests**:
  - **New** `tests/patching/test_patch_quality_contract.py`

**PR-APPLY-4: Extract apply engine**
- **Create**: `src/autopack/patching/apply_engine.py`
- **Add tests**:
  - **New** `tests/patching/test_apply_engine_no_side_effects_on_failure.py`

### 6.4 Anthropic client split: `src/autopack/anthropic_clients.py`

**PR-LLM-1: Transport wrapper**
- **Create**: `src/autopack/llm/providers/anthropic_transport.py`
- **Add tests**:
  - **New** `tests/llm_providers/test_anthropic_transport_contract.py`

**PR-LLM-2: Prompt builders**
- **Create**: `src/autopack/llm/prompts/anthropic_builder_prompts.py`
- **Add tests**:
  - **New** `tests/llm_prompts/test_anthropic_prompt_modes_contract.py`

**PR-LLM-3: Parser package split**
- **Create**: `src/autopack/llm/parsers/anthropic/*`
- **Add tests**:
  - **New** `tests/llm_parsers/test_full_file_json_repair_contract.py`
  - **New** `tests/llm_parsers/test_ndjson_truncation_tolerance_contract.py`

**PR-LLM-4: Diff generator helper**
- **Create**: `src/autopack/patching/diff_generator.py`
- **Add tests**:
  - **New** `tests/patching/test_diff_generator_contract.py`

### 6.5 LlmService split: `src/autopack/llm_service.py`

**PR-SVC-1: Client resolution**
- **Create**: `src/autopack/llm/client_resolution.py`
- **Add tests**:
  - **New** `tests/llm_service/test_client_resolution_fallbacks.py`

**PR-SVC-2: Usage recording module**
- **Create**: `src/autopack/llm/usage.py`
- **Add tests**:
  - **New** `tests/llm_service/test_usage_recording_total_only_contract.py`

**PR-SVC-3: Doctor extraction**
- **Create**: `src/autopack/llm/doctor.py`
- **Add tests**:
  - Add/extend a “JSON-only response” contract test (small, targeted)

---

## 7) “Gap reappearance” prevention rules (what to enforce as you refactor)

These rules are the “why” behind the seam map; they keep future refactors from reintroducing drift:

- **Routes never disappear silently**: keep `tests/api/test_route_contract.py` strict (update the minimum deliberately).
- **Special phase dispatch stays registry-based**: keep `tests/unit/test_executor_phase_dispatch_contract.py` as a blocker.
- **Executor never talks raw HTTP**: enforce that `autonomous_executor.py` only uses `SupervisorApiClient` (one grep-based test can enforce this if desired).
- **No dead logic in runtime files**: avoid “obsolete code below” blocks in `src/` (keep history in `archive/` instead).



