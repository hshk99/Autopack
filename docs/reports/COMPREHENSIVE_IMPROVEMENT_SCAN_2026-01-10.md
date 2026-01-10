# Comprehensive Improvement Scan (Repo-Wide)

**Date**: 2026-01-10  
**Scope**: Autopack repo current state + recent PR themes + “ideal state” as defined by `README.md` and SOT docs (especially `docs/INDEX.md`, `docs/WORKSPACE_ORGANIZATION_SPEC.md`, `docs/IMPROVEMENTS_GAP_ANALYSIS.md`).  
**Goal**: Identify **all** remaining areas for improvement/enhancement at once, with concrete evidence and acceptance criteria.

This report is intentionally “single-pane”: it links to deeper SOT docs (so we don’t create “two truths”), but still enumerates every actionable gap we can see from the repo surface.

---

## Executive Summary (Where you’re already strong)

- **Mechanical enforcement is real**: CI has strong contracts (`docs-sot-integrity`, doc drift, workspace structure, security diff gates, pinned-actions policy) and a clear “default-deny” governance posture (`docs/GOVERNANCE.md`, `RiskScorer`, approval system).
- **Security is unusually disciplined**: committed baselines + deterministic normalization + diff gate in `.github/workflows/security.yml` and strong documentation in `security/README.md`.
- **Operator UX is improving quickly**: recent PRs added a real operator surface (runs inbox, artifacts view, progress endpoints + UI) and reduced risky API error leakage.

The remaining work is mostly **convergence (“one truth”)** and **hardening for multi-tenant / external-side-effect autonomy**, plus a set of tracked performance/UX polish items.

---

## P0 — “Two truths” / safety contract violations (must fix)

### P0.1 `docs/AUTHENTICATION.md` is legacy but currently treated as canonical

- **Problem**: `docs/AUTHENTICATION.md` references a non-existent `src/backend/*` structure and recommends `init_db()` usage in ways that contradict current code + DB bootstrap guardrails.
- **Evidence**:
  - `docs/AUTHENTICATION.md` references `src/backend/models/user.py`, `src/backend/api/auth.py`, etc. (these paths do not exist in this repo).
  - Real auth code lives under `src/autopack/auth/*` and is mounted at `/api/auth/*` (see `src/autopack/auth/router.py`, `src/autopack/auth/security.py`).
  - `docs/WORKSPACE_ORGANIZATION_SPEC.md` lists `docs/AUTHENTICATION.md` under “Canonical Guides (Truth Sources)”.
- **Why P0**: Operators/agents will copy-paste this doc and get a false model of the system, which breaks the repo’s core thesis (deterministic + mechanically enforceable).
- **Fix options (pick one, enforce via CI)**:
  - **Option A (preferred)**: Rewrite `docs/AUTHENTICATION.md` to match `src/autopack/auth/*` + `docs/CANONICAL_API_CONTRACT.md` (already documents `/api/auth/*`).
  - **Option B**: Mark as legacy/historical and move to `archive/` (then remove from canonical docs lists).
- **Acceptance criteria**:
  - `docs/AUTHENTICATION.md` contains **no** `src/backend/` references.
  - The documented endpoints match `docs/CANONICAL_API_CONTRACT.md` Authentication section and the code in `src/autopack/auth/router.py`.
  - A **doc contract test** blocks regressions (forbid `src/backend/` strings in canonical operator docs allowlist).

### P0.2 `docs/GOVERNANCE.md` contains internal contradictions about whether docs/tests can be auto-approved

- **Problem**: The governance doc simultaneously claims:
  - Tier 1 includes “new test files” and “documentation updates” as auto-approved examples, and
  - Category safety says tests/docs require approval (not auto-approved) per NEVER_AUTO_APPROVE policy.
- **Evidence**: `docs/GOVERNANCE.md`:
  - Tier 1 examples include `tests/test_*.py` and `docs/*.md`
  - Category Safety says: “Tests: Require approval … Docs: Require approval …”
  - Auto-approval examples show tests/docs “AUTO_APPROVED”
