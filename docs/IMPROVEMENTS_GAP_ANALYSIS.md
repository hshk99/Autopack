# Autopack — Comprehensive Improvement / Gap Analysis (vs README “ideal state” + WORKSPACE_ORGANIZATION_SPEC + beyond)

**Last Verified**: 2026-01-07  
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
- **Missing expected scaffolding**:
  - `.env.example` **does not exist** (but is referenced in `docs/PROJECT_INDEX.json`)
  - `.github/dependabot.yml` **does not exist** (but multiple docs/comments imply automated updates)
  - `docs/api/` does not exist (allowed by spec and referenced by multiple docs)
  - `docker-compose.prod.yml` does not exist (referenced as a pattern/idea in docs/comments)
- **TODO density (quick scan)**:
  - `src/`: 19 TODOs (12 in `src/autopack/autonomous_executor.py`)
  - `scripts/`: 51 TODOs
  - `tests/`: 2 TODOs

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

---

## 1) P0 — “Ideal state” violations / high-confidence breakages

### 1.1 `docker-compose.dev.yml` is broken (wrong services + wrong command + missing build target)

- **Evidence**: `docker-compose.dev.yml`
  - References `build.target: development` (no `development` stage in `Dockerfile`)
  - Uses `uvicorn src.backend.main:app` (backend is `autopack.main:app`)
  - Overrides a non-existent service `postgres:` (base compose uses `db:`)
- **Why it matters**: The repo advertises safe, deterministic operation. A broken dev compose path undermines “mechanically enforceable” + “easy local reproduction”.
- **Recommended fix**:
  - Either delete `docker-compose.dev.yml` (if not supported) or make it a valid override for `docker-compose.yml`:
    - target correct service name (`db`) and correct uvicorn app (`autopack.main:app`)
    - if “development image” is desired, add a `development` stage to `Dockerfile` (or remove `target:`).
- **Acceptance criteria**:
  - `docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build` works from a clean clone.

### 1.2 `Dockerfile.frontend` will not build the root frontend output as configured

- **Evidence**:
  - `vite.config.ts` outputs to `dist/frontend`
  - `Dockerfile.frontend` copies `/app/dist` → nginx html
- **Why it matters**: This is a deterministic, reproducible build contract gap.
- **Recommended fix** (choose one):
  - Update `vite.config.ts` back to `outDir: "dist"` (standard), **or**
  - Update `Dockerfile.frontend` to copy `/app/dist/frontend`.
- **Acceptance criteria**:
  - `docker build -f Dockerfile.frontend .` succeeds from a clean clone and serves the app.

### 1.3 “Two frontends” is currently an unclear product contract (and one lives under `src/`)

- **Evidence**: `src/frontend/…` and `src/autopack/dashboard/frontend/…`
- **Why it matters**:
  - Creates “two truths” for operators and agents (“which UI is canonical?”).
  - The dashboard frontend’s **local artifacts** (`node_modules/`, `dist/`) sitting under `src/` violate `docs/WORKSPACE_ORGANIZATION_SPEC.md` intent (“src is code only”), even if they’re untracked.
- **Recommended fix**:
  - Decide the canonical UI:
    - If **root Vite** is canonical: migrate dashboard features into `src/frontend`, and remove `src/autopack/dashboard/frontend` (or move it to `archive/experiments/`).
    - If **dashboard** is canonical: move it to repo root `frontend/` (per workspace spec), wire Docker/CI/docs to it, and delete the root Vite frontend.
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

### 1.5 Broad docs drift: compose service names and legacy commands are still present

- **Evidence**:
  - `docs/PARALLEL_RUNS.md` uses `docker-compose up -d postgres` but service is `db`.
  - `docs/BUILD_HISTORY.md` contains archived instructions `docker-compose logs -f api` (service is `backend`).
  - Some guides still reference legacy/incorrect uvicorn entrypoints (e.g. `autopack.api.server:app` or `uvicorn src.autopack.main:app`) while the canonical contract is `PYTHONPATH=src uvicorn autopack.main:app`.
- **Why it matters**: even if CI is strong, docs are part of the “mechanically enforceable” operator contract. Wrong commands = wasted time + broken reproducibility.
- **Recommended fix**:
  - Run a “docs drift sweep” (scripted) that replaces known-bad patterns with canonical equivalents:
    - `postgres` → `db`
    - `api` → `backend` (for compose service naming)
    - `uvicorn src.autopack.main:app` → `PYTHONPATH=src uvicorn autopack.main:app`
    - quarantine truly-legacy commands in one explicitly labeled “legacy” section (so greps don’t keep reintroducing them)
