# BUILD-127/128/129 Manual Implementation Plan

**Date**: 2025-12-23
**Type**: Manual Implementation (All Builds)
**Reason**: Complex architectural changes, high risk, requires human judgment
**Prerequisites**: BUILD-130 Prevention Infrastructure (COMPLETE)

---

## Executive Summary

Manual implementation of three interconnected builds:
- **BUILD-127**: Self-Healing Governance (3 phases, ~1200 lines)
- **BUILD-128**: Already implemented (Deliverables-Aware Manifest)
- **BUILD-129**: Token Budget Intelligence (3 phases, ~1050 lines)
- **TOKEN_BUDGET_ANALYSIS_REVISED**: GPT-5.2 validated strategy

**Total Scope**: ~2250 lines of new code, 8 new files, 15+ modified files, 3 database migrations

**Timeline**: 4-6 hours for BUILD-127 Phase 1, 6-8 hours total for all phases

---

## Build Status

| Build | Status | Complexity | Risk | Implementation |
|-------|--------|------------|------|----------------|
| BUILD-130 | ✅ COMPLETE | HIGH | MEDIUM | Manual (prevention infrastructure) |
| BUILD-128 | ✅ COMPLETE | MEDIUM | LOW | Manual (deliverables-aware manifest) |
| BUILD-127 | 🔴 BLOCKED | VERY HIGH | HIGH | Manual (self-healing governance) |
| BUILD-129 | 🔴 BLOCKED | HIGH | MEDIUM | Manual (token budget intelligence) |

---

## Implementation Order

### Phase 1: BUILD-127 Phase 1 - PhaseFinalizer + TestBaselineTracker (PRIORITY 1)
**Duration**: 4-6 hours
**Risk**: HIGH (modifies completion authority)
**Impact**: Fixes BUILD-126 false completion bug

**Files to Create**:
1. `src/autopack/phase_finalizer.py` (~250 lines)
   - PhaseFinalizationDecision dataclass
   - PhaseFinalizer class with assess_completion()
   - Comprehensive gate checks (CI, quality, deliverables)

2. `src/autopack/test_baseline_tracker.py` (~350 lines)
   - TestBaseline dataclass with JSON serialization
   - TestDelta dataclass with regression analysis
   - TestBaselineTracker with caching + retry logic
   - Uses pytest-json-report plugin

3. `tests/test_phase_finalizer.py` (~200 lines)
   - Mock all gates, verify blocking logic
   - Test phase validation_tests overlap
   - Test warnings vs blocking thresholds

4. `tests/test_baseline_tracker.py` (~250 lines)
   - Test baseline capture and caching
   - Test delta computation
   - Test flaky detection retry logic

**Files to Modify**:
1. `src/autopack/autonomous_executor.py`
   - Add T0 baseline capture in __init__ or startup
   - Replace completion logic at line ~4473 with PhaseFinalizer call
   - Integration: ~50 lines of changes

**Dependencies**:
```bash
pip install pytest-json-report
```

**Success Criteria**:
- ✅ BUILD-126 Phase E2 scenario: BLOCKED for missing test file (not COMPLETE)
- ✅ Pre-existing errors (11 in BUILD-126) ignored in baseline
- ✅ New collection error → retry once → if persistent, BLOCK
- ✅ New test failure in phase's validation_tests → BLOCK
- ✅ Flaky tests (pass on retry) → WARN only
- ✅ Baseline cached by commit SHA

---

### Phase 2: BUILD-129 Phase 1 - Output-Size Predictor (PRIORITY 2)
**Duration**: 3-4 hours
**Risk**: MEDIUM (additive, minimal modification)
**Impact**: Reduces truncation from 50% → 30%

**Files to Create**:
1. `src/autopack/token_estimator.py` (~400 lines)
   - estimate_output_tokens() - Deliverable-based estimation
   - Category-specific templates (backend, frontend, tests)
   - File complexity heuristics (imports, LOC, nesting)
   - Conservative multipliers (1.2x-1.5x safety margin)

