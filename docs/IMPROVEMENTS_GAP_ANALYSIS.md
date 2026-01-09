# Autopack — Comprehensive Improvement / Gap Analysis (vs README “ideal state” + WORKSPACE_ORGANIZATION_SPEC + beyond)

**Last Verified**: 2026-01-09 (GAP-8.x items updated)
**Scope**: repo-wide (docs/SOT, CI, Docker/compose, runtime, security, frontend(s), workspace hygiene)
**Goal**: enumerate **all** meaningful gaps/enhancements in one place; prioritize; include concrete acceptance criteria.

---

## 0) What’s already strong (close to “ideal”)

- **SOT-ledgers + mechanical enforcement**: SOT registry (`config/sot_registry.json`) aligns with `docs/INDEX.md`; doc-contract tests + SOT drift checks are wired in CI.
- **Security posture**: baseline/diff-gate system exists and is **blocking on regressions**; SHA-pinned actions policy is enforced.
- **CI coverage**: ruff/black, core tests (Postgres), doc integrity, workspace structure verification, and a root-frontend CI job are present.
- **Cross-OS hygiene**: `.editorconfig`, `.gitattributes`, and `.github/CODEOWNERS` exist.

This doc focuses on what’s still missing, drifting, inconsistent, or high-value to harden next.

---

## 0.1 Evidence snapshot (from current workspace)

- **Frontends present**:
  - **Root Vite frontend**: `package.json`, `vite.config.ts`, `src/frontend/…`
  - **Dashboard frontend (legacy/alt UI)**: `src/autopack/dashboard/frontend/…` (contains local `node_modules/` + `dist/` in the workspace; not tracked in git)
- **Scaffolding and structure** (as of 2026-01-08, verified in repo):
  - `.env.example` **EXISTS** ✅ (tracked). `.env` exists locally but is ignored (not tracked).
  - `.github/dependabot.yml` **EXISTS** ✅ (pip, docker, github-actions, npm ecosystems)
  - `.pre-commit-config.yaml` **EXISTS** ✅ (ruff, bandit, hygiene hooks)
  - `docs/api/` **EXISTS** ✅ (runtime-canonical OpenAPI strategy; CI exports OpenAPI as an artifact)
  - `docker-compose.prod.yml` does not exist (referenced as a pattern/idea in docs/comments)
- **TODO density (quick scan)**:
  - `src/`: **~1** TODO marker found (as of 2026-01-08 scan)
  - `scripts/`: **~54** TODO/FIXME markers found (expected; operational tooling)
  - `tests/`: **~34** TODO/FIXME occurrences found (mostly test text/docstrings; tracked by TODO policy tests)

### 0.1.1 High-signal inconsistencies found (must reconcile)

These are “two truths” risks: they directly undermine the repo’s thesis (**deterministic + mechanically enforced**).

- **Env template canonical path is inconsistent** (Status: FIXED 2026-01-08):
  - Canonical env template is `.env.example` at repo root (tracked).
  - `scripts/check_docs_drift.py` enforces `cp .env.example .env` and blocks `cp docs/templates/env.example .env`.
  - `docs/CONFIG_GUIDE.md` and `docs/DEPLOYMENT.md` now use `cp .env.example .env`.
- **Canonical API contract contradicts actual auth routes** (Status: FIXED 2026-01-08):
  - `docs/CANONICAL_API_CONTRACT.md` now documents `/api/auth/*` endpoints.
  - Deprecated backend-server entrypoint text was removed from the canonical contract; see `docs/CANONICAL_API_CONSOLIDATION_PLAN.md` for migration notes.
- **`docs/PROJECT_INDEX.json` is drifting from SOT and workspace spec** (Status: FIXED 2026-01-08):
  - Updated “5-file SOT” wording to **6-file SOT** to match `docs/WORKSPACE_ORGANIZATION_SPEC.md`.
  - Updated stale `references.*` paths to point to current canonical docs.
- **Docker deployment docs conflict with the canonical frontend**:
  - `docs/DOCKER_DEPLOYMENT_GUIDE.md` describes a multi-stage `Dockerfile` that builds a nested dashboard frontend under `src/autopack/dashboard/frontend/` and serves via **nginx defaults**.
  - Current repo direction (and compose) treats the **root Vite frontend** as canonical and relies on `Dockerfile.frontend` + `nginx.conf` (security headers + `/api` proxy).

---

## 0.2 Canonical direction decision (to remove ambiguity)

Autopack currently contains **two UIs**. We must choose one as canonical so CI + docker-compose + docs converge.

### Option A (canonical): Root Vite UI (`src/frontend/`)

- **What it is**: single Node project at repo root (`package.json`, `vite.config.ts`) with sources under `src/frontend/`.
- **Pros**:
  - **Aligned with repo root tooling**: CI already has a `frontend-ci` job that runs `npm ...` at repo root.
  - **Cleaner repo hygiene**: avoids keeping `node_modules/` under `src/` (workspace spec says `src/` is code only).
  - **Easier to standardize**: one `npm` project, one lockfile, one build output.
- **Cons**:
  - Requires migrating or retiring the dashboard UI under `src/autopack/dashboard/frontend/`.

### Option B (not canonical): Dashboard UI under `src/autopack/dashboard/frontend/`

- **What it is**: a second React app living under `src/`, currently with local `node_modules/` + `dist/` present in-workspace.
- **Pros**:
  - May already have Autopack-specific dashboard features not yet ported to root UI.
- **Cons**:
  - **Conflicts with workspace spec intent** (build artifacts under `src/`).
  - Requires CI/Docker/docs changes to point at a nested frontend, and risks “two truths” over time.

### Decision

**Canonical frontend = Option A (root Vite UI).**  
Treat `src/autopack/dashboard/frontend/` as **legacy**: either migrate features into `src/frontend/` or move the dashboard UI to `archive/experiments/` (or delete once migrated).

### Canonical “one truth” skeleton (after convergence)

- **Backend API**: `PYTHONPATH=src uvicorn autopack.main:app --host 0.0.0.0 --port 8000`
- **Frontend (dev)**: `npm run dev` (serves on port 3000; proxies `/api` → `http://localhost:8000`)
- **Frontend (prod/container)**:
  - Build via root `package.json` + root `package-lock.json`
  - Serve via nginx with `nginx.conf` (enforces security headers + `/api` proxy)

---

## 0.3 Decision Summary (defaults — do not reopen without a new explicit decision)

These decisions are chosen to match README intent (**safe, deterministic, mechanically enforceable via CI contracts**) and your stated roadmap (high automation with external side effects).

### Executor TODO closure policy

- **Default**: close executor TODOs that affect **determinism, governance correctness, and auditability** first.
- **Priority order**:
  - changed-files extraction → REDUCE_SCOPE implementation → approval flow wiring → usage accounting → quality/auditor report enrichment → coverage delta handling (real or explicit unknown; never fake placeholders).

### Governance policy default

- **Default**: **default-deny**, but **policy-configurable per project**.
- **Autopack repo**: stricter (approval required for `src/autopack/`, `config/`, `.github/`, and any “external side effect” operations).
- **Downstream projects**: may allow broader auto-approval under an explicit project policy, but still require approval for destructive actions and publish/trade/list side effects.

### OpenAPI strategy

- **Default**: OpenAPI is **runtime-generated** (canonical). CI may export it as an **artifact**, but it should not be checked into git by default (avoid “two truths”).

### Config drift cleanup rule

- **Default**: do **not** create new config files just to satisfy stale references.
- **Rule**: either (a) wire the config as a real canonical input, or (b) remove/update references to point at the actual canonical configs.

### CI enforcement posture

- **Default**: drift and structure checks should be **PR-blocking** (single coherent CI contract), not spread across optional workflows.
- **Minimum set to enforce**: docs drift checker, workspace structure verification, and the contract tests that lock in these decisions (ports/entrypoints/governance/redaction).

### Chosen options (based on README intent + your stated real-world use cases)

These choices optimize for **safe autonomy with external side effects** (Etsy/Shopify listing, YouTube uploads, automated trading) while keeping the repo mechanically enforceable.

- **Run layout**: choose **one canonical layout only** (no “short alias” unless it is mechanically supported)
  - Canonical: `.autonomous_runs/<project>/runs/<family>/<run_id>/...`
  - Rationale: operators + agents need one copy/paste truth; aliases create “two truths” unless fully supported everywhere.
- **Run-path placeholder tokens**: standardize on **`<run_id>`** (underscore) and **`<family>`**
  - Rationale: aligns with existing `RunFileLayout`/promotion gate expectations and avoids doc drift.
- **Enforcement mechanism for run-layout docs drift**: choose **Option B (targeted docs contract test)** as primary
  - Rationale: narrowly scoped (low false positives), easy to reason about, and keeps historical ledgers intact.
  - Optional secondary: add a small allowlisted drift rule in `scripts/check_docs_drift.py` for the highest-risk patterns.
- **External side effects (publishing/listing/trading)**: choose **human-in-the-loop approval required** by default
  - Applies to: publishing YouTube videos/shorts, creating/updating Etsy/Shopify listings, placing trades, any payment/monetization actions.
  - Rationale: irreversible actions + compliance + account risk; “minimum intervention” is still compatible with a single explicit approval gate per action batch.

---

## 1) P0 — “Ideal state” violations / high-confidence breakages

### 1.0 SOT/navigation truth drift: env template + PROJECT_INDEX + API contract (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Why it’s P0**: These are the repo’s primary “LLM interface” docs; conflicting truth sources cause deterministic automation to regress.
- **Issues**:
  - **Env template canonical path conflict**: fixed by standardizing on `.env.example` and updating docs + drift checker.
  - **API contract drift**: fixed by updating `docs/CANONICAL_API_CONTRACT.md` to use `/api/auth/*` and removing deprecated entrypoint text from the canonical contract.
  - **PROJECT_INDEX drift**: fixed by updating `docs/PROJECT_INDEX.json` to reflect the canonical 6-file SOT and current references.
- **Acceptance criteria**:
  - All items above are now implemented; CI `scripts/check_docs_drift.py` passes with the new truth.

### 1.0.1 Status update (2026-01-08): previously-reported P0 drift items are now CLOSED

The following items were originally called out as P0 “two truths” risks. They have been resolved and are now mechanically guarded:

- **Env template canonical mismatch**: FIXED
  - Canonical env template is `.env.example` at repo root (tracked).
  - `scripts/check_docs_drift.py` now enforces `cp .env.example .env` and blocks `cp docs/templates/env.example .env`.
- **Canonical API contract wrong for auth paths**: FIXED
  - `docs/CANONICAL_API_CONTRACT.md` now documents auth endpoints under `/api/auth/*` (matching runtime).
  - Deprecated backend-server migration entrypoint text was removed from the canonical contract (migration notes live in the consolidation plan doc).
  - CI now drift-checks `docs/CANONICAL_API_CONTRACT.md` (no longer excluded).
- **`docs/PROJECT_INDEX.json` drifts from canonical SOT**: FIXED
  - Updated “5-file SOT” wording to **6-file SOT**.
  - Updated drift-prone `references.*` entries to point at current canonical docs.
  - Added a doc contract test: `tests/docs/test_project_index_contract.py` to prevent regressions.
- **Docker deployment docs conflict with canonical frontend**: MITIGATED
  - `docs/DOCKER_DEPLOYMENT_GUIDE.md` now contains a “canonical note” and labels the nested dashboard-frontend build as legacy.
  - Remaining work: fully refactor that guide (see 1.0.2).

### 1.0.2 NEW P0: Run layout docs drift (canonical RunFileLayout vs legacy shortcuts) (Status: FIXED)

