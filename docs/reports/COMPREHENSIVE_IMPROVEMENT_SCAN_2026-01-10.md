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

**Status**: ✅ Appears resolved (auth docs now match `src/autopack/auth/*`).

- **What to improve (still useful)**:
  - Update `docs/ARCHITECTURE_DECISIONS.md` entry **DEC-050** from “🧭 Planned” → “✅ Implemented” if the rewrite is considered complete (avoid “two truths” in the decisions ledger).

### P0.2 `docs/GOVERNANCE.md` contains internal contradictions about whether docs/tests can be auto-approved

**Status**: ❌ Still a “two truths” risk (doc vs contract-tested policy mismatch).

- **Problem**: The repo’s *contract-tested* default-deny policy (DEC-046) requires approval for changes under `docs/`, `tests/`, `config/`, `.github/`, `src/autopack/`, but `docs/GOVERNANCE.md` still describes docs/tests as auto-approvable and lists them as “Allowed Paths”.
- **Evidence**:
  - `src/autopack/planning/plan_proposer.py` defines:
    - `NEVER_AUTO_APPROVE_PATTERNS = ["docs/", "config/", ".github/", "src/autopack/", "tests/"]`
  - `tests/planning/test_governance_policy.py` asserts (DEC-046) that actions touching these paths are **not** auto-approved.
  - `docs/GOVERNANCE.md` includes Tier 1 examples for `tests/` and `docs/`, and lists them under “Allowed Paths”.
- **Why P0**: Governance docs are operator-facing. Drift here makes the system feel nondeterministic even if enforcement is correct.
- **Recommended direction**:
  - Update `docs/GOVERNANCE.md` to match DEC-046 and the contract tests (docs/tests/config/.github/src/autopack are **never auto-approved**).
  - Add a docs contract test that blocks reintroducing “auto-approved” examples for any `NEVER_AUTO_APPROVE_PATTERNS` paths.
- **Acceptance criteria**:
  - `docs/GOVERNANCE.md` describes the same policy that is enforced and tested.

### P0.3 Legacy approval endpoint defaults to auto-approve (conflicts with default-deny posture)

- **Problem**: `POST /approval/request` (BUILD-113/117 legacy) defaults to auto-approving requests via `AUTO_APPROVE_BUILD113=true` default, which contradicts DEC-046’s default-deny posture.
- **Evidence**:
  - `src/autopack/main.py` reads `AUTO_APPROVE_BUILD113` with default `"true"` and immediately approves when enabled.
- **Why P0**: This is a safety footgun if the legacy path is reachable in any environment where approval should be human-in-the-loop.
- **Recommended direction**:
  - Default `AUTO_APPROVE_BUILD113` to `"false"` (opt-in only), or gate the endpoint behind an explicit “legacy mode”.
  - Document legacy behavior clearly (and ideally deprecate/remove if unused).
- **Acceptance criteria**:
  - Default posture is not silent auto-approval.

### P0.4 GLM is referenced in docs, but GLM support is disabled in runtime routing

**Status**: ✅ Canonical onboarding largely labels GLM as tooling-only / disabled for runtime.

- **Remaining improvement (optional)**:
  - Ensure any remaining GLM mentions in canonical “getting started” docs are consistently labeled “tooling-only (not runtime)”.

### P0.5 Auth posture for operator “read” endpoints (prod auth required; dev opt-in public read)

**Status**: ✅ Implemented.

- **Current state**:
  - Production: auth required.
  - Development: public read only when `AUTOPACK_PUBLIC_READ=1`.
- **Still worth doing**:
  - Per-run authorization + artifact redaction (tracked in `docs/IMPROVEMENTS_GAP_ANALYSIS.md` as GAP-8.11.2 / GAP-8.11.3).

### P0.6 `docs/WORKSPACE_ORGANIZATION_SPEC.md` vs reality drift risk (archival policy vs docs contents)

**Status**: ✅ Already updated (event-driven archival, not age-based).

---

## P1 — Hardening, determinism, and correctness improvements (high ROI)

### P1.1 Dependency drift enforcement is partially disabled (known, but still a gap)

**Status**: ✅ CI runs dependency drift checks, but “single deterministic lock surface” is still a decision.

