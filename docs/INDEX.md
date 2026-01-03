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
- **BUILD-170.8 Supply-Chain Hardening - Third-Party Action SHA Pinning**:
  - Eliminated mutable tag attack vector via immutable SHA pinning for all third-party GitHub Actions
  - Pinned 11 third-party action instances to commit SHAs (aquasecurity/trivy-action 2x, github/codeql-action 5x, gitleaks/gitleaks-action 1x, docker/setup-buildx-action 1x, peter-evans/create-pull-request 1x, codecov/codecov-action 1x)
  - Security benefit: Immutable SHAs prevent supply-chain attacks where compromised tags point to malicious code
  - Maintenance: Dependabot already configured for github-actions ecosystem (weekly updates)
  - Fixed codecov-action v5 breaking change (files parameter vs file)
  - See [docs/BUILD_HISTORY.md#build-1708](BUILD_HISTORY.md#build-1708) for details
- **BUILD-170.7 Final SOT Hardening - CI Standardization + Stub Policy Enforcement**:
  - Completed "beyond README ideal state" hardening
  - Standardized ALL CI workflows on GitHub Actions v4 (13 checkout upgrades across 3 files)
  - Added explicit permissions blocks to all 5 workflows (minimal read-only default)
  - Established DEBUG_LOG stub policy (Policy A: stubs are canonical placeholders)
  - Created test_debug_log_stub_policy.py (enforces canonical stub marker)
  - All acceptance criteria met: 5/5 doc tests pass, 0 v3 actions remain, no drift
  - See [docs/BUILD_HISTORY.md#build-1707](BUILD_HISTORY.md#build-1707) for details
- **BUILD-170.6 SOT Ideal State Polish - Recent Window Enforcement + Actions Upgrade**:
  - DEBUG_LOG recent window enforcement (top 50 INDEX rows strict, historical loose)
  - Added 30 missing DEBUG_LOG stub sections (DBG-084 through DBG-050)
  - Upgraded doc-link-deep-scan.yml to actions v4 + permissions hardening
  - See [docs/BUILD_HISTORY.md#build-1706](BUILD_HISTORY.md#build-1706) for details
- **BUILD-170.5 SOT Ideal State - Workflow Consolidation + DEBUG_LOG Contract Test**:
  - Closed last "two truths" gaps: workflow deduplication + DEBUG_LOG validation
  - Deleted .github/workflows/doc-link-check.yml (fully redundant)
  - Kept doc-link-deep-scan.yml as ONLY scheduled deep scan (Monday weekly)
  - Created test_debug_log_index_matches_sections.py (DEBUG_LOG contract test)
  - All acceptance criteria met: 4/4 doc tests pass, no drift, zero duplication
  - See [docs/BUILD_HISTORY.md#build-1705](BUILD_HISTORY.md#build-1705) for details
- **BUILD-170 SOT Ledgers as Canonical Truth - CI Enforcement**:
  - Established SOT ledgers as single source of truth with automated drift detection
  - Added --check mode to sot_summary_refresh.py (exit 0 clean, exit 1 drift)
  - Created doc format contract tests (README summary validation, INDEX sync, DEC-### uniqueness)
  - Added docs-sot-integrity CI job (blocks PRs on drift)
  - Created weekly deep doc link scan workflow (report-only, 90-day retention)
  - Removed competing generators from db_sync.py (eliminated "two truths")
  - See [docs/BUILD_HISTORY.md#build-170](BUILD_HISTORY.md#build-170) for details
- **BUILD-169 Targeted Doc Link Fixes - 12% Reduction (Focus Docs 100% Clean)**:
  - 11.9% reduction: 478 → 421 missing_file (57 resolved)
  - Focus docs cleaned: CHANGELOG.md (27→0) + PRE_TIDY_GAP_ANALYSIS (30→0) = 100%
  - High fix ratio: 82% real fixes (47) vs 18% scoped ignores (10)
  - Infrastructure hardening: Windows UTF-8 safety, path normalization fixes
  - Regression protection: Added test_fenced_code_blocks_bypass_deep_scan()
  - See [docs/BUILD_HISTORY.md#build-169](BUILD_HISTORY.md#build-169) for details
- **BUILD-168 Doc Link Burndown - 20% Missing File Reduction**:
  - 20.6% reduction: 746 → 592 missing_file (154 resolved)
  - 60+ triage rules + 300 file+target specific ignores
  - Fixed scripts/check_doc_links.py to use ignore_patterns (fundamental mismatch)
  - See [docs/BUILD_HISTORY.md#build-168](BUILD_HISTORY.md#build-168) for details
- **BUILD-167 Doc Link Burndown + High-ROI Improvements**:
  - Implementation: [docs/BUILD-167_COMPLETION_REPORT.md](BUILD-167_COMPLETION_REPORT.md)
  - Exit code standards: [docs/EXIT_CODE_STANDARDS.md](EXIT_CODE_STANDARDS.md)
  - 27 triage rules + 4 redirect stubs + backtick heuristics extraction
  - Zero regression (746 baseline maintained)
  - Acceptance criteria for future doc hygiene builds
- **BUILD-163 Standalone SOT → DB/Qdrant Sync**:
  - Implementation: [docs/BUILD-163_SOT_DB_SYNC.md](BUILD-163_SOT_DB_SYNC.md)
  - Standalone sync tool decoupled from full tidy runs (30-50x faster)
  - Four mutually exclusive modes: docs-only, db-only, qdrant-only, full
  - Bounded execution with explicit write control (--execute flag required)
  - Idempotent upserts with content hash-based change detection
  - Result: SOT→DB sync in < 5s without 5-10 min full tidy
- **BUILD-159 Deep Doc Link Checker + Mechanical Fixer**:
  - Implementation: [docs/BUILD-159_DEEP_DOC_LINK_CHECKER_MECHANICAL_FIXER.md](BUILD-159_DEEP_DOC_LINK_CHECKER_MECHANICAL_FIXER.md)
  - Layered heuristic matching for broken link suggestions
  - Mechanical fixer with confidence-based auto-apply
  - Result: 31% broken link reduction (58 → 40), INDEX.md now 100% clean
- **BUILD-158 Tidy Lock/Lease + Doc Link Checker**:
  - Implementation: [docs/BUILD-158_TIDY_LOCK_LEASE_DOC_LINKS.md](BUILD-158_TIDY_LOCK_LEASE_DOC_LINKS.md)
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


