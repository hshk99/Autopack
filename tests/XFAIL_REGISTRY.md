# XFail/Skip Test Registry

**Date**: 2026-02-02
**Total Marked Tests**: 39
**Last Audit**: IMP-TEST-007 Wave 6

## Summary by Category

| Category | Count | Status |
|----------|-------|--------|
| Known Bug (impl) | 12 | Need Fix |
| Unimplemented Feature | 7 | Pending IMP |
| Flaky Tests | 3 | Need Fix |
| Invalid/API Change | 7 | Need Update |
| Environment Dependency | 8 | OK |
| Platform-Specific | 2 | OK |
| **TOTAL** | **39** | |

---

## 1. Known Bug - Implementation Issues (12)

Tests skipped due to verified implementation bugs that need separate PRs to fix.

### 1.1 Dictionary/Content Field Mismatch
- **File**: `tests/test_format_retrieved_context_caps.py:32`
- **Test**: `test_format_retrieved_context_caps`
- **Status**: `skip`
- **Issue**: `format_retrieved_context` expects 'content_preview' in payload, but test passes 'content'
- **Category**: Known Bug (impl)
- **Action**: Fix in separate PR - update function signature or test data
- **Linked IMP**: Related to SCHEMA improvements

### 1.2 Model Runtime Stats - Percentile Calculation
- **File**: `tests/test_model_intelligence_runtime_stats.py:191`
- **Test**: `test_compute_token_percentiles_accuracy`
- **Status**: `skip`
- **Issue**: `compute_token_percentiles` returns wrong p90 value (assert 11200 == 12000)
- **Category**: Known Bug (impl)
- **Action**: Investigate percentile calculation logic in separate PR
- **Root Cause**: Percentile computation error in statistics module

### 1.3 Model Runtime Stats - Duplicate Creation
- **File**: `tests/test_model_intelligence_runtime_stats.py:215`
- **Test**: `test_compute_runtime_stats_idempotent`
- **Status**: `skip`
- **Issue**: `compute_runtime_stats` creates duplicate stats instead of being idempotent (assert 2 == 0)
- **Category**: Known Bug (impl)
- **Action**: Implement upsert logic in separate PR
- **Root Cause**: Missing idempotency check, same pattern as ingest_pricing_updates

### 1.4 Model Intelligence - Catalog Filtering
- **File**: `tests/test_model_intelligence_recommender.py:141`
- **Test**: `test_generate_candidates_single_provider`
- **Status**: `skip`
- **Issue**: `generate_candidates` not finding expected models in catalog (assert 'glm-4.7' in [])
- **Category**: Known Bug (impl)
- **Action**: Investigate catalog filtering logic in separate PR
- **Root Cause**: Catalog search/filter not working correctly

### 1.5 Model Intelligence - Cross-Provider Candidates
- **File**: `tests/test_model_intelligence_recommender.py:156`
- **Test**: `test_generate_candidates_multi_provider`
- **Status**: `skip`
- **Issue**: `generate_candidates` returns empty list when should return cross-provider candidates (assert 0 > 0)
- **Category**: Known Bug (impl)
- **Action**: Investigate catalog filtering logic in separate PR
- **Root Cause**: Cross-provider filtering broken

### 1.6 Model Intelligence - Pricing Ingestion Duplicates
- **File**: `tests/test_model_intelligence_catalog_ingest.py:144`
- **Test**: `test_ingest_pricing_updates_existing`
- **Status**: `skip`
- **Issue**: `ingest_pricing` creates duplicate records instead of updating (assert 3 == 0)
- **Category**: Known Bug (impl)
- **Action**: Implement proper upsert/update logic in separate PR
- **Root Cause**: Missing duplicate detection or update logic

### 1.7 SOT Telemetry - Foreign Key Constraints
- **File**: `tests/test_sot_telemetry_fields.py:247`
- **Test**: `test_foreign_key_constraint_violation`
- **Status**: `skip`
- **Issue**: SQLite in-memory DB doesn't enforce FK constraints by default
- **Category**: Known Bug (impl)
- **Action**: Add `PRAGMA foreign_keys=ON` in test setup in separate PR
- **Root Cause**: SQLite FK constraints not enabled by default