2. `tests/test_token_estimator.py` (~200 lines)
   - Test estimation accuracy
   - Test BUILD-127 scenario (18k-22k vs 16k fixed)
   - Test multi-file phases
   - Test edge cases (empty files, huge files)

**Files to Modify**:
1. `src/autopack/anthropic_clients.py` (~30 lines)
   - Integrate token estimator in complexity-based budgeting
   - Replace file-count heuristic with estimator

2. `src/autopack/manifest_generator.py` (~20 lines)
   - Call estimator during scope generation
   - Store estimated_tokens in phase metadata

**Success Criteria**:
- ✅ BUILD-127 scenario: Estimated 18k-22k tokens (vs 16k fixed)
- ✅ All existing tests pass
- ✅ BUILD-112/113/114 stability maintained
- ✅ No regressions in token allocation

---

### Phase 3: BUILD-127 Phase 2 - Governance Request Handler (PRIORITY 3)
**Duration**: 4-5 hours
**Risk**: MEDIUM (new subsystem, database migration)
**Impact**: Enables self-negotiation for protected paths

**Files to Create**:
1. `src/autopack/governance_requests.py` (~200 lines)
   - GovernanceRequest dataclass
   - create_governance_request()
   - approve_request(), deny_request()
   - Auto-approval policy (conservative defaults)

2. Database Migration:
   - `alembic/versions/xxx_add_governance_requests.py`
   - Create governance_requests table
   - Index on pending requests

**Files to Modify**:
1. `src/autopack/autonomous_executor.py` (~150 lines)
   - Add _handle_governance_request()
   - Add _retry_with_allowance()
   - Modify patch application to detect governance errors
   - Integration with existing approval flow

2. `src/autopack/main.py` (~80 lines)
   - Add GET /api/governance/pending
   - Add POST /api/governance/approve/{request_id}
   - Extend existing approval endpoints

3. `src/autopack/governed_apply.py` (~30 lines)
   - Return structured error for protected path violations
   - JSON-encode error data (no signature change)

**Success Criteria**:
- ✅ BUILD-126 Phase G: Autopack requests approval for quality_gate.py
- ✅ Request visible via API
- ✅ Human approves via API or Telegram
- ✅ Phase retries with temporary allowance
- ✅ Audit trail persisted

---

### Phase 4: BUILD-129 Phase 2 - Continuation-Based Recovery (PRIORITY 4)
**Duration**: 3-4 hours
**Risk**: MEDIUM (complex retry logic)
**Impact**: Reduces wasted tokens on truncation

**Files to Create**:
1. `src/autopack/continuation_handler.py` (~300 lines)
   - detect_truncation() - Multiple signals
   - extract_partial_output() - Parse incomplete JSON/diff
   - generate_continuation_prompt() - Smart resumption
   - merge_continuations() - Combine partial outputs

2. `tests/test_continuation_handler.py` (~150 lines)

**Files to Modify**:
1. `src/autopack/autonomous_executor.py` (~100 lines)
   - Integrate continuation handler in Builder pipeline
   - Add retry logic with continuation context

---

### Phase 5: BUILD-127 Phase 3 - Enhanced Deliverables Validation (PRIORITY 5)
**Duration**: 2-3 hours
**Risk**: LOW (enhancement to existing system)
**Impact**: Better deliverable enforcement

**Files to Modify**:
1. Builder System Prompt (~50 lines)
   - Add DELIVERABLES_MANIFEST requirement
   - Structured JSON format for created/modified files

2. `src/autopack/deliverables_validator.py` (~150 lines)
   - Add validate_structured_manifest()
   - Symbol existence checks
   - Integration with PhaseFinalizer

---

### Phase 6: BUILD-129 Phase 3 - Dependency-Aware Batching (PRIORITY 6)
**Duration**: 3-4 hours
**Risk**: MEDIUM (complex dependency analysis)
**Impact**: Prevents type/consumer splits

**Files to Create**:
1. `src/autopack/dependency_batcher.py` (~350 lines)
   - analyze_dependencies() - AST-based analysis
   - create_batches() - Topological sort
   - validate_batch_completeness() - No dangling refs

