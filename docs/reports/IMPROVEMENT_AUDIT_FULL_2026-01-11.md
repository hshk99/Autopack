# Autopack — Full Improvement Audit (Post-PR #103–#109) — 2026-01-11

> **HISTORICAL SNAPSHOT** — This audit reflects state as of PRs #103–#109. The delta items were closed in PR #110. Kept as a record; not a canonical planning surface.

**Question answered**: "Given current state of Autopack (and recent PR trajectory), what's still worth improving vs the README 'ideal state' (and beyond)?"

This report is designed to be **comprehensive in one place**, without creating “two truths.” It therefore:

- **References** existing canonical scan/backlog artifacts (rather than duplicating them).
- Adds a **single consolidated list** of the remaining improvement areas as of the latest merges visible in `git log` (PRs #103–#109).

---

## 0) Canonical sources (already present)

Start with these (they already contain large, repo-wide scans/backlogs):

- **Primary backlog (P0–P3)**: `docs/IMPROVEMENTS_GAP_ANALYSIS.md`
- **Single-pane scan**: `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`
- **Delta audit (focused on missed/stale items)**: `docs/reports/IMPROVEMENT_AUDIT_DELTA_2026-01-11.md`
- **Ideal-state context**:
  - `README.md` (intent + quickstart + SOT summary)
  - `docs/INDEX.md` (navigation hub + “one truth” surfaces)
  - `docs/WORKSPACE_ORGANIZATION_SPEC.md` (workspace contract)

This file focuses on: **what remains after the recent hardening PR streak**.

---

## 1) Recent PR trajectory (what it already closed)

From the recent merges (PRs **#103–#109**), many of the previously-documented “two truths” issues appear already closed, including:

- **Docs truth drift fixes** (e.g., BUILD-041 status drift; `ARCHITECTURE.md` path correctness).
- **Canonical-doc portability enforcement** (CI-level).
- **CI enforcement ladder documentation**.
- **Feature flags registry + stronger extraction**.
- **Rollback env var wiring**.
- **Pre-commit vs CI parity (ruff)**.
- **Requirements headers aligned to Python 3.11**.

That shifts the “next best work” away from small doc nits and toward **maintainability, correctness-hardening, and remaining operator-surface convergence**.

---

## 2) Remaining improvement areas (comprehensive list)

### 2.1 “One truth” / docs portability cleanup (still leaks in living SOT docs)

- **`docs/FUTURE_PLAN.md` contains workstation-specific paths** (e.g., `cd c:/dev/Autopack`) and **legacy repo paths** (e.g., `src/backend/`).
  - Why it matters: `FUTURE_PLAN.md` is part of the **6-file SOT** per `docs/WORKSPACE_ORGANIZATION_SPEC.md`; it should not be copy/paste-bait for wrong paths.
  - Fix shape:
    - Replace `cd c:/dev/Autopack` with `$REPO_ROOT`-portable guidance.
    - Where `src/backend/` appears, either:
      - explicitly scope it to downstream project repos (FileOrganizer), or
      - replace with paths that exist in this repo.

### 2.2 Maintainability risk: very large “god files” in core runtime

The codebase still has multiple extremely large modules (line counts from a binary scan):

- `src/autopack/autonomous_executor.py` (~11.5k lines)
- `src/autopack/anthropic_clients.py` (~4.2k)
- `src/autopack/main.py` (~3.3k)
- `src/autopack/governed_apply.py` (~2.4k)

Why this matters relative to README “ideal state”:

- It increases the risk of **accidental drift** (hard to review, hard to test, easy to regress).
- It worsens **mechanical enforcement** (more per-file lint ignores, harder to isolate invariants).

High-ROI follow-ups:

- Extract stable submodules behind narrow interfaces (e.g., `api/routes/*`, `executor/*`, `apply/*`, `llm/*`), with contract tests per interface.
- Reduce/retire broad lint ignores (especially any ignores on “critical paths” like `main.py` / executor / apply).

### 2.3 CI determinism gaps (Docker/DB parity)

- **CI Postgres image is not patch-pinned** (`postgres:15-alpine`), while `docker-compose.yml` uses `postgres:15.10-alpine`.
  - Risk: subtle drift between “works in compose” vs “fails in CI.”
  - Fix shape: align CI to the same patch tag (or explicitly ADR why CI is intentionally “moving patch line”).

### 2.4 Windows DX: Makefile is not Windows-safe

`Makefile` uses `sleep`, `rm`, `find`, and `bash`, which will fail on Windows without MSYS/WSL.

Options:

- **Document**: “Makefile requires WSL/Git Bash.”
- Or add a **PowerShell or Python task runner** equivalent (preferred if Windows is a first-class environment).

### 2.5 Security posture clarifications (explicit decisions reduce “implicit drift”)

Even with strong regression-only diff gates (Trivy + CodeQL), there are still “policy posture” items worth making explicit to avoid future ambiguity:

- **Safety scan posture** (artifact-only vs diff-gated vs replaced by a deterministic scanner for Python deps).
- **Secrets persistence posture** (especially around OAuth tokens / credential material): ensure policy is explicit and mechanically enforced for production.
- **Artifact boundary**: ensure size caps + optional redaction are enforced consistently for *all* artifact read paths (API + UI).

### 2.6 Auth / operator UX end-to-end story (web UI vs API key vs JWT)

The repo supports both:

- `X-API-Key` style operator access, and
- JWT auth under `/api/auth/*`,

…but the “canonical, production-safe operator UI story” must be crystal-clear and mechanically enforceable:

- If the UI is meant for production humans: prefer JWT for browser sessions + keep API key for machine/executor boundary.
- If the UI is dev-only: explicitly document that, and ensure production posture doesn’t rely on baking secrets into a frontend bundle.

### 2.7 Feature flags registry boundary (keep it “one truth” without becoming “everything”)

The registry and its tests improved recently, but the *ongoing* risk is scope creep:

- Decide and enforce what belongs:
  - **A)** only `AUTOPACK_*` + explicit “accepted legacy aliases”, or
  - **B)** all runtime env vars that influence behavior.
