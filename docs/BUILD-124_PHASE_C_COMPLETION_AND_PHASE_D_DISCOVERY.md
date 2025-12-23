# BUILD-124: Phase C Complete + Phase D Requirements Discovered

**Date**: 2025-12-22
**Status**: Phase C ✅ Complete | Phase D Requirements Identified

---

## Executive Summary

**Phase C (Grounded Context Builder)** has been successfully completed with all 7 tests passing. Through a test-driven requirements discovery approach, we've identified concrete requirements for **Phase D (PlanAnalyzer Integration)**.

**Key Achievements**:
- ✅ Phase C: 381-line deterministic context builder with 4000-char budget
- ✅ Fixed hardcoded GPT-4o → Claude Sonnet 4.5
- ✅ Created 14 integration tests revealing 7 Phase D gaps
- ✅ Documented concrete implementation requirements

---

## Phase C Completion ✅

### Deliverables

1. **[src/autopack/plan_analyzer_grounding.py](../src/autopack/plan_analyzer_grounding.py)** (381 lines)
   - `GroundedContext` dataclass for LLM prompt context
   - `GroundedContextBuilder` class with methods:
     - `build_context()` - single-phase analysis
     - `build_multi_phase_context()` - plan-level analysis
     - `_build_repo_summary()` - repo structure summary
     - `_build_phase_context()` - phase-specific context
     - `_get_top_level_dirs()` - directory extraction
   - Hard 4000 character limit with smart truncation
   - Zero LLM calls, fully deterministic
   - PatternMatcher integration for category detection

2. **[tests/test_plan_analyzer_grounding.py](../tests/test_plan_analyzer_grounding.py)** ✅ **7/7 tests passing**
   - Basic context generation
   - Pre-computed match results
   - Truncation behavior
   - Empty repository handling
   - Multi-phase context
   - Truncation with many phases
   - Top-level directory extraction