- **Why P0**: Governance policy is the safety envelope; ambiguity here undermines deterministic approval behavior and operator trust.
- **Recommended direction**:
  - Make one policy canonical and delete the conflicting examples.
  - If current implementation is default-deny for docs/tests, update Tier 1 examples and “Auto-Approved” examples accordingly.
- **Acceptance criteria**:
  - `docs/GOVERNANCE.md` is internally consistent and matches the actual policy in code (and/or has contract tests verifying the documented policy).

### P0.3 GLM is referenced as a required API key in docs, but GLM support is disabled in runtime routing

- **Problem**: Canonical onboarding surfaces still mention GLM as a viable/required provider, while runtime code says GLM is disabled and will error if selected.
- **Evidence**:
  - `docs/PROJECT_INDEX.json` references `GLM_API_KEY` as an option in setup.
  - `src/autopack/llm_service.py` explicitly states GLM support is disabled (`GLM_AVAILABLE = False`) and treats `glm-*` as misconfiguration.
- **Why P0**: This creates a “false affordance” for operators and will cause confusing failures during setup.
- **Recommended direction**:
  - Remove GLM from canonical onboarding docs (or clearly label it “legacy/disabled”) and ensure `docs/PROJECT_INDEX.json` matches `config/models.yaml` and `src/autopack/llm_service.py` behavior.
- **Acceptance criteria**:
  - Canonical docs do not present GLM as a supported provider unless code/config truly support it end-to-end.
  - A doc-contract test blocks reintroducing GLM as “required/normal” if it remains disabled.

### P0.4 Auth/authorization inconsistencies on “operator surface” endpoints (artifact/read endpoints are unauthenticated)

- **Problem**: The canonical contract currently allows many endpoints as **public read** (including run listing and artifact file read). This is convenient for local single-user operation, but it is a **multi-tenant / shared-host risk**.
- **Evidence**:
  - `docs/CANONICAL_API_CONTRACT.md` lists `GET /runs` and artifact endpoints as `Auth: None` and tracks “future auth enhancement”.
- **Why P0 (for your intended future use)**: Once Autopack is used beyond a single local machine, unauthenticated artifact reads can leak secrets/PII in run logs/artifacts.
- **Decision (chosen)**: **Auth required in production/hosted mode** for run listing and artifact reads.
  - Default posture: **secure-by-default** (matches “safe autonomy” thesis and your intended external-side-effect usage).
  - Developer convenience: allow an explicit **dev-only opt-in** for public read (e.g., `AUTOPACK_PUBLIC_READ=1`) and default it to OFF.
- **Implementation direction**:
  - Apply `verify_api_key` (or a single auth dependency) consistently to:
    - `GET /runs`
    - `GET /runs/{run_id}/progress`
    - `GET /runs/{run_id}/artifacts/index`
    - `GET /runs/{run_id}/artifacts/file`
    - `GET /runs/{run_id}/browser/artifacts`
  - Keep “executor trust boundary” endpoints as-is if desired, but document the boundary explicitly in `docs/CANONICAL_API_CONTRACT.md`.
- **Acceptance criteria**:
  - In production/hosted mode: all run listing and artifact reads return 401/403 without auth.
  - In development mode: public read is available only when explicitly enabled and is clearly documented as local-only.

### P0.5 `docs/WORKSPACE_ORGANIZATION_SPEC.md` vs reality drift risk (archival policy vs docs contents)

- **Problem**: The spec states historical `BUILD-NNN_*.md` older than 30 days “should be archived”, but the repo keeps many build reports in `docs/` and `docs/INDEX.md` links to them. This creates ambiguity: is `docs/` “truth sources only” or also “historical reports repository”?
- **Evidence**:
  - `docs/WORKSPACE_ORGANIZATION_SPEC.md` “Historical Files (Should Be Archived)” section.
  - `docs/INDEX.md` includes many `BUILD-*` references and build reports exist under `docs/`.
