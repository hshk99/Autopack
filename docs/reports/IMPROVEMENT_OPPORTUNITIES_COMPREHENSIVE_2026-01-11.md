# Autopack — Comprehensive Improvement Opportunities Scan (2026-01-11)

**Scope**: Current repo state + recent PR trajectory (as captured by existing in-repo audits) + a fresh mechanical scan (TODO/FIXME/ROADMAP signals, workstation-path leakage, and legacy-path leakage).

**Goal**: One consolidated view of *all* remaining improvement areas vs `README.md` ideal state (**safe, deterministic, mechanically enforceable**) and “beyond README” hardening.

## Canonical sources (already exist — do not duplicate them)

Use these as the durable “deep backlog” and historical record:

- **Repo-wide backlog (P0–P3)**: `docs/IMPROVEMENTS_GAP_ANALYSIS.md`
- **Single-pane scan**: `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`
- **Delta audits**: `docs/reports/IMPROVEMENT_AUDIT_DELTA_2026-01-11.md`, `docs/reports/IMPROVEMENT_AUDIT_FULL_2026-01-11.md`
- **North-star navigation**: `docs/INDEX.md` + SOT ledgers (BUILD_HISTORY / DEBUG_LOG / ARCHITECTURE_DECISIONS)

This file is a **consolidated index of remaining opportunities** plus **new mechanical-scan findings** that are easy to miss.

## Mechanical scan highlights (fresh evidence)

These are counts from a repo-wide scan (intended to detect “copy/paste traps” and stale-claim density):

- **Workstation-path leakage in `docs/`**
  - `c:/dev/Autopack` (case-insensitive): **58 matches** across **20 files**
  - `C:\\dev\\Autopack`: **72 matches** across **17 files**
- **Legacy repo path leakage in `docs/`**
  - `src/backend`: **109 matches** across **16 files**
- **TODO/FIXME/ROADMAP/IN PROGRESS density (whole repo)**
  - **308 matches** across **77 files**
  - Note: a large fraction lives under `archive/` and historical reports; treat “canonical docs” separately from “history.”

## Improvements vs README ideal state (comprehensive, categorized)

### 1) “One truth” surfaces: docs portability + copy/paste safety (P0/P1)

- **Problem**: Canonical-ish planning/onboarding docs still contain workstation-specific commands and legacy paths.
  - Example: `docs/FUTURE_PLAN.md` contains `cd c:/dev/Autopack` (copy/paste trap).
  - Example: `src/backend/` appears in multiple docs; even if historical, it continues to be copied into plans.
- **Why it matters**: README’s thesis (“safe, deterministic, mechanically enforceable”) fails if *human/agent instructions* are not mechanically portable and accurate.
- **Improvement actions**
  - **SOT portability contract**: Add a contract test/check that bans workstation absolute paths in **6-file SOT docs** (or at minimum `docs/FUTURE_PLAN.md`) unless explicitly marked `LEGACY/HISTORICAL`.
  - **Legacy-path containment**: For canonical operator docs, ban `src/backend` mentions (or require a “LEGACY” banner) to avoid “two truths.”
  - **Keep append-only ledgers low-noise**: enforce only on “recent window” for append-only ledgers to avoid rewriting history.

### 2) Feature flags / env vars as a mechanically enforced interface (P0/P1)

- **Problem**: The repo increasingly treats env vars as part of a formal, contract-tested interface.
  - You now have a “single source of truth” (`config/feature_flags.yaml`), but the hard part is keeping it complete and mechanically verified.
- **Why it matters**: Drift here creates a stealth “second truth” surface: code behavior changes without the operator interface being updated.
- **Improvement actions**
  - **Define the boundary**: Decide whether the registry is:
    - **AUTOPACK_* only** (recommended), with explicit handling of legacy aliases, or
    - “all env vars that influence runtime behavior.”
  - **Mechanical extraction parity**: Ensure the registry test extracts env vars from:
    - direct `os.getenv(...)` / `os.environ[...]`, *and*
    - Pydantic settings aliases / field mappings (where many real knobs live).
  - **Operator knob completeness**: Ensure README-described toggles (notably SOT-memory toggles) are always present in the registry and tested.

