# Prompt for Other Cursor: Phase D Implementation Guidance

## Context

We've successfully completed BUILD-124 Phase C (Grounded Context Builder) and used a test-driven approach to discover concrete Phase D requirements. We now have:

- ✅ **Phase A**: Config flag and plumbing (no LLM calls)
- ✅ **Phase B**: Async/sync boundary helper (`run_async_safe()`)
- ✅ **Phase C**: Grounded context builder (381 lines, 7/7 tests passing)
- ❌ **Phase D**: PlanAnalyzer integration (requirements identified, 7/14 tests failing)

We created 14 integration tests that revealed exactly what needs to be implemented. **7 tests pass** (baseline behavior works), **7 tests fail** (revealing implementation gaps).

## Request for Detailed Guidance

We need your detailed guidance on **Phase D implementation** for the following specific concerns:

---

## Concern 1: Trigger Logic Precision

**Current Understanding**:
```python
def _should_trigger_plan_analyzer(confidence: float, scope: List[str]) -> bool:
    # Low confidence with empty scope
    if confidence < 0.15 and len(scope) == 0:
        return True

    # Medium confidence (ambiguous)
    if 0.15 <= confidence < 0.30:
        return True  # Always trigger?

    return False
```

**Questions**:
1. For **medium confidence (0.15-0.30)**, should we ALWAYS trigger, or only when the category match is "ambiguous"?
2. What constitutes "ambiguous"? Is it:
   - Multiple categories with similar confidence scores? (e.g., top 2 categories within 10% of each other)
   - Low keyword match count but high anchor match?
   - High file count (>50 files) suggesting overly broad scope?
3. Should we add a **"safety trigger"** for high file counts even at higher confidence?
   - Example: confidence=0.60 but scope has 95 files → still trigger to validate?

**Why This Matters**: We want to avoid unnecessary LLM calls while catching edge cases where deterministic matching might be wrong.

**Test Case Reference**: `test_medium_confidence_with_ambiguous_match_triggers_plan_analyzer` currently passes but doesn't test the actual trigger logic.

---

## Concern 2: Error Handling Strategy

**Current Understanding**:
```python
try:
    analysis = run_async_safe(analyzer.analyze_phase(...))
    plan_analysis.status = "ran"
except TimeoutError:
    plan_analysis.status = "failed"
    plan_analysis.error = "LLM timeout"
except Exception as e:
    plan_analysis.status = "failed"
    plan_analysis.error = str(e)
```

**Questions**:
1. Should **timeout errors** be treated differently from other failures?
   - Log as warning vs error?
   - Different status code? ("timeout" vs "failed"?)
2. Should we **retry** on transient errors (network issues, rate limits)?
   - If yes, how many retries? Exponential backoff?
3. What's the **recommended timeout** for LLM calls?
   - 30 seconds seems reasonable, but Claude Sonnet 4.5 might need more time for complex analysis
   - Should it be configurable per phase complexity?
4. Should we **log the full error** or sanitize it? (Avoid leaking API keys, sensitive data)

**Why This Matters**: LLM calls are unreliable. We need robust error handling without breaking manifest generation.

**Test Case Reference**:
- `test_timeout_handling_for_slow_llm_responses`
- `test_error_recovery_on_llm_failure`

---

## Concern 3: Phase Count Limiting Strategy

**Current Understanding**:
```python
MAX_PHASES_TO_ANALYZE = 3

analyzed_count = 0
for phase in phases:
    if analyzed_count >= MAX_PHASES_TO_ANALYZE:
        break

    if should_trigger(phase):
        run_analysis(phase)
        analyzed_count += 1
```

**Questions**:
1. Should we **prioritize** which phases to analyze?
   - Lowest confidence first? (Most likely to benefit from LLM)
   - Earliest phases first? (Dependencies likely more critical)
   - User-specified priority field?
2. Is **max 3 phases** the right limit?
   - Should it scale with total phase count? (e.g., analyze up to 20% of phases)
   - Should it be configurable via `models.yaml` or environment variable?
3. Should we **warn the user** when we skip phases?
   - Add to `plan_analysis.warnings`?
   - Log at what level? (INFO, WARNING, ERROR?)
