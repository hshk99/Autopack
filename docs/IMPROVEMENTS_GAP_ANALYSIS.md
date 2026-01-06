# Autopack — Comprehensive Improvement / Gap Analysis (vs README "ideal state" and beyond)

**Last Updated**: 2026-01-07
**Scope**: repo-wide (docs, CI, runtime, security, dashboard, packaging, hygiene)
**Goal**: enumerate *all* meaningful gaps/enhancements in one place; prioritize; give concrete acceptance criteria.

---

## Status Summary (BUILD-188)

| Section | Status | Notes |
|---------|--------|-------|
| 1.1 Build artifacts | **DONE** | CI check added, `.gitignore` extended |
| 1.2 Root DB clutter | **DONE** | Already in `.gitignore`; untracked by design |
| 1.3 Hardcoded paths | **DONE** | Migration now schema-only; seed in `docs/examples/` |
| 1.4 Unsafe logging | **DONE** | `sanitize_url()` applied; `print()` → `logger.debug()` |
| 1.5 Error sanitization | **DONE** | `src/autopack/sanitizer.py` + tests added |
| 1.9 Stray backup files | **DONE** | Removed `.bak2`; CI check extended to `*.bak*` |

---

## 0) What's already close to "ideal"

- **SOT-ledgers + mechanical enforcement**: docs integrity tests, SOT drift checks, link checks, SECBASE enforcement, actions pinning guardrails.
- **Safety-first posture**: run-local writes + tidy gating is a strong foundation; parallel runs have explicit isolation model documented and implemented.
- **Security baseline system**: SARIF artifacts + baseline refresh PR workflow + burndown counting is unusually complete.
- **Three-gate test strategy**: core/aspirational/research split is a pragmatic way to keep CI meaningful.

This doc focuses on what’s still missing, drifting, inconsistent, or can be materially improved.

---

## 1) P0 (High-impact / correctness / “ideal state” violations)

### 1.1 Repo hygiene violations: tracked build artifacts + dependency dirs

- **Problem**: `src/autopack/dashboard/frontend/` currently contains `node_modules/` and `dist/`. Even if `.gitignore` ignores them, they appear present in-workspace and often end up committed; they also expand scan surface and slow CI.
- **Why it matters**: violates determinism + mechanical enforceability goals (CI behavior changes based on local state), bloats repo, increases security scanning noise.
- **Recommended fix**:
  - Remove committed `node_modules/` and `dist/` from git history (at least from HEAD).
  - Add/extend **workspace structure verification** to **hard-fail** if any `node_modules/` or `dist/` exist under tracked paths in the repo.
- **Acceptance criteria**:
  - `git ls-files | grep -E "(^|/)node_modules/|(^|/)dist/"` returns empty.
  - CI contains a check that fails PRs reintroducing those directories.

### 1.2 Root “telemetry_seed_*.db” violates `docs/WORKSPACE_ORGANIZATION_SPEC.md`

- **Problem**: root contains multiple `telemetry_seed_*.db` files. The spec explicitly says historical/test DBs must not be at root; only active `autopack.db` is allowed.
- **Recommended fix**:
  - Move seed DBs into `archive/data/databases/telemetry_seeds/...` (or `tests/fixtures/` if tests require them).
  - Add tidy + verification routing rules specifically for `telemetry_seed_*.db`.
- **Acceptance criteria**:
  - Only `autopack.db` may exist at root (and ideally it is **untracked**).
  - `verify_workspace_structure.py` reports 0 root DB clutter warnings/errors.

### 1.3 Portability break: hardcoded local Windows paths inside SQL seeds

- **Problem**: `src/autopack/migrations/add_directory_routing_config.sql` seeds values like `C:\dev\Autopack\...`.
- **Why it matters**: breaks determinism/portability across machines/OS; DB content becomes workstation-specific; CI/prod cannot safely apply it.
- **Recommended fix**:
  - Replace absolute paths with **relative** paths or env-driven values.
  - Separate “example seed data” from “migration schema” (schema migrations should not embed developer workstation paths).