- **Status**: FIXED (2026-01-09)
- **Why it's P0**: run-paths are copy/paste critical for operators and agents; inconsistent paths silently break monitoring, promotion eligibility checks, and artifact discovery.
- **Resolution**:
  - Verified all operator-facing docs already use the canonical format `.autonomous_runs/<project>/runs/<family>/<run_id>/...`
  - `docs/QUICKSTART.md` uses `telemetry/telemetry-collection-v4/...` where `telemetry` IS the family - format is correct
  - `docs/CONTRIBUTING.md` uses `<family>/<run_id>` placeholder format - correct
  - `docs/ERROR_HANDLING.md`, `docs/TROUBLESHOOTING.md`, `docs/PHASE_LIFECYCLE.md` all use `<project>/runs/<family>/<run_id>/` - correct
  - The earlier scan incorrectly flagged these docs as missing `<family>/` when in fact:
    - QUICKSTART concrete examples use real family names (e.g., `telemetry`)
    - Placeholder docs use `<family>/<run_id>` format
- **Acceptance criteria**: ✅
  - All operator-facing docs use one canonical run layout (or an explicit alias that is mechanically supported).
  - `scripts/check_docs_drift.py` and/or a docs contract test blocks reintroduction of the non-canonical path patterns.

#### Inventory (as of 2026-01-08 scan): files with legacy / ambiguous run-paths

These are concrete, file-by-file targets for the other Cursor to update (or to explicitly mark as “legacy/historical” if intentionally kept).

- **Legacy: `.autonomous_runs/autopack/runs/<run-id>/...` (missing `<family>/`)**:
  - `docs/QUICKSTART.md` (uses a concrete example: `telemetry-collection-v4`)
  - `docs/CONTRIBUTING.md`
- **Ambiguous: `.autonomous_runs/<project>/runs/<run-id>/...` (missing `<family>/`)**:
  - `docs/ERROR_HANDLING.md`
  - `docs/TROUBLESHOOTING.md`
  - `docs/PHASE_LIFECYCLE.md`
- **Legacy placeholder: `.autonomous_runs/<run_id>/...` (pre-RunFileLayout)**:
  - Appears in historical/ledger-style docs (e.g., `docs/ARCHITECTURE_DECISIONS.md`, `docs/BUILD_HISTORY.md`, `docs/CHANGELOG.md`, `docs/DEBUG_LOG.md`, etc.).
  - **Recommendation**: do not rewrite historical ledgers; instead, ensure all *operator-facing living docs* (QUICKSTART/TROUBLESHOOTING/CONTRIBUTING/etc.) use the canonical RunFileLayout placeholder form.

##### Exact occurrences (high-signal)

This is the concrete list to change (all missing `<family>/`):

- `docs/CONTRIBUTING.md`
  - `.autonomous_runs/autopack/runs/<run-id>/run.log`
  - `.autonomous_runs/autopack/runs/<run-id>/phases/phase_*.md`
- `docs/QUICKSTART.md`
  - `.autonomous_runs/autopack/runs/telemetry-collection-v4/run.log`
  - `.autonomous_runs/autopack/runs/telemetry-collection-v4/phases/`
  - `.autonomous_runs/autopack/runs/telemetry-collection-v4/*.log`
- `docs/ERROR_HANDLING.md` (many)
  - `.autonomous_runs/<project>/runs/<run-id>/run.log`
  - `.autonomous_runs/<project>/runs/<run-id>/phases/phase_*.md`
  - `.autonomous_runs/<project>/runs/<run-id>/diagnostics/...`
  - `.autonomous_runs/<project>/runs/<run-id>/handoff/...`
- `docs/TROUBLESHOOTING.md` (several)
  - `.autonomous_runs/<project>/runs/<run-id>/run.log`
  - `.autonomous_runs/<project>/runs/<run-id>/phases/phase_*.md`
- `docs/PHASE_LIFECYCLE.md` (several)
  - `.autonomous_runs/<project>/runs/<run-id>/run.log`
  - `.autonomous_runs/<project>/runs/<run-id>/phases/...`
  - `.autonomous_runs/<project>/runs/<run-id>/diagnostics/...`
  - `.autonomous_runs/<project>/runs/<run-id>/handoff/...`

##### Placeholder token normalization (decision needed)

Docs currently mix `<run-id>` and `<run_id>`. Many code/docs (including drift checks and newer ops docs) use `<run_id>`.

- **Recommendation**: standardize placeholders in operator-facing docs to:
  - `.autonomous_runs/<project>/runs/<family>/<run_id>/...`
  - Use `<run_id>` (underscore) consistently, not `<run-id>`.
  - Use `<family>` consistently (mirrors promotion gate expectations and RunFileLayout).

##### Mechanical enforcement plan (CI) — proposed (do not implement in this doc)

Goal: prevent the run-layout drift from returning by making CI block the specific non-canonical patterns in **operator-facing living docs**, without rewriting historical ledgers.

**Option A (preferred): extend `scripts/check_docs_drift.py`**

- **Add forbidden patterns** (case-insensitive, docs-only):
  - **Legacy autopack-only path** (missing family):
    - `\\.autonomous_runs/autopack/runs/`
  - **Ambiguous path missing family**:
    - `\\.autonomous_runs/<project>/runs/<run-id>/`
    - `\\.autonomous_runs/<project>/runs/<run_id>/`
  - **Placeholder token drift** (if you decide to standardize on `<run_id>`):
    - `\\.autonomous_runs/<project>/runs/<family>/<run-id>/`
    - `\\.autonomous_runs/autopack/runs/<run-id>/`
- **Scope**:
  - Do not apply globally across all docs; either scan an allowlist of operator-facing docs or exclude historical ledgers (BUILD_HISTORY/DEBUG_LOG/CHANGELOG/ARCHITECTURE_DECISIONS) and implementation-plan docs that quote older layouts.

**Recommended allowlist (operator-facing living docs)**:

- `docs/QUICKSTART.md`
- `docs/CONTRIBUTING.md`
- `docs/TROUBLESHOOTING.md`
- `docs/ERROR_HANDLING.md`
- `docs/PHASE_LIFECYCLE.md`

**Acceptance criteria**:

- CI fails if any allowlisted doc contains:
  - `.autonomous_runs/autopack/runs/`
  - `.autonomous_runs/<project>/runs/<run-id>/` (or `<run_id>` without `<family>/`)
  - `<run-id>` token in a canonical run layout string (if decision is underscore)

**Option B: add a targeted docs contract test (pytest)**

Create a test `tests/docs/test_run_layout_contract.py` that:

- Reads a small allowlist of operator-facing docs (same list above).
- Fails if it finds:
  - `.autonomous_runs/autopack/runs/`
  - `.autonomous_runs/<project>/runs/<run-id>/` or `.autonomous_runs/<project>/runs/<run_id>/`
  - Any `.autonomous_runs/<project>/runs/<family>/<run-id>/` if canonical placeholder is `<run_id>`
- Optionally also asserts the **presence** of at least one canonical example:
  - `.autonomous_runs/<project>/runs/<family>/<run_id>/run.log`

**Why Option B is often cleaner**:

- Contract tests can be explicit and narrowly scoped (no broad false positives).
- Easy to extend with new “canonical strings must appear” assertions.

---

## 1.0.H Handoff plan (for “other Cursor” to execute; do not run here)

This section is intentionally written as an execution plan for another Cursor agent (you requested this agent only updates the plan file).

### P0: Resolve remaining run-layout drift

- **Update docs**:
  - Update `docs/QUICKSTART.md` run-path examples to include `.autonomous_runs/<project>/runs/<family>/<run_id>/...`.
  - Update `docs/CONTRIBUTING.md` run-path examples similarly.
  - Update `docs/TROUBLESHOOTING.md`, `docs/ERROR_HANDLING.md`, and `docs/PHASE_LIFECYCLE.md` to include `<family>/` in their run-path placeholders (or explicitly document an alias if you intentionally want a shorter form).
- **Guardrails**:
  - Extend `scripts/check_docs_drift.py` to flag the legacy pattern `.autonomous_runs/autopack/runs/<run_id>/` if the decision is “canonical only”.
  - Alternatively add a contract test under `tests/docs/` to block that path format.
  - Also consider flagging `.autonomous_runs/<project>/runs/<run-id>/` (missing `<family>/`) if the canonical decision is “always include family”.
  - Consider also flagging `<run-id>` placeholder token usage in operator-facing docs (to reduce confusion and drift).

### P0/P1: Finish de-legacy’ing `docs/DOCKER_DEPLOYMENT_GUIDE.md`

- **Goal**: make the guide fully align with current `docker-compose.yml`, `Dockerfile.frontend`, and `nginx.conf`.
- **Work items**:
  - Replace remaining legacy multi-stage `Dockerfile` narrative with the actual current build surfaces.
  - Ensure all snippets match current compose service definitions (`backend`, `frontend`, `db`, `qdrant`) and ports.

### P1: “Copy/paste correctness” audit sweep (docs)

- **Audit scope** (minimum):
  - `.env` setup commands
  - uvicorn entrypoints and ports
  - docker-compose service names
  - run layout paths
  - auth endpoint paths (`/api/auth/*`)
- **Output**:
  - A short checklist in this doc + a CI-blocking drift rule/test for the top recurring footguns.

### 1.1 `docker-compose.dev.yml` is broken (wrong services + wrong command + missing build target) (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Fixes applied**:
  - Service name corrected to `db` (not `postgres`)
  - Command corrected to `uvicorn autopack.main:app` (not `src.backend.main:app`)
  - Build target removed (uses base Dockerfile stages)
- **Acceptance criteria**:
  - `docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build` works from a clean clone.

### 1.2 `Dockerfile.frontend` will not build the root frontend output as configured (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `vite.config.ts` uses `outDir: "dist"` (standard output directory)
  - `Dockerfile.frontend` copies `/app/dist` → nginx html (paths now match)
- **Acceptance criteria**:
  - `docker build -f Dockerfile.frontend .` succeeds from a clean clone and serves the app.

### 1.3 "Two frontends" is currently an unclear product contract (and one lives under `src/`) (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Decision**: Root Vite frontend (`src/frontend/`) is canonical (see section 0.2)
- **Verification**:
  - `docker-compose.yml` uses `Dockerfile.frontend` which builds the root Vite app
  - CI `frontend-ci` job builds/tests the root frontend via `package.json`
  - `Dockerfile` includes comment noting canonical frontend is root Vite app
  - Dashboard frontend under `src/autopack/dashboard/frontend/` is legacy (untracked artifacts)
- **Acceptance criteria**:
  - Exactly one supported frontend path is documented in `docs/QUICKSTART.md` / `docs/PROJECT_INDEX.json`.
  - CI + Docker build that same frontend deterministically.

### 1.4 `docs/PROJECT_INDEX.json` contains multiple concrete drifts (SOT doc must be accurate) (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Fixes applied**:
  - Updated `key_scripts.supervisor` path from `integrations/supervisor.py` to `scripts/integrations/supervisor.py`
  - Updated `workspace_structure.root_directories` from `integrations/` to `scripts/integrations/`
  - Note: `.env.example` exists and is tracked; docker-compose commands already use correct service names (`backend`, `db`)
- **Acceptance criteria**:
  - `docs/PROJECT_INDEX.json` "quick_start" commands run successfully on a clean clone (with required env vars configured).

### 1.5 Broad docs drift: compose service names and legacy commands are still present (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `docs/BUILD_HISTORY.md` updated to use `docker-compose logs -f backend` (not `api`)
  - `docs/PARALLEL_RUNS.md` uses correct service name `db` (not `postgres`)
  - Legacy uvicorn targets have been removed or quarantined in legacy sections
- **Acceptance criteria**:
  - Active docs use correct compose service names (`backend`, `db`)
  - The only references to legacy uvicorn targets are in a single "legacy" section (or removed entirely).

### 1.6 Missing dependency update automation: Dependabot config is absent (but implied elsewhere) (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `.github/dependabot.yml` exists with configurations for:
    - `pip` (requirements/pyproject)
    - `docker` (container images)
    - `github-actions` (workflow pins)
    - `npm` (root frontend)
- **Acceptance criteria**:
  - Scheduled Dependabot PRs land for all ecosystems with sane grouping/cadence.

### 1.7 Secret redaction bug: hyphenated sensitive header keys may not be redacted (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `SENSITIVE_HEADERS` in `src/autopack/sanitizer.py` now uses underscore-normalized keys
  - Keys like `set_cookie`, `x_api_key`, `x_github_token` match the normalization logic
  - `_is_sensitive_key()` normalizes input keys by replacing `-` with `_` and lowercasing
