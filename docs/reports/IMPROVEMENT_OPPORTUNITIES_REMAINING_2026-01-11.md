# Autopack — Remaining Improvement Opportunities (Delta vs `main`) — 2026-01-11

**Scope**: What is *still* worth improving vs the `README.md` “ideal state” (**safe, deterministic, mechanically enforceable**) **after** the recent PR streak visible in `git log` (PR-02..PR-07).

This file is intentionally a **delta** that de-duplicates the existing comprehensive scans/backlogs.

## 0) Canonical sources (do not duplicate)

- **Primary backlog (P0–P3)**: `docs/IMPROVEMENTS_GAP_ANALYSIS.md`
- **Single-pane scan**: `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`
- **Full audit snapshot**: `docs/reports/IMPROVEMENT_AUDIT_FULL_2026-01-11.md`
- **Opportunities index + mechanical scan**: `docs/reports/IMPROVEMENT_OPPORTUNITIES_COMPREHENSIVE_2026-01-11.md`
- **North-star navigation**: `README.md`, `docs/INDEX.md`, SOT ledgers

This document only lists **remaining, still-real** gaps and a **recommended next PR stack**.

## 1) Items already closed (verify against code/CI)

These were prominent in audits but are now **implemented** on `main`:

- **Health checks correctness**:
  - `src/autopack/health_checks.py` now requires **at least one** provider key (not all).
  - DB check is backend-aware (socket probe for Postgres, file check for SQLite).
- **Rate limiting behind proxies**:
  - `src/autopack/main.py` uses `Limiter(key_func=get_client_ip)` with trusted-proxy checks (PR-06 posture).
- **CI ↔ compose parity (Postgres tag)**:
  - `.github/workflows/ci.yml` pins the Postgres service to `postgres:15.10-alpine`, matching `docker-compose.yml`.
- **SOT “copy/paste trap” containment in FUTURE_PLAN**:
  - `docs/FUTURE_PLAN.md` currently scopes legacy `src/backend/...` as “FileOrganizer repo, NOT Autopack” (already contained).
- **Frontend production sourcemap posture**:
  - `frontend-ci` job enforces “no `*.map` in production build” (PR-07).

## 2) Remaining improvement areas (comprehensive, de-duplicated)

### 2.1 ~~Determinism gap: Qdrant autostart uses `qdrant/qdrant:latest`~~ — **CLOSED**

**Status**: Implemented in PR-111 (2026-01-11).

**What was done**:
- Added `image: "qdrant/qdrant:v1.12.5"` to `config/memory.yaml` as the single config source.
- Updated `src/autopack/health_checks.py` and `src/autopack/memory/memory_service.py` to read from config (with `AUTOPACK_QDRANT_IMAGE` env override).
- Added CI guardrail: `scripts/ci/check_no_qdrant_latest_in_autostart.py` prevents `qdrant/qdrant:latest` in autostart code paths.
- Added unit tests: `tests/ci/test_no_qdrant_latest_in_autostart.py`.

### 2.2 Lint "paper-over" debt in critical runtime (P1) — **PARTIALLY CLOSED**

**Status**: Partially addressed in PR-112 (2026-01-11).

**What was done**:
- Removed stale `F821` ignore from `src/autopack/main.py` (verified clean).
- Added missing `Tuple` import to `src/autopack/anthropic_clients.py`.
- Updated comments in `pyproject.toml` to document remaining real issues.

**Remaining** (genuine issues that need code fixes):
- `src/autopack/autonomous_executor.py`: `F821` — references `Phase` without import in some code paths.
- `src/autopack/anthropic_clients.py`: `F821`, `F823` — references `GovernedApplyPath`, `batches` without proper scope/import.

**Next steps**: Fix the underlying import/scope issues in these files before removing ignores.

### 2.3 Maintainability risk: "god files" still dominate core surfaces (P1/P2) — **CONTRACT TEST ADDED**

**Status**: Safety net added in PR-113 (2026-01-11).

**What was done**:
- Created `src/autopack/api/__init__.py` API package structure.
- Added `tests/api/test_route_contract.py` with route shape contract tests:
  - Asserts minimum 44 routes exist.
  - Validates required route patterns are present.
  - Uses OpenAPI spec for mechanical verification.

**Remaining** (refactoring can now proceed safely):
- Split `main.py` into routers (`api/routes/*`).
- Extract executor phase handlers, context loading, retry policy.
- Provider client seam extractions.

The contract test prevents route-shape drift during future refactoring.

### 2.4 ~~Canonical-doc checker has a "fenced code" blind spot~~ — **CLOSED**

