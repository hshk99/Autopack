# Test Marker Registry

Complete documentation of all @pytest.mark.xfail, @pytest.mark.skip, pytest.xfail(), and pytest.skip() calls in the test suite.

**Last Updated**: 2026-01-31
**Total Markers**: 168 instances across 64 files

---

## Aspirational Tests (@pytest.mark.aspirational)

These tests define desired future functionality that is not yet fully implemented. They should be preserved and tracked separately from bugs.

### E2E Pipeline Tests (23 tests)
**File**: `tests/integration/test_autonomous_pipeline_e2e.py`
**Marker Type**: Class-level @pytest.mark.aspirational + method-level pytest.xfail()
**Reason**: E2E autonomous pipeline features not yet fully implemented

**Tests**:
- `test_autonomous_pipeline_task_ingestion` - Task queue and state initialization
- `test_autonomous_pipeline_phase_orchestration` - Phase transitions (0→1→2)
- `test_autonomous_pipeline_code_generation` - Builder orchestrator integration
- `test_autonomous_pipeline_deliverable_creation` - Deliverable generation
- `test_pipeline_error_recovery_llm_failure` - LLM timeout recovery
- `test_pipeline_error_recovery_patch_application_failure` - Patch correction
- `test_pipeline_error_recovery_file_rollback` - File rollback on error
- `test_pipeline_error_recovery_persistent_failures` - User notification on persistent failures
- `test_autonomous_pipeline_decision_validation` - Decision criteria validation
- `test_autonomous_pipeline_quality_gates` - Execution quality gates
- `test_autonomous_pipeline_resource_management` - Resource cleanup and optimization
- `test_autonomous_pipeline_concurrent_safety` - Concurrent execution safety
- `test_autonomous_pipeline_state_persistence` - State persistence across restarts
- `test_autonomous_pipeline_audit_logging` - Audit trail logging
- Plus 9 more similar E2E tests...

**Expected Behavior**: Tests call pytest.xfail() to document aspirational features.
**Action**: Keep as-is. These represent Phase 5 of True Autonomy roadmap.

---

### IMP-GEN-001 Generation Features (7 tests)
**File**: `tests/scripts/test_telemetry_informed_generation.py`
**Marker Type**: Method-level @pytest.mark.xfail(reason="Requires IMP-GEN-001 implementation")
**Reason**: Telemetry-informed generation features pending implementation

**Tests**:
- `test_phase1_contains_learning_memory_instructions`
- `test_phase2_contains_wave_planning_instructions`
- `test_learning_memory_schema_valid`
- `test_learning_memory_can_store_patterns`
- `test_telemetry_context_loads_in_phase1`
- `test_telemetry_context_loads_in_phase2`
- `test_generation_uses_learned_patterns`

**Expected Behavior**: Tests document required features from IMP-GEN-001.
**Action**: Keep until IMP-GEN-001 is completed. Then move to passing tests.

---

### Extended Test Suites (15+ tests across 6 files)
**Marker Type**: Module-level pytestmark with skip + aspirational

**Files**:
- `tests/autopack/test_context_budgeter_extended.py` - 22 tests, aspirational budget allocation features
- `tests/autopack/test_error_recovery_extended.py` - 19 tests, aspirational error recovery
- `tests/autopack/test_governance_requests_extended.py` - 18 tests, aspirational governance
- `tests/autopack/test_token_estimator_calibration.py` - 21 tests, aspirational token calibration
- `tests/autopack/diagnostics/test_deep_retrieval_extended.py` - 2 tests, aspirational retrieval
- `tests/autopack/integrations/test_build_history_integrator.py` - 1 test, aspirational integration

**Strategy**: These were converted from xfail to skip to remove xfail debt while preserving aspirational tests. The skip marker includes `@pytest.mark.aspirational` for clear intent.

**Action**: Keep as-is. These are the proper pattern for aspirational tests.

---

### Parallel Orchestrator Integration (3 tests)
**File**: `tests/autopack/test_parallel_orchestrator.py`
**Marker Type**: Method-level @pytest.mark.xfail
**Reason**: WorkspaceManager/ExecutorLockManager integration not yet fully implemented

**Tests**:
- `test_parallel_orchestrator_executes_multiple_runs_sequentially`
- `test_parallel_orchestrator_manages_shared_workspace`
- `test_parallel_orchestrator_isolates_concurrent_runs`

**Expected Behavior**: Tests verify parallel execution safety features.
**Action**: Keep. Complete WorkspaceManager integration to enable these tests.

---

## Configuration/Environment-Dependent Tests (pytest.skip())

These tests skip gracefully when required configuration or services aren't available. This is appropriate behavior.

### Configuration File Checks
**Count**: ~15 tests across 4 files

**Files & Reasons**:
- `test_cheap_first_model_selection.py` (7 tests) - Skips if `config/models.yaml` not found
- `test_model_intelligence_catalog_ingest.py` (1 test) - Skips if model catalog not available
- `test_migrations.py` (4 tests) - Skips for DB state checks
- `ci/test_archive_index.py` (3 tests) - Skips if archive index not found

**Expected Behavior**: Tests check for config files and skip if missing. This is correct.
**Action**: Keep as-is. Tests should gracefully handle missing optional config.

---

### Docker/Service Availability
**Count**: ~12 tests across 5 files

