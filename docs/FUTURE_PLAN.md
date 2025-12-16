# What's Left to Build - Autopack Project Plans

**Last Updated**: 2025-12-16
**Active Projects**:
1. Research System (Citation Validity Improvement)
2. FileOrganizer Phase 2 (Beta Release)

This file contains tasks in Autopack format for autonomous execution.

---

## ACTIVE: Research System - Citation Validity Improvement

**Current Status**: Phase 0 ✅ | Phase 1 ✅ | BUILD-039 ✅ | Restoration PENDING
**Citation Validity**: 59.3% baseline (target: ≥80%)
**Plan Version**: v2.2
**Reference**: [docs/RESEARCH_CITATION_FIX_PLAN.md](RESEARCH_CITATION_FIX_PLAN.md)

### Context
The research system citation validity improvement project is implementing fixes to increase citation accuracy from 59.3% to ≥80%. Foundation work and Phase 1 fix are complete. Remaining work involves restoring github_gatherer and evaluation modules, then running evaluation tests.

**Completed Work**:
- ✅ Phase 0: Foundation modules (text_normalization.py, verification.py) - 54/54 tests passing
- ✅ Phase 1: Relax numeric verification (validators.py created with fix) - 20/20 tests passing
- ✅ BUILD-039: JSON repair for structured_edit mode (enables autonomous recovery)

**First Restoration Run Results** (2025-12-16, v2.1):
- Duration: 20 minutes
- Failures: 12/25 budget consumed
- Root cause: JSON parsing errors in structured_edit mode (fixed by BUILD-039)
- Status: FATAL (marked for retry with BUILD-039 active)

### Task R1: Restore GitHub Gatherer ✅ PARTIALLY COMPLETE / 🔄 NEEDS COMPLETION
**Phase ID**: `restore_github_gatherer_v2`
**Category**: restoration
**Complexity**: medium
**Description**: Create src/autopack/research/gatherers/github_gatherer.py with GitHub API integration, README fetching, and LLM-based finding extraction.

**Acceptance Criteria**:
- [ ] File src/autopack/research/gatherers/github_gatherer.py exists
- [ ] GitHubGatherer class with discover_repositories(), fetch_readme(), extract_findings() methods
- [ ] LLM extraction prompt emphasizes CHARACTER-FOR-CHARACTER quotes in extraction_span
- [ ] JSON parsing handles markdown code blocks
- [ ] File imports successfully (no syntax errors)

**Dependencies**: None (standalone file creation)
**Estimated Tokens**: 8,000
**Status**: QUEUED (ready for v2.2 run with BUILD-039 active)
**Previous Attempt**: Failed 5 times with "Unterminated string" JSON errors (BUILD-039 now fixes this)

### Task R2: Restore Evaluation Module
**Phase ID**: `restore_evaluation_module_v2`
**Category**: restoration
**Complexity**: medium
**Description**: Create src/autopack/research/evaluation/ module with CitationValidityEvaluator class that uses validators.CitationValidator.

**Acceptance Criteria**:
- [ ] Directory src/autopack/research/evaluation/ exists
- [ ] File citation_validator.py created with CitationValidityEvaluator
- [ ] Imports validators.CitationValidator successfully
- [ ] evaluate_summary() method implemented (tracks valid/invalid counts, failure reasons)
- [ ] Returns structured results: total, valid, invalid, validity_percentage, failure_breakdown

**Dependencies**: Task R1 (github_gatherer must exist)
**Estimated Tokens**: 6,000
**Status**: QUEUED (blocked by R1)
**Previous Attempt**: Builder succeeded but Quality Gate blocked (pytest exit code 2 due to R1 failure cascade)

### Task R3: Run Phase 1 Evaluation
**Phase ID**: `run_phase1_evaluation_v2`
**Category**: test
**Complexity**: low
**Description**: Execute evaluation script to measure citation validity after Phase 1 fix. Test on 3-5 sample repositories.