- **Acceptance criteria**:
  - `grep -R "docker-compose up -d postgres" docs/` returns empty.
  - `grep -R "docker-compose logs -f api" docs/` returns empty.
  - The only references to legacy uvicorn targets are in a single “legacy” section (or removed entirely).

### 1.6 Missing dependency update automation: Dependabot config is absent (but implied elsewhere)

- **Evidence**:
  - No `.github/dependabot.yml`
  - Comments/docs imply it exists (e.g., Dockerfile notes “Dependabot monitors Docker images”)
- **Why it matters**: SHA pins + security baselines become manual toil; pins and deps will stale-drift.
- **Recommended fix**:
  - Add `.github/dependabot.yml` for:
    - `github-actions` (workflow pins)
    - `pip` (requirements/pyproject strategy)
    - `npm` (root frontend, and dashboard frontend if retained)
- **Acceptance criteria**:
  - Scheduled Dependabot PRs land for all 3 ecosystems with sane grouping/cadence.

### 1.7 Secret redaction bug: hyphenated sensitive header keys may not be redacted

- **Evidence**: `src/autopack/sanitizer.py`
  - `_is_sensitive_key()` normalizes keys by replacing `-` with `_`, but `SENSITIVE_HEADERS` contains many hyphenated header names (e.g., `x-api-key`, `set-cookie`).
  - Result: keys like `X-API-Key` / `Set-Cookie` can evade the direct membership test and be persisted in error artifacts.
- **Why it matters**: Autopack explicitly persists error artifacts to disk under `.autonomous_runs/…/errors/…`. Any redaction bug is a P0 security gap.
- **Recommended fix**:
  - Normalize `SENSITIVE_HEADERS`/`SENSITIVE_KEYS` into the same canonical form used by `_is_sensitive_key()` (or stop mutating the input key and compare using a consistent normalization function).
  - Add contract tests proving redaction for `Authorization`, `Cookie`, `Set-Cookie`, `X-API-Key`, `X-GitHub-Token`, etc., including mixed case and hyphen/underscore variants.
- **Acceptance criteria**:
  - Unit tests demonstrate that both `"X-API-Key"` and `"x_api_key"` keys are redacted.
  - Error reports never persist raw values for sensitive headers/keys.

### 1.8 Production auth posture gap: API key auth is “open” when `AUTOPACK_API_KEY` is unset

- **Evidence**: `src/autopack/main.py` `verify_api_key()` returns `None` (allows access) when `AUTOPACK_API_KEY` is not set.
- **Why it matters**: In `AUTOPACK_ENV=production`, the API should not be accidentally runnable unauthenticated.
- **Recommended fix**:
  - In production mode, fail fast if `AUTOPACK_API_KEY` is not set (or require JWT auth for non-public endpoints).
  - Ensure docs clearly state “dev can be open; prod must be authenticated”.
- **Acceptance criteria**:
  - With `AUTOPACK_ENV=production` and no API key configured, startup fails clearly.

### 1.9 Root frontend CI is likely broken: `npm ci` runs but there is no root `package-lock.json`

- **Evidence**:
  - `.github/workflows/ci.yml` runs `npm ci` in the repo root (`frontend-ci` job).
  - There is **no** root `package-lock.json` (the only `package-lock.json` present is under `src/autopack/dashboard/frontend/`).
- **Why it matters**: `npm ci` requires a lockfile. If the repo’s canonical frontend is the root Vite app, CI is currently failing and builds are not deterministic.
- **Recommended fix** (choose one):
  - **Preferred**: generate and commit root `package-lock.json` and keep it in sync with `package.json`.
  - **Alternative**: change CI from `npm ci` → `npm install` (less deterministic), or repoint the CI job to the dashboard frontend and treat it as canonical.
- **Acceptance criteria**:
  - Frontend CI passes from a clean checkout, and root frontend builds deterministically.

### 1.10 Docker/compose frontend does not match the “root frontend” (and does not use `nginx.conf`)

- **Evidence**:
  - `docker-compose.yml` `frontend` builds `Dockerfile` with no target (uses the final nginx stage).
  - `Dockerfile`’s frontend build stage uses `src/autopack/dashboard/frontend/` (dashboard UI), not `src/frontend/`.
  - `nginx.conf` (with `/api` proxy + security headers) is only copied by `Dockerfile.frontend`, not by the nginx stage in `Dockerfile`.