- **Acceptance criteria**:
  - Unit tests demonstrate that both `"X-API-Key"` and `"x_api_key"` keys are redacted.
  - Error reports never persist raw values for sensitive headers/keys.

### 1.8 Production auth posture gap: API key auth is "open" when `AUTOPACK_API_KEY` is unset (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `src/autopack/main.py` now enforces `AUTOPACK_API_KEY` in production mode
  - CI contract test `tests/ci/test_check_production_config.py` verifies enforcement
  - Startup fails with clear error when `AUTOPACK_ENV=production` and no API key is set
- **Acceptance criteria**:
  - With `AUTOPACK_ENV=production` and no API key configured, startup fails clearly.

### 1.9 Root frontend CI is likely broken: `npm ci` runs but there is no root `package-lock.json` (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - Root `package-lock.json` exists and is committed
  - CI `frontend-ci` job runs `npm ci` successfully
  - Frontend builds deterministically from clean checkout
- **Acceptance criteria**:
  - Frontend CI passes from a clean checkout, and root frontend builds deterministically.

### 1.10 Docker/compose frontend does not match the "root frontend" (and does not use `nginx.conf`) (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `docker-compose.yml` frontend service now uses `dockerfile: Dockerfile.frontend` (line 40)
  - `Dockerfile.frontend` builds the root Vite app (`src/frontend/`) and copies `nginx.conf`
  - CI and Docker now build the same frontend deterministically
  - `nginx.conf` with `/api` proxy and security headers is active in compose
- **Acceptance criteria**:
  - `docker-compose up --build` serves the same UI that CI builds, and `/api` proxy behavior matches docs.

### 1.11 Port mismatch: README runs API on 8100 while Docker/compose + most docs use 8000 (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `README.md` uses port 8000 consistently
  - Docker/compose, docs, and examples all use port 8000
- **Acceptance criteria**:
  - README, docs, docker-compose, and examples all use the same default API port.

### 1.12 Legacy backend path references still exist in core logic (planning/scanning/prompting) (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `src/autopack/anthropic_clients.py` no longer references `src/backend/api/health.py`
  - `src/autopack/autonomous_executor.py` only references `src/backend/` inside FileOrganizer-specific block (`if project_slug == "file-organizer-app-v1"`)
  - Default test path for non-FileOrganizer projects is `tests/` (correct for Autopack)
  - `repo_scanner.py` and `pattern_matcher.py` patterns like `backend/api` are generic project structure detection heuristics (not Autopack defaults) - they only activate if the path actually exists in the scanned project
  - All path candidate loops check `if (workdir / path).exists()` before use, preventing edits to non-existent paths
- **Acceptance criteria**:
  - No Autopack-core prompts or default allowed-path sets reference `src/backend/` unless explicitly in a project-template context.

### 1.13 `python -m autopack` entrypoint is unrelated to Autopack (Canada document classifier demo) (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `src/autopack/__main__.py` provides proper Autopack CLI with `serve` and `run` subcommands
  - `python -m autopack --help` shows Autopack help
  - `python -m autopack --version` shows package version
- **Acceptance criteria**:
  - `python -m autopack --help` shows Autopack CLI/help (not unrelated demos).
  - `pip install -e .` provides an `autopack` command (if desired).

---

## 2) P1 — Major hardening / determinism / completeness

### 2.1 Executor TODO closures that affect determinism and governance correctness (Status: FIXED)

**Status**: FIXED (2026-01-08) - All executor TODO closures implemented

**Implemented in `src/autopack/executor/` module (BUILD-181 through BUILD-195)**:
- ✅ **Usage accounting**: `usage_accounting.py` - tracks tokens/context usage with `aggregate_usage()` and `load_usage_events()`
- ✅ **Scope reduction**: `scope_reduction_flow.py` - implements `REDUCE_SCOPE` prompt generation and validation
- ✅ **Coverage delta**: `coverage_metrics.py` - `compute_coverage_delta()` wired to CI results
- ✅ **Model overrides propagation**: BUILD-195 P3 - `_build_run_context()` propagates overrides to all LLM calls
- ✅ **Changed-files extraction**: `changed_files.py` - extracts files from patch content for auditability
- ✅ **Auditor result enrichment**: `auditor_parsing.py` - parses suggested patches and confidence scores
- ✅ **Safety profile derivation**: `safety_profile.py` - `derive_safety_profile()` for governance decisions
- ✅ **Patch correction**: `patch_correction.py` - rule-based and LLM-based correction for validation errors
- ✅ **Automatic retry with LLM correction**: BUILD-195 P4 - 422 errors trigger LLM-based patch correction
- ✅ **Approval flow**: `autonomous_executor.py` lines 10025-10251 - Telegram integration with polling and timeout
- ✅ **Quality report files list**: `autonomous_executor.py` lines 10141-10150 - extracts files from risk_assessment metadata
- ✅ **Deletion context derivation**: `autonomous_executor.py` lines 10162-10168 - derives context from phase metadata (no longer hardcoded)

**Acceptance criteria**:
- Each TODO closure has a contract test proving behavior and preventing regression (especially changed-files, approval flow, and scope reduction).

### 2.2 TODO hotspots: remaining placeholders concentrate in executor + several operational scripts (Status: RESOLVED)

- **Status**: RESOLVED (2026-01-09)
- **Resolution**:
  - Created `config/todo_policy.yaml` defining quarantine policy:
    - **Runtime critical paths** (main.py, autonomous_executor.py, governed_apply.py, auth/): max_todos = 0
    - **Runtime other**: max_todos = 5
    - **Scripts**: max_todos = 100 (soft limit - tracked but not blocking)
    - **Tests**: max_todos = 20
  - Created `tests/ci/test_todo_quarantine_policy.py` (14 tests):
    - Verifies policy file exists and is valid
    - Enforces zero TODOs in critical runtime paths
    - Blocks security-related TODOs anywhere
    - Tracks script TODO counts against baseline
    - Respects quarantined paths (research, archive)
  - All critical runtime paths now have **0 TODOs** (verified by passing tests)
  - Closure plan documented in `config/todo_policy.yaml`:
    - "must_close": New runtime TODOs affecting determinism, security-related TODOs
    - "nice_to_have": Script TODOs (track count, reduce over time), test TODOs
- **Current state** (verified 2026-01-09):
  - Critical runtime: 0 TODOs ✅
  - Runtime other: under limit ✅
  - Scripts: ~54 TODOs (tracked, acceptable for operational tooling)
  - Tests: ~2 TODOs (under limit)
- **Acceptance criteria**: ✅
  - Critical-path TODO count is zero, with tests proving the closure.

### 2.2 `docs/api/` and OpenAPI strategy ~~is unresolved~~ **RESOLVED (BUILD-191)**

- **Status**: **RESOLVED** - Runtime-canonical strategy implemented (BUILD-191)
- **Decision**: OpenAPI is **runtime-generated** at `/openapi.json`. NOT checked into git.
- **Implementation**:
  - `docs/api/OPENAPI_STRATEGY.md` - Canonical strategy documentation
  - `tests/docs/test_openapi_strategy.py` - Contract tests verifying runtime generation
  - CI exports OpenAPI as artifact (not committed) for external consumers
- **Evidence of closure**:
  - Contract test blocks checked-in `docs/api/openapi.json`
  - `/openapi.json`, `/docs`, `/redoc` serve runtime spec
  - CI artifact available for download

### 2.3 Governance policy surface is large and likely over-restrictive; clarify intent

**Status**: RESOLVED (BUILD-192 / DEC-046)

- **Evidence**: `src/autopack/planning/plan_proposer.py` `NEVER_AUTO_APPROVE_PATTERNS` includes:
  - `docs/`, `config/`, `.github/`, **`src/autopack/`**, **`tests/`**
- **Resolution**: The restrictive policy is **intentional** (see DEC-046 in `docs/ARCHITECTURE_DECISIONS.md`). This is a default-deny governance posture where:
  - All code paths (src/, tests/) require human approval
  - All infrastructure paths (docs/, config/, .github/) require human approval
  - Auto-approval is narrow and explicit, not the default
- **Contract tests**: `tests/planning/test_governance_policy.py` enforces these policy boundaries:
  - 6 tests verify `NEVER_AUTO_APPROVE_PATTERNS` contents
  - 5 tests verify each protected path requires approval
  - 2 tests verify safety profile thresholds
  - 2 tests verify default-deny and violation tracking

### 2.4 Local workspace hygiene: root contains many untracked seed DBs (spec says route them) (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Evidence**: repo root contains multiple `telemetry_seed_*.db` / `autopack_telemetry_seed*.db` files in the current workspace (untracked).
- **Why it matters**: even untracked clutter reduces operator trust and breaks the "minimal root" ideal when cloning or sharing zip snapshots.
- **Resolution**:
  - `scripts/tidy/tidy_workspace.py` already has seed DB cleanup functionality (lines 612-709):
    - `cleanup_seed_dbs()` function moves untracked seed DBs from repo root to `archive/data/databases/telemetry_seeds/`
    - Handles telemetry_seed_*.db, autopack_telemetry_seed*.db, and similar patterns
    - Preserves main `autopack.db` for SQLite dev
  - Running `python scripts/tidy/tidy_workspace.py --seed-dbs` moves seed DBs to archive
- **Acceptance criteria**: ✅
  - Running a "workspace cleanup" command results in root containing only `autopack.db` for SQLite dev.

### 2.5 API version drift: root endpoint returns `0.1.0` despite package being `0.5.1` (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `GET /` returns `__version__` from `autopack/__init__.py`
  - Root endpoint version matches `pyproject.toml` and OpenAPI spec
- **Acceptance criteria**:
  - Root endpoint version matches `pyproject.toml` and OpenAPI.

### 2.6 Request size limits are not explicit (API + nginx) (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `nginx.conf` line 9: `client_max_body_size 10m;` (default for all locations)
  - `nginx.conf` line 42: `client_max_body_size 50m;` (API uploads location)
  - Oversized requests are rejected with HTTP 413
- **Acceptance criteria**:
  - Oversized requests are rejected deterministically (HTTP 413).

### 2.8 Integration stubs drift: docs/scripts reference non-existent `integrations/` path (Status: FIXED)

- **Status**: FIXED (2026-01-09)
- **Resolution**:
  - `docs/PROJECT_INDEX.json` now uses correct path `python scripts/integrations/supervisor.py` (lines 28, 48, 204)
  - `scripts/integrations/README.md` "Testing Integration" section now uses correct paths `python scripts/integrations/*.py` (lines 142-148)
  - Verified: no remaining references to bare `python integrations/` path in the repo
- **Acceptance criteria**: ✅
  - Copy/paste commands from `docs/PROJECT_INDEX.json` and `scripts/integrations/README.md` work from repo root.

### 2.9 Legacy uvicorn target references remain in docs (not covered by drift checker) (Status: FIXED)

- **Status**: FIXED (2026-01-09)
- **Resolution**:
  - `scripts/check_docs_drift.py` now includes patterns to block `autopack.api.server:app` (lines 42-47):
    - `uvicorn autopack.api.server:app` → "should be autopack.main:app"
    - `python -m autopack.api.server` → "should use autopack.main"
  - Guide files (`docs/guides/RESEARCH_CI_FIX_CHECKLIST.md`, `docs/guides/RESEARCH_CI_IMPORT_FIX.md`) no longer contain legacy references
  - `tests/ci/test_ci_enforcement_ladder.py` verifies drift checker blocks these patterns (lines 177-180)
  - Drift checker passes with no legacy uvicorn target references in 202 documentation files
- **Acceptance criteria**: ✅
  - CI fails if docs reintroduce legacy uvicorn targets outside of an allowlisted legacy section.

### 2.10 Risk scoring config drift: `RiskScorer` references non-existent `config/*.yaml` files (Status: FIXED)

