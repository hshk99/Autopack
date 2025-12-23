# BUILD-129: Self-Improvement - Token Budget Intelligence

**Date**: 2025-12-23
**Type**: Self-Improvement (Autopack implementing Autopack improvements)
**Priority**: HIGH (unblocks BUILD-127, improves all future phases)
**Complexity**: HIGH (multi-file, multiple subsystems)
**Predecessor**: BUILD-128 (Deliverables-Aware Manifest)
**Reference**: docs/TOKEN_BUDGET_ANALYSIS_REVISED.md (GPT-5.2 validated)

---

## Executive Summary

Autopack will **autonomously implement GPT-5.2's 4-layer token budget policy** to reduce truncation failures from 50% → 10% for multi-file phases. This is a **self-improvement build** demonstrating Autopack's ability to implement complex architectural changes autonomously (similar to BUILD-126 quality_gate.py).

**Why Autopack Can Do This**:
1. ✅ BUILD-126 precedent: Autopack autonomously implemented 535-line quality_gate.py
2. ✅ BUILD-112/113/114 active: Deep retrieval, goal-aware decisions, structured edit fallback
3. ✅ Clear specification: TOKEN_BUDGET_ANALYSIS_REVISED.md provides detailed implementation
4. ✅ Incremental phases: 3 phases with clear success criteria

**Monitoring Strategy**: Run BUILD-129 phases while monitoring BUILD-112/113/114 stability metrics from recent runs.

---

## Current State Analysis

### Token Budget System (Current)

