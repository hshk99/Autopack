# Remaining Improvements After BUILD-162 (Comprehensive Backlog)

This document consolidates **all remaining improvement areas** across:

- **Autopack tidy system** (`scripts/tidy/*`)
- **Documentation integrity** (SOT ledgers, link checks, CI)
- **Storage Optimizer**
- **Autopack core (“True Autonomy”)**

Status baseline: **BUILD-162 complete** (locks UX + `--quick` + SOT summary refresh + doc link CI + queue policies).

---

## Definitions & policies (to reduce ambiguity)

These conventions are **canonical** for planning and future automation:

- **Canonical truth sources**
  - **Markdown SOT ledgers** in `docs/` are canonical (human-readable, reviewable).
  - **PostgreSQL / SQLite** and **Qdrant** are **derived indexes** (rebuildable, must be idempotent).

- **Database fallback**
  - PostgreSQL is the intended production DB.
  - SQLite is an acceptable local/dev fallback when `DATABASE_URL` is not set (but tools must be explicit about which DB they target to avoid surprises).

- **Build counting**
  - **Build entries**: count of BUILD rows/entries in `docs/BUILD_HISTORY.md` (can include multiple entries per BUILD ID).
  - **Unique builds**: count of unique `BUILD-###` identifiers.
  - Any status summary MUST specify which number it is reporting (entries vs unique).

- **Decision naming**
  - Architecture decisions use `DEC-###` (single namespace). Avoid introducing alternate prefixes (e.g., AD-*).

- **Tidy modes**
  - `tidy_up.py --quick`: bounded, fast, skips heavy operations (especially archive consolidation) and should not hang.
  - Full tidy: may perform archive consolidation and deep scanning.

- **Doc link enforcement policy**
  - **Nav-only CI** enforces navigation docs (`README.md`, `docs/INDEX.md`, `docs/BUILD_HISTORY.md`) and fails only on `missing_file` links.
  - **Deep scans** are report-first and should remain opt-in/scheduled until noise is low.
  - Runtime endpoints (`/api/...`, `localhost`) are informational (validated via API contract tests, not file-link checks).

---

## Backlog item template (use this format for new work)

When adding items below, use this structure:

- **Why**: what pain this solves / what “ideal state” gap it closes
- **Scope**: what will be changed (files, commands, flags)
- **Non-goals**: what is explicitly not included
- **Acceptance criteria**: measurable success conditions
- **Failure modes**: how it should fail (and how it should *not* fail)
- **Environment assumptions**: required env vars/services (Postgres/Qdrant optionality)
- **CI coverage plan**: what runs always vs scheduled vs optional

---

## Executive summary (what’s left)

### Highest-ROI remaining items (recommended next builds)

1. **Tidy → DB / Qdrant sync path (decouple from full tidy)**
   Make the “SOT → PostgreSQL/Qdrant” sync runnable without a full tidy run and without hanging.

2. **Doc link hygiene in deep mode (reduce noise without weakening nav-only CI)**
   Keep CI strict for navigation docs, but make deep scans actionable (triage + redirect stubs where appropriate).

3. **Parallelism readiness (only if you plan concurrent mutation)**
   Add per-subsystem locks + canonical ordering. Keep umbrella lock as safety net until proven.

4. **Autopack core: telemetry → deterministic mitigations loop**
   Use existing error/telemetry artifacts to automatically propose and codify prevention rules.

5. **Storage Optimizer: execution safety gate + Windows edge hardening**
   If/when destructive actions exist, require approval artifacts and strengthen junction/ACL protections.

---

## 1) Tidy system backlog (beyond BUILD-162)

### 1.1 SOT → DB/Qdrant sync decoupling (production reliability)

**Problem**: The repo has multiple “sync” concepts:
- README SOT summary refresh (now fast via `sot_summary_refresh.py`)
- Full tidy run (`tidy_up.py`)
- Structured DB/Qdrant sync (`db_sync.py` / similar)

**Goal**: Provide a **standalone, bounded** sync command that does not depend on full tidy and is safe to run frequently.

**Suggested implementation**
- Add a focused CLI:
  - `python scripts/tidy/sot_db_sync.py --execute`
  - Modes:
    - `--docs-only` (no DB writes; just validates parse + prints planned operations)
    - `--db-only` (write to DB, no Qdrant)
    - `--qdrant-only` (write to Qdrant, no DB)
    - `--full` (DB + Qdrant)