### 1.8 Storage Executor - Freed Bytes Calculation
- **File**: `tests/test_storage_executor.py:204`
- **Test**: `test_approving_content_frees_bytes`
- **Status**: `skip`
- **Issue**: Test bug - file contains 16 bytes but expects freed_bytes==100. Implementation correctly reports actual freed bytes.
- **Category**: Test Bug (not impl)
- **Action**: Fix test to match implementation behavior - DB size should match actual file size
- **Root Cause**: Test expectation mismatch

### 1.9 Tidy Entry ID - Archive File Processing
- **File**: `tests/test_tidy_entry_id_stability.py:142`
- **Test**: `test_explicit_id_preferred_over_generated`
- **Status**: `skip`
- **Issue**: `_process_archive_files()` returns 0 entries when should find 1
- **Category**: Known Bug (impl)
- **Action**: Debug archive file processing logic in separate PR
- **Root Cause**: Archive processing not finding files

### 1.10 Tidy Entry ID - Low Classification Confidence
- **File**: `tests/test_tidy_entry_id_stability.py:170`
- **Test**: `test_archive_classified_as_unsorted`
- **Status**: `skip`
- **Issue**: `_process_archive_files()` returns 0 entries when should find 1. File goes to UNSORTED due to low classification confidence.
- **Category**: Known Bug (impl)
- **Action**: Debug archive processing and classification confidence in separate PR
- **Root Cause**: Same as #1.9 - archive processing issue

### 1.11 Intention Anchor - Duplicate Methods
- **File**: `tests/autopack/test_intention_anchor_prompt_wiring.py:162`
- **Test**: `test_intention_anchors_in_user_prompt`
- **Status**: `skip`
- **Issue**: AnthropicBuilderClient has duplicate `_build_user_prompt` methods
- **Category**: Known Bug (impl - pre-existing)
- **Action**: Deduplicate methods and fix implementation in separate PR
- **Root Cause**: Code duplication in AnthropicBuilderClient

### 1.12 Tidy Safety - API Change
- **File**: `tests/test_tidy_safety.py:307`
- **Test**: `test_autonomous_executor_integration`
- **Status**: `skip`
- **Issue**: AutonomousExecutor.__init__() no longer accepts 'project_id' parameter
- **Category**: API Change (test needs update)
- **Action**: Update test to match new executor initialization API
- **Root Cause**: Executor API refactoring

---

## 2. Unimplemented Features (7)

Tests for features in active development or planned for future waves.

### 2.1-2.7 Telemetry-Informed Generation Tests
- **File**: `tests/scripts/test_telemetry_informed_generation.py:34-105`
- **Tests**: 7 tests (all with same reason)
  - `test_phase1_contains_learning_memory_instructions` (line 34)
  - `test_phase2_contains_wave_planning_instructions` (line 44)
  - `test_trigger_script_exists` (line 75)
  - `test_trigger_script_has_telemetry_flag` (line 81)
  - `test_trigger_script_references_aggregator` (line 89)
  - `test_trigger_script_references_learning_memory` (line 97)
  - `test_trigger_script_powershell_syntax_valid` (line 105)
- **Status**: `xfail` + `skipif` (PowerShell check)
- **Reason**: Requires IMP-GEN-001 implementation
- **Category**: Unimplemented Feature
- **Action**: Remove xfail markers when IMP-GEN-001 is complete
- **Linked IMP**: IMP-GEN-001 (Wave 2-3) - Generative AI telemetry integration

---

## 3. Flaky Tests (3)

Tests that fail intermittently due to race conditions or timing issues.

### 3.1 Parallel Runs - Lock Manager Race Condition
- **File**: `tests/integration/test_parallel_runs.py:339`
- **Test**: `test_multiple_parallel_runs_with_shared_resources`
- **Status**: `skip`
- **Reason**: Race condition in CI parallel environments where all threads acquire lock before coordination completes
- **Category**: Flaky Test
- **Action**: Fix ExecutorLockManager race condition logic in separate PR
- **Root Cause**: Lock coordination timing issue in multi-threaded execution
- **Recommendation**: Run serially with `pytest -n0` for now