### 3) Large-module risk (maintainability + review correctness) (P1/P2)

- **Problem**: Multiple “god files” remain (notably `src/autopack/autonomous_executor.py`, `src/autopack/main.py`, provider clients).
- **Why it matters**: Large modules increase regression probability and make it harder to enforce invariants (lint/type safety, contract tests, code review).
- **Improvement actions**
  - **Low-risk extractions first**: split `main.py` into routers (`api/routes/*`) without changing route shapes.
  - **Executor seams**: introduce registry-based phase handlers and extract pure helpers (context loading, retry policy, checkpointing).
  - **Contract tests per seam**: every extraction should add/extend a contract test to prevent behavior drift.

### 4) Lint/type “paper-over” debt on critical paths (P1)

- **Problem**: `pyproject.toml` still contains per-file Ruff ignores for critical runtime files (e.g., `F821`/undefined-name allowances).
- **Why it matters**: “mechanically enforceable” implies critical runtime should not rely on broad lint suppressions to stay green.
- **Improvement actions**
  - **Policy**: quarantine broad ignores only for explicitly quarantined subsystems (e.g., `research/`), not core runtime.
  - **Refactor-driven removal**: as you split modules, remove the ignores and/or replace with narrowly scoped line-level suppressions with comments.
  - **Mypy ladder expansion**: continue the staged mypy allowlist into higher-value modules once the seam refactors land.

### 5) Deployment determinism / parity gaps (CI vs compose vs prod template) (P1/P2)

- **Problem**: Determinism is strong in Dockerfiles (digest pinning), but parity can still drift across CI/compose/prod templates.
- **Why it matters**: Small drift causes “works here, fails there” which undermines operator trust and increases debugging noise.
- **Improvement actions**
  - **Align CI service images with compose** (or document the intentional mismatch in an ADR).
  - **Optional**: digest-pin `postgres` and `qdrant` in the *production override template* if you want parity with Dockerfile supply-chain rigor.
  - **Add a compose topology smoke test** (manual/scheduled, non-blocking if needed): validates nginx routing + backend readiness together.

### 6) Auth + operator UI: end-to-end “production-safe” story (P0/P1)

- **Problem**: The backend supports both API key and JWT auth patterns; the frontend and reverse-proxy topology must have a single coherent “production-safe” story.
- **Why it matters**: Any ambiguity here is a safety bug for hosted/operator contexts (secrets in bundles, unprotected reads, confusing defaults).
- **Improvement actions**
  - **Choose and document**: single-tenant (API-key + outer auth/proxy) vs multi-user (JWT for UI, API key for executor boundary).
  - **Prove it in CI**: contract tests that ensure production auth coverage matches the canonical API contract.

### 7) Health checks correctness (DB backend + provider keys) (P1)

- **Problem**: “health” can become misleading if it assumes SQLite file existence when Postgres is configured, or if it requires *all* provider keys when only one is needed.
- **Why it matters**: Operators rely on health to be a truthful readiness signal; incorrect health checks encourage unsafe secret injection and mis-triage.
- **Improvement actions**
  - Make DB health check reflect the configured DB backend (SQLite file checks vs Postgres connectivity).
  - Make provider-key health reflect “at least one configured provider key” rather than “all keys must exist.”

### 8) Rate limiting behind reverse proxies (correct keying) (P2)

- **Problem**: IP-based rate limiting can be wrong behind nginx without careful forwarded-header trust.
- **Why it matters**: Artifact endpoints + heavy reads become susceptible to unfair throttling or ineffective throttling.
- **Improvement actions**
  - Decide whether rate limiting keys on **principal** (`X-API-Key` / JWT) vs **client IP** (proxy-aware).
  - Document it in `docs/DEPLOYMENT.md`, and (if possible) add a minimal test for the chosen key function.

### 9) Frontend maturity (testing + production posture) (P2)

- **Problem**: The frontend toolchain is clean (Vite + TS strict + ESLint), but there’s limited evidence of:
  - frontend tests,
  - production-safe sourcemap posture, and
  - an explicit auth integration story (if UI is used beyond dev).
