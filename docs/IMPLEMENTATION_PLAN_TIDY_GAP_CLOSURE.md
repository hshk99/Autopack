# Implementation Plan: Close the Gap on “Autopack Tidy Up” (README Intent → Reality)

Audience: maintainers + next implementation cursor  
Goal: make “tidy up” behavior match the **intention described in `README.md`**, especially for keeping `C:\dev\Autopack\` and `C:\dev\Autopack\docs\` clean and preventing surprise directory creation.

---

## 1) What the README says the intention is (ground truth)

The README is explicit that **tidy is not “just cleaning up docs”**; it exists to make project knowledge reusable by humans and models via a **standard SOT** and by pushing historical clutter into archives.

Key intent statements (quotes are from `README.md`):

- **Standardized 6-file SOT** (per project):

```91:170:README.md
### Multi-Project Documentation & Tidy System (2025-12-13)

**Standardized 6-File SOT Structure**:
All projects follow a consistent documentation structure for AI navigation:
1. **PROJECT_INDEX.json** - Quick reference (setup, API, structure)
2. **BUILD_HISTORY.md** - Implementation history (auto-updated)
3. **DEBUG_LOG.md** - Troubleshooting log (auto-updated)
4. **ARCHITECTURE_DECISIONS.md** - Design decisions (auto-updated)
5. **FUTURE_PLAN.md** - Roadmap and backlog (manual)
6. **LEARNED_RULES.json** - Auto-updated learned rules (auto-updated)

**Intention (critical)**:
The tidy + SOT system is not just for “cleaning up docs”. Its purpose is to ensure that:
- Autopack and Cursor can **retrieve relevant project knowledge when needed** (not re-read entire archives).
- The authoritative ledgers remain **machine-usable** (stable structure, low drift).
- The system supports both:
  - **Linear reuse** (explicit links, SOT doc substitution/history pack for token efficiency)
  - **Semantic reuse** (vector memory retrieval when enabled)
```

- **File organization rules**:
  - SOT lives in `docs/`, historical artifacts in `archive/` buckets.

```166:171:README.md
**File Organization**:
- ✅ **SOT files** (6 files) go in `<project>/docs/`
- ✅ **Runtime cache** (phase plans, issue backlogs) go in `.autonomous_runs/`
- ✅ **Historical files** go in `<project>/archive/` (organized by type: plans/, reports/, research/, etc.)
```

- **Root-created clutter should be routed away** (Cursor creates files at repo root; tidy routes them into the right buckets, keeping “truth sources” in `docs/`):

```716:766:README.md
Cursor creates files in the workspace root. The tidy system **automatically detects and routes** files based on project and type:
...
3. **Routes to destination**:
  - **Autopack files**: `C:\dev\Autopack\{archive or scripts}\{bucket}\{file}`
...
4. **Truth Sources** (never moved):
  - Autopack: `C:\dev\Autopack\docs\`
```

### Practical interpretation of the README intent

- **The docs root should be “truth sources”, not an inbox**.
- **Archive is the inbox + history** (organized into buckets).
- **Tidy should prevent drift** (so you don’t reaccumulate mess between runs).

---

## 2) Why `C:\dev\Autopack\` and `C:\dev\Autopack\docs\` are still messy today

### A) The “tidy” entrypoint most people run doesn’t target repo root or `docs/`

`scripts/tidy/run_tidy_all.py` defaults to tidying only:
- `.autonomous_runs/file-organizer-app-v1`
- `.autonomous_runs`
- `archive`

It does **not** include `.` (repo root) nor `docs/` by default, which means:
- stray root files won’t be routed
- `docs/` clutter won’t be reduced

This directly matches your observation: “tidy ran, but root/docs remain messy.”

### B) There are multiple overlapping tidy/cleanup systems with conflicting or stale assumptions

Examples of drift:
- Several scripts and docs refer to `docs/WORKSPACE_ORGANIZATION_SPEC.md`, but that file is currently missing in the repo (yet referenced as a “truth anchor” by `scripts/tidy/tidy_workspace.py`).
- Different scripts target different purposes:
  - `autonomous_tidy.py`: “audit + consolidate + verify”
  - `tidy_workspace.py`: incremental routing/moves + optional semantic actions
  - `corrective_cleanup_v2.py`: heavy refactor / structural moves
  - `consolidate_docs_v2.py`: “archive → SOT ledgers” content consolidation

Without a single authoritative “tidy up” command and without a validator that enforces “docs is not an inbox”, drift is inevitable.

### C) Why subdirectories appear under `docs/`

There are **two legitimate reasons** you may see new `docs/*` subdirectories:
- Some tidy/cleanup scripts create canonical subpaths such as `docs/api/` (e.g., moving `openapi.json` under it).
- Some project-specific organization rules intentionally place docs into structured subtrees (e.g., `docs/research/` for certain projects).

