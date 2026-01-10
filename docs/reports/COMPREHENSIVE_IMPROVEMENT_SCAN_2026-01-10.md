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

The remaining work is mostly **convergence ("one truth")** and **hardening for multi-tenant / external-side-effect autonomy**, plus a set of tracked performance/UX polish items.

---

## Balanced "Readiness Program" (equal-weight across all areas)

This section is for the posture: **do not use Autopack until it is ready**. It intentionally avoids over-optimizing any single feature area early. The goal is to raise the floor across *all* critical surfaces at once, matching the README intent of safety + determinism + mechanical enforceability.

### Readiness gates (must all be satisfied before "ready")

| Gate | What it covers | Exit criteria (must be mechanically enforced) |
|------|-----------------|----------------------------------------------|
| G1. Auth & exposure | API auth, endpoint allowlists, production default-deny | CI contract proves **no sensitive endpoint is open** in `AUTOPACK_ENV=production` |
| G2. Governance & approvals | default-deny change policy, approval flows, "two truths" in governance docs | Docs match enforced rules; approvals cannot be bypassed for protected classes of actions |
| G3. External side effects | anything that can publish/spend/mutate external systems | Side-effect actions are **proposal-only unless explicitly approved**; approval binding is hash-verified |
| G4. Secrets & persistence | secret loading, `_FILE` support, disk writes of credentials | Production does not write plaintext secrets; secrets can be injected via secret files |
| G5. Artifact boundary | artifact viewing endpoints, redaction, size caps, path safety | Artifact endpoints enforce **size bounds** + optional redaction; tested deterministically |
| G6. Deployment invariants | docker-compose + nginx routing + health semantics | Canonical deployment works end-to-end; health reflects backend readiness (not nginx only) |
| G7. Observability correctness | usage/metrics endpoints, kill switches, caps | Metrics do not trigger LLM costs; kill switches default OFF; caps are from config |
| G8. Documentation convergence | canonical contract vs implementation vs tests | No "two truths": contract docs are validated against code and tests in CI |

### Proposed "equal-weight" PR sequence (balanced across gates)

Instead of optimizing one area early, deliver one readiness slice per gate:

- **R-01 (G1 + G8)**: canonical API contract + auth coverage contracts aligned (docs + CI)
- **R-02 (G6)**: nginx routing + health semantics made canonical and tested
- **R-03 (G4)**: `_FILE` secrets support + production secret handling hardening
- **R-04 (G2)**: governance docs + enforcement surfaces converge; approval endpoints hardened
- **R-05 (G3)**: external action ledger enforcement: approval binding + "no pending execute"
- **R-06 (G5)**: artifact boundary: size caps + optional redaction + UI-safe metadata
- **R-07 (G7)**: observability correctness: token caps source-of-truth + contract tests

### Mapping: Readiness sequence (`R-*`) ↔ existing executable PR plan (`PR-*`)

The readiness sequence is a *balanced framing* of the already-detailed `PR-01..PR-07` plan below. Use this table to ensure you're not over-investing in one surface while another remains unsafe.

| Readiness item | Gate(s) | Best matching existing PR(s) | Notes |
|---------------|---------|-------------------------------|-------|
| **R-01** | G1 + G8 | **PR-01**, **PR-07** | PR-01 covers operator/auth consistency + contract alignment; PR-07 covers auth decision/UI path. |
| **R-02** | G6 | **PR-02** | nginx `/api/auth/*` routing without breaking `/api/runs*`, plus health semantics as follow-up. |
| **R-03** | G4 | **PR-03**, **PR-04** | `_FILE` secrets support (PR-03) + OAuth credential persistence hardening (PR-04). |
| **R-04** | G2 | **PR-05** (and governance docs follow-up) | PR-05 is where approval enforcement becomes real; governance docs must be updated in the same window to avoid "two truths". |
| **R-05** | G3 | **PR-05** | External side effects approval policy enforcement is the core of PR-05. |
| **R-06** | G5 | **PR-06** | Artifact boundary hardening (caps + optional redaction + UI-safe metadata). |
| **R-07** | G7 | **PR-07** (plus a focused follow-up) | PR-07 contains the "auth unification decision" milestone; observability token caps may merit a dedicated small PR if not already captured. |

### R-* implementation checklists (file-by-file)

These are intentionally "equal weight": each list is short, high-leverage, and should be covered by a contract test where possible.

- **R-01 (G1 + G8)**:
  - **Docs**:
    - Ensure `docs/CANONICAL_API_CONTRACT.md` remains the single canonical list of required endpoints + auth posture (already being enforced by drift audits).
  - **CI contracts**:
    - `tests/ci/test_production_auth_coverage.py`: treat both `verify_api_key` and `verify_read_access` as "protected".
    - Add/extend a test that fails if any route outside the allowlist is unauthenticated in production.
  - **Acceptance criteria**:
    - Drift between canonical contract and implementation is caught before merge.

- **R-02 (G6)**:
  - **nginx**:
    - Fix `/api/auth/*` routing so it works alongside `/api/runs*` (no silent prefix-stripping breakage).
    - Clarify `/health` semantics (nginx liveness vs backend readiness).
  - **Docs**:
    - `docs/DEPLOYMENT.md` (or equivalent) documents the canonical reverse-proxy mapping.
  - **Acceptance criteria**:
    - In docker-compose + nginx, `/api/runs` and `/api/auth/login` both work as documented.

- **R-03 (G4)**:
  - **Runtime config**:
    - Add `*_FILE` support for secrets used by production compose templates (DB URL, JWT keys, API key).
  - **Tests**:
    - Add unit tests for each `*_FILE` env var path (missing/unreadable/empty file behavior).
  - **Acceptance criteria**:
    - Production compose template works end-to-end without "secret injection drift".

- **R-04 (G2)**:
  - **Docs**:
    - `docs/GOVERNANCE.md` must match the enforced default-deny policy (no internal contradictions).
  - **Runtime**:
    - Ensure approval/governance endpoints cannot be reached unauthenticated in production.
  - **Acceptance criteria**:
    - Governance docs are not a second truth; approvals cannot be bypassed.

- **R-05 (G3)**:
  - **Policy**:
    - Introduce an explicit "side-effect action policy" (what requires approval, what is forbidden to auto-execute).
  - **Ledger enforcement**:
    - Require an approval record + payload hash match for side-effect actions; block `PENDING` execution for those classes.
  - **Acceptance criteria**:
    - "Proposal-only unless approved" is mechanically enforced.

- **R-06 (G5)**:
  - **Artifacts API**:
    - Enforce size caps; optionally redact on read; return metadata indicating truncation/redaction.
  - **Tests**:
    - Deterministic tests for truncation + redaction patterns.
  - **Acceptance criteria**:
    - Artifact viewing is safe-by-default for hosted usage.