- **Why it matters**: This creates “three truths”:
  - CI frontend job targets the root app
  - docker-compose serves the dashboard app
  - nginx proxy/security headers are defined in `nginx.conf` but may not be active in compose
- **Recommended fix**:
  - Decide canonical frontend and converge CI + Docker + docs:
    - If root app is canonical: make compose build `Dockerfile.frontend` (or update `Dockerfile` to build root app and copy `nginx.conf`).
    - If dashboard is canonical: update CI to lint/typecheck/build `src/autopack/dashboard/frontend` and stop treating root `package.json` as canonical.
- **Acceptance criteria**:
  - `docker-compose up --build` serves the same UI that CI builds, and `/api` proxy behavior matches docs.

### 1.11 Port mismatch: README runs API on 8100 while Docker/compose + most docs use 8000

- **Evidence**:
  - `README.md` suggests `python -m uvicorn autopack.main:app … --port 8100`.
  - `Dockerfile`/`docker-compose.yml` expose 8000 and most docs use `http://localhost:8000`.
- **Why it matters**: breaks the “single canonical contract” for operators and agents.
- **Recommended fix**:
  - Pick one canonical port (likely 8000, since docker-compose + docs are already on 8000) and update README/examples accordingly.
- **Acceptance criteria**:
  - README, docs, docker-compose, and examples all use the same default API port.

### 1.12 Legacy backend path references still exist in core logic (planning/scanning/prompting)

- **Evidence**:
  - `src/autopack/autonomous_executor.py` still includes default allowed paths like `src/backend/` and `src/frontend/` (FileOrganizer legacy).
  - `src/autopack/repo_scanner.py` / `src/autopack/pattern_matcher.py` include legacy path heuristics like `backend/api`.
  - `src/autopack/anthropic_clients.py` prompt instructions still cite `src/backend/api/health.py` as a canonical example path.
- **Why it matters**: Autopack itself no longer has a `src/backend/` app, so these heuristics/prompt examples create noise and can cause mis-targeted patches in autonomous runs.
- **Recommended fix**:
  - Separate “Autopack repo defaults” from “external project templates”:
    - Autopack should default to `src/autopack/…` (and root frontend if retained).
    - FileOrganizer/other projects can have their own templates/allowed paths and repo scanners.
  - Add a small contract test that ensures Autopack runs never propose edits under non-existent default roots (e.g., `src/backend/` in this repo).
- **Acceptance criteria**:
  - No Autopack-core prompts or default allowed-path sets reference `src/backend/` unless explicitly in a project-template context.

### 1.13 `python -m autopack` entrypoint is unrelated to Autopack (Canada document classifier demo)

- **Evidence**:
  - `src/autopack/__main__.py` runs a `CanadaDocumentClassifier` demo, which is unrelated to Autopack’s build framework.
  - The real CLI surface appears to be under `src/autopack/cli/` (and `src/autopack/cli/__main__.py` exists).
  - `pyproject.toml` does not define `console_scripts` / `[project.scripts]` entrypoints.
- **Why it matters**: `python -m autopack` is a natural “what is this package?” entrypoint. If it runs unrelated demo code, it undermines trust and confuses agents/operators.
- **Recommended fix**:
  - Replace `src/autopack/__main__.py` with a thin delegate to the canonical CLI (e.g., `autopack.cli`), and/or print help text.
  - Add a proper console script in `pyproject.toml` (e.g., `autopack = autopack.cli.main:main`) so users can run `autopack ...` after install.
- **Acceptance criteria**:
  - `python -m autopack --help` shows Autopack CLI/help (not unrelated demos).
  - `pip install -e .` provides an `autopack` command (if desired).

---

## 2) P1 — Major hardening / determinism / completeness

### 2.1 Executor TODO closures that affect determinism and governance correctness

**Hotspot**: `src/autopack/autonomous_executor.py` (12 TODOs remaining). High-value closures:

- **Usage accounting**: track actual tokens/context usage in the LLM execution path (today: placeholder counters).
- **Scope reduction**: implement `REDUCE_SCOPE` prompt generation + validation (today: fallback).
- **Coverage delta**: wire coverage delta computation (CI produces coverage.xml; executor still returns 0.0).
- **Model overrides propagation**: `run_context` includes overrides but TODO says “pass model_overrides”.
- **Changed-files extraction**: executor currently sets `changes = []` (loses auditability and quality gate signal).
- **Auditor result enrichment**: suggested patches + confidence parsing are TODO.
- **Approval flow**: Telegram approval flow integration is TODO (currently fails to manual approval path).
- **Quality report files list**: `files: []` TODO.
- **Deletion “context” derivation**: hardcoded `"troubleshoot"` TODO.
- **Automatic retry with LLM correction**: TODO.