- **Why it matters**: The UI is part of the operator surface; it must not become the weakest link.
- **Improvement actions**
  - Add a minimal UI test harness (or component smoke tests) if the UI is production-relevant.
  - Decide sourcemap policy for production builds (enable for internal, disable for hosted/public).

### 10) Repo hygiene / working tree cleanliness (P2)

- **Problem**: The current workspace snapshot includes multiple untracked generated artifacts (`__pycache__`, `.pyc`) and new/untracked source/docs files.
- **Why it matters**: It increases the chance of accidental commits of generated files, and makes audits harder to reproduce.
- **Improvement actions**
  - Ensure `.gitignore` and cleanup scripts cover all generated artifacts for both Python and Node workflows.
  - Add a `clean` script (or expand Makefile/scripts) that reliably purges Python caches and other generated files on Windows and Linux.

## Recommended “next work” ordering (balanced and high ROI)

1. **Docs portability + “copy/paste trap” reduction**: focus on 6-file SOT docs (especially `docs/FUTURE_PLAN.md`).
2. **Feature flags registry mechanical completeness**: finalize boundary + strengthen extraction to include Pydantic settings aliases.
3. **Seam refactors**: split `main.py` into routers; introduce executor handler registry; reduce lint suppressions as seams land.
4. **Deployment parity**: align CI vs compose images; add a lightweight compose topology smoke test.
5. **Health + rate-limit correctness**: ensure health reflects configured backend; decide rate-limit key strategy behind proxies.

---

## Appendix A — Hotspot inventory (exact files)

This appendix is purely mechanical: it lists the files that currently contain high-risk “copy/paste trap” strings.

### A.1 Workstation path leakage: `c:/dev/Autopack` (19 files under `docs/`)

- `docs/reports/IMPROVEMENT_OPPORTUNITIES_COMPREHENSIVE_2026-01-11.md`
- `docs/BUILD_HISTORY.md`
- `docs/reports/IMPROVEMENT_AUDIT_FULL_2026-01-11.md`
- `docs/cursor/CURSOR_PROMPT_IMPLEMENT_IMPROVEMENT_AUDIT_DELTA_2026-01-11.md`
- `docs/reports/IMPROVEMENT_AUDIT_DELTA_2026-01-11.md`
- `docs/FUTURE_PLAN.md`
- `docs/IMPROVEMENTS_GAP_ANALYSIS.md`
- `docs/CHANGELOG.md`
- `docs/guides/RESEARCH_CI_FIX_CHECKLIST.md`
- `docs/DEBUG_LOG.md`
- `docs/PRE_TIDY_GAP_ANALYSIS_2026-01-01.md`
- `docs/guides/BUILD-144_USAGE_TOTAL_TOKENS_MIGRATION_RUNBOOK.md`
- `docs/BUILD-153_COMPLETION_SUMMARY.md`
- `docs/guides/BUILD-142_MIGRATION_RUNBOOK.md`
- `docs/STORAGE_OPTIMIZER_PHASE2_COMPLETION.md`
- `docs/STORAGE_OPTIMIZER_AUTOMATION.md`
- `docs/TIDY_SYSTEM_REVISION_PLAN_2026-01-01.md`
- `docs/cursor/CURSOR_PROMPT_RESEARCH_SYSTEM.md`
- `docs/guides/TELEMETRY_COLLECTION_UNIFIED_WORKFLOW.md`

**Highest-risk instance (6-file SOT)**: `docs/FUTURE_PLAN.md` contains copy/paste commands:

- `cd c:/dev/Autopack` at lines ~698 and ~881 (two occurrences).

### A.2 Workstation path leakage: `C:\\dev\\Autopack` (17 files under `docs/`)