### 3.2 Parallel Orchestrator - WorkspaceManager Integration (Test 1)
- **File**: `tests/autopack/test_parallel_orchestrator.py:134`
- **Test**: `test_orchestrate_concurrent_projects`
- **Status**: `xfail` (strict=False)
- **Reason**: Aspirational test - WorkspaceManager/ExecutorLockManager integration not fully implemented
- **Category**: Flaky/Unimplemented
- **Action**: Complete WorkspaceManager integration, then remove xfail
- **Root Cause**: Incomplete integration between components

### 3.3 Parallel Orchestrator - WorkspaceManager Integration (Test 2)
- **File**: `tests/autopack/test_parallel_orchestrator.py:175`
- **Test**: `test_orchestrate_with_resource_limits`
- **Status**: `xfail` (strict=False)
- **Reason**: Aspirational test - WorkspaceManager/ExecutorLockManager integration not fully implemented
- **Category**: Flaky/Unimplemented
- **Action**: Complete WorkspaceManager integration, then remove xfail
- **Root Cause**: Incomplete integration between components

### 3.4 Parallel Orchestrator - WorkspaceManager Integration (Test 3)
- **File**: `tests/autopack/test_parallel_orchestrator.py:569`
- **Test**: `test_orchestrate_adaptive_parallelism`
- **Status**: `xfail` (strict=False)
- **Reason**: Aspirational test - WorkspaceManager/ExecutorLockManager integration not fully implemented
- **Category**: Flaky/Unimplemented
- **Action**: Complete WorkspaceManager integration, then remove xfail
- **Root Cause**: Incomplete integration between components

### 3.5 Telemetry Unblock - T2 Retry Logic
- **File**: `tests/autopack/test_telemetry_unblock_fixes.py:151`
- **Test**: `test_empty_files_retry_once`
- **Status**: `xfail`
- **Reason**: T2 retry logic not yet implemented - aspirational test
- **Category**: Unimplemented/Aspirational
- **Action**: Implement T2 retry logic, then remove xfail
- **Root Cause**: Feature not yet implemented

### 3.6 Phase Approach Reviser - xdist Parallel Execution (Test 1)
- **File**: `tests/executor/test_phase_approach_reviser.py:278`
- **Test**: `test_approach_revision_integrates_feedback`
- **Status**: `skip`
- **Reason**: Fixed mock state races with `.clear()` but still incompatible with pytest-xdist parallel execution
- **Category**: Flaky Test
- **Action**: Either fix for xdist or document requirement to run with `pytest -n0`
- **Root Cause**: Mock state management not thread-safe
- **Workaround**: Run with `pytest -n0` (no xdist parallelism)

### 3.7 Phase Approach Reviser - xdist Parallel Execution (Test 2)
- **File**: `tests/executor/test_phase_approach_reviser.py:324`
- **Test**: `test_approach_revision_handles_streaming`
- **Status**: `skip`
- **Reason**: Fixed mock state races with `.clear()` but still incompatible with pytest-xdist parallel execution
- **Category**: Flaky Test
- **Action**: Either fix for xdist or document requirement to run with `pytest -n0`
- **Root Cause**: Mock state management not thread-safe
- **Workaround**: Run with `pytest -n0` (no xdist parallelism)

---

## 4. Invalid/API Change (7)

Tests that are broken due to code refactoring or API changes and need updates.

### 4.1 WizTree Scanner - Windows-Specific Test
- **File**: `tests/test_wiztree_scanner.py:27`
- **Test**: `test_get_wiztree_path_windows`
- **Status**: `skip`
- **Reason**: Windows-specific test - WizTree is Windows-only. Test expects Windows paths that don't exist on Linux CI.
- **Category**: Platform-Specific/Invalid
- **Action**: Skip on non-Windows platforms properly with skipif
- **Root Cause**: Test hardcodes Windows path

### 4.2 WizTree Scanner - API Change (Test 1)
- **File**: `tests/test_wiztree_scanner.py:52`
- **Test**: `test_wiztree_scanner_scan_drive`
- **Status**: `skip`
- **Reason**: StorageScanner object no longer has 'scan_drive' attribute - API has changed
- **Category**: API Change
- **Action**: Update test to use new scanner API
- **Root Cause**: Scanner interface refactored