- **Decision (chosen)**: **Option A** — update the spec to match reality and reduce churn.
  - Rationale: The repo already treats `docs/INDEX.md` as a navigation hub and retains many build reports under `docs/`. Forcing age-based archival would be a large, noisy migration and risks breaking links.
  - Guardrail: Make the distinction explicit:
    - **Canonical operator docs**: small allowlist, drift-tested, copy/paste safe.
    - **Historical build reports**: allowed in `docs/` (or `docs/reports/`) but clearly labeled “historical”, excluded from copy/paste allowlists and drift checks.
- **Acceptance criteria**:
  - `docs/WORKSPACE_ORGANIZATION_SPEC.md` no longer claims age-based archival as a requirement.
  - Canonical operator docs list remains small and mechanically enforced; historical docs are explicitly labeled/excluded.

---

## P1 — Hardening, determinism, and correctness improvements (high ROI)

### P1.1 Dependency drift enforcement is partially disabled (known, but still a gap)

- **Problem**: `.github/workflows/ci.yml` disables full pip-compile drift checking (`scripts/check_dependency_sync.py`) due to cross-platform output drift.
- **Evidence**: `.github/workflows/ci.yml` comments explain the disabled check and the current portability guard.
- **Recommended direction**:
  - Keep Linux-canonical policy (already documented) but add a *stronger* mechanical contract for “pyproject → requirements” sync, e.g.:
    - Run pip-compile in CI and compare output (CI is canonical), or
    - Switch to a tool with stable cross-platform lock outputs (decision).
- **Acceptance criteria**:
  - CI blocks PRs where `pyproject.toml` deps differ from `requirements*.txt` without a corresponding regeneration.

### P1.2 Production compose posture is implied but not concretely provided (prod override template missing)

- **Problem**: `docker-compose.yml` includes explicit warnings and references a `docker-compose.prod.yml` pattern, but the repo does not provide a concrete production override template.
- **Evidence**:
  - `docker-compose.yml` comments reference `docker-compose.prod.yml`.
  - The compose file exposes `db:5432` and `qdrant:6333` ports on the host by default (appropriate for local dev, risky for production if reused).
- **Recommended direction**:
  - Add a **non-secret** `docker-compose.prod.example.yml` that:
    - removes host port exposure for `db`/`qdrant` (internal network only),
    - uses Docker secrets / `*_FILE` envs for credentials,
    - pins images the same way (or by digest if you choose).
- **Acceptance criteria**:
  - There is a clear, copy/paste-safe “production override” template that matches docs (`docs/DEPLOYMENT.md`) and does not encourage unsafe defaults.

### P1.3 Telemetry/usage “cap” is hardcoded as 0 (ROADMAP marker)

- **Problem**: Dashboard usage response sets `cap_tokens=0` and `percent_of_cap=0.0`.
- **Evidence**: `src/autopack/main.py` has `cap_tokens=0  # ROADMAP(P3): Get from config`.
- **Recommended direction**:
  - Define token cap source of truth (likely `config/pricing.yaml` or `config/models.yaml` via a new `telemetry_caps` section).
  - Surface cap consistently in UI and health/ops docs.
- **Acceptance criteria**:
  - Cap tokens come from config; percent is computed correctly; unit tests cover.

### P1.4 Learned rules relevance filtering is incomplete (ROADMAP markers)

- **Problem**: Learned rule selection does not currently use scope intersection / scope-pattern matching, risking noisy hint injection.
- **Evidence**: `src/autopack/learned_rules.py` has ROADMAP markers for:
  - scope path intersection check
  - scope pattern matching
- **Recommended direction**:
  - Implement relevance filters with deterministic matching + stable ordering.
- **Acceptance criteria**:
  - Tests demonstrate correct inclusion/exclusion and stable ordering across runs.

### P1.5 Continuation recovery for truncated JSON is heuristic (ROADMAP marker)