- `docs/BUILD_HISTORY.md`
- `docs/GOVERNANCE.md` (appears with both slash styles in workspace)
- `docs/guides/BUILD-144_USAGE_TOTAL_TOKENS_MIGRATION_RUNBOOK.md`
- `docs/guides/BUILD-142_MIGRATION_RUNBOOK.md`
- `docs/TIDY_LOCKED_FILES_HOWTO.md`
- `docs/guides/WINDOWS_TASK_SCHEDULER_TIDY.md`
- `docs/ARCHITECTURE_DECISIONS.md`
- `docs/guides/BATCH_DRAIN_SYSTEMIC_BLOCKERS_REMEDIATION_PLAN.md`
- `docs/cursor/PROMPT_FOR_OTHER_CURSOR_FILEORG.md`
- `docs/guides/NGROK_SETUP_GUIDE.md`
- `docs/IMPROVEMENTS_GAP_ANALYSIS.md`
- `docs/WORKSPACE_ORGANIZATION_SPEC.md`
- `docs/STORAGE_OPTIMIZER_PHASE3_COMPLETION.md`
- `docs/cursor/CURSOR_PROMPT_RESEARCH_SYSTEM.md`
- `docs/IMPLEMENTATION_PLAN_TIDY_GAP_CLOSURE.md`

**Note**: some of these are Windows-focused runbooks where an absolute Windows path might be acceptable, but it should be explicitly scoped (e.g., “example for this workstation”) and avoided in canonical operator docs and 6-file SOT.

### A.3 Legacy path leakage: `src/backend` (17 files under `docs/`)

- `docs/FUTURE_PLAN.md`
- `docs/BUILD-166_COMPLETION_REPORT.md`
- `docs/BUILD_HISTORY.md`
- `docs/IMPROVEMENTS_GAP_ANALYSIS.md`
- `docs/reports/IMPROVEMENT_AUDIT_FULL_2026-01-11.md`
- `docs/cursor/CURSOR_HELP_EXECUTOR_API_ISSUE.md`
- `docs/CURSOR_PROMPT_IMPLEMENT_COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`
- `docs/reports/IMPROVEMENT_OPPORTUNITIES_COMPREHENSIVE_2026-01-11.md`
- `docs/CANONICAL_API_CONSOLIDATION_PLAN.md`
- `docs/ARCHITECTURE_DECISIONS.md`
- `docs/DEBUG_LOG.md`
- `docs/DOC_LINK_TRIAGE_REPORT.md`
- `docs/reports/COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md`
- `docs/CHANGELOG.md`
- `docs/BUILD-166_CURSOR_ADVICE_FOLLOWUP.md`

**Highest-risk instance (6-file SOT)**: `docs/FUTURE_PLAN.md` includes `Allowed Paths` that contain:

- `src/backend/packs/`
- `src/backend/`

These should be either scoped as “FileOrganizer repo paths” (explicitly not Autopack), moved out of Autopack’s SOT doc, or replaced with paths that exist in this repo.

### A.4 TODO/FIXME/ROADMAP/IN PROGRESS markers outside `archive/`

This is where “real, actionable debt” tends to hide.

- **`src/`**: no matches found (good sign: runtime code is low on “TODO”-style uncertainty markers).
- **`scripts/`**: 20 files with markers (expected; scripts are where long-lived maintenance items often live):
  - `scripts/ci/check_sot_hygiene.py`
  - `scripts/ci/check_security_baseline_log_entry.py`
  - `scripts/ci/check_production_config.py`
  - `scripts/tidy/consolidate_docs_v2.py`
  - `scripts/tidy/sot_summary_refresh.py`
  - `scripts/check_doc_links.py`
  - `scripts/model_intel.py`
  - `scripts/pre_publish_checklist.py`
  - `scripts/pattern_expansion.py`
  - `scripts/file_classifier_with_memory.py`
  - `scripts/integrations/*` (several)
  - (plus a few build seeding helpers: `scripts/create_build132_run.py`, `scripts/seed_build132_run.py`, etc.)
- **`tests/`**: 4 files with markers (mostly expected in tests/contracts):
  - `tests/ci/test_todo_quarantine_policy.py`
  - `tests/test_tidy_entry_id_stability.py`
  - `tests/test_manifest_validation.py`
  - `tests/test_dashboard_integration.py`

---

## Appendix B — Line-level cleanup checklist (SOT + canonical operator docs)

This appendix is intentionally a **checklist**: you can open each file and make the smallest possible change to remove “copy/paste traps” while preserving historical meaning.

