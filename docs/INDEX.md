# Autopack Docs Index (Start Here)

This repo contains **a lot** of documentation. This file is the **navigation hub** (especially for AI agents) so you don’t need to scan a 3K+ line `README.md`.

---

## Source-of-Truth (SOT) docs (authoritative)

These are the canonical references that should stay current and are designed to be machine-consumable:

### Primary SOT Ledgers (Append-Only)
- **`docs/BUILD_HISTORY.md`**: What was built, when, and the completion status (high-signal execution ledger).
- **`docs/DEBUG_LOG.md`**: Failures, debugging sessions, and fixes (root-cause trail).
- **`docs/ARCHITECTURE_DECISIONS.md`**: Design rationale and key decisions (the "why").
- **`docs/CHANGELOG.md`**: Full historical update ledger (moved from README Recent Updates on 2026-01-01).

### Living SOT Docs (Updated as Needed)
- **`docs/DEPLOYMENT.md`**: Production deployment and database configuration (PostgreSQL is production).
- **`docs/PRODUCTION_ROLLOUT_CHECKLIST.md`**: Staged rollout plan + monitoring queries.
- **`docs/MODEL_INTELLIGENCE_SYSTEM.md`**: Model catalog + recommendation system (evidence-based model upgrades).
- **`docs/PROJECT_INDEX.json`**: Machine-friendly index for quick project orientation.
- **`docs/LEARNED_RULES.json`**: Accumulated prevention rules / heuristics.

**Note**: SOT docs are also used by Autopack features like artifact substitution (history pack / SOT doc summaries).

---

## "Read this next" (common paths)

- **Project status & latest updates**: `README.md` (quickstart + current status), `docs/CHANGELOG.md` (full historical ledger)
- **Running Autopack / using the API**: `docs/QUICKSTART.md`, `docs/API_BASICS.md`, `docs/CANONICAL_API_CONTRACT.md`
- **True Autonomy implementation details**: `docs/IMPLEMENTATION_PLAN_TRUE_AUTONOMY.md`, `archive/superseded/reports/unsorted/TRUE_AUTONOMY_COMPLETE_IMPLEMENTATION_REPORT.md`
- **Storage Optimizer**: `archive/superseded/reports/unsorted/STORAGE_OPTIMIZER_MVP_COMPLETION.md`, `docs/STORAGE_OPTIMIZER_INTELLIGENCE_COMPLETE.md`, `docs/STORAGE_OPTIMIZER_AUTOMATION.md`
- **Protection & Retention Policy**: `docs/PROTECTION_AND_RETENTION_POLICY.md` (unified policy for Tidy + Storage Optimizer)
- **Testing**: `docs/TESTING_GUIDE.md`
- **Troubleshooting**: `docs/TROUBLESHOOTING.md`

---

## Tidy system + doc consolidation

- **Tidy scripts overview**: `scripts/tidy/README.md`
- **What tidy does**: consolidates scattered markdown into the SOT ledgers above, and can sync SOT content into:
  - **PostgreSQL** (structured `sot_entries`)
  - **Qdrant** (vector index for semantic retrieval)
- **SOT Memory Integration**: SOT ledgers can be indexed into `MemoryService` for runtime retrieval
  - See `docs/TIDY_SOT_RETRIEVAL_INTEGRATION_PLAN.md` for implementation details
  - See `docs/SOT_MEMORY_INTEGRATION_EXAMPLE.md` for integration examples
- **BUILD-158 Tidy Lock/Lease + Doc Link Checker**:
  - Implementation: `docs/BUILD-158_TIDY_LOCK_LEASE_DOC_LINKS.md`
  - Cross-process safety via filesystem-based lease primitive
  - Automated doc link drift detection for CI
- - **BUILD-145 Tidy Improvements**:
  - Implementation: `docs/BUILD-145-TIDY-SYSTEM-REVISION-COMPLETE.md`
  - Follow-up (Persistent Queue): `docs/BUILD-145-FOLLOWUP-QUEUE-SYSTEM.md`
  - Windows file locks: `docs/TIDY_LOCKED_FILES_HOWTO.md` (4 solution strategies)
  - Windows Task Scheduler: `docs/guides/WINDOWS_TASK_SCHEDULER_TIDY.md` (automation setup)
  - Workspace cleanup: .autonomous_runs/ cleanup, database routing, locked file handling, automatic retry
- **BUILD-157 Smart Retry + Queue Hygiene**:
  - Implementation: `docs/BUILD-157_SMART_RETRY_QUEUE_HYGIENE.md`
  - Per-reason retry policies (locked/permission/dest_exists/unknown)
  - Queue lifecycle with 30-day retention (prevents unbounded growth)
  - New `needs_manual` status for actionable user intervention
- **BUILD-155 CI Drift Enforcement**:
  - CI guardrails for dependency sync (pyproject.toml ↔ requirements.txt)
  - CI guardrails for version consistency (pyproject.toml, PROJECT_INDEX.json, __version__)
  - Scripts: `scripts/check_dependency_sync.py`, `scripts/check_version_consistency.py`
  - Telemetry schema additions: `include_sot`, `sot_chunks_retrieved`, `sot_chars_raw`, etc.

---

## Where to put new docs (to reduce bloat)

- **Authoritative state / decisions / completion journals** → prefer updating the relevant SOT doc:
  - `BUILD_HISTORY.md` (builds completed)
  - `DEBUG_LOG.md` (errors and fixes)
  - `ARCHITECTURE_DECISIONS.md` (design rationale)
  - `CHANGELOG.md` (version updates and feature announcements)
- **Operational how-to** → `docs/guides/` (if a guide category fits) or a focused doc with a clear name
- **One-off reports / deep dives** → `docs/reports/` (if present) or `archive/` if historical-only

If you're unsure: write the doc, then run the tidy workflow to consolidate and keep the SOT ledgers up to date.

---

## SOT Document Types (Understanding the System)

**Append-Only Ledgers** (timestamp-ordered, never delete entries):
- `BUILD_HISTORY.md` - execution ledger
- `DEBUG_LOG.md` - problem-solving trail
- `ARCHITECTURE_DECISIONS.md` - decision rationale
- `CHANGELOG.md` - update announcements

**Living Documents** (edit/update as needed):
- `README.md` - project overview, quickstart, current status
- `DEPLOYMENT.md` - current deployment procedures
- `PRODUCTION_ROLLOUT_CHECKLIST.md` - operational checklists
- Configuration files (`.json`, `.yaml`)

**Tidy System Behavior**:
- README.md is **skipped** by consolidation (has `<!-- SOT_SUMMARY_START/END -->` markers)
- Append-only ledgers are **auto-updated** by `consolidate_docs_v2.py` during Phase 6 cleanup
- Living docs require **manual updates** but can reference ledgers via links


