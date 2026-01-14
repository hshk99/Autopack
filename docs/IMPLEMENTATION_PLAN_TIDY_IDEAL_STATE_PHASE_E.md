# Implementation Plan: Autopack Tidy “Ideal State” (Phase E — Prevention + Reuse Quality)

Audience: implementation cursor (cheaper model)
Scope: Improve “tidy up” beyond the current gap-closure so it matches `README.md`’s *ideal intention* and stays clean over time.
Primary entrypoint: `scripts/tidy/tidy_up.py`
Validator: `scripts/tidy/verify_workspace_structure.py`
Key reuse mechanism: SOT indexing + retrieval (`include_sot`) via `MemoryService` and executor startup indexing.

---

## 0) What “ideal state” means (from README intent)

The README’s tidy/SOT intent is **not** “make fewer files”. It is:
- keep a **machine-usable** single source of truth (SOT) with low drift,
- enable **linear reuse** (explicit links/history pack substitution) and **semantic reuse** (vector retrieval),
- avoid rereading entire archives by making knowledge **easy to retrieve when needed**.

This plan focuses on: (A) quality of reuse, (B) preventing re-mess, (C) aligning verifier/spec with actual intended truth sources.

---

## 1) Current status (baseline)

Already implemented:
- unified tidy entrypoint (`scripts/tidy/tidy_up.py`)
- docs hygiene mode + reduction mode
- root routing + safety for divergent root SOT duplicates
- dirty marker handoff + executor detects/clears marker on successful indexing
- verifier runs on Windows and avoids most `.autonomous_runs` false positives
- tests exist for safety + marker behavior

Remaining problems:
- lots of `docs/` warnings because allowlist/spec is too narrow vs repo reality
- `.autonomous_runs/autopack` is treated as a “project” but does not have the 6-file SOT set (fails verification)
- root clutter keeps recurring because many scripts log to CWD
- consolidation can duplicate information over time if not idempotent at the content level
- SOT entries are not guaranteed to be retrieval-friendly (stable anchors, bounded, consistent metadata)

---

## 2) Deliverables

### New/updated docs
- `docs/WORKSPACE_ORGANIZATION_SPEC.md` (update) — clarify what counts as “truth sources”, allowed guides, and `.autonomous_runs/autopack` semantics.
- `docs/TIDY_SYSTEM_USAGE.md` (update) — add “steady-state” workflow and enforcement strategy.

### New code (proposed)
- `src/autopack/logging_config.py` (or `src/autopack/logging_utils.py`) — centralized logging defaults.
- `scripts/tidy/tidy_report.py` — stable report writer (json + md) for each tidy run (optional if already exists elsewhere).
- `scripts/tidy/verify_workspace_structure.py` (update) — align allowlist + project detection.
- `scripts/tidy/tidy_up.py` (optional update) — record report path, record SOT-change hashes, integrate logging redirection hints.

### CI / hooks
- `.github/workflows/ci.yml` update to run workspace verification (initially non-blocking).
- Optional: `.githooks/pre-commit` (or documented hook) to prevent committing root clutter.

---

## 3) Phase E.1 — Align spec + verifier with intended “truth sources” (reduce false warnings)

### Problem
Verifier currently flags many `docs/*.md` as “Non-SOT” even though they are clearly intended *current* documentation (deployment, governance, troubleshooting, runbooks, etc.).

### Design choice
Keep the **6-file SOT set** as “core”, but allow a **curated set of canonical guides** in `docs/` (truth sources), not shoved into `archive/`.

### Implementation steps
1) Define a “truth guides” allowlist in `docs/WORKSPACE_ORGANIZATION_SPEC.md`:
   - Allow explicit filenames like:
     - `DEPLOYMENT.md`, `GOVERNANCE.md`, `TROUBLESHOOTING.md`, `TESTING_GUIDE.md`, `CONFIG_GUIDE.md`, `AUTHENTICATION.md`, etc.
   - Allow patterns for stable categories (keep bounded):
     - `*_GUIDE.md`, `RUNBOOK_*.md`, `*_ROLL_OUT_*.md`, `*_CHECKLIST.md`, `PHASE_*.md` (only if truly canonical)
   - Explicitly state which “build report” forms belong in docs vs archive:
     - Example: `docs/BUILD_HISTORY.md` is canonical, but `docs/BUILD-129_...md` is historical and should be archived.

2) Update `scripts/tidy/verify_workspace_structure.py`:
   - Expand `DOCS_ALLOWED_FILES` / `DOCS_ALLOWED_PATTERNS` to match the spec.
   - Ensure the verifier’s definition matches `tidy_up.py` docs hygiene allowlist, or create a shared module/constants file (recommended) to avoid drift.

3) Update `scripts/tidy/tidy_up.py` docs hygiene:
   - Keep conservative mode reporting aligned with verifier.
   - In `--docs-reduce-to-sot`, move only truly historical/ephemeral docs, not canonical guides.

### Acceptance criteria
- Running verifier produces warnings that are “actionable”, not hundreds of known-good docs.
- `docs/` steady-state contains:
  - the 6 SOT files
  - a bounded set of canonical guides
  - allowed subdirectories (guides/cursor/api/etc.)