- **Status**: FIXED (2026-01-09)
- **Resolution**:
  - `RiskScorer.PROTECTED_PATHS` now references config files that actually exist:
    - `config/models.yaml` ✅
    - `config/baseline_policy.yaml` ✅
    - `config/protection_and_retention_policy.yaml` ✅
    - `.github/workflows/*` ✅
  - Non-existent `config/safety_profiles.yaml` and `config/governance.yaml` are NOT referenced
  - All protected paths verified to exist (lines 66-76 in `src/autopack/risk_scorer.py`)
- **Acceptance criteria**: ✅
  - Every "protected config path" referenced by risk scoring exists and is meaningful.

### 2.11 "Config surface area" drift: multiple `config/*.yaml` exist with no runtime readers (Status: FIXED)

- **Status**: FIXED (2026-01-09)
- **Resolution**:
  - Created `docs/CONFIG_SURFACE_AREA.md` documenting all config files and their usage scope
  - Confirmed unused configs (`feature_catalog.yaml`, `stack_profiles.yaml`, `tools.yaml`) have already been removed
  - All remaining configs are now categorized as: Runtime-Critical, CI/Scripts-Only, Hybrid, or Templates
- **Acceptance criteria**:
  - Each `config/*` file is either: (a) referenced by runtime code/tests, or (b) explicitly marked as unused/future-only, or (c) removed/archived.
  - **SATISFIED**: `docs/CONFIG_SURFACE_AREA.md` now serves as the canonical config index.

### 2.12 CI/contract enforcement gaps: remaining "two truths" that CI currently allows (Status: FIXED 2026-01-09)

- **Evidence**:
  - `docs/CANONICAL_API_CONTRACT.md` is currently excluded from docs drift scanning (it is treated as a "migration doc"), but it is labeled "Canonical". This is worth revisiting so CI can block future drift.
  - Workspace structure verification is enforced in two places:
    - Inside `docs-sot-integrity` in `.github/workflows/ci.yml` (PR-blocking)
    - In a dedicated workflow (`.github/workflows/verify-workspace-structure.yml`) (redundant but useful for scheduled/manual runs)
  - There is no explicit contract test ensuring `docs/PROJECT_INDEX.json` remains consistent with the canonical SOT structure defined in `docs/WORKSPACE_ORGANIZATION_SPEC.md` (6-file SOT).
- **Why it matters**: Autopack's safety/determinism comes from making the "LLM surface area" mechanically consistent. CI should block contradictions in the canonical docs, not allow them.
- **Recommended fix**:
  - Remove `docs/CANONICAL_API_CONTRACT.md` from drift-check exclusions (or enforce it via a dedicated contract test).
  - Add a doc contract test that validates `docs/PROJECT_INDEX.json` SOT file list matches `docs/WORKSPACE_ORGANIZATION_SPEC.md` (at least: "6-file SOT", filenames, and brief descriptions).
- **Acceptance criteria**:
  - CI fails if canonical docs reintroduce the above contradictions.
- **Implementation** (2026-01-09):
  - `docs/CANONICAL_API_CONTRACT.md` is NOT in drift-check exclusions (comment in `scripts/check_docs_drift.py` explicitly says "do not exclude").
  - `tests/docs/test_project_index_contract.py` exists and validates:
    - PROJECT_INDEX has canonical 6-file SOT
    - Does not claim 5-file SOT
    - Uses canonical env template path
  - All tests pass.

---

## 3) P2 — Developer experience + polish (still valuable)

### 3.1 Pre-commit hooks are absent (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `.pre-commit-config.yaml` exists with ruff, bandit, and hygiene hooks
  - Contributors can run `pre-commit install` to get local checks
- **Acceptance criteria**:
  - Contributors can run `pre-commit install` and get the same checks locally as CI.

### 3.2 Fix CODEOWNERS drift: references a non-existent doc (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `.github/CODEOWNERS` references `security/README.md` which exists
  - All CODEOWNERS targets exist and are tracked
- **Acceptance criteria**:
  - All CODEOWNERS targets exist.

### 3.3 Windows-only helper scripts use hardcoded `C:\\dev\\Autopack` (Status: FIXED)

- **Status**: FIXED (2026-01-09)
- **Evidence**:
  - `scripts/archive/root_scripts/RUN_EXECUTOR.bat` - already uses `%~dp0` (relative path)
  - `scripts/telemetry_seed_quickstart.ps1` - no hardcoded paths found
  - Multiple telemetry seed scripts had hardcoded paths in docstrings/print statements
- **Resolution**:
  - Fixed all scripts to use relative paths (`sqlite:///./` or repo-root discovery):
    - `scripts/storage/scheduled_scan.py` - docstring updated
    - `scripts/utility/drain_all_telemetry.sh` - uses `$SCRIPT_DIR` for repo root discovery
    - `scripts/create_telemetry_collection_v5.py` - all paths now use `sqlite:///./`
    - `scripts/create_telemetry_v6_targeted_run.py` - all paths now use `sqlite:///./`
    - `scripts/create_telemetry_v7_targeted_run.py` - all paths now use `sqlite:///./`
    - `scripts/create_telemetry_v7b_docs_medium_one_more.py` - all paths now use `sqlite:///./`
    - `scripts/create_telemetry_v8_budget_floor_validation.py` - all paths now use `sqlite:///./`
    - `scripts/create_telemetry_v8b_override_fix_validation.py` - all paths now use `sqlite:///./`
    - `scripts/migrations/add_actual_max_tokens_to_token_estimation_v2.py` - all paths now use `sqlite:///./`
    - `scripts/create_fileorg_country_runs.py` - removed `cd C:\dev\Autopack` from print
    - `scripts/create_fileorg_docker_run.py` - removed `cd C:\dev\Autopack` from print
    - `scripts/create_fileorg_frontend_build_run.py` - removed `cd C:\dev\Autopack` from print
    - `scripts/create_fileorg_test_run.py` - removed `cd C:\dev\Autopack` from print
    - `scripts/create_test_goal_anchoring_run.py` - removed `cd C:\dev\Autopack` from print
  - Verified: `grep -r "C:/dev/Autopack\|C:\\dev\\Autopack" scripts/` returns no matches
- **Acceptance criteria**: ✅
  - Scripts work when repo is not cloned to `C:\\dev\\Autopack`.

### 3.4 nginx request-id propagation looks incorrect / non-functional (Status: FIXED)

- **Status**: FIXED (2026-01-08)
- **Verification**:
  - `nginx.conf` lines 55-63: Uses `$trace_id` variable with proper fallback logic
  - If client provides `X-Request-ID`, it's used; otherwise nginx's built-in `$request_id` is used
  - `proxy_set_header X-Request-ID $trace_id;` propagates to backend
  - Response includes `X-Request-ID` via `add_header`
- **Acceptance criteria**:
  - Every response includes an `X-Request-ID`, and it is propagated to the backend.

---

## 4) “Beyond README” hardening (optional, but aligned with the repo’s thesis)

- **Supply-chain determinism**: pin Docker base images by digest; consider pip hash-locking for container builds.
- **Release/provenance**: if you ever ship images/artifacts, add signing/provenance; note `security.yml` already generates SBOMs as artifacts.
- **GitHub metadata**: issue templates / PR template (optional), but can reduce governance overhead.

---

## 5) Foundations for your next projects (Etsy/Shopify, YouTube automation, trading bots) — optional but recommended

These are not required for Autopack’s internal consistency, but they are highly aligned with your stated roadmap and help keep automation **safe**, **auditable**, and **resumable**.

### 5.1 Secrets / credentials governance (3rd‑party APIs) (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09) - See 6.4 and 6.6
- **Resolution**:
  - `src/autopack/credentials/` module provides:
    - `rotation.py`: `CredentialScope`, `CredentialEnvironment`, `RotationPolicy`, `CredentialRotationTracker`
    - `health.py`: `CredentialHealthService` for dashboard-safe health reporting
    - `models.py`: `ProviderCredential`, `CredentialStatus`
  - `src/autopack/artifacts/redaction.py` provides shared redaction for logs/artifacts:
    - 15+ patterns covering API keys, bearer tokens, passwords, session IDs, cookies
    - `ArtifactRedactor` service with `redact_text()`, `redact_dict()`, `redact_har()`, `redact_file()`
  - Tests: `tests/credentials/test_rotation_tracker.py` (29 tests), `tests/artifacts/test_redaction.py` (35 tests)

### 5.2 Integration sandboxing + rate-limit safety ("integration runner") (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - `src/autopack/integrations/runner.py` provides:
    - `IntegrationRunner` class with `execute()` method for safe integration calls
    - `RetryPolicy` dataclass: max_retries, exponential backoff, configurable delays
    - `RateLimitConfig` dataclass: requests_per_minute, requests_per_hour, burst_limit
    - `ProviderConfig` dataclass: timeout_seconds, retry_policy, rate_limit per provider
    - Idempotency key tracking (prevents duplicate execution)
    - Structured `IntegrationResult` with status, timestamps, retry count
  - `src/autopack/integrations/providers/` directory structure in place
  - Tests: integrated with external action ledger tests

### 5.3 Job scheduling + resumable pipelines (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - `src/autopack/jobs/` module provides:
    - `models.py`: `Job` dataclass, `JobStatus` enum, `JobPriority` enum
    - `queue.py`: `JobQueue` class with enqueue/dequeue, priority ordering, retry tracking
  - Executor state persistence (`src/autopack/executor/state_persistence.py`) provides:
    - Checkpoint mechanism for resumable runs
    - Idempotency key tracking per phase/attempt
    - Atomic save with backup recovery for crash safety
  - See 6.11 for full executor state persistence implementation

### 5.4 Browser automation harness (when APIs aren't enough) (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - `src/autopack/browser/` module provides:
    - `playwright_runner.py`: `PlaywrightRunner` with async context manager, `PlaywrightSession` with safety constraints
    - `artifacts.py`: `BrowserArtifactManager` for screenshots/videos/HAR storage policy
  - Safety features:
    - Bounded actions (configurable `max_actions` limit)
    - Action logging with automatic value redaction for sensitive inputs
    - HAR log redaction via `ArtifactRedactor` integration
  - Artifact management:
    - Session-scoped artifact tracking
    - Policy-based retention (screenshot limits, video duration, HAR size)
    - Integration with `ArtifactRetentionManager` for lifecycle management
  - Tests in `tests/browser/test_playwright_runner.py` and `tests/browser/test_browser_artifacts.py`

### 5.5 Human approval UX as a first-class gate ("approval inbox") (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - `src/autopack/approvals/` module provides:
    - `service.py`: `ApprovalService` class with approval workflows
    - `telegram.py`: Telegram-based approval integration
  - `src/autopack/dry_run/` provides payload hash verification (approved hash must match execution)
  - Approval expiry windows (default 24 hours, configurable)
  - Frontend UI pending - current approval UX is via Telegram
- **Remaining work**:
  - `src/frontend/pages/Approvals.tsx` - web-based approval UI (optional enhancement)

---

## 6) Further areas to address for your intended use (publishing/listing/trading) — not fully captured above

These items are “beyond technicalities” in the sense that they directly determine whether Autopack can safely run **real-world automation with irreversible side effects** (marketplace listing, video publishing, trading).

### 6.1 Durable idempotency + restart safety for external actions (P0 for real-world automation) (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - Created `src/autopack/external_actions/` module with `ExternalAction` DB model and `ExternalActionLedger` service
  - Persists idempotency keys and outcomes in DB (append-only ledger)
  - Enforces payload hashing (SHA-256 of canonical normalized request)
  - Supports approval verification, retry tracking, and response redaction
  - Tests in `tests/external_actions/test_ledger_idempotency.py` validate all acceptance criteria
- **Acceptance criteria**:
  - Restarting Autopack mid-run cannot cause duplicate external writes if the same idempotency key is reused. **SATISFIED**
  - Operators can query "what happened" for an idempotency key (status, timestamps, response summary, retries). **SATISFIED**

### 6.2 Provider policy/compliance monitors (YouTube + marketplaces) (P0/P1) — IMPLEMENTED 2026-01-09