However, if your intended end-state is “docs is clean and mostly flat; non-truth docs go to archive”, then the current behavior needs a **hard allowlist** and a **docs reduction step** (see plan below).

---

## 3) The gap to close (what’s missing vs README)

From the README’s intent, “tidy up” must do **all** of the following:

- **Root hygiene**: route stray “Cursor-created” files out of repo root into `archive/` buckets (or `scripts/` for scripts).
- **Docs hygiene**: ensure `docs/` contains only:
  - the 6-file SOT set (plus an allowlist of true “truth-source guides” if desired), and
  - optionally a small number of structured subdirectories that are explicitly allowed.
- **Archive consolidation**: consolidate archive markdown into the SOT ledgers and then mark processed content as superseded (so it doesn’t get reprocessed).
- **Determinism + idempotency**: repeated runs should not keep moving/recreating things.
- **Single entrypoint**: the command users run should actually perform the above.

---

## 4) Proposed implementation plan (phased, safe, testable)

### Phase 0 — Re-establish the canonical spec (stop “missing spec” drift)

- **Create/restore** `docs/WORKSPACE_ORGANIZATION_SPEC.md` as the canonical, current organization policy.
  - Source material exists in the repo’s SOT ledgers (e.g., in `docs/BUILD_HISTORY.md` referencing the spec).
  - The restored spec must explicitly define:
    - what belongs at repo root
    - what belongs in `docs/` (truth sources)
    - what belongs in `archive/` (history/inbox)
    - whether `docs/` subdirectories are allowed, and if so, which ones
- **Update references** that currently point to a non-existent file:
  - `scripts/tidy/tidy_workspace.py` default truth anchors
  - `scripts/tidy/README.md`
  - `docs/PROJECT_INDEX.json` (it already suggests the spec “moved”; reconcile this)

Deliverables:
- `docs/WORKSPACE_ORGANIZATION_SPEC.md` (authoritative)
- A short “spec version” header + date so future drift is detectable

---

### Phase 1 — Unify “tidy up” into a single command that matches README expectations

Add a single top-level entrypoint (pick one):
- **Option A (preferred)**: `python scripts/tidy/tidy_up.py`
- **Option B**: extend `scripts/tidy/run_tidy_all.py` to include repo root + docs and rename it in docs/README so users run the right thing.

This entrypoint should orchestrate:
- **Step 1: root routing** (stray files in repo root → `archive/*` or `scripts/*`)
- **Step 2: docs hygiene** (see Phase 2)
- **Step 3: archive consolidation** (archive → SOT ledgers; mark processed as superseded)
- **Step 4: .autonomous_runs cleanup** (if enabled)
- **Step 5: verification** (assert structure matches spec; fail with a clear report)
- **Step 6: (optional) SOT re-index handoff** (see Phase 1.5)

Required flags:
- default: `--dry-run`
- `--execute` to apply
- `--checkpoint` (zip before changes) and optional `--git-checkpoint` (pre/post commits)
- `--project` / `--scope` to restrict to `autopack` vs subproject

---

### Phase 1.5 — Align with the *reuse* pipeline (tidy → SOT → MemoryService → retrieval)

This is the part that makes the README’s statement materially true end-to-end:
**“tidy backlog → SOT ledgers → semantic indexing → Autopack uses it when it needs it”**.

Current runtime reality (already implemented on `main`):
- Autopack can **index SOT** (6 files) into vector memory (opt-in).
- Autopack can **retrieve SOT** during `retrieve_context()` via `include_sot` gated by `AUTOPACK_SOT_RETRIEVAL_ENABLED` (opt-in).

Gap to close for “tidy up”:
- “tidy up” runs out-of-band from the executor, so after it moves/consolidates docs, **the SOT index may be stale** until the next startup indexing run (and depending on config, indexing may be disabled).

Implementation requirements:
- **Do not break SOT paths**: the 6 canonical SOT files must remain in `<project>/docs/` with stable names because indexing and retrieval expect those paths.
- **Stable chunk IDs**: tidy/consolidation should preserve line endings normalization and avoid unnecessary churn (so “skip existing chunks” works and re-index cost doesn’t explode).

Two acceptable designs (pick one):
- **Design A (recommended): dirty-flag + fast no-op**
  - After “tidy up” writes/modifies any of the 6 SOT files, write a small marker:
    - repo-root project: `C:\dev\Autopack\.autonomous_runs\sot_index_dirty_autopack.json`
    - sub-project: `.autonomous_runs/<project>/.autonomous_runs/sot_index_dirty.json` (or another consistent location under the project root)
  - Executor startup indexing checks:
    - if marker absent → fast no-op
    - if marker present → run `index_sot_docs(...)` then clear marker on success
  - This keeps indexing opt-in and avoids re-embedding work when nothing changed.