- **Current state**: CI runs `scripts/check_dependency_sync.py` plus `scripts/check_requirements_portability.py` (Linux/CI canonical) to prevent drift.
- **Gap**: This does not yet establish a single deterministic lock output (pip-compile/uv lock) unless you adopt one explicitly.
- **Recommended direction**:
  - Decide whether requirements files remain the derived artifact (current posture) or become the true lock surface (pip-compile/uv).
- **Acceptance criteria**:
  - CI has one unambiguous “dependency truth” and blocks drift against it.

### P1.2 Production compose posture is implied but not concretely provided (prod override template missing)

**Status**: ✅ `docker-compose.prod.example.yml` exists.

- **Remaining improvement**:
  - Ensure docs/comments consistently point at `docker-compose.prod.example.yml` as the safe reference (and consider whether you want a real `docker-compose.prod.yml` tracked or not).

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

**Status**: ✅ No nested dashboard frontend under `src/autopack/dashboard/frontend/` in current repo state.

- **Remaining improvement (still relevant)**:
  - Keep converging docs/compose/CI around the single canonical UI (root Vite frontend).

### P2.2 Makefile/DX mismatch: `make install` uses requirements files, CI uses editable extras

**Status**: ✅ `make install` uses `pip install -e ".[dev]"` (aligned with CI).

### P2.3 Canonical docs contain stale response examples (health response version mismatch)

**Status**: ✅ No obvious `"version": "1.0.0"` example found in `docs/DEPLOYMENT.md` (appears already corrected).

### P2.4 Contributor onboarding still uses derived requirements as the primary install surface in some docs

**Status**: ✅ No `requirements-dev.txt` install instruction found in `docs/PROJECT_INDEX.json` in current state.

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

1. **PR-A (P0)**: Governance “one truth” convergence (DEC-046)
   - Update `docs/GOVERNANCE.md` to match the contract-tested default-deny posture (`NEVER_AUTO_APPROVE_PATTERNS`)
   - Add/extend a docs contract test to block reintroducing “docs/tests are auto-approved” examples

2. **PR-B (P0)**: Remove legacy auto-approval footgun
   - Change `AUTO_APPROVE_BUILD113` default from `true` → `false` (opt-in only), or gate `/approval/request` behind an explicit “legacy mode”
   - Document deprecation/compat posture (keep or remove) so operators know which approval path is canonical

3. **PR-C (P2)**: Operator-surface security hardening
   - Implement per-run authorization checks for artifact endpoints (GAP-8.11.2)
   - Add optional artifact content redaction (GAP-8.11.3)

4. **PR-D (P3)**: API scale polish
   - Fix `GET /runs` N+1 query pattern (GAP-8.11.1)

5. **PR-E (P1/P2)**: Telemetry caps wiring
   - Wire token caps from config into `/dashboard/usage` (remove hardcoded `cap_tokens=0`)

6. **PR-F (P3)**: Migration surface clarity
   - Decide how to treat `alembic` dependency in `pyproject.toml` under scripts-first posture (keep as “future-only” vs move to optional extra vs remove)

---

## “Already tracked elsewhere” (still part of the full scan)

To avoid “two truths”, deep closure history/backlogs live in:

- `docs/IMPROVEMENTS_GAP_ANALYSIS.md` (large backlog; includes GAP-8.10 and future GAP-8.11 items)
- `docs/FUTURE_PLAN.md` (project plan index / queued items)
- `docs/SECURITY_BASELINE_AUTOMATION_STATUS.md`, `security/README.md` (security program)
- `docs/INDEX.md` (navigation + recent build/decision references)

---

## Additional gaps/enhancements found during “continue” pass (still comprehensive, but higher granularity)

### P0 — Safety / policy drift risks

#### P0.X Governance enforcement surfaces are fragmented (legacy vs modern)

- **Problem**: There are (at least) two approval/governance “stories” in the repo:
  - **Modern**: gap → plan proposer (`PlanProposer`) with DEC-046 default-deny contract tests
  - **Legacy**: `/approval/request` endpoint logic (BUILD-113/117) with `AUTO_APPROVE_BUILD113` defaulting to `"true"`
- **Why P0**: If both remain reachable, operators cannot form a reliable model of “what requires approval” and “what defaults are safe”.
- **Recommended direction**:
  - Decide and document which surface is canonical (and explicitly deprecate the other).
  - Make legacy defaults safe-by-default if legacy must remain.

### P1 — SOT/spec consistency and mechanical enforcement alignment

#### P1.X “SOT registry vs docs index vs verifier” needs explicit convergence rules