- **Problem**: Truncated “full-file JSON” parsing uses brittle heuristics.
- **Evidence**: `src/autopack/continuation_recovery.py` has `ROADMAP(P4): Use proper JSON parsing with error recovery`.
- **Recommended direction**:
  - Replace with a robust incremental/partial JSON parser strategy (or enforce NDJSON format more strongly).
- **Acceptance criteria**:
  - Add tests for common truncation shapes; continuation prompts never re-generate already-complete files.

### P1.6 Model catalog “seed fallback” still exists (clarify the true source of truth)

- **Observation**: `src/autopack/model_routing_refresh.py` loads from config but still carries `SEED_CATALOG` and a ROADMAP note about “dynamic catalog source”.
- **Recommended direction**:
  - If config files are always present in production (they are copied into Docker image), consider removing seed catalog or constraining it to tests only.
  - If seed fallback is intentionally kept, add contract tests ensuring it cannot drift from config silently.
- **Acceptance criteria**:
  - One clear truth for model pricing + routing selection; drift is mechanically detected.

---

## P2 — UX/DX improvements (important, but not blocking)

### P2.0 Commit hygiene: this report must be tracked in git

- **Problem**: This report can be deleted/lost again unless it is tracked in git.
- **Evidence**: Past deletion event (this file was previously deleted from the workspace); treat as a durability gap for the “repo memory” layer.
- **Recommended direction**:
  - Ensure `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md` is **tracked** (committed) and referenced from `docs/INDEX.md` if you want it discoverable.
- **Acceptance criteria**:
  - `git status` shows the report is not untracked; PR includes this file.

### P2.1 “Two UIs” cleanup: legacy dashboard frontend under `src/autopack/dashboard/frontend/`

- **Problem**: A legacy UI exists under `src/` and contains TODOs/hardcoded URLs. This conflicts with the workspace spec principle “`src/` is code only” and creates “two truths” for UI.
- **Evidence**:
  - `src/autopack/dashboard/frontend/src/components/ModelMapping.jsx` includes a TODO for model override API call.
  - Root UI is the canonical Vite app (`package.json`, `src/frontend/`, `Dockerfile.frontend`).
- **Recommended direction**:
  - Either fully retire/move the legacy dashboard UI to `archive/experiments/` OR migrate any missing features into the root UI.
- **Acceptance criteria**:
  - Only one supported UI path is documented and built in CI and docker.

### P2.2 Makefile/DX mismatch: `make install` uses requirements files, CI uses editable extras

- **Problem**: `Makefile` installs from `requirements-dev.txt`, while CI uses `pip install -e ".[dev]"` (pyproject is SOT). This is a small but real “two truths” for contributors.
- **Recommended direction**:
  - Align `make install` with CI (`pip install -e ".[dev]"`) and keep requirements files as derived artifacts only.
- **Acceptance criteria**:
  - `make install` and CI install the same dependency set.

### P2.3 Canonical docs contain stale response examples (health response version mismatch)

- **Problem**: `docs/DEPLOYMENT.md` includes a `/health` response example with `"version": "1.0.0"`, which does not match current project versioning (`pyproject.toml` is `0.5.1`) and can confuse operators.
- **Evidence**: `docs/DEPLOYMENT.md` contains `"version": "1.0.0"` in the health response example.
- **Recommended direction**:
  - Change the example to match current semantics (or remove fixed version strings from examples).
- **Acceptance criteria**:
  - Canonical docs do not contain obviously stale version literals for contract endpoints.

### P2.4 Contributor onboarding still uses derived requirements as the primary install surface in some docs

- **Problem**: Some onboarding surfaces still instruct installing via `requirements-dev.txt` rather than the canonical pyproject extras.
- **Evidence**: `docs/PROJECT_INDEX.json` has `"install_deps": "pip install -r requirements-dev.txt"`.
- **Recommended direction**:
  - Prefer `pip install -e ".[dev]"` in canonical onboarding docs (keep requirements as derived artifacts for pip compatibility).
- **Acceptance criteria**:
  - The canonical onboarding path (PROJECT_INDEX + CONTRIBUTING) uses the same install method as CI.