- **R-07 (G7)**:
  - **Caps source-of-truth**:
    - Move token cap from "ROADMAP placeholder" to a config-backed value.
  - **Kill switches**:
    - Keep observability endpoints behind kill switches default OFF.
  - **Acceptance criteria**:
    - Observability is correct, bounded, and cannot accidentally trigger new LLM spend.

---

## Recommended posture for external-side-effect automation (Etsy/Shopify/YouTube/Trading)

This section treats **publishing/listing/trading** as the highest-risk autonomy surfaces. The posture below is designed to match the README's intent: deterministic, safe-by-default, mechanically enforceable.

### Tiered action policy (A/B/C)

| Tier | Definition | Examples (aligned to your target projects) | Default execution mode |
|------|------------|--------------------------------------------|------------------------|
| **A — Read-only / Non-side-effect** | No external mutation; safe to run repeatedly | research, trend discovery, competitor scraping, story ideation, drafting titles/descriptions, simulation/backtests (no orders), local file organization planning | **Auto-run allowed** |
| **B — Reversible / Locally bounded** | Mutations are local or can be undone safely; bounded spend | background removal, mockup generation, local asset pipelines, staging payload generation (but not publishing) | **Auto-run allowed with constraints** (size/time/cost caps) |
| **C — External side effects** | Irreversible or money/customer-impacting actions | Etsy/Shopify listing creation, YouTube upload/publish, trading order placement, account changes, paid API spend beyond caps | **Proposal-only** + **explicit approval required** |

### Auth decision (recommended for this posture)

- **Primary control-plane auth**: **`X-API-Key`** (instance/operator key), required in production by default.
- **JWT (`/api/auth/*`)**: **optional**. Enable only when you need multi-user UI roles; do not make JWT a prerequisite for the executor boundary.

### Approval requirements for Tier C

Tier C must be mechanically approval-gated:

- **Approval is required before execution**, not "best effort".
- **Approval must bind to the exact payload** that will execute:
  - store a **payload hash** at approval time
  - re-check the **same hash** at execution time
- **No `PENDING` execution** for Tier C (pending means "blocked").
- **Approval must be attributable** (who approved, how, when).

### Minimum audit log fields (publish/trade actions)

For every Tier C proposal and execution attempt, log a structured record with at least:

- **who**: `approved_by` (human identifier), `requested_by` (principal), `auth_principal_type` (api_key/user), `auth_principal_id` (if available)
- **what**: `action_type`, `provider` (etsy/shopify/youtube/broker), `operation` (create_listing/publish_video/place_order), `run_id`, `phase_id`, `idempotency_key`
- **when**: `requested_at`, `approved_at`, `executed_at`, `completed_at`
- **inputs**:
  - `payload_hash` (required)
  - `payload_summary` (non-secret, human-readable)
  - `external_target` (channel/account/store identifier; redacted if sensitive)
- **outputs**:
  - `external_object_id` (listing id / video id / order id)
  - `result_status` (success/failure)
  - `error_code` / `error_summary` (no secrets)
- **safety**:
  - `risk_score` / `risk_level`
  - `kill_switch_snapshot` (which switches were on/off)
  - `spend_snapshot` (estimated + actual, if available)

### Kill switches to require before production autonomy

All Tier C actions should be disabled by default and require explicit opt-in via env/config:

- **Global**:
  - `AUTOPACK_EXTERNAL_ACTIONS_ENABLED=0` (default OFF)
- **Per-domain**:
  - `AUTOPACK_ENABLE_ETSY_PUBLISH=0`
  - `AUTOPACK_ENABLE_SHOPIFY_PUBLISH=0`
  - `AUTOPACK_ENABLE_YOUTUBE_PUBLISH=0`
  - `AUTOPACK_ENABLE_TRADING_ORDERS=0`
- **Spend caps**:
  - `AUTOPACK_MAX_DAILY_SPEND_USD` (hard cap)
  - `AUTOPACK_MAX_ACTIONS_PER_DAY` (rate cap)
- **Dry-run mode**:
  - `AUTOPACK_SIDE_EFFECTS_DRY_RUN=1` (default ON until explicitly disabled)

---

## "Autopack Ready" checklist (single-pane, equal-weight)

Use this as the final go/no-go checklist. Autopack is "ready" only when every item below is ✅.

- **G1 (Auth & exposure)**:
  - [ ] In production, all non-allowlisted endpoints reject unauthenticated calls.
  - [ ] CI proves no protected endpoint can become public without failing contracts.

- **G2 (Governance & approvals)**:
  - [ ] `docs/GOVERNANCE.md` matches the enforced default-deny policy (no contradictions).
  - [ ] Approval endpoints cannot be bypassed in production.

- **G3 (External side effects)**:
  - [ ] Tier C actions are proposal-only unless explicitly approved.
  - [ ] Approval binds to payload hash; execution re-verifies the hash.
  - [ ] Audit logs contain the minimum fields (who/what/when/inputs/outputs).

- **G4 (Secrets & persistence)**:
  - [x] `*_FILE` secrets are supported for production templates. ✅ PR-03: `config.py` supports `DATABASE_URL_FILE`, `JWT_*_KEY_FILE`, `AUTOPACK_API_KEY_FILE`
  - [x] No plaintext credential persistence in production by default. ✅ PR-04: `OAuthCredentialManager._save()` raises `OAuthProductionSecurityError` in production unless `AUTOPACK_OAUTH_ALLOW_PLAINTEXT_PERSISTENCE=1`

- **G5 (Artifact boundary)**:
  - [ ] Artifact endpoints enforce size caps and safe response semantics.
  - [ ] Optional redaction is deterministic and tested.

- **G6 (Deployment invariants)**:
  - [x] nginx routes `/api/runs*` and `/api/auth/*` correctly. ✅ PR-02: `nginx.conf` has separate `/api/auth/` location block preserving prefix.
  - [x] Health semantics reflect backend readiness in production topology. ✅ PR-02: `/health` proxies to backend, `/nginx-health` for nginx liveness.

- **G7 (Observability correctness)**:
  - [ ] Observability endpoints are kill-switched default OFF.
  - [ ] Usage caps come from config and are consistent across UI + API.

- **G8 (Documentation convergence)**:
  - [ ] Canonical API contract matches implementation (auth + response shapes), and drift is CI-blocked.

### Readiness score rubric (0–16)

Score each gate from 0–2:
- **0** = not implemented / not enforced
- **1** = implemented but not fully contract-tested or has known exceptions
- **2** = implemented + contract-tested + documented with no "two truths"