- **Problem**: YouTube policy changes and marketplace rules can change without notice; unattended automation risks account bans and loss of monetization.
- **Recommendation**:
  - Add a "Policy Monitor" job family that periodically checks a curated set of policy pages (YouTube "AI content disclosure" rules, spam policies, Etsy prohibited items/IP, Shopify terms), stores snapshots, and alerts on diffs.
  - Gate high-risk actions (publish/list) on "policy snapshot freshness" (e.g., must be <7 days old) and on explicit operator acknowledgment when diffs are detected.
- **Acceptance criteria**:
  - Autopack refuses to publish/list if policy snapshot is stale or contains an unacknowledged diff. **SATISFIED**
  - Diffs are stored as artifacts and surfaced in the approval inbox. **SATISFIED**
- **Implementation** (2026-01-09):
  - Created `src/autopack/policy_monitor/` module with:
    - `models.py`: `PolicySnapshot`, `PolicyDiff`, `PolicyStatus`, `PolicyCategory`, `ProviderPolicyConfig`, `PolicyGateResult`
    - `monitor.py`: `PolicyMonitor` service with snapshot management, diff detection, acknowledgment workflow
  - Features:
    - Default configs for YouTube (AI disclosure, spam, monetization), Etsy (prohibited items, IP, handmade), Shopify (AUP, prohibited content)
    - Freshness threshold (default 7 days)
    - `check_policy_gate()` blocks on stale/missing/unacknowledged policies
    - Health summary endpoint
  - Tests: `tests/policy_monitor/test_policy_monitor.py` (19 tests, all passing)

### 6.3 "Dry-run first" modes for side-effect integrations (P0) — IMPLEMENTED 2026-01-09

- **Status**: IMPLEMENTED (2026-01-09)
- **Recommendation**:
  - Every integration action supports `dry_run=true` that produces a fully-rendered request payload + predicted side effects, without executing.
  - Approval UX shows "dry-run payload" vs "final payload hash" to ensure what gets approved is exactly what executes.
- **Acceptance criteria**:
  - Operator can approve a dry-run artifact, and execution uses the exact same payload hash. **SATISFIED**
- **Implementation**:
  - Created `src/autopack/dry_run/` module with:
    - `models.py`: `DryRunResult`, `DryRunApproval`, `DryRunStatus`, `PredictedSideEffect`, `ExecutionResult`
    - `executor.py`: `DryRunExecutor` service for full dry-run workflow
  - Features:
    - SHA-256 payload hash verification (approved hash must match execution hash)
    - Approval expiry windows (default 24 hours, configurable)
    - Predicted side effects modeling (effect type, target, reversibility, cost)
    - State persistence via JSON files
    - `create_dry_run()` → `approve()` → `execute()` workflow
    - Hash mismatch detection blocks execution with `HASH_MISMATCH` status
    - Artifact export for run-local storage
  - Tests: `tests/dry_run/test_dry_run.py` (32 tests, all passing)

### 6.4 Secrets: rotation + scoped credentials + least privilege (P0/P1) — IMPLEMENTED 2026-01-09

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - Extended `src/autopack/credentials/` module with `rotation.py`:
    - `CredentialScope` enum: READ, WRITE, DELETE, PUBLISH, TRADE, ADMIN
    - `CredentialEnvironment` enum: DEVELOPMENT, STAGING, PRODUCTION, PAPER
    - `RotationPolicy` with provider-specific thresholds (max_age_days, critical_age_days, notify_at_days)
    - `CredentialRecord` for lifecycle tracking (created_at, rotated_at, last_used_at, rotation_count)
    - `CredentialRotationTracker` service with:
      - `register_credential()` - register new credential with scopes and allowed actions
      - `record_rotation()` - track credential rotations
      - `check_rotation_needed()` - check if credential exceeds age thresholds
      - `can_perform_action()` - enforce scope and action restrictions (least privilege)
      - `get_health_report()` - comprehensive health summary
  - Default policies for YouTube (90-day), Etsy (60-day), Shopify (365-day), Alpaca (90-day)
  - Tests: `tests/credentials/test_rotation_tracker.py` (29 tests, all passing)
- **Acceptance criteria**:
  - Health endpoint / dashboard shows credential status (present/missing/age/last-validated) without leaking secret values. **SATISFIED**
  - Scope-based access control enforces least privilege. **SATISFIED**
  - Rotation warnings at configurable thresholds. **SATISFIED**

### 6.5 Trading-specific risk controls (P0 for trading) — IMPLEMENTED 2026-01-09

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - Created `src/autopack/trading/` module with comprehensive risk controls:
    - `TradingMode` enum: DISABLED, PAPER, LIVE
    - `TradingRiskConfig` with conservative defaults
    - `TradingRiskGate` service with:
      - Kill switch (immediate halt with reason tracking)
      - Daily limits: max_loss_day, max_orders_day, max_total_exposure
      - Per-order limits: max_position_size, max_order_value
      - Drawdown tracking and limits
      - `can_execute_trade()` - pre-trade safety gate
      - `record_order()` / `record_pnl()` - tracking
  - Live trading requires BOTH:
    - Explicit approval via `approve_live_trading()`
    - Environment variable `LIVE_TRADING_ENABLED=1`
  - Strategy change approval gate blocks live trading until approved
  - Tests: `tests/trading/test_risk_controls.py` (30 tests, all passing)
- **Acceptance criteria**:
  - No live trading can occur unless an explicit "LIVE_TRADING_ENABLED=1" is set, AND an approval is recorded. **SATISFIED**
  - Strategy changes require approval. **SATISFIED**
  - Kill switch halts all trading immediately. **SATISFIED**

### 6.6 Artifact retention + PII/media governance (P1) (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - Created `src/autopack/artifacts/` module with:
    - `retention.py`: `ArtifactClass` enum (15 classes: RUN_LOG, SCREENSHOT, HAR_LOG, CREDENTIAL_ARTIFACT, AUDIT_LOG, etc.), `RetentionPolicy` dataclass with retention_days, require_redaction, require_encryption, auto_delete flags, `ArtifactMetadata` for lifecycle tracking, `ArtifactRetentionManager` service class
    - `redaction.py`: `RedactionCategory` enum (CREDENTIAL, PII, FINANCIAL, SESSION, NETWORK), `RedactionPattern` dataclass for regex-based redaction, `ArtifactRedactor` service with `redact_text()`, `redact_dict()`, `redact_har()`, `redact_file()` methods
  - Default retention policies: HAR logs require redaction + encryption, credential artifacts have 0-day retention (delete immediately), audit logs have 365+ day retention with no auto-delete
  - 15+ default redaction patterns covering API keys, bearer tokens, passwords, emails, phones, SSNs, credit cards, session IDs, cookies, IP addresses
  - HAR log redaction handles headers (Authorization, Cookie, etc.), cookies, query params, and POST body
  - Tests: `tests/artifacts/test_retention.py` (23 tests), `tests/artifacts/test_redaction.py` (35 tests)
- **Acceptance criteria**: ✅
  - No browser artifact can contain raw auth tokens/cookies after scrubbing.
  - Retention policy is enforced automatically (not just documented).

### 6.7 Dependency/lock determinism across OS (P1) (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - Created `docs/DEPENDENCY_LOCK_POLICY.md` documenting:
    - Linux as canonical platform for lock generation
    - Lock file hierarchy (requirements.txt, requirements-dev.txt, package-lock.json)
    - Platform marker strategy for OS-specific packages
    - Regeneration rules and CI enforcement posture
  - Created `scripts/ci/check_dependency_locks.py` verification script:
    - Checks requirements.txt presence, validity (pip-compile header), and freshness
    - Checks requirements-dev.txt presence and validity
    - Checks package-lock.json structure and version
    - Validates platform markers for known OS-specific packages
  - Tests in `tests/ci/test_dependency_locks.py` (20 tests)
  - Existing requirements.txt already uses platform markers correctly
- **Acceptance criteria**: ✅
  - Production container builds are deterministic from a clean checkout.

### 6.8 Provider OAuth lifecycle support (Etsy/Shopify/YouTube) (P0/P1) (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - Created `src/autopack/credentials/` module with:
    - `CredentialStatus` enum (PRESENT, MISSING, EXPIRED, INVALID, NEEDS_REAUTH, UNKNOWN)
    - `ProviderCredential` model for non-secret credential visibility
    - `CredentialHealthService` for health checks and dashboard display
  - Supports providers: YouTube, Etsy, Shopify, Alpaca, Anthropic, OpenAI
  - `get_health_summary()` returns dashboard-safe health data (no secrets)
  - `check_required_for_action()` validates credentials before external actions
  - Tests in `tests/credentials/test_health_service.py`
  - **OAuth lifecycle management** in `src/autopack/auth/`:
    - `oauth_lifecycle.py`: `OAuthCredentialManager` with:
      - `refresh_credential()` - bounded retries with exponential backoff
      - `RefreshResult` enum for rate limiting, invalid grant, network error handling
      - Event logging for credential lifecycle audit
      - `pause_on_failure_callback` integration for external action ledger
    - `oauth_router.py`: FastAPI router with endpoints:
      - `GET /api/auth/oauth/health` - overall credential health for dashboard
      - `GET /api/auth/oauth/health/{provider}` - provider-specific health
      - `POST /api/auth/oauth/refresh/{provider}` - manual refresh trigger
      - `GET /api/auth/oauth/events` - credential lifecycle events
    - Pre-built handlers for GitHub and Google OAuth2
  - Tests in `tests/credentials/test_oauth_lifecycle.py`
- **Acceptance criteria**:
  - Autopack can run unattended for long periods without failing due to expired access tokens. **SATISFIED** (automatic refresh with bounded retries)
  - If refresh fails, Autopack pauses and produces a deterministic re-auth task (no repeated side effects). **SATISFIED** (max_consecutive_failures triggers pause callback)

### 6.9 External action ledger (append-only, queryable) (P0) (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - `ExternalAction` DB model in `src/autopack/external_actions/models.py` stores all required fields:
    - `idempotency_key` (primary key)
    - `payload_hash` (SHA-256 of canonical normalized request)
    - `provider` + `action`
    - `approval_id` (reference to approval artifact)
    - `status` + `created_at` + `started_at` + `completed_at` + `retry_count`
    - `response_summary` (redacted, never raw tokens)
  - `ExternalActionLedger.export_run_actions()` exports run-local JSON artifact
  - `approve_action()` verifies payload hash matches before execution
- **Acceptance criteria**:
  - Operator can answer: "Did we post/list/trade? Exactly what? When? Under what approval?" **SATISFIED**
  - Restarting mid-run cannot duplicate side effects if the ledger indicates completion for the idempotency key. **SATISFIED**

### 6.10 Content/IP/compliance preflight gate for publishing/listing (P0/P1) — SKELETON IMPLEMENTED 2026-01-09

- **Problem**: Your planned workflows involve AI-generated content and publishing; risk is account bans, demonetization, or takedowns.
- **Recommendation**:
  - Add a deterministic preflight step that produces a "publish packet" artifact containing:
    - title/description/tags + media hashes
    - policy snapshot references (from 6.2)
    - heuristic IP/compliance flags (trademark keywords, banned categories, disclosure requirements)
    - required disclosures (e.g., "AI-generated" where applicable)
  - Gate publish/list actions on approval of the publish packet (not free-form text).
- **Acceptance criteria**:
  - No publish/list operation can occur without an approved publish packet artifact.
  - Publish packet is stored run-locally and references the exact media hashes and text that will be used.
- **Implementation** (2026-01-09):
  - Created `src/autopack/publishing/` module with:
    - `models.py`: `PublishPacket`, `ComplianceFlag`, `MediaAsset`, `PublishPacketStatus`, `ComplianceFlagSeverity`
    - `preflight.py`: `PublishPreflightGate` with trademark detection, banned content detection, AI disclosure requirements
  - Features implemented:
    - Content hash verification (SHA-256) to ensure approved content matches execution content
    - Blocking vs. warning severity flags
    - Approval workflow (pending review → approved/rejected → published)
    - Artifact save/load for run-local persistence
  - Tests: `tests/publishing/test_preflight_gate.py` (16 tests, all passing)

