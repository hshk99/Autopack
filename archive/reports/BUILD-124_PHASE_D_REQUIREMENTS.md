# BUILD-124 Phase D: Requirements Discovery

**Date**: 2025-12-22
**Status**: Requirements Identified via Testing Plan

---

## Test Results Summary

**Results**: 7/14 tests pass (50% baseline)

### ✅ Passing Tests (Baseline Behavior)

1. `test_high_confidence_does_not_trigger_plan_analyzer` ✅
   - High confidence (>= 0.70) correctly returns status="skipped"
   - Deterministic scope generated successfully

2. `test_medium_confidence_with_ambiguous_match_triggers_plan_analyzer` ✅
   - Medium confidence scenarios handled (structure exists)

3. `test_flag_disabled_never_triggers_plan_analyzer` ✅
   - `enable_plan_analyzer=False` correctly returns status="disabled"
   - Current behavior preserves opt-in requirement

4. `test_large_repo_context_stays_under_budget` ✅
   - Phase C grounded context stays under 4000 char limit
   - Large repos (150 files) handled correctly

5. `test_multiple_phases_do_not_accumulate_unbounded_context` ✅
   - Multi-phase context sharing works correctly

6. `test_plan_analysis_metadata_structure` ✅
   - PlanAnalysisMetadata structure is correct

7. `test_max_phases_analyzed_per_run` ✅
   - Baseline passes (Phase D will enforce limit)

### ❌ Failing Tests (Phase D Gaps)

1. `test_low_confidence_with_empty_scope_triggers_plan_analyzer` ❌
   - **Gap**: PlanAnalyzer not imported in manifest_generator.py
   - **Need**: Conditional import when `enable_plan_analyzer=True`

2. `test_async_plan_analyzer_call_with_grounded_context` ❌
   - **Gap**: LLMService not exposed in plan_analyzer module
   - **Need**: Verify import path or use existing llm_service module

3. `test_timeout_handling_for_slow_llm_responses` ❌
   - **Gap**: PlanAnalyzer not integrated in manifest flow
   - **Need**: Timeout handling wrapper for LLM calls

4. `test_error_recovery_on_llm_failure` ❌
   - **Gap**: No error handling for PlanAnalyzer failures
   - **Need**: Graceful fallback to deterministic scope

5. `test_plan_analysis_never_overrides_deterministic_scope` ❌
   - **Gap**: No protection against scope override
   - **Need**: Preserve deterministic scope, attach LLM analysis as metadata only

6. `test_disabled_flag_means_zero_llm_calls` ❌
   - **Gap**: LLMService import path issue
   - **Need**: Verify no LLM imports when disabled

7. `test_enabled_flag_allows_conditional_llm_use` ❌
   - **Gap**: PlanAnalyzer not conditionally instantiated
   - **Need**: Lazy initialization only when enabled AND triggered

---

## Concrete Phase D Requirements

Based on test failures, Phase D must implement:

### 1. **Conditional PlanAnalyzer Import**

```python
# In manifest_generator.py

def generate_manifest(self, plan_data, skip_validation=False):
    # ... existing code ...

    # Only import if enabled AND conditions met
    if self.enable_plan_analyzer:
        # Trigger conditions
        should_analyze = (
            confidence < 0.15 and len(scope) == 0  # Low conf, empty scope
            or (0.15 <= confidence < 0.30 and is_ambiguous)  # Medium conf, ambiguous
        )

        if should_analyze:
            from autopack.plan_analyzer import PlanAnalyzer
            # ... lazy initialization ...
```

**Why**: Avoids importing unused modules when disabled

### 2. **Trigger Logic Implementation**

```python
def _should_trigger_plan_analyzer(
    self,
    confidence: float,
    scope: List[str],
    category: str
) -> bool:
    """Determine if PlanAnalyzer should run for this phase"""

    # Never run if disabled
    if not self.enable_plan_analyzer:
        return False

    # High confidence - skip
    if confidence >= 0.70:
        return False

    # Low confidence with empty scope - run
    if confidence < 0.15 and len(scope) == 0:
        return True

    # Medium confidence with ambiguous match - run
    if 0.15 <= confidence < 0.30:
        # Check if category match is ambiguous
        # (e.g., multiple categories with similar scores)
        return True

    return False
```

**Why**: Clear criteria for when LLM analysis adds value

### 3. **Async/Sync Integration**

```python
from autopack.manifest_generator import run_async_safe

# Inside generate_manifest()
if should_analyze_phase:
    analyzer = self._get_or_create_plan_analyzer()

    # Use Phase B helper for async boundary
    analysis = run_async_safe(
        analyzer.analyze_phase(
            phase_spec=phase,
            context=grounded_context.to_prompt_section()
        )
    )
```

**Why**: PlanAnalyzer.analyze_phase() is async, ManifestGenerator is sync

### 4. **Error Handling & Fallback**

```python
try:
    analysis = run_async_safe(analyzer.analyze_phase(...))
    plan_analysis_metadata.status = "ran"
    # Attach to phase metadata (never override scope)
    phase["metadata"]["plan_analysis"] = {
        "feasible": analysis.feasible,
        "confidence": analysis.confidence,
        "concerns": analysis.concerns,
        "recommendations": analysis.recommendations
    }
except TimeoutError as e:
    plan_analysis_metadata.status = "failed"
    plan_analysis_metadata.error = f"LLM timeout: {e}"
    # Fall back to deterministic scope (already set)
except Exception as e:
    plan_analysis_metadata.status = "failed"
    plan_analysis_metadata.error = f"Analysis failed: {e}"
    # Fall back to deterministic scope
```