| Gate | Score (0–2) | Evidence link (tests/docs) |
|------|-------------|----------------------------|
| G1 Auth & exposure | 2 | `tests/ci/test_production_auth_coverage.py` (0 gaps), `tests/ci/test_production_auth_requirement.py` |
| G2 Governance & approvals | 2 | `tests/ci/test_governance_docs_contract.py` (10 tests), `docs/GOVERNANCE.md` (DEC-046 aligned) |
| G3 External side effects | 2 | `tests/ci/test_governance_docs_contract.py` (NEVER_AUTO_APPROVE enforcement), `src/autopack/planning/plan_proposer.py` (default-deny) |
| G4 Secrets & persistence | 2 | `tests/ci/test_secret_file_support.py` (18 tests), `tests/ci/test_oauth_persistence_hardening.py` (11 tests), `docs/DEPLOYMENT.md` (Secret File Support + OAuth Credential Security sections) |
| G5 Artifact boundary | 0 |  |
| G6 Deployment invariants | 2 | `tests/ci/test_nginx_config_contract.py`, `docs/DEPLOYMENT.md` (Reverse Proxy Routing Invariants) |
| G7 Observability correctness | 0 |  |
| G8 Documentation convergence | 2 | `docs/CANONICAL_API_CONTRACT.md` matches implementation |

**Ready threshold**: 16/16 (no gate can be "1" for production use).

---

## P0 — "Two truths" / safety contract violations (must fix)

### P0.1 `docs/AUTHENTICATION.md` is legacy but currently treated as canonical

**Status**: ✅ Appears resolved (auth docs now match `src/autopack/auth/*`).

- **What to improve (still useful)**:
  - Update `docs/ARCHITECTURE_DECISIONS.md` entry **DEC-050** from “🧭 Planned” → “✅ Implemented” if the rewrite is considered complete (avoid “two truths” in the decisions ledger).

### P0.2 `docs/GOVERNANCE.md` contains internal contradictions about whether docs/tests can be auto-approved

**Status**: ✅ Resolved (PR-05 G2+G3).

- **Problem**: The repo's *contract-tested* default-deny policy (DEC-046) requires approval for changes under `docs/`, `tests/`, `config/`, `.github/`, `src/autopack/`, but `docs/GOVERNANCE.md` still describes docs/tests as auto-approvable and lists them as "Allowed Paths".
- **Resolution**:
  - `docs/GOVERNANCE.md` updated to match DEC-046: docs/tests/config/.github/src/autopack are now documented as **NEVER auto-approved**.
  - `tests/ci/test_governance_docs_contract.py` added (10 tests) to block reintroducing "auto-approved" examples for NEVER_AUTO_APPROVE_PATTERNS paths.
  - Tier 1 section clarifies NEVER_AUTO_APPROVE paths.
  - "Allowed Paths" section updated to show only `examples/` and `scripts/` as auto-approvable.
  - "Common Paths" section updated with NEVER_AUTO_APPROVE (DEC-046) subsection.
- **Evidence**:
  - `tests/ci/test_governance_docs_contract.py::test_docs_tests_not_auto_approved` - blocks listing docs/tests as auto-approvable
  - `tests/ci/test_governance_docs_contract.py::test_never_auto_approve_documented` - all NEVER_AUTO_APPROVE_PATTERNS documented
  - `docs/GOVERNANCE.md` now references DEC-046 throughout.

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

## Executable PR plan (detailed file-by-file + tests)

**Readiness crosswalk**: This PR plan is the detailed implementation view of the balanced readiness sequence.
See the table: **"Mapping: Readiness sequence (`R-*`) ↔ existing executable PR plan (`PR-*`)"** in the "Balanced Readiness Program" section above.

This is a more "mechanical" version of the sequence above: each PR lists the exact files to touch and the tests that should be added/updated to prevent regressions.

### PR-01 (P0): Operator auth consistency + update canonical contract

**Covers**: **R-01 (G1 + G8)** — auth/exposure hardening + doc/contract convergence.

**Exit criteria (readiness gate)**:
- All operator "read" endpoints return 401/403 without `X-API-Key` in `AUTOPACK_ENV=production`.
- CI contract coverage recognizes both read-gating (`verify_read_access`) and strict auth (`verify_api_key`) as protection.
- `docs/CANONICAL_API_CONTRACT.md` matches route auth + response shapes (drift caught in CI).

- **Goal**: make production operator surface consistently protected and align the canonical contract with reality.
- **Code changes**:
  - `src/autopack/main.py`
    - Add `Depends(verify_read_access)` to:
      - `GET /runs/{run_id}`
      - `GET /runs/{run_id}/issues/index`
      - `GET /runs/{run_id}/errors`
      - `GET /runs/{run_id}/errors/summary`
- **Doc changes**:
  - `docs/CANONICAL_API_CONTRACT.md`
    - Update the auth posture for `GET /runs/{run_id}` to match the operator-surface model (prod auth required; dev opt-in public read).
- **Tests**:
  - Update `tests/ci/test_production_auth_coverage.py`:
    - It currently detects only `verify_api_key`; extend it to treat `verify_read_access` as “protected” for read endpoints.
  - Add a narrow route-level contract test (new file suggested):
    - `tests/ci/test_operator_read_endpoints_require_auth.py`
    - Assert every `@app.get("/runs...")` endpoint is either allowlisted or has `verify_read_access` (don’t rely on fragile string matching in docs).

### PR-02 (P0): Fix nginx `/api/auth/*` routing without breaking existing `/api/runs*`

**Covers**: **R-02 (G6)** — deployment invariants (reverse-proxy routing correctness).

**Exit criteria (readiness gate)**:
- In nginx + compose, `/api/runs*` and `/api/auth/*` both work as documented.
- Deployment docs describe the canonical reverse-proxy mapping (no "two truths").
- Health semantics are explicit (nginx liveness vs backend readiness).

- **Goal**: make docker-compose + nginx support both:
  - `/api/runs` → backend `/runs`
  - `/api/auth/login` → backend `/api/auth/login`
- **Config changes**:
  - `nginx.conf`
    - Add a dedicated `location /api/auth/ { ... }` that preserves the `/api/auth` prefix when proxying.
    - Keep the existing `/api/` location behavior for legacy non-namespaced routes (until a bigger API namespace decision).
- **Docs**:
  - `docs/DEPLOYMENT.md` and/or `docs/CANONICAL_API_CONTRACT.md`
    - Add a short “nginx routing semantics” note so `/api/*` expectations are explicit.
- **Tests**:
  - Add a simple config contract test (new file):
    - `tests/ci/test_nginx_proxy_contracts.py`
    - Assert nginx has a specific `/api/auth/` location block (string-based, but stable) and that it does not obviously strip the prefix.

### PR-03 (P0): `*_FILE` secrets support (match production compose template)

**Covers**: **R-03 (G4)** — secrets injection + production config correctness.