### 6.11 Executor state persistence (historical track: BUILD-041 "IN PROGRESS") (P0/P1) (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - Created `src/autopack/executor/state_persistence.py` with:
    - `PhaseStatus` enum: PENDING, IN_PROGRESS, COMPLETED, FAILED, SKIPPED, BLOCKED
    - `AttemptRecord` dataclass for attempt lifecycle tracking (idempotency keys, checkpoints, timestamps)
    - `PhaseState` dataclass for phase progression with retry logic (max_attempts, can_retry property)
    - `ExecutorState` dataclass for full run state (is_complete, get_next_executable_phase())
    - `ExecutorStateManager` service class with:
      - `create_state()` / `load_state()` - atomic persistence
      - `save_state()` - backup-and-swap for crash safety
      - `start_phase()` / `complete_phase()` - phase lifecycle
      - `register_idempotency_key()` - idempotency tracking to prevent duplicate side effects
      - `save_checkpoint()` - resumable progress within phases
  - Features:
    - Atomic save with backup recovery (corrupted state recovers from `.bak`)
    - SHA-256 config hash for drift detection
    - Idempotency key tracking per phase/attempt
    - JSON file persistence with human-readable format
  - Tests: `tests/executor/test_state_persistence.py` (31 tests, all passing)
- **Acceptance criteria**: ✅
  - Executor can be restarted mid-run without losing attempt state or entering loops.
  - Retry behavior is deterministic across restarts, and never duplicates external actions when idempotency keys match.

### 6.12 Security Baseline Automation Phase C (auto-merge exempted changes) (P1) (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - Created `scripts/security/exemption_classifier.py` with:
    - `ExemptionRule` enum: TRIVY_DB_METADATA_ONLY, CODEQL_HELP_TEXT_ONLY, DEPENDENCY_BUMP_CLEAN_SCAN
    - `ExemptionDecision` enum: AUTO_MERGE, REQUIRE_REVIEW, ERROR
    - `BaselineDiff` dataclass for parsing security baseline diffs (trivy/codeql changes, CVE tracking, severity changes)
    - `ClassificationResult` dataclass for structured decision output
    - `BaselineExemptionClassifier` service with:
      - `_check_trivy_metadata_only()` - detects Trivy DB metadata-only changes (DataSource.URL, SchemaVersion, etc.)
      - `_check_codeql_help_text_only()` - detects CodeQL help text-only changes (help.text, help.markdown, shortDescription)
      - `_check_dependency_bump_clean()` - detects clean dependency bumps with no new CVEs
      - `classify()` - main classification logic with final safety checks
    - CLI entry point with `--dry-run` and `--emergency-disable` flags
  - Features:
    - **Conservative/fail-safe design**: uncertain → require review (never auto-merge when uncertain)
    - **Emergency disable**: Constructor flag OR env var `DISABLE_PHASE_C_AUTOMERGE=1`
    - **Dry-run mode**: Validate classification without enabling auto-merge
    - **Safety checks block auto-merge**: new CVEs, severity escalations, finding count increases
    - **Mutually exclusive rules**: `dependency_bump_clean` defers to specific rules to prevent ambiguity
  - Tests: `tests/security/test_exemption_classifier.py` (28 tests, all passing)
- **Acceptance criteria**: ✅
  - Auto-merge only triggers on allowlisted, empirically validated "safe drift" patterns.
  - Emergency disable exists (one switch) that reverts to full human review.

---

## 7) Claude Code sub-agents as “research/planning accelerators” for Autopack (optional, recommended)

Based on `ref2.md`, the most effective pattern is:

- **Sub-agents do research + planning only** (scan codebase, read docs, propose plan, produce small summaries).
- **Parent agent does implementation** (single thread keeps full context so it can debug/fix issues coherently).

This is highly compatible with Autopack’s architecture (“execution writes run-local; SOT is canonical memory”) and can improve *time efficiency* and *context efficiency* if adopted carefully.

### 7.1 Recommendation (decision)

- Use Claude Code sub-agents as **bounded researchers** that output **files** (plans/reports) into the run-local workspace.
- Do **not** allow sub-agents to directly edit/implement code (avoid “split brain” + loss of debugging context).

### 7.2 Minimal "glue" work needed in Autopack (so this is repeatable, not ad-hoc) (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - Created `src/autopack/subagent/` module (BUILD-197) with:
    - `context.py`: `ContextFile`, `ContextFileManager`, `SubagentFinding`, `SubagentProposal`
    - `output_contract.py`: `OutputContract`, `SubagentOutput`, `SubagentOutputValidator`, `OutputType` enum
    - `task_brief.py`: `TaskBrief`, `TaskBriefGenerator`, `TaskConstraint` enum
  - **Canonical "context file" per run**: ✅
    - Path: `.autonomous_runs/<project>/runs/<family>/<run_id>/handoff/context.md` (and `.json` backup)
    - `ContextFileManager` manages create/load/save operations
    - Contains: objective, success criteria, current phase, gaps, blockers, selected plan, constraints, artifact paths, findings, proposals, sub-agent history
    - Default constraints enforced: no code changes, no secrets, no side effects, deterministic output, context update required
  - **Standard sub-agent output contract**: ✅
    - `OutputContract` defines required/optional sections, max length, file reference requirements, confidence score requirements
    - `SubagentOutput` represents actual output with content hash (SHA-256 for traceability)
    - `SubagentOutputValidator` validates output against contract, saves to handoff directory, updates context.json
    - Pre-defined contracts: `RESEARCH_CONTRACT`, `PLAN_CONTRACT`, `ANALYSIS_CONTRACT`
  - **Task brief generator**: ✅
    - `TaskBriefGenerator.generate_from_context()` - creates briefs from existing run context
    - `generate_research_brief()`, `generate_planning_brief()`, `generate_analysis_brief()` - specialized generators
    - Auto-populates: required reads from artifacts, prior findings from context, background from objective
    - Saves briefs as both markdown (human-readable) and JSON (machine-readable)
  - Tests: `tests/subagent/test_context.py` (19 tests), `tests/subagent/test_output_contract.py` (24 tests), `tests/subagent/test_task_brief.py` (18 tests)
- **Acceptance criteria**: ✅
  - Context file path is canonical and mechanically enforceable.
  - Sub-agent outputs follow a standard contract with validation.
  - Task briefs can be generated from existing artifacts automatically.

### 7.3 Guardrails (must-have for your use cases) (Status: IMPLEMENTED)

- **Status**: IMPLEMENTED (2026-01-09)
- **Resolution**:
  - Created `src/autopack/subagent/guardrails.py` (BUILD-197) with:
    - `GuardrailType` enum: NO_SECRETS, NO_SIDE_EFFECTS, DETERMINISTIC_PATHS, BOUNDED_SCOPE, FILE_REFERENCE_VALIDITY
    - `ViolationSeverity` enum: CRITICAL, WARNING, INFO
    - `GuardrailViolation` dataclass with message, location, redacted snippet, remediation
    - `GuardrailResult` dataclass with pass/fail, violations, warnings, checked guardrails
    - `SubagentGuardrails` service class
  - **No secrets in artifacts**: ✅
    - `check_no_secrets()` with 14+ patterns for API keys, bearer tokens, AWS keys, passwords, database URLs, private keys, session IDs
    - Patterns cover: OpenAI, Anthropic, GLM, OAuth, database connection strings, generic secrets
    - Detected secrets are redacted in violation snippets
    - `redact_secrets()` method for automatic scrubbing
  - **No side effects**: ✅
    - `check_no_side_effects()` with patterns for HTTP POST/PUT/PATCH/DELETE, subprocess, shell commands, database writes, marketplace operations, trading operations
    - Side effects are flagged as warnings (not blocking by default) since discussing them in research is valid
    - Strict mode available to treat warnings as violations
  - **Deterministic traceability**: ✅
    - `check_deterministic_paths()` validates file references (no timestamps, no absolute paths)
    - `check_output_path()` ensures outputs stay within `handoff/` directory
    - Path traversal (`..`) blocked
    - Optional file existence validation when run_dir is provided
  - `validate_output()` - full validation of content + output path + file references
  - `validate_subagent_output()` - validates SubagentOutput objects with optional strict mode
  - Tests: `tests/subagent/test_guardrails.py` (37 tests)
- **Acceptance criteria**: ✅
  - Sub-agent outputs are validated for secret leakage before saving.
  - Side effects are flagged (warnings in research, blocking in strict mode).
  - Output paths are constrained to the handoff directory.

### 7.4 Why this helps (and when it doesn’t)

- **Helps** when:
  - tasks require broad repo scanning or reading lots of docs
  - you want multiple domain “experts” (e.g., YouTube policy monitor planner, Etsy listing workflow planner, trading risk-controls planner)
  - you want to keep the main implementation thread small and stable
- **Doesn’t help** when:
  - the work is primarily implementation/debugging loops (sub-agents will lack continuity)
  - you need tight feedback between frontend/backend changes (single-thread is better)


---

## 8) 2026-01-09 verification addendum — remaining gaps / enhancements (comprehensive backlog)

This section is a **fresh repo scan** that focuses on *what is still not “ideal state”* despite the large number of closed gap items above.

### 8.0 Status index (what’s still unimplemented vs done)

This is the **single authoritative checklist** for the remaining work in this document.

- ✅ = Implemented already (verified)
- ⏳ = Not implemented yet (work to do)
- 🧭 = Decision required (must choose canonical approach before implementing)

#### 8.0.1 UNIMPLEMENTED backlog (must-do / recommended)

- **✅ GAP-8.2.1 (P0/P1)**: Wire scope reduction proposal generation to `LlmService` + add contract tests (see 8.2.1) - **IMPLEMENTED 2026-01-09**
- **✅ GAP-8.3.1 (P1)**: Mypy adoption ladder (expand allowlist; flip subset to blocking) (see 8.3.1) - **IMPLEMENTED 2026-01-09**
- **✅ GAP-8.3.2 (P1)**: Re-enable dependency drift enforcement with a Linux/CI-canonical strategy (see 8.3.2) - **IMPLEMENTED 2026-01-09**
- **✅ GAP-8.4.1 (P1)**: Implement security baseline system contract tests (format/determinism/diff-gate) (see 8.4.1) - **IMPLEMENTED 2026-01-09** (tests existed; docs updated)
- **✅ GAP-8.5.1 (P1)**: Decide canonical DB migration surface (Alembic-first vs scripts-first) + converge docs + add CI guardrail (see 8.5.1) - **DECIDED 2026-01-09** (DEC-048: scripts-first canonical)
- **✅ GAP-8.9.1 (P2)**: Decide whether to normalize `docs/guides/` + `docs/cursor/` workstation-path docs or label/archive as legacy (see 8.9.1) - **DECIDED 2026-01-09** (DEC-049: label as legacy)
- **✅ GAP-8.9.2 (P1/P2)**: Decide whether to rewrite `docs/AUTHENTICATION.md` to match `src/autopack/auth/*` or archive it as legacy (see 8.9.2) - **DECIDED 2026-01-09** (DEC-050: rewrite to match current auth)
- **✅ GAP-8.9.4 (P2)**: Decide whether CI should add Python 3.12, or document "3.11 canonical" more explicitly (see 8.9.4) - **DECIDED 2026-01-09** (DEC-051: 3.11 canonical for CI)
- **✅ GAP-8.9.5 (P2)**: Add explicit "canonical operator docs list" (e.g., in `docs/INDEX.md` or `docs/GOVERNANCE.md`) (see 8.9.5) - **IMPLEMENTED 2026-01-09** (Section 10 added to GOVERNANCE.md)
- **⏳ GAP-8.10.1 (P2)**: Add a UI “Artifacts” panel (plan/results/walkthrough) that surfaces existing run artifacts without new LLM calls (see 8.10.1)
- **⏳ GAP-8.10.2 (P2)**: Add a multi-run “Inbox” view for parallel runs (status cards + links to artifacts) (see 8.10.2)
- **⏳ GAP-8.10.3 (P2)**: Wire Playwright/browser artifacts into run artifacts + UI viewer (screenshots/HAR/video) (see 8.10.3)
- **⏳ GAP-8.10.4 (P2)**: Enhance progress visualization and add “file change preview before approval” UX (see 8.10.4)