- **Design B: “tidy up” optionally triggers re-index**
  - Add `--reindex-sot` to the unified tidy command.
  - When enabled and memory is configured/available, call `MemoryService.index_sot_docs(project_id, workspace_root, docs_dir=resolved_docs_dir)`.
  - Still keep bounded + non-fatal: log warnings and continue if store unavailable.

Verification:
- Add an integration-ish test asserting:
  - tidy modifies SOT → dirty flag created
  - executor startup indexing sees dirty flag and indexes once (then clears)
  - `retrieve_context(... include_sot=True)` returns the “Relevant Documentation (SOT)” section when enabled

---

### Phase 2 — Implement “docs hygiene” (this is the missing piece for your complaint)

Design: `docs/` should not be an inbox. We need **two explicit modes**:

- **Mode 1: conservative (default)**  
  - Do not move anything under `docs/` automatically except clearly non-truth artifacts (e.g., `UNSORTED_REVIEW.md` is allowed, but random `ref*.md` is not).
  - Enforce “no new docs subdirs” by denylisting unknown directories.

- **Mode 2: reduce docs (explicit opt-in)** (`--docs-reduce-to-sot`)  
  - Move *everything* in `docs/` that is not in an allowlist into `archive/reports/docs_superseded/` (or `archive/superseded/reports/docs/`).
  - Optionally leave behind a small stub file (redirect) pointing to the new archive location (only if helpful).

Concrete rules (initial allowlist proposal, adjust to taste):
- Always allow in `docs/`:
  - `PROJECT_INDEX.json`
  - `BUILD_HISTORY.md`
  - `DEBUG_LOG.md`
  - `ARCHITECTURE_DECISIONS.md`
  - `FUTURE_PLAN.md`
  - `LEARNED_RULES.json`
  - `INDEX.md` (nav hub)
- Allow `docs/` subdirectories only if explicitly listed in the spec (example: `docs/guides/`, `docs/cursor/`, `docs/examples/`, `docs/cli/`, `docs/api/`). Anything else becomes a **candidate for archive**.

Important: docs hygiene must remain compatible with reuse:
- If `docs/` cleanup moves non-SOT docs out of `docs/`, ensure their information is still reachable by:
  - consolidation into the SOT ledgers where appropriate, and/or
  - archival into `archive/` buckets (human reference), without breaking the 6-file SOT set.

Classification for “docs clutter” moves (when reduction mode is enabled):
- `BUILD-*.md`, `DBG-*.md`, `DEC-*.md`, `*_SUMMARY*.md`, `*_REPORT*.md` → `archive/reports/`
- `*_PROMPT*.md`, `*_DELEGATION*.md` → `archive/prompts/`
- `*_DIAGNOSTIC*.md` or logs → `archive/diagnostics/`
- unknown → `archive/unsorted/`

---

### Phase 3 — Stop surprise directory creation (hard guardrails)

Add a validation layer (run in dry-run and execute):
- **Allowed directory set** for `docs/` (from spec).
- If tidy attempts to create a new `docs/<x>/` not in allowlist:
  - block the operation (in `--execute`)
  - emit a clear error with the exact path and the rule that triggered

Also add a “path construction” validator for moves (similar to the existing nesting checks in `tidy_workspace.py`), but applied globally and enforced strictly.

---

### Phase 4 — Make it hard to regress: tests + a structural verifier

Add automated tests around the new behavior:
- **Unit tests** for:
  - docs allowlist logic (`--docs-reduce-to-sot`)
  - routing of root-created files
  - “no new docs subdirs” enforcement
  - idempotency (run twice → no changes second time)
- **Integration-style test** using a temp fixture workspace with:
  - stray root files (md/log/json)
  - a “messy docs” set (extra md files, unknown subdirs)
  - expected outputs under `archive/`

Add a standalone verifier:
- `python scripts/tidy/verify_workspace_structure.py`
  - checks repo root allowed files
  - checks `docs/` allowlist + allowed subdirs
  - checks `archive/` has required buckets
  - outputs a machine-readable report (JSON) + short markdown summary

Optional (recommended): wire verifier into CI as a non-blocking job at first, then promote to blocking once clean.

---

## 5) Recommended immediate next steps (to unblock you fastest)

1) Implement Phase 0 + Phase 1 entrypoint unification (so “tidy up” means one thing).  
2) Implement Phase 2 docs hygiene in **opt-in reduction mode**, so you can clean `docs/` safely without surprising moves.  
3) Add Phase 4 verifier + tests so it doesn’t drift again.

---

## 6) Notes / constraints

- Must remain **dry-run by default**.
- Must remain **reversible** (checkpoint zip + git checkpoint).
- Must never delete protected truth sources; deletions must remain **opt-in**.
- Must work on Windows paths and avoid runaway nesting.