---

## 4) Phase E.2 — Decide and encode `.autonomous_runs/autopack` semantics

### Problem
`.autonomous_runs/autopack` exists, but it’s primarily runtime workspace + runs; it does not contain the full 6-file SOT set, so verifier flags it as broken.

### Choose ONE model (write it into spec + code)

**Model A (recommended): `.autonomous_runs/autopack` is a runtime workspace, not a project SOT root**
- Verifier should **exclude** `.autonomous_runs/autopack` from “project SOT validation”
  - Still allow verifying that it has expected runtime directories if desired.

**Model B: `.autonomous_runs/autopack` must become a proper project workspace**
- Create `.autonomous_runs/autopack/docs/` and `.autonomous_runs/autopack/archive/` with the 6-file SOT set.
- Ensure tidy/executor use it consistently for project_id “autopack”.

### Implementation steps
1) Pick model in `docs/WORKSPACE_ORGANIZATION_SPEC.md`.
2) Update `verify_workspace_structure.py` project detection:
   - If Model A: skip `autopack` in known_projects OR treat it as “infra-only”.
   - If Model B: enforce SOT presence and add missing files/directories via tidy/repair command.

### Acceptance criteria
- Verifier does not claim “project autopack is missing SOT” unless that is intentionally required.

---

## 5) Phase E.3 — Centralized logging to prevent root clutter recurrence

### Problem
Root violations are dominated by logs and ad-hoc outputs written to CWD.

### Implementation steps
1) Add `src/autopack/logging_config.py`:
   - Provide a function like `configure_logging(run_id: str | None, project_id: str | None, workspace: Path, default_log_dir: Path)`.
   - Default log dir:
     - Autopack root: `archive/diagnostics/logs/`
     - Sub-project: `.autonomous_runs/<project>/archive/diagnostics/logs/` (or equivalent)
   - Ensure Windows-safe encoding (`utf-8`) and file handler mode.

2) Identify top offenders (scripts that write `*.log` next to CWD):
   - Update them to call the centralized config or to honor `AUTOPACK_LOG_DIR`.

3) Add a small “log-dir guard” helper for scripts:
   - If running in repo root and output filename ends with `.log`, default to archive logs directory.

### Acceptance criteria
- After normal workflows, root log accumulation drops dramatically (new logs go to archive by default).

---

## 6) Phase E.4 — Make consolidation idempotent at the content level (avoid re-duplication)

### Problem
Even if files are moved to `archive/superseded/`, reruns can still re-append similar content if inputs shift or the consolidation process changes.

### Implementation steps (minimal viable)
1) Add stable “merge markers” in SOT ledgers for consolidated entries:
   - include `source_path`, `source_sha`, and a `tidy_run_id`
   - Example marker:
     - `<!-- tidy-merged-from:path=archive/reports/X.md sha=... run=... -->`
2) Before appending a new entry, check if `sha` marker already exists in the target SOT file.
3) Ensure SOT write operations remain **append-only**, but not duplicate.

### Acceptance criteria
- Re-running tidy does not keep growing SOT with repeated identical entries.

---

## 7) Phase E.5 — Improve SOT retrieval quality (make `include_sot` consistently useful)

### Problem
Vector retrieval works best when chunks have consistent structure and high signal. If SOT entries are inconsistent, retrieval can be noisy or miss key info.

### Implementation steps
1) Standardize SOT entry format in the ledgers:
   - For BUILD_HISTORY entries: include stable “Phase ID”, “Files changed”, “Summary”, “Source”
   - For DEBUG_LOG: include “Symptom/Root cause/Fix” fields when possible
   - For ARCHITECTURE_DECISIONS: include “Decision/Options/Rationale/Impact”
2) Ensure chunking boundaries are stable:
   - headings/paragraphs, bounded chunk size, consistent separators (already partly implemented in `sot_indexing.py`)
3) Add a lightweight “SOT smoke check” script:
   - verifies the ledgers exist, are parseable, and contain recent entries

### Acceptance criteria
- With `AUTOPACK_SOT_RETRIEVAL_ENABLED=true`, retrieved SOT context includes relevant, bounded chunks for typical “why is X broken / where is Y implemented” queries.

---

## 8) Phase E.6 — Enforcement: CI and pre-commit (prevent regression)

### Implementation steps
1) Add verifier to CI as **non-blocking** initially:
   - emits report artifact
2) Once repo is cleaned, switch to **blocking**:
   - fail PR if root violations exceed threshold
3) Provide optional pre-commit hook:
   - warn/fail if committing disallowed root files (logs, phase jsons, etc.)

### Acceptance criteria
- Root clutter doesn’t reaccumulate silently between tidy runs.

---

## 9) Execution order (recommended)

1) E.2 choose `.autonomous_runs/autopack` semantics (otherwise verifier stays noisy/confusing)
2) E.1 expand doc allowlist + align verifier/tidy constants
3) E.3 centralized logging
4) E.4 consolidation idempotency markers
5) E.6 CI + hook enforcement
6) E.5 retrieval quality improvements + smoke checks (ongoing)