**Exit criteria (readiness gate)**:
- `*_FILE` env vars work end-to-end for critical secrets (DB URL, JWT keys, API key).
- Precedence is deterministic (`*_FILE` > env > defaults) with safe logging.
- Missing/empty/unreadable secret files fail fast with actionable errors in production.

- **Goal**: production template (`docker-compose.prod.example.yml`) works as-is (beyond providing secrets).
- **Code changes**:
  - `src/autopack/config.py`
    - Support `DATABASE_URL_FILE` (priority over `DATABASE_URL`).
    - Support `JWT_PRIVATE_KEY_FILE` / `JWT_PUBLIC_KEY_FILE` (priority over direct env vars).
    - Optionally support `AUTOPACK_API_KEY_FILE`.
  - Ensure any startup logging continues to use redacted output (`sanitize_url` etc.).
- **Tests**:
  - Add `tests/autopack/test_secret_file_env_support.py`
    - Create temp files with secret content; set `*_FILE`; assert settings/database-url resolution behaves correctly.
    - Include failure modes: missing file, empty file, unreadable.

### PR-04 (P0): OAuth credential persistence hardening

**Covers**: **R-03 (G4)** — secret persistence hardening (no plaintext-by-default).

**Exit criteria (readiness gate)**:
- Production forbids plaintext OAuth token persistence by default (unless explicitly enabled via documented exception).
- `.credentials/` is clearly excluded/routed per workspace policy and never required for normal operation.
- Audit logs record credential lifecycle events without leaking secrets.

- **Goal**: never write OAuth tokens to plaintext disk by default in production.
- **Code changes**:
  - `src/autopack/auth/oauth_lifecycle.py`
    - In `AUTOPACK_ENV=production`, either:
      - forbid persistence entirely unless an explicit override is set, or
      - require encrypted/keychain backend.
  - Potentially introduce a new secret backend using `src/autopack/secrets/store.py` (or extend it) rather than ad-hoc `.credentials/`.
- **Docs**:
  - `docs/AUTHENTICATION.md` (OAuth section) and/or a dedicated `docs/OAUTH_CREDENTIALS.md`:
    - canonical credential storage strategy; production-safe defaults.
- **Tests**:
  - Extend `tests/credentials/test_oauth_lifecycle.py`:
    - Assert production mode fails fast on plaintext persistence unless override is set.

### PR-05 (P0/P1): External side effects approval policy enforcement

**Covers**: **R-04 (G2)** + **R-05 (G3)** — governance/approvals + side-effect safety enforcement.

**Exit criteria (readiness gate)**:
- A deterministic policy declares which actions are Tier C "external side effects".
- Tier C actions are proposal-only unless approved; `PENDING` is non-executable for Tier C.
- Approval binds to payload hash; execution re-verifies hash before side effects.
- Audit trail contains minimum fields (who/what/when/inputs/outputs) and is queryable.

- **Goal**: "external side effects" never execute from `PENDING` unless policy explicitly says no approval is required.
- **Code changes**:
  - `src/autopack/external_actions/models.py` / `ledger.py`
    - Tighten `can_execute()` semantics (or enforce via a higher-level policy gate).
  - Add a policy surface (config YAML) for “approval required per provider/action”.
- **Tests**:
  - Extend `tests/external_actions/test_ledger_idempotency.py`:
    - Assert side-effect providers/actions require APPROVED (and payload hash match).

### PR-06 (P1): Artifact boundary hardening (size caps + optional redaction on read)

**Covers**: **R-06 (G5)** — artifact boundary safety (bounded responses + optional redaction).

**Exit criteria (readiness gate)**:
- Artifact/file reads are bounded (size caps and/or deterministic truncation markers).
- Optional redaction is deterministic and tested for common secret patterns.
- Responses include metadata indicating redaction/truncation was applied (UI-safe).

- **Goal**: safe artifact viewing in hosted/operator contexts.
- **Code changes**:
  - `src/autopack/main.py` (`/runs/{run_id}/artifacts/file`)
    - enforce size cap and/or truncation markers
    - optionally run `ArtifactRedactor` for text-ish content before returning
- **Tests**:
  - Add `tests/artifacts/test_artifact_read_endpoint_hardening.py`:
    - verify traversal block remains
    - verify caps/truncation are enforced
    - verify redaction works when enabled (reuse patterns tested in `tests/artifacts/test_redaction.py`)

### PR-07 (P0/P2): Auth unification decision + minimal UI path

**Readiness crosswalk**: This PR is a key part of **R-01** (G1+G8) and **R-07** (G7) in the readiness program.

**Covers**: **R-01 (G1 + G8)** + **R-07 (G7)** — operator auth decision + long-term readiness alignment.

**Exit criteria (readiness gate)**:
- One coherent operator auth story is documented and works in the canonical deployment (no static-bundle secrets).
- If JWT is used for the UI, it does not weaken the executor boundary (`X-API-Key`) and can be combined with per-run authorization when introduced.
- Any remaining legacy approval paths/kill switches are explicitly documented (no "silent auto-approve" surprises).

- **Goal**: one coherent operator auth story.
- **Option A (single-tenant)**:
  - Keep API key model; document reverse-proxy injection or dev-only public read.
- **Option B (multi-user)**:
  - Add a login page to frontend; store JWT in memory/secure storage; send Bearer to operator endpoints; add run ownership model (larger).
- **Files likely touched**:
  - `src/frontend/*` (add login UI, token handling)
  - `src/autopack/main.py` (accept JWT on operator endpoints) + `src/autopack/models.py` (run ownership) if multi-user

---

## Contract drift audit: `docs/CANONICAL_API_CONTRACT.md` vs `src/autopack/main.py` (actionable mismatches)

This is the highest-signal “diff-to-action” inventory: places where the canonical contract currently states `Auth: None` (or outdated notes) but the implementation is clearly moving toward production read-gating via `verify_read_access`.

### Drift 1 — `GET /runs/{run_id}` auth posture

- **Contract says**: `Auth: None (public read)` (Run Lifecycle section).
- **Code does**: currently **no** `verify_read_access` dependency (unprotected), while the operator-surface model expects prod auth for run data.
- **Resolution**:
  - **Preferred**: update code to require `verify_read_access`, and update contract to match the operator-surface policy (prod requires `X-API-Key`, dev may allow public read).

### Drift 2 — Issue and error read endpoints auth posture

- **Contract says**: these are `Auth: None`:
  - `GET /runs/{run_id}/issues/index`
  - `GET /runs/{run_id}/errors`
  - `GET /runs/{run_id}/errors/summary`
- **Code does**: currently unprotected (no `verify_read_access`), despite being “operator surface” data.
- **Resolution**:
  - Protect them with `verify_read_access` and update contract accordingly.