- Ensure tests match that boundary (AST-based extraction + Settings alias detection already points in the right direction; keep it aligned with the policy).

### 2.8 Remaining “stale-claim” hygiene across docs

Mechanical scan shows non-trivial remaining `TODO implement` / `ROADMAP(...)` / `FIXME` occurrences across repo docs/scripts.

Recommendation:

- Keep “stale-claim cleanup” focused on **canonical operator docs** and **6-file SOT** (avoid rewriting append-only ledgers).
- Where possible: turn roadmap markers into tracked issues in `docs/FUTURE_PLAN.md` with a single status truth.

---

## 3) Suggested next PR stack (minimal-churn, high ROI)

1. **Docs**: sanitize `docs/FUTURE_PLAN.md` (portable paths; no accidental `src/backend` copy/paste) + add/extend CI guardrail scoped to canonical docs if desired.
2. **CI**: align Postgres version tag between CI and compose (or ADR the intentional difference).
3. **DX**: Makefile Windows stance (document WSL requirement or add PS/Python runner).
4. **Refactor**: carve `src/autopack/main.py` into route modules; carve `autonomous_executor.py` into stable components; add contract tests per component boundary.
5. **Security posture**: decide Safety posture (informational vs regression gate) and encode it (docs + CI).

---

## 4) Notes (how to extend this audit)

If you ask “continue”, the next extension pass should add:

- A file-by-file list of the **largest modules** with suggested extraction seams (lowest-risk cuts first).
- A scan of **ruff per-file ignores** and a prioritized plan to eliminate them.
- A canonical-doc allowlist sweep for remaining **workstation path** occurrences (especially in SOT docs).

---

## 5) Largest-module seam map (low-risk extraction plan)

This section proposes extraction seams that preserve behavior (thin wrappers first), then add contract tests, then progressively delete dead paths / relax lint ignores.

### 5.1 `src/autopack/autonomous_executor.py` (~11.5k LOC)

High-signal seams visible in-file:

- **Run initialization + infrastructure wiring**
  - Includes: dotenv loading, key selection, error-recovery bootstrap, DB init, `BuilderOutputConfig`, `MemoryService`, SOT indexing, `RunFileLayout`, diagnostics-agent init.
  - **Extract to**: `src/autopack/executor/bootstrap.py` + `src/autopack/executor/infrastructure.py`

- **Phase execution orchestration**
  - `execute_phase()` is mixing:
    - intention-first tracking,
    - scope generation (`manifest_generator`),
    - DB retry state,
    - token escalation event handling,
    - recovery execution wrapper.
  - **Extract to**: `src/autopack/executor/phase_runner.py` with a stable interface:
    - `run_phase_attempt(phase: dict) -> PhaseAttemptResult`