**Acceptance criteria**:
- Each TODO closure has a contract test proving behavior and preventing regression (especially changed-files, approval flow, and scope reduction).

### 2.2 TODO hotspots: remaining placeholders concentrate in executor + several operational scripts

- **Evidence (quick inventory)**:
  - `src/autopack/autonomous_executor.py`: 12 TODOs (governance, determinism, reporting)
  - `scripts/ci/check_sot_hygiene.py`: 13 TODO/FIXME markers (mostly report-only heuristics)
  - `scripts/pattern_expansion.py`: 9 TODO/FIXME markers (generator logic)
  - `scripts/ci/check_security_baseline_log_entry.py`: 8 TODO/FIXME markers (policy checks)
  - `scripts/pre_publish_checklist.py`: 4 TODO/FIXME markers (release-readiness checks)
  - `scripts/integrations/*`: multiple TODOs (explicitly stubbed integrations)
- **Why it matters**: Autopack’s pitch is “safe + deterministic + mechanically enforceable”. TODOs in the executor and CI policy scripts are directly on that critical path.
- **Recommended fix**:
  - Convert the remaining TODOs into a tracked “closure plan” (build doc or FUTURE_PLAN entries) with:
    - “must close” (executor determinism/governance/security)
    - “nice to have” (dev tooling, generators)
  - For each “must close”, add/extend tests so the behavior is enforced.
- **Acceptance criteria**:
  - Critical-path TODO count trends toward zero, with tests proving the closure.

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

### 2.4 Local workspace hygiene: root contains many untracked seed DBs (spec says route them)

- **Evidence**: repo root contains multiple `telemetry_seed_*.db` / `autopack_telemetry_seed*.db` files in the current workspace (untracked).
- **Why it matters**: even untracked clutter reduces operator trust and breaks the “minimal root” ideal when cloning or sharing zip snapshots.
- **Recommended fix**:
  - Add a documented + scripted routing rule: move these into `archive/data/databases/telemetry_seeds/…`.
  - Add a tidy routine to optionally move them for local hygiene (CI can’t catch untracked files).
- **Acceptance criteria**:
  - Running a “workspace cleanup” command results in root containing only `autopack.db` for SQLite dev.

### 2.5 API version drift: root endpoint returns `0.1.0` despite package being `0.5.1`

- **Evidence**: `src/autopack/main.py` uses `version=__version__` for OpenAPI, but `GET /` returns `"version": "0.1.0"`.
- **Why it matters**: version consistency is part of the CI drift contracts and affects operators/clients.
- **Recommended fix**:
  - Return `__version__` from the root endpoint (and/or add `/version`).
- **Acceptance criteria**:
  - Root endpoint version matches `pyproject.toml` and OpenAPI.

### 2.6 Request size limits are not explicit (API + nginx)

- **Evidence**:
  - FastAPI uses SlowAPI for rate limiting, but there is no explicit request-body size limit.
  - `nginx.conf` does not set `client_max_body_size`.
- **Why it matters**: file uploads and large JSON payloads can cause resource exhaustion; “safe by default” should include hard limits.
- **Recommended fix**:
  - Add `client_max_body_size` in nginx (and document it).
  - Add an API-side max body size middleware (defense-in-depth), at least in production.
- **Acceptance criteria**:
  - Oversized requests are rejected deterministically (HTTP 413).

### 2.8 Integration stubs drift: docs/scripts reference non-existent `integrations/` path

- **Evidence**:
  - `docs/PROJECT_INDEX.json` references `python integrations/supervisor.py …` but integrations are under `scripts/integrations/`.
  - `scripts/integrations/README.md` “Testing Integration” section also uses `python integrations/*.py` (wrong path).
- **Why it matters**: These are presented as the orchestration entry points; wrong paths break quickstart and confuse agents.
- **Recommended fix**:
  - Update docs to use `python scripts/integrations/supervisor.py` etc.
  - Optional: add a small compatibility shim directory `integrations/` that imports/execs the scripts (if you want to preserve legacy paths).
- **Acceptance criteria**:
  - Copy/paste commands from `docs/PROJECT_INDEX.json` and `scripts/integrations/README.md` work from repo root.

### 2.9 Legacy uvicorn target references remain in docs (not covered by drift checker)