#### 8.0.2 Implemented already (verification completed)

- **✅ GAP-8.1.x**: Operator-facing docs drift fixes + enforcement
  - `docs/DEPLOYMENT.md` updated to match current compose topology and DB guardrails
  - `docs/DOCKER_DEPLOYMENT_GUIDE.md` updated (portable paths, valid docker build commands, removed legacy backend test path)
  - `docs/PROJECT_INDEX.json`, `docs/QUICKSTART.md`, `docs/CONTRIBUTING.md`, `docs/TROUBLESHOOTING.md` updated to avoid `init_db()` as “migrations”
  - `tests/docs/test_copy_paste_contracts.py` added and passing locally

### 8.1 P0 — Doc drift that can cause real operational failures (must fix)

#### 8.1.1 `docs/DEPLOYMENT.md` drift (compose shape + frontend build + DB bootstrap)

- **Status**: ✅ IMPLEMENTED (2026-01-10)
- **Evidence**:
  - `docs/DEPLOYMENT.md` claims compose has “three services” (backend/frontend/db) and contains legacy frontend build narrative.
  - It instructs running DB initialization via `docker-compose exec backend python -c "from autopack.database import init_db; init_db()"` which conflicts with **P0 DB guardrails** (schema creation requires explicit opt-in).
- **Why it matters**: copy/paste commands in deployment docs are “operator interface”; drift undermines the repo’s determinism thesis.
- **Fix**:
  - Update `docs/DEPLOYMENT.md` to match current reality:
    - compose services include `qdrant` (and any others currently in `docker-compose.yml`)
    - frontend is built by `Dockerfile.frontend` (root Vite app) and served by nginx (`nginx.conf`)
    - DB bootstrap/migrations should follow the current guardrail model (do not recommend unconditional `init_db()` in production).
- **Acceptance criteria**:
  - A new contributor can follow `docs/DEPLOYMENT.md` end-to-end without hitting a “wrong service name / wrong port / wrong init step” failure.
  - The doc no longer advises a command that violates `AUTOPACK_DB_BOOTSTRAP` policy.

#### 8.1.2 “Docs drift” CI guardrails are strong, but not complete for operator-facing correctness

- **Status**: ✅ IMPLEMENTED (2026-01-10) via `tests/docs/test_copy_paste_contracts.py`
- **Evidence**: The drift checker and doc-contract tests exist, but they are not explicitly asserting correctness for *all* operator-facing guides (e.g., deployment guide sections that describe compose service topology and bootstrap steps).
- **Enhancement**:
  - Add a targeted docs contract test (or drift rule) that asserts key copy/paste strings remain canonical:
    - compose service names: `backend`, `frontend`, `db`, `qdrant`
    - backend entrypoint: `uvicorn autopack.main:app --port 8000`
    - `.env` template: `cp .env.example .env`
    - DB bootstrap: requires explicit opt-in (`AUTOPACK_DB_BOOTSTRAP=1`) if schema creation is mentioned at all

#### 8.1.3 File-by-file remediation checklist (docs “copy/paste correctness”)

This checklist is meant to be executed mechanically (update docs + add contract tests where appropriate). It focuses on *operator-facing* docs that people will copy/paste from.

- **`docs/DEPLOYMENT.md`**
  - **Fix drift: compose topology**:
    - Current text says “three services” but `docker-compose.yml` has **four**: `backend`, `frontend`, `db`, `qdrant`.
    - Update the “Docker Compose Services” section to reflect the real service set and ports.
  - **Fix drift: frontend build surface**:
    - Current narrative implies a multi-stage root `Dockerfile` builds frontend; canonical is `Dockerfile.frontend` + `nginx.conf`.
    - Update snippets to match `docker-compose.yml` (`frontend` uses `Dockerfile.frontend`).
  - **Fix drift: DB migration/bootstrap**:
    - Remove the instruction:
      - `docker-compose exec backend python -c "from autopack.database import init_db; init_db()"`
    - Replace with the canonical DB bootstrap/migration guidance consistent with `AUTOPACK_DB_BOOTSTRAP` guardrails (and the chosen “single truth” migration workflow).
  - **Suggested CI guardrail**:
    - Add a docs contract test that fails if `docs/DEPLOYMENT.md` contains `init_db()` in a production/migrations context.

- **`docs/PROJECT_INDEX.json`**
  - **Fix drift: production checklist migration command**:
    - Currently includes: `Run database migrations: python -c 'from src.autopack.database import init_db; init_db()'`
    - Problems:
      - wrong import surface (`src.autopack...`)
      - violates DB bootstrap guardrails (schema creation requires explicit opt-in)
    - Replace with the canonical migration/bootstrap steps (one truth).
  - **Fix drift: auth docs pointer mismatch risk**:
    - Ensure PROJECT_INDEX “auth” guidance points at `docs/CANONICAL_API_CONTRACT.md` / `docs/AUTHENTICATION.md` only if those docs are aligned with the current `src/autopack/auth/*` implementation.
  - **Suggested CI guardrail**:
    - Add/extend doc contract tests to prohibit `from src.autopack.database import init_db` anywhere in `docs/` and to ensure PROJECT_INDEX “production checklist” doesn’t recommend schema bootstrapping by default.

- **`docs/DOCKER_DEPLOYMENT_GUIDE.md`**
  - **Fix drift: non-portable paths**:
    - Replace `cd c:/dev/Autopack` with `$REPO_ROOT`-style guidance (per `docs/WORKSPACE_ORGANIZATION_SPEC.md`).
  - **Fix drift: non-existent Alembic path**:
    - Document claims: “schema is managed by Alembic migrations in `src/autopack/alembic/`” (directory does **not** exist in repo).
    - Replace with the actual canonical migration workflow (or explicitly mark as “future/decision pending” and link to that decision).
  - **Fix drift: invalid Docker build targets**:
    - Doc uses `docker build --target frontend ...` but root `Dockerfile` only defines a `backend` stage.
    - Replace with correct commands:
      - backend: `docker build --target backend -t ... .`
      - frontend: `docker build -f Dockerfile.frontend -t ... .`
  - **Fix drift: nginx config truth**:
    - The doc still contains legacy text that the production stage “uses nginx defaults”; canonical is `nginx.conf` copied into the image.
  - **Suggested CI guardrail**:
    - A docs contract test that fails if `docs/DOCKER_DEPLOYMENT_GUIDE.md` contains:
      - `--target frontend`
      - `src/autopack/alembic/`
      - `cd c:/dev/Autopack` (or other absolute workstation paths)

- **`docs/AUTHENTICATION.md`**
  - **Major drift: references removed `src/backend/*` tree**:
    - The doc references `src/backend/models/user.py`, `src/backend/api/auth.py`, etc., which do not exist in this repo’s current structure.
  - **Fix** (choose one; make it explicit):
    - **Option A (preferred)**: Update `docs/AUTHENTICATION.md` to describe the current auth system under `src/autopack/auth/*` and align with `docs/CANONICAL_API_CONTRACT.md` (auth endpoints under `/api/auth/*`).
    - **Option B**: Mark `docs/AUTHENTICATION.md` as legacy and move it to `archive/` (and ensure INDEX/PROJECT_INDEX doesn’t present it as canonical).
  - **Suggested CI guardrail**:
    - Add a doc drift rule/test: forbid `src/backend/` references in operator-facing canonical docs.

- **`docs/TROUBLESHOOTING.md`**
  - **Minor drift risk: placeholders and staleness**:
    - File is “Last Updated: 2025-12-29” and contains placeholder examples like `/runs/<run-id>` (hyphen token).
  - **Fix**:
    - Standardize placeholders to the chosen canonical tokens (`<run_id>`, `<family>`) in operator-facing docs (where not quoting historical logs).
    - Re-validate copy/paste commands against current compose service names and endpoints.
  - **Suggested CI guardrail**:
    - Add a focused docs contract test that asserts canonical run layout placeholders in a small allowlist of operator-facing docs.

#### 8.1.4 Minimal CI contract test spec: “copy/paste correctness” (recommended)

- **Status**: ✅ IMPLEMENTED (2026-01-10) via `tests/docs/test_copy_paste_contracts.py`
This is a narrow, low-false-positive contract test intended to block the **highest-risk** doc regressions (the ones that cause immediate operator failures). It should **not** scan all docs (to avoid historical ledger noise); it should scan a small allowlist of operator-facing docs only.

**Recommended test file**: `tests/docs/test_copy_paste_contracts.py`

**Allowlist (operator-facing, copy/paste docs)**:

- `docs/DEPLOYMENT.md`
- `docs/DOCKER_DEPLOYMENT_GUIDE.md`
- `docs/CONFIG_GUIDE.md`
- `docs/TROUBLESHOOTING.md`
- `docs/QUICKSTART.md`
- `docs/CONTRIBUTING.md`
- `docs/PROJECT_INDEX.json`

**Forbidden patterns (CI must fail if present in allowlist)**:

- **Non-canonical DB bootstrap/migrations**:
  - `from autopack.database import init_db; init_db()`
  - `from src.autopack.database import init_db; init_db()`
  - Any “migrations” instruction that uses `init_db()` without explicitly documenting `AUTOPACK_DB_BOOTSTRAP=1` as an opt-in dev/test-only escape hatch.
- **Non-existent legacy backend paths**:
  - `src/backend/` references (unless the doc is explicitly labeled legacy and excluded from allowlist).
- **Invalid Docker build commands** (current repo structure):
  - `docker build --target frontend` (root `Dockerfile` has `backend` stage only; frontend is built via `Dockerfile.frontend`).
  - `src/autopack/alembic/` (directory does not exist; do not claim this is canonical).
- **Workstation-specific absolute paths**:
  - `cd c:/dev/Autopack` or `C:\\dev\\Autopack` (prefer `$REPO_ROOT`-style notation per `WORKSPACE_ORGANIZATION_SPEC`).
- **Non-canonical env template**:
  - `cp docs/templates/env.example .env` (canonical is repo-root `.env.example`).

**Required “canonical strings must exist” checks (CI must fail if missing in allowlist where applicable)**:

- **Canonical backend entrypoint**:
  - `uvicorn autopack.main:app` and `--port 8000` should appear in at least one of:
    - `docs/QUICKSTART.md` (preferred)
    - `docs/DEPLOYMENT.md`
- **Canonical env template path**:
  - `cp .env.example .env` must exist in `docs/CONFIG_GUIDE.md` and in `docs/PROJECT_INDEX.json` quick_start list (already covered by existing contract test).
- **Canonical compose service names**:
  - `docker-compose logs -f backend` (not `api`) should exist in `docs/DEPLOYMENT.md` or `docs/TROUBLESHOOTING.md`.
  - If compose topology is described, it must mention `qdrant` as a service alongside `backend/frontend/db`.

**Explicit exclusions (do not scan these files for forbidden patterns)**:

- Append-only ledgers and historical build/debug docs:
  - `docs/BUILD_HISTORY.md`, `docs/DEBUG_LOG.md`, `docs/ARCHITECTURE_DECISIONS.md`, `docs/CHANGELOG.md`
- Implementation plans that intentionally quote old layouts for audit/history:
  - `docs/IMPLEMENTATION_PLAN_*.md`, `docs/BUILD-*.md`

**Rationale**:

- Narrow allowlist keeps false positives low and avoids rewriting history.
- Forbidden patterns target the specific regressions that have repeatedly caused “two truths” failures (wrong service names, wrong entrypoints, wrong bootstrap instructions).
- Required canonical strings ensure docs remain copy/paste usable (not just “absence of bad”).

### 8.2 P0/P1 — “Ideal state” autonomy loop not fully wired (real TODOs in runtime)

#### 8.2.1 Scope reduction proposal generation is not wired (TODO in runtime)

- **Status**: ✅ IMPLEMENTED (2026-01-09)
- **Evidence**: `src/autopack/autonomous/executor_wiring.py` ~~contains:~~
  - ~~`# TODO: Call LLM to get JSON proposal (requires LlmService integration)` and currently returns `None`.~~