- **Special-cased phase handlers (batched execution)**
  - `_execute_phase_with_recovery()` contains multiple `if phase_id == "...": return _execute_*_batched(...)` branches.
  - **Extract to**:
    - `src/autopack/executor/phase_handlers/` (registry-based dispatch):
      - `PhaseHandler` protocol + `DEFAULT_HANDLER`
      - `HANDLERS: dict[str, PhaseHandler]`
    - This removes “giant if ladder” and turns new special-cases into isolated modules.

- **Context loading**
  - `_load_repository_context()` contains multiple modes (scope-aware → targeted → heuristic).
  - **Extract to**: `src/autopack/executor/context_loading.py`
    - Keep the policy text and ordering identical; move only the implementation.

- **Run checkpoints / rollback logging**
  - The rollback-to-checkpoint flow is self-contained and can be extracted with minimal coupling.
  - **Extract to**: `src/autopack/executor/run_checkpoint.py`

**Refactor strategy (safe order)**:

1. Create extracted modules that are called by existing methods (no behavior changes).
2. Add contract tests around each module boundary.
3. Only then remove dead code / delete duplicate code paths.

### 5.2 `src/autopack/main.py` (~3.3k LOC)

This file is currently both:

- auth policy (`verify_api_key`, `verify_read_access`),
- app lifecycle,
- **and** a very large collection of endpoints (runs, dashboard, artifacts, governance, approvals, auth, storage, etc.).

**Low-risk seam**: split into routers without changing routes:

- `src/autopack/api/app.py`: build `FastAPI()` + middleware + limiter + lifecycle tasks
- `src/autopack/api/deps.py`: auth deps (`verify_api_key`, `verify_read_access`) + DB deps
- `src/autopack/api/routes/runs.py`: `/runs*`
- `src/autopack/api/routes/artifacts.py`: `/runs/{run_id}/artifacts/*`, `/runs/{run_id}/browser/artifacts`
- `src/autopack/api/routes/approvals.py`: `/approval/*`, `/telegram/*` webhook surfaces
- `src/autopack/api/routes/governance.py`: `/governance/*`
- `src/autopack/api/routes/dashboard.py`: `/dashboard/*`
- `src/autopack/api/routes/auth.py`: `/api/auth/*` and OAuth health/refresh endpoints
- `src/autopack/api/routes/storage.py`: `/storage/*`
- Keep `src/autopack/main.py` as a thin import shim (or flip the entrypoint to `api.app:app` once stable).

### 5.3 `src/autopack/anthropic_clients.py` (~4.2k LOC)

Given it still has per-file ignores for undefined names (see Section 6), the safest extraction path is:

- Introduce a single typed “client surface” (request/response dataclasses).
- Move prompt building to `src/autopack/llm/prompts/anthropic.py`.
- Move retry/backoff + token budgeting into `src/autopack/llm/runtime.py`.
- Keep the provider adapter thin and deterministic.

### 5.4 `src/autopack/governed_apply.py` (~2.4k LOC)

This is safety-critical; treat it like a “micro-kernel”:

- Extract parsing/normalization functions (pure) into `src/autopack/patching/`.
- Keep enforcement logic in `governed_apply.py` but shrink it.
- Add more table-driven tests for:
  - path allow/deny,
  - protected-path enforcement,
  - rollback behavior toggles,
  - deletion thresholds.

---

## 6) Ruff-ignore reduction plan (what’s still risky)

Current per-file ignores (from `pyproject.toml`) include:

- `src/autopack/main.py`: `E402`, `F821`
- `src/autopack/llm_service.py`: `E402`
- `src/autopack/anthropic_clients.py`: `F821`, `F823`
- `src/autopack/autonomous_executor.py`: `F821`

**Why this still matters**:

- `F821` / `F823` in *critical runtime* means there are code paths with undefined names (or legacy dead branches), and lint is being used to “paper over” that risk.

**Suggested policy**:

- Keep broad ignores only for explicitly quarantined subsystems (research) and test scaffolding.
- For production-critical paths (`main.py`, executor, governed_apply, provider clients): drive toward **zero `F821/F823` ignores**.

**Concrete next steps**:

1. As part of the module-splitting work (Section 5), isolate legacy/dead branches into modules that are either deleted or explicitly quarantined.
2. Remove `F821` ignore from `main.py` if it is no longer needed (it appears likely stale given the modern `/auditor_result` endpoint).
3. Replace “global per-file ignores” with **local, line-scoped** ignores where truly justified (and add a short comment explaining the contract).

---

## 7) Canonical-doc portability sweep (focused on SOT/living docs)

### 7.1 Workstation paths and legacy repo paths still appear in 6-file SOT docs

Observed:

- `docs/FUTURE_PLAN.md` contains workstation path references (`c:/dev/Autopack`) and `src/backend/` strings.
- `docs/PROJECT_INDEX.json` appears clean of workstation paths.
- `docs/ARCHITECTURE_DECISIONS.md` contains a workstation-path mention (historical context).

**Key “two truths” risk**:

- The canonical-doc refs checker (`scripts/ci/check_canonical_doc_refs.py`) does **not** scan `docs/FUTURE_PLAN.md` today (it’s not in the canonical operator-doc allowlist), so these leaks are not mechanically blocked.

**Recommended fix options**:

- **Option A (preferred)**: add a small CI check scoped to the **6-file SOT docs** that forbids workstation paths unless explicitly marked `LEGACY/HISTORICAL`.
- **Option B**: add `docs/FUTURE_PLAN.md` to the canonical-doc allowlist check.

### 7.2 Keep “append-only ledgers” out of the blast radius

`docs/BUILD_HISTORY.md` / `docs/DEBUG_LOG.md` are append-only and will often contain historical strings. Do not globally enforce workstation-path bans across them unless you do it in an allowlisted, “new entries only” manner.

---

## 8) Updated next PR stack (sequenced to minimize risk)

1. **Docs/SOT**: sanitize `docs/FUTURE_PLAN.md` (portable `$REPO_ROOT`, no accidental `src/backend/` path guidance).
2. **CI parity**: pin CI Postgres to match compose (e.g., `postgres:15.10-alpine`) or record an ADR explaining the intentional mismatch.
3. **Windows DX**: Makefile stance (document WSL/Git Bash requirement or provide `scripts/tasks.ps1` equivalent).
4. **Refactor (API)**: split `main.py` into routers (`api/routes/*`) with no route changes; add “route shape” contract tests.
5. **Refactor (Executor)**: introduce registry-based phase handlers + extract context loading; then progressively shrink `autonomous_executor.py`.
6. **Lint-hardening**: remove/retire `F821/F823` ignores for critical modules once the refactors isolate legacy branches.

---

## 9) Exact “copy/paste trap” fixes to apply in `docs/FUTURE_PLAN.md`

These are concrete lines that currently violate the portable-path intent and/or reintroduce legacy repo structure paths.

### 9.1 Workstation path: `cd c:/dev/Autopack` (2 occurrences)

**Occurrence A (research tracer bullet launch command)**:

- `docs/FUTURE_PLAN.md` lines ~696–703:
  - `cd c:/dev/Autopack`

**Occurrence B (Lovable integration execution instructions)**:

- `docs/FUTURE_PLAN.md` lines ~880–894:
  - `cd c:/dev/Autopack`

**Recommended replacement (portable)**:

- Replace `cd c:/dev/Autopack` with **either**:
  - `cd $REPO_ROOT` (preferred; matches `docs/WORKSPACE_ORGANIZATION_SPEC.md`), or
  - remove the `cd` line entirely and state “run from repo root”.

### 9.2 Legacy repo path leakage: `src/backend/` (2 occurrences)

These are in the **Maintenance Backlog** section and read like “allowed paths” guidance:

- `docs/FUTURE_PLAN.md` lines ~568–580:
  - `Allowed Paths`: includes `src/backend/packs/`
  - `Allowed Paths`: includes `src/backend/`

**Why this is risky**:

- `docs/FUTURE_PLAN.md` is part of the **6-file SOT**, so these strings are highly likely to be copied into new phases/plans by humans/agents.
- In this repo, `src/backend/` is a legacy shape; for Autopack itself, the canonical code path is `src/autopack/`.

**Recommended fixes (choose one)**:

- **Option A (best hygiene)**: move the FileOrganizer-specific maintenance backlog out of Autopack’s core SOT:
  - relocate that backlog into `.autonomous_runs/file-organizer-app-v1/docs/FUTURE_PLAN.md` (project-specific SOT), and link to it from this file.