### 4.3 WizTree Scanner - API Change (Test 2)
- **File**: `tests/test_wiztree_scanner.py:113`
- **Test**: `test_wiztree_scanner_with_mocked_output`
- **Status**: `skip`
- **Reason**: StorageScanner object no longer has 'scan_drive' attribute
- **Category**: API Change
- **Action**: Update test to use new scanner API
- **Root Cause**: Scanner interface refactored

### 4.4 WizTree Scanner - Module Export Change
- **File**: `tests/test_wiztree_scanner.py:250`
- **Test**: `test_wiztree_scanner_factory`
- **Status**: `skip`
- **Reason**: Module 'autopack.storage_optimizer.scanner' no longer exports 'WizTreeScanner'
- **Category**: API Change
- **Action**: Update import or factory function in test
- **Root Cause**: Module exports changed

### 4.5 WizTree Scanner - Module Export Change (Test 2)
- **File**: `tests/test_wiztree_scanner.py:268`
- **Test**: `test_wiztree_scanner_in_factory_list`
- **Status**: `skip`
- **Reason**: Module 'autopack.storage_optimizer.scanner' no longer exports 'WizTreeScanner'
- **Category**: API Change
- **Action**: Update import or factory function in test
- **Root Cause**: Module exports changed

### 4.6 WizTree Scanner - Windows Path Existence
- **File**: `tests/integration/test_scheduled_scan.py:254`
- **Test**: `test_scheduled_scan_job_creation`
- **Status**: `skipif`
- **Reason**: WizTree not installed (checks for C:/Program Files/WizTree/wiztree64.exe)
- **Category**: Environment Dependency
- **Action**: OK - proper environment check

### 4.7 WizTree Scanner - Windows Path Existence (Test 2)
- **File**: `tests/integration/test_scheduled_scan.py:290`
- **Test**: `test_scheduled_scan_execution`
- **Status**: `skipif`
- **Reason**: WizTree not installed
- **Category**: Environment Dependency
- **Action**: OK - proper environment check

---

## 5. Environment Dependency (8)

Tests that require specific external tools/services and are correctly skipped.

### 5.1 FAISS Vector Store Tests (4)
- **Files**: `tests/memory/test_faiss_store.py` (lines 568, 618, 640, 658)
- **Tests**:
  - `test_faiss_index_loaded_from_file` (568)
  - `test_faiss_index_loaded_from_npz` (618)
  - `test_faiss_batch_search` (640)
  - `test_faiss_index_persisted` (658)
- **Status**: `skipif (not FAISS_AVAILABLE)`
- **Reason**: FAISS library not installed
- **Category**: Environment Dependency
- **Action**: OK - proper dependency check

### 5.2 Qdrant Integration Test
- **File**: `tests/autopack/memory/test_memory_service_qdrant_integration.py:353`
- **Test**: `test_memory_service_with_qdrant_backend`
- **Status**: `skipif (not QDRANT_AVAILABLE_FOR_TESTS)`
- **Reason**: Qdrant not available
- **Category**: Environment Dependency
- **Action**: OK - proper environment check

### 5.3 Database Migration Tests (4)
- **File**: `tests/test_migrations.py` (lines 91, 101, 110, 169)
- **Tests**:
  - `test_downgrade_command` (91)
  - `test_current_command` (101)
  - `test_show_command` (110)
  - `test_migration_integration` (169)
- **Status**: `skipif (CI == "true")`
- **Reason**: Skip Alembic tests in CI, use run_migrations() instead for CI
- **Category**: Environment Dependency
- **Action**: OK - proper CI/local environment separation

### 5.4 Checkpoint Logger Database Test
- **File**: `tests/storage/test_checkpoint_logger.py:174`
- **Test**: `test_checkpoint_database_integration`
- **Status**: `skipif` (DB file not found)
- **Reason**: Database not available for integration test
- **Category**: Environment Dependency
- **Action**: OK - proper environment check