**Acceptance Criteria**:
- [ ] Evaluation script runs successfully
- [ ] 3-5 repositories tested (GitHub search for "machine learning" or similar)
- [ ] Citation validity measured and documented
- [ ] Results saved to .autonomous_runs/research-citation-fix/phase1_evaluation_results.json
- [ ] Comparison to 59.3% baseline included
- [ ] Decision: If ≥80%, mark SUCCESS. If <80%, proceed to R4.

**Dependencies**: Tasks R1, R2
**Estimated Tokens**: 5,000
**Expected Impact**: Citation validity: 59.3% → 74-79%
**Status**: QUEUED (blocked by R1, R2)

### Task R4: Enhanced Text Normalization (CONDITIONAL)
**Phase ID**: `phase2_enhanced_normalization_v2`
**Category**: feature
**Complexity**: medium
**Description**: IF Task R3 evaluation shows <80% validity, integrate text_normalization.normalize_text() into validators.py _normalize_text() method.

**Acceptance Criteria**:
- [ ] CONDITIONAL: Execute only if R3 shows <80%
- [ ] validators.py imports from autopack.text_normalization
- [ ] _normalize_text() uses normalize_text(text, strip_markdown=True)
- [ ] HTML entity handling verified
- [ ] Unicode normalization verified
- [ ] Markdown artifact stripping verified
- [ ] All tests pass (20/20 in test_research_validators.py)

**Dependencies**: Task R3 results
**Estimated Tokens**: 6,000
**Expected Impact**: +5-10% citation validity (74-79% → 79-89%)
**Status**: CONDITIONAL

### Task R5: Final Evaluation (CONDITIONAL)
**Phase ID**: `run_phase2_evaluation_v2`
**Category**: test
**Complexity**: low
**Description**: IF Task R4 was applied, re-run evaluation to measure final citation validity.

**Acceptance Criteria**:
- [ ] CONDITIONAL: Execute only if R4 was applied
- [ ] Evaluation runs successfully on same test repositories
- [ ] Final citation validity measured
- [ ] Results compared to Phase 0 (59.3%) and Phase 1 baselines
- [ ] Decision documented: SUCCESS (≥80%) or needs Phase 3

**Dependencies**: Task R4
**Estimated Tokens**: 3,000
**Expected Impact**: Final validation of ≥80% target
**Status**: CONDITIONAL

### Infrastructure Fixes Completed
**BUILD-039** (2025-12-16T18:45) - JSON Repair for Structured Edit Mode
- ✅ Added JsonRepairHelper to structured_edit mode parser
- ✅ Enables autonomous recovery from malformed JSON
- ✅ Addresses 7 out of 12 failures from first restoration run
- ✅ Completes auto-recovery pipeline: BUILD-037 → BUILD-038 → BUILD-039
- **Impact**: Next restoration run should succeed with JSON repair active

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

## Items Requiring Manual Design Input

The following require **user decisions** before Autopack can build:

### 1. Embedding Model Selection
**Decision Needed**: Continue with OpenAI embeddings or switch to local model?
- **Option A**: Keep OpenAI (current) - paid API, high quality
- **Option B**: Switch to Sentence Transformers - free, local, slightly lower quality

### 2. Cloud Sync Strategy
**Decision Needed**: Should FileOrganizer support cloud sync?
- **Option A**: No cloud (current) - local only, simple
- **Option B**: Optional cloud sync - S3/Google Drive integration

### 3. Licensing Model
**Decision Needed**: Open source or commercial?
- **Option A**: Fully open source (MIT)
- **Option B**: Dual license (open core + paid features)

### 4. Language Support Priority
**Decision Needed**: Which languages to support after English?
- **Options**: Spanish, French, German, Chinese, etc.

---

**Document Status**: Ready for Autopack autonomous execution
**Last Updated**: 2025-12-13 (merged maintenance backlog)
**Next Action**: Run Autopack with this task file
**Expected Outcome**: FileOrganizer v1.0 Beta ready in 25-35 autonomous hours