- **Option B (minimal change)**: keep the backlog in this file, but **make the scope explicit**:
  - annotate those bullets with a prefix such as: `FileOrganizer repo paths:` and/or add a one-line note that `src/backend/` is not an Autopack repo path.
  - optionally replace `src/backend/` with `src/autopack/` **only if** these tasks are intended to be executed inside this repo (unlikely).

---

## 10) Proposed CI guardrail: “6-file SOT portability contract”

Current situation:

- `scripts/ci/check_canonical_doc_refs.py` checks an allowlist of **canonical operator docs**, but it does **not** scan `docs/FUTURE_PLAN.md`.
- The result is a “two truths” hole: **SOT docs can accumulate workstation paths** without mechanical enforcement.

### 10.1 Minimal, low-false-positive approach (recommended)

Add a dedicated doc-contract test (scoped, not global) that scans *only* the **6-file SOT docs** for workstation-specific absolute paths.

- **Suggested new test**: `tests/docs/test_sot_portability_contract.py`
- **Scope**: only these files:
  - `docs/PROJECT_INDEX.json`
  - `docs/BUILD_HISTORY.md` (optional: only enforce on “recent window” if you want to avoid rewriting history)
  - `docs/DEBUG_LOG.md` (same optional “recent window” tactic)
  - `docs/ARCHITECTURE_DECISIONS.md` (allow historical context if explicitly labeled)
  - `docs/FUTURE_PLAN.md`
  - `docs/LEARNED_RULES.json` (likely irrelevant, but include for completeness)

**Patterns to forbid** (unless line is explicitly marked `LEGACY`/`HISTORICAL`):

- `C:\\dev\\Autopack`
- `c:/dev/Autopack`

**Allowed replacements**:

- `$REPO_ROOT/...` notation (portable)

### 10.2 Alternative: include FUTURE_PLAN in canonical-doc scan

Add `docs/FUTURE_PLAN.md` to `CANONICAL_OPERATOR_DOCS` in `scripts/ci/check_canonical_doc_refs.py`.

Tradeoff:

- This will likely cause CI failures until FUTURE_PLAN is cleaned up (which is desirable), but you must be careful about:
  - fenced code blocks that intentionally quote history (the script’s “skip code blocks” comment is not actually implemented as a real fenced-block parser).

---

## 11) Additional gaps discovered in continue pass #2 (with acceptance criteria + minimal PR shapes)

These are additional items identified after the earlier audit sections were written. They are “real gaps” even if they aren’t currently causing CI failures.

### 11.1 Health checks: API key requirements are stricter than runtime reality