### B.1 Canonical operator doc allowlist (what CI actually enforces)

The canonical-doc allowlist is defined in `scripts/ci/check_canonical_doc_refs.py` as `CANONICAL_OPERATOR_DOCS`:

- `docs/QUICKSTART.md`
- `docs/DEPLOYMENT.md`
- `docs/CONTRIBUTING.md`
- `docs/TROUBLESHOOTING.md`
- `docs/ARCHITECTURE.md`
- `docs/GOVERNANCE.md`
- `docs/API_BASICS.md`
- `docs/CANONICAL_API_CONTRACT.md`
- `docs/AUTHENTICATION.md`
- `docs/AUTOPILOT_OPERATIONS.md`
- `docs/PARALLEL_RUNS.md`
- `security/README.md`

CI enforcement patterns (same script) currently include:

- `src/backend/` (legacy)
- `backend/` (legacy)
- workstation paths: `C:\\dev\\Autopack` and `c:/dev/Autopack`

### B.2 6-file SOT docs: workstation-path occurrences (line-level)

Search scope used here:

- `docs/PROJECT_INDEX.json`
- `docs/BUILD_HISTORY.md`
- `docs/DEBUG_LOG.md`
- `docs/ARCHITECTURE_DECISIONS.md`
- `docs/FUTURE_PLAN.md`
- `docs/LEARNED_RULES.json`

#### B.2.1 `docs/FUTURE_PLAN.md`

**Workstation path copy/paste trap**:

- `cd c:/dev/Autopack` appears twice (in fenced bash blocks):
  - around the “Launch Command” section (line ~698)
  - around the “Execution Instructions” section (line ~881)

**Recommended minimal fix**:

- Replace `cd c:/dev/Autopack` with `cd $REPO_ROOT` (or “run from repo root”), keeping the rest of the command unchanged.

#### B.2.2 `docs/BUILD_HISTORY.md`

**Workstation path appears in historical build entries**, e.g. references like:

- `schtasks ... "python C:/dev/Autopack ..."`
- `sqlite:///C:/dev/Autopack/...`

**Recommended minimal fix** (to avoid rewriting history):

- Prefer leaving older entries as-is (append-only ledger), unless you adopt a “recent window only” rewrite policy.
- If you do rewrite: add “HISTORICAL:” marker and/or switch to `$REPO_ROOT` notation where safe.

#### B.2.3 `docs/ARCHITECTURE_DECISIONS.md`

This file contains workstation-path examples inside decision context blocks (e.g., “workstation-specific paths like `C:\\dev\\Autopack`”).

**Recommended minimal fix**:

- Keep as-is when it is explicitly describing the problem (“these exist and are copy/pasted”), but ensure any literal path examples are clearly framed as examples, not instructions.

### B.3 6-file SOT docs: `src/backend` legacy-path occurrences (line-level)

#### B.3.1 `docs/FUTURE_PLAN.md` (highest risk)

Two “Allowed Paths” bullets currently include legacy repo paths:

- `Allowed Paths`: `packs/`, `src/backend/packs/`, `tests/`
- `Allowed Paths`: `src/backend/`, `src/frontend/`, `tests/`

**Why high risk**: this is a 6-file SOT doc and reads like executable governance instructions.

**Recommended minimal fix options**:

- **Option A (best containment)**: move FileOrganizer-specific maintenance items to that project’s own SOT file (run-local), and link to it from `docs/FUTURE_PLAN.md`.
- **Option B (minimal churn)**: prefix these bullets with “FileOrganizer repo paths (NOT Autopack): …” so the string cannot be misread as Autopack’s canonical tree.

#### B.3.2 `docs/BUILD_HISTORY.md` / `docs/DEBUG_LOG.md` / other ledgers

These contain `src/backend/...` in historical entries (e.g., documenting pre-consolidation architecture).

**Recommended approach**:

- Keep historical entries intact; rely on canonical-doc containment to prevent operators from using legacy paths as current truth.

---

## Appendix C — Canonical operator docs: exact excerpts that trigger the CI checker

This appendix is a “direct edit queue” for the **canonical operator doc allowlist** (the set enforced by `scripts/ci/check_canonical_doc_refs.py`).