- **Observation**: There are multiple “canonical lists” of SOT/truth docs:
  - `config/sot_registry.json` defines a broader `docs_sot_files` set (includes security ledgers + FUTURE_PLAN + PROJECT_INDEX + LEARNED_RULES, etc.)
  - `scripts/tidy/verify_workspace_structure.py` treats the “6-file SOT” as: `PROJECT_INDEX.json`, `BUILD_HISTORY.md`, `DEBUG_LOG.md`, `ARCHITECTURE_DECISIONS.md`, `FUTURE_PLAN.md`, `LEARNED_RULES.json`
  - `docs/INDEX.md` lists “Primary SOT ledgers” and additional security ledgers
  - `docs/WORKSPACE_ORGANIZATION_SPEC.md` states the “6-file SOT structure” includes `FUTURE_PLAN.md`
- **Why it matters**: The system is designed around “one truth” and mechanical enforcement; multiple overlapping lists are fine only if their relationships are explicit.
- **Recommended direction**:
  - Define *one canonical* SOT registry and treat others as derived projections:
    - `config/sot_registry.json` as the canonical list of protected SOT docs (already used by CI/tests in places)
    - `verify_workspace_structure.py` should reference `config/sot_registry.json` (or auto-generate its SOT list from it) to avoid drift
  - Add/extend a contract test that ensures:
    - `docs/INDEX.md` “SOT docs” section ⟷ `config/sot_registry.json` stay consistent (or explicitly enumerates allowed differences)
- **Acceptance criteria**:
  - A single source of truth for “what is SOT”, and mechanical drift prevention across the three surfaces.

#### P1.Y Workspace DB artifact routing is specified but may not be “self-healing” locally

- **Observation**: Workspace spec explicitly routes telemetry seed DBs to `archive/data/databases/telemetry_seeds/`, and `verify_workspace_structure.py` allows only `autopack.db` at root.
- **Gap**: In a typical local workspace, it’s easy to accumulate many `*.db` files at root (e.g., telemetry seeds). CI won’t see this (since these are ignored), so the only enforcement is “local discipline” + running tidy/verify manually.
- **Recommended direction**:
  - Add an explicit “local hygiene” command (or make `scripts/tidy/tidy_up.py` include a safe “route root DB artifacts” mode) that:
    - moves non-`autopack.db` SQLite DBs into the spec’d archive buckets
    - is safe under Windows file locks (queue/retry)
- **Acceptance criteria**:
  - One command can make a messy local workspace comply with WORKSPACE_ORGANIZATION_SPEC for DB artifacts.

### P2 — Developer experience and release posture (beyond README, still high ROI)

#### P2.X SBOM generation is present; dependency vulnerability scanning is partially “informational”

- **Current state**:
  - Trivy + CodeQL are baseline/diff-gated (blocking regressions) in `.github/workflows/security.yml`
  - SBOM generation exists (CycloneDX) in `security.yml`
  - “Security SARIF Artifacts” workflow exists to generate canonical SARIF artifacts for baseline refresh
  - Safety runs in CI but is not diff-gated and is uploaded only as artifacts
- **Opportunity**:
  - Decide whether Safety results are meant to be actionable/enforced:
    - If yes: normalize + diff-gate (like Trivy/CodeQL) or switch to `pip-audit` / OSV-based scanning with stable keys
    - If no: document it as informational-only and keep it out of “security regression-only blocking” narrative to avoid false expectations

#### P2.Y Migration surface clarity: `alembic` dependency remains in `pyproject.toml`

- **Current state**:
  - DEC-048 declares scripts-first migrations canonical, but `pyproject.toml` still includes `alembic>=1.13.0`.
- **Recommended direction** (decision required):
  - Move Alembic to an optional extra (e.g., `[project.optional-dependencies] migrations = ["alembic>=..."]`) or remove until it becomes canonical.
- **Acceptance criteria**:
  - Dependencies and docs/ADRs do not imply two migration systems are canonical at once.

### P3 — Performance/scale and future hardening

#### P3.X API query consolidation and pagination limits

- **Already tracked**:
  - `GET /runs` N+1 query optimization (GAP-8.11.1)
- **Additional suggestions**:
  - Add explicit server-side caps for “artifact index” size, and return deterministic truncation markers (prevents accidental huge payloads)
  - Add ETag/If-None-Match support for artifact index responses (cheap caching for the UI)