3. **Model Update**
   - [src/autopack/plan_analyzer.py:236](../src/autopack/plan_analyzer.py#L236)
   - Changed `gpt-4o` → `claude-sonnet-4-5`
   - Per user requirement: "use sonnet 4.5 for plananalyzer"

4. **Documentation**
   - Updated [BUILD-123v2_COMPLETION.md](BUILD-123v2_COMPLETION.md)
   - Created [BUILD-124_PHASE_D_REQUIREMENTS.md](BUILD-124_PHASE_D_REQUIREMENTS.md)

### Phase C Features

```python
from autopack.plan_analyzer_grounding import GroundedContextBuilder

builder = GroundedContextBuilder(
    repo_scanner=scanner,
    pattern_matcher=matcher,
    max_chars=4000  # Hard token budget limit
)

context = builder.build_context(
    goal="Add JWT authentication",
    phase_id="auth-backend",
    description="Implement JWT token generation",
    match_result=pattern_match_result  # Optional, reuse from pattern matching
)

# Output: GroundedContext with:
# - repo_summary: top-level dirs, detected anchors, file counts
# - phase_context: pattern match results, candidate files
# - total_chars: actual character count
# - truncated: bool flag if exceeded budget

prompt_text = context.to_prompt_section()
# Ready for LLM with proper formatting
```

---

## Phase D Requirements Discovery 🔍

### Testing Plan Approach

Created [tests/test_plan_analyzer_integration.py](../tests/test_plan_analyzer_integration.py) with 14 tests across 6 categories:

1. **Trigger Conditions** (4 tests)
2. **LLM Integration** (3 tests)
3. **Context Budget** (2 tests)
4. **Metadata Attachment** (2 tests)
5. **Opt-In Behavior** (2 tests)
6. **Phase Count Limits** (1 test)

### Test Results: 7/14 Passing (50% Baseline)

#### ✅ Passing Tests (Baseline Behavior Works)

1. `test_high_confidence_does_not_trigger_plan_analyzer` ✅
   - **Verifies**: High confidence (≥0.70) correctly skips PlanAnalyzer
   - **Status**: Deterministic scope generated, status="skipped"

2. `test_medium_confidence_with_ambiguous_match_triggers_plan_analyzer` ✅
   - **Verifies**: Medium confidence structure exists
   - **Status**: Metadata structure correct

3. `test_flag_disabled_never_triggers_plan_analyzer` ✅
   - **Verifies**: `enable_plan_analyzer=False` → status="disabled"
   - **Status**: Opt-in requirement preserved

4. `test_large_repo_context_stays_under_budget` ✅
   - **Verifies**: Phase C context stays under 4000 chars (150 files)
   - **Status**: Token budget enforcement works

5. `test_multiple_phases_do_not_accumulate_unbounded_context` ✅
   - **Verifies**: Multi-phase context sharing (no accumulation)
   - **Status**: Phase C multi-phase builder works

6. `test_plan_analysis_metadata_structure` ✅
   - **Verifies**: PlanAnalysisMetadata structure correct
   - **Status**: Phase A metadata infrastructure works

7. `test_max_phases_analyzed_per_run` ✅
   - **Verifies**: Baseline passes (limit enforced in Phase D)
   - **Status**: Structure supports limiting

#### ❌ Failing Tests (Phase D Implementation Gaps)

All 7 failures reveal concrete implementation needs:

1. `test_low_confidence_with_empty_scope_triggers_plan_analyzer` ❌
   - **Error**: `AttributeError: module 'autopack.manifest_generator' does not have attribute 'PlanAnalyzer'`
   - **Gap**: No conditional import of PlanAnalyzer
   - **Fix**: Add lazy import when enabled and triggered

2. `test_async_plan_analyzer_call_with_grounded_context` ❌
   - **Error**: `AttributeError: module 'autopack.plan_analyzer' does not have attribute 'LLMService'`
   - **Gap**: Wrong import path in test (actual: `LlmService`)
   - **Fix**: Update test mocking path to `autopack.llm_service.LlmService`

3. `test_timeout_handling_for_slow_llm_responses` ❌
   - **Error**: Same as #1 (no PlanAnalyzer import)
   - **Gap**: No timeout wrapper for LLM calls
   - **Fix**: Add timeout protection (30s default?)

4. `test_error_recovery_on_llm_failure` ❌
   - **Error**: Same as #1
   - **Gap**: No try/except for LLM failures
   - **Fix**: Graceful fallback to deterministic scope

5. `test_plan_analysis_never_overrides_deterministic_scope` ❌
   - **Error**: Same as #1
   - **Gap**: No protection against scope override
   - **Fix**: Attach LLM results as metadata only (never replace scope)

6. `test_disabled_flag_means_zero_llm_calls` ❌
   - **Error**: Wrong import path
   - **Gap**: Need to verify zero imports when disabled
   - **Fix**: Update test + ensure no LLM code when flag=False

7. `test_enabled_flag_allows_conditional_llm_use` ❌
   - **Error**: Same as #1
   - **Gap**: No conditional PlanAnalyzer instantiation
   - **Fix**: Lazy init only when enabled AND triggered

---

## Concrete Phase D Implementation Requirements

Based on test failures, Phase D needs **7 changes to manifest_generator.py**:

### 1. Conditional Import

```python
# Only import when needed
def _maybe_run_plan_analyzer(self, phase, confidence, scope):
    if not self.enable_plan_analyzer:
        return None

    if not self._should_trigger(confidence, scope):
        return None

    # Lazy import (only when actually needed)
    from autopack.plan_analyzer import PlanAnalyzer
    analyzer = self._get_or_create_plan_analyzer()
    # ...
```

### 2. Trigger Logic

```python
def _should_trigger_plan_analyzer(
    self,
    confidence: float,
    scope: List[str],
    category: str
) -> bool:
    """Determine if PlanAnalyzer should run"""

    # Never run if disabled
    if not self.enable_plan_analyzer:
        return False

    # High confidence - skip
    if confidence >= 0.70:
        return False

    # Low confidence with empty scope - run
    if confidence < 0.15 and len(scope) == 0:
        return True

    # Medium confidence - potentially run
    if 0.15 <= confidence < 0.30:
        return True  # Phase D can refine this logic

    return False
```

### 3. Async/Sync Boundary

```python
from autopack.manifest_generator import run_async_safe

# Use Phase B helper
analysis = run_async_safe(
    analyzer.analyze_phase(
        phase_spec=phase,
        context=grounded_context.to_prompt_section()
    )
)
```

### 4. Error Handling

```python
try:
    analysis = run_async_safe(analyzer.analyze_phase(...))
    self.plan_analysis.status = "ran"

except TimeoutError as e:
    self.plan_analysis.status = "failed"
    self.plan_analysis.error = f"LLM timeout: {e}"
    # Fall back to deterministic scope (already set)

except Exception as e:
    self.plan_analysis.status = "failed"
    self.plan_analysis.error = f"Analysis failed: {e}"
    # Fall back to deterministic scope
```

### 5. Scope Preservation

```python
# CRITICAL: Never override deterministic scope

# ❌ WRONG:
phase["scope"]["paths"] = analysis.recommended_scope

# ✅ CORRECT:
# Attach as metadata only
phase["metadata"]["plan_analysis"] = {
    "feasible": analysis.feasible,
    "confidence": analysis.confidence,
    "llm_recommended_scope": analysis.recommended_scope,  # Advisory
    "concerns": analysis.concerns,
    "recommendations": analysis.recommendations
}
```

### 6. Phase Count Limit

```python
MAX_PHASES_TO_ANALYZE = 3

analyzed_count = 0
for phase in phases:
    if analyzed_count >= MAX_PHASES_TO_ANALYZE:
        self.plan_analysis.warnings.append(
            f"Analyzed max {MAX_PHASES_TO_ANALYZE} phases"
        )
        break

    if should_trigger(phase):
        run_analysis(phase)
        analyzed_count += 1
```

### 7. Grounded Context Integration

```python
from autopack.plan_analyzer_grounding import GroundedContextBuilder

# Create once, reuse for all phases
context_builder = GroundedContextBuilder(
    repo_scanner=self.scanner,
    pattern_matcher=self.matcher,
    max_chars=4000
)

# For each phase
grounded_context = context_builder.build_context(
    goal=phase["goal"],
    phase_id=phase["phase_id"],
    description=phase.get("description", ""),
    match_result=pattern_match_result  # Reuse from pattern matching
)

analysis = analyzer.analyze_phase(
    phase_spec=phase,
    context=grounded_context.to_prompt_section()
)
```

---

## Import Path Corrections

Test mocking paths need updates:

| Test Mock | Should Be |
|-----------|-----------|
| `autopack.plan_analyzer.LLMService` | `autopack.llm_service.LlmService` |
| `autopack.manifest_generator.PlanAnalyzer` | Valid (will exist after import added) |

**Note**: Actual import is `from autopack.llm_service import LlmService` (lowercase 'm' in 'Llm')

---

## Phase D Implementation Checklist

Based on test requirements:

- [ ] Add conditional `PlanAnalyzer` import to `manifest_generator.py`
- [ ] Implement `_should_trigger_plan_analyzer()` method
- [ ] Add `_get_or_create_plan_analyzer()` lazy initialization
- [ ] Integrate `GroundedContextBuilder` in manifest flow
- [ ] Add try/except error handling for LLM calls
- [ ] Implement timeout protection (30s default?)
- [ ] Add phase count tracking (`MAX_PHASES_TO_ANALYZE = 3`)
- [ ] Ensure scope is NEVER overridden (metadata only)
- [ ] Fix test import paths
- [ ] Add logging for trigger decisions
- [ ] Update `plan_analysis` metadata status tracking
- [ ] Run tests iteratively until 14/14 pass

---

## Estimated Phase D Effort

**Lines of Code**: ~150-200 lines
**Files Modified**: 2 (manifest_generator.py + test fixes)
**Risk Level**: Medium (LLM integration, async boundary, error handling)
**Test Coverage**: 14 tests define exact behavior

---

## Questions for Discussion

Before implementing Phase D, confirm:

1. **Timeout Duration**: 30 seconds for LLM calls? (Configurable?)
2. **Cost Control**: Is max 3 phases per run acceptable?
3. **Error Behavior**: Log warnings or fail silently on LLM errors?
4. **Scope Override**: Confirm LLM NEVER replaces deterministic scope (metadata only)
5. **Priority Sorting**: If >3 phases need analysis, prioritize lowest confidence first?

---

## Success Criteria

Phase D complete when:

1. ✅ 14/14 integration tests pass
2. ✅ `enable_plan_analyzer=False` → zero LLM imports
3. ✅ `enable_plan_analyzer=True` → conditional LLM use
4. ✅ Timeout/error handling prevents failures
5. ✅ Deterministic scope never overridden
6. ✅ Max 3 phases analyzed per run
7. ✅ Phase C grounded context used for all LLM calls

---

## Related Documents

- [BUILD-123v2_COMPLETION.md](BUILD-123v2_COMPLETION.md) - Overall completion status
- [BUILD-124_PHASE_D_REQUIREMENTS.md](BUILD-124_PHASE_D_REQUIREMENTS.md) - Detailed requirements
- [tests/test_plan_analyzer_grounding.py](../tests/test_plan_analyzer_grounding.py) - Phase C tests
- [tests/test_plan_analyzer_integration.py](../tests/test_plan_analyzer_integration.py) - Phase D tests

---

## Next Steps

**Option 1**: Implement Phase D now based on discovered requirements
**Option 2**: Request more detailed guidance from other cursor on specific concerns
**Option 3**: Present this discovery to user for approval before proceeding

**Recommendation**: Proceed with incremental Phase D implementation, running tests after each step to ensure correctness.
