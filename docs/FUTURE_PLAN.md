# What's Left to Build - Autopack Project Plans

**Last Updated**: 2025-12-18
**Completed Projects**:
1. ✅ Research System (Citation Validity Improvement) - 77.8% validity achieved
2. ✅ Runs Management API - Full CRUD API operational
3. ✅ BUILD-049: Deliverables Validation & Self-Correction

**Active Projects**:
1. FileOrganizer Phase 2 (Beta Release)
2. Research System Chunk 0 (Tracer Bullet) - Monitoring first successful run

This file contains tasks in Autopack format for autonomous execution.

---

## ✅ COMPLETE: Research System - Citation Validity Improvement

**Current Status**: Phase 0 ✅ | Phase 1 ✅ | Phase 2 ✅ | PROJECT COMPLETE
**Citation Validity**: 77.8% (was 59.3% baseline, +18.5% improvement)
**Plan Version**: v2.3
**Reference**: [docs/RESEARCH_CITATION_FIX_PLAN.md](RESEARCH_CITATION_FIX_PLAN.md)
**Completion Date**: 2025-12-16

### Context
The research system citation validity improvement project implemented fixes to increase citation accuracy from 59.3% baseline toward ≥80% target. All planned phases are complete. **Final status: 77.8% validity (+18.5% improvement)**.

**Phase 3 Decision**: Further improvements NOT RECOMMENDED. Remaining 2.2% gap is due to LLM quality issues (category selection, quote extraction) rather than validator bugs. Validator logic is working correctly per RESEARCH_CITATION_FIX_PLAN.md.

**Completed Work**:
- ✅ Phase 0: Foundation modules (text_normalization.py, verification.py) - 54/54 tests passing
- ✅ Phase 1: Relax numeric verification (validators.py created with fix) - 20/20 tests passing - **72.2% validity**
- ✅ Phase 1 Evaluation: Citation validity 72.2% (+12.9% from baseline)
- ✅ **Phase 2: Enhanced Text Normalization** - Selective normalization (HTML + Unicode, no markdown) - **77.8% validity (+5.6%)**
- ✅ Phase 3 Investigation: Remaining issues analyzed - LLM quality, not validator bugs
- ✅ BUILD-039: JSON repair for structured_edit mode - **VALIDATED**
- ✅ BUILD-040: Auto-convert full-file format to structured_edit - **VALIDATED**
- ✅ File Restoration: github_gatherer.py, citation_validator.py - **COMPLETE**

**Restoration Run Results**:

**v2.1 Run** (2025-12-16, 16:37-16:57):
- Duration: 20 minutes | Failures: 12/25 budget | Status: FATAL
- Root cause: JSON parsing errors in structured_edit mode

**v2.2 Run** (2025-12-16, 21:35-21:45):
- Duration: 10 minutes | Failures: 0/25 budget | Status: ✅ SUCCESS
- BUILD-039 validated: JSON repair 100% success (3/3)
- Issue: Empty operations (schema mismatch) - no files created

**v2.3 Run** (2025-12-16, 22:25-22:43):
- Duration: 17 minutes | Format conversions: 3/4 success | Status: ✅ FILES CREATED
- BUILD-040 validated: Format auto-conversion working
- Files created: github_gatherer.py (9.2KB), citation_validator.py (4KB), __init__.py (204B)

### Task R1: Restore GitHub Gatherer ✅ COMPLETE
**Phase ID**: `restore_github_gatherer_v2`
**Category**: restoration
**Complexity**: medium
**Description**: Create src/autopack/research/gatherers/github_gatherer.py with GitHub API integration, README fetching, and LLM-based finding extraction.

**Acceptance Criteria**:
- [x] File src/autopack/research/gatherers/github_gatherer.py exists
- [x] GitHubGatherer class with discover_repositories(), fetch_readme(), extract_findings() methods
- [x] LLM extraction prompt emphasizes CHARACTER-FOR-CHARACTER quotes in extraction_span
- [x] JSON parsing handles markdown code blocks
- [x] File imports successfully (no syntax errors)

**Dependencies**: None
**Completion**: v2.3 run (2025-12-16T22:28)
**Status**: ✅ COMPLETE

### Task R2: Restore Evaluation Module ✅ COMPLETE
**Phase ID**: `restore_evaluation_module_v2`
**Category**: restoration
**Complexity**: medium
**Description**: Create src/autopack/research/evaluation/ module with CitationValidityEvaluator class that uses validators.CitationValidator.

**Acceptance Criteria**:
- [x] Directory src/autopack/research/evaluation/ exists
- [x] File citation_validator.py created with CitationValidityEvaluator
- [x] Imports validators.CitationValidator successfully
- [x] evaluate_summary() method implemented (tracks valid/invalid counts, failure reasons)
- [x] Returns structured results: total, valid, invalid, validity_percentage, failure_breakdown

