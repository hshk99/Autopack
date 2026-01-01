# Data Retention & Storage Policy (Tidy + Storage Optimizer)

**Version**: 1.0  
**Date**: 2026-01-01  
**Status**: Canonical policy (applies repo-wide)

This document is the **single source of truth** for:
- what must **never** be deleted or moved,
- what may be archived, compacted, or deleted (and under what conditions),
- retention windows for logs/runs/superseded artifacts,
- coordination rules between **Autopack Tidy** and the **Storage Optimizer**.

---

## 1) Definitions

- **SOT (Source of Truth)**: the canonical project knowledge set stored in `docs/` (core 6-file SOT + approved truth guides).
- **Archive**: historical artifacts and inbox buckets under `archive/` (and per-project archives under `.autonomous_runs/<project>/archive/`).
- **Superseded**: artifacts that have been consolidated into SOT and retained for auditability (`archive/superseded/`).
- **Runtime artifacts**: run directories, phase state, diagnostics outputs under `.autonomous_runs/`.

---

## 2) Absolute protections (NEVER delete; NEVER “optimize away”)

These paths are **forbidden** for deletion by Storage Optimizer and should be treated as protected by Tidy:

- **Source code & tests**
  - `src/**`
  - `tests/**`
  - `scripts/**` (except explicit “safe-to-delete” temp outputs under `scripts/storage/tmp/` if created)

- **Git + repo metadata**
  - `.git/**`
  - `.github/**`

- **Core SOT**
  - `docs/PROJECT_INDEX.json`
  - `docs/BUILD_HISTORY.md`
  - `docs/DEBUG_LOG.md`
  - `docs/ARCHITECTURE_DECISIONS.md`
  - `docs/FUTURE_PLAN.md`
  - `docs/LEARNED_RULES.json`
  - plus approved truth guides and specs (see `docs/WORKSPACE_ORGANIZATION_SPEC.md`)

- **Databases (unless explicitly approved)**
  - `*.db`, `*.sqlite`, `autopack.db`, `fileorganizer.db`
  - any Postgres data directories (if used locally)

- **Audit trail**
  - `archive/superseded/**` (keep; only purge via explicit retention policy and explicit approval)

---

## 3) Managed storage categories (allowed actions)

### A) Developer caches (reclaimable; usually safe)

- `**/node_modules/**`
  - **Allowed**: delete with approval (default: approval required)
  - **Preferred**: delete only if not touched in N days (see retention)

- `**/.venv/**`, `**/venv/**`
  - **Allowed**: delete with approval
  - **Preferred**: delete only if not touched in N days

- Build outputs (`dist/`, `build/`, `**/*.pyc`, `__pycache__/`)
  - **Allowed**: delete without approval if clearly regenerable (pyc/cache)
  - For `dist/`/`build/`: approval recommended

### B) Logs and diagnostics (managed; retention-based)

- `archive/diagnostics/**`
- `.autonomous_runs/**/runs/**/diagnostics/**`
- `.autonomous_runs/**/runs/**/errors/**`

**Allowed**:
- compress after X days
- delete after Y days (requires explicit approval if Y is aggressive)

### C) Run artifacts (managed; retention-based)

- `.autonomous_runs/<project>/runs/**`

**Allowed**:
- compress old runs after X days
- delete after Y days **only** if:
  - run is terminal,
  - required summaries/SOT entries exist,
  - and user approval is obtained.

### D) Archive buckets (managed; tidy-first)

- `archive/reports/**`, `archive/research/**`, `archive/prompts/**`, `archive/plans/**`, `archive/unsorted/**`

**Rule**:
- Prefer **Tidy consolidation first**.
- Storage Optimizer may:
  - compress old artifacts,
  - propose deletions only after artifacts are superseded and past retention windows.

---

## 4) Retention windows (default)

These are defaults. Adjust per workstation constraints and project risk tolerance.

- **Root clutter**: should be routed by tidy immediately (no retention at root).
- **Diagnostics/logs**:
  - compress after **14 days**
  - delete after **90 days** (approval required)
- **Run directories**:
  - compress after **30 days**
  - delete after **180 days** (approval required; skip if marked “keep”)
- **`archive/superseded/`**:
  - keep at least **180 days**
  - delete after **365 days** only with explicit approval

---

## 5) Coordination rules (Tidy ↔ Storage Optimizer)

### A) Tidy owns knowledge correctness
- Tidy must never lose information needed for SOT, retrieval, or auditability.
- Storage Optimizer must treat Tidy-managed directories as **managed state**, not trash.

### B) Storage Optimizer must not break retrieval
- Do not delete:
  - SOT files,
  - `archive/superseded/**` inside retention window,
  - required run summaries (if your runtime retrieval depends on them).

### C) Ordering
Recommended operational order:
1) Run `python scripts/tidy/tidy_up.py --execute` (or at least routing-only)
2) Ensure SOT is up to date (dirty marker cleared after next executor startup indexing, if enabled)
3) Run Storage Optimizer cleanup proposals and approvals

---

## 6) Implementation skeleton (how code should use this)

### A) Machine-readable policy file (tooling source of truth)

Tools should load:
- `config/storage_policy.yaml`

This markdown document remains the canonical *human-readable* explanation, but the YAML is what Tidy and Storage Optimizer should execute against.

### A) Policy representation (proposed)

Create a policy loader (YAML or JSON) that maps:
- protected paths globs,
- category match rules,
- allowed actions per category,
- retention windows.

**Location**: `config/storage_policy.yaml`

### B) Tidy integration (skeleton)
- Before moving/deleting anything, check “protected paths”.
- When routing, respect “managed categories”.
- When consolidation happens, preserve `archive/superseded/` and ensure idempotent markers.

### C) Storage Optimizer integration (skeleton)
- Load the policy first.
- Classify candidates into categories.
- For each category, apply retention rules and action permissions.
- Produce a report + require approvals for risky actions.

---

## 7) Notes

- This policy is intentionally conservative.
- If you change retention windows, update both:
  - policy config (machine-readable), and
  - this document (human-readable).