- **Evidence**:
  - `docs/guides/RESEARCH_CI_FIX_CHECKLIST.md` and `docs/guides/RESEARCH_CI_IMPORT_FIX.md` reference `python -m uvicorn autopack.api.server:app ...`
  - `scripts/check_docs_drift.py` blocks backend-main drift but does **not** currently block `autopack.api.server:app` drift.
- **Why it matters**: these are copy/paste footguns; they reintroduce the very “two control planes” problem Autopack already closed.
- **Recommended fix**:
  - Extend `scripts/check_docs_drift.py` forbidden patterns to include `autopack.api.server:app` and other legacy uvicorn targets.
  - Or consolidate legacy references into an explicitly labeled section and exclude that file from drift checks.
- **Acceptance criteria**:
  - CI fails if docs reintroduce legacy uvicorn targets outside of an allowlisted legacy section.

### 2.10 Risk scoring config drift: `RiskScorer` references non-existent `config/*.yaml` files

- **Evidence**: `src/autopack/risk_scorer.py`
  - `PROTECTED_PATHS` includes `config/safety_profiles.yaml` and `config/governance.yaml`, but these files do not exist in `config/`.
- **Why it matters**: risk scoring is meant to be deterministic + enforceable; referencing non-existent config files either creates dead code paths or gives a false sense of coverage.
- **Recommended fix** (choose one):
  - Create the missing config files (and define their schema + ownership), **or**
  - Update `RiskScorer.PROTECTED_PATHS` to reference the real policy/config sources that exist (e.g., `config/models.yaml`, `config/protection_and_retention_policy.yaml`, `config/sot_registry.json`, `.github/workflows/*`).
- **Acceptance criteria**:
  - Every “protected config path” referenced by risk scoring exists and is meaningful.

### 2.11 “Config surface area” drift: multiple `config/*.yaml` exist with no runtime readers

- **Evidence**:
  - No runtime references found for: `config/feature_catalog.yaml`, `config/stack_profiles.yaml`, `config/tools.yaml`.
  - `config/project_types.yaml` appears to be used only by `scripts/launch_claude_agents.py`.
- **Why it matters**: unused configs become stale quickly and create “two truths” for agents (“is this canonical?”).
- **Recommended fix**:
  - Decide for each config file: **wire it**, **archive it**, or **document it as future-only** (and keep it out of “canonical config” lists).
  - Prefer a “config index” doc explaining which config files are consumed at runtime and by which subsystem.
- **Acceptance criteria**:
  - Each `config/*` file is either: (a) referenced by runtime code/tests, or (b) explicitly marked as unused/future-only, or (c) removed/archived.

### 2.12 CI/contract enforcement gaps: several known drifts are not mechanically blocked

- **Evidence**:
  - `scripts/check_docs_drift.py` exists, but is **not invoked** by `.github/workflows/ci.yml` (docs integrity currently runs `pytest tests/docs/`, `check_doc_links.py`, and SOT drift checks).
  - Workspace structure verification is enforced in a **separate workflow** (`.github/workflows/verify-workspace-structure.yml`) and is not part of the default “Autopack CI” required checks list.
  - No tests currently assert:
    - `GapScanner` baseline-policy drift detection matches the real repo state (`config/baseline_policy.yaml` exists, but scanner can still produce a “missing baseline policy” gap if path expectations drift).
    - `RiskScorer` protected-config paths exist (it currently references non-existent `config/safety_profiles.yaml` and `config/governance.yaml`).
    - `python -m autopack` exposes the Autopack CLI/help (it currently runs a Canada classifier demo).
    - README/API port consistency (README uses 8100; docker/compose/docs use 8000).
  - Docs drift checker does not currently block legacy `autopack.api.server:app` references (still present in some guides).
- **Why it matters**: these are exactly the kinds of “ideal state” violations that regress unless CI blocks them.
- **Recommended fix**:
  - Add a new CI step (or a docs contract test) that runs `python scripts/check_docs_drift.py` and expand it to cover:
    - legacy uvicorn targets like `autopack.api.server:app`
    - known bad compose service names (`postgres`, `api`) if you want to enforce them
  - Add minimal, low-flake contract tests for:
    - GapScanner baseline-policy detection (clean repo should not emit a missing baseline policy gap).
    - RiskScorer protected-config path existence.
    - `python -m autopack --help` returns Autopack help.
    - README port consistency with docker-compose defaults.
  - Add `verify-workspace-structure` to the recommended required checks list in `scripts/ci/github_settings_self_audit.py` (and/or merge its checks into `ci.yml` if you want PR-blocking by default).