### C.1 Workstation path references inside canonical operator docs

These are *allowed only when they are explicitly framed as historical examples / “do not copy-paste”*. The CI checker currently permits lines that include markers like `HISTORICAL` / `LEGACY` / `DEPRECATED`.

#### `docs/GOVERNANCE.md`

- **Why it appears**: this is a *meta* warning telling readers that some documents contain workstation paths and are excluded from drift checks.
- **Excerpt** (keep as-is; it is not an instruction to run commands):
  - “These documents contain historical context, workstation-specific paths (e.g., `C:\\dev\\Autopack`)…”

### C.2 Canonical operator docs with no current hits

Based on the current scan of the canonical allowlist for these patterns:

- `c:/dev/Autopack`
- `C:\\dev\\Autopack`
- `src/backend/`
- `backend/`

…the following canonical docs were **clean** (no matches found):

- `docs/QUICKSTART.md`
- `docs/DEPLOYMENT.md`
- `docs/CONTRIBUTING.md`
- `docs/TROUBLESHOOTING.md`
- `docs/ARCHITECTURE.md`
- `docs/API_BASICS.md`
- `docs/CANONICAL_API_CONTRACT.md`
- `docs/AUTHENTICATION.md`
- `docs/AUTOPILOT_OPERATIONS.md`
- `docs/PARALLEL_RUNS.md` (if present)
- `security/README.md`

---

## Appendix D — 6-file SOT docs: direct excerpt list (line-level targets)

This appendix focuses on the **6-file SOT docs** (because they are high-leverage and high copy/paste risk), even when they contain historical content.

### D.1 `docs/FUTURE_PLAN.md` (highest urgency; executable instructions)

Covered in Appendix B already, but restated here for completeness:

- `cd c:/dev/Autopack` (2 occurrences) → replace with `cd $REPO_ROOT` (or “run from repo root”).
- `Allowed Paths` bullets containing `src/backend/...` → scope as “FileOrganizer repo paths” or move out of Autopack SOT.

### D.2 `docs/DEBUG_LOG.md` (append-only; historical, but still copied)

Contains legacy backend references in historical debug entries, e.g.:

- `src/backend/api/runs.py`
- `src/backend/main.py`
- `backend.main:app` → `src/backend/main.py`

**Recommended handling**:

- Prefer not rewriting historical debug entries.
- If you want to reduce copy/paste risk, add a small standard prefix in those entries like:
  - `HISTORICAL (pre-consolidation): ...`

### D.3 `docs/ARCHITECTURE_DECISIONS.md` (durable truth; but contains examples)

Contains `src/backend` / `backend/` mentions in decision context and rationale sections, e.g.:

- A planned DEC referencing “`docs/AUTHENTICATION.md` references `src/backend/*`…”
- Rationale discussing why pattern-based ignores like `backend/` are too broad.

**Recommended handling**:

- Keep these references when they describe historical drift or policy (they are “about the problem”).
- Ensure none of these become executable instructions; where necessary, add “(legacy)” or “(historical)” in-line.

### D.4 `docs/BUILD_HISTORY.md` (append-only; contains both workstation paths and legacy paths)

This file contains:

- workstation-path examples (e.g., `C:\\dev\\Autopack` and `C:/dev/Autopack` inside quoted commands), and
- legacy `src/backend/...` mentions inside historical build entries.

**Recommended handling**:

- Avoid rewriting older entries (append-only).
- If you adopt a “recent window” cleanup policy, restrict edits to the newest N entries and normalize only *instructional* snippets to `$REPO_ROOT`.

### D.5 `docs/PROJECT_INDEX.json` and `docs/LEARNED_RULES.json`

No matches found for the workstation/legacy-path patterns in these two SOT files (good).

---

## Appendix E — PR-ready execution checklist (minimal diffs, maximum closure)

This appendix converts the scan into a **small PR queue**. Each PR is scoped to be reviewable and to reduce “two truths” risk without rewriting history.

### PR-E1 — Fix the two highest-risk copy/paste traps in `docs/FUTURE_PLAN.md` (6-file SOT)