### Drift 3 — Operator surface notes contain an internal contradiction about dev defaults

- **Contract says** (Operator Surface section):
  - “Development: Public by default, or opt-in to require auth by NOT setting `AUTOPACK_PUBLIC_READ=1`”
  - “Dev with public read (`AUTOPACK_PUBLIC_READ=1`): No auth required”
- **Code does** (`verify_read_access`):
  - Dev **only** allows public read when `AUTOPACK_PUBLIC_READ=1`. If it is unset, behavior depends on whether `AUTOPACK_API_KEY` is configured.
- **Resolution**:
  - Rewrite that bullet list so it matches the actual behavior:
    - dev + `AUTOPACK_PUBLIC_READ=1` ⇒ public
    - dev + `AUTOPACK_PUBLIC_READ!=1` ⇒ requires API key *if configured*; otherwise permissive

### Drift 4 — Nginx proxy contract is not represented in canonical API contract

- **Observed reality**:
  - Frontend uses `API_BASE='/api'` (calls `/api/runs`, `/api/runs/{id}/...`).
  - Nginx proxies `/api/` to backend `/` (stripping the prefix), which makes `/api/runs` work but breaks `/api/auth/*` unless special-cased.
- **Resolution**:
  - Add a small “Reverse proxy routing invariants” section to `docs/CANONICAL_API_CONTRACT.md` (or `docs/DEPLOYMENT.md`) documenting:
    - which external paths exist (`/api/runs`, `/api/auth/*`)
    - how they map to backend routes under nginx

### Applied fix (doc-only): exact lines/endpoints changed in `docs/CANONICAL_API_CONTRACT.md`

This pass **updated the contract document itself** to reflect the recommended production posture (default-deny) and to correct response-shape drift.

- **Authentication header/posture (lines 13–16)**:
  - Added explicit “**Production posture: default-deny**” statement and clarified Bearer tokens are only for `/api/auth/*`.

- **Run Lifecycle section (lines 31–57)**:
  - `GET /runs/{run_id}` (line 31): changed from public-read to “**Requires `X-API-Key` in production** (dev may allow public read)”.
  - `POST /runs/{run_id}/phases/{phase_id}/update_status` (line 36): changed to “**Requires `X-API-Key` in production** (executor trust boundary)”.
  - `POST /runs/{run_id}/phases/{phase_id}/builder_result` (line 42): changed to “**Requires `X-API-Key` in production** (executor trust boundary)”.
  - `POST /runs/{run_id}/phases/{phase_id}/auditor_result` (line 48): changed to “**Requires `X-API-Key` in production** (executor trust boundary)”.
  - `POST /runs/{run_id}/phases/{phase_id}/record_issue` (line 54): changed to “**Requires `X-API-Key` in production** (executor trust boundary)”.

- **Dashboard endpoints auth (lines 79–135)**:
  - `GET /dashboard/runs/{run_id}/status` (line 79): now “Requires `X-API-Key` in production”.
  - `GET /dashboard/usage` (line 84): now “Requires `X-API-Key` in production”.
  - `GET /dashboard/models` (line 90): now “Requires `X-API-Key` in production”.
  - `GET /dashboard/runs/{run_id}/consolidated-metrics` (line 107): now “Requires `X-API-Key` in production”.
  - `GET /dashboard/ab-results` (line 119): now “Requires `X-API-Key` in production”.
  - `POST /dashboard/human-notes` (line 125): now “Requires `X-API-Key` in production”.
  - `POST /dashboard/models/override` (line 131): now “Requires `X-API-Key` in production”.

- **Issue + Error reads auth (lines 141–163)**:
  - `GET /runs/{run_id}/issues/index` (line 141): now “Requires `X-API-Key` in production”.
  - `GET /project/issues/backlog` (line 146): now “Requires `X-API-Key` in production”.
  - `GET /runs/{run_id}/errors` (line 155): now “Requires `X-API-Key` in production”.
  - `GET /runs/{run_id}/errors/summary` (line 160): now “Requires `X-API-Key` in production”.

- **Approval + Governance auth (lines 169–205)**:
  - `POST /approval/request` (line 169): now “Requires `X-API-Key` in production”.
  - `GET /approval/status/{approval_id}` (line 176): now “Requires `X-API-Key` in production”.
  - `GET /approval/pending` (line 181): now “Requires `X-API-Key` in production”.
  - `GET /governance/pending` (line 196): now “Requires `X-API-Key` in production”.
  - `POST /governance/approve/{request_id}` (line 201): now “Requires `X-API-Key` in production”.

- **Operator surface policy bullets + performance note + browser artifacts response (lines 273–305)**:
  - **Auth Policy dev bullet** (line 275): removed the contradictory “dev public by default” phrasing; replaced with a statement aligned to `verify_read_access` behavior.
  - `GET /runs` Notes (line 282): removed “known N+1 query”; replaced with “implementation uses eager loading”.
  - `GET /runs/{run_id}/browser/artifacts` Response (line 305): changed from `{ screenshots, html_files, total_size_bytes }` to `{ artifacts: [{ path, type, size_bytes, modified_at }], total_count }` to match `src/autopack/main.py`.

- **Storage endpoints auth (lines 326–348)**:
  - `GET /storage/steam/games` (line 326): now “Requires `X-API-Key` in production”.
  - `POST /storage/patterns/analyze` (line 331): now “Requires `X-API-Key` in production”.
  - `GET /storage/learned-rules` (line 336): now “Requires `X-API-Key` in production”.
  - `POST /storage/learned-rules/{rule_id}/approve` (line 341): now “Requires `X-API-Key` in production”.
  - `GET /storage/recommendations` (line 346): now “Requires `X-API-Key` in production”.

### CI contract test contradictions (must be updated if/when code is hardened to match the contract)

- **`tests/ci/test_production_auth_coverage.py` only detects `verify_api_key`**:
  - It does not treat `verify_read_access` as “protected”.
  - This means it can under-report coverage and won’t be able to enforce the operator-surface read gating strategy unless extended.

- **`tests/test_canonical_api_contract.py` assumes certain endpoints are callable without API key**:
  - `test_dashboard_endpoints_exist` expects `GET /dashboard/usage` and `GET /dashboard/models` to return 200 without headers.
  - `test_approval_endpoints_exist` expects `GET /approval/pending` to return 200 without headers.
  - If production-style auth is enforced in non-testing mode (or if the `TESTING` bypass is removed), these tests will need to either pass `X-API-Key` headers or accept 401/403 as valid outcomes.

### Applied fix (code + CI): exact routes/functions changed to match the contract

This pass implemented the production default-deny posture in the canonical server by adding `verify_api_key` / `verify_read_access` dependencies to endpoints that were still open.

