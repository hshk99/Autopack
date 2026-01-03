# Autopack Framework

**Autonomous AI Code Generation Framework**

Autopack is a framework for orchestrating autonomous AI agents (Builder and Auditor) to plan, build, and verify software projects. It uses a structured approach with phased execution, quality gates, and self-healing capabilities.

---

## Docs Navigation (recommended "start here")

This repo's documentation is intentionally extensive. For the fastest orientation (especially for AI agents), start with:

- `docs/INDEX.md` (navigation hub)
- `docs/BUILD_HISTORY.md` (what was built + completion ledger)
- `docs/DEBUG_LOG.md` (failures + fixes)
- `docs/ARCHITECTURE_DECISIONS.md` (design rationale)
- `docs/MODEL_INTELLIGENCE_SYSTEM.md` (model catalog & recommendation system)

`README.md` includes a long "Recent Updates" history and can exceed 3,000 lines; the index above is the intended entry point for efficient context loading.

## North Star: “True Autonomy” (Project Intention → Build Completion)

Autopack’s long-term objective is **fully autonomous building with minimal human intervention**, while remaining safe and cost-effective.

This means Autopack should be able to:

- **Handle any project / any plan input**
  - Works even when the input “plan” is unstructured (notes, messy requirements, partial thoughts).
  - Autopack must **normalize unstructured intent into a safe, structured execution plan** (deliverables, scope, tests/build, budgets).

- **Retain and apply “Project Intention Memory” end-to-end (semantic)**
  - Autopack should store a compact “intention anchor” + supporting planning artifacts in vector memory (semantic embeddings).
  - That intention should be retrieved and applied consistently across the lifecycle:
    - plan normalization → manifest/scope generation → context budgeting → build/apply → auditing → failure recovery → completion.
  - Prevents “goal drift” and improves plan normalization quality for ambiguous projects.

- **Be universal across languages/toolchains (pluggable)**
  - Toolchain detection, install/build/test commands, and repo conventions should be **extensible and composable**.
  - Truly arbitrary or unsafe plans can still be rejected or require human approval (safety is mandatory).

- **Harden against real failure modes (self-improving loop)**
  - Use telemetry + artifacts to identify top failure signatures and add deterministic mitigations.
  - Prefer deterministic fixes over extra LLM calls; keep token usage low.

- **Parallel execution in the most efficient state (safe + isolated)**
  - Concurrent runs must be isolated (git worktrees) and protected (locks/leases), with a production-grade orchestrator.
  - Parallelism is not just “threads”: it’s safe isolation + bounded concurrency + predictable throughput.

In practice, “autonomous” requires that each phase has:
- **Good deliverables**: explicit file outputs / behaviors expected
- **A safe scope**: allowed paths and read-only context defined
- **Runnable build/tests**: at least one validation command or quality gate
- **A supported toolchain**: detected and configured deterministically where possible

## Recent Updates

**For the complete historical update ledger, see [docs/CHANGELOG.md](docs/CHANGELOG.md)** (moved from README on 2026-01-01 to improve AI navigation efficiency).

### Latest Highlights (Last 3 Builds)

#### 2026-01-03: BUILD-169 - Targeted Doc Link Fixes: 12% Reduction (Focus Docs 100% Clean) ✅
**High-Signal Fixes Over Ignores**
- 11.9% reduction: 478 → 421 missing_file issues (57 resolved via 47 real fixes + 10 scoped ignores)
- Focus docs cleaned: CHANGELOG.md (27→0) + PRE_TIDY_GAP_ANALYSIS (30→0) = 100% reduction
- Infrastructure hardening: Windows UTF-8 safety, path normalization fixes (.github/ preserved), nav-mode restored
- Regression guard: Added test_fenced_code_blocks_bypass_deep_scan() to prevent parser changes re-inflating counts
- Fix ratio: 82% real fixes (canonical paths, fenced blocks, config links) vs 18% scoped ignores
- See [docs/BUILD_HISTORY.md](docs/BUILD_HISTORY.md) BUILD-169 entry for details

#### 2026-01-03: BUILD-168 - Doc Link Burndown: 20% Missing File Reduction ✅
**Material Reduction via Triage Rules + Check Script Patch**
- 20.6% reduction achieved: 746 → 592 missing_file issues (154 resolved, exceeded 10% target by 2x)
- Nav-mode pristine: 0 missing_file maintained (README, INDEX, BUILD_HISTORY)
- Fixed tool mismatch: Patched check_doc_links.py to use ignore_patterns from triage tool
- 60+ triage rules added: Historical BUILD-129 docs, temp files, runtime dirs, API endpoints
- Established workflow: Repeatable triage process for future burndown phases
- See [docs/BUILD_HISTORY.md](docs/BUILD_HISTORY.md) BUILD-168 entry for details

#### 2026-01-03: BUILD-167 - Doc Link Burndown + High-ROI Improvements ✅
**Exit Code Standards, Redirect Stubs, Acceptance Criteria**
- Exit code standards documented: CI integration behavior for check_doc_links.py + sot_db_sync.py
- 27 triage rules added: Historical code paths + file extensions properly classified
- 4 redirect stubs created: SOT_BUNDLE.md, CONSOLIDATED_DEBUG.md (with validation tests)
- Zero regression: 746 baseline maintained after post-review corrections
- See [docs/BUILD-167_COMPLETION_REPORT.md](docs/BUILD-167_COMPLETION_REPORT.md)