- **Acceptance criteria**:
  - No migrations or seeds include `C:\dev\` or other machine-specific absolute roots.
  - Seeds are either removed, made relative, or generated at runtime.

### 1.4 Potential secret leakage / unsafe logging in API startup

- **Problem**: `src/autopack/main.py` prints `DATABASE_URL` from environment **before** dotenv load (and again after). This can leak credentials in logs.
- **Recommended fix**:
  - Replace `print(...)` with structured logging and **credential redaction** (mask user/pass).
  - Gate verbose diagnostics behind `DEBUG_DB_IDENTITY=1` (or similar) and ensure it prints only masked values.
- **Acceptance criteria**:
  - No startup logs output raw DB credentials.
  - A unit test (or static check) ensures DB URLs are redacted when logged.

### 1.5 Secret/PII persistence risk in error reporting (sanitize before writing)

- **Problem**: `src/autopack/main.py` global exception handler passes request `headers` and `query_params` into `report_error(...)`. Even if the API response is safe, persisted error reports can capture secrets/PII (e.g., `Authorization`, API keys, cookies, webhook tokens, email addresses).
- **Recommended fix**:
  - Implement a single `sanitize_context()` (or `sanitize_request_context()`) used *everywhere* before writing any error report artifact.
  - Strip/replace known sensitive headers and query keys (allowlist preferred, otherwise robust denylist), and truncate large values.
  - Add a contract/unit test that proves secrets are redacted in persisted error payloads.
- **Acceptance criteria**:
  - No stored error report contains raw values for: `Authorization`, `Cookie`, `Set-Cookie`, `X-API-Key`, `token`, `secret`, `password` (case-insensitive).
  - Redaction behavior is mechanically enforced by tests.

### 1.6 Governance rule contradictions (docs vs implementation)

- **Problem**: `docs/GOVERNANCE.md` says tests/docs can be “always allowed” for low-risk; `src/autopack/planning/plan_proposer.py` includes `tests/` in `NEVER_AUTO_APPROVE_PATTERNS` (always requires approval).
- **Recommended fix**:
  - Choose one canonical rule set (docs should match code; code should match intended safety model).
  - Encode the governance policy in a single module/config, then import it everywhere.
- **Acceptance criteria**:
  - One canonical policy source; docs and code match; governance tests cover the rule.

### 1.7 Versioning mismatch: FastAPI advertises `0.1.0` while project is `0.5.1`

- **Problem**: `FastAPI(... version="0.1.0")` diverges from `pyproject.toml` version and README status.
- **Recommended fix**:
  - Use `autopack.__version__` (or `pyproject`-derived) as the API version string.
- **Acceptance criteria**:
  - `/` and OpenAPI show the same version as `autopack.__version__` and `pyproject.toml`.

### 1.8 Docker/frontend build path mismatch (high likelihood of breakage)

- **Problem**: `Dockerfile.frontend` copies `src/frontend/`, but the repo’s frontend sources appear under `src/autopack/frontend` and/or `src/autopack/dashboard/frontend`.
- **Recommended fix**:
  - Decide which frontend is canonical (dashboard vs root UI), then update Dockerfile(s) accordingly.
  - Remove dead build paths to avoid “green locally / broken in container”.
- **Acceptance criteria**:
  - `docker build -f Dockerfile.frontend .` succeeds deterministically from a clean clone.

### 1.9 Stray backup-like file under `src/` (reliability hazard)

- **Problem**: There is at least one backup-like file in source tree (example currently present: `src/autopack/governed_apply.py.bak2`).
- **Why it matters**: violates the “one truth” expectation for runtime imports; creates ambiguity for humans/LLMs; can accidentally get imported or referenced; defeats workspace structure intent.
- **Recommended fix**:
  - Delete any `*.bak*` / `*.backup*` / `*.broken*` variants under `src/` (including `*.bak2`, not just `*.bak`).
  - Expand the CI stray-file check to cover suffix variants (`*.bak1`, `*.bak2`, etc.) and common “dot variants” (`*.bak.<ext>`, `*.backup.<ext>`).
- **Acceptance criteria**:
  - No backup-like files exist under `src/` (`find src -type f -name "*.bak*" -o -name "*.backup*" -o -name "*.broken*"` returns empty).
  - CI blocks reintroduction.

### 1.10 Root DB clutter beyond `telemetry_seed_*.db` (spec violation)

- **Problem**: In addition to `telemetry_seed_*.db`, there are other root `.db` artifacts (e.g., `autopack_telemetry_seed*.db`) which also violate the “only active `autopack.db` at root” rule.
- **Recommended fix**:
  - Extend routing/verification to cover *all* non-`autopack.db` root `*.db` files.
  - Decide which DBs are true fixtures (→ `tests/fixtures/`) vs historical artifacts (→ `archive/data/databases/...`).
- **Acceptance criteria**:
  - Root contains **only** `autopack.db` (dev) and no other `*.db`.

---

## 2) P1 (Major improvements: determinism, CI coverage, operator UX, safety)

### 2.1 Frontend is not covered by CI (lint/typecheck/build)

- **Problem**: CI workflows do not run `npm` lint/typecheck/build for any frontend(s).
- **Recommended fix**:
  - Add a dedicated `frontend` job that runs `npm ci`, `npm run lint`, `npm run type-check`, `npm run build`.
  - Decide which frontend(s) are supported; if multiple, test both or consolidate.
- **Acceptance criteria**:
  - CI fails on TS/ESLint errors and build failures.

### 2.2 Python version drift across workflows (3.11 vs 3.12)

- **Problem**: `ci.yml` uses Python 3.11; `intention-autonomy-ci.yml` uses Python 3.12.
- **Recommended fix**:
  - Standardize to one version (likely 3.11 per `pyproject.toml`) or introduce a matrix (3.11+3.12) explicitly.
- **Acceptance criteria**:
  - Documented policy; workflows align; failures aren’t version-accidental.

### 2.3 Type safety not enforced (mypy unused in CI)

- **Problem**: `mypy` is in `dev` deps but not run in CI; large repo means regressions can slip.
- **Recommended fix**:
  - Add `mypy` to CI with an incremental adoption plan (module allowlist + baseline).
- **Acceptance criteria**:
  - `mypy` runs in CI; failures are actionable; adoption is staged if needed.

### 2.4 Security “diff gates” are still non-blocking

- **Problem**: `security.yml` diff gates are `continue-on-error: true` (rollout mode).
- **Recommended fix**:
  - Move to blocking once stable, at least for PRs into `main`.
  - Align cadence: `security.yml` is daily; `security-artifacts.yml` is weekly. Decide desired posture to reduce redundant scanning.
- **Acceptance criteria**:
  - New findings block PRs by default; baseline refresh remains explicit and reviewable.

### 2.5 “Gap scanner” is currently guaranteed to produce a baseline-policy gap

- **Problem**: `GapScanner._detect_baseline_policy_drift()` looks for `config/baseline_policy.yaml`, which does not exist (current policies are elsewhere under `config/`).
- **Recommended fix**:
  - Either create `config/baseline_policy.yaml` (canonical), or update scanner to reference the real policy files.
- **Acceptance criteria**:
  - A clean repo state produces no “missing baseline policy” gap.

### 2.6 Autonomy artifacts path consistency

- **Problem**: docs/examples sometimes reference `.autonomous_runs/<run_id>/...` while the repo’s canonical layout is `.autonomous_runs/<project>/runs/<family>/<run_id>/...`.
- **Recommended fix**:
  - Ensure docs, CLI help, and `RunFileLayout` agree, and examples don’t teach legacy paths.
- **Acceptance criteria**:
  - One canonical path structure used everywhere; old paths are documented as legacy only.

### 2.7 Executor ↔ API operational hardening

- **Opportunities**:
  - **Redaction**: error responses currently return `detail=str(exc)` always; consider safer error messages unless `DEBUG=1`.
  - **Auth posture**: API key auth is bypassed if `AUTOPACK_API_KEY` is unset; consider a “prod requires key” gate (e.g., `AUTOPACK_ENV=prod`).
  - **Background task lifecycle**: `approval_timeout_cleanup()` loops forever; ensure graceful shutdown and exception isolation (mostly present), but consider structured cancellation and backoff.
- **Acceptance criteria**:
  - Production config cannot accidentally run with open auth.
  - Error payloads are safe-by-default.

### 2.8 Supply-chain determinism gaps: Docker image digests + Python deps in images

- **Problem**:
  - Docker images are pinned by tag but generally **not pinned by digest** (e.g., `python:3.11-slim`, `nginx:alpine`, `postgres:15.10-alpine`, `qdrant/qdrant:v1.12.5`).
  - Backend `Dockerfile` installs from `requirements.txt`, but requirements are not guaranteed to be hash-locked; build can drift over time.
- **Recommended fix**:
  - Pin Docker base images by digest (or explicitly document why tags are acceptable).
  - Introduce a deterministic dependency strategy for container builds:
    - either `pip-compile --generate-hashes` for a container-specific lock,
    - or `constraints.txt` pinned for Docker builds,
    - or build from a pinned wheelhouse artifact.
- **Acceptance criteria**:
  - Rebuilding containers at different times yields identical dependency sets (or drift is intentional + documented).
  - CI detects dependency drift impacting Docker builds.

### 2.9 Reduce redundant / low-signal security scanning

- **Problem**: `security.yml` runs Safety + Trivy + CodeQL daily; `security-artifacts.yml` runs a weekly SARIF artifact generation used for baseline refresh. This can create redundant scans and noisy artifacts without added enforcement.
- **Recommended fix**:
  - Decide the canonical enforcement path (baseline diff gates) and consolidate schedules.
  - If Safety is kept, either baseline it too or remove it (currently it’s report-only via `|| true`).
- **Acceptance criteria**:
  - One coherent security posture: what blocks PRs, what is scheduled, and what is baseline-driven.

### 2.10 Docs absolute-path cleanup (portability + copy/paste safety)

- **Problem**: There are many `C:\...` references across `docs/`. Some are legitimate Windows-only guides, but others are workstation-specific and don’t generalize (hurts “ideal state” portability and encourages copy/paste footguns).
- **Recommended fix**:
  - Standardize docs to use `%REPO_ROOT%` / `<repo_root>` / `$REPO_ROOT` conventions.
  - Keep absolute paths only in explicitly labeled Windows-only sections, and prefer environment-variable based examples.
  - Add a “docs portability” check (non-blocking at first) that flags suspicious absolute paths outside Windows-only guides.
- **Acceptance criteria**:
  - Non-Windows-only docs do not contain workstation-specific absolute roots.
  - CI (or a doc contract test) flags regressions.

---

## 3) P2 (Design/maintenance improvements: cleanup, consolidation, quality-of-life)

### 3.1 Consolidate frontends / clarify the canonical UI

- **Observation**: There is a root Vite setup (`package.json`, `vite.config.ts`) and also `src/autopack/dashboard/frontend` (React app) plus `src/autopack/frontend`.
- **Recommended fix**:
  - Choose a single canonical UI (or document why multiple exist).
  - Remove dead/unused packages or wire them explicitly into docs + Docker + CI.
- **Acceptance criteria**:
  - “One true way” to run/build the UI is documented and tested.

### 3.2 Replace ad-hoc migration scripts with a single migration discipline

- **Observation**: `alembic` is a dependency, but migrations exist as a mix of Python scripts and `.sql` files in multiple places.
- **Recommended fix**:
  - Standardize on Alembic (or explicitly standardize on “SQL migrations only”), document and enforce it.
- **Acceptance criteria**:
  - One migration toolchain; reproducible DB setup; no workstation-specific seeds in schema migrations.

### 3.3 Strengthen workspace structure checks

- **Recommended additions**:
  - Detect stray `*.bak2` / `*.bak*` under `src/` (current CI check catches `*.bak` but not variants).
  - Detect committed caches (`__pycache__`, `.pyc`) under `src/` and `tests/`.
  - Detect root DB clutter and route it per spec.
- **Acceptance criteria**:
  - CI blocks new hygiene regressions without relying on human review.

### 3.4 Standardize “dev install” commands and docs

- **Observation**: `pyproject.toml` is SOT; CI uses `pip install -e ".[dev]"`; Makefile uses `requirements-dev.txt`.
- **Recommended fix**:
  - Align Makefile/docs with the SOT approach (or formally support both, but keep them consistent).
- **Acceptance criteria**:
  - One recommended install path; no drift between CI and local docs.

### 3.5 Add missing community/metadata files expected by workspace spec

- **Gaps**:
  - `LICENSE*` missing at repo root (spec expects it).
  - `SECURITY.md` missing at repo root (there is `security/README.md`, but GitHub expects `SECURITY.md`).
  - `CODE_OF_CONDUCT.md` missing (optional, but helpful).
- **Acceptance criteria**:
  - Files exist at root and match current policies.

### 3.6 Improve API versioning + OpenAPI stability

- **Recommended**:
  - Expose `X-Autopack-Version` header or `/version` endpoint.
  - Add contract test ensuring OpenAPI metadata version matches package version.
- **Acceptance criteria**:
  - Version consistency is mechanically enforced.

### 3.7 Observability polish

- **Recommended**:
  - Consolidate “token cap” and “usage cap” handling (dashboard has TODO for cap).
  - Consider structured JSON logging for API/executor (esp. if integrating with a log pipeline later).
- **Acceptance criteria**:
  - Dashboard shows meaningful caps; telemetry fields are consistent; logs are parseable.

### 3.8 Release engineering / distribution hardening (optional but “beyond README”)

- **Gaps**:
  - No standard release workflow (tag → build artifacts → changelog/release notes).
  - No SBOM generation for releases/containers (useful if publishing images).
  - No documented support policy for Python/Node versions (beyond `pyproject`).
- **Recommended fix**:
  - Add a release process doc and (optionally) a GitHub Actions workflow for tagged releases.
  - Generate SBOMs for Docker images and/or Python distributions on release.
- **Acceptance criteria**:
  - A tagged release produces reproducible artifacts + an auditable paper trail.

---

## 4) Known “paper cuts” / consistency tweaks (low risk)

- **Docs example drift**: `docs/PARALLEL_RUNS.md` references `docker-compose up -d postgres` but compose service is `db`.
- **Schema location mismatch**: some docs reference `docs/schemas/*` but schemas live in `src/autopack/schemas/*`.
- **Security workflow duplication**: daily `security.yml` + weekly `security-artifacts.yml` might be more than needed; decide and document.

---

## 5) Next-tier hardening backlog (extensive, beyond the “big rocks”)

These are “second-order” hardening items: they typically don’t unlock core functionality, but materially improve **security**, **privacy**, **operability**, and **determinism** over time.

### 5.1 Data protection: sanitize anything written to disk (errors, telemetry, artifacts)

- **Gap**: `src/autopack/error_reporter.py` records:
  - `context_data` verbatim
  - `stack_frames[*].local_vars` (repr of locals) which can include tokens, headers, credentials, payloads, file contents
- **Hardening**:
  - Add a central sanitizer used by `ErrorReporter`:
    - redact sensitive keys (case-insensitive): `authorization`, `cookie`, `set-cookie`, `x-api-key`, `api_key`, `token`, `secret`, `password`, `session`, `jwt`
    - truncate values aggressively
    - avoid persisting `local_vars` by default (or allowlist a small subset)
  - Ensure “error report artifacts” are treated as potentially sensitive and excluded from any SOT consolidation by default.
- **Acceptance criteria**:
  - Tests prove redaction works for headers, query params, and stack locals.
  - No error report contains raw credential strings even in nested structures.

### 5.2 Auth hardening: tighten “dev conveniences” so they can’t reach prod

- **Gap**: JWT key generation (`ensure_keys`) can generate keys when missing; this is convenient, but risky if it ever happens in production.
- **Hardening**:
  - Add an explicit “environment mode” flag (e.g., `AUTOPACK_ENV=dev|test|prod`) and enforce:
    - **prod**: fail fast if JWT keys are not configured; never generate ephemeral keys
    - **dev/test**: generation allowed
  - Add a similar guard for API key auth “open mode” (only allowed in dev/test).
- **Acceptance criteria**:
  - In prod mode, startup fails if auth prerequisites are missing.
  - CI test ensures prod mode cannot run with generated keys or open auth.

### 5.3 API hardening: request limits, CORS, and safer error responses

- **Hardening**:
  - Add request-body size limits (avoid DoS / memory blowups).
  - Define explicit CORS policy (even if default-deny).
  - In non-DEBUG mode, avoid returning internal exception strings to clients (return opaque IDs + reference to error report).
- **Acceptance criteria**:
  - Oversized requests are rejected deterministically (413).
  - CORS behavior is explicit and tested.
  - Error responses do not leak internal paths/stack traces unless `DEBUG=1`.

### 5.4 Reverse proxy hardening (nginx)

- **Hardening**:
  - Add a Content-Security-Policy (CSP) suitable for the chosen frontend.
  - Add `Permissions-Policy`.
  - Ensure `proxy_set_header` includes `X-Request-ID` propagation (or generate one).
  - Consider `client_max_body_size` and upstream timeouts aligned with long-running operations.
- **Acceptance criteria**:
  - Security headers are present and validated by a small integration test (or curl-based script).

### 5.5 Executor reliability: close known TODOs that affect determinism/safety

There are several TODOs in `src/autopack/autonomous_executor.py` that map to real contract gaps (not just “nice to have”):

- **Hardening targets**:
  - Derive safety profile from intention anchor (avoid mismatched governance thresholds).
  - Deterministic changed-files extraction and persistence for builder results.
  - Integrate approval flows consistently (Telegram/CLI) rather than placeholder logic.
  - Coverage computation plumbing if it’s part of quality gate decisions.
- **Acceptance criteria**:
  - New/updated contract tests cover each TODO closure (fail on regression).
  - Executor output artifacts are deterministic for identical inputs.

### 5.6 DB discipline hardening: migrations, seeding, and “dev password” leakage

- **Hardening**:
  - Ensure dev-only compose files don’t train users into using hardcoded weak passwords in production.
  - Centralize migration discipline (Alembic or SQL-only) and document exactly how schema changes are applied.
  - Add a “schema drift” check that compares expected migrations vs live DB in CI integration tests.
- **Acceptance criteria**:
  - No production docs/configs include default credentials.
  - Schema drift is detected early and deterministically.

### 5.7 Policy-as-code expansion: static analysis of dangerous operations

- **Hardening**:
  - Extend write-protection / hygiene scanners to additional runtime modules, not just the executor.
  - Add static checks for:
    - `print()` in production modules (force logging)
    - logging of URLs that may contain credentials
    - writing outside allowlisted directories at runtime
- **Acceptance criteria**:
  - CI blocks these patterns on PRs (low false positives; allowlist exceptions with rationale).

### 5.8 Provenance and build integrity

- **Hardening**:
  - Generate SBOMs for containers and (if published) Python distribution artifacts.
  - Consider signing release artifacts (Sigstore/cosign) if Autopack is distributed.
- **Acceptance criteria**:
  - Release artifacts include SBOM + provenance metadata and are reproducible.

---

## 5) Suggested execution plan (if you want me to start fixing, in order)

1. **Clean committed artifacts**: remove `node_modules/`, `dist/`, move telemetry seed DBs to `archive/...`.
2. **Fix portability**: remove/replace hardcoded `C:\dev\Autopack` seeds in DB migrations.
3. **Harden logging**: redact DB URLs; remove raw prints; align API version.
4. **Align governance policy**: make docs+code match (tests/ auto-approve vs never-auto-approve).
5. **CI completeness**: add frontend build/lint, add mypy (staged), unify Python versions.
6. **Tidy remaining drift**: align docs paths, schema locations, compose service naming in docs.