**Dependencies**: Task R1
**Completion**: v2.3 run (2025-12-16T22:30)
**Status**: ✅ COMPLETE

### Task R3: Run Phase 1 Evaluation ✅ COMPLETE
**Phase ID**: `run_phase1_evaluation_v2`
**Category**: test
**Complexity**: low
**Description**: Execute evaluation script to measure citation validity after Phase 1 fix. Test on 3-5 sample repositories.

**Acceptance Criteria**:
- [x] Evaluation script created and runs successfully
- [x] 6 repositories tested across 3 topics (ML, web, data viz)
- [x] Citation validity measured: **72.2%** (13 valid / 18 total findings)
- [x] Results saved to .autonomous_runs/research-citation-fix/phase1_evaluation_results.json
- [x] Comparison to baseline: +12.9% improvement (from 59.3% to 72.2%)
- [x] Decision: **<80% → Proceed to Phase 2 (Task R4)**

**Evaluation Results**:
- Repositories: tensorflow/tensorflow, huggingface/transformers, twbs/bootstrap, fastapi/fastapi, d3/d3, grafana/grafana
- Failure Analysis: 3 "extraction_span not found" (text normalization), 2 "numeric mismatch"
- **Conclusion**: Phase 1 improved validity but Phase 2 needed for ≥80% target

**Dependencies**: Tasks R1 ✅, R2 ✅
**Completion**: 2025-12-16T23:04
**Status**: ✅ COMPLETE

### Task R4: Enhanced Text Normalization ✅ COMPLETE
**Phase ID**: `phase2_enhanced_normalization_v2`
**Category**: feature
**Complexity**: medium
**Description**: Integrated text_normalization.normalize_text() into validators.py _normalize_text() method with selective normalization approach.

**Acceptance Criteria**:
- [x] validators.py imports from autopack.text_normalization
- [x] _normalize_text() uses normalize_text(text, strip_markdown=False) - **selective approach**
- [x] HTML entity handling verified
- [x] Unicode normalization verified
- [x] Markdown stripping DISABLED (strip_markdown=False) - prevents over-normalization of GitHub content
- [x] All tests pass (20/20 in test_research_validators.py)

**Dependencies**: Task R3 results
**Actual Impact**: +5.6% citation validity (72.2% → 77.8%)
**Completion**: 2025-12-16
**Status**: ✅ COMPLETE

### Task R5: Final Evaluation ✅ COMPLETE
**Phase ID**: `run_phase2_evaluation_v2`
**Category**: test
**Complexity**: low
**Description**: Final evaluation after Task R4 enhanced normalization. Measured citation validity and analyzed remaining failures.

**Acceptance Criteria**:
- [x] Evaluation ran successfully on test repositories
- [x] Final citation validity measured: **77.8%**
- [x] Results compared to Phase 0 (59.3%) and Phase 1 (72.2%) baselines
- [x] **Phase 3 Investigation**: Remaining failures analyzed - due to LLM quality, not validator bugs
- [x] **Decision**: Project complete. No further validator improvements recommended.

**Dependencies**: Task R4
**Actual Result**: 77.8% validity (+18.5% total improvement, +5.6% from Phase 2)
**Completion**: 2025-12-16
**Status**: ✅ COMPLETE

### Summary

**Project Complete**: Research Citation Validity Improvement achieved 77.8% validity (+18.5% from 59.3% baseline). While below the 80% target, remaining 2.2% gap is due to LLM extraction quality issues, not validator logic. Further improvements require prompt engineering, not validator changes.

### Infrastructure Fixes Completed

**BUILD-039** (2025-12-16T18:45) - JSON Repair for Structured Edit Mode
- ✅ Added JsonRepairHelper to structured_edit mode parser
- ✅ Enables autonomous recovery from malformed JSON
- ✅ Validation: v2.2 run had 0 JSON parse failures (vs 12 in v2.1)

**BUILD-040** (2025-12-16T22:43) - Auto-Convert Full-File Format to Structured Edit
- ✅ Auto-converts `{"files": [...]}` to `{"operations": [...]}`
- ✅ Handles semantic errors (wrong schema) in addition to syntax errors
- ✅ Validation: v2.3 run successfully created all 3 files
- ✅ Completes 4-layer auto-recovery: BUILD-037 → 038 → 039 → 040