**Files Involved**:
- [anthropic_clients.py:155-180](c:\dev\Autopack\src\autopack\anthropic_clients.py#L155-L180) - Complexity-based budgeting
- [autonomous_executor.py:3870-3900](c:\dev\Autopack\src\autopack\autonomous_executor.py#L3870-L3900) - Token escalation (BUILD-046)
- [model_router.py](c:\dev\Autopack\src\autopack\model_router.py) - Model selection

**Current Logic**:
```python
# Complexity-based (ignores scope size)
if complexity == "low": max_tokens = 8192
elif complexity == "medium": max_tokens = 12288
elif complexity == "high": max_tokens = 16384

# Category overrides (partial scope awareness)
if task_category in ("deployment", "frontend"): max_tokens = max(max_tokens, 16384)
if task_category == "backend" and len(scope_paths) >= 3: max_tokens = max(max_tokens, 12000)

# Escalation on truncation (NOW WORKS after GPT-5.2 fix)
if was_truncated: escalated_tokens = min(int(current_max_tokens * 1.5), 64000)
```

**Gaps** (per GPT-5.2 analysis):
1. ❌ No output-size prediction (uses file count as weak proxy)
2. ❌ No continuation-based recovery (regenerates everything on truncation)
3. ❌ Monolithic output formats (diff, single JSON) - catastrophically fragile under truncation
4. ❌ No dependency-aware batching (would split types from consumers)

### BUILD-112/113/114 Stability Monitoring

**Recent Usage Evidence** (from BUILD_HISTORY.md):
- BUILD-127: Deep retrieval triggered ✅ (line 97-99 in execution log)
- BUILD-127: Structured edit fallback triggered ✅ (BUILD-114)
- BUILD-126: Goal-aware decision making used ✅ (BUILD-113)

**Monitoring Metrics**:
```python
# Track during BUILD-129 execution:
build112_triggers = count("DeepRetrieval] Starting bounded retrieval")
build113_decisions = count("GoalAwareDecisionMaker] Decision:")
build114_fallbacks = count("Falling back to structured_edit")

# Success criteria: No regression from baseline
baseline_build112_triggers = 15 (from recent builds)
baseline_build113_decisions = 8
baseline_build114_fallbacks = 12
```

---

## BUILD-129 Implementation Plan

### Phase 1: Output-Size Predictor (Layer 1)

**Goal**: Replace file-count heuristic with deliverable-based token estimation

**Deliverables**:
1. `src/autopack/token_estimator.py` - New module with estimation logic
2. `src/autopack/anthropic_clients.py` modifications - Integrate estimator
3. `src/autopack/manifest_generator.py` modifications - Call estimator during scope generation
4. `tests/test_token_estimator.py` - 15+ tests validating estimation accuracy
5. `docs/BUILD-129_PHASE1_OUTPUT_SIZE_PREDICTOR.md` - Implementation documentation

**Success Criteria**:
- ✅ BUILD-127 scenario: Estimated 18k-22k tokens (vs current 16k fixed)
- ✅ All existing tests pass (no regressions)
- ✅ BUILD-112/113/114 stability: No drop in trigger counts

**Complexity**: MEDIUM (new module + 2 integrations)
**Risk Level**: LOW (additive only, doesn't change existing logic)
**Estimated Token Budget**: 20k (6 files, backend category, medium complexity)

---

### Phase 2: Continuation Recovery (Layer 2) - HIGHEST PRIORITY

**Goal**: Implement continuation-based truncation recovery to avoid wasted work

**Deliverables**:
1. `src/autopack/continuation_handler.py` - New module with continuation logic
2. `src/autopack/autonomous_executor.py` modifications - Integrate continuation recovery
3. `src/autopack/anthropic_clients.py` modifications - Add continuation prompt support
4. `tests/test_continuation_recovery.py` - 12+ tests for diff and JSON continuation
5. `docs/BUILD-129_PHASE2_CONTINUATION_RECOVERY.md` - Implementation documentation

**Success Criteria**:
- ✅ Truncation at 95% → continuation completes remaining 5%
- ✅ BUILD-127 scenario: First attempt truncates at file #11, continuation completes files #11-12
- ✅ No full regeneration on continuation (verify via token usage logs)

**Complexity**: HIGH (multi-file, complex parsing logic)
**Risk Level**: MEDIUM (modifies retry logic, needs careful testing)
**Estimated Token Budget**: 28k (8 files, backend category, high complexity)

---

### Phase 3: NDJSON Structured-Edit Format (Layer 3)

**Goal**: Replace monolithic JSON with line-delimited format for truncation tolerance

**Deliverables**:
1. `src/autopack/ndjson_handler.py` - New module with NDJSON parsing/generation
2. `src/autopack/anthropic_clients.py` modifications - Add NDJSON format option
3. `src/autopack/apply_handler.py` modifications - NDJSON operation applier
4. `src/autopack/autonomous_executor.py` modifications - Select NDJSON for multi-file scopes
5. `tests/test_ndjson_structured_edit.py` - 20+ tests including truncation scenarios
6. `docs/BUILD-129_PHASE3_NDJSON_FORMAT.md` - Implementation documentation

**Success Criteria**:
- ✅ Truncation at operation #8/12 → parse and apply operations #1-7 successfully
- ✅ Continuation from operation #8 (not #1)
- ✅ JSON repair failures eliminated (NDJSON doesn't need repair)

**Complexity**: HIGH (new format, multiple integration points)
**Risk Level**: MEDIUM (changes output contract, needs Builder prompt updates)
**Estimated Token Budget**: 32k (9 files, backend category, high complexity)

---

### Phase 4 (DEFERRED): Dependency-Aware Batching (Layer 4)

**Status**: DEFERRED to BUILD-130
**Reason**: Phases 1-3 should reduce truncation rate to <10%, making batching lower priority

**Trigger Condition**: If post-Phase-3 truncation rate >15% for very large scopes (>20 files)

---

## Implementation Strategy

### Phased Autonomous Execution

```json
{
  "run_id": "build129-token-budget-intelligence",
  "goal": "Implement GPT-5.2's 4-layer token budget policy to reduce truncation failures from 50% to 10%",
  "phases": [
    {
      "phase_id": "build129-phase1-output-size-predictor",
      "display_name": "Phase 1: Output-Size Predictor (Layer 1)",
      "complexity": "medium",
      "task_category": "backend",
      "scope": {
        "deliverables": [
          "src/autopack/token_estimator.py (new module with estimate_output_tokens)",
          "src/autopack/anthropic_clients.py modifications (integrate estimator at line 160)",
          "src/autopack/manifest_generator.py modifications (call estimator in _enhance_phase)",
          "tests/test_token_estimator.py (15 tests covering all deliverable types)",
          "docs/BUILD-129_PHASE1_OUTPUT_SIZE_PREDICTOR.md"
        ],
        "protected_paths": [
          "src/autopack/autonomous_executor.py",
          "src/autopack/models.py",
          "src/frontend/"
        ]
      },
      "acceptance_criteria": [
        "BUILD-127 scenario estimated at 18k-22k tokens",
        "All existing tests pass",
        "BUILD-112/113/114 trigger counts stable"
      ]
    },
    {
      "phase_id": "build129-phase2-continuation-recovery",
      "display_name": "Phase 2: Continuation Recovery (Layer 2)",
      "complexity": "high",
      "task_category": "backend",
      "dependencies": ["build129-phase1-output-size-predictor"],
      "scope": {
        "deliverables": [
          "src/autopack/continuation_handler.py (new module with handle_truncation_with_continuation)",
          "src/autopack/autonomous_executor.py modifications (integrate continuation at line 3800)",
          "src/autopack/anthropic_clients.py modifications (add continuation prompt support)",
          "tests/test_continuation_recovery.py (12 tests for diff and JSON continuation)",
          "docs/BUILD-129_PHASE2_CONTINUATION_RECOVERY.md"
        ],
        "protected_paths": [
          "src/autopack/models.py",
          "src/frontend/"
        ]
      },
      "acceptance_criteria": [
        "Truncation at 95% triggers continuation (not regeneration)",
        "BUILD-127 scenario: continuation completes after first truncation",
        "Token usage logs show no full regeneration on continuation"
      ]
    },
    {
      "phase_id": "build129-phase3-ndjson-format",
      "display_name": "Phase 3: NDJSON Structured-Edit Format (Layer 3)",
      "complexity": "high",
      "task_category": "backend",
      "dependencies": ["build129-phase2-continuation-recovery"],
      "scope": {
        "deliverables": [
          "src/autopack/ndjson_handler.py (new module with parse_ndjson_structured_edit)",
          "src/autopack/anthropic_clients.py modifications (add NDJSON format selection)",
          "src/autopack/apply_handler.py modifications (NDJSON operation applier)",
          "src/autopack/autonomous_executor.py modifications (select NDJSON for multi-file)",
          "tests/test_ndjson_structured_edit.py (20 tests including truncation)",
          "docs/BUILD-129_PHASE3_NDJSON_FORMAT.md"
        ],
        "protected_paths": [
          "src/autopack/models.py",
          "src/frontend/"
        ]
      },
      "acceptance_criteria": [
        "Truncated NDJSON parseable up to last complete line",
        "Continuation from last operation (not full regeneration)",
        "JSON repair failures eliminated"
      ]
    }
  ]
}
```

### Monitoring During Execution

**BUILD-112/113/114 Stability Metrics**:

```python
# After each BUILD-129 phase completion:
def check_build112_114_stability():
    """
    Verify BUILD-112/113/114 features still working during BUILD-129 implementation.
    """
    # Check BUILD-112 (Deep Retrieval)
    recent_runs = get_runs_since("2025-12-23")
    deep_retrieval_triggers = sum(
        count_log_pattern(run, "DeepRetrieval] Starting bounded retrieval")
        for run in recent_runs
    )
    assert deep_retrieval_triggers >= baseline_build112_triggers, \
        f"BUILD-112 regression: {deep_retrieval_triggers} < {baseline_build112_triggers}"

    # Check BUILD-113 (Goal-Aware Decisions)
    goal_aware_decisions = sum(
        count_log_pattern(run, "GoalAwareDecisionMaker] Decision:")
        for run in recent_runs
    )
    assert goal_aware_decisions >= baseline_build113_decisions, \
        f"BUILD-113 regression: {goal_aware_decisions} < {baseline_build113_decisions}"

    # Check BUILD-114 (Structured Edit Fallback)
    structured_fallbacks = sum(
        count_log_pattern(run, "Falling back to structured_edit")
        for run in recent_runs
    )
    assert structured_fallbacks >= baseline_build114_fallbacks, \
        f"BUILD-114 regression: {structured_fallbacks} < {baseline_build114_fallbacks}"

    logger.info("[STABILITY_CHECK] BUILD-112/113/114 stable ✅")
```

**Run After**:
- BUILD-129 Phase 1 completion
- BUILD-129 Phase 2 completion
- BUILD-129 Phase 3 completion

---

## Risk Assessment

### Low Risk Areas ✅

1. **Phase 1 (Output-Size Predictor)**:
   - Additive only (new module)
   - Doesn't change existing budget logic (only provides better input)
   - Easy rollback (remove estimator call)

2. **BUILD-112/113/114 Isolation**:
   - BUILD-129 doesn't modify diagnostics_agent.py, build_history_integrator.py, or goal-aware components
   - Token budget changes are orthogonal to retrieval/decision logic

### Medium Risk Areas ⚠️

1. **Phase 2 (Continuation Recovery)**:
   - Modifies retry logic in autonomous_executor.py
   - Could interfere with existing escalation (BUILD-046)
   - **Mitigation**: Test continuation + escalation interaction explicitly

2. **Phase 3 (NDJSON Format)**:
   - Changes Builder output contract
   - Requires prompt updates for LLM to emit NDJSON
   - **Mitigation**: Keep existing formats as fallback, add NDJSON as opt-in

### High Risk Areas 🔴

**None** - BUILD-129 is well-scoped and doesn't touch high-risk subsystems (governance, frontend, database schema)

---

## Success Metrics

### Primary Metrics (Token Budget)

**Before BUILD-129**:
- Truncation rate (multi-file phases ≥10 files): 50%
- Average attempts per multi-file phase: 2.3
- Wasted tokens (failed attempts): ~8k per truncated phase

**After BUILD-129 Phase 1**:
- Target truncation rate: 30% (better budget selection)
- Target attempts: 1.8 average

**After BUILD-129 Phase 2**:
- Target truncation rate: 15% (continuation recovers most)
- Target attempts: 1.3 average

**After BUILD-129 Phase 3**:
- Target truncation rate: 10% (NDJSON tolerates truncation)
- Target attempts: 1.1 average

### Secondary Metrics (BUILD-112/113/114 Stability)

**Baseline** (from recent runs):
- BUILD-112 deep retrieval triggers: ~15 per week
- BUILD-113 goal-aware decisions: ~8 per week
- BUILD-114 structured edit fallbacks: ~12 per week

**Target During BUILD-129**:
- No >10% drop in any baseline metric
- Zero new regressions in diagnostic tests

### Tertiary Metrics (Self-Improvement)

**BUILD-126 Comparison**:
- BUILD-126: 535 lines quality_gate.py, 1 phase, HIGH complexity
- BUILD-129: ~800 lines total, 3 phases, HIGH complexity
- Expected: Similar autonomous implementation success

---

## Timeline and Resource Estimate

### Phase 1: Output-Size Predictor
- **Estimated Duration**: 1-2 hours autonomous execution
- **Token Budget**: 20k (6 files)
- **Dependencies**: None

### Phase 2: Continuation Recovery
- **Estimated Duration**: 2-3 hours autonomous execution
- **Token Budget**: 28k (8 files)
- **Dependencies**: Phase 1 complete

### Phase 3: NDJSON Format
- **Estimated Duration**: 3-4 hours autonomous execution
- **Token Budget**: 32k (9 files)
- **Dependencies**: Phase 2 complete

### Total BUILD-129
- **Total Duration**: 6-9 hours autonomous execution (over 1-2 days with monitoring pauses)
- **Total Token Budget**: ~80k tokens
- **Total Cost**: ~$1.20 (input) + $1.20 (output) = **$2.40 estimated**

---

## Rollback Plan

### Phase 1 Rollback
```bash
# Remove estimator integration
git checkout src/autopack/anthropic_clients.py src/autopack/manifest_generator.py
rm src/autopack/token_estimator.py tests/test_token_estimator.py
```

### Phase 2 Rollback
```bash
# Remove continuation logic
git checkout src/autopack/autonomous_executor.py src/autopack/anthropic_clients.py
rm src/autopack/continuation_handler.py tests/test_continuation_recovery.py
```

### Phase 3 Rollback
```bash
# Remove NDJSON format
git checkout src/autopack/anthropic_clients.py src/autopack/apply_handler.py src/autopack/autonomous_executor.py
rm src/autopack/ndjson_handler.py tests/test_ndjson_structured_edit.py
```

### Full BUILD-129 Rollback
```bash
git reset --hard <pre-build129-commit-hash>
```

---

## BUILD-127 Retry Plan (Post BUILD-129)

**After Phase 1**:
- Retry BUILD-127 Phase 1 with output-size predictor
- Expected: 18k-22k budget selected (vs 16k before)
- Expected: Lower truncation probability (but not eliminated)

**After Phase 2**:
- Retry BUILD-127 Phase 1 with continuation recovery
- Expected: First attempt may truncate, continuation completes
- Expected: 1 successful generation (vs 2+ failed attempts before)

**After Phase 3**:
- Retry BUILD-127 Phase 1 with NDJSON format
- Expected: Even if truncation occurs, partial operations applied
- Expected: Zero JSON parse failures

---

## Decision Points

### Go/No-Go Criteria for Each Phase

**Phase 1**:
- ✅ GO if: All tests pass, BUILD-112/113/114 stable
- ❌ NO-GO if: Estimation accuracy <50%, existing tests fail

**Phase 2**:
- ✅ GO if: Phase 1 successful, continuation logic tested
- ❌ NO-GO if: Continuation conflicts with escalation, Phase 1 unstable

**Phase 3**:
- ✅ GO if: Phase 2 successful, NDJSON parsing robust
- ❌ NO-GO if: Builder cannot emit valid NDJSON, Phase 2 unstable

---

## Comparison to BUILD-126

**BUILD-126** (Quality Gate Implementation):
- **Scope**: 535 lines, 1 new module, 1 phase
- **Complexity**: HIGH (git operations, test execution, rollback)
- **Result**: ✅ SUCCESS (Autopack autonomously implemented)
- **Validation**: BUILD-113 goal-aware decision making used

**BUILD-129** (Token Budget Intelligence):
- **Scope**: ~800 lines, 3 new modules, 3 phases
- **Complexity**: HIGH (estimation, continuation, new format)
- **Expected Result**: ✅ SUCCESS (similar to BUILD-126)
- **Validation**: BUILD-112/113/114 stability monitoring

**Key Similarity**: Both are **self-improvement builds** where Autopack implements Autopack enhancements.

---

## Conclusion

BUILD-129 is **feasible for autonomous implementation** with the following confidence factors:

1. ✅ **BUILD-126 Precedent**: Autopack successfully implemented complex feature autonomously
2. ✅ **BUILD-112/113/114 Active**: Deep retrieval, goal-aware decisions, structured edit available
3. ✅ **Clear Specification**: TOKEN_BUDGET_ANALYSIS_REVISED.md provides detailed guidance
4. ✅ **Phased Approach**: 3 incremental phases with clear success criteria
5. ✅ **Low Risk**: Doesn't touch governance, frontend, or database schema
6. ✅ **Monitoring Strategy**: BUILD-112/113/114 stability checks after each phase

**Recommendation**: Proceed with BUILD-129 autonomous execution while monitoring BUILD-112/113/114 stability.

---

**Next Steps**:
1. Create BUILD-129 run configuration
2. Execute Phase 1 (Output-Size Predictor)
3. Validate + check BUILD-112/113/114 stability
4. Execute Phase 2 (Continuation Recovery)
5. Validate + check BUILD-112/113/114 stability
6. Execute Phase 3 (NDJSON Format)
7. Validate + retry BUILD-127 with new system

**Prepared by**: Claude Sonnet 4.5
**Date**: 2025-12-23
**Status**: READY FOR AUTONOMOUS EXECUTION