#### 2026-01-03: BUILD-163 - Standalone SOT → DB/Qdrant Sync ✅
**Bounded, Mode-Selective Sync from Canonical SOT Ledgers**
- Standalone sync tool: Decoupled from full tidy runs, four mutually exclusive modes (--docs-only/--db-only/--qdrant-only/--full)
- Explicit write control: Requires --execute flag for DB/Qdrant writes (no-surprises safety), default --docs-only mode never writes
- Bounded execution: --max-seconds timeout (default 120s), per-operation timing output, total execution < 5s for db-only mode
- Idempotent upserts: Stable entry IDs (BUILD-###/DEC-###/DBG-###), content hash change detection, PostgreSQL/SQLite dual support
- **Result**: SOT→DB sync runnable without 5-10 min full tidy, scheduled sync possible, 173 entries parsed in <1s, zero duplicates
- See [scripts/tidy/sot_db_sync.py](scripts/tidy/sot_db_sync.py) for implementation

#### 2026-01-03: BUILD-161 - Lock Status UX + Safe Stale Lock Breaking ✅
**Operator-Friendly Lock Diagnostics**
- Lock status diagnostics: Cross-platform PID detection (tristate True/False/None), comprehensive status output with visual indicators (✅/⚠️/❌/🔒)
- Safe lock breaking: Conservative policy (expired + PID not running), --force flag for edge cases (malformed/unknown PID)
- CLI integration: `--lock-status` (diagnostics), `--break-stale-lock` (safe breaking), `--lock-name`, `--lock-grace-seconds`, `--force`
- **Result**: Zero manual lock deletion needed, operator-friendly diagnostics, prevents accidental breaking of valid locks, 20/20 tests passing
- See commit [c44bd276](https://github.com/hshk99/Autopack/commit/c44bd276) for full implementation

#### 2026-01-03: BUILD-159 - Deep Doc Link Checker + Mechanical Fixer ✅
**Automated Link Repair with Layered Matching**
- Enhanced checker: Deep mode (scan all docs/), layered heuristic matching (3-step algorithm), confidence scoring (high/medium/low)
- Mechanical fixer: Confidence-based auto-apply (high ≥0.90 default), atomic backup, dry-run mode, regex-safe path handling
- Fix plan export: JSON + Markdown formats with actionable suggestions
- **Result**: 31% broken link reduction (58 → 40), docs/INDEX.md now 100% clean, 20 mechanical fixes applied
- See [docs/BUILD-159_DEEP_DOC_LINK_CHECKER_MECHANICAL_FIXER.md](docs/BUILD-159_DEEP_DOC_LINK_CHECKER_MECHANICAL_FIXER.md) for full details

#### 2026-01-03: BUILD-158 - Tidy Lock/Lease + Doc Link Checker ✅
**Cross-Process Safety + Documentation Hygiene**
- Lease primitive: Atomic acquisition, TTL-based expiry, heartbeat renewal, stale lock auto-breaking
- Tidy integration: Lease acquired even for dry-run, released in finally block, heartbeat at phase boundaries
- Atomic write helper: Unified temp+replace pattern with retry tolerance (antivirus/indexing locks)
- Doc link checker: Validates file references in README.md + docs/INDEX.md + docs/BUILD_HISTORY.md
- **Result**: Safe concurrent tidy runs, crashed process recovery, 16/16 tests passing, 43 broken links detected
- See [docs/BUILD-158_TIDY_LOCK_LEASE_DOC_LINKS.md](docs/BUILD-158_TIDY_LOCK_LEASE_DOC_LINKS.md) for full details

#### 2026-01-03: BUILD-156 - Queue Improvements & First-Run Ergonomics ✅
**Actionable Queue Reporting + Reason Taxonomy + Resource Caps + UX Shortcuts**
- P0: Queue actionable reporting (top N items by priority, suggested next actions, JSON/Markdown reports)
- P1: Reason taxonomy (locked/permission/dest_exists/unknown) enables smart retry logic
- P1: Queue caps/guardrails (max 1000 items, 10 GB total) prevent unbounded growth
- P1: Verification --strict flag for CI enforcement (treat warnings as errors)
- P2: --first-run flag as one-command bootstrap (execute + repair + docs-reduce-to-sot)
- **Result**: Users get concrete next actions instead of "figure it out yourself"
- See [archive/diagnostics/BUILD-156_QUEUE_IMPROVEMENTS_SUMMARY.md](archive/superseded/diagnostics/BUILD-156_QUEUE_IMPROVEMENTS_SUMMARY.md) for full details

#### 2026-01-03: BUILD-155 - Tidy First-Run Resilience (P0-P1 Complete) ✅
**Tidy Always Succeeds: Profiling + Locked-File Resilience**
- Phase 0.5 profiling infrastructure (per-step timing, optional memory tracking)
- Optimized empty-directory deletion (streaming bottom-up, memory-bounded, 1-3s completion)
- Dry-run non-mutation guarantee (strict read-only, queue hash unchanged)
- Queued-items-as-warnings verification (exit code 0 with locked files, first-run success)
- **Result**: "Tidy always succeeds" README promise now delivered
- See [docs/BUILD_155_SOT_TELEMETRY_COMPLETION.md](docs/BUILD_155_SOT_TELEMETRY_COMPLETION.md) for full details

#### 2026-01-02: BUILD-153 - Storage Optimizer Automation & Production Hardening ✅
**Production-Ready Automation: Weekly Scans + Delta Reporting + Unified Protection Policy**
- **Task Scheduler automation**: Weekly scans via Windows Task Scheduler/cron with delta reporting (what changed since last scan)
- **Delta reporting**: New/removed cleanup opportunities, per-category breakdown, size change tracking, JSON + text reports
- **Telegram notifications**: Optional mobile alerts with scan summary, delta statistics, review links
- **Protection policy unification**: Shared Tidy + Storage Optimizer policy (single source of truth, no policy drift)
- **Canary test**: 60 files deleted successfully (100% success rate, 8 seconds, 0 failures, full audit trail)
- **Test pack**: 26 unit tests (100% passing) - lock detector, checkpoint logger, executor retry logic
- **Safety features**: Scan-only automation (no auto-deletion), Recycle Bin safety, category execution caps, lock-aware retry
- See [docs/BUILD-153_COMPLETION_SUMMARY.md](docs/BUILD-153_COMPLETION_SUMMARY.md) for full details

#### 2026-01-02: BUILD-151 Phase 4 - Storage Optimizer Intelligence Features ✅
**Intelligence System: Pattern Learning, Smart Categorization & Strategic Recommendations**
- Implemented Approval Pattern Analyzer: learns cleanup rules from user approval history (100% confidence patterns detected)
- Smart Categorizer: LLM-powered edge case handling (~9K tokens per 100 unknowns, GLM-first fallback)
- Recommendation Engine: trend analysis, growth alerts, recurring waste detection (10 strategic insights generated)
- Steam Game Detector: manual-trigger analysis for large uninstalled games
- All 3 intelligence components working: 44 approvals → 4 learned patterns → 10 recommendations ✅
- **Database Fixes**: SQLite auto-increment compatibility, session handling, temp file categorization
- Production-ready: zero-token pattern learning, minimal-token categorization, PostgreSQL + SQLite support

#### 2026-01-01: BUILD-147 Phase A P11 - SOT Runtime + Model Intelligence Integration ✅
**Memory Integration: SOT Runtime Observability & Validation Hardening**
- Validated complete SOT runtime integration (all 8 parts from IMPROVEMENTS_PLAN already implemented)
- Fixed test infrastructure: consistent `retrieve_context` return structure + singleton settings reload
- All 26 SOT memory indexing tests passing ✅
- Production-ready: opt-in design (disabled by default), bounded outputs, multi-project support
- See [BUILD_HISTORY.md](docs/BUILD_HISTORY.md#build-147-phase-a-p11) and [docs/IMPROVEMENTS_PLAN_SOT_RUNTIME_AND_MODEL_INTEL.md](docs/IMPROVEMENTS_PLAN_SOT_RUNTIME_AND_MODEL_INTEL.md) for full details

#### 2026-01-01: BUILD-146 Phase A P17.x - DB Idempotency Hardening ✅
**Production Polish: Operator Guidance + Optional Postgres Validation**
- Enhanced smoke test with database context hints (PostgreSQL vs SQLite clarity)
- Rollout checklist explicit index verification step (Stage 0 pre-production validation)
- Optional Postgres integration test validates real DB enforcement (4 tests, opt-in by default)
- See [BUILD_HISTORY.md](docs/BUILD_HISTORY.md#build-146-phase-a-p17x) for full details

#### 2025-12-31: BUILD-146 Phase A P16+ - Windows/Test Hardening ✅
**Production Reliability: UTF-8 + In-Memory DB Safety**
- Windows UTF-8 encoding safety in calibration tests
- In-memory SQLite default for test isolation (prevents accidental Postgres dependency)
- See [BUILD_HISTORY.md](docs/BUILD_HISTORY.md#build-146-phase-a-p16) for full details

**Prior updates**: See [docs/CHANGELOG.md](docs/CHANGELOG.md) for the complete version history from v0.4.6 through BUILD-145.

---
## Repository Structure (Autopack + Projects)
- Autopack core lives at the repo root and includes executor, diagnostics, dashboard, and tooling.
- Project artifacts live under `.autonomous_runs/<project>/` (plans, diagnostics, consolidated logs); e.g., `file-organizer-app-v1` is the first project built with Autopack.
- Additional projects stay under `.autonomous_runs/<project>/` within this repo (not separate repos).
- Use branches per project/maintenance effort when applying automated fixes to keep histories clean; checkpoints are recommended for maintenance/apply flows.

### Multi-Project Documentation & Tidy System

**Standardized 6-File SOT Structure**:
All projects follow a consistent documentation structure for AI navigation:
1. **PROJECT_INDEX.json** - Quick reference (setup, API, structure)
2. **BUILD_HISTORY.md** - Implementation history (auto-updated)
3. **DEBUG_LOG.md** - Troubleshooting log (auto-updated)
4. **ARCHITECTURE_DECISIONS.md** - Design decisions (auto-updated)
5. **FUTURE_PLAN.md** - Roadmap and backlog (manual)
6. **LEARNED_RULES.json** - Auto-updated learned rules (auto-updated)

**Intention (CRITICAL for AI agents)**:
The tidy + SOT system exists to ensure **Autopack remains maintainable and self-improving**:
- **Workspace Organization**: Root stays clean, archives are organized, `.autonomous_runs/` cleanup is automatic
- **Knowledge Retrieval**: Autopack/Cursor can retrieve relevant project knowledge without re-reading entire archives
- **Machine-Usable Ledgers**: SOT docs have stable structure with low drift
- **Dual Retrieval**: Supports both linear reuse (explicit links, history packs) and semantic reuse (vector memory)

**`.autonomous_runs/` & Run Archival Policy** (CRITICAL):

**`.autonomous_runs/` should ONLY contain**:
1. **Runtime Workspaces**: System directories (_shared, baselines, checkpoints, .locks, batch_drain_sessions, tidy_checkpoints, autopack)
2. **Project Workspaces**: Individual projects with SOT structure (file-organizer-app-v1/, storage-optimizer/, etc.)

**Old run directories are ARCHIVED, NOT kept in `.autonomous_runs/`**:
- **Autopack runs** → `C:\dev\Autopack\archive\runs\` (build*, autopack-*, diagnostics-*, research-*, retry-*, lovable-*, telemetry-*, p10-*, etc.)
- **Project runs** → `C:\dev\Autopack\.autonomous_runs\<project>\archive\runs\`
- **Tidy behavior**: Keeps last 10 runs per prefix at `.autonomous_runs/` root, moves older runs to respective `archive/runs/` directories
- **Active runs** may temporarily exist at `.autonomous_runs/<run-id>/` but should be archived when complete

**Correct Structure**:
```
C:\dev\Autopack\
  archive\
    runs\                           # OLD Autopack run directories (archived by tidy)
      build112-completion\
      build126-e2-through-i\
      autopack-diagnostics-parity-v3\
      ...
  .autonomous_runs\
    _shared\                        # Runtime workspace
    baselines\                      # Runtime workspace
    checkpoints\                    # Runtime workspace
    autopack\                       # Autopack runtime workspace (active runs ONLY)
    build145-structure-fix\         # ACTIVE Autopack run (will be archived when old)
    file-organizer-app-v1\         # Project workspace
      docs\, src\
      archive\
        runs\                       # OLD file-organizer runs (archived by tidy)
    storage-optimizer\             # Project workspace
      docs\, src\
      archive\
        runs\                       # OLD storage-optimizer runs (archived by tidy)
```

**Current State & Gaps (BUILD-154, 2026-01-02)**:
✅ **Implemented**:
- Workspace tidy system (`scripts/tidy/tidy_up.py`) handles root cleanup, database archival, directory routing
- `.autonomous_runs/` cleanup removes orphaned files (logs, JSON), old run directories (keeps last 10/prefix), empty dirs
- Project migration (e.g., `fileorganizer/` → `.autonomous_runs/file-organizer-app-v1/`)
- SOT consolidation from archive backlog → SOT ledgers
- File lock handling (skips locked databases, continues cleanup)
- Documentation drift fixes: version alignment (0.5.1), dependency reconciliation (BUILD-154)
- Dependency management strategy: `pyproject.toml` as canonical source (BUILD-154)

⚠️ **Known Gaps** (to address in future builds):
1. **Incomplete .autonomous_runs cleanup on first execution**:
   - Orphaned files: ✅ Fixed (45 files archived successfully)
   - Old run directories: ⚠️ Partial (21 dirs detected but may fail if database locks block Phase 1)
   - **Root Cause**: Phase 1 database routing fails on locked files → Phase 2.5 cleanup never runs
   - **Fix Needed**: Reorder phases OR run Phase 2.5 before Phase 1 OR make Phase 1 continue on errors

2. **Database file locks block cleanup**:
   - ✅ RESOLVED (BUILD-145 Follow-up): Persistent queue system with automatic retry
   - Locked files are queued in `.autonomous_runs/tidy_pending_moves.json` and retried on next tidy run
   - See "Windows File Locks & Automatic Retry" section below for details

3. **SOT → Semantic Indexing (runtime) hardening**:
   - ✅ SOT indexing + retrieval is implemented (opt-in) via `MemoryService.index_sot_docs()` and `retrieve_context(..., include_sot=True)`
   - ⚠️ Remaining work: strengthen budget-aware gating + add telemetry so SOT context can never bloat prompts silently
   - See `docs/SOT_MEMORY_INTEGRATION_EXAMPLE.md` and `docs/TIDY_SOT_RETRIEVAL_INTEGRATION_PLAN.md`

4. **Dependency sync enforcement (pyproject.toml ↔ requirements.txt)**:
   - ✅ RESOLVED (BUILD-155): CI drift enforcement via `scripts/check_dependency_sync.py`
   - CI now fails if requirements.txt drifts from pyproject.toml (deterministic pip-compile check)

5. **Version consistency enforcement**:
   - ✅ RESOLVED (BUILD-155): CI version consistency check via `scripts/check_version_consistency.py`
   - CI now fails if version mismatches detected across pyproject.toml, PROJECT_INDEX.json, and __version__

**Next High-Leverage Improvements**:
1. **SOT Budget-Aware Retrieval Telemetry + Tests** (highest ROI):
   - Add per-phase telemetry fields: `include_sot`, `sot_chunks_retrieved`, `sot_chars_raw`, `total_context_chars`, `budget_utilization_pct`
   - Test coverage: budget gating, `format_retrieved_context()` char caps, opt-in defaults
   - **Why important**: Prevents silent token bloat, enables cost/quality optimization, validates BUILD-154 SOT documentation
   - Files: `src/autopack/autonomous_executor.py`, `tests/test_sot_budget_gating.py`, `tests/test_format_retrieved_context_caps.py`

**Intended Tidy Behavior** (for future AI agents to achieve):
```bash
# When user runs tidy, it should ALWAYS succeed at cleaning workspace, even if some files are locked
python scripts/tidy/tidy_up.py --execute

# Expected results (every time):
# ✅ Root directory: only autopack.db + allowed files/dirs remain
# ✅ All orphaned files archived to archive/diagnostics/logs/
# ✅ Old run directories cleaned (keep last 10 per prefix, age > 0 days)
# ✅ Empty directories removed
# ✅ Locked files reported but don't block cleanup of other items
# ✅ .autonomous_runs/ is CLEAN (no strayed files/folders)
```

**How to Verify Tidy is Working**:
```bash
# 1. Check .autonomous_runs is clean (should have ~8-15 items: runtime workspaces + active projects)
ls -la .autonomous_runs/ | wc -l

# 2. Verify no orphaned files at .autonomous_runs root
ls .autonomous_runs/*.log .autonomous_runs/*.json 2>&1 | grep "cannot access"  # Should show "No such file"

# 3. Check workspace violations
python scripts/tidy/verify_workspace_structure.py  # Should report 0 errors or only locked DB warnings
```

**Windows File Locks & Automatic Retry**: Tidy now **queues locked files for automatic retry**:
- Locked moves are saved to `.autonomous_runs/tidy_pending_moves.json`
- Next tidy run automatically retries pending items (after reboot/lock release)
- Uses exponential backoff (5min → 24hr) with bounded attempts (max 10, abandon after 30 days)
- **Automation**: Set up Windows Task Scheduler to run tidy at logon/daily (see [docs/guides/WINDOWS_TASK_SCHEDULER_TIDY.md](docs/guides/WINDOWS_TASK_SCHEDULER_TIDY.md))
- **Manual handling**: See [docs/TIDY_LOCKED_FILES_HOWTO.md](docs/TIDY_LOCKED_FILES_HOWTO.md) for immediate unlock strategies

**Latest Updates**:
- **BUILD-155 (2026-01-02)**: ✅ CI drift enforcement (dependency sync + version consistency), ✅ Telemetry schema fields added (`include_sot`, `sot_chunks_retrieved`, etc.), ✅ Packaging hygiene locked in. See [docs/BUILD_HISTORY.md](docs/BUILD_HISTORY.md#build-155) for details.
- **BUILD-145 Follow-up (2026-01-02)**: ✅ Persistent queue system for locked files, ✅ Automatic retry on next run, ✅ Windows Task Scheduler automation guide
- **BUILD-145 (2026-01-02)**: ✅ .autonomous_runs/ cleanup operational (46 orphaned files archived, 910 empty dirs cleaned), ✅ Windows lock handling (graceful skip + prevention), ✅ Database routing logic implemented, ✅ Run archival policy (archive/runs/, keep-last-N configurable). See [docs/BUILD-145-TIDY-SYSTEM-REVISION-COMPLETE.md](docs/BUILD-145-TIDY-SYSTEM-REVISION-COMPLETE.md) for details.

**Autonomous Tidy Workflow**:
Automatically consolidates archive files into SOT documentation using AI-powered classification:

```bash
# Tidy a project's archive directory
cd .autonomous_runs/your-project
python ../../scripts/tidy/autonomous_tidy.py archive --dry-run    # Preview changes
python ../../scripts/tidy/autonomous_tidy.py archive --execute    # Apply changes

# The system auto-detects the project from your working directory
```

**Excluded Directories**:
The tidy system automatically excludes these directories from processing:
- `superseded/` - Already classified files moved here after manual review
- `.git/` - Version control files
- `.autonomous_runs/` - Runtime artifacts
- `__pycache__/`, `node_modules/` - Build artifacts

Files in `archive/superseded/` have been reviewed and classified into SOT files and will not be processed again.

**Adding New Projects**:
1. Create project structure under `.autonomous_runs/<project-id>/`
2. Add configuration to database OR add default config in `scripts/tidy/project_config.py`:
   ```python
   elif project_id == "your-project":
       return {
           'project_id': 'your-project',
           'project_root': '.autonomous_runs/your-project',
           'docs_dir': 'docs',
           'archive_dir': 'archive',
           'sot_build_history': 'BUILD_HISTORY.md',
           'sot_debug_log': 'DEBUG_LOG.md',
           'sot_architecture': 'ARCHITECTURE_DECISIONS.md',
           'sot_unsorted': 'UNSORTED_REVIEW.md',
           'project_context': {
               'keywords': {
                   'build': ['implementation', 'feature', 'build'],
                   'debug': ['error', 'bug', 'fix'],
                   'architecture': ['decision', 'design', 'architecture']
               }
           },
           'enable_database_logging': True,
           'enable_research_workflow': True
       }
   ```

3. Run tidy from within your project directory - it will auto-detect the project and update the correct docs/ folder

**File Organization**:
- ✅ **SOT files** (6 files) go in `<project>/docs/`
- ✅ **Runtime cache** (phase plans, issue backlogs) go in `.autonomous_runs/`
- ✅ **Historical files** go in `<project>/archive/` (organized by type: plans/, reports/, research/, etc.)

See [PROJECT_INDEX.json](docs/PROJECT_INDEX.json) for complete configuration reference.

#### Script Organization System (Step 0 of Autonomous Tidy)

The Script Organization System automatically moves scattered scripts, patches, and configuration files from various locations into organized directories within the `scripts/` and `archive/` folders as **Step 0** of the autonomous tidy workflow.

**What Gets Organized:**

1. **Root Scripts** → `scripts/archive/root_scripts/`
   - Scripts at the repository root level: `*.py`, `*.sh`, `*.bat`
   - Example: `probe_script.py`, `test_auditor_400.py`, `run_full_probe_suite.sh`

2. **Root Reports** → `archive/reports/`
   - Markdown documentation from root: `*.md` (will be consolidated by tidy)
   - Example: `REPORT_TIDY_V7.md`, `ANALYSIS_PHASE_PLAN.md`

3. **Root Logs** → `archive/diagnostics/`
   - Log and debug files from root: `*.log`, `*.diff`
   - Example: `tidy_execution.log`, `patch_apply.diff`

4. **Root Config** → `config/`
   - Configuration files from root: `*.yaml`, `*.yml`
   - Example: `tidy_scope.yaml`, `models.yaml`

5. **Examples** → `scripts/examples/`
   - All files from `examples/` directory
   - Example: `multi_project_example.py`

6. **Tasks** → `archive/tasks/`
   - Task configuration files: `*.yaml`, `*.yml`, `*.json`
   - Example: `tidy_consolidation.yaml`

7. **Patches** → `archive/patches/`
   - Git patches and diff files: `*.patch`, `*.diff`
   - Example: `oi-fo-ci-failure.patch`

**What Stays in Place** (Never Moved):

Special Files:
- `setup.py`, `manage.py` - Package setup
- `conftest.py` - Pytest configuration
- `wsgi.py`, `asgi.py` - WSGI/ASGI entry points
- `__init__.py` - Python package markers
- `README.md` - Project README (stays at root)
- `docker-compose.yml`, `docker-compose.dev.yml` - Docker configs (stay at root)

Directories (Never Scanned):
- `scripts/` - Already organized
- `src/` - Source code
- `tests/` - Test suites (pytest)
- `config/` - Configuration files
- `.autonomous_runs/` - Sub-project workspaces
- `archive/` - Already archived
- `.git/`, `venv/`, `node_modules/`, `__pycache__/` - System directories

**Usage:**

```bash
# Manual standalone script organization (preview)
python scripts/organize_scripts.py

# Execute the organization
python scripts/organize_scripts.py --execute

# Automatic organization (integrated with tidy - runs as Step 0)
python scripts/tidy/autonomous_tidy.py archive --execute
```

**Note:** Script organization only runs for the **main Autopack project**, not for sub-projects in `.autonomous_runs/`.

**Integration with Autonomous Tidy:**

The script organizer runs as **Step 0** before the main tidy workflow:

```
AUTONOMOUS TIDY WORKFLOW
═══════════════════════════════════════════════════════════

Step 0: Script Organization (Autopack only)
   ↓
Step 1: Pre-Tidy Auditor
   ↓
Step 2: Documentation Consolidation
   ↓
Step 3: Archive Cleanup (sub-projects only)
   ↓
Step 4: Database Synchronization
   ↓
Post-Tidy Verification
```

**Configuration:** The script organization rules are defined in [scripts/tidy/script_organizer.py](scripts/tidy/script_organizer.py). To add new organization rules, edit the `script_patterns` configuration in that file.

### Storage Optimizer (2026-01-01)

**Policy-aware disk space analysis and cleanup recommendations**

The Storage Optimizer analyzes disk usage and identifies cleanup opportunities while respecting protected paths and retention policies. MVP provides dry-run reporting only (no deletion).

**Quick Start:**
```bash
# Scan C: drive and generate report
python scripts/storage/scan_and_report.py

# Scan specific directory
python scripts/storage/scan_and_report.py --dir c:/dev
```

**Key Features:**
- Policy-driven classification from `config/protection_and_retention_policy.yaml`
- Protected path enforcement (never flags SOT files, src/, tests/, .git/, databases)
- Retention window compliance (90/180/365 day windows)
- Category-based analysis (dev_caches, diagnostics_logs, runs, archive_buckets)
- Dry-run reporting (text + JSON formats)

**Documentation:**
- **Module**: [src/autopack/storage_optimizer/](src/autopack/storage_optimizer/)
- **Completion Report**: [docs/STORAGE_OPTIMIZER_MVP_COMPLETION.md](archive/superseded/reports/unsorted/STORAGE_OPTIMIZER_MVP_COMPLETION.md)
- **Policy**: [config/protection_and_retention_policy.yaml](config/protection_and_retention_policy.yaml) + [docs/DATA_RETENTION_AND_STORAGE_POLICY.md](archive/superseded/reports/unsorted/DATA_RETENTION_AND_STORAGE_POLICY.md)

Future phases will add execution capabilities (send2trash), automation (Windows Task Scheduler), and WizTree integration for faster scanning.

## Plan Conversion (Markdown -> phase_spec)
- Use `scripts/plan_from_markdown.py --in docs/PLAN.md --out .autonomous_runs/<project>/plan_generated.json` to convert markdown tasks into phase specs matching `docs/phase_spec_schema.md`.
- Inline tags in bullets override defaults: `[complexity:low]`, `[category:tests]`, `[paths:src/,tests/]`, `[read_only:docs/]`.
- Defaults: complexity=medium, task_category=feature; acceptance criteria come from indented bullets under each task.
- Fully automated run: `scripts/auto_run_markdown_plan.py --plan-md docs/PLAN.md --run-id my-run --patch-dir patches --apply --auto-apply-low-risk --test-cmd "pytest -q tests/smoke"` converts → plan JSON → runs maintenance mode (diagnostics first, gated apply). Checkpoints are on by default for maintenance runs.

## Owner Intent (Troubleshooting Autonomy)
- Autopack should approach Cursor “tier 4” troubleshooting depth: when failures happen, it should autonomously run governed probes/commands (from a vetted allowlist), gather evidence (logs, test output, patch traces), iterate hypotheses, and log decisions—without requiring the user to type raw commands.
- Natural-language control is preferred: the intent router (and future dashboard hooks) should trigger safe actions like planning ingest, memory maintenance, diagnostics, and context queries.
- Safety is mandatory: all actions must respect allowlists/denylists, timeouts, budgets, and avoid destructive ops; writes happen only in approved worktrees/contexts.
- See `docs/IMPLEMENTATION_PLAN_DIAGNOSTICS_PARITY_WITH_CURSOR.md` for the implementation plan to reach this capability.

### Patch Apply Hardening (2025-12-06)
- `GovernedApplyPath` now refuses the direct-write fallback whenever a patch touches existing files; fallback is limited to clean new-file-only patches and must write all expected files.
- Patch validation still runs first (dry-run git apply, lenient/3-way) and preserves backups; scope + protected-path enforcement remains unchanged.
- SQLite dev DB (`autopack.db`) now includes the `phases.scope` column to match the production schema (run_id already present).

### Comprehensive Error Reporting System (NEW)
Detailed error context capture and reporting for easier debugging:
- **Automatic Error Capture**: All exceptions automatically captured with full context
- **Rich Context**: Stack traces, phase/run info, request data, environment details
- **Error Reports**: Saved to `.autonomous_runs/{run_id}/errors/` as JSON + human-readable text
- **API Endpoints**:
  - `GET /runs/{run_id}/errors` - Get all error reports for a run
  - `GET /runs/{run_id}/errors/summary` - Get error summary
- **Stack Frame Analysis**: Captures local variables and function context at each stack level
- **Component Tracking**: Identifies where errors occurred (api, executor, builder, etc.)

**Error Report Location**:
```
.autonomous_runs/
  {run_id}/
    errors/
      20251203_013555_api_AttributeError.json  # Detailed JSON
      20251203_013555_api_AttributeError.txt   # Human-readable summary
```

**Usage**:
```bash
# View error summary for a run
curl http://localhost:8000/runs/my-run-id/errors/summary

# Get all error reports
curl http://localhost:8000/runs/my-run-id/errors
```

### Deletion Safeguards & Telegram Notifications (NEW - BUILD-107 to BUILD-111)
Two-tier deletion protection system with mobile notifications:

**Two-Tier Notification System**:
| Net Deletion   | Action            | Rationale                                      |
|----------------|-------------------|------------------------------------------------|
| < 100 lines    | No notification   | Small changes, safe to proceed automatically   |
| 100-200 lines  | **Notify only**   | Send Telegram notification, execution continues|
| > 200 lines    | **Block + Notify**| Require human approval via Telegram            |
| 50+ lines      | **Auto-save**     | Create git tag save point before deletion      |

**Key Features**:
- **Automatic Save Points**: Git tags created before deletions >50 lines for easy recovery
- **Telegram Integration**: Mobile notifications for large deletions and phase failures
- **Interactive Approval**: Optional approve/reject buttons via webhook (requires ngrok)
- **Smart Detection**: Net deletion calculation (lines removed - lines added)

**Configuration** (`.env`):
```bash
# Required for Telegram notifications
TELEGRAM_BOT_TOKEN="your_bot_token"
TELEGRAM_CHAT_ID="your_chat_id"

# Optional for interactive buttons
NGROK_URL="https://your-domain.ngrok.app"
AUTOPACK_CALLBACK_URL="http://localhost:8001"
```

**Setup & Testing**:
```bash
# Interactive setup wizard
python scripts/setup_telegram.py

# Verify credentials
python scripts/verify_telegram_credentials.py

# Test notifications (no actual deletions)
python scripts/test_deletion_safeguards.py --test-telegram

# Test full approval workflow (requires ngrok + backend)
python scripts/test_deletion_safeguards.py --test-approval

# Test threshold sensitivity
python scripts/test_deletion_safeguards.py --test-thresholds
```

**Recovery from Deletions**:
```bash
# List save points
git tag | grep save-before-deletion

# Restore from save point
git reset --hard save-before-deletion-{phase_id}-{timestamp}
```

See [docs/BUILD-107-108_SAFEGUARDS_SUMMARY.md](archive/superseded/reports/BUILD-107-108_SAFEGUARDS_SUMMARY.md) for complete documentation.

### Iterative Autonomous Investigation (NEW - BUILD-113)
Multi-round autonomous debugging that resolves failures without human intervention when safe, plus **proactive decision-making** for fresh feature implementations:

**Key Features**:
- **Goal-Aware Decisions**: Uses deliverables + acceptance criteria to guide fixes
- **Multi-Round Investigation**: Iteratively collects evidence until root cause found (reactive mode)
- **Proactive Patch Analysis**: Analyzes fresh patches BEFORE applying them (NEW)
- **Autonomous Low-Risk Fixes**: Auto-applies fixes <100 lines with no side effects
- **Full Audit Trails**: All decisions logged with rationale and alternatives
- **Safety Nets**: Git save points, automatic rollback, risk-based gating

**How It Works**:

*Reactive Mode* (after failure):
1. **Investigation**: Autopack runs multi-round diagnostics, collecting evidence iteratively
2. **Goal Analysis**: Compares evidence against phase deliverables and acceptance criteria
3. **Risk Assessment**: LOW (<100 lines, safe), MEDIUM (100-200, notify), HIGH (>200, block)
4. **Autonomous Fix**: For low-risk fixes, auto-applies with git save point + rollback on failure
5. **Smart Escalation**: Only blocks for truly risky (protected paths, large deletions) or ambiguous situations

*Proactive Mode* (NEW - before applying):
1. **Patch Analysis**: Builder generates patch, BUILD-113 analyzes it before application
2. **Risk Classification**: Database files → HIGH, >200 lines → HIGH, 100-200 → MEDIUM, <100 → LOW
3. **Confidence Scoring**: Based on deliverables coverage, patch size, code clarity
4. **Decision**:
   - **CLEAR_FIX** (LOW/MED risk + high confidence) → Auto-apply with DecisionExecutor
   - **RISKY** (HIGH risk) → Request human approval via Telegram before applying
   - **AMBIGUOUS** (low confidence or missing deliverables) → Request clarification
5. **Safe Execution**: All CLEAR_FIX patches applied with save points, validation, rollback on failure

**Enable** (experimental, default: false):
```bash
python -m autopack.autonomous_executor \
  --run-id my-run \
  --enable-autonomous-fixes
```

**Review Decision Logs**:
```bash
# View autonomous decisions
cat .autonomous_runs/my-run/decision_log.json

# Each decision includes:
# - Rationale (why this fix?)
# - Alternatives considered (what else was possible?)
# - Risk assessment (why low/medium/high?)
# - Deliverables met (which goals achieved?)
# - Files modified + net deletion count
# - Git save point for rollback
```

**Example Autonomous Fix**:
```
Phase: research-tracer-bullet
Failure: ImportError - cannot import 'TracerBullet'

Round 1: Initial diagnostics
- Found: TracerBullet class exists in tracer_bullet.py
- Missing: Import statement in __init__.py

Decision: CLEAR_FIX (auto-applied)
- Fix: Add "from .tracer_bullet import TracerBullet" to __init__.py
- Risk: LOW (1 line added, within allowed_paths, no side effects)
- Result: Tests passed, deliverable met, committed automatically
- Save point: git tag save-before-fix-research-tracer-bullet-20251221
```

See [docs/BUILD-113_ITERATIVE_AUTONOMOUS_INVESTIGATION.md](archive/superseded/reports/BUILD-113_ITERATIVE_AUTONOMOUS_INVESTIGATION.md) for complete documentation.

### Autopack Doctor
LLM-based diagnostic system for intelligent failure recovery:
- **Failure Diagnosis**: Analyzes phase failures and recommends recovery actions
- **Model Routing**: Uses Claude Sonnet 4.5 for routine failures and Claude Opus 4.5 for complex ones
- **Actions**: `retry_with_fix` (with hint), `replan`, `skip_phase`, `mark_fatal`, `rollback_run`
- **Budgets**: Per-phase limit (2 calls) and run-level limit (10 calls) to prevent loops
- **Confidence Escalation**: Upgrades to strong model if confidence < 0.7
- **Rule Refresh**: Project learned rules auto-reload mid-run when updated, so replans use the latest hints/rules without restarting.

**Configuration** (`config/models.yaml`):
```yaml
doctor_models:
  cheap: claude-sonnet-4-5
  strong: claude-opus-4-5
  min_confidence_for_cheap: 0.7
  health_budget_near_limit_ratio: 0.8
  high_risk_categories: [import, logic]
```

### Model Escalation System
Automatically escalates to more powerful models when phases fail repeatedly:
- **Intra-tier escalation**: Within complexity level (e.g., glm-4.7 -> claude-sonnet-4-5)
- **Cross-tier escalation**: Bump complexity level after N failures (low -> medium -> high)
- **Configurable thresholds**: `config/models.yaml` defines `complexity_escalation` settings

### Mid-Run Re-Planning with Message Similarity
Detects "approach flaws" vs transient failures using error message similarity:
- `_normalize_error_message()` - Strips variable content (paths, UUIDs, timestamps, line numbers)
- `_calculate_message_similarity()` - Uses `difflib.SequenceMatcher` with 0.8 threshold
- `_detect_approach_flaw()` - Triggers re-planning after consecutive same-type failures with similar messages

**Configuration** (`config/models.yaml`):
```yaml
replan:
  trigger_threshold: 2
  message_similarity_enabled: true
  similarity_threshold: 0.8
  fatal_error_types: [wrong_tech_stack, schema_mismatch, api_contract_wrong]
```

### Run-Level Health Budget
Prevents infinite retry loops by tracking failures across the run:
- `MAX_HTTP_500_PER_RUN`: 10 (stop after too many server errors)
- `MAX_PATCH_FAILURES_PER_RUN`: 15 (stop after too many patch failures)
- `MAX_TOTAL_FAILURES_PER_RUN`: 25 (hard cap on total failures)

### LLM Multi-Provider Routing
- Routes primarily to Anthropic (Claude Sonnet/Opus). GLM is disabled; OpenAI is fallback.
- **Provider tier strategy**:
  - Low/Medium/High: Claude Sonnet 4.5 (primary), escalate to Claude Opus 4.5 when needed
- Automatic fallback chain: Anthropic -> OpenAI
- Per-category routing policies (BEST_FIRST, PROGRESSIVE, CHEAP_FIRST)

**Environment Variables**:
```bash
# Required for each provider you want to use
ANTHROPIC_API_KEY=your-anthropic-key   # Anthropic - primary
OPENAI_API_KEY=your-openai-key         # OpenAI - optional fallback

# Backend auth (JWT, RS256)
JWT_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----...dev or prod key...-----END PRIVATE KEY-----"
JWT_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----...dev or prod key...-----END PUBLIC KEY-----"
# Optional overrides
JWT_ISSUER=autopack-backend
JWT_AUDIENCE=autopack-clients
```

### Auth tokens & JWKS
- Tokens are RS256 JWTs with `iss`/`aud` enforced.
- JWKS endpoint: `/api/auth/.well-known/jwks.json` (share with verifiers).
- Key load status: `/api/auth/key-status` (reports env vs generated keys).

### 📊 Real-Time Dashboard
- Provides run status, usage, and models list. Refer to `tests/test_dashboard_integration.py` for expected payloads/fields.
- Key routes (FastAPI):
  - `GET /dashboard/status` — overall health/version.
  - `GET /dashboard/usage` — recent token/phase usage aggregates.
  - `GET /dashboard/models` — current model routing table (source: `config/models.yaml`).
- Start the dashboard/API (dev): `python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8100` (set `PYTHONPATH=src`, `DATABASE_URL=sqlite:///autopack.db`).
- Start the dashboard/API (production): use PostgreSQL via `DATABASE_URL=postgresql://...` (see `docs/DEPLOYMENT.md` “Database Configuration”; Postgres is the supported production DB).
- Architecture: **LlmService (Model Router + Usage Track)** is the central control-plane routing layer feeding dashboard/model metadata.

### Hardening: Syntax + Unicode + Incident Fatigue
- Pre-emptive encoding fix at startup
- `PYTHONUTF8=1` environment variable for all subprocesses
- UTF-8 encoding on all file reads
- SyntaxError detection in CI checks

### Stage 2: Structured Edits for Large Files (NEW)
Enables safe modification of files of any size using targeted edit operations:
- **Automatic Mode Selection**: Files >1000 lines automatically use structured edit mode
- **Operation Types**: INSERT, REPLACE, DELETE, APPEND, PREPEND
- **Safety Features**: Validation, context matching, rollback on failure
- **No Truncation Risk**: Only generates changed lines, not entire file content
- **Format Contract**: Builder outputs must be JSON with a `files` array; legacy git-diff fallback is disabled for malformed outputs.

**3-Bucket Policy**:
- **Bucket A (≤500 lines)**: Full-file mode - LLM outputs complete file content
- **Bucket B (501-1000 lines)**: Diff mode - LLM generates git diff patches  
- **Bucket C (>1000 lines)**: Structured edit mode - LLM outputs targeted operations

For details, see [Stage 2 Documentation](docs/stage2_structured_edits.md) and [Phase Spec Schema](docs/phase_spec_schema.md).

---

## Phase 3 Preview: Direct Fix Execution

### Doctor `execute_fix` Action (Coming Soon)
Enables Doctor to execute infrastructure-level fixes directly without going through Builder:
- **Problem Solved**: Merge conflicts, missing files, Docker issues currently require manual intervention
- **Solution**: Doctor emits shell commands (`git checkout`, `docker restart`, etc.) executed directly
- **Safety**: Strict whitelist, workspace-only paths, opt-in via config, no sudo/admin

**Configuration** (`config/models.yaml`):
```yaml
doctor:
  allow_execute_fix_global: true    # Enabled (whitelisted commands only)
  max_execute_fix_per_phase: 1      # One attempt per phase
  allowed_fix_types: ["git", "file"] # Typed categories
```

**Supported Fix Types** (v1):
- `git`: `checkout`, `reset`, `stash`, `clean`, `merge --abort`
- `file`: `rm`, `mkdir`, `cp`, `mv` (workspace only)
- `python`: `pip install`, `pytest` (planned)

---

## Documentation

For comprehensive documentation, see **[docs/INDEX.md](docs/INDEX.md)** - the authoritative navigation hub for all project documentation.

### Quick Links
- **[Phase Spec Schema](docs/phase_spec_schema.md)**: Phase specification format, safety flags, and file size limits
- **[Structured Edits Guide](docs/stage2_structured_edits.md)**: Guide to structured edit mode for large files
- **[Build History](docs/BUILD_HISTORY.md)**: Authoritative completion ledger (what was built, when, and the completion status)
- **[Architecture Decisions](docs/ARCHITECTURE_DECISIONS.md)**: Design rationale and key decisions (the "why")
- **[Debug Log](docs/DEBUG_LOG.md)**: Failures, debugging sessions, and fixes (root-cause trail)

## Project Structure

```
C:/dev/Autopack/
├── .autonomous_runs/         # Runtime data and project-specific archives
│   ├── file-organizer-app-v1/# Example Project: File Organizer
│   └── ...
├── archive/                  # Framework documentation archive
├── config/
│   └── models.yaml           # Model configuration, escalation, routing policies
├── logs/
│   └── archived_runs/        # Archived log files from previous runs
├── src/
│   └── autopack/             # Core framework code
│       ├── autonomous_executor.py  # Main orchestration loop
│       ├── llm_service.py          # Multi-provider LLM abstraction
│       ├── model_router.py         # Model selection with quota awareness
│       ├── model_selection.py      # Escalation chains and routing policies
│       ├── error_recovery.py       # Error categorization and recovery
│       ├── archive_consolidator.py # Documentation management
│       ├── debug_journal.py        # Self-healing system wrapper
│       ├── memory/                 # Vector memory for context retrieval
│       │   ├── embeddings.py       # Text embeddings (OpenAI + local)
│       │   ├── faiss_store.py      # FAISS backend
│       │   ├── memory_service.py   # High-level insert/search
│       │   ├── maintenance.py      # TTL pruning
│       │   └── goal_drift.py       # Goal drift detection
│       ├── validators/             # Pre-apply validation
│       │   └── yaml_validator.py   # YAML/compose validation
│       └── ...
├── scripts/                  # Utility scripts
│   └── consolidate_docs.py   # Documentation consolidation
└── tests/                    # Framework tests
```

## Key Features

- **Autonomous Orchestration**: Wires Builder and Auditor agents to execute phases automatically.
- **Model Escalation**: Automatically escalates to more powerful models after failures.
- **Mid-Run Re-Planning**: Detects approach flaws and revises phase strategy.
- **Self-Healing**: Automatically logs errors, fixes, and extracts prevention rules.
- **Quality Gates**: Enforces risk-based checks before code application.
- **Multi-Provider LLM**: Routes to Gemini, GLM, Anthropic, or OpenAI with automatic fallback.
- **Project Separation**: Strictly separates runtime data and docs for different projects.

## Usage

### Running an Autonomous Build

```bash
python src/autopack/autonomous_executor.py --run-id my-new-run
```

### File Organization & Storage Structure

#### 🗂️ Directory Structure by Project

**Autopack Core** (`C:\dev\Autopack\`):
```
C:\dev\Autopack/
├── docs/                          # Truth sources for Autopack project
│   ├── README.md                  # Main Autopack documentation
│   └── consolidated_*.md          # Consolidated reference docs
├── scripts/                       # Active scripts (organized by type)
│   ├── backend/                   # Backend-related scripts (API, database)
│   ├── frontend/                  # Frontend-related scripts (UI, components)
│   ├── test/                      # Test scripts (pytest, unittest)
│   ├── temp/                      # Temporary/scratch scripts
│   └── utility/                   # General utility scripts (.sql, runners)
├── archive/                       # Archived Autopack artifacts
│   ├── plans/                     # Archived planning documents (.md, .json, .yaml)
│   ├── analysis/                  # Archived analysis & reviews (.md)
│   ├── logs/                      # Archived logs (.log, failure .json)
│   ├── prompts/                   # Archived prompts & delegations (.md)
│   ├── scripts/                   # Archived scripts (.py, .sh, .ps1)
│   ├── superseded/                # Old/superseded documents
│   └── unsorted/                  # Inbox for unclassified files
└── .autonomous_runs/              # Runtime data (see below)
```

**File Organizer Project** (`.autonomous_runs/file-organizer-app-v1/`):
```
.autonomous_runs/file-organizer-app-v1/
├── docs/                          # Truth sources for File Organizer
│   ├── WHATS_LEFT_TO_BUILD.md     # Current build plan
│   ├── CONSOLIDATED_*.md          # Consolidated docs
│   └── README.md                  # Project documentation
├── runs/                          # Active run outputs (NEW STRUCTURE)
│   ├── fileorg-country-uk/        # Family: UK country pack runs
│   │   ├── fileorg-country-uk-20251205-132826/
│   │   │   ├── run.log            # Run logs inside run folder
│   │   │   ├── errors/            # Error reports
│   │   │   ├── diagnostics/       # Diagnostic outputs
│   │   │   └── issues/            # Issue tracking
│   │   └── fileorg-country-uk-20251206-173917/
│   ├── fileorg-docker/            # Family: Docker-related runs
│   │   └── fileorg-docker-build-20251204-194513/
│   ├── fileorg-p2/                # Family: Phase 2 runs
│   └── backlog-maintenance/       # Family: Backlog maintenance runs
├── archive/                       # Archived project artifacts
│   ├── plans/                     # Archived planning documents (.md, .json, .yaml)
│   ├── analysis/                  # Archived analysis & reviews (.md)
│   ├── reports/                   # Consolidated reports (.md)
│   ├── prompts/                   # Archived prompts (.md)
│   ├── diagnostics/               # Archived diagnostics (.md, .log)
│   ├── scripts/                   # Archived scripts (organized by type)
│   │   ├── backend/               # Backend scripts
│   │   ├── frontend/              # Frontend scripts
│   │   ├── test/                  # Test scripts
│   │   ├── temp/                  # Temporary scripts
│   │   └── utility/               # Utility scripts
│   ├── logs/                      # Archived logs (.log, .json)
│   └── superseded/                # Old run outputs
│       ├── runs/                  # Archived runs by family
│       │   ├── fileorg-country-uk/
│       │   ├── fileorg-docker/
│       │   └── ...
│       ├── research/              # Old research docs
│       ├── refs/                  # Old reference files
│       └── ...
└── fileorganizer/                 # Source code
    ├── backend/
    └── frontend/
```

#### 📝 File Creation Guidelines

**For Cursor-Created Files** (All File Types):

Cursor creates files in the workspace root. The tidy system **automatically detects and routes** files based on project and type:

**Automatic Classification** (Project-First Approach):
1. **Detects project** from filename/content:
   - `fileorg-*`, `backlog-*`, `maintenance-*` → File Organizer project
   - `autopack-*`, `tidy-*`, `autonomous-*` → Autopack project
   - Content keywords also used for detection

2. **Classifies file type** by extension and content:
   - **Markdown files** (`.md`):
     - `IMPLEMENTATION_PLAN_*` → `plans/`
     - `ANALYSIS_*`, `REVIEW_*`, `REVISION_*` → `analysis/`
     - `PROMPT_*`, `DELEGATION_*` → `prompts/`
     - `REPORT_*`, `SUMMARY_*`, `CONSOLIDATED_*` → `reports/`
     - `DIAGNOSTIC_*` → `diagnostics/`

   - **Python scripts** (`.py`):
     - Backend-related (FastAPI, SQLAlchemy, database) → `scripts/backend/`
     - Frontend-related (React, UI, components) → `scripts/frontend/`
     - Test scripts (`test_*`, pytest) → `scripts/test/`
     - Temporary/scratch scripts → `scripts/temp/`
     - Utility scripts (runners, executors) → `scripts/utility/`

   - **Log files** (`.log`):
     - All logs → `logs/`

   - **JSON files** (`.json`):
     - Plans/configs (`*plan*.json`, `*phase*.json`) → `plans/`
     - Failures/errors (`*failure*.json`, `*error*.json`) → `logs/`
     - Other JSON → `unsorted/`

   - **SQL files** (`.sql`):
     - All SQL → `scripts/utility/`

   - **Config files** (`.yaml`, `.yml`, `.toml`):
     - Config/settings → `plans/`
     - Other YAML/TOML → `unsorted/`

   - **Shell scripts** (`.sh`, `.ps1`, `.txt`):
     - Scripts → `scripts/utility/`

3. **Routes to destination**:
   - **Autopack files**: `C:\dev\Autopack\{archive or scripts}\{bucket}\{file}`
   - **File Organizer files**: `.autonomous_runs\file-organizer-app-v1\archive\{bucket}\{file}`
   - **Unsorted inbox**: Used when classification is uncertain

4. **Truth Sources** (never moved):
   - Autopack: `C:\dev\Autopack\docs\`
   - File Organizer: `.autonomous_runs\file-organizer-app-v1\docs\`
   - Protected files: `WHATS_LEFT_TO_BUILD*.md`, `*.db`, `project_learned_rules.json`

**For Autopack-Created Files** (Runs, Logs):

Autopack automatically creates files in the correct locations:
- Run directories: `.autonomous_runs/{project}/runs/{family}/{run-id}/`
- Run logs: Inside the run directory at `{run-id}/run.log`
- Errors: `{run-id}/errors/`
- Diagnostics: `{run-id}/diagnostics/`

#### 🛠️ Tidy & Archive Maintenance

**Memory-Based Classification System** (98%+ Accuracy):

The tidy system uses a sophisticated hybrid classification approach combining PostgreSQL, Qdrant vector DB, and pattern matching to achieve 98%+ accuracy in file routing:

**Three-Tier Classification Pipeline**:
1. **PostgreSQL Keyword Matching**: Fast lookup using routing rules with content keywords (checks user corrections FIRST for 100% confidence)
2. **Qdrant Semantic Similarity**: 384-dimensional embeddings using sentence-transformers for deep content understanding
3. **Enhanced Pattern Matching**: Multi-signal detection with content validation and structure heuristics

**Classification Confidence Hierarchy**:
- **User Corrections**: 1.00 (absolute truth from manual corrections)
- **PostgreSQL Rules**: 0.95-1.00 (explicit routing rules)
- **Qdrant Semantic**: 0.90-0.95 (learned patterns from successful classifications)
- **Pattern Matching**: 0.60-0.92 (enhanced fallback with validation) ← **Improved Dec 11, 2025**

**Recent Enhancements (2025-12-11)**:
- **PostgreSQL Connection Pooling**: Eliminates transaction errors with auto-commit mode (1-5 connection pool)
- **Enhanced Pattern Confidence (0.60-0.92)**: Improved from 0.55-0.88 via content validation + structure heuristics
  - Content validation scoring: Type-specific semantic markers (plans: "## goal", scripts: "import", logs: "[INFO]")
  - File structure heuristics: Rewards length (>500 chars) and organization (3+ headers, 4+ sections)
  - Base confidence increased: 0.55 → 0.60
  - Maximum confidence increased: 0.88 → 0.92
- **Smart Prioritization**: Boosts confidence when high-quality signals disagree (PostgreSQL ≥0.8 → 0.75, Qdrant ≥0.85 → 0.70)
- **Interactive Correction CLI** ([scripts/correction/interactive_correction.py](scripts/correction/interactive_correction.py)): Review and correct classifications interactively
- **Batch Correction Tool** ([scripts/correction/batch_correction.py](scripts/correction/batch_correction.py)): Pattern/CSV/directory-based bulk corrections
- **Regression Test Suite** ([tests/test_classification_regression.py](tests/test_classification_regression.py)): 15 comprehensive tests ensuring 98%+ accuracy (100% pass rate)

**Accuracy Enhancements**:
- **Multi-Signal Detection**: Combines filename indicators, content keywords, and extension patterns with confidence boosting when signals agree (3+ signals = 85% confidence)
- **Disagreement Resolution**: When methods disagree, uses weighted voting (PostgreSQL=2.0, Qdrant=1.5, Pattern=1.0) to select best classification
- **Extension-Specific Validation**: Content validation per file type with confidence multipliers (e.g., `.log` files get 1.3x boost)
- **User Feedback Loop**: Interactive correction tool ([scripts/correction/interactive_correction.py](scripts/correction/interactive_correction.py)) stores corrections with highest priority
- **LLM-Based Auditor**: Reviews low-confidence classifications (<80%) using contextual analysis to approve, override, or flag for manual review
- **Automatic Learning**: Successful classifications (>80% confidence) automatically stored back to Qdrant for continuous improvement

**If Accuracy Needs Further Improvement**:

The current system achieves 98%+ accuracy with optimal confidence ranges. **Do not artificially inflate pattern matching confidence beyond 0.92**, as this would collapse the confidence hierarchy and reduce system reliability. Instead, use these approaches:

1. **Add More PostgreSQL Routing Rules** (Explicit Knowledge):
   - Add project-specific keyword patterns to `routing_rules` table
   - Define explicit filename patterns for high-volume file types
   - Create content-based rules for domain-specific files
   - Best for: Known patterns with clear classification rules

2. **Improve Qdrant Pattern Learning** (Semantic Knowledge):
   - Seed Qdrant with more high-quality examples
   - Use interactive correction tool to fix misclassifications (auto-learns to Qdrant)
   - Manually add edge cases with `init_file_routing_patterns.py`
   - Best for: Ambiguous files requiring semantic understanding

3. **Adjust Auditor Threshold** (Review More Files):
   - Lower threshold from 80% to 70% to review more borderline cases
   - Configure in classification auditor to catch more low-confidence files
   - Best for: Projects with high accuracy requirements

4. **NOT: Inflate Pattern Matching Confidence Artificially**:
   - Pattern matching is fundamentally limited (lacks semantic understanding)
   - Artificially boosting beyond 0.92 would overlap with Qdrant (0.90-0.95)
   - Would cause hierarchy collapse and reduce system reliability
   - Current 0.92 cap is well-positioned in the confidence spectrum

**Classification Auditor** ([classification_auditor.py](scripts/classification_auditor.py)):
- Provides deep semantic understanding vs pattern matching
- Uses LLM with full file content and project context from database
- Only audits classifications below 80% confidence threshold
- Can approve (boost confidence 10%), override (correct to 95% confidence), or flag for manual review
- Not redundant: Vector DB provides "looks like X" while Auditor provides "IS about Y feature"

**Setup Requirements**:
```bash
# Install vector DB dependencies
pip install sentence-transformers qdrant-client

# Start Qdrant
docker run -p 6333:6333 qdrant/qdrant

# Initialize file routing patterns collection
QDRANT_HOST="http://localhost:6333" python scripts/init_file_routing_patterns.py

# Configure environment
export DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"
export QDRANT_HOST="http://localhost:6333"
export EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"
```

**User Feedback & Corrections**:

**Interactive Review** (NEW - Dec 11, 2025):
```bash
# Review recent classifications interactively (one-by-one)
python scripts/correction/interactive_correction.py --interactive

# Review files flagged by auditor
python scripts/correction/interactive_correction.py --flagged

# Show correction statistics
python scripts/correction/interactive_correction.py --stats
```

**Batch Corrections** (NEW - Dec 11, 2025):
```bash
# Correct files by pattern (dry-run)
python scripts/correction/batch_correction.py \
  --pattern "fileorg_*.md" \
  --project file-organizer-app-v1 \
  --type plan

# Execute corrections for directory
python scripts/correction/batch_correction.py \
  --directory .autonomous_runs/temp \
  --project autopack \
  --type log \
  --execute

# Export potential misclassifications to CSV
python scripts/correction/batch_correction.py --export misclassified.csv

# Import corrections from CSV
python scripts/correction/batch_correction.py --csv corrections.csv --execute
```

**Legacy Tool** (Still Available):
```bash
# Interactively correct misclassifications (legacy)
python scripts/correct_classification.py --interactive

# View recent corrections
python scripts/correct_classification.py --show --limit 20
```

Corrections are stored in PostgreSQL `classification_corrections` table and immediately added to Qdrant as high-priority patterns with 100% confidence. The new tools provide dual storage (PostgreSQL + Qdrant) with immediate learning feedback.

**Manual Tidy Operations**:
```bash
# One-shot tidy with semantic analysis
python scripts/run_tidy_all.py

# Dry run to preview changes (with memory-based classification)
python scripts/tidy_workspace.py --root .autonomous_runs --dry-run --verbose

# Execute cleanup for specific project
python scripts/tidy_workspace.py --root .autonomous_runs/file-organizer-app-v1 --execute
```

**Configuration** (`tidy_scope.yaml`):
- Sets roots to tidy (default: `.autonomous_runs/file-organizer-app-v1`, `.autonomous_runs`, `archive`)
- Optional `purge: true` for permanent deletion (default is archive)
- Optional `db_overrides` per root for Postgres DSN

**Tidy Operations**:
1. **Superseded Handling**:
   - Files route to appropriate buckets: `research`, `delegations`, `phases`, `tiers`, `prompts`, `diagnostics`, `runs`, `refs`, `reports`, `plans`, `analysis`, `logs`, `scripts`
   - Run folders grouped by family: `.../archive/superseded/runs/<family>/<run-id>`
   - Family derived from run ID prefix (e.g., `fileorg-country-uk-20251205-132826` → family: `fileorg-country-uk`)

2. **Cursor File Detection** (All File Types):
   - Automatically detects **all file types** in workspace root (`.md`, `.py`, `.json`, `.log`, `.sql`, etc.)
   - **Project-first classification**: Detects which project files belong to
   - **Type classification**: Routes by file extension and content analysis
   - **Script sub-classification**: Python files classified as backend/frontend/test/temp/utility
   - Processes files created within last 7 days
   - Fallback to `archive/unsorted/` if classification fails

3. **Truth Source Protection**:
   - Never moves: `WHATS_LEFT_TO_BUILD*.md`, `*.db`, `project_learned_rules.json`
   - Protected prefixes: `plan_`, `plan-generated`
   - Protected files remain in their canonical locations

**Creation-Time Routing Helpers**:
- `route_new_doc(name, purpose, project_hint, archived)` - Get destination path for new documents
- `route_run_output(project_hint, family, run_id, archived)` - Get path for run outputs
- CLI: `python scripts/run_output_paths.py --doc-name PLAN.md --doc-purpose plan --project file-organizer-app-v1`

**Database Logging**:
- Tidy operations logged to `tidy_activity` table in PostgreSQL (if `DATABASE_URL` set)
- Fallback: JSONL at `.autonomous_runs/tidy_activity.log`
- Tracks: project_id, action, src/dest paths, SHA256 hashes, timestamp

**Classification Learning**:
- Successful classifications (>80% confidence) automatically stored to Qdrant
- User corrections stored in PostgreSQL and Qdrant with highest priority
- System continuously improves accuracy over time
- Uses `sentence-transformers/all-MiniLM-L6-v2` for embeddings (384-dimensional vectors)

**Safety**:
- Dry-run by default (review changes before executing)
- Creates checkpoint archives before moves/deletes
- Git commits before/after (optional via `--git-commit-before`/`--git-commit-after`)
- Purge is opt-in only (default is archive, not delete)
- Flagged files (from Auditor) are never auto-moved

**Comprehensive Workspace Cleanup**:
- Target structure: `archive/` buckets (plans, reports, analysis, research, prompts, diagnostics/logs, scripts, refs) and project-scoped `.../.autonomous_runs/<project>/archive/superseded/` buckets (same + runs/<family>/<run-id>). Truth sources live in `C:\dev\Autopack\docs` (Autopack) and `.../<project>/docs` (projects).
- Routing: use `route_new_doc` / `route_run_output` (or CLI helpers `run_output_paths.py` / `create_run_with_routing.py`) so new docs/runs land in the right project/bucket up front; `archive\unsorted` is last-resort inbox only.
- Diagnostics truth: treat `CONSOLIDATED_DEBUG.md` and similar diagnostics (e.g., `ENHANCED_ERROR_LOGGING.md`) as truth candidates—review/merge into the active `docs` copy, then archive or discard if superseded.
- For tidy system documentation, see **[scripts/tidy/README.md](scripts/tidy/README.md)**.

#### Tidy vs Storage Optimizer: Responsibilities + Shared Retention Policy

Autopack has **two** related systems that touch files on disk:

- **Tidy (workspace organization + knowledge reuse)**:
  - Goal: keep project knowledge **machine-usable** and **retrievable** (SOT ledgers + optional semantic indexing).
  - Actions: route root clutter into `archive/` buckets, consolidate historical markdown into SOT ledgers, maintain `archive/superseded/` as an audit trail.
  - Safety: never silently overwrite divergent SOT files; default should be dry-run/explicit.

- **Storage Optimizer (disk space reclamation)**:
  - Goal: reclaim disk space (primarily Windows) via safe cleanup + approvals + rollback.
  - Actions: remove or compact *safe* storage candidates (dev caches, old artifacts, etc.) based on policy.
  - Safety: must never delete SOT, source code, or required run artifacts without explicit approval.

**Single source of truth for retention and deletion safety**:
- See `archive/superseded/reports/unsorted/DATA_RETENTION_AND_STORAGE_POLICY.md` for:
  - protected paths (never delete),
  - retention windows for logs/runs/superseded,
  - allowed cleanup actions by category,
  - how Tidy + Storage Optimizer coordinate without breaking SOT retrieval or auditability.

### Consolidating Documentation

To tidy up and consolidate documentation across projects:

```bash
python scripts/consolidate_docs.py
```

This will:
1. Scan all documentation files.
2. Sort them into project-specific archives (`archive/` vs `.autonomous_runs/<project>/archive/`).
3. Create consolidated reference files (`CONSOLIDATED_DEBUG.md`, etc.) and keep truth sources in the project docs roots (`C:\dev\Autopack\docs` for Autopack; `.../file-organizer-app-v1/docs` for File Organizer).
4. Move processed files to `superseded/`.

---

## Configuration

### Model Escalation (`config/models.yaml`)

```yaml
complexity_escalation:
  enabled: true
  thresholds:
    low_to_medium: 2    # Escalate after 2 failures at low complexity
    medium_to_high: 2   # Escalate after 2 failures at medium complexity
  max_attempts_per_phase: 5
  failure_types:
    - auditor_reject
    - ci_fail
    - patch_apply_error

escalation_chains:
  builder:
    low:
      models: [glm-4.5-20250101, gemini-2.5-pro, claude-sonnet-4-5]
    medium:
      models: [gemini-2.5-pro, claude-sonnet-4-5, gpt-5]
    high:
      models: [claude-sonnet-4-5, gpt-5]
  auditor:
    low:
      models: [glm-4.5-20250101, gemini-2.5-pro]
    medium:
      models: [gemini-2.5-pro, claude-sonnet-4-5]
    high:
      models: [claude-sonnet-4-5, claude-opus-4-5]
```

### Re-Planning (`config/models.yaml`)

```yaml
replan:
  trigger_threshold: 2          # Consecutive same-type failures before re-plan
  message_similarity_enabled: true
  similarity_threshold: 0.8     # How similar messages must be (0.0-1.0)
  min_message_length: 30        # Skip similarity check for short messages
  max_replans_per_phase: 1      # Prevent infinite re-planning loops
  fatal_error_types:            # Immediate re-plan triggers
    - wrong_tech_stack
    - schema_mismatch
    - api_contract_wrong
```

---

**Version**: 0.5.1 (Memory & Classification Enhancements)
**License**: MIT
**Milestone note**: The “tests-passing-v1.0” milestone refers to a scoped historical validation suite, not the full repository test run used in modern draining. See “CI / completion policy” below.
**Classification Tests**: 100% pass rate (15/15 regression tests passing)

## CI / completion policy (important for draining)

During draining, Autopack runs the repo’s CI (typically `pytest`) but **phase completion is based on regression delta**, not absolute “all tests green”:

- **Baseline-delta gating**: a phase may complete even if CI exitcode is non-zero when it introduces no new persistent regressions relative to the captured baseline.
- **Collection/import errors**: pytest collection failures (exitcode `2`, failed collectors / import errors) are treated as **hard blocks** and should not complete.
- **Human approval override**: quality-gate “BLOCKED” can be overridden only within the existing PhaseFinalizer rules (it still blocks on critical regressions and collection errors).


## Project Status

<!-- SOT_SUMMARY_START -->
**Last Updated**: 2026-01-03 20:00

- **Builds Completed**: 173 (includes multi-phase builds, 153 unique)
- **Latest Build**: BUILD-166: Critical Improvements + Follow-Up Refinements ✅
- **Architecture Decisions**: 32 unique decisions (DEC-001 through DEC-020, with gaps)
- **Debugging Sessions**: 83

*Auto-generated by Autopack Tidy System*
<!-- SOT_SUMMARY_END -->