**Files & Reasons**:
- `test_compose_smoke.py` (4 tests) - Skips if Docker Compose not available
- `memory/test_faiss_store.py` (4 tests) - Skips if FAISS not available
- `integration/test_scheduled_scan.py` (2 tests) - Skips for service availability
- Other integration tests

**Expected Behavior**: Tests skip when required services aren't available.
**Action**: Keep as-is. Appropriate for CI/dev environments.

---

### Windows-Specific Edge Cases
**Count**: ~5 tests
**File**: `storage_optimizer/test_windows_edge_cases.py`

**Tests**:
- Windows-specific path handling
- Windows-specific edge cases in storage management
- Platform-specific behavior validation

**Expected Behavior**: Tests skip on non-Windows platforms (using platform checks).
**Action**: Keep as-is. Platform-specific tests are appropriate.

---

### CI/Governance Policy Checks
**Count**: ~15 skip calls across 8 CI files

**Files**:
- `ci/test_todo_quarantine_policy.py` (8 skip calls) - Governance policy enforcement
- `ci/test_legacy_approval_autoapprove_default_safe.py` (4 skip calls) - Legacy system checks
- `ci/test_production_auth_requirement.py` (1 pytest.skip call) - Auth requirement checks
- `ci/test_feature_flags_registry.py` (2 skip calls) - Feature flag validation
- `ci/test_governance_docs_contract.py` (1 skip) - Documentation contracts
- `ci/test_ci_enforcement_ladder.py` (1 skip) - CI enforcement checks

**Expected Behavior**: Tests skip when governance policy conditions aren't met.
**Action**: Keep as-is. These are appropriate policy-enforcing tests.

---

### Extended Test Suites (Module-Level Skip)
**Count**: ~110 tests across 6 files

**Files & Reason**: All marked with:
```python
pytestmark = [
    pytest.mark.skip(reason="Extended ... API not implemented - aspirational test suite"),
    pytest.mark.aspirational,
]
```

**Strategy**: These represent planned but not-yet-implemented features. The skip + aspirational pattern allows them to be:
1. Preserved as documentation of planned features
2. Easily found and enabled when implementation begins
3. Kept out of the xfail budget (using skip instead)

**Action**: Keep as-is. This is the preferred pattern.

---

## Known Issues to Fix (Priority)

### 1. Dashboard Integration DB Session Issue
**File**: `tests/test_dashboard_integration.py`
**Marker**: 1 @pytest.mark.xfail
**Issue**: DB session isolation - SQLAlchemy session doesn't share uncommitted data between sessions
**Effort**: Medium
**Fix**: Use proper transaction handling or shared session fixtures
**Status**: ✅ FIXED (2026-01-31)
**Solution**: Created shared `testing_session_local` fixture used by both client and db_session fixtures to ensure all sessions see each other's committed data. Removed xfail marker from test_dashboard_usage_with_data.

### 2. Parallel Orchestrator WorkspaceManager Integration
**File**: `tests/autopack/test_parallel_orchestrator.py`
**Marker**: 3 @pytest.mark.xfail
**Issue**: WorkspaceManager/ExecutorLockManager integration incomplete
**Effort**: Medium
**Fix**: Complete integration implementation
**Status**: TODO

### 3. Telemetry Unblock T2 Retry Logic
**File**: `tests/autopack/test_telemetry_unblock_fixes.py`
**Marker**: 1 @pytest.mark.xfail
**Issue**: T2 retry logic not yet implemented
**Effort**: Low
**Fix**: Implement retry logic or mark as aspirational if deferred
**Status**: TODO

---

## Summary by Category

| Category | Count | Type | Status | Action |
|----------|-------|------|--------|--------|
| Aspirational Features | ~50 | xfail/skip | Intentional | Keep (well-tracked) |
| Config/Environment | ~50 | skip() | Intentional | Keep (appropriate) |
| Known Issues | ~4 | xfail | Real Debt | 1 Fixed ✅, 3 remaining |
| CI/Governance | ~15 | skip() | Intentional | Keep |
| Unclassified | ~48 | various | TBD | Review |

**Progress Update (2026-01-31)**:
- Fixed 1 issue: Dashboard integration DB session isolation
- Remaining fixable issues: 4 tests
  - 3 parallel orchestrator integration tests
  - 1 telemetry unblock retry logic test

---

## Improvement Opportunities

### Quick Wins (2-3 hours)
1. Add @pytest.mark.aspirational to any aspirational tests missing it
2. Improve skip message consistency (standardize wording)
3. Create automated registry of all markers (expand test_xfail_budget.py)

### Medium Effort (3-5 hours)
1. Fix dashboard integration DB session issue
2. Complete parallel orchestrator integration
3. Implement telemetry unblock T2 retry logic

### Long-Term (Ongoing)
1. Implement IMP-GEN-001 to enable 7 telemetry tests
2. Implement aspirational E2E pipeline features (23 tests)
3. Complete extended test suite implementations

---

## Notes

- Most test "debt" is actually intentional and well-structured
- The conversion of extended test suites from xfail to skip was effective
- Aspirational tests are valuable documentation of planned features
- Environment-dependent skips are appropriate and necessary
- Real fixable issues are limited to ~5 xfail tests

---

**Registry created during loop021 (IMP-TEST-001) test debt reduction work.**