**BUILD-041** (2025-12-17T02:00) - 🔄 IN PROGRESS: Executor State Persistence Fix
- **Status**: Phases 1-2 Complete, Phase 3 In Progress
- **Problem**: Executor enters infinite loop when execute_phase() returns early before exhausting max_attempts
- **Root Cause**: State split between instance attributes (attempt counter) and database (phase state)
- **Solution**: Database-backed state persistence - move attempt tracking to database columns
- **Progress**:
  - ✅ Phase 1: Database schema migration (4 columns added: attempts_used, max_attempts, last_attempt_timestamp, last_failure_reason)
  - ✅ Phase 2: Database helper methods (4 methods: _get_phase_from_db, _update_phase_attempts_in_db, _mark_phase_complete_in_db, _mark_phase_failed_in_db)
  - 🔄 Phase 3: Refactor execute_phase() to use database state (IN PROGRESS)
  - ⏳ Phase 4: Update get_next_executable_phase() method
  - ⏳ Phase 5: Feature flag and testing
  - ⏳ Phase 6: Rollout and monitoring
- **Reference**: [BUILD-041_EXECUTOR_STATE_PERSISTENCE.md](BUILD-041_EXECUTOR_STATE_PERSISTENCE.md)
- **Blocked**: FileOrganizer Phase 2 Beta Release (infinite loop prevents execution)

**BUILD-049** (2025-12-18T04:00) - ✅ COMPLETE: Deliverables Validation & Self-Correction
- **Status**: Complete - 3 critical bugs fixed
- **Problem**: Builder creating files in wrong locations, unable to self-correct despite validation
- **Root Causes Discovered**:
  - **Bug #1 (DBG-010)**: UnboundLocalError - duplicate Path import shadowed module import (autonomous_executor.py:3447)
  - **Bug #2 (DBG-011)**: Empty scope dict - hard-coded `scope: {}` instead of reading from database (autonomous_executor.py:1261)
  - **Bug #3 (DBG-012)**: Learning hints not passed to retry attempts - excluded same-phase hints (learned_rules.py:197)
  - **Bug #4 (DBG-013)**: Vague hints - only showed first 3 missing files without path pattern
  - **Bug #5 (DBG-014)**: Re-planning interference - Doctor resets attempts counter, causing regression (SYSTEMIC)
- **Solutions**:
  - Bug #1: Removed duplicate `from pathlib import Path` at line 3447
  - Bug #2: Changed to `getattr(phase_db, 'scope', None) or {}` at line 1261
  - Bug #3: Changed `if hint.phase_index >= phase_index:` to `>` at line 197 (enables intra-phase learning)
  - Bug #4: Enhanced hint generation to show wrong→correct transformations and common path prefix
  - Bug #5: ➡️ Escalated to BUILD-050 (architectural fix required)
- **Impact**: Enables autonomous self-correction - Builder now receives validation feedback on retry attempts
- **Verification**: Executor attempt 7 confirmed Builder receiving 5 hints (0 before fix), attempt 8 showed partial success with improved hints
- **Reference**: [BUILD-049_DELIVERABLES_VALIDATION.md](BUILD-049_DELIVERABLES_VALIDATION.md), [DEBUG_LOG.md](DEBUG_LOG.md)

**BUILD-050** (2025-12-18) - ✅ COMPLETE (Phases 1 & 2): Self-Correction Architecture Improvements
- **Status**: Phase 1 ✅ Complete | Phase 2 ✅ Complete | Phase 3 Future Work
- **Completion Date**: 2025-12-18
- **Problem**: Attempt counter overloading causes non-deterministic self-correction behavior
- **Root Cause Analysis**:
  - Single `attempt` counter serves three conflicting purposes:
    1. **Retry progression**: Tracking hints accumulation across attempts
    2. **System state epoch**: Marking replan boundaries
    3. **Model selection signal**: Triggering escalation (Sonnet → Opus)
  - When Doctor re-planning resets `attempt=0`, it destroys information about retry progression and model escalation
  - Deliverables contract enforced through soft hints instead of hard constraints
  - Builder receives conflicting guidance from tactical (hints) and strategic (Doctor replan) systems
- **Implemented Solution**:
  - ✅ **Phase 1**: Deliverables contract as hard constraint in Builder prompt
    - Created `_build_deliverables_contract()` helper function (autonomous_executor.py:743-820)
    - Injected contract BEFORE learning hints in all Builder clients (openai_clients.py:246, anthropic_clients.py:2229)
    - Contract includes: required file paths, common prefix, forbidden patterns from previous failures
  - ✅ **Phase 2**: Decoupled attempt counters (non-destructive replanning)
    - Added three new Phase model fields: `retry_attempt`, `revision_epoch`, `escalation_level` (models.py:208-210)
    - Removed deprecated `attempts_used` and `max_attempts` fields
    - Created database migration script (scripts/migrations/migrate_build050_decoupled_counters.py)
    - Updated all 15+ references in autonomous_executor.py to use new counters
    - Modified replan logic (4 locations) to increment `revision_epoch` instead of resetting attempts
    - Added `MAX_RETRY_ATTEMPTS = 5` constant
  - ⏳ **Phase 3**: Generalize tactical vs strategic error handling (future enhancement)