**Status**: Implemented in PR-114 (2026-01-11).

**What was done**:
- Added fenced-code-block state machine to `scripts/ci/check_canonical_doc_refs.py`:
  - Tracks `in_fence` and `fence_is_historical` state.
  - Skips fenced blocks that have a `HISTORICAL` marker in the 3 lines before the fence.
  - Scans fenced blocks without historical markers (strict policy).
- Added `_has_historical_marker_before()` helper function.
- Added 7 new tests in `tests/ci/test_canonical_doc_refs.py` for fenced code handling.

### 2.5 ~~Windows-first DX remains partially "documentation only"~~ — **CLOSED**

**Status**: Implemented in PR-116 (2026-01-11).

**What was done**:
- Created `scripts/tasks.ps1` PowerShell task runner with:
  - `help`, `install`, `lint`, `format`, `test` tasks.
  - `docker-up`, `docker-down`, `docker-logs` tasks.
  - `clean` task for removing generated files.
- Updated `docs/CONTRIBUTING.md` with Task Runners section documenting both PowerShell and Makefile paths.
- Both paths are now first-class, documented equivalents.

### 2.6 Rate limiting key strategy is still IP-based (policy decision) (P2)

**Current state**: proxy-safe IP extraction exists.

**Remaining decision**: should rate limiting key on:
- **principal** (API key / JWT subject), or
- **client IP** (current)?

**Why it matters**: operator APIs are often better protected by principal-based limits to avoid penalizing users behind NAT/proxies.

**Recommended fix shape**:
- Document the chosen keying strategy in `docs/DEPLOYMENT.md`.
- If switching to principal-based: implement `key_func` fallback order (principal → IP).

### 2.7 Import-time DB binding footgun (P2/P3)

**Risk**: if `src/autopack/database.py` binds engine/session at import time, tests and subprocesses can become order-dependent.

**Recommended fix shape**:
- Either document “DB URL is bound at import” everywhere it matters, or
- Refactor to lazy `get_engine()` / `get_sessionmaker()` getters and add a small test proving env overrides work before first use.

### 2.10 Repo hygiene: tracked run-local / tool-working-set artifacts (P2)

**Evidence (tracked files)**:
- `.autonomous_runs/file-organizer-app-v1/.gitignore` is tracked.
- `.autopack/**` contains a substantial set of handoff notes, calibration outputs, and telemetry archives and is tracked.

**Why it matters** (README ideal state):
- Run-local execution output should stay run-local; once tracked, it becomes another long-lived “truth surface” that can drift and confuse operators/reviewers.
- Hidden dot-directories can quietly accumulate “second truth” docs that bypass the normal docs/SOT discipline.

**Recommended fix shape**:
- Decide and document a policy:
  - either treat `.autopack/` as a first-class, documented repo surface (with strict rules + a small CI check), or
  - move these artifacts into `archive/` (historical) or `docs/reports/` (curated), and stop tracking tool/run outputs.
- Consider a tiny CI guardrail (future PR) like:
  - tracked `.autonomous_runs/**` is only allowed for `.autonomous_runs/.gitignore` (and nothing project-specific),
  - tracked `.autopack/**` must be allowlisted or forbidden entirely.

### 2.11 Portability + “two truths” risk: hardcoded `.autonomous_runs/file-organizer-app-v1` paths in runtime code (P1/P2)

**Evidence** (examples found in `src/`):
- `src/autopack/memory/faiss_store.py`: default `index_dir` points at `.autonomous_runs/file-organizer-app-v1/.faiss`
- `src/autopack/memory/memory_service.py`: multiple references to `.autonomous_runs/file-organizer-app-v1/.faiss`
- `src/autopack/research/preflight_analyzer.py`: CLI examples reference `.autonomous_runs/file-organizer-app-v1/...`
- `src/autopack/migrations/add_tidy_project_config.sql`: inserts/mentions `.autonomous_runs/file-organizer-app-v1`

**Why it matters**:
- Autopack is a framework repo; baking in a single downstream project slug creates accidental coupling, breaks portability, and increases the chance of writing artifacts into the wrong run directory.
- This also drives repo hygiene problems (tracked `.autonomous_runs/file-organizer-app-v1/.gitignore`) and makes “run-local only” enforcement harder.

**Recommended fix shape**:
- Introduce a single canonical project slug source (e.g., `AUTOPACK_PROJECT_SLUG` with a sensible default like `autopack`/`autopack-framework`) in `src/autopack/config.py`.
- Replace all hardcoded `file-organizer-app-v1` path usage with `project_slug`-derived paths.
- Update migrations/seed data to avoid embedding a concrete project slug in SQL; store relative paths or compute at runtime.