#### `src/autopack/main.py` (route-level changes)

- **Read endpoints now gated via `verify_read_access`** (prod requires `X-API-Key`, dev can allow public read):
  - `GET /runs/{run_id}` → `get_run(..., _auth=Depends(verify_read_access))`
  - `GET /runs/{run_id}/issues/index` → `get_run_issue_index(..., _auth=Depends(verify_read_access))`
  - `GET /project/issues/backlog` → `get_project_backlog(_auth=Depends(verify_read_access))`
  - `GET /runs/{run_id}/errors` → `get_run_errors(..., _auth=Depends(verify_read_access))`
  - `GET /runs/{run_id}/errors/summary` → `get_run_error_summary(..., _auth=Depends(verify_read_access))`
  - `GET /approval/status/{approval_id}` → `get_approval_status(..., _auth=Depends(verify_read_access))`
  - `GET /approval/pending` → `get_pending_approvals(..., _auth=Depends(verify_read_access))`
  - `GET /governance/pending` → `get_pending_governance_requests(..., _auth=Depends(verify_read_access))`
  - Dashboard reads:
    - `GET /dashboard/runs/{run_id}/status` → `get_dashboard_run_status(..., _auth=Depends(verify_read_access))`
    - `GET /dashboard/usage` → `get_dashboard_usage(..., _auth=Depends(verify_read_access))`
    - `GET /dashboard/models` → `get_dashboard_models(..., _auth=Depends(verify_read_access))`
    - `GET /dashboard/runs/{run_id}/consolidated-metrics` → `get_dashboard_consolidated_metrics(..., _auth=Depends(verify_read_access))`
  - Storage reads:
    - `GET /storage/steam/games` → `get_steam_games(..., _auth=Depends(verify_read_access))`
    - `GET /storage/learned-rules` → `get_learned_rules(..., _auth=Depends(verify_read_access))`
    - `GET /storage/recommendations` → `get_storage_recommendations(..., _auth=Depends(verify_read_access))`

- **Write/control endpoints now gated via `verify_api_key`**:
  - `POST /runs/{run_id}/phases/{phase_id}/update_status` → decorator adds `dependencies=[Depends(verify_api_key)]`
  - `POST /runs/{run_id}/phases/{phase_id}/record_issue` → decorator adds `dependencies=[Depends(verify_api_key)]`
  - `POST /runs/{run_id}/phases/{phase_id}/builder_result` → decorator adds `dependencies=[Depends(verify_api_key)]`
  - **Missing canonical endpoint added**:
    - `POST /runs/{run_id}/phases/{phase_id}/auditor_result` → new `submit_auditor_result(...)` endpoint (also removes unreachable stray `auditor_result` code that was accidentally placed after the builder return)
  - `POST /approval/request` → decorator adds `dependencies=[Depends(verify_api_key)]`
  - `POST /governance/approve/{request_id}` → decorator adds `dependencies=[Depends(verify_api_key)]`
  - `POST /dashboard/human-notes` → adds `api_key: str = Depends(verify_api_key)`
  - `POST /dashboard/models/override` → adds `api_key: str = Depends(verify_api_key)`
  - `POST /storage/patterns/analyze` → decorator adds `dependencies=[Depends(verify_api_key)]`
  - `POST /storage/learned-rules/{rule_id}/approve` → decorator adds `dependencies=[Depends(verify_api_key)]`

#### `tests/ci/test_production_auth_coverage.py` (contract test fix)

- **Auth detection expanded**:
  - Routes protected by either `verify_api_key` **or** `verify_read_access` are now counted as “protected”.
- **Runtime enforcement expanded**:
  - Added a production-mode check that `GET /runs` (a `verify_read_access` endpoint) rejects requests without `X-API-Key`.


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

#### P0.Y Operator-surface auth is not consistently applied across all run endpoints

- **Problem**: Some run-level “read” endpoints in `src/autopack/main.py` do **not** include `Depends(verify_read_access)` even though newer operator-surface endpoints do. In production, this can expose run metadata and error artifacts without auth.
- **Evidence**:
  - ✅ Protected (has `_auth: str = Depends(verify_read_access)`):
    - `GET /runs`
    - `GET /runs/{run_id}/progress`
    - `GET /runs/{run_id}/artifacts/index`
    - `GET /runs/{run_id}/artifacts/file`
    - `GET /runs/{run_id}/browser/artifacts`
  - ❌ Unprotected (no `verify_read_access` dependency):
    - `GET /runs/{run_id}`
    - `GET /runs/{run_id}/issues/index`
    - `GET /runs/{run_id}/errors`
    - `GET /runs/{run_id}/errors/summary`
- **Why P0**: This undermines the documented prod posture (“auth required in production”) and creates an obvious data leak surface in any hosted deployment.
- **Recommended direction**:
  - Add `Depends(verify_read_access)` to all run-level read endpoints (or explicitly mark the few intended to remain public and document why).
  - Add a small contract test that asserts all `@app.get("/runs...")` endpoints require `verify_read_access` unless explicitly allowlisted.
- **Acceptance criteria**:
  - In `AUTOPACK_ENV=production`, all run-level read endpoints return 403 without valid `X-API-Key`.
  - In dev, public read behavior is consistent and fully documented.

#### P0.Z Production compose template uses `*_FILE` secrets, but runtime config does not read `*_FILE`

- **Problem**: `docker-compose.prod.example.yml` uses `DATABASE_URL_FILE`, `JWT_PRIVATE_KEY_FILE`, and `JWT_PUBLIC_KEY_FILE`, but `src/autopack/config.py:get_database_url()` only checks `DATABASE_URL` (and then falls back to config default). There is no corresponding `*_FILE` support in settings.
- **Why P0**: This is both an operator trap (production template looks secure but won’t actually configure the app) and a reliability risk (service may boot with wrong DB URL / missing keys).
- **Recommended direction**:
  - Implement `*_FILE` support for critical secrets:
    - `DATABASE_URL_FILE` (highest priority)
    - `JWT_PRIVATE_KEY_FILE` / `JWT_PUBLIC_KEY_FILE`
    - optionally `AUTOPACK_API_KEY_FILE`
  - Enforce precedence: `*_FILE` > direct env var > defaults, and sanitize logging.
  - Add a small unit test suite for each `*_FILE` path and failure mode (missing file, empty file, unreadable).
- **Acceptance criteria**:
  - Production compose template works end-to-end without modification beyond providing secrets.
  - In production, missing required secret files fails fast with actionable error messages.

#### P0.A Multi-tenant “run ownership” is not represented in the DB schema (blocks per-run authorization)

