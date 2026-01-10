# Propose-Only Patchset: Readiness Program + External Side-Effect Posture

This file is a **bundle of propose-only diffs** intended for another Cursor agent to apply.

- **Status**: NOT applied automatically by this patchset file
- **Target**: `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`

---

## Patch 1 — Add “Balanced Readiness Program” + “External-side-effect posture” + “Ready checklist”

```diff
diff --git a/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md b/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
index 0000000..0000000 100644
--- a/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
+++ b/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
@@
 ## Executive Summary (Where you’re already strong)
@@
 The remaining work is mostly **convergence (“one truth”)** and **hardening for multi-tenant / external-side-effect autonomy**, plus a set of tracked performance/UX polish items.
 
 ---
+
+## Balanced “Readiness Program” (equal-weight across all areas)
+
+This section is for the posture: **do not use Autopack until it is ready**. It intentionally avoids over-optimizing any single feature area early. The goal is to raise the floor across *all* critical surfaces at once, matching the README intent of safety + determinism + mechanical enforceability.
+
+### Readiness gates (must all be satisfied before “ready”)
+
+| Gate | What it covers | Exit criteria (must be mechanically enforced) |
+|------|-----------------|----------------------------------------------|
+| G1. Auth & exposure | API auth, endpoint allowlists, production default-deny | CI contract proves **no sensitive endpoint is open** in `AUTOPACK_ENV=production` |
+| G2. Governance & approvals | default-deny change policy, approval flows, “two truths” in governance docs | Docs match enforced rules; approvals cannot be bypassed for protected classes of actions |
+| G3. External side effects | anything that can publish/spend/mutate external systems | Side-effect actions are **proposal-only unless explicitly approved**; approval binding is hash-verified |
+| G4. Secrets & persistence | secret loading, `_FILE` support, disk writes of credentials | Production does not write plaintext secrets; secrets can be injected via secret files |
+| G5. Artifact boundary | artifact viewing endpoints, redaction, size caps, path safety | Artifact endpoints enforce **size bounds** + optional redaction; tested deterministically |
+| G6. Deployment invariants | docker-compose + nginx routing + health semantics | Canonical deployment works end-to-end; health reflects backend readiness (not nginx only) |
+| G7. Observability correctness | usage/metrics endpoints, kill switches, caps | Metrics do not trigger LLM costs; kill switches default OFF; caps are from config |
+| G8. Documentation convergence | canonical contract vs implementation vs tests | No “two truths”: contract docs are validated against code and tests in CI |
+
+### Proposed “equal-weight” PR sequence (balanced across gates)
+
+Instead of optimizing one area early, deliver one readiness slice per gate:
+
+- **R-01 (G1 + G8)**: canonical API contract + auth coverage contracts aligned (docs + CI)
+- **R-02 (G6)**: nginx routing + health semantics made canonical and tested
+- **R-03 (G4)**: `_FILE` secrets support + production secret handling hardening
+- **R-04 (G2)**: governance docs + enforcement surfaces converge; approval endpoints hardened
+- **R-05 (G3)**: external action ledger enforcement: approval binding + “no pending execute”
+- **R-06 (G5)**: artifact boundary: size caps + optional redaction + UI-safe metadata
+- **R-07 (G7)**: observability correctness: token caps source-of-truth + contract tests
+
+### R-* implementation checklists (file-by-file)
+
+These are intentionally “equal weight”: each list is short, high-leverage, and should be covered by a contract test where possible.
+
+- **R-01 (G1 + G8)**:
+  - **Docs**:
+    - Ensure `docs/CANONICAL_API_CONTRACT.md` remains the single canonical list of required endpoints + auth posture (already being enforced by drift audits).
+  - **CI contracts**:
+    - `tests/ci/test_production_auth_coverage.py`: treat both `verify_api_key` and `verify_read_access` as “protected”.
+    - Add/extend a test that fails if any route outside the allowlist is unauthenticated in production.
+  - **Acceptance criteria**:
+    - Drift between canonical contract and implementation is caught before merge.
+
+- **R-02 (G6)**:
+  - **nginx**:
+    - Fix `/api/auth/*` routing so it works alongside `/api/runs*` (no silent prefix-stripping breakage).
+    - Clarify `/health` semantics (nginx liveness vs backend readiness).
+  - **Docs**:
+    - `docs/DEPLOYMENT.md` (or equivalent) documents the canonical reverse-proxy mapping.
+  - **Acceptance criteria**:
+    - In docker-compose + nginx, `/api/runs` and `/api/auth/login` both work as documented.
+
+- **R-03 (G4)**:
+  - **Runtime config**:
+    - Add `*_FILE` support for secrets used by production compose templates (DB URL, JWT keys, API key).
+  - **Tests**:
+    - Add unit tests for each `*_FILE` env var path (missing/unreadable/empty file behavior).
+  - **Acceptance criteria**:
+    - Production compose template works end-to-end without “secret injection drift”.
+
+- **R-04 (G2)**:
+  - **Docs**:
+    - `docs/GOVERNANCE.md` must match the enforced default-deny policy (no internal contradictions).
+  - **Runtime**:
+    - Ensure approval/governance endpoints cannot be reached unauthenticated in production.
+  - **Acceptance criteria**:
+    - Governance docs are not a second truth; approvals cannot be bypassed.
+
+- **R-05 (G3)**:
+  - **Policy**:
+    - Introduce an explicit “side-effect action policy” (what requires approval, what is forbidden to auto-execute).
+  - **Ledger enforcement**:
+    - Require an approval record + payload hash match for side-effect actions; block `PENDING` execution for those classes.
+  - **Acceptance criteria**:
+    - “Proposal-only unless approved” is mechanically enforced.
+
+- **R-06 (G5)**:
+  - **Artifacts API**:
+    - Enforce size caps; optionally redact on read; return metadata indicating truncation/redaction.
+  - **Tests**:
+    - Deterministic tests for truncation + redaction patterns.
+  - **Acceptance criteria**:
+    - Artifact viewing is safe-by-default for hosted usage.
+
+- **R-07 (G7)**:
+  - **Caps source-of-truth**:
+    - Move token cap from “ROADMAP placeholder” to a config-backed value.
+  - **Kill switches**:
+    - Keep observability endpoints behind kill switches default OFF.
+  - **Acceptance criteria**:
+    - Observability is correct, bounded, and cannot accidentally trigger new LLM spend.
+
+---
+
+## Recommended posture for external-side-effect automation (Etsy/Shopify/YouTube/Trading)
+
+This section treats **publishing/listing/trading** as the highest-risk autonomy surfaces. The posture below is designed to match the README’s intent: deterministic, safe-by-default, mechanically enforceable.
+
+### Tiered action policy (A/B/C)
+
+| Tier | Definition | Examples (aligned to your target projects) | Default execution mode |
+|------|------------|--------------------------------------------|------------------------|
+| **A — Read-only / Non-side-effect** | No external mutation; safe to run repeatedly | research, trend discovery, competitor scraping, story ideation, drafting titles/descriptions, simulation/backtests (no orders), local file organization planning | **Auto-run allowed** |
+| **B — Reversible / Locally bounded** | Mutations are local or can be undone safely; bounded spend | background removal, mockup generation, local asset pipelines, staging payload generation (but not publishing) | **Auto-run allowed with constraints** (size/time/cost caps) |
+| **C — External side effects** | Irreversible or money/customer-impacting actions | Etsy/Shopify listing creation, YouTube upload/publish, trading order placement, account changes, paid API spend beyond caps | **Proposal-only** + **explicit approval required** |
+
+### Auth decision (recommended for this posture)
+
+- **Primary control-plane auth**: **`X-API-Key`** (instance/operator key), required in production by default.
+- **JWT (`/api/auth/*`)**: **optional**. Enable only when you need multi-user UI roles; do not make JWT a prerequisite for the executor boundary.
+
+### Approval requirements for Tier C
+
+Tier C must be mechanically approval-gated:
+
+- **Approval is required before execution**, not “best effort”.
+- **Approval must bind to the exact payload** that will execute:
+  - store a **payload hash** at approval time
+  - re-check the **same hash** at execution time
+- **No `PENDING` execution** for Tier C (pending means “blocked”).
+- **Approval must be attributable** (who approved, how, when).
+
+### Minimum audit log fields (publish/trade actions)
+
+For every Tier C proposal and execution attempt, log a structured record with at least:
+
+- **who**: `approved_by` (human identifier), `requested_by` (principal), `auth_principal_type` (api_key/user), `auth_principal_id` (if available)
+- **what**: `action_type`, `provider` (etsy/shopify/youtube/broker), `operation` (create_listing/publish_video/place_order), `run_id`, `phase_id`, `idempotency_key`
+- **when**: `requested_at`, `approved_at`, `executed_at`, `completed_at`
+- **inputs**:
+  - `payload_hash` (required)
+  - `payload_summary` (non-secret, human-readable)
+  - `external_target` (channel/account/store identifier; redacted if sensitive)
+- **outputs**:
+  - `external_object_id` (listing id / video id / order id)
+  - `result_status` (success/failure)
+  - `error_code` / `error_summary` (no secrets)
+- **safety**:
+  - `risk_score` / `risk_level`
+  - `kill_switch_snapshot` (which switches were on/off)
+  - `spend_snapshot` (estimated + actual, if available)
+
+### Kill switches to require before production autonomy
+
+All Tier C actions should be disabled by default and require explicit opt-in via env/config:
+
+- **Global**:
+  - `AUTOPACK_EXTERNAL_ACTIONS_ENABLED=0` (default OFF)
+- **Per-domain**:
+  - `AUTOPACK_ENABLE_ETSY_PUBLISH=0`
+  - `AUTOPACK_ENABLE_SHOPIFY_PUBLISH=0`
+  - `AUTOPACK_ENABLE_YOUTUBE_PUBLISH=0`
+  - `AUTOPACK_ENABLE_TRADING_ORDERS=0`
+- **Spend caps**:
+  - `AUTOPACK_MAX_DAILY_SPEND_USD` (hard cap)
+  - `AUTOPACK_MAX_ACTIONS_PER_DAY` (rate cap)
+- **Dry-run mode**:
+  - `AUTOPACK_SIDE_EFFECTS_DRY_RUN=1` (default ON until explicitly disabled)
+
+---
+
+## “Autopack Ready” checklist (single-pane, equal-weight)
+
+Use this as the final go/no-go checklist. Autopack is “ready” only when every item below is ✅.
+
+- **G1 (Auth & exposure)**:
+  - [ ] In production, all non-allowlisted endpoints reject unauthenticated calls.
+  - [ ] CI proves no protected endpoint can become public without failing contracts.
+
+- **G2 (Governance & approvals)**:
+  - [ ] `docs/GOVERNANCE.md` matches the enforced default-deny policy (no contradictions).
+  - [ ] Approval endpoints cannot be bypassed in production.
+
+- **G3 (External side effects)**:
+  - [ ] Tier C actions are proposal-only unless explicitly approved.
+  - [ ] Approval binds to payload hash; execution re-verifies the hash.
+  - [ ] Audit logs contain the minimum fields (who/what/when/inputs/outputs).
+
+- **G4 (Secrets & persistence)**:
+  - [ ] `*_FILE` secrets are supported for production templates.
+  - [ ] No plaintext credential persistence in production by default.
+
+- **G5 (Artifact boundary)**:
+  - [ ] Artifact endpoints enforce size caps and safe response semantics.
+  - [ ] Optional redaction is deterministic and tested.
+
+- **G6 (Deployment invariants)**:
+  - [ ] nginx routes `/api/runs*` and `/api/auth/*` correctly.
+  - [ ] Health semantics reflect backend readiness in production topology.
+
+- **G7 (Observability correctness)**:
+  - [ ] Observability endpoints are kill-switched default OFF.
+  - [ ] Usage caps come from config and are consistent across UI + API.
+
+- **G8 (Documentation convergence)**:
+  - [ ] Canonical API contract matches implementation (auth + response shapes), and drift is CI-blocked.
```

---

## Patch 2 — Map `R-01..R-07` ↔ existing `PR-01..PR-07`

```diff
diff --git a/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md b/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
index 0000000..0000000 100644
--- a/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
+++ b/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
@@
 ### Proposed “equal-weight” PR sequence (balanced across gates)
@@
 - **R-07 (G7)**: observability correctness: token caps source-of-truth + contract tests
+
+### Mapping: Readiness sequence (`R-*`) ↔ existing executable PR plan (`PR-*`)
+
+The readiness sequence is a *balanced framing* of the already-detailed `PR-01..PR-07` plan below. Use this table to ensure you’re not over-investing in one surface while another remains unsafe.
+
+| Readiness item | Gate(s) | Best matching existing PR(s) | Notes |
+|---------------|---------|-------------------------------|-------|
+| **R-01** | G1 + G8 | **PR-01**, **PR-07** | PR-01 covers operator/auth consistency + contract alignment; PR-07 covers auth decision/UI path. |
+| **R-02** | G6 | **PR-02** | nginx `/api/auth/*` routing without breaking `/api/runs*`, plus health semantics as follow-up. |
+| **R-03** | G4 | **PR-03**, **PR-04** | `_FILE` secrets support (PR-03) + OAuth credential persistence hardening (PR-04). |
+| **R-04** | G2 | **PR-05** (and governance docs follow-up) | PR-05 is where approval enforcement becomes real; governance docs must be updated in the same window to avoid “two truths”. |
+| **R-05** | G3 | **PR-05** | External side effects approval policy enforcement is the core of PR-05. |
+| **R-06** | G5 | **PR-06** | Artifact boundary hardening (caps + optional redaction + UI-safe metadata). |
+| **R-07** | G7 | **PR-07** (plus a focused follow-up) | PR-07 contains the “auth unification decision” milestone; observability token caps may merit a dedicated small PR if not already captured. |
```

---

## Patch 3 — Add cross-link note at PR plan section header + PR-07

```diff
diff --git a/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md b/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
index 0000000..0000000 100644
--- a/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
+++ b/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
@@
 ## Executable PR plan (detailed file-by-file + tests)
+
+**Readiness crosswalk**: This PR plan is the detailed implementation view of the balanced readiness sequence.  
+See the table: **“Mapping: Readiness sequence (`R-*`) ↔ existing executable PR plan (`PR-*`)”** in the “Balanced Readiness Program” section above.
@@
 ### PR-07 (P0/P2): Auth unification decision + minimal UI path
+
+**Readiness crosswalk**: This PR is a key part of **R-01** (G1+G8) and **R-07** (G7) in the readiness program.
```

---

## Patch 4 — Add “Covers: R-* (G*)” under each PR header

```diff
diff --git a/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md b/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
index 0000000..0000000 100644
--- a/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
+++ b/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
@@
 ### PR-01 (P0): Operator auth consistency + update canonical contract
+
+**Covers**: **R-01 (G1 + G8)** — auth/exposure hardening + doc/contract convergence.
@@
 ### PR-02 (P0): Fix nginx `/api/auth/*` routing without breaking existing `/api/runs*`
+
+**Covers**: **R-02 (G6)** — deployment invariants (reverse-proxy routing correctness).
@@
 ### PR-03 (P0): `*_FILE` secrets support (match production compose template)
+
+**Covers**: **R-03 (G4)** — secrets injection + production config correctness.
@@
 ### PR-04 (P0): OAuth credential persistence hardening
+
+**Covers**: **R-03 (G4)** — secret persistence hardening (no plaintext-by-default).
@@
 ### PR-05 (P0/P1): External side effects approval policy enforcement
+
+**Covers**: **R-04 (G2)** + **R-05 (G3)** — governance/approvals + side-effect safety enforcement.
@@
 ### PR-06 (P1): Artifact boundary hardening (size caps + optional redaction on read)
+
+**Covers**: **R-06 (G5)** — artifact boundary safety (bounded responses + optional redaction).
@@
 ### PR-07 (P0/P2): Auth unification decision + minimal UI path
+
+**Covers**: **R-01 (G1 + G8)** + **R-07 (G7)** — operator auth decision + long-term readiness alignment.
```

---

## Patch 5 — Add “Exit criteria (readiness gate)” under each PR header

```diff
diff --git a/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md b/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
index 0000000..0000000 100644
--- a/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
+++ b/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
@@
 ### PR-01 (P0): Operator auth consistency + update canonical contract
+**Exit criteria (readiness gate)**:
+- All operator “read” endpoints return 401/403 without `X-API-Key` in `AUTOPACK_ENV=production`.
+- CI contract coverage recognizes both read-gating (`verify_read_access`) and strict auth (`verify_api_key`) as protection.
+- `docs/CANONICAL_API_CONTRACT.md` matches route auth + response shapes (drift caught in CI).
@@
 ### PR-02 (P0): Fix nginx `/api/auth/*` routing without breaking existing `/api/runs*`
+**Exit criteria (readiness gate)**:
+- In nginx + compose, `/api/runs*` and `/api/auth/*` both work as documented.
+- Deployment docs describe the canonical reverse-proxy mapping (no “two truths”).
+- Health semantics are explicit (nginx liveness vs backend readiness).
@@
 ### PR-03 (P0): `*_FILE` secrets support (match production compose template)
+**Exit criteria (readiness gate)**:
+- `*_FILE` env vars work end-to-end for critical secrets (DB URL, JWT keys, API key).
+- Precedence is deterministic (`*_FILE` > env > defaults) with safe logging.
+- Missing/empty/unreadable secret files fail fast with actionable errors in production.
@@
 ### PR-04 (P0): OAuth credential persistence hardening
+**Exit criteria (readiness gate)**:
+- Production forbids plaintext OAuth token persistence by default (unless explicitly enabled via documented exception).
+- `.credentials/` is clearly excluded/routed per workspace policy and never required for normal operation.
+- Audit logs record credential lifecycle events without leaking secrets.
@@
 ### PR-05 (P0/P1): External side effects approval policy enforcement
+**Exit criteria (readiness gate)**:
+- A deterministic policy declares which actions are Tier C “external side effects”.
+- Tier C actions are proposal-only unless approved; `PENDING` is non-executable for Tier C.
+- Approval binds to payload hash; execution re-verifies hash before side effects.
+- Audit trail contains minimum fields (who/what/when/inputs/outputs) and is queryable.
@@
 ### PR-06 (P1): Artifact boundary hardening (size caps + optional redaction on read)
+**Exit criteria (readiness gate)**:
+- Artifact/file reads are bounded (size caps and/or deterministic truncation markers).
+- Optional redaction is deterministic and tested for common secret patterns.
+- Responses include metadata indicating redaction/truncation was applied (UI-safe).
@@
 ### PR-07 (P0/P2): Auth unification decision + minimal UI path
+**Exit criteria (readiness gate)**:
+- One coherent operator auth story is documented and works in the canonical deployment (no static-bundle secrets).
+- If JWT is used for the UI, it does not weaken the executor boundary (`X-API-Key`) and can be combined with per-run authorization when introduced.
+- Any remaining legacy approval paths/kill switches are explicitly documented (no “silent auto-approve” surprises).
```

---

## Patch 6 — Add readiness score rubric (0–16)

```diff
diff --git a/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md b/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
index 0000000..0000000 100644
--- a/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
+++ b/docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md
@@
 ## “Autopack Ready” checklist (single-pane, equal-weight)
@@
 - **G8 (Documentation convergence)**:
   - [ ] Canonical API contract matches implementation (auth + response shapes), and drift is CI-blocked.
+
+### Readiness score rubric (0–16)
+
+Score each gate from 0–2:
+- **0** = not implemented / not enforced
+- **1** = implemented but not fully contract-tested or has known exceptions
+- **2** = implemented + contract-tested + documented with no “two truths”
+
+| Gate | Score (0–2) | Evidence link (tests/docs) |
+|------|-------------|----------------------------|
+| G1 Auth & exposure |  |  |
+| G2 Governance & approvals |  |  |
+| G3 External side effects |  |  |
+| G4 Secrets & persistence |  |  |
+| G5 Artifact boundary |  |  |
+| G6 Deployment invariants |  |  |
+| G7 Observability correctness |  |  |
+| G8 Documentation convergence |  |  |
+
+**Ready threshold**: 16/16 (no gate can be “1” for production use).
```