**Mechanical enforcement**:
- Add a small CI check (future PR) that fails if the literal string `file-organizer-app-v1` appears in `src/` (except under `archive/`), to prevent reintroducing the coupling.

### 2.12 Repo hygiene: tracked tool configuration surface (`.claude/`) (P3)

**Evidence (tracked files)**:
- `.claude/commands/tidy.md`
- `.claude/settings.json`
- `.claude/workflows.json`

**Why it matters**:
- Tooling config can be legitimate, but it’s also a “second truth” surface that can drift across developers/tools and silently change behavior.

**Recommended fix shape**:
- Decide policy explicitly:
  - either keep `.claude/` as an intentional, documented repo surface (document in `docs/CONTRIBUTING.md` + keep it minimal), or
  - move it under `archive/` and treat it as historical, or
  - gate it with a small CI allowlist (only specific files allowed; no secrets; no auto-generated dumps).

### 2.13 Supply-chain posture: inconsistent GitHub Actions pinning (P2)

**Evidence**:
- `.github/workflows/ci.yml` uses tag-based actions in some jobs (e.g., `actions/checkout@v4`, `actions/setup-python@v5`) while other jobs pin by full commit SHA.

**Why it matters**:
- Tag-based action references are a moving target; SHA pinning is more mechanically enforceable and aligns with the project’s “deterministic + supply-chain safe” ideal state.

**Recommended fix shape**:
- Align to one posture across workflows:
  - prefer SHA pinning everywhere (including `actions/*`) unless there is an explicitly documented exception.
- Tighten `scripts/ci/check_github_actions_pinning.py` allowlist over time so tags don’t silently creep back in.

### 2.14 Portability: hardcoded `.autonomous_runs/file-organizer-app-v1` in tooling/scripts/docs (P2)

**Evidence**:
- The literal `.autonomous_runs/file-organizer-app-v1` appears widely outside `src/` as well (in various `scripts/` helpers and some docs/reports).

**Why it matters**:
- Even if runtime is fixed (2.11), hardcoded slugs in tooling perpetuate the same coupling and make it easy for contributors to “do the wrong thing” (generate artifacts in the wrong run directory, copy/paste incorrect commands, etc.).

**Recommended fix shape**:
- Standardize on a single project slug resolution method for scripts too:
  - `AUTOPACK_PROJECT_SLUG` (env) and/or a small `scripts/_project_slug.py` helper shared across scripts.
- Update docs/examples to use a placeholder slug (e.g., `<project-slug>`) or the canonical default (e.g., `autopack-framework`) unless the document is explicitly historical.

### 2.15 Ops safety: local prod override compose file is recommended but not ignored (P1/P2)

**Evidence**:
- `docs/DEPLOYMENT.md` recommends creating a local `docker-compose.prod.yml` via:
  - `cp docker-compose.prod.example.yml docker-compose.prod.yml`
- `.gitignore` does not currently ignore `docker-compose.prod.yml`.

**Why it matters**:
- This file is exactly where production secrets/overrides tend to land. Without an ignore rule, it’s easy to accidentally commit it.
- The new “canonical compose variants” guardrail will block a *tracked* `docker-compose.prod.yml`, but it won’t stop someone from staging it before noticing (or from leaking content in other ways).

**Recommended fix shape**:
- Add `docker-compose.prod.yml` to `.gitignore`.
- Keep the CI guardrail that fails if any `docker-compose*.yml` outside `archive/` is tracked unless it’s one of the canonical allowlist files.

### 2.16 Configuration template drift: `.env.example` contradicts current runtime posture (P2)

**Evidence**:
- `.env.example` describes `GLM_API_KEY` as a runtime key (“used for low-complexity tasks”), which conflicts with the current “GLM tooling-only / runtime disabled” posture tracked in section 6.
- `.env.example` and `src/autopack/notifications/telegram_notifier.py` use `AUTOPACK_CALLBACK_URL` defaulting to `http://localhost:8001`.

**Why it matters**:
- Operator-facing templates are “soft policy.” If they contradict runtime truth, they create “it depends” failures and violate the “one truth” ideal state.

**Recommended fix shape**:
- Make `.env.example` match the decided GLM posture (Option A vs Option B in section 6).
- Document what `AUTOPACK_CALLBACK_URL` should be in common deployments (direct `:8000` vs nginx `:80`) and align defaults accordingly.

### 2.17 Documentation drift: non-canonical docs still recommend `:latest` and unpinned CI topology (P2)