- **Impact**: Enables consistent, reliable autonomous self-correction with non-destructive replanning
- **Reference**: [DBG-014_REPLAN_INTERFERENCE_ANALYSIS.md](DBG-014_REPLAN_INTERFERENCE_ANALYSIS.md), [DEBUG_LOG.md](DEBUG_LOG.md#dbg-014)
- **Commits**: da261695, 9d24aa73

---

## FileOrganizer Phase 2 (Beta Release)

**Current Status**: v1.0.0 Alpha Complete (9/9 weeks finished)
**Next Phase**: Beta Release + Production Hardening

---

## Phase 2 Tasks (Autopack-Ready)

### Task 1: Test Suite Fixes
**Phase ID**: `fileorg-p2-test-fixes`
**Category**: testing
**Complexity**: low
**Description**: Fix test suite dependency conflicts (httpx/starlette version issues). Resolve version pins in requirements.txt and ensure all 12 test files pass.

**Acceptance Criteria**:
- [ ] All 12 test files passing
- [ ] pytest.ini with proper configuration
- [ ] Updated requirements.txt with compatible versions
- [ ] No dependency conflicts

**Dependencies**: None

**Estimated Tokens**: 8,000
**Confidence**: 95%
**Status**: Dependency pins updated (FastAPI 0.104.x, Starlette 0.27.x, HTTPX 0.25.x<0.26). Current pytest run: 83 passed, 161 skipped (feature-dependent tests still pending implementation).

---

### Task 2: Frontend Build System
**Phase ID**: `fileorg-p2-frontend-build`
**Category**: frontend
**Complexity**: low
**Description**: Setup frontend build system. Run npm install, create production build, test Electron packaging, and commit package-lock.json.

**Acceptance Criteria**:
- [ ] node_modules installed (locally)
- [ ] Production build created (dist/)
- [ ] Electron app packaged for distribution
- [ ] package-lock.json committed

**Dependencies**: None

**Estimated Tokens**: 5,000
**Confidence**: 90%

---

### Task 3: Docker Deployment
**Phase ID**: `fileorg-p2-docker`
**Category**: deployment
**Complexity**: medium
**Description**: Create Docker deployment configuration. Implement Dockerfile for backend, docker-compose.yml for multi-container setup, .dockerignore, deployment scripts, and documentation.

**Acceptance Criteria**:
- [ ] Dockerfile (Python 3.11 + dependencies)
- [ ] docker-compose.yml (multi-container setup)
- [ ] .dockerignore (exclude venv, node_modules)
- [ ] deploy.sh script
- [ ] Updated DEPLOYMENT_GUIDE.md
- [ ] Local docker deployment tested

**Dependencies**: `fileorg-p2-test-fixes`

**Estimated Tokens**: 12,000
**Confidence**: 85%

---

### Task 4: Country-Specific Pack Templates (UK)
**Phase ID**: `fileorg-p2-country-uk`
**Category**: backend
**Complexity**: medium
**Description**: Create UK-specific pack templates for tax and immigration documents. Research UK requirements, create YAML templates, add country-specific categories and keywords, create validation tests.

**Acceptance Criteria**:
- [ ] tax_uk.yaml with UK-specific categories
- [ ] immigration_uk.yaml with UK visa requirements
- [ ] Test suite for UK pack loading
- [ ] User guide updates for UK packs

**Dependencies**: None

**Estimated Tokens**: 15,000
**Confidence**: 75%

---

### Task 5: Country-Specific Pack Templates (Canada)
**Phase ID**: `fileorg-p2-country-canada`
**Category**: backend
**Complexity**: medium
**Description**: Create Canada-specific pack templates for tax and immigration documents. Research Canadian requirements, create YAML templates, add country-specific categories and keywords, create validation tests.

**Acceptance Criteria**:
- [ ] tax_canada.yaml with Canadian-specific categories
- [ ] immigration_canada.yaml with Canadian visa requirements
- [ ] Test suite for Canada pack loading
- [ ] User guide updates for Canada packs

**Dependencies**: None

**Estimated Tokens**: 15,000
**Confidence**: 75%

---

### Task 6: Country-Specific Pack Templates (Australia)
**Phase ID**: `fileorg-p2-country-australia`
**Category**: backend
**Complexity**: medium
**Description**: Create Australia-specific pack templates for tax and immigration documents. Research Australian requirements, create YAML templates, add country-specific categories and keywords, create validation tests.

**Acceptance Criteria**:
- [ ] tax_australia.yaml with Australian-specific categories
- [ ] immigration_australia.yaml with Australian visa requirements
- [ ] Test suite for Australia pack loading
- [ ] User guide updates for Australia packs

**Dependencies**: None

**Estimated Tokens**: 15,000
**Confidence**: 75%

---

### Task 7: Backlog Maintenance (Proposal)
**Phase ID**: `fileorg-backlog-maintenance`
**Category**: maintenance
**Complexity**: medium
**Description**: Run an opt-in maintenance mode that parses a curated backlog (e.g., `consolidated_debug.md`), converts items into scoped phases with `allowed_paths`, runs diagnostics/probes, and produces propose-first patches plus targeted tests. Applies only under governed_apply with checkpoints and budget caps.

**Acceptance Criteria**:
- [ ] Backlog parser produces per-item phases with `allowed_paths` and budgets
- [ ] Diagnostics artifacts stored under `.autonomous_runs/<run_id>/diagnostics` per item
- [ ] Propose-first output (patch + test results); apply guarded behind approval/checkpoint
- [ ] Checkpoint/rollback in place (branch+commit per item or revert on failure)
- [ ] DecisionLog entries and dashboard diagnostics card reflect latest maintenance run
- [ ] Use compact JSON summaries for diagnostics/auditor/test outcomes to keep token usage efficient (store full logs/patches as artifacts and reference paths, not inline)

**Dependencies**: None (opt-in)
**Estimated Tokens**: 8,000
**Confidence**: 70%

---

### Task 7: Advanced Search & Filtering
**Phase ID**: `fileorg-p2-search`
**Category**: backend
**Complexity**: medium
**Description**: Implement advanced search and filtering capabilities. Add full-text search using SQLite FTS5, multi-field search (filename, OCR text, category), date range filtering, confidence score filtering, and export functionality.

**Acceptance Criteria**:
- [ ] Backend: FTS5 index on documents table
- [ ] Backend: Advanced search endpoint
- [ ] Multi-field search (filename, OCR, category)
- [ ] Date range filtering
- [ ] Confidence score filtering
- [ ] Export search results functionality
- [ ] Frontend: Advanced search UI component
- [ ] Tests: Search query validation

**Dependencies**: `fileorg-p2-test-fixes`

**Estimated Tokens**: 10,000
**Confidence**: 90%

---

### Task 8: Batch Upload & Processing
**Phase ID**: `fileorg-p2-batch-upload`
**Category**: backend
**Complexity**: medium
**Description**: Implement batch upload and processing system. Add multi-file upload endpoint, background job queue (threading), progress tracking, batch classification, frontend drag-and-drop multi-file upload, and progress indicators.

**Acceptance Criteria**:
- [ ] Backend: Batch upload endpoint
- [ ] Backend: Job queue system (threading)
- [ ] Backend: Progress tracking per document
- [ ] Backend: Batch classification endpoint
- [ ] Frontend: Multi-file drag-and-drop
- [ ] Frontend: Batch progress indicator
- [ ] Tests: Concurrent upload tests

**Dependencies**: None

**Estimated Tokens**: 10,000
**Confidence**: 85%

---

### Task 9: User Authentication & Multi-User Support
**Phase ID**: `fileorg-p2-auth`
**Category**: backend
**Complexity**: high
**Description**: Implement user authentication and multi-user support. Add User model, JWT authentication using fastapi-users, user registration/login endpoints, document ownership, frontend login/register pages, protected routes, and user-specific pack instances.

**Acceptance Criteria**:
- [ ] Backend: User model + authentication
- [ ] Backend: JWT token management
- [ ] Backend: User registration/login endpoints
- [ ] Backend: Document ownership (user_id foreign key)
- [ ] Backend: User-specific pack instances
- [ ] Frontend: Login/register UI
- [ ] Frontend: Protected routes
- [ ] Tests: Authentication flow tests
- [ ] Database migration scripts

**Dependencies**: `fileorg-p2-test-fixes`, `fileorg-p2-docker`

**Estimated Tokens**: 20,000
**Confidence**: 80%

---

## Summary

**Total Tasks**: 9
**Total Estimated Tokens**: ~110,000 tokens (55% of 200K budget)
**Total Estimated Time**: 20-30 hours (autonomous execution)

**Priority Tiers**:
- **Tier 1 (High Priority)**: Test Suite Fixes, Frontend Build System
- **Tier 2 (Medium Priority)**: Docker Deployment, Country Packs (UK, Canada, Australia)
- **Tier 3 (Low Priority)**: Advanced Search, Batch Upload, Authentication

**Recommended Execution Order**:
1. Test Suite Fixes (quick win, 95% confidence)
2. Frontend Build System (validates npm workflow)
3. Docker Deployment (larger but standard pattern)
4. Country packs can run in parallel
5. Advanced Search & Batch Upload
6. Authentication (highest complexity, benefits from prior learnings)

---

## Maintenance Backlog

**Purpose**: Focused maintenance plan for addressing open issues (OI-FO-*) using the Autopack maintenance flow. This is separate from the Phase 2 feature tasks above.

### Modes
- **Option A**: Maintain/build the maintenance system (meta) — run acceptance criteria for `fileorg-backlog-maintenance`.
- **Option B**: Use maintenance to fix specific open issues (OI-FO-*) from `DEBUG_LOG.md`.

### Runbook
1. **Convert markdown → plan JSON**
   ```bash
   python scripts/plan_from_markdown.py --in .autonomous_runs/file-organizer-app-v1/WHATS_LEFT_TO_BUILD.md --out .autonomous_runs/file-organizer-app-v1/plan_generated.json
   ```
   If merging: add `--merge-base autopack_phase_plan.json --allow-update` (only when overwriting IDs)

2. **Run maintenance (checkpoints on by default)**
   Diagnostics first; apply only if auditor approves + checkpoint exists; low-risk auto-apply optional.
   ```bash
   python src/autopack/autonomous_executor.py --run-id backlog-maint \
     --maintenance-plan .autonomous_runs/file-organizer-app-v1/plan_generated.json \
     --maintenance-patch-dir patches \
     --maintenance-apply \
     --maintenance-auto-apply-low-risk \
     --maintenance-checkpoint \
     --test-cmd "pytest -q tests/smoke"
   ```

3. **Logging/token efficiency**
   Default: compact JSON summaries; include short excerpts only for high-priority events (apply failure, auditor reject, test failure, protected-path violation); keep full logs/patches as artifacts.

4. **Safety**
   Allowed paths: constrain per item; protected: `.git/`, `.autonomous_runs/`, `config/`.
   Apply is gated by auditor and checkpoints; auto-apply low-risk enforces size/test guards.

### Maintenance Items (OI-FO-*)

**Task: Fix UK YAML truncation**
- **Phase ID**: `fileorg-maint-uk-yaml-truncation`
- **Category**: maintenance
- **Complexity**: medium
- **Description**: Resolve OI-FO-UK-YAML-TRUNCATION (truncated YAML in UK packs). Validate/repair YAML headers and required mappings.
- **Acceptance Criteria**:
  - [ ] YAML loads without truncation errors
  - [ ] Tests pass for UK packs (targeted YAML validation or pack load)
  - [ ] Compact diagnostics summary + artifact paths; excerpts only on failure
- **Allowed Paths**: `prompts/`, `docs/`, `templates/`, `src/`
- **Tests**: `pytest -q tests/test_pack_routes.py -k uk`
- **Apply**: low-risk auto-apply permitted if auditor approves; otherwise propose-first.

**Task: Fix frontend no-op**
- **Phase ID**: `fileorg-maint-frontend-noop`
- **Category**: maintenance
- **Complexity**: medium
- **Description**: Resolve OI-FO-FRONTEND-NOOP (frontend action not taking effect). Identify and fix the no-op behavior.
- **Acceptance Criteria**:
  - [ ] Repro fixed (no-op resolved)
  - [ ] Targeted tests pass
  - [ ] Compact diagnostics summary + artifact paths
- **Allowed Paths**: `src/frontend/`, `prompts/`, `docs/`, `scripts/`
- **Tests**: `npm test` or `pytest -q tests/test_frontend_*`
- **Apply**: low-risk auto-apply permitted if auditor approves; otherwise propose-first.

**Task: YAML Schema Warnings**
- **Phase ID**: `oi-fo-yaml-schema`
- **Description**: Resolve YAML schema warnings across packs.
- **Allowed Paths**: `packs/`, `src/backend/packs/`, `tests/`
- **Tests**: `pytest -q tests/test_pack_routes.py`
- **Apply**: allowed (auditor+checkpoint)

**Task: Patch Apply Mismatch**
- **Phase ID**: `oi-fo-patch-mismatch`
- **Description**: Address patch apply mismatches on structured edits.
- **Allowed Paths**: `src/backend/`, `src/frontend/`, `tests/`
- **Tests**: `pytest -q tests/test_autonomous_executor.py`
- **Apply**: allowed (auditor+checkpoint)

**Task: CI Failure Review**
- **Phase ID**: `oi-fo-ci-failure`
- **Description**: Investigate failing CI items; collect diagnostics and propose fixes.
- **Allowed Paths**: `src/`, `tests/`, `README`, `docs/`
- **Tests**: `pytest -q` (or targeted failing suites)
- **Apply**: propose-first unless auditor approves + checkpoint

**Meta Task (Maintenance System) — optional**
- **Phase ID**: `fileorg-backlog-maintenance`
- **Description**: Build/verify backlog maintenance system (diagnostics, auditor, apply gating, checkpoints, compact summaries).
- **Allowed Paths**: `scripts/`, `src/autopack/`, `README`, `docs/`
- **Apply**: propose-first; apply only for guarded changes.

---

## Design Decisions (Resolved)

The following design decisions have been finalized for FileOrganizer Phase 2:

### ✅ 1. Embedding Model Selection
**Decision**: Use `all-mpnet-base-v2` (Sentence Transformers)
- **Model**: `sentence-transformers/all-mpnet-base-v2`
- **Rationale**:
  - 87-88% accuracy on STS-B benchmark (vs 84-85% for all-MiniLM-L6-v2)
  - 768-dimensional embeddings for better semantic understanding
  - 110M parameters (~420MB) - reasonable for local deployment
  - Proven stability and wide production adoption
  - Free, local inference (no API costs)
- **Alternative**: `all-MiniLM-L6-v2` for resource-constrained environments (5x faster, 80% smaller, 3-4% accuracy trade-off)
- **Benchmark Reference**: MTEB leaderboard December 2025
- **Date Decided**: 2025-12-17

### ✅ 2. Cloud Sync Strategy
**Decision**: Optional Google Drive sync (user choice)
- **Default Mode**: Local-only (SQLite + local file storage)
- **Optional Mode**: Google Drive sync via OAuth2
- **Architecture**: Hybrid with user-selectable sync mode
  - Local cache for offline access
  - Google Drive API v3 for cloud sync
  - Bidirectional sync with last-write-wins conflict resolution
- **Rationale**:
  - Respects user privacy (opt-in only)
  - No forced cloud vendor lock-in
  - Simple local deployment path
  - Future extensibility (Dropbox, OneDrive possible)
- **Implementation Estimate**: ~15,000 tokens, 4-6 hours
- **Date Decided**: 2025-12-17

### ✅ 3. Licensing Model
**Decision**: MIT License
- **Rationale**:
  - Maximize adoption during Beta phase
  - Build community trust and attract contributors
  - Align with Python ecosystem standards (FastAPI, SQLAlchemy, Sentence-Transformers)
  - No barriers to commercial use
  - Can revisit post-1.0 for enterprise features if needed
- **Future Consideration**: Dual licensing possible after 1.0 (MIT core + proprietary enterprise features)
- **Date Decided**: 2025-12-17

### 🔄 4. Language Support Priority
**Decision Pending**: Which languages to support after English?
- **Options**: Spanish, French, German, Chinese, etc.
- **Status**: Defer until Phase 2 core features complete

---

**Document Status**: Ready for Autopack autonomous execution
**Last Updated**: 2025-12-13 (merged maintenance backlog)
**Next Action**: Run Autopack with this task file
**Expected Outcome**: FileOrganizer v1.0 Beta ready in 25-35 autonomous hours

---

## Research System Implementation (Full-Scale)

**Current Status**: Planning Complete (8 chunks ready for execution)
**Next Phase**: Tracer Bullet (Chunk 0) - Feasibility Validation
**Plan Location**: `.autonomous_runs/file-organizer-app-v1/archive/research/active/`
**Documentation**: [UNIFIED_RESEARCH_SYSTEM_IMPLEMENTATION_V2_REVISED.md](.autonomous_runs/file-organizer-app-v1/archive/research/active/UNIFIED_RESEARCH_SYSTEM_IMPLEMENTATION_V2_REVISED.md)

### Overview
Comprehensive research & marketing intelligence system for product discovery and validation. Implements LLM-orchestrated data gathering from GitHub, Reddit, and Web sources with code-based decision frameworks to eliminate hallucinations.

**Total Effort**: 550-690 hours over 15.5-20 weeks (8 autonomous execution chunks)
**Cost Estimate**: $5,740 first year ($4K development review + $1.5K operations + $240 infrastructure)

### Execution Strategy
Implementation split into 8 autonomous chunks with human review gates. Each chunk is 60-100 hours (1-2 weeks for Autopack).

| Chunk | Phase ID | Duration | Focus | Status |
|-------|----------|----------|-------|--------|
| **0** | research-tracer-bullet | 2 weeks | Tracer Bullet (feasibility) | ✅ READY |
| **1A** | research-foundation-orchestrator | 1.5 weeks | Orchestrator + Evidence | ✅ READY |
| **1B** | research-foundation-intent-discovery | 1.5 weeks | Intent + Discovery | ✅ READY |
| **2A** | research-gatherers-social | 2 weeks | GitHub + Reddit Gatherers | ✅ READY |
| **2B** | research-gatherers-web-compilation | 1.5 weeks | Web + Compilation | ✅ READY |
| **3** | research-meta-analysis | 2 weeks | Decision Frameworks | ✅ READY |
| **4** | research-integration | 2 weeks | Autopack Integration | ✅ READY |
| **5** | research-testing-polish | 3 weeks | Testing + Polish | ✅ READY |

### Chunk 0: Tracer Bullet (CRITICAL)
**Phase ID**: `research-tracer-bullet`
**Requirements**: [chunk0-tracer-bullet.yaml](.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk0-tracer-bullet.yaml)

**Goal**: Validate feasibility with minimal end-to-end pipeline before committing to full implementation.

**Success Criteria**:
- 10/10 test topics complete successfully
- Evaluation score ≥7.0/10
- Factuality ≥80%
- Citation validity ≥75%

**If Chunk 0 fails**: ⛔ STOP - Do not proceed. Analyze issues, revise approach or abort project.

**Launch Command**:
```bash
cd c:/dev/Autopack
autopack execute-phase \
  --requirements .autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk0-tracer-bullet.yaml \
  --ci-enabled \
  --quality-gate NEEDS_REVIEW
```

### All Chunks

**Chunk 1A: Foundation - Orchestrator** (60-75 hours)
- **Requirements**: [chunk1a-foundation-orchestrator.yaml](.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk1a-foundation-orchestrator.yaml)
- Production-ready research orchestrator with evidence model
- 5-stage pipeline, validation framework, CLI command
- Dependencies: Chunk 0 COMPLETE

**Chunk 1B: Foundation - Intent & Discovery** (60-75 hours)
- **Requirements**: [chunk1b-foundation-intent-discovery.yaml](.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk1b-foundation-intent-discovery.yaml)
- Intent clarification (3 modes), source discovery, content sanitizer
- Trust tiers configuration
- Dependencies: Chunk 1A COMPLETE

**Chunk 2A: Gatherers - GitHub & Reddit** (70-85 hours)
- **Requirements**: [chunk2a-gatherers-social.yaml](.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk2a-gatherers-social.yaml)
- GitHub repo analyzer, Reddit thread miner
- Rate limiting, error handling, parallel execution
- Dependencies: Chunk 1B COMPLETE

**Chunk 2B: Gatherers - Web & Compilation** (60-75 hours)
- **Requirements**: [chunk2b-gatherers-web-compilation.yaml](.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk2b-gatherers-web-compilation.yaml)
- Web content scraper (robots.txt compliant)
- Compilation agent, gap analysis
- Dependencies: Chunk 2A COMPLETE

**Chunk 3: Meta-Analysis** (80-100 hours)
- **Requirements**: [chunk3-meta-analysis.yaml](.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk3-meta-analysis.yaml)
- 4 decision framework calculators (LLM extract → Python calculate)
- Meta-auditor agent, report generator, APA citations
- Dependencies: Chunk 2B COMPLETE

**Chunk 4: Integration** (80-100 hours)
- **Requirements**: [chunk4-integration.yaml](.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk4-integration.yaml)
- BUILD_HISTORY integration, RESEARCH phase type
- Autonomous mode hooks, review workflow
- Dependencies: Chunk 3 COMPLETE

**Chunk 5: Testing & Polish** (80-100 hours)
- **Requirements**: [chunk5-testing-polish.yaml](.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk5-testing-polish.yaml)
- 100+ unit tests, 20+ integration tests
- Performance testing, documentation, UX polish
- Dependencies: Chunk 4 COMPLETE

### Documentation Index
- **Quick Start**: [README.md](.autonomous_runs/file-organizer-app-v1/archive/research/active/README.md)
- **Execution Strategy**: [ALL_CHUNKS_SUMMARY.md](.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/ALL_CHUNKS_SUMMARY.md)
- **Navigation Index**: [INDEX.md](.autonomous_runs/file-organizer-app-v1/archive/research/active/INDEX.md)

### Prerequisites
- FileOrg Phase 2 stabilized (targeting 2025-12-20)
- GitHub API key configured
- Anthropic API key configured
- Reddit API credentials (optional, for Reddit gatherer)

### Key Features
- **Evidence-Based**: All findings require citations (source_url + extraction_span)
- **No Hallucinations**: Decision frameworks use Python code for calculations (deterministic)
- **Trust Tiers**: Official docs (1.0) → GitHub (0.9) → Reddit (0.7) → Blogs (0.5) → Web (0.3)
- **3 Research Modes**: Autopack, Market, App
- **Human-in-the-Loop**: Review gates between chunks prevent cascading failures

### Risk Mitigation
- Chunk 0 validates feasibility before full investment
- Each chunk has clear success/failure criteria
- Human review required before proceeding to next chunk
- Comprehensive testing in final chunk (Chunk 5)

**Recommended Start Date**: After FileOrg Phase 2 stabilizes (targeting 2025-12-20)

---

**Last Updated**: 2025-12-17 (added Research System Implementation)