---

## Testing Strategy

### Unit Tests
- **Phase Finalizer**: 15+ tests (blocking logic, warnings, gate combinations)
- **Baseline Tracker**: 15+ tests (caching, delta, retry, flaky detection)
- **Token Estimator**: 12+ tests (accuracy, edge cases, categories)
- **Governance Requests**: 10+ tests (approval flow, auto-approval, audit)
- **Continuation Handler**: 10+ tests (truncation detection, merge logic)
- **Dependency Batcher**: 12+ tests (dependency analysis, batch creation)

**Target Coverage**: ≥80% for all new modules

### Integration Tests
- **BUILD-126 Regression**: Phase E2 must BLOCK (not COMPLETE)
- **BUILD-127 Scenario**: Self-healing governance flow end-to-end
- **BUILD-129 Scenario**: Token budget prevents truncation
- **Stability**: BUILD-112/113/114 trigger counts maintained

### Manual Validation
- **Break-glass repair**: Test diagnose + repair on real database
- **Governance approval**: Test Telegram + API approval flow
- **Baseline caching**: Verify commit SHA caching works
- **Token estimation**: Compare estimates vs actual usage

---

## Risk Mitigation

### High-Risk Changes
1. **Completion Authority** (BUILD-127 Phase 1)
   - Risk: False positives (block valid completions) or false negatives (allow invalid)
   - Mitigation: Comprehensive test suite, manual validation on BUILD-126 scenarios
   - Rollback: Git tag before changes, restore original completion logic

2. **Token Budget Changes** (BUILD-129)
   - Risk: Misconfiguration causes all builds to truncate or over-allocate
   - Mitigation: Conservative estimates (1.2x-1.5x multipliers), existing escalation as fallback
   - Rollback: Feature flag to disable estimator, fall back to complexity-based

3. **Database Migration** (BUILD-127 Phase 2)
   - Risk: Migration failure blocks all runs
   - Mitigation: Test migration on copy of database first, backup before migration
   - Rollback: Down migration script, restore from backup

### Architectural Concerns
1. **Backward Compatibility**
   - All changes must preserve existing API signatures
   - Use structured errors (JSON in error message) instead of signature changes
   - Feature flags for new behavior

2. **Performance**
   - Baseline capture: Cache by commit SHA (avoid repeated pytest runs)
   - Token estimation: Deterministic calculation (no LLM calls)
   - Dependency analysis: Cache AST parses

3. **Security**
   - Auto-approval: Conservative defaults (tests/docs only)
   - Protected paths: Never auto-approve core files
   - Governance: Audit trail for all approvals

---

## Dependencies Between Builds

```
BUILD-130 (Prevention Infrastructure)
    ↓ (enables safe autonomous implementation)
BUILD-128 (Deliverables-Aware Manifest) ✅ COMPLETE
    ↓ (provides accurate scope inference)
BUILD-127 Phase 1 (PhaseFinalizer)
    ↓ (enables completion validation)
BUILD-129 Phase 1 (Token Estimator)
    ↓ (prevents truncation)
BUILD-127 Phase 2 (Governance)
    ↓ (enables self-negotiation)
BUILD-129 Phase 2 (Continuation)
    ↓ (improves recovery)
BUILD-127 Phase 3 (Deliverables Enhancement)
BUILD-129 Phase 3 (Dependency Batching)
```

---

## Implementation Checklist

### Pre-Implementation
- [ ] Backup database (`cp autopack.db autopack.db.backup`)
- [ ] Create git tag (`git tag -a build127-129-start -m "Before BUILD-127/129 manual implementation"`)
- [ ] Install dependencies (`pip install pytest-json-report`)
- [ ] Run break-glass repair diagnosis (`python scripts/break_glass_repair.py diagnose`)
- [ ] Run baseline tests (`PYTHONPATH=src pytest tests/ -v`)