**Evidence**:
- `docs/BUILD-163_CI_COVERAGE.md` contains examples using:
  - `qdrant/qdrant:latest`
  - `postgres:15` (not patch-pinned)
  - older action tags (e.g., `actions/checkout@v3`, `actions/setup-python@v4`)

**Why it matters**:
- Even if this doc is “historical,” it lives under `docs/` and can be copy/pasted by operators, reintroducing non-determinism and supply-chain drift.

**Recommended fix shape**:
- Either:
  - move it under `archive/` (explicitly historical), or
  - update the examples to match canonical current policy (pin versions; avoid `:latest`; prefer SHA-pinned actions), and add “HISTORICAL” markings where needed.

### 2.8 Mechanical guardrail: compose + TS/Vite config drift (P1)

**What can drift**:
- Extra `docker-compose*.yml` variants (often created for prod and can accidentally carry secrets).
- Extra `tsconfig*.json` or `vite.config.*` committed under subfolders (accidental “second frontend”).

**Guardrail implemented (pending PR)**:
- `scripts/ci/check_canonical_build_surfaces.py` now enforces:
  - `docker-compose*.yml` outside `archive/` must be one of:
    - `docker-compose.yml`
    - `docker-compose.dev.yml`
    - `docker-compose.prod.example.yml`
  - Any `tsconfig*.json` / `vite.config.*` outside `archive/` must live at **repo root** only.
- Covered by `tests/ci/test_canonical_build_surfaces.py` and runs in CI `lint` job.

**Why it matters**: it prevents a repeat of “two truths” frontend/build surfaces and reduces accidental secret-bearing compose files landing in the repo.

### 2.9 ~~Derived "consolidated" journals: clarify as non-SOT + prevent confusion~~ — **CLOSED**

**Status**: Implemented in PR-115 (2026-01-11).

**What was done**:
- Created `scripts/ci/check_no_tracked_docs_consolidated_md.py` CI guardrail:
  - Blocks tracked `docs/**/CONSOLIDATED_*.md` files.
  - Uses `git ls-files` for tracked-files-only checking.
  - Allows `archive/` paths (explicitly historical).
- Created `tests/ci/test_no_tracked_docs_consolidated_md.py` with parametrized path classification tests.
- Moved `docs/CONSOLIDATED_DEBUG.md` to `archive/docs/CONSOLIDATED_DEBUG.md` (historical redirect stub).
- Added CI step in `.github/workflows/ci.yml`.

**Remaining** (policy clarification):
- Document that `ArchiveConsolidator` should only write to run-local paths (`.autonomous_runs/.../archive/`), never to `docs/`.
- The CI guardrail now mechanically enforces this boundary.

## 3) Recommended next PR stack (high ROI, low churn order) — **COMPLETED**

All 6 PRs in this stack have been implemented (2026-01-11):

1. ~~**Determinism**: remove `qdrant/qdrant:latest` from autostart fallbacks~~ — PR-111 ✓
2. ~~**Lint-hardening**: reduce/retire `F821/F823` per-file ignores~~ — PR-112 (partial) ✓
3. ~~**Maintainability**: add contract tests for route shape~~ — PR-113 ✓
4. ~~**Mechanical enforcement accuracy**: fix canonical-doc checker fenced-block policy~~ — PR-114 ✓
5. ~~**Docs "second truth" prevention**: add `CONSOLIDATED_*.md` guardrail~~ — PR-115 ✓
6. ~~**Windows DX**: add PowerShell task runner~~ — PR-116 ✓

### Next recommended work (remaining items from section 2)

1. **Fix F821/F823 root causes** (2.2): Fix import/scope issues in `autonomous_executor.py` and `anthropic_clients.py`.
2. **Complete main.py refactor** (2.3): Split into routers now that contract tests are in place.
3. **Rate limiting keying strategy** (2.6): Document decision (principal vs IP).
4. **DB binding footgun** (2.7): Refactor to lazy getters or document import-time binding.
5. **Hardcoded project slug** (2.11, 2.14): Introduce `AUTOPACK_PROJECT_SLUG` and eliminate `file-organizer-app-v1`.
6. **Repo hygiene** (2.10, 2.12): Policy decisions for `.autopack/` and `.claude/` surfaces.

---

If you say **“continue”**, I’ll extend this delta with:
- a seam map for `autonomous_executor.py` (lowest-risk extractions first),
- a concrete plan to eliminate each current Ruff ignore with minimal behavior changes,
- a quick scan of “runtime autostart / self-heal” code paths for other non-deterministic defaults.

## 4) Seam maps (low-risk extraction plan; preserve behavior first)