**Observation**: `src/autopack/health_checks.py` currently checks for *all* of:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`

…but the executor/runtime can operate with **any one** provider key (and can also involve `GLM_API_KEY` depending on posture).

**Why it matters**: This can create false “unhealthy” results and encourages operators to add unused secrets (anti-ideal-state for safe operation).

**Acceptance criteria**:

- Health check passes when **at least one** configured LLM provider key is present.
- Health check fails with an actionable message when **no provider keys** are present.
- If GLM is “tooling-only”, it is either excluded from the health check or explicitly labeled as such.

**Minimal PR shape**:

- **Code**: adjust `HealthChecker.check_api_keys()` to match “at least one provider” logic.
- **Tests**: add unit tests for all key combinations (none, one, multiple).
- **Docs**: ensure the operator-facing health/runbook docs match the rule.

### 11.2 GLM posture is still ambiguous (runtime vs tooling-only)

**Observation**: `GLM_API_KEY` appears in:

- runtime code (`src/autopack/autonomous_executor.py`, `src/autopack/llm_service.py`, `src/autopack/glm_clients.py`)
- operator docs (`docs/PROJECT_INDEX.json` and other docs)

**Why it matters**: “one truth” about supported providers is part of the operator interface. Ambiguity here causes wrong expectations and can break runs in ways that feel non-deterministic.

**Acceptance criteria** (pick one posture and make it true):

- **Option A (runtime-supported)**:
  - GLM is treated as a first-class provider:
    - documented as such,
    - included in health checks,
    - included in feature flags/env registry,
    - has deterministic fallback behavior.
- **Option B (tooling-only / disabled for runtime)**:
  - Runtime does not depend on GLM:
    - runtime selection logic does not treat GLM as “primary”,
    - GLM-only code paths are behind an explicit feature flag default OFF,
    - docs label GLM as tooling-only and avoid presenting it as runtime requirement.

**Minimal PR shape**:

- **Docs**: add one explicit “Provider posture” paragraph (canonical place: `docs/ARCHITECTURE.md` or `docs/PROJECT_INDEX.json`).
- **Code**: either wire GLM as supported (Option A) or gate/remove runtime dependence (Option B).
- **Tests**: small contract test proving the posture (e.g., “no GLM key still allows run if Anthropic present”).

### 11.3 Import-time DB engine binding (configuration mutability footgun)

**Observation**: `src/autopack/database.py` creates the SQLAlchemy engine at import time from `get_database_url()`.

**Why it matters**:

- If any code expects `DATABASE_URL` / `*_FILE` values to be swapped after module import, it won’t take effect.
- It complicates test isolation (order-dependent imports can pin the engine unexpectedly).

**Acceptance criteria**:

- Either explicitly document: “DB URL is bound at import; set env vars before import,” **or**
- Refactor to lazy-create the engine/session via a getter so tests and subprocesses can control binding deterministically.

**Minimal PR shape**:

- **Option A (doc-only)**: add a short note in `docs/DEPLOYMENT.md` and/or `docs/CONTRIBUTING.md` about import-time binding expectations.
- **Option B (code hardening)**:
  - create `get_engine()` / `get_sessionmaker()` in `database.py` and use them in `get_db()` / init paths.
  - add 1–2 tests proving that setting `DATABASE_URL` before calling `get_engine()` works as expected.

### 11.4 Add a single “compose topology smoke test” (beyond unit/contract tests)

**Observation**: Many invariants are covered by unit/contract tests, but the repo lacks a single “compose-level smoke” that proves:

- nginx routing works (`/api/*` and `/api/auth/*`),
- backend is reachable and healthy,
- the canonical topology (`backend`, `frontend`, `db`, `qdrant`) boots coherently.

**Why it matters**: This is the easiest way to catch real-world regressions that unit tests miss (bad ports, bad proxy paths, missing env vars, missing container dependencies).

**Acceptance criteria**:

- A scripted smoke test can bring up compose, hit `/nginx-health` and `/health`, and (optionally) hit one basic API endpoint.
- It is safe-by-default: does not require real secrets; uses `AUTOPACK_ENV=development` and a test DB.
- It runs either as a manual workflow (`workflow_dispatch`) or as a non-blocking scheduled job, to avoid CI time bloat.

**Minimal PR shape**:

- Add `scripts/ci/smoke_compose_topology.py` (or `.sh`) that:
  - runs `docker compose up -d`,
  - polls health endpoints with a timeout,
  - tears down compose reliably.
- Add a dedicated GitHub Actions workflow (`.github/workflows/compose-smoke.yml`) as **manual + scheduled** (non-blocking unless you choose otherwise).

---

## 12) Additional gaps discovered in continue pass #3 (with acceptance criteria + minimal PR shapes)

### 12.1 Rate limiting behind reverse proxies (nginx) likely keys on proxy IP (ineffective/unfair)

**Observation**: `src/autopack/main.py` uses SlowAPI:

- `Limiter(key_func=get_remote_address)`

In typical nginx deployments, `get_remote_address` will often see the proxy IP unless forwarded headers are handled safely.

**Why it matters**:

- Rate limits can become ineffective (all clients share one IP) or overly strict/unfair.
- It’s a correctness/safety issue for bandwidth-heavy endpoints and any write endpoints you want to protect from bursts.

**Acceptance criteria** (choose one keying strategy and make it true):

- **Option A (per-IP, proxy-aware)**:
  - In the canonical compose+nginx topology, rate limiting keys on the real client IP (or at least on `X-Forwarded-For` first hop) without enabling spoofing vulnerabilities.
- **Option B (per-principal)**:
  - Rate limiting keys on `X-API-Key` (or JWT principal) rather than IP, which is often the correct model for operator APIs.

**Minimal PR shape**:

- **Code**:
  - add an explicit rate-limit key function consistent with the chosen strategy (A or B),
  - and document the trusted-proxy assumptions (if any).
- **Tests / validation**:
  - add a small unit test for the chosen key function,
  - optionally add a compose-smoke step that demonstrates rate limit behavior (non-blocking).
- **Docs**:
  - document “what rate limiting keys on” in `docs/DEPLOYMENT.md` (one paragraph; prevents future drift).

### 12.2 Executor DB bootstrap behavior remains a “works-in-one-mode, surprises-in-another” risk

**Observation**: `init_db()` is invoked from multiple places:

- `src/autopack/main.py` (API server bootstrap path)
- `src/autopack/autonomous_executor.py` (executor startup)
- `src/autopack/database.py` (contains guardrails via `AUTOPACK_DB_BOOTSTRAP`)

**Why it matters**:

- There’s still a risk of accidental schema creation / drift when switching between SQLite dev and Postgres (CI/prod) modes, or when running executor vs server in different environments.
- It also affects determinism: “schema existence” should be a mechanically enforced precondition, not a side effect.

**Acceptance criteria**:

- Executor and API server behave consistently:
  - In production-like modes: schema must already exist; fail fast with actionable errors.
  - In dev/test: schema bootstrap is possible only under explicit opt-in (`AUTOPACK_DB_BOOTSTRAP=1`).
- The docs’ “canonical DB lifecycle” matches reality for both:
  - sqlite dev (optional),
  - postgres production/CI (canonical).

**Minimal PR shape**:

- **Code**:
  - ensure executor and server call `init_db()` under the same policy (or explicitly document why they differ),
  - tighten logging so it’s obvious whether bootstrap mode is on/off (without leaking secrets).
- **Tests**:
  - add a small contract test proving production-mode startup fails when schema is missing unless bootstrap is explicitly enabled.
- **Docs**:
  - add one short “DB bootstrap behavior” section (or link) in `docs/DEPLOYMENT.md` and `docs/CONTRIBUTING.md`.

---

## 13) Additional gaps discovered in continue pass #4 (with acceptance criteria + minimal PR shapes)

### 13.1 Health checks assume SQLite (`autopack.db`) even when Postgres is canonical for CI/prod

**Observation**: `src/autopack/health_checks.py` contains a DB health check that:

- explicitly checks for a local SQLite file: `autopack.db`
- checks file existence and writability

**Why it matters**:

- It’s incorrect/misleading in Postgres mode (`DATABASE_URL=postgresql://...`), which is canonical for CI and production-like deployments.
- It encourages operators to “fix health” by creating a local SQLite file even when that’s not the intended runtime storage.

**Acceptance criteria**:

- Health checks correctly reflect the configured DB backend:
  - If `DATABASE_URL` is Postgres: health check verifies connectivity (and optionally verifies key tables exist).
  - If `DATABASE_URL` is SQLite: health check verifies file exists/writable (or creates it only in explicit dev bootstrap mode).
- Output message is explicit about which DB backend was checked and what failed.

**Minimal PR shape**:

- **Code**: update `HealthChecker.check_database()` to:
  - detect DB backend from `get_database_url()` / `DATABASE_URL`,
  - run a minimal DB ping (e.g., `SELECT 1`) for non-SQLite backends.
- **Tests**: add targeted unit tests for:
  - sqlite URL path → file checks,
  - postgres URL → connectivity check (mock engine/session).
- **Docs**: add a short note in `docs/CONTRIBUTING.md` or `docs/DEPLOYMENT.md` about what health checks validate per backend.

### 13.2 Decision ledger drift: DEC-050 is “Planned” but `docs/AUTHENTICATION.md` appears already rewritten

**Observation**:

- `docs/ARCHITECTURE_DECISIONS.md` shows **DEC-050** (“AUTHENTICATION.md rewrite”) as **🧭 Planned**
- `docs/AUTHENTICATION.md` currently documents:
  - `src/autopack/auth/*` file paths
  - endpoints under `/api/auth/*`

**Why it matters**:

- This is an internal “two truths” problem inside the architecture decision ledger itself (high cost: ADRs are supposed to be the durable truth).

**Acceptance criteria**:

- Either:
  - DEC-050 is updated to **✅ Implemented** with evidence links (and any remaining TODOs moved to a follow-up DEC), **or**
  - DEC-050 remains Planned but the doc rewrite is explicitly scoped as incomplete (and `docs/AUTHENTICATION.md` is adjusted to match that scope).

**Minimal PR shape**:

- **Docs-only**:
  - Update the DEC-050 status line and add a 1–2 bullet “Evidence” section pointing to the current `docs/AUTHENTICATION.md` + relevant test(s)/PR(s).
  - If anything is still missing (e.g., a specific contract test), list it as “Remaining work” and link to a tracked item in `docs/FUTURE_PLAN.md`.