4. Should phases be **analyzed in parallel** (multiple concurrent LLM calls) or **sequentially**?
   - Parallel could be faster but increases complexity and cost spikes
   - Sequential is safer but slower

**Why This Matters**: Cost control is critical. We need a balanced strategy that analyzes the right phases without runaway costs.

**Test Case Reference**: `test_max_phases_analyzed_per_run`

---

## Concern 4: Scope Override Protection

**Current Understanding**:
```python
# NEVER do this:
# phase["scope"]["paths"] = analysis.recommended_scope  # ❌

# Instead, attach as metadata:
phase["metadata"]["plan_analysis"] = {
    "feasible": analysis.feasible,
    "confidence": analysis.confidence,
    "llm_recommended_scope": analysis.recommended_scope,  # Advisory only
    "concerns": analysis.concerns
}
```

**Questions**:
1. Should we **ever** use LLM-recommended scope?
   - Even if deterministic scope is empty and LLM provides suggestions?
   - What if LLM confidence is very high (>0.90) and deterministic confidence is low (<0.15)?
2. Should we **flag discrepancies** between deterministic and LLM scopes?
   - If they differ significantly, log a warning?
   - Add to `concerns` field for human review?
3. Should we **merge** scopes in some cases?
   - Deterministic scope as baseline + LLM suggestions as optional additions?
   - Mark LLM files as "suggested" vs "required"?
4. What should happen if **both** deterministic and LLM analysis fail?
   - Return empty scope with clear error message?
   - Fail the entire manifest generation?

**Why This Matters**: This is a critical safety boundary. We need to be 100% clear on when (if ever) LLM recommendations affect actual scope.

**Test Case Reference**: `test_plan_analysis_never_overrides_deterministic_scope`

---

## Concern 5: Grounded Context Integration Details

**Current Understanding**:
```python
from autopack.plan_analyzer_grounding import GroundedContextBuilder

context_builder = GroundedContextBuilder(
    repo_scanner=self.scanner,
    pattern_matcher=self.matcher,
    max_chars=4000
)

grounded_context = context_builder.build_context(
    goal=phase["goal"],
    phase_id=phase["phase_id"],
    description=phase.get("description", ""),
    match_result=pattern_match_result  # Reuse from earlier
)

analysis = analyzer.analyze_phase(
    phase_spec=phase,
    context=grounded_context.to_prompt_section()
)
```

**Questions**:
1. Should we **cache** the GroundedContextBuilder instance?
   - Create once per manifest generation? Or once per phase?
   - RepoScanner already caches scan results, so this might be redundant
2. Should we **reuse** pattern_match_result from deterministic scope generation?
   - This saves computation, but what if the LLM needs fresh analysis?
   - Should we re-run pattern matching specifically for PlanAnalyzer?
3. Should we **include additional context** beyond Phase C's grounded context?
   - File contents for key files? (Would exceed 4000 char budget)
   - Git history for the phase's likely scope?
   - Related tests/docs?
4. If grounded context **truncates**, should we:
   - Proceed anyway with truncated context?
   - Skip LLM analysis and use deterministic scope?
   - Log a warning and let user know context was incomplete?

**Why This Matters**: Phase C built the context infrastructure, but we need to use it correctly in Phase D.

**Test Case Reference**: `test_async_plan_analyzer_call_with_grounded_context`

---

## Concern 6: Lazy Initialization and Import Strategy

**Current Understanding**:
```python
# In ManifestGenerator
def __init__(self, enable_plan_analyzer: bool = False):
    self.enable_plan_analyzer = enable_plan_analyzer
    self._plan_analyzer = None  # Lazy init

def _get_or_create_plan_analyzer(self):
    if self._plan_analyzer is None:
        # Lazy import (only when actually needed)
        from autopack.plan_analyzer import PlanAnalyzer
        self._plan_analyzer = PlanAnalyzer(
            repo_scanner=self.scanner,
            pattern_matcher=self.matcher,
            workspace=self.workspace
        )
    return self._plan_analyzer
```

**Questions**:
1. Should the import be **at the top of the method** or **inside `__init__`**?
   - Top-level import if `enable_plan_analyzer=True`?
   - Defer until actual use (current approach)?
2. Should we **validate** that PlanAnalyzer imports successfully?
   - Catch ImportError and set `plan_analysis.status = "failed"`?
   - Or let it fail loudly to surface configuration issues?