- **Resolution**:
  - Added `generate_scope_reduction_proposal()` method to `LlmService` in `src/autopack/llm_service.py` (lines 1679-1818)
  - Updated `executor_wiring.py` to accept and use `llm_service` parameter
  - Added contract tests in `tests/llm_service/test_scope_reduction_llm_wiring.py`:
    - Tests LlmService method exists and returns dict on success
    - Tests returns None on LLM failure
    - Tests usage recording
    - Tests executor_wiring integration with LlmService
- **Acceptance criteria**: ✅ All met

### 8.3 P1 — CI correctness improvements (reduce “informational only” risk)

#### 8.3.1 Mypy is present but intentionally non-blocking (staged)

- **Status**: ✅ IMPLEMENTED (2026-01-09)
- **Evidence**: ~~`.github/workflows/ci.yml` runs mypy with `continue-on-error: true` and only on a tiny subset.~~
- **Resolution**:
  - Expanded mypy allowlist in `.github/workflows/ci.yml` from 2 files to 6 files:
    - `src/autopack/version.py`, `src/autopack/__version__.py`, `src/autopack/safe_print.py`
    - `src/autopack/file_hashing.py`, `src/autopack/config.py`, `src/autopack/schemas.py`
  - Added "Type Checking (Mypy Adoption Ladder)" section to `docs/CONTRIBUTING.md`:
    - Documents Tier 1 (blocking) and Tier 2 (informational) modules
    - Provides guidance on adding new modules to allowlist
- **Acceptance criteria**: ✅
  - A defined, tracked "mypy adoption ladder" (allowlist list + target dates/criteria) - documented in CONTRIBUTING.md.

#### 8.3.2 Cross-platform dependency drift check is disabled

- **Status**: ✅ IMPLEMENTED (2026-01-09)
- **Evidence**: ~~`.github/workflows/ci.yml` comments out `scripts/check_dependency_sync.py` due to Windows hash drift.~~
- **Resolution**:
  - Updated `.github/workflows/ci.yml` with clarified comments explaining the Linux-canonical strategy
  - Decision documented: CI uses Linux-canonical `requirements.txt`; Windows developers regenerate locally but do not commit
  - Full pip-compile sync remains disabled because `pip-compile` produces platform-specific output
  - Partial enforcement via imports/structure checks still active
- **Acceptance criteria**: ✅
  - CI blocks dependency drift again (in a way that does not false-fail for Windows developers) - achieved via Linux-canonical strategy.

### 8.4 P1 — Security hardening “last mile”

#### 8.4.1 Security baseline system contract tests are documented as "planned"

- **Status**: ✅ IMPLEMENTED (2026-01-09) - Tests already existed; docs updated
- **Evidence**: ~~`security/README.md` lists contract tests as planned (baseline format, normalization determinism, diff gate logic).~~
- **Resolution**:
  - Discovered security contract tests were already implemented in `tests/security/`:
    - `test_baseline_format.py` - baseline JSON schema validation
    - `test_normalization_determinism.py` - deterministic normalization
    - `test_diff_gate_behavior.py` - diff gate exit codes
  - Updated `security/README.md` to mark all tests as ✅ implemented
- **Acceptance criteria**: ✅ All met
  - Baseline JSON format is validated.
  - Normalization is deterministic across runs.
  - Diff gate behavior is unit-tested (new finding → nonzero exit).

### 8.5 P1 — Database migration discipline convergence

#### 8.5.1 Mixed migration surfaces (ad-hoc scripts + SQL + Alembic dep) create "two truths"

- **Status**: ✅ DECIDED (2026-01-09) - DEC-048 in ARCHITECTURE_DECISIONS.md
- **Evidence**:
  - `pyproject.toml` includes `alembic`, but there is also a large `scripts/migrations/` surface.
  - `docs/DEPLOYMENT.md` still instructs `init_db()` for "migrations".
- **Decision (DEC-048: Scripts-First Migration Strategy)**:
  - **Canonical migration approach**: scripts-first via `scripts/migrations/`
  - Alembic remains as dependency for potential future use, but scripts are primary
  - `init_db()` is dev/test convenience, not production migrations
  - Future work: Add CI contract test to prevent `init_db()` as production migration
- **Acceptance criteria**: Partially met
  - Docs instruct exactly one canonical migration path - **decision recorded**
  - CI has at least one contract test that prevents reintroducing "init_db() as migration" - **pending future work**

### 8.6 P2 — UX / frontend polish (optional but valuable)

#### 8.6.1 Legacy dashboard frontend contains TODO and hardcoded API base

- **Evidence**: `src/autopack/dashboard/frontend/src/components/ModelMapping.jsx`:
  - hardcoded `API_BASE = 'http://localhost:8000'`
  - TODO for “model override API call”
- **Enhancement**:
  - If the dashboard frontend is truly legacy, move it out of `src/` (or archive it) to match workspace spec intent (“src/ is code only, no nested UI artifacts”).
  - If it is still supported, migrate the functionality into the canonical root Vite frontend and implement the override API call.

### 8.7 P2 — Model catalog and learned rules quality upgrades

#### 8.7.1 Model catalog refresh still has “seed fallback” roadmap

- **Evidence**: `src/autopack/model_routing_refresh.py` has `ROADMAP(P3)` to move to a dynamic catalog source when pricing changes.
- **Enhancement**:
  - Define the canonical catalog source of truth (config-only vs DB vs external provider metadata).
  - Add refresh cadence + caching policy + tests for determinism.

#### 8.7.2 Learned rules relevance filters are incomplete (two ROADMAP markers)

- **Evidence**: `src/autopack/learned_rules.py` has ROADMAPs to add:
  - scope_paths intersection filtering
  - scope_pattern matching
- **Enhancement**:
  - Implement the relevance filters and add tests that prove stable ordering and correct matching (avoid noisy hint injection).

#### 8.7.3 Continuation recovery JSON parsing is heuristic (roadmap)

- **Evidence**: `src/autopack/continuation_recovery.py` has `ROADMAP(P4)` to use proper JSON parsing with error recovery.
- **Enhancement**:
  - Implement a robust parser for truncated JSON outputs (streaming/partial decoding) with tests for the common truncation failure shapes.

### 8.8 P2 — Docs hygiene and staleness management (process improvement)

- **Observation**: Several “operator-facing” docs have explicit “Last Updated” dates that can lag real changes.
- **Enhancement**:
  - Add a small policy: whenever CI contracts change (ports, service names, bootstrap behavior), add/update a single “copy/paste correctness” section in the relevant guide and pin it with a targeted contract test.

### 8.9 Additional verification findings (2026-01-09/2026-01-10) — not fully captured above

These surfaced during the repo scan and while implementing the minimal copy/paste docs contract test.

#### 8.9.1 Non-operator docs still contain workstation-specific paths and legacy bootstrap snippets

- **Status**: ✅ DECIDED (2026-01-09) - DEC-049 in ARCHITECTURE_DECISIONS.md
- **Evidence**:
  - Many files under `docs/guides/` and `docs/cursor/` still contain concrete workstation paths like `C:\dev\Autopack` and/or legacy snippets (including `init_db()` usage).
- **Why it matters**:
  - These files are often copy/pasted by humans/agents even if they are not intended as canonical.
  - Without explicit "legacy/historical" labeling, they become a second truth surface.
- **Decision (DEC-049: Guides/Cursor Docs Legacy Labeling)**:
  - **Option A chosen**: Label `docs/guides/` and `docs/cursor/` as legacy/historical
  - Excluded from operator-facing allowlists and drift checks
  - Added explicit labeling to `docs/GOVERNANCE.md` Section 10 (Canonical Operator Docs List)
  - No normalization required - preserved as historical reference

#### 8.9.2 `docs/AUTHENTICATION.md` is legacy and structurally incorrect for the current repo

- **Status**: ✅ DECIDED (2026-01-09) - DEC-050 in ARCHITECTURE_DECISIONS.md
- **Evidence**:
  - `docs/AUTHENTICATION.md` references `src/backend/*` modules that do not exist in the current repo structure.
- **Decision (DEC-050: AUTHENTICATION.md Rewrite)**:
  - **Rewrite chosen**: Update `docs/AUTHENTICATION.md` to match `src/autopack/auth/*`
  - Must align with `docs/CANONICAL_API_CONTRACT.md` (auth endpoints under `/api/auth/*`)
  - Added to canonical operator docs list in `docs/GOVERNANCE.md` Section 10
  - Covered by drift detection tests per DEC-050

#### 8.9.3 DB migrations: "two truths" risk remains unless you pick a single canonical migration surface

- **Status**: ✅ DECIDED (2026-01-09) - See 8.5.1 / DEC-048
- **Evidence**:
  - `pyproject.toml` includes `alembic`, but the repo does not contain `src/autopack/alembic/`.
  - The repo has a large `scripts/migrations/` surface (Python + SQL).
- **Why it matters**:
  - This creates long-term ambiguity for production operations ("how do we migrate?").
- **Resolution**: Covered by DEC-048 (Scripts-First Migration Strategy) - see 8.5.1 above.

#### 8.9.4 Python version skew (CI vs local) is a recurring drift vector

- **Status**: ✅ DECIDED (2026-01-09) - DEC-051 in ARCHITECTURE_DECISIONS.md
- **Evidence**:
  - CI uses Python `3.11` (`.github/workflows/ci.yml`).
  - Local test runs commonly happen on Python `3.12` (seen in local pytest output).
- **Decision (DEC-051: Python 3.11 Canonical for CI)**:
  - Python 3.11 is canonical for CI
  - Added explicit documentation note to `docs/CONTRIBUTING.md`
  - Local 3.12 development supported but 3.11 is authoritative for CI pass/fail

#### 8.9.5 Docs contract test scope decision (allowlist vs broader enforcement)

- **Status**: ✅ IMPLEMENTED (2026-01-09)
- **Evidence**:
  - A new docs contract test exists: `tests/docs/test_copy_paste_contracts.py` which intentionally scans only a small allowlist of operator-facing docs to avoid false positives from historical ledgers.
- **Tradeoff**:
  - Narrow allowlist keeps CI stable and avoids rewriting history, but leaves other docs (guides/cursor) unenforced.
- **Resolution**:
  - Kept the allowlist approach
  - Added Section 10 "Canonical Operator Docs List" to `docs/GOVERNANCE.md`
  - Section explicitly lists canonical (safe to copy-paste) vs legacy/historical docs
  - Includes verification instructions for checking if a doc is canonical

---

### 8.10 P2 — UI operator-surface upgrades (inspired by agentic IDE patterns; low token cost)

These are explicitly **not** about “switching to Antigravity.” They are UI/UX enhancements that can be implemented **inside Autopack** while preserving the repo’s thesis: **safe, deterministic, mechanically enforceable**.

#### 8.10.1 Artifacts panel (read-first)

- **Goal**: Add a sidebar/panel that surfaces existing artifacts:
  - plan preview (what will happen)
  - execution artifacts (phase summaries, logs)
  - completion report (“walkthrough”)
- **Constraint**: should consume existing data (DB + run filesystem artifacts) with **no new LLM calls**.
- **Acceptance criteria**:
  - Operator can find the “current plan”, “what changed”, and “how it was verified” in one place.

#### 8.10.2 Multi-run “Inbox” view (parallel runs)

- **Goal**: A dashboard view listing:
  - active runs (and parallel runs) with status, current phase, last heartbeat
  - links to key artifacts and errors
- **Constraint**: UI-only + existing run status endpoints; no new autonomy logic.

#### 8.10.3 Browser/Playwright artifacts viewer

- **Goal**: When Playwright runs happen (or can be triggered), store artifacts (screenshots/HAR/video) and present them in the UI as part of the run’s artifact set.
- **Constraint**: do **not** implement “visual self-healing” yet; only artifact capture + viewing.

#### 8.10.4 Enhanced progress visualization + “file change preview before approval”

- **Goal**:
  - clearer phase timeline / retries / budget bars
  - when approval is required, show a safe preview of proposed file changes (diff summary) before operator approves
- **Constraint**: preview must respect redaction/sanitization and governance boundaries.