### BUILD-127 Phase 1
- [ ] Create `src/autopack/phase_finalizer.py`
- [ ] Create `src/autopack/test_baseline_tracker.py`
- [ ] Create `tests/test_phase_finalizer.py`
- [ ] Create `tests/test_baseline_tracker.py`
- [ ] Modify `src/autopack/autonomous_executor.py` (baseline capture + completion logic)
- [ ] Run unit tests (`PYTHONPATH=src pytest tests/test_phase_finalizer.py tests/test_baseline_tracker.py -v`)
- [ ] Run integration test (BUILD-126 Phase E2 scenario)
- [ ] Manual validation (baseline caching, flaky retry)

### BUILD-129 Phase 1
- [ ] Create `src/autopack/token_estimator.py`
- [ ] Create `tests/test_token_estimator.py`
- [ ] Modify `src/autopack/anthropic_clients.py`
- [ ] Modify `src/autopack/manifest_generator.py`
- [ ] Run unit tests
- [ ] Validate BUILD-127 scenario (18k-22k estimate)
- [ ] Monitor BUILD-112/113/114 stability

### BUILD-127 Phase 2
- [ ] Create `src/autopack/governance_requests.py`
- [ ] Create alembic migration
- [ ] Modify `src/autopack/autonomous_executor.py` (governance handler)
- [ ] Modify `src/autopack/main.py` (API endpoints)
- [ ] Modify `src/autopack/governed_apply.py` (structured errors)
- [ ] Run migration (`alembic upgrade head`)
- [ ] Test governance flow end-to-end
- [ ] Test Telegram approval integration

### BUILD-129 Phase 2
- [ ] Create `src/autopack/continuation_handler.py`
- [ ] Create `tests/test_continuation_handler.py`
- [ ] Modify `src/autopack/autonomous_executor.py` (continuation integration)
- [ ] Test truncation recovery scenarios

### BUILD-127 Phase 3
- [ ] Modify Builder system prompt
- [ ] Modify `src/autopack/deliverables_validator.py` (structured manifest)
- [ ] Test symbol validation

### BUILD-129 Phase 3
- [ ] Create `src/autopack/dependency_batcher.py`
- [ ] Create `tests/test_dependency_batcher.py`
- [ ] Test dependency analysis

### Post-Implementation
- [ ] Run full test suite (`PYTHONPATH=src pytest tests/ -v`)
- [ ] Update BUILD_HISTORY.md
- [ ] Update README.md
- [ ] Create BUILD-127_IMPLEMENTATION.md
- [ ] Create BUILD-129_IMPLEMENTATION.md
- [ ] Git commit and push
- [ ] Monitor first autonomous run with new infrastructure

---

## Success Metrics

### BUILD-127
- **False Completion Rate**: 0% (down from ~20% in BUILD-126)
- **Governance Approval**: <5 minutes response time
- **Test Baseline**: 100% accuracy (pre-existing errors ignored)
- **Flaky Detection**: ≥90% accuracy

### BUILD-129
- **Truncation Rate**: <10% (down from ~50%)
- **Token Efficiency**: ≥85% (reduce waste from conservative budgets)
- **Estimation Accuracy**: Within ±20% of actual
- **Continuation Success**: ≥80% (recover from truncation)

### Overall
- **Build Stability**: BUILD-112/113/114 trigger counts maintained
- **Test Coverage**: ≥80% for all new code
- **Regression Rate**: 0% (no broken existing functionality)
- **Implementation Time**: ≤20 hours total

---

## Rollback Plan

### If BUILD-127 Phase 1 Fails
```bash
git checkout build127-129-start
git reset --hard HEAD
cp autopack.db.backup autopack.db
```

### If Database Migration Fails
```bash
alembic downgrade -1
cp autopack.db.backup autopack.db
```

### If Token Budget Breaks
- Feature flag: `DISABLE_TOKEN_ESTIMATOR=1` in .env
- Falls back to complexity-based budgeting

---

## Next Steps

1. **Start with BUILD-127 Phase 1** (highest priority, fixes critical bug)
2. **Validate thoroughly** before proceeding to Phase 2
3. **Monitor BUILD-112/113/114** throughout implementation
4. **Document learnings** for future autonomous implementations

Ready to begin manual implementation!