3. Should `PlanAnalyzer` be **constructed once** or **per phase**?
   - Current approach: once per ManifestGenerator instance
   - Alternative: create new instance per phase (stateless)
4. Should we **clear the instance** after manifest generation?
   - To avoid holding LLM service connections?
   - Or is this premature optimization?

**Why This Matters**: We want zero overhead when `enable_plan_analyzer=False`, but robust initialization when enabled.

**Test Case Reference**:
- `test_disabled_flag_means_zero_llm_calls`
- `test_enabled_flag_allows_conditional_llm_use`

---

## Concern 7: Integration Flow in generate_manifest()

**Current Flow** (simplified):
```python
def generate_manifest(self, plan_data):
    # 1. Validate input
    # 2. For each phase:
    #    a. Run pattern matcher (deterministic)
    #    b. Generate scope
    #    c. Expand scope
    # 3. Run preflight validation
    # 4. Return result
```

**Proposed Flow with Phase D**:
```python
def generate_manifest(self, plan_data):
    # 1. Validate input
    # 2. For each phase:
    #    a. Run pattern matcher (deterministic)
    #    b. Generate scope
    #    c. ** IF should_trigger: Run PlanAnalyzer **
    #    d. Expand scope (use deterministic, attach LLM as metadata)
    # 3. Run preflight validation
    # 4. Return result
```

**Questions**:
1. Should PlanAnalyzer run **before** or **after** scope expansion?
   - Before: LLM sees unexpanded scope (cleaner)
   - After: LLM sees full file list (might be too verbose)
2. Should we run PlanAnalyzer **in parallel** for multiple phases?
   - Single message with multiple `run_async_safe()` calls?
   - Or sequential to control concurrency?
3. Should PlanAnalyzer results **influence** preflight validation?
   - If LLM says "not feasible", should preflight fail?
   - Or just warn and continue?
4. Where should we **attach** the plan_analysis metadata?
   - Per phase: `phase["metadata"]["plan_analysis"]`
   - Top-level: `result.enhanced_plan["plan_analysis_summary"]`
   - Both?

**Why This Matters**: The integration point determines what information is available to PlanAnalyzer and how results flow through the system.

---

## Summary of Needed Guidance

Please provide detailed guidance on:

1. **Trigger Logic**: Precise conditions for medium confidence scenarios
2. **Error Handling**: Timeout strategy, retry logic, error classification
3. **Phase Limiting**: Prioritization strategy, configurable limits
4. **Scope Override**: Hard rules on when/if LLM affects scope
5. **Context Integration**: Caching, reuse, truncation handling
6. **Lazy Initialization**: Import timing, validation, lifecycle
7. **Integration Flow**: Where PlanAnalyzer fits in the manifest generation pipeline

## What We Have

- ✅ 14 integration tests defining expected behavior
- ✅ Grounded context builder (Phase C) ready to use
- ✅ Async/sync boundary helper (Phase B) ready
- ✅ Config flag infrastructure (Phase A) in place
- ✅ Test failure analysis showing exact gaps

## What We Need

Concrete implementation guidance to make all 14 tests pass while maintaining:
- **Cost control** (max 3 phases, 30s timeout)
- **Safety** (never override deterministic scope)
- **Reliability** (graceful error handling)
- **Zero overhead** when disabled

## Files to Review

For full context, please review:

1. [tests/test_plan_analyzer_integration.py](../tests/test_plan_analyzer_integration.py) - 14 tests defining Phase D behavior
2. [BUILD-124_PHASE_D_REQUIREMENTS.md](BUILD-124_PHASE_D_REQUIREMENTS.md) - Detailed requirements from test discovery
3. [BUILD-124_PHASE_C_COMPLETION_AND_PHASE_D_DISCOVERY.md](BUILD-124_PHASE_C_COMPLETION_AND_PHASE_D_DISCOVERY.md) - Full discovery report
4. [src/autopack/manifest_generator.py](../src/autopack/manifest_generator.py) - Where Phase D will be implemented
5. [src/autopack/plan_analyzer_grounding.py](../src/autopack/plan_analyzer_grounding.py) - Phase C context builder

Thank you for the detailed guidance on the skeleton plan. Your input will help us implement Phase D correctly the first time!