This section is deliberately “seams-first”: extract pure helpers + routers with **no behavior change**, add contract tests, then shrink the source file.

### 4.1 `src/autopack/main.py` (~3343 LOC, ~36 route decorators)

**Current shape**: one file mixes:
- app lifecycle + middleware,
- auth dependencies (`verify_api_key`, `verify_read_access`),
- rate limiting (`get_client_ip`),
- many endpoint families (runs, phases, artifacts, approvals/telegram, governance, dashboard, auth, etc.).

**Low-risk seam plan** (thin wrappers first):

1. **Create an API package**:
   - `src/autopack/api/app.py`: creates `FastAPI()` and wires middleware/limiter/lifespan
   - `src/autopack/api/deps.py`: auth deps + DB deps
   - `src/autopack/api/routes/*.py`: routers per domain (see below)

2. **Move endpoint blocks into routers** (no route path changes):
   - `routes/runs.py`: `/runs/*`
   - `routes/phases.py`: `/runs/{run_id}/phases/*`
   - `routes/artifacts.py`: `/runs/{run_id}/artifacts/*` and any browser-facing artifact endpoints
   - `routes/approvals.py`: `/approval/*` + `/telegram/*`
   - `routes/governance.py`: `/governance/*`
   - `routes/dashboard.py`: `/dashboard/*`
   - `routes/auth.py`: `/api/auth/*`
   - `routes/health.py`: `/health`, `/nginx-health`, etc.

3. **Keep `src/autopack/main.py` as a compatibility shim** (first PR):
   - `from autopack.api.app import app`
   - no import side-effects beyond that

**Mechanical safety net (contract tests)**:
- Add a “route shape contract” test that asserts the exported OpenAPI has a stable set of paths.
  - CI already generates `openapi.json` as an artifact; a unit test can load `autopack.main.app.openapi()` and assert:
    - key routes exist (high-signal allowlist), and/or
    - total path count doesn’t unexpectedly drop.

### 4.2 `src/autopack/autonomous_executor.py` (~11585 LOC)

**Highest-signal seams visible in-file**:

#### Seam A — Special-cased phase handlers registry

Evidence: `_execute_phase_with_recovery()` has a phase-id ladder:
- `research-tracer-bullet`
- `research-gatherers-web-compilation`
- `diagnostics-handoff-bundle`
- `diagnostics-cursor-prompt`
- `diagnostics-second-opinion-triage`
- `diagnostics-deep-retrieval`
- `diagnostics-iteration-loop`

**Extraction**:
- `src/autopack/executor/phase_handlers/base.py`: `PhaseHandler` protocol + default handler
- `src/autopack/executor/phase_handlers/registry.py`: mapping `phase_id -> handler`
- Move each `_execute_*_batched()` implementation into its own module.

**Acceptance criteria**:
- Identical behavior: same phases still dispatch to the same batching logic, same status outcomes.
- Unit test: dispatch table returns expected handler for each known special phase id.

#### Seam B — Context loading engine

Evidence: `_load_repository_context()` already documents and implements a 3-mode policy:
1) scope-aware (highest priority),
2) targeted patterns (templates/frontend/docker),
3) heuristic fallback with token budget.

**Extraction**:
- `src/autopack/executor/context_loading.py`:
  - `load_repository_context(phase, workspace, ...) -> dict`
  - sub-functions: `load_scoped_context`, `load_targeted_frontend`, `load_targeted_docker`, etc.

**Acceptance criteria**:
- Scope precedence preserved (scope overrides targeted).
- Determinism: same workspace + phase yields stable loaded file list ordering (sort keys before returning).

#### Seam C — DB/session + telemetry wiring

Evidence: `__init__()` builds its own SQLAlchemy engine/session and calls `init_db()`.

**Extraction**:
- `src/autopack/executor/db.py`: `create_executor_session()` that returns a session + a tiny wrapper for “best-effort telemetry.”

**Acceptance criteria**:
- No behavior changes to schema/bootstrap guardrails (still enforced).
- Clear separation between “must-have DB” vs “best-effort telemetry DB” (if you want the executor to run without DB in some modes).

#### Seam D — Retry/escalation decisioning (pure logic)

Evidence: `execute_phase()` is a mix of:
- scope generation,
- attempt tracking,
- budget escalation lookups,
- orchestrating builder/auditor/quality gate.

**Extraction**:
- `src/autopack/executor/retry_policy.py`: pure functions:
  - choose_model(attempt_index, escalation_level, policy) -> model id
  - should_escalate(...) -> bool
  - next_attempt_state(...) -> struct