- **Problem**: The repo is starting to talk about “per-run authorization” (GAP-8.11.2), but the core `Run` DB model has no ownership concept (no `user_id`, no `api_key_hash`, no tenant/project owner fields).
- **Evidence**:
  - `src/autopack/models.py:Run` includes operational fields (state, budgets, timestamps, goal_anchor) but no owner principal.
  - The canonical API auth for most operator endpoints is `X-API-Key` (instance-wide), while JWT/Bearer is used for `/api/auth/*` and OAuth admin surfaces.
- **Why P0**: Without an owner principal, “per-run authorization” cannot be correct—any valid API key (or dev public read) can read all runs. For a hosted/multi-tenant future, this is the core blocker.
- **Recommended direction (choose explicitly)**:
  - **Option A (single-tenant, simplest)**: Treat `AUTOPACK_API_KEY` as instance-wide and explicitly document: “anyone with the key can access all runs”; defer per-run authorization.
  - **Option B (multi-tenant, future-proof)**:
    - Add `runs.owner_user_id` (FK to auth user) and/or `runs.owner_api_key_hash` (for non-JWT clients)
    - Ensure `verify_read_access` returns a principal (user or API key id) and enforce ownership checks at:
      - `GET /runs`, `GET /runs/{run_id}`, and all artifacts/errors/issues endpoints
    - Decide how the UI authenticates (JWT bearer vs API key) and unify semantics.
- **Acceptance criteria**:
  - The repo has a single, explicit stance: either “single-tenant instance key” (documented) or “multi-tenant run ownership” (implemented + tested).

#### P0.B Canonical auth model is split (X-API-Key vs JWT) and the frontend currently uses neither

- **Problem**: The repo currently has *two distinct* auth mechanisms:
  - **Instance API key**: `X-API-Key` checked by `verify_api_key` / `verify_read_access` in `src/autopack/main.py` (used for some endpoints; production hardening requires `AUTOPACK_API_KEY`).
  - **User JWT**: `/api/auth/*` endpoints issue RS256 JWTs and expect `Authorization: Bearer ...` (implemented in `src/autopack/auth/router.py` + `src/autopack/auth/security.py`).

  Meanwhile, the canonical Vite frontend (`src/frontend`) calls the operator surface (`/runs`, `/runs/{run_id}/progress`, `/runs/{run_id}/artifacts/*`) with **no auth headers**.
- **Why P0**: In production mode (`AUTOPACK_ENV=production`), operator endpoints are intended to require auth. Without a single canonical identity story, the UI cannot work safely in a hosted deployment.
- **Recommended direction (explicit decision required)**:
  - **Option A (single-tenant operator key, simplest)**:
    - Keep `X-API-Key` as the only operator auth mechanism.
    - Make the dashboard/UI operate only in environments where auth is not required (dev), or require a reverse proxy that injects `X-API-Key` (explicitly documented as unsafe for multi-user).
    - Consider removing/hibernating user JWT auth if it is not used for operator UI.
  - **Option B (JWT for humans, API key for executors — recommended for multi-user)**:
    - Treat **JWT Bearer** as the canonical auth for the web UI and human operators (login/session).
    - Keep `X-API-Key` as the executor/machine boundary (service-to-service).
    - Wire operator endpoints to accept JWT (and, if needed, also accept `X-API-Key` for trusted automation).
    - Couple this with P0.A (run ownership) so JWT can authorize per-run.
- **Acceptance criteria**:
  - The frontend has a supported auth flow in production that does **not** require embedding secrets in the static bundle.
  - Docs (`docs/CANONICAL_API_CONTRACT.md`, `docs/DEPLOYMENT.md`) describe one coherent operator authentication story.

#### P0.C Nginx `/api/` proxy rewrites paths in a way that breaks `/api/auth/*` endpoints

- **Problem**: `nginx.conf` uses:
  - `location /api/ { proxy_pass http://backend:8000/; }`

  With nginx’s trailing-slash `proxy_pass` behavior, this **strips** the `/api/` prefix when forwarding. That matches the frontend’s current calls for run endpoints (`/api/runs` → backend `/runs`), but it breaks auth endpoints:
  - Browser calls `/api/auth/login` → backend receives `/auth/login` (but FastAPI serves `/api/auth/login`).
- **Why P0**: This prevents the JWT auth system from being usable via the canonical frontend proxy setup.
- **Recommended direction (pick one)**:
  - **Option A**: Make all backend routes live under `/api/*` (bigger change; would require updating many routes + frontend).
  - **Option B**: Keep backend routes at `/runs/*` etc and change auth router prefix to `/auth/*` (drop `/api`), updating docs/tests accordingly.
  - **Option C**: Keep auth at `/api/auth/*` and add a dedicated nginx location that preserves the prefix (e.g., special-case `/api/auth/`), while continuing to strip `/api/` for legacy routes.
- **Acceptance criteria**:
  - In docker-compose + nginx, both `/api/runs` and `/api/auth/login` work as documented.

#### P0.D OAuth credential storage is plaintext on disk by default (`.credentials/credentials.json`)

- **Problem**: `OAuthCredentialManager` persists credentials to a workspace-local directory (default `.credentials/credentials.json`) including sensitive fields (`client_secret`, `access_token`, `refresh_token`) when present.
- **Why P0**: In any real deployment (or even a shared dev machine), plaintext token storage is a major secret leakage risk and bypasses the repo’s “no secrets in repo artifacts” ethos.
- **Recommended direction**:
  - In production (`AUTOPACK_ENV=production`), forbid plaintext credential persistence unless explicitly enabled (fail fast).
  - Move storage to one of:
    - environment variables / secret files (`*_FILE`) with rotation outside the app
    - OS keychain via `keyring` (local single-user)
    - an encrypted file backend (envelope encryption; key provided via secret manager)
  - Ensure `.credentials/` is explicitly ignored and/or routed per workspace spec (it currently isn’t mentioned in WORKSPACE_ORGANIZATION_SPEC).
- **Acceptance criteria**:
  - No production path writes OAuth refresh/access tokens to plaintext disk by default.
  - Operator docs clearly describe the canonical credential storage strategy.

#### P0.E External action ledger approval linkage is underspecified (risk of “approved-by-default” execution)

- **Observation**:
  - `ExternalActionLedger` supports approval (`approve_action(idempotency_key, approval_id, payload_hash=...)`), but `ExternalAction.can_execute()` currently allows execution in `PENDING` state (“If no approval required”).
  - The approval system (`ApprovalRequest`) produces integer `approval_id`s and is used by the executor/Telegram workflow.
- **Why P0**: For “external side effects” (publishing/listing/trading), the repo’s stated posture is human-in-the-loop. Allowing `PENDING` to execute without a strong policy gate risks accidental side effects.
- **Recommended direction**:
  - Make approval requirements explicit per provider/action (policy file), and enforce:
    - `PENDING` is non-executable for “side-effect” actions unless policy says otherwise
    - payload hash is always verified at approval time and re-verified at execution time
  - Normalize the approval reference type:
    - either use ApprovalRequest integer IDs everywhere, or introduce a structured “approval_ref” (type + id)