- **Acceptance criteria**:
  - CI fails on reintroduction of the above drifts (before merge), not after-the-fact.

---

## 3) P2 — Developer experience + polish (still valuable)

### 3.1 Pre-commit hooks are absent

- **Problem**: no `.pre-commit-config.yaml`
- **Recommended fix**:
  - Add pre-commit with `ruff`, `black`, and basic hygiene hooks (end-of-file-fixer, trailing whitespace, check-yaml).
- **Acceptance criteria**:
  - Contributors can run `pre-commit install` and get the same checks locally as CI.

### 3.2 Fix CODEOWNERS drift: references a non-existent doc

- **Evidence**: `.github/CODEOWNERS` references `docs/SECURITY_BASELINE.md` which does not exist (baseline doc is `security/README.md`).
- **Recommended fix**:
  - Update CODEOWNERS to point at the actual baseline doc (or create `docs/SECURITY_BASELINE.md` as a short pointer).
- **Acceptance criteria**:
  - All CODEOWNERS targets exist.

### 3.3 Windows-only helper scripts use hardcoded `C:\\dev\\Autopack`

- **Evidence**:
  - `scripts/archive/root_scripts/RUN_EXECUTOR.bat`
  - `scripts/telemetry_seed_quickstart.ps1`
  - Comment in `scripts/tidy/tidy_workspace.py`
- **Recommended fix**:
  - Use `%~dp0` / repo-root discovery (`git rev-parse --show-toplevel`) or `$PSScriptRoot` rather than absolute paths.
- **Acceptance criteria**:
  - Scripts work when repo is not cloned to `C:\\dev\\Autopack`.

### 3.4 nginx request-id propagation looks incorrect / non-functional

- **Evidence**: `nginx.conf`:
  - Sets `$request_id` from `$http_x_request_id`, then on empty executes `set $request_id $request_id;` (no-op).
- **Why it matters**: request-id correlation is valuable for debugging distributed failures; incorrect config gives false confidence.
- **Recommended fix**:
  - Use nginx’s built-in `$request_id` if available (or generate a UUID via a known module), and only fall back to client-provided header when present.
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

### 5.1 Secrets / credentials governance (3rd‑party APIs)

- **Goal**: standardize how Autopack stores/loads/rotates credentials for Etsy/Shopify/YouTube/brokers, and ensure secrets are never persisted in logs/artifacts.
- **Skeleton**:
  - `src/autopack/secrets/`:
    - `providers.py` (typed secret descriptors per provider)
    - `store.py` (env + optional encrypted file/OS keychain backend)
    - `redaction.py` (shared redaction helpers used by sanitizer + logs)
  - `docs/SECRETS_AND_CREDENTIALS.md` (canonical usage + rotation)

### 5.2 Integration sandboxing + rate-limit safety (“integration runner”)

- **Goal**: safe wrapper for external side effects with timeouts, retries/backoff, idempotency keys, and rate limiting.
- **Skeleton**:
  - `src/autopack/integrations/runner.py`:
    - timeout + retry policy
    - idempotency keys
    - per-provider rate limiter
    - structured audit events
  - `src/autopack/integrations/providers/{etsy,shopify,youtube,broker}/...`

### 5.3 Job scheduling + resumable pipelines

- **Goal**: durable background jobs (queue + retry + checkpoint) so automation doesn’t rely on a single long-running process.
- **Skeleton**:
  - `src/autopack/jobs/`:
    - `models.py` (Job table/state)
    - `queue.py` (enqueue/dequeue, retry rules)
    - `worker.py` (single worker; later expand)
    - `checkpoints.py` (idempotent checkpoints)

### 5.4 Browser automation harness (when APIs aren’t enough)

- **Goal**: Playwright runner with strict safety (no credential leaks, bounded actions, deterministic artifacts).
- **Skeleton**:
  - `src/autopack/browser/`:
    - `playwright_runner.py`
    - `artifacts.py` (screenshots/videos/har logs storage policy)
    - `redaction.py` (scrub cookies/tokens)

### 5.5 Human approval UX as a first-class gate (“approval inbox”)

- **Goal**: for high-risk actions (posting videos, listing products, executing trades), add a first-class approval inbox beyond Telegram.
- **Skeleton**:
  - `src/autopack/approvals/`:
    - `models.py` (ApprovalRequest with payload hash + decision)
    - `api.py` (list/approve/reject endpoints)
  - `src/frontend/pages/Approvals.tsx` (simple review UI)