**Acceptance criteria**:
- Unit tests for attempt→model mapping (no runtime dependencies).

## 5) Ruff-ignore elimination plan (tighten enforcement)

### 5.1 Reality check: F821/F823 suppressions appear stale

Even though `pyproject.toml` lists per-file ignores for `F821/F823`, a direct lint pass scoped to those rules currently reports clean for:
- `src/autopack/main.py`
- `src/autopack/anthropic_clients.py`
- `src/autopack/autonomous_executor.py`

**Recommended PR**:
- Remove `F821/F823` from per-file ignores for these files.
- Then run `ruff check src/ tests/` in CI to confirm no regression.

### 5.2 Keep vs remove `E402` (import order)

`E402` is currently ignored for a few files due to intentional env/bootstrap ordering.

**Recommended policy**:
- Keep `E402` only where it is a true contract (e.g., dotenv must load before importing settings), but prefer refactors that eliminate it:
  - move early env/bootstrap logic into a dedicated `bootstrap.py`,
  - keep module import sections “clean”.

## 6) Provider posture: GLM is currently a “two truths” surface (P0/P1)

**Evidence of inconsistency**:
- `src/autopack/autonomous_executor.py` treats `GLM_API_KEY` as a valid runtime provider key and labels it “primary” (also exposed via CLI help).
- `src/autopack/llm_service.py` explicitly states: **“GLM support is currently disabled”** (`GLM_AVAILABLE = False`; clients are `None`).
- `src/autopack/health_checks.py` excludes GLM from runtime provider keys (“tooling-only”).
- `config/feature_flags.yaml` labels `GLM_API_KEY` as “tooling-only” and claims runtime GLM is disabled.
- `src/autopack/glm_clients.py` still implements runtime-capable GLM clients, despite the router being disabled.

**Why it matters**:
- This is exactly the kind of operator-interface ambiguity that violates “one truth” and creates non-deterministic failures (health says “unhealthy” while executor can run, or vice versa).

**Recommended fix shape** (choose one posture and make all surfaces match):
- **Option A (runtime-supported)**: include GLM in health checks + operator docs + registry as first-class.
- **Option B (tooling-only)**: gate GLM runtime usage behind an explicit feature flag default OFF, and make executor ignore GLM unless enabled.

### 6.1 Current “effective runtime truth” (as of this scan)

Given `LlmService` disables GLM, the current runtime truth is closer to:

- **Executor validates GLM key exists** (today), but
- **LLM routing does not actually use GLM** (today), and
- some error messages still mention GLM as a possible provider even though it cannot be selected (misleading).

That’s a hidden “it depends” surface and should be collapsed.

### 6.2 PR-ready resolution (recommended: tooling-only posture)

**PR-G1 — Make GLM tooling-only consistently**

- **Goal**: GLM is allowed for tidy/model-intelligence tooling, but never for runtime Builder/Auditor.
- **Code changes (shape)**:
  - `autonomous_executor.py`: remove “GLM is primary” language and stop treating `GLM_API_KEY` as satisfying “at least one runtime provider key” unless an explicit enable flag is set.
  - `llm_service.py`: remove unreachable GLM fallbacks and remove GLM from “set one of these keys” error messages if GLM is disabled.
  - `glm_clients.py`: keep for tooling only, or move under a clearly labeled tooling module tree (or guard imports behind feature flag).
- **Docs/config changes (shape)**:
  - ensure all “run autopack” docs treat GLM as tooling-only (some already do; some Cursor prompts still list it as runtime).
- **Acceptance criteria**:
  - `HealthChecker.check_api_keys()` and executor startup agree on what counts as “runtime provider configured.”
  - No runtime error message instructs setting `GLM_API_KEY` when GLM routing is disabled.
  - A small unit/contract test enforces the posture (“GLM disabled: GLM key does not satisfy runtime provider requirement”).

## 7) DB binding footgun: `database.py` binds engine at import time (P2)

**Evidence**:
- `src/autopack/database.py` creates `engine = create_engine(get_database_url(), ...)` at import time.

**Why it matters**:
- Environment-variable changes after import won’t affect the engine.
- Test isolation can become order-dependent if imports happen before env setup.

**Recommended fix shape**:
- Replace module globals with lazy getters (`get_engine()` cached, `get_sessionmaker()`), or explicitly document “binds at import” and enforce env setup in entrypoints.

## 8) “Self-heal / autostart” non-determinism quick scan (beyond Qdrant)

The key remaining “automatic runtime action” risk found in this pass is the Qdrant `:latest` fallback.

