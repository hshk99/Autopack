# Test Suite Stabilization Plan

**Status**: ANALYSIS COMPLETE - Awaiting User Direction
**Date**: 2025-12-31
**Goal**: Reach "green-by-default CI" - make core test suite pass reliably

---

## Current State

**Test Results**:
- **1439 tests passing** (core functionality)
- **105 tests failing** across 14 files
- **34 tests skipped**
- **360+ tests quarantined** (research subsystem)

**Problem**: 105 pre-existing failures mean the repo cannot reliably detect regressions in CI.

---

## Analysis of 105 Failures

### Category 1: API Drift - Extended Test Suites (85+ failures)

These tests expect APIs that were designed but never fully implemented:

**Files**:
- `tests/autopack/test_context_budgeter_extended.py` (24 tests)
  - Expects: `ContextBudgeter` class
  - Reality: Only `BudgetSelection` class + functions exist

- `tests/autopack/test_error_recovery_extended.py` (24 tests)
  - Expects: Retry/backoff/circuit breaker classes
  - Reality: We have `CircuitBreaker` but not all the retry mechanisms these tests expect

- `tests/autopack/test_governance_requests_extended.py` (20+ tests)
  - Expects: Governance/approval workflow classes
  - Reality: Partial implementation or design-only

- `tests/autopack/test_telemetry_unblock_fixes.py` (2 tests)
- `tests/autopack/test_telemetry_utils.py` (1 test)
- `tests/autopack/test_token_estimator_calibration.py` (24 tests)
  - Expects: Token estimator calibration APIs
  - Reality: Basic token estimation exists, not full calibration system

**Root Cause**: These appear to be "aspirational" test suites written for features that were planned but not fully built.

**Recommendation**:
- **Option A**: Quarantine with `@pytest.mark.extended` marker + xfail
- **Option B**: Delete these tests (they test non-existent code)
- **Option C**: Implement the missing APIs (high effort, unclear ROI)

### Category 2: Integration Test Failures (10+ failures)

**Files**:
- `tests/autopack/diagnostics/test_package_detector_integration.py` (1 test)
  - Issue: Circular includes test

- `tests/autopack/diagnostics/test_retrieval_triggers.py` (1 test)
  - Issue: Root cause investigation trigger logic

- `tests/autopack/test_parallel_orchestrator.py` (unknown count)
  - Issue: Parallel execution behavior

- `tests/integration/test_parallel_runs.py` (1 test)
  - Issue: Test baseline tracker artifacts

**Root Cause**: Integration tests may have environmental dependencies or timing issues.

**Recommendation**: Investigate each, fix if simple, otherwise convert to `xfail` with issue tracking.

### Category 3: Simple Assertion Mismatches (4 failures)

**Files**:
- `tests/test_api.py::test_health_check` (1 test)
  - **Issue**: Health endpoint now returns more fields than test expects
  - **Fix**: Update assertion to check subset or exact new schema
  - **Effort**: 5 minutes

- `tests/test_dashboard_integration.py::test_dashboard_usage_with_data` (1 test)
  - **Issue**: Usage data not persisting (expects 3800 tokens, gets 0)
  - **Fix**: Investigate data persistence, may be database setup issue
  - **Effort**: 30-60 minutes

- `tests/test_phase6_p3_migration.py::test_migration_idempotence` (1 test)
  - **Issue**: Permission error or migration state issue
  - **Fix**: Check migration script behavior
  - **Effort**: 30 minutes

- `tests/test_tracer_bullet.py::TestWebScraper::test_rate_limiting` (1 test)
  - **Issue**: Rate limiting not working (expects ≥0.5s delay, gets 0.0s)
  - **Fix**: Check rate limiter implementation or test mock
  - **Effort**: 15-30 minutes

**Recommendation**: Fix these 4 tests - they're testing real production code.

---

## Proposed Strategy

### Phase 1: Quick Wins (Est. 2-3 hours)

1. **Fix 4 simple assertion tests** ✅ HIGH PRIORITY
   - test_api.py health check
   - test_dashboard_integration.py usage data
   - test_phase6_p3_migration.py migration
   - test_tracer_bullet.py rate limiting

2. **Quarantine extended test suites with markers**
   - Add `@pytest.mark.extended` to all *_extended.py test files
   - Add `@pytest.mark.xfail(strict=False, reason="API not implemented")` to failing tests
   - Update pytest.ini to deselect extended tests by default

3. **Investigate integration test failures** (fix or xfail each)
   - test_package_detector_integration.py
   - test_retrieval_triggers.py
   - test_parallel_orchestrator.py
   - integration/test_parallel_runs.py

**Expected Outcome**: Core CI green (0-10 failures max)

### Phase 2: Marker-Based Quarantine (Est. 1-2 hours)

1. **Remove pytest.ini ignores** for research tests
2. **Add markers** to all research tests:
   ```python
   @pytest.mark.research
   @pytest.mark.xfail(strict=False, reason="Research subsystem has API drift - see RESEARCH_QUARANTINE.md")
   ```
3. **Update CI** to run two jobs:
   - `pytest -m "not research and not extended"` (must pass)
   - `pytest -m "research or extended"` (allowed to fail, but reported)

**Expected Outcome**: No hidden failures, all tests run and reported

### Phase 3: Restore High-Signal Tests (Est. 2-4 hours)

1. **Restore and fix**:
   - `tests/autopack/integrations/test_build_history_integrator.py`
   - `tests/autopack/memory/test_memory_service_extended.py`

2. **Why these matter**:
   - build_history_integrator: Tests SOT integrity (aligns with "self-improving loop")
   - memory_service_extended: Tests intention memory backend (aligns with "project intention memory")

**Expected Outcome**: High-signal observability tests passing

---

## Risk Assessment

### Low Risk
- Fixing simple assertion tests (Category 3)
- Adding markers to extended tests
- Updating pytest.ini to use markers instead of ignores

### Medium Risk
- Investigating and fixing integration tests
- Restoring build_history_integrator and memory_service_extended

### High Risk
- Implementing missing APIs for extended test suites (not recommended)
- Deleting extended test suites without stakeholder approval

---

## Recommendations

### Immediate Action (User Decision Required)

**Question 1**: Extended test suites (85+ failing tests)
- **Option A**: Quarantine with `@pytest.mark.extended` + xfail (keeps tests, marks as expected failures)
- **Option B**: Delete entirely (removes dead code)
- **Option C**: Defer decision, keep in current quarantine state

**Question 2**: Time budget
- **Full fix (Phases 1-3)**: 5-9 hours of focused work
- **Minimal fix (Phase 1 only)**: 2-3 hours, gets core CI mostly green
- **Defer**: Document plan, execute in next session

**Question 3**: CI strategy
- **Two-job CI** (recommended): Core must-pass + Extended/Research reported-only
- **Single-job CI**: Only run non-quarantined tests (hides failures)

---

## Next Steps

**If user approves Phase 1**:
1. Fix 4 simple assertion tests
2. Add xfail markers to extended test suites
3. Investigate and triage integration tests
4. Commit and verify core CI green

**If user requests full execution**:
1. Execute all three phases
2. Create CI configuration files for two-job strategy
3. Update documentation with new test organization

**If user defers**:
1. Push current work (import path fixes)
2. Document this plan in repo
3. Wait for next instruction

---

## Current Commit State

✅ **Committed**: Import path fixes (53 files, `src.autopack` → `autopack`)
⏳ **Pending**: 105 failures still present, awaiting strategy approval