- Add clear timeouts:
  - `--max-seconds` default (e.g., 60–120)
  - per-step timing output
 - Be explicit about targets:
   - `--database-url` override (otherwise use `DATABASE_URL` or default to SQLite)
   - `--qdrant-host` override (otherwise use `QDRANT_HOST` or skip unless required by mode)

**Acceptance criteria**
- Sync completes in bounded time on typical workspace.
- If DB or Qdrant unreachable, the command exits with a clear diagnostic and does not partially corrupt state.
- Running sync twice is idempotent (no duplicates).
 - No-surprises behavior:
   - DB writes only occur when explicitly requested (`--db-only`/`--full`) AND `--execute` is set.
   - Qdrant writes only occur when explicitly requested AND Qdrant is configured.

**Ambiguities to resolve**
- What is canonical: DB, Qdrant, or markdown SOT?
  Recommendation: markdown SOT is canonical; DB/Qdrant are derived indexes.
 - Migration behavior: does the tool run migrations or require them?
   Recommendation: require schema/migrations already applied (fail fast with instructions), unless you add a minimal “ensure table exists” step solely for the SOT index table.

---

### 1.2 Subsystem locks + lock ordering (parallel mutation readiness)

**Only needed if** you anticipate running tidy concurrently with other mutation processes (scheduled tasks, parallel autopack runs, storage optimizer execution).

**Suggested implementation**
- Add `scripts/tidy/locks.py` implementing a `MultiLock` that acquires per-subsystem locks in a canonical order:
  - `queue -> runs -> archive -> docs` (plus optional umbrella `tidy`)
- Extend lock UX:
  - `--lock-status --all` already exists; ensure it shows subsystem locks too.

**Acceptance criteria**
- No deadlocks (ordering enforced).
- When a subsystem lock is held, other operations report a clear wait/timeout.

**Ambiguities to resolve**
- Whether to keep umbrella `tidy.lock`:
  Recommendation: yes, keep until subsystem locks proven.

---

### 1.3 “Quick tidy” semantics hardening

`--quick` now makes tidy bounded and fast. Remaining polish:

- Add `--quick-include-autonomous-runs-cleanup` (explicit opt-in if not already).
- Ensure `--quick` never triggers deep archive scans or doc consolidation.
 - Document whether `--quick` refreshes README SOT summary automatically (and whether that happens in dry-run).

**Acceptance criteria**
- `--quick` runtime stays stable across large workspaces (< ~5–10s typical).

---

### 1.4 Lease renewal robustness (edge cases)

- Add periodic renewal during long loops (not just phase boundaries).
- Add “heartbeat age” to lock status output (already likely, but ensure it is visible).
- Add `--break-stale-lock --all` (optional) to clean up multiple expired locks safely.

---

## 2) Documentation integrity + CI (beyond BUILD-162)

### 2.1 Deep-scan link hygiene (without weakening nav CI)

**Current state**: nav-only CI is green; deep scan still has runtime/historical links.

**Suggested improvements**
- Extend deep scan reporting to produce:
  - top offenders by source file
  - category breakdown by enforcement policy
  - “fix candidates” list (high-confidence updates)
- Add optional `--check-anchors`:
  - Validate internal anchors in markdown links (`foo.md#section`) *only after paths are stable*.
- Add “redirect stubs” for important moved docs:
  - For historically referenced docs: create a tiny `docs/OLD.md` that points to `docs/NEW.md`
  - Prevents long-tail breakage without forcing massive edits.
 - Clarify and codify classification rules:
   - `missing_file` (CI-failing in nav-only mode)
   - `runtime_endpoint` (informational)
   - `historical_ref` (informational)
   - `external_url` (informational; optional future validator)

**Acceptance criteria**
- Deep scan produces an actionable report with minimal false positives.
- Nav-only CI remains strict and fast.

**Ambiguities to resolve**
- Should BUILD_HISTORY be allowed to reference source code paths?
  Recommendation: allow as informational only; do not enforce as file-links unless you want strictness.
 - Should deep scan include `archive/` by default?
   Recommendation: no; require explicit include globs to avoid noise.

---

### 2.2 META drift elimination (generator-owned truth)

**Observed**: META blocks in SOT ledgers drift (Total_* counts).