**Recommended follow-up scan targets** (fast, high ROI):
- any other `docker run ... :latest` patterns,
- any auto-download behaviors (models, tools) without pinned versions,
- any “auto-migrate / create schema” behaviors outside explicit `AUTOPACK_DB_BOOTSTRAP` gating.

## 9) Additional seam maps: provider client + governed apply (high ROI, safety-aware)

### 9.1 `src/autopack/anthropic_clients.py` (~4184 LOC)

**Role**: Provider adapter + prompt builder + output parsing + truncation recovery + telemetry.

**Low-risk seam plan**:

- **Seam A — Prompt construction**
  - Extract `*_build_system_prompt()` and `*_build_user_prompt()` into `src/autopack/llm/prompts/anthropic.py`.
  - Acceptance criteria: byte-identical prompts for the same inputs (golden tests).

- **Seam B — Output parsing**
  - Extract:
    - `_extract_diff_from_text()`
    - `_parse_full_file_output()`
    - `_parse_legacy_diff_output()`
    - `_parse_structured_edit_output()`
    - `_parse_ndjson_output()`
  - Into `src/autopack/llm/parsing/anthropic_output.py`.
  - Acceptance criteria: existing test corpus (or captured fixtures) parses to identical `BuilderResult`.

- **Seam C — Recovery systems are already distinct modules**
  - Keep `ContinuationRecovery`, `NDJSONParser/Applier`, `JsonRepairHelper` as-is; the “gap” is that orchestration lives in one file.
  - Refactor by moving orchestration helpers (e.g., “try parse once then repair”) into a `anthropic_pipeline.py` helper module.

**Why this matters**:
- shrinking the provider adapter makes it easier to remove broad lint suppressions, reason about token accounting invariants, and keep determinism.

### 9.2 `src/autopack/governed_apply.py` (~2397 LOC)

**Role**: Safety kernel for patch application. This is correctness/supply-chain critical.

**Low-risk seam plan** (keep enforcement core, extract pure helpers):

- **Seam A — Patch parsing / normalization**
  - Move pure functions like:
    - `_classify_patch_files()`
    - `_extract_files_from_patch()`
    - `_extract_new_content_from_patch()`
    - `_replace_file_content_in_patch()`
  - Into `src/autopack/patching/patch_parsing.py`.

- **Seam B — Path policy**
  - Move:
    - `PROTECTED_PATHS`, `ALLOWED_PATHS`
    - `_is_path_protected()`
    - `_validate_patch_paths()`
  - Into `src/autopack/patching/path_policy.py`.
  - Add a table-driven unit test: (path, mode) → allow/deny + reason.

- **Seam C — Content validators**
  - Extract:
    - symbol preservation + structural similarity checks,
    - merge conflict marker checks,
    - YAML truncation detection/repair (if stable).
  - Into `src/autopack/patching/validators.py`.

**Acceptance criteria**:
- `governed_apply.py` remains the orchestrator, but becomes “readable” (imports helpers; core logic shrinks).
- Existing behavior is preserved (regression tests + a few golden patches).

## 10) Additional gaps found in follow-up sweep (not previously listed)

### 10.1 “Two frontends” risk: duplicate Vite/package surfaces (P1/P2)

**Evidence**:
- Root-level frontend: `package.json` + `vite.config.ts` (this is what CI runs).
- A second frontend tree exists under `src/autopack/frontend/` with its own `package.json` + `vite.config.ts`.
- There is also at least one historical frontend `package.json` under `archive/`.

**Why it matters**:
- This is a classic “two truths” footgun: humans/agents won’t know which frontend is canonical.
- It increases the chance of security posture drift (e.g., sourcemap settings, dependencies) across two configs.

**Recommended fix shape**:
- Decide the canonical frontend root (current CI implies **repo root**).
- Either delete / archive `src/autopack/frontend/` or convert it into a clearly labeled legacy experiment (and exclude it from any docs that imply it is active).
- Add a CI guardrail: “only one active `vite.config.ts`/`package.json` for operator UI” (exclude archive/).

## 11) Canonical vs legacy build surfaces (matrix)

This is a “two truths” inventory: it lists every major build/deploy surface and whether it appears to be canonical (used by CI/compose) vs legacy/secondary.

### 11.1 Docker / Compose

- **Canonical (active)**
  - `Dockerfile` (backend; digest pinned)
  - `Dockerfile.frontend` (frontend; digest pinned; builds from repo root `package.json` + `vite.config.ts`)
  - `docker-compose.yml` (local dev topology; postgres/qdrant pinned by tag)
  - `docker-compose.prod.example.yml` (production override template; secrets via *_FILE)
  - `docker-compose.dev.yml` (dev override; reload + source mounts)
  - `nginx.conf` (frontend reverse proxy; includes `/api/auth` prefix-preservation contract)