**Why**: LLM failures must not break manifest generation

### 5. **Scope Preservation**

```python
# CRITICAL: Never override deterministic scope
# PlanAnalyzer results are advisory only

# ❌ WRONG:
if analysis.recommended_scope:
    phase["scope"]["paths"] = analysis.recommended_scope

# ✅ CORRECT:
# Keep deterministic scope unchanged
# Attach LLM analysis as metadata for human review
phase["metadata"]["plan_analysis"] = {
    "feasible": analysis.feasible,
    "llm_recommended_scope": analysis.recommended_scope,  # Advisory only
    "concerns": analysis.concerns
}
```

**Why**: Deterministic scope is trusted, LLM is advisory

### 6. **Phase Count Limit**

```python
MAX_PHASES_TO_ANALYZE = 3

analyzed_count = 0
for phase in phases:
    if analyzed_count >= MAX_PHASES_TO_ANALYZE:
        plan_analysis_metadata.warnings.append(
            f"Analyzed max {MAX_PHASES_TO_ANALYZE} phases, skipping remaining"
        )
        break

    if should_trigger(phase):
        # Run analysis
        analyzed_count += 1
```

**Why**: Control cost (max 3 LLM calls per run)

### 7. **Grounded Context Integration**

```python
from autopack.plan_analyzer_grounding import GroundedContextBuilder

# Build grounded context for each phase
context_builder = GroundedContextBuilder(
    repo_scanner=self.scanner,
    pattern_matcher=self.matcher,
    max_chars=4000
)

grounded_context = context_builder.build_context(
    goal=phase["goal"],
    phase_id=phase["phase_id"],
    description=phase.get("description", ""),
    match_result=pattern_match_result  # Reuse from pattern matching
)

# Pass to PlanAnalyzer
analysis = analyzer.analyze_phase(
    phase_spec=phase,
    context=grounded_context.to_prompt_section()  # Use Phase C builder
)
```

**Why**: Leverage Phase C deterministic context (no redundant work)

---

## Import Path Issues to Resolve

### Issue 1: LLMService Import

**Current**: Tests try to patch `autopack.plan_analyzer.LLMService`
**Actual**: Need to check if it's `autopack.llm_service.LLMService`

**Check**:
```python
# In plan_analyzer.py, what's the actual import?
from autopack.llm_service import LLMService  # If this
# Then patch: autopack.llm_service.LLMService

# OR if it's:
from .llm_service import LLMService
# Then patch still: autopack.llm_service.LLMService
```

### Issue 2: PlanAnalyzer Not in manifest_generator

**Current**: No import in manifest_generator.py
**Needed**: Conditional lazy import

```python
# Only import when actually needed
if self.enable_plan_analyzer and should_trigger:
    from autopack.plan_analyzer import PlanAnalyzer
```

---

## Implementation Checklist

Based on test requirements, Phase D needs:

- [ ] Add conditional `PlanAnalyzer` import to `manifest_generator.py`
- [ ] Implement `_should_trigger_plan_analyzer()` method
- [ ] Add `_get_or_create_plan_analyzer()` lazy initialization
- [ ] Integrate `GroundedContextBuilder` in manifest flow
- [ ] Add try/except error handling for LLM calls
- [ ] Implement timeout protection (default 30s?)
- [ ] Add phase count tracking (`MAX_PHASES_TO_ANALYZE = 3`)
- [ ] Ensure scope is NEVER overridden (attach as metadata only)
- [ ] Fix import paths for test mocking
- [ ] Add logging for trigger decisions
- [ ] Update `plan_analysis` metadata status tracking

---

## Success Criteria

Phase D implementation is complete when:

1. ✅ All 14 integration tests pass
2. ✅ `enable_plan_analyzer=False` → zero LLM imports (confirmed via tests)
3. ✅ `enable_plan_analyzer=True` → conditional LLM use based on confidence
4. ✅ Timeout/error handling prevents manifest generation failures
5. ✅ Deterministic scope is never overridden
6. ✅ Max 3 phases analyzed per run
7. ✅ Grounded context from Phase C is used for all LLM calls

---

## Estimated Complexity

**Lines of Code**: ~150-200 lines
**Files Modified**: 1 ([manifest_generator.py](../src/autopack/manifest_generator.py))
**Risk Level**: Medium (LLM integration, async boundary, error handling)

**Recommendation**: Implement incrementally, running tests after each change

---

## Next Steps

1. Review llm_service.py to confirm LLMService import path
2. Implement `_should_trigger_plan_analyzer()` trigger logic
3. Add conditional PlanAnalyzer import and lazy initialization
4. Integrate GroundedContextBuilder in manifest flow
5. Add error handling and timeout protection
6. Implement phase count limiting
7. Run tests iteratively until all 14 pass
8. Document final behavior in BUILD-123v2_COMPLETION.md

---

## Questions for User/Other Cursor

1. **Timeout Duration**: What timeout should we use for LLM calls? (Suggest: 30s)
2. **Cost Control**: Is max 3 phases per run acceptable, or should it be configurable?
3. **Error Behavior**: On LLM failure, should we log warnings or fail silently?
4. **Scope Override**: Confirm LLM recommendations should NEVER replace deterministic scope (only attach as metadata)
5. **Priority Sorting**: When >3 phases need analysis, should we prioritize lowest confidence first?