**Suggested improvements**
- Either:
  - Update doc generator (`consolidate_docs_v2.py` or similar) to keep META correct, OR
  - Declare META as informational and make derived counts canonical everywhere.

**Acceptance criteria**
- No recurring META vs derived mismatch warnings, OR warnings are explicitly documented as expected.

**Clarification**
- If derived counts are canonical, META mismatches should be treated as warnings only (not blockers), and the generator should be updated when convenient to reduce confusion.

---

### 2.3 CI preflight (developer UX)

Provide a single local command to run the same “pre-push” checks as CI:

- `python scripts/dev_preflight.py` (or `make preflight`)
  - doc link nav check
  - dependency/version drift checks
  - import smoke tests (tidy)
  - syntax check

---

## 3) Storage Optimizer backlog (beyond BUILD-162)

### 3.1 Execution safety gate (if destructive ops are present/planned)

**Suggested improvements**
- Approval artifact requirement for destructive actions:
  - Generate `report.json` with `report_id = sha256(report)`
  - Require `approval.json` containing the report_id before execution
- Emit a signed/hashed audit record for any deletion/move.

**Acceptance criteria**
- No destructive action occurs without an approval artifact.
- All actions produce a durable audit trail artifact.

**Ambiguities to resolve**
- Is deletion/execution currently allowed in Storage Optimizer? If not, treat this as a pre-work item before enabling destructive actions.

---

### 3.2 Windows edge hardening

**Suggested improvements**
- Junction/symlink traversal policy (explicit allow/deny)
- ACL / permission denied behavior: warn and continue; never crash; never bypass protected paths
- Add regression tests for these cases.

---

### 3.3 Incremental scanning (performance + UX)

**Suggested improvements**
- Cache last scan snapshot (paths, sizes, mtimes) and compute delta
- Optional fast scan backend integration (with deterministic fallback)

---

## 4) Autopack core backlog (“True Autonomy”, beyond BUILD-162)

### 4.1 Telemetry → deterministic mitigation loop

**Goal**: reduce repeated incidents without extra LLM calls.

**Suggested implementation**
- New script: `scripts/analyze_failures_to_rules.py`
  - Reads recent `.autonomous_runs/*/errors/*.json` and/or DB telemetry
  - Groups top failure signatures
  - Proposes deterministic mitigations
  - Appends reviewed rules to `docs/LEARNED_RULES.json`

**Acceptance criteria**
- Repeated common failures are reduced over time (measurable).
- Rules are versioned/audited.

**Ambiguities to resolve**
- Where are rules consumed (runtime enforcement vs operator guidance)?
  Recommendation: start as operator guidance + lint-style warnings, then graduate to deterministic enforcement for safe classes.

---

### 4.2 Phase spec invariants enforcement (plan → scope → validation)

**Suggested improvements**
- Validator that refuses phase specs missing:
  - allowed write paths
  - read-only context
  - validation/test command(s)
  - budgets

**Acceptance criteria**
- “goal drift” and unsafe writes become harder to trigger by construction.

---

### 4.3 Shared resource leasing beyond tidy

**Suggested improvements**
- Use the lease primitive for:
  - `autopack.db` migrations
  - `.autonomous_runs` mutations by executor
  - any background maintenance

---

## Suggested build sequencing (optional)

- **BUILD-163**: Standalone SOT→DB/Qdrant sync (bounded + timed) + docs note on canonical counts
- **BUILD-164**: Deep scan hygiene (redirect stubs + optional anchor checking) + refine ignore policy
- **BUILD-165**: Per-subsystem locks + ordering (if parallel mutation is planned soon)
- **BUILD-166**: Telemetry→mitigations loop + LEARNED_RULES workflow
- **BUILD-167**: Storage optimizer execution safety gate + Windows edge tests

---

## Appendix: “What ideal state should look like”

### Tidy
- Always completes (even with locks) and produces actionable next steps.
- Has fast (`--quick`) and full modes with clear semantics.
- Has robust lock UX for operators.

### Docs
- Navigation docs are correct and enforced in CI.
- Deep scans produce triageable reports, not noise.

### Storage optimizer
- Safe by default, auditable, and hardened for Windows edge cases.

### Autopack core
- Prevents repeated failures via deterministic learning.
- Enforces safe scopes and validation.