### P2.5 Legacy-doc containment: canonical docs must not reference `src/backend/`

- **Problem**: `src/backend/` references exist across many docs (including append-only ledgers and various guides). Even if these are “historical”, they can act as a second truth surface unless clearly labeled or mechanically excluded.
- **Recommended direction**:
  - Add a **mechanical rule**: canonical operator docs (the allowlist in `docs/GOVERNANCE.md` Section 10 + doc-contract allowlist) must not contain `src/backend/`.
  - For documents that intentionally preserve history, add an explicit banner at top: “**LEGACY/HISTORICAL — do not copy/paste**”.
- **Acceptance criteria**:
  - CI fails if any canonical operator doc contains `src/backend/`.
  - Historical docs that still contain legacy paths are explicitly labeled as legacy/historical.

---

## P3 — Supply-chain and scale optimizations (optional, “beyond README”)

### P3.0 Migration surface ambiguity: `alembic` dependency vs scripts-first migration posture

- **Problem**: The repo’s documented “canonical migrations” posture is scripts-first, but `pyproject.toml` still includes `alembic` in core dependencies, which can imply Alembic is active/canonical.
- **Recommended direction** (decision required):
  - **Option A**: Keep Alembic as “future-only” and add an explicit ADR (“Alembic present but not canonical; scripts/migrations is canonical”).
  - **Option B**: Remove Alembic from core dependencies to reduce “two truths” and re-add only if/when it becomes canonical.
- **Acceptance criteria**:
  - Docs and dependencies do not contradict the chosen canonical migration strategy.

### P3.1 Docker base image digest pinning

- **Problem**: Dockerfiles use tags, not immutable digests (explicitly acknowledged in `Dockerfile` comments).
- **Recommended direction**:
  - For high-assurance deployments: pin base images by digest and rely on automation to update digests.
- **Acceptance criteria**:
  - Base images are pinned by digest (or there is an explicit ADR that tags are acceptable with compensating controls).

### P3.2 API performance: `GET /runs` N+1

- **Problem**: Known N+1 pattern for phase counts in run listing.
- **Evidence**: Tracked in `docs/IMPROVEMENTS_GAP_ANALYSIS.md` as GAP-8.11.1.
- **Acceptance criteria**:
  - Phase counts fetched in ≤2 queries for typical list sizes.

---

## Recommended “next PRs” sequence (minimize risk, maximize convergence)

1. **PR-A (P0)**: Fix doc truth for auth
   - Rewrite or archive `docs/AUTHENTICATION.md`
   - Add/extend doc-contract tests to prevent `src/backend/` references in canonical docs

2. **PR-B (P0)**: Fix governance doc contradictions
   - Make `docs/GOVERNANCE.md` match real enforcement (docs/tests approval posture)
   - Add a small contract test if needed (“governance doc must not contradict NEVER_AUTO_APPROVE policy”)

3. **PR-C (P0/P1)**: Resolve GLM drift
   - Remove GLM from canonical onboarding surfaces (or re-enable GLM end-to-end—likely not desired)
   - Align `docs/PROJECT_INDEX.json` + `docs/CONFIG_GUIDE.md` with actual supported providers

4. **PR-D (P1)**: Production compose safety template
   - Add `docker-compose.prod.example.yml` and update `docs/DEPLOYMENT.md` to reference it

5. **PR-E (P1/P2)**: Telemetry caps + polish
   - Wire token caps from config into `/dashboard/usage`
   - Fix stale `/health` example in docs

---

## “Already tracked elsewhere” (still part of the full scan)

To avoid “two truths”, deep closure history/backlogs live in:

- `docs/IMPROVEMENTS_GAP_ANALYSIS.md` (large backlog; includes GAP-8.10 and future GAP-8.11 items)
- `docs/FUTURE_PLAN.md` (project plan index / queued items)
- `docs/SECURITY_BASELINE_AUTOMATION_STATUS.md`, `security/README.md` (security program)
- `docs/INDEX.md` (navigation + recent build/decision references)