- **Goal**: remove workstation-specific commands and legacy path guidance from a SOT doc that is explicitly used as an execution plan.
- **Minimal edits**:
  - Replace `cd c:/dev/Autopack` → `cd $REPO_ROOT` (or “run from repo root”) in both fenced bash blocks.
  - For the two “Allowed Paths” bullets containing `src/backend/...`:
    - either prefix as **`FileOrganizer repo paths (NOT Autopack): ...`**, or
    - move those maintenance items into the FileOrganizer project’s own SOT/planning file and link from here.
- **Acceptance criteria**:
  - `docs/FUTURE_PLAN.md` contains **no** `c:/dev/Autopack` or `C:\\dev\\Autopack`.
  - `docs/FUTURE_PLAN.md` contains **no** unscoped `src/backend` guidance (either removed or explicitly labeled as non-Autopack).

### PR-E2 — Add a “6-file SOT portability contract” (mechanical enforcement)

Right now the canonical-doc CI check is strong, but **6-file SOT docs** (notably `docs/FUTURE_PLAN.md`) can still accumulate copy/paste traps.

- **Goal**: mechanically block workstation-path reintroduction into the SOT surface.
- **Implementation options**:
  - **Option A (recommended)**: add a dedicated test such as `tests/docs/test_sot_portability_contract.py` that scans only:
    - `docs/PROJECT_INDEX.json`
    - `docs/BUILD_HISTORY.md` (optional: “recent window only”)
    - `docs/DEBUG_LOG.md` (optional: “recent window only”)
    - `docs/ARCHITECTURE_DECISIONS.md` (optional: “recent window only”)
    - `docs/FUTURE_PLAN.md` (strict)
    - `docs/LEARNED_RULES.json`
  - **Option B**: expand the existing canonical-doc checker to also cover SOT docs (risk: false positives in append-only ledgers).
- **Patterns to block** (unless explicitly marked `HISTORICAL`/`LEGACY`):
  - `C:\\dev\\Autopack` (and variants)
  - `c:/dev/Autopack` (case-insensitive)
- **Acceptance criteria**:
  - CI fails if a workstation absolute path is added to SOT docs (at least `docs/FUTURE_PLAN.md`).
  - No failures triggered by historical ledgers unless you explicitly choose “recent window” enforcement.

### PR-E3 — Containment policy for legacy `src/backend` references in SOT ledgers (optional)

- **Goal**: reduce accidental reintroduction of a legacy repo structure into current plans.
- **Minimal approach**:
  - Do **not** rewrite append-only ledgers; instead add/standardize “HISTORICAL (pre-consolidation)” prefixes where the legacy paths appear as instructions (rare).
  - Keep policy/rationale mentions in `docs/ARCHITECTURE_DECISIONS.md` (they are “about the drift problem”).
- **Acceptance criteria**:
  - Any executable-looking legacy instruction snippet in SOT ledgers is clearly labeled as historical.

### PR-E4 — Scripts-only TODO/ROADMAP triage (reduce long-lived maintenance debt)

The scan shows **no TODO markers in `src/`**, but **20 script files** still contain TODO/ROADMAP/IN PROGRESS markers.

- **Goal**: ensure scripts do not quietly accumulate stale claims that outlive reality.
- **Minimal approach**:
  - For each script TODO:
    - either convert to a concrete issue entry in `docs/FUTURE_PLAN.md` (with status),
    - or mark as explicitly “intentional / low priority,”
    - or delete if obsolete.
  - Optionally add a small “script TODO density” baseline contract (if you want regression-only blocking for scripts too).
- **Acceptance criteria**:
  - Script TODOs are either tracked in one place (FUTURE_PLAN) or explicitly marked as intentionally deferred.

### PR-E5 — Beyond-docs: maintainability risk program (seam refactors) (optional larger effort)

This is not a “minimal PR,” but it is the highest long-term ROI to preserve the README ideal state as the codebase grows.

- **Start with `src/autopack/main.py` → routers** (no route changes), then the executor seams.
- **Acceptance criteria**:
  - Route shapes unchanged; contract tests still pass.
  - Reduced broad lint suppressions on critical runtime paths over time.