- **Acceptance criteria**:
  - Any action classified “external side effect” is non-executable without an approval record + payload hash match.
  - Ledger-to-approval linkage is unambiguous and queryable.

### P2 — Minimal viable secure operator auth proposal (smallest coherent end-to-end path)

This is a concrete “first secure milestone” that makes docker-compose + nginx + frontend consistent without a full multi-tenant redesign:

- **Step 1 (P0)**: Fix nginx routing so `/api/auth/*` works without breaking existing `/api/runs*` routes:
  - Add a dedicated `location /api/auth/` that preserves the `/api/auth` prefix when proxying to backend.
  - Keep the current `/api/` strip behavior for legacy routes (`/api/runs` → backend `/runs`) until you decide to fully namespace the API.

- **Step 2 (P0)**: Decide the operator auth posture for the UI:
  - If **single-tenant**: rely on `AUTOPACK_PUBLIC_READ=1` in dev only; in prod, require a reverse proxy auth layer (or add a UI prompt for API key sent as header, but **do not** bake secrets into the bundle).
  - If **multi-user** (recommended): implement a login page and use JWT Bearer for UI calls.

- **Step 3 (P0/P1)**: Make run endpoints consistent:
  - Apply `verify_read_access` to all run read endpoints (see P0.Y).
  - If adopting JWT for UI, update `verify_read_access` to accept JWT and return a principal.

- **Acceptance criteria**:
  - In docker-compose + nginx, auth endpoints are reachable and operator UI can authenticate in the canonical way.
  - In production mode, no operator endpoint that returns run/artifact/error data is accessible without auth.

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

#### P1.Z Artifact read endpoints return raw content; redaction/size caps are not enforced at the boundary

- **Problem**: `GET /runs/{run_id}/artifacts/file` returns raw file content. The repo already has an `ArtifactRedactor` (`src/autopack/artifacts/redaction.py`) and retention concepts (`src/autopack/artifacts/retention.py`), but the API boundary does not apply redaction or size limits.
- **Why P1**: In hosted scenarios, artifact viewing is one of the highest-risk surfaces for accidental secret/PII leakage and DoS via huge files.
- **Recommended direction**:
  - Add size caps at the API boundary (e.g., refuse >N MB, or stream with truncation markers).
  - Add optional redaction on read (policy-gated; at minimum redact common secrets/headers).
  - Return structured metadata including whether redaction/truncation was applied.
- **Acceptance criteria**:
  - Artifact responses never exceed bounded size, and can be safely shown in the UI.
  - Redaction behavior is deterministic and tested (including hyphenated headers, cookies, bearer tokens).

#### P1.A Rate limiting coverage is partial and may be incorrect behind reverse proxies

- **Current state**:
  - SlowAPI is configured with `key_func=get_remote_address`.
  - `POST /runs/start` is rate-limited (`10/minute`).
  - Most operator read endpoints (runs list, artifacts index/file, errors/issues) are not explicitly rate-limited.
- **Why it matters**:
  - In production behind nginx/Traefik, `get_remote_address` may see the proxy IP rather than the real client IP unless forwarded headers are handled correctly, which can make rate limiting ineffective or unfair.
  - Artifact/file endpoints can be abused for bandwidth/CPU even when auth is enforced.
- **Recommended direction**:
  - Decide the canonical rate-limit key:
    - for single-tenant: per-api-key limits may be more meaningful than per-IP
    - for multi-tenant: per-user/per-tenant limits
  - Ensure proxy headers are honored (or explicitly terminate rate limiting at the reverse proxy).
  - Add lightweight rate limits to the heaviest read endpoints (artifacts/file, artifacts/index, /runs list).
- **Acceptance criteria**:
  - Rate limiting is deterministic and effective in the canonical deployment topology (docker-compose + nginx).
  - Tests (or a documented ops runbook) show how limits behave with/without proxy headers.

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

#### P3.Y Compose/digests: Dockerfiles are digest-pinned, but docker-compose images are tag-pinned

- **Current state**:
  - `Dockerfile` and `Dockerfile.frontend` pin base images by digest (good for supply-chain determinism).
  - `docker-compose.yml` pins Postgres/Qdrant by version tag (e.g., `postgres:15.10-alpine`, `qdrant/qdrant:v1.12.5`) but **not** by digest.
- **Why it matters**: Tags can still drift if a registry mutates them (rare but possible); digest pinning is the stronger invariant.
- **Recommended direction**:
  - Decide whether compose images should be digest-pinned for high-assurance deployments.
  - If yes: pin Postgres/Qdrant by digest in the production override template (lowest-churn place).
- **Acceptance criteria**:
  - Either (a) production compose pins images by digest, or (b) there is an explicit ADR that tags are acceptable with compensating controls.

#### P3.Z Nginx `/health` is currently a static “nginx is up” check, not an Autopack backend health check

- **Current state**:
  - `nginx.conf` serves `GET /health` with a static `200 healthy` response.
  - Backend health is at `GET http://backend:8000/health` (compose exposes backend on 8000 in dev).
- **Why it matters**:
  - In production where you might expose only port 80, `GET /health` could appear green even if backend is down/misconfigured (DB, auth keys, etc.).
- **Recommended direction** (pick one):
  - Proxy `GET /health` to backend (`proxy_pass http://backend:8000/health`) and add a separate `GET /nginx-health` for “nginx only”, OR
  - Keep `/health` as nginx-only but document that “real health” is `/api/health` (and implement `/api/health` proxy), OR
  - Keep both with explicit semantics and use them correctly in deployment docs/monitoring.
- **Acceptance criteria**:
  - Production “health” endpoint reflects backend readiness (DB connectivity + config), not just nginx liveness.

### P2 — Infra/doc convergence polish (low effort, reduces “two truths”)

#### P2.Z docker-compose comment references `docker-compose.prod.yml`, but repo provides `docker-compose.prod.example.yml`

- **Problem**: `docker-compose.yml` suggests using `docker-compose.prod.yml`, while the repo ships `docker-compose.prod.example.yml` as the template.
- **Why it matters**: Small drift creates copy/paste confusion for operators, and it’s exactly the kind of “two truths” the repo tries to eliminate.
- **Recommended direction**:
  - Update the comment block in `docker-compose.yml` to reference `docker-compose.prod.example.yml` explicitly (or add a short note: “copy example to prod.yml, do not commit secrets”).
- **Acceptance criteria**:
  - Compose comments and `docs/DEPLOYMENT.md` point at the same production override template and procedure.