### 5.5 Second Opinion Integration - API Key
- **File**: `tests/autopack/diagnostics/test_second_opinion_integration.py:213`
- **Test**: `test_real_api_integration`
- **Status**: `skipif (not ANTHROPIC_API_KEY)`
- **Reason**: ANTHROPIC_API_KEY not set
- **Category**: Environment Dependency
- **Action**: OK - proper API key check

### 5.6 Steam Detector Tests (2)
- **Files**: `tests/storage/test_steam_detector.py` (lines 332, 349)
- **Tests**:
  - `test_steam_registry_reading` (332)
  - `test_steam_library_folders_parsing` (349)
- **Status**: `skipif` (Steam not installed)
- **Reason**: Steam not installed (checks for c:/program files (x86)/steam)
- **Category**: Environment Dependency
- **Action**: OK - proper environment check

---

## 6. Platform-Specific (2)

Tests that only run on specific platforms.

### 6.1 Unix Command Tests (6)
- **File**: `tests/autonomy/test_timeout_cleanup.py` (lines 29, 40, 61, 77, 86, 131)
- **Tests**:
  - `test_timeout_returns_error_result` (29)
  - `test_timeout_kills_process_tree` (40)
  - `test_timeout_exception_is_caught` (61)
  - `test_command_error_captured` (77)
  - `test_timeout_logging` (86)
  - `test_unix_pipes_shell_false_mode` (131)
- **Status**: `skipif (platform == "win32")`
- **Reason**: Unix commands (sleep, ls) not available on Windows
- **Category**: Platform-Specific
- **Action**: OK - proper platform check

### 6.2 PowerShell Syntax Test
- **File**: `tests/scripts/test_telemetry_informed_generation.py:106`
- **Test**: `test_trigger_script_powershell_syntax_valid`
- **Status**: `skipif` (platform != "win32")
- **Reason**: PowerShell syntax check only runs on Windows
- **Category**: Platform-Specific
- **Action**: OK - proper platform check

---

## Action Items for Cleanup

### Immediate (Remove/Update Invalid Markers)
1. **WizTree Scanner API Tests** - Update to new scanner API or mark for removal
   - `test_wiztree_scanner.py:52, 113, 250, 268`

2. **Tidy Safety API Change** - Update to new AutonomousExecutor API
   - `test_tidy_safety.py:307`

### Short-term (Add Proper Issues & Links)
3. Add GitHub issue numbers to all Known Bug markers
4. Add IMP tracking to Unimplemented Feature markers
5. Document expected completion dates

### Medium-term (Fix Implementation)
6. Fix storage executor test expectation (test bug, not impl)
7. Fix percentile calculation bug
8. Fix runtime stats duplication bug
9. Fix catalog filtering bugs
10. Fix pricing ingestion duplication

### Longer-term (Feature Completion)
11. Complete IMP-GEN-001 (telemetry generation)
12. Complete WorkspaceManager integration
13. Implement T2 retry logic

---

## Statistics

- **Total Marked Tests**: 39
- **Skip Markers**: 20
- **XFail Markers**: 10
- **SkipIf Markers**: 9

### By Status
- **OK (Environment/Platform)**: 10 tests - no action needed
- **Need Update**: 7 tests - test or API needs updating
- **Need Fix**: 12 tests - implementation bugs
- **Need Feature**: 7 tests - waiting on IMP completion
- **Flaky**: 3 tests - race conditions to fix

### By Priority
1. **High**: Implementation bugs (12 tests) - blocking functionality
2. **Medium**: Flaky tests (3 tests) - CI reliability
3. **Low**: Unimplemented features (7 tests) - waiting on dependent work
4. **Low**: Invalid tests (7 tests) - API/test updates
5. **None**: Environment checks (8 tests) - correct as-is
6. **None**: Platform checks (2 tests) - correct as-is

---

## Recommendations

1. **Reduce Technical Debt**: Fix the 12 known bugs systematically
2. **Improve CI Reliability**: Fix flaky tests by addressing race conditions
3. **Clear Blockers**: Complete IMP-GEN-001 to unblock 7 telemetry tests
4. **Update Tests**: Modernize API-changed tests to match refactored code
5. **Documentation**: Add issue links to all markers for traceability

---

**Next Review Date**: After IMP-GEN-001 and bug fixes complete