- **Drift risks / improvements**
  - **Digest pinning in compose**: `docker-compose.yml` pins by version tag (good) but not by digest (optional “beyond README” hardening).
  - **Qdrant autostart fallback**: runtime still uses `qdrant/qdrant:latest` in fallback paths (already tracked as P0/P1).

### 11.2 Frontend (Node/Vite/TS)

- **Canonical (active)**
  - `package.json` (repo root)
  - `package-lock.json` (repo root; used by CI via `npm ci`)
  - `vite.config.ts` (repo root; aliases to `src/frontend`)
  - `tsconfig.json`, `tsconfig.node.json` (repo root; include `src/frontend`)

- **Secondary / likely legacy (needs decision)**
  - `src/autopack/frontend/package.json`
  - `src/autopack/frontend/vite.config.ts`
  - `src/autopack/frontend/tsconfig.json`, `src/autopack/frontend/tsconfig.node.json`
  - `archive/experiments/legacy-dashboard-frontend/frontend/*` (clearly legacy)

**Why this matters**:
- Two parallel frontend configs is a classic security + maintenance drift vector (deps, sourcemaps, build flags).

**Recommended hardening**:
- Keep only one active frontend surface. If `src/autopack/frontend/` is not needed:
  - move to `archive/` or delete, and
  - add a CI check blocking non-archive `src/**/vite.config.ts` and `src/**/package.json` duplicates.

### 11.3 Python dependency surfaces

- **Canonical**
  - `pyproject.toml` (declared “single source of truth”)
  - `requirements.txt`, `requirements-dev.txt` (generated for pip compatibility; CI drift checks enforce sync)

- **Potential drift risk**
  - `scripts/integrations/requirements.txt` (separate requirements surface; if used, it can become a “second truth”).
    - Current content appears to be a single line (`requests>=2.31.0`), and there are no other in-repo references found in this scan.
    - Recommendation: either delete it (if unused), or explicitly document its purpose and keep it synchronized with `pyproject.toml` (prefer folding into `project.optional-dependencies`).

### 10.2 Latent SOT-write path: `build_history_integrator` includes a “would append to BUILD_HISTORY” stub (P2)

**Evidence**:
- `src/autopack/integrations/build_history_integrator.py` has a `record_research_outcome()` method that logs “this would append to BUILD_HISTORY.md” and is currently `pass`.

**Why it matters**:
- README ideal state says **execution writes run-local only**; SOT updates happen via tidy, gated.
- A future implementation of this stub could accidentally reintroduce direct SOT writes from runtime.

**Recommended fix shape**:
- Either:
  - remove the method entirely (if unused), or
  - change it to write a **run-local artifact** (e.g., `.autonomous_runs/.../research_outcomes.json`) that tidy can consolidate later.
- Add a small “no runtime SOT writes” contract test that blocks direct writes to `docs/BUILD_HISTORY.md` from `src/` modules.

### 10.3 Legacy derived-SOT path: `.autonomous_runs/BUILD_HISTORY.md` is treated as an SOT doc candidate (P2)

**Evidence**:
- `src/autopack/artifact_loader.py` treats both `docs/BUILD_HISTORY.md` and `.autonomous_runs/BUILD_HISTORY.md` as substitutable “SOT docs.”

**Why it matters**:
- This is another “two truths” risk unless `.autonomous_runs/BUILD_HISTORY.md` is explicitly defined as a derived/legacy mirror.

**Recommended fix shape**:
- Make one canonical:
  - prefer `docs/BUILD_HISTORY.md` as canonical SOT,
  - treat any `.autonomous_runs/BUILD_HISTORY.md` as deprecated/derived and clearly label it in code/docs (or remove support).

### 10.4 Parallel run safety: worktree isolation exists, but the core executor doesn’t use it (P2)

**Evidence**:
- Worktree/parallel infrastructure exists (`workspace_manager.py`, `parallel_orchestrator.py`, supervisor).
- `src/autopack/autonomous_executor.py` does not appear to use worktree isolation directly.

**Why it matters**:
- If users run multiple executors manually in the same repo root, they can still corrupt git state / artifacts.

**Recommended fix shape**:
- Add an explicit “parallel-run guard” in the executor entrypoint:
  - refuse to run in shared workspace if a lease/lock indicates another run is active (unless a `--force`/explicit override).
  - or always require using the supervisor/orchestrator for parallel runs.
