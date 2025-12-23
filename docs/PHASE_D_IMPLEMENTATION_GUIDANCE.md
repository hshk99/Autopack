# Phase D Implementation Guidance - Detailed Answers

**Date**: 2025-12-22
**Status**: Implementation Guidance for BUILD-124 Phase D

---

## Concern 1: Trigger Logic Precision

### Answers:

**Q1: For medium confidence (0.15-0.30), should we ALWAYS trigger?**
**A1**: No. Only trigger when there's genuine ambiguity. Medium confidence alone doesn't guarantee the LLM will help.

**Q2: What constitutes "ambiguous"?**
**A2**: Ambiguous means:
- **Empty or very small scope** (< 3 files) with medium confidence → suggests pattern matcher uncertain
- **Category match with low keyword count** (< 2 keywords) → weak signal
- **NOT**: High file count (that's a different concern)

**Q3: Should we add a safety trigger for high file counts?**
**A3**: No. If confidence is high and scope is large, the pattern matcher is working well. Adding a safety trigger would waste LLM calls. Instead, trust the deterministic matcher at high confidence.

### Recommended Implementation:

```python
def _should_trigger_plan_analyzer(
    self,
    confidence: float,
    scope: List[str],
    category: str
) -> bool:
    """Determine if PlanAnalyzer should run"""

    if not self.enable_plan_analyzer:
        return False

    # High confidence - skip (deterministic matcher is working)
    if confidence >= 0.70:
        return False

    # Low confidence with empty scope - ALWAYS trigger
    if confidence < 0.15 and len(scope) == 0:
        return True

    # Medium confidence - trigger ONLY if ambiguous
    if 0.15 <= confidence < 0.30:
        # Ambiguous if: small scope (< 3 files) OR category is "unknown"
        if len(scope) < 3 or category == "unknown":
            return True

    return False
```

---

## Concern 2: Error Handling Strategy

### Answers:

**Q1: Should timeout errors be treated differently?**
**A1**: Yes, log as WARNING (not ERROR). Timeouts are expected with slow LLM responses. Log separately for debugging.

**Q2: Should we retry on transient errors?**
**A2**: No. Retries add complexity and unpredictable latency. Single attempt with clear timeout. If it fails, fall back to deterministic scope.

**Q3: What's the recommended timeout?**
**A3**: **30 seconds** for all phases. Claude Sonnet 4.5 is fast enough. Don't make it configurable yet (YAGNI).

**Q4: Should we log the full error or sanitize?**
**A4**: Sanitize. Log error type and first 200 chars of message (avoid API keys, tokens).

### Recommended Implementation:

```python
import asyncio
from typing import Optional

async def _run_plan_analyzer_with_timeout(
    self,
    analyzer,
    phase: Dict,
    grounded_context: GroundedContext
) -> Optional[Any]:
    """Run PlanAnalyzer with timeout protection"""

    try:
        # 30 second timeout
        analysis = await asyncio.wait_for(
            analyzer.analyze_phase(
                phase_spec=phase,
                context=grounded_context.to_prompt_section()
            ),
            timeout=30.0
        )
        return analysis

    except asyncio.TimeoutError:
        logger.warning(
            f"PlanAnalyzer timeout for phase {phase.get('phase_id', 'unknown')} "
            f"(exceeded 30s)"
        )
        return None

    except Exception as e:
        # Sanitize error message (max 200 chars)
        error_msg = str(e)[:200]
        logger.error(
            f"PlanAnalyzer failed for phase {phase.get('phase_id', 'unknown')}: "
            f"{type(e).__name__}: {error_msg}"
        )
        return None
```

---

## Concern 3: Phase Count Limiting Strategy

### Answers:

**Q1: Should we prioritize which phases to analyze?**
**A1**: Yes. **Lowest confidence first**. These phases are most likely to benefit from LLM analysis.

**Q2: Is max 3 phases the right limit?**
**A2**: Yes. Keep it simple and non-configurable for now. 3 LLM calls at ~$0.01 each = $0.03 per run (acceptable). Don't optimize prematurely.

**Q3: Should we warn the user when we skip phases?**
**A3**: Yes. Add to `plan_analysis.warnings` at INFO level (not ERROR/WARNING). User should know but it's not a problem.

**Q4: Should phases be analyzed in parallel or sequentially?**
**A4**: **Sequential**. Simpler implementation, easier debugging, avoids cost spikes. Parallel can be added later if needed (YAGNI).

### Recommended Implementation:

```python
MAX_PHASES_TO_ANALYZE = 3

def _select_phases_for_analysis(
    self,
    phases: List[Dict],
    confidence_scores: Dict[str, float]
) -> List[Dict]:
    """Select up to MAX_PHASES_TO_ANALYZE phases, prioritizing lowest confidence"""

    # Filter phases that should trigger PlanAnalyzer
    candidates = [
        (phase, confidence_scores.get(phase.get("phase_id", ""), 1.0))
        for phase in phases
        if self._should_trigger_plan_analyzer(
            confidence=confidence_scores.get(phase.get("phase_id", ""), 1.0),
            scope=phase.get("scope", {}).get("paths", []),
            category=phase.get("metadata", {}).get("category", "unknown")
        )
    ]

    # Sort by confidence (lowest first)
    candidates.sort(key=lambda x: x[1])

    # Take top MAX_PHASES_TO_ANALYZE
    selected = [phase for phase, _ in candidates[:MAX_PHASES_TO_ANALYZE]]

    # Warn if we skipped any
    if len(candidates) > MAX_PHASES_TO_ANALYZE:
        skipped = len(candidates) - MAX_PHASES_TO_ANALYZE
        logger.info(
            f"Selected {MAX_PHASES_TO_ANALYZE} lowest-confidence phases for analysis, "
            f"skipped {skipped} additional candidates"
        )

    return selected
```

---

## Concern 4: Scope Override Protection

### Answers:

**Q1: Should we EVER use LLM-recommended scope?**
**A1**: **Never** in Phase D. Deterministic scope is the source of truth. LLM recommendations are advisory metadata only.

**Q2: Should we flag discrepancies?**
**A2**: Yes. If LLM recommends files not in deterministic scope, add to `concerns` list. Don't block, just inform.

**Q3: Should we merge scopes?**
**A3**: No. Merging adds complexity and unclear semantics. Keep it simple: deterministic scope is used, LLM scope is logged.

**Q4: What if both fail?**
**A4**: Return empty scope with clear status. Don't fail manifest generation. Let preflight validation handle it.

### Recommended Implementation:

```python
def _attach_plan_analysis_metadata(
    self,
    phase: Dict,
    analysis: Any,
    status: str,
    error: Optional[str] = None
) -> None:
    """Attach PlanAnalyzer results as metadata (NEVER override scope)"""

    metadata = {
        "status": status,  # "ran", "failed", "timeout", "skipped", "disabled"
        "timestamp": datetime.now().isoformat(),
    }

    if status == "ran" and analysis:
        metadata.update({
            "feasible": analysis.feasible,
            "confidence": analysis.confidence,
            "llm_recommended_scope": analysis.recommended_scope,  # Advisory only
            "concerns": analysis.concerns,
            "recommendations": analysis.recommendations,
        })

        # Flag discrepancies
        deterministic_scope = set(phase.get("scope", {}).get("paths", []))
        llm_scope = set(analysis.recommended_scope or [])

        if llm_scope and llm_scope != deterministic_scope:
            diff = llm_scope - deterministic_scope
            if diff:
                metadata["scope_discrepancy"] = {
                    "llm_suggested_additional": list(diff),
                    "note": "These files were suggested by LLM but not in deterministic scope"
                }

    if error:
        metadata["error"] = error

    # CRITICAL: Attach to metadata, NEVER to scope
    if "metadata" not in phase:
        phase["metadata"] = {}
    phase["metadata"]["plan_analysis"] = metadata
```

---

## Concern 5: Grounded Context Integration Details

### Answers:

**Q1: Should we cache GroundedContextBuilder?**
**A1**: Create once per ManifestGenerator instance. RepoScanner already caches scan results internally, so this is minimal overhead.

**Q2: Should we reuse pattern_match_result?**
**A2**: Yes. We already ran pattern matching for deterministic scope. Pass it to `build_context()` to avoid duplicate work.

**Q3: Should we include additional context?**
**A3**: No. 4000 chars is already tight. File contents would blow the budget. Stick to the Phase C design.

**Q4: If grounded context truncates, should we proceed?**
**A4**: Yes, proceed anyway. Log at INFO level that truncation occurred. LLM can still provide value with partial context.

### Recommended Implementation:

```python
def __init__(self, ...):
    # ... existing init ...
    self._context_builder = None  # Lazy init

def _get_or_create_context_builder(self):
    """Lazy initialization of GroundedContextBuilder"""
    if self._context_builder is None:
        from autopack.plan_analyzer_grounding import GroundedContextBuilder
        self._context_builder = GroundedContextBuilder(
            repo_scanner=self.scanner,
            pattern_matcher=self.matcher,
            max_chars=4000
        )
    return self._context_builder

def _build_grounded_context_for_phase(
    self,
    phase: Dict,
    match_result: Optional[MatchResult] = None
) -> GroundedContext:
    """Build grounded context, reusing pattern match if available"""

    builder = self._get_or_create_context_builder()

    context = builder.build_context(
        goal=phase.get("goal", ""),
        phase_id=phase.get("phase_id", ""),
        description=phase.get("description", ""),
        match_result=match_result  # Reuse from earlier pattern matching
    )

    if context.truncated:
        logger.info(
            f"Grounded context truncated for phase {phase.get('phase_id', 'unknown')} "
            f"({context.total_chars} chars)"
        )

    return context
```

---

## Concern 6: Lazy Initialization and Import Strategy

### Answers:

**Q1: Should import be at method top or inside __init__?**
**A1**: Inside the lazy getter method. Only import when actually needed (when enabled AND triggered).

**Q2: Should we validate PlanAnalyzer imports successfully?**
**A2**: Let it fail loudly. ImportError should surface immediately if there's a configuration issue. Don't hide errors.

**Q3: Should PlanAnalyzer be constructed once or per phase?**
**A3**: Once per ManifestGenerator instance. PlanAnalyzer is stateless, reuse the same instance.

**Q4: Should we clear the instance after generation?**
**A4**: No. Premature optimization. Let Python GC handle it when ManifestGenerator is destroyed.

### Recommended Implementation:

```python
def __init__(self, enable_plan_analyzer: bool = False, ...):
    # ... existing init ...
    self.enable_plan_analyzer = enable_plan_analyzer
    self._plan_analyzer = None  # Lazy init

def _get_or_create_plan_analyzer(self):
    """Lazy initialization of PlanAnalyzer (only when needed)"""
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

---

## Concern 7: Integration Flow in generate_manifest()

### Answers:

**Q1: Should PlanAnalyzer run before or after scope expansion?**
**A1**: **Before expansion**. LLM should see unexpanded scope (cleaner, less verbose). Expansion is a mechanical process.

**Q2: Should we run PlanAnalyzer in parallel for multiple phases?**
**A2**: No, sequential. Simpler implementation, easier to debug, avoids cost spikes.

**Q3: Should PlanAnalyzer results influence preflight validation?**
**A3**: No. PlanAnalyzer is advisory. Preflight validates deterministic scope only.

**Q4: Where should we attach plan_analysis metadata?**
**A4**: Per-phase only: `phase["metadata"]["plan_analysis"]`. Don't add top-level summary yet (YAGNI).

### Recommended Integration Point:

```python
def generate_manifest(self, plan_data, skip_validation=False):
    # 1. Validate input
    # 2. For each phase:
    #    a. Run pattern matcher (deterministic) → match_result
    #    b. Generate scope from match_result → scope
    #    c. Store confidence score for later
    # 3. ** NEW: Select phases for analysis (max 3, lowest confidence first) **
    # 4. ** NEW: For each selected phase: **
    #    a. Build grounded context (reuse match_result)
    #    b. Run PlanAnalyzer with timeout
    #    c. Attach results as metadata (NEVER override scope)
    # 5. Expand scope (use deterministic scope, ignore LLM)
    # 6. Run preflight validation
    # 7. Return result
```

**Integration happens AFTER deterministic scope generation, BEFORE scope expansion.**

---

## Summary Implementation Checklist

Based on the guidance above, Phase D implementation needs:

- [ ] Add `_should_trigger_plan_analyzer(confidence, scope, category)` method
- [ ] Add `_get_or_create_plan_analyzer()` lazy initialization
- [ ] Add `_get_or_create_context_builder()` lazy initialization
- [ ] Add `_run_plan_analyzer_with_timeout(analyzer, phase, context)` async method
- [ ] Add `_select_phases_for_analysis(phases, confidence_scores)` method
- [ ] Add `_build_grounded_context_for_phase(phase, match_result)` method
- [ ] Add `_attach_plan_analysis_metadata(phase, analysis, status, error)` method
- [ ] Integrate into `generate_manifest()` flow after scope generation, before expansion
- [ ] Use `run_async_safe()` from Phase B for async boundary
- [ ] Fix test import paths (`LlmService` not `LLMService`)
- [ ] Run tests iteratively until 14/14 pass

---

## Key Design Decisions

1. **Trigger Logic**: Low confidence + empty scope → always; Medium confidence → only if < 3 files or unknown category
2. **Timeout**: Hard 30 seconds, no retries, log as WARNING
3. **Phase Limiting**: Max 3 phases, prioritize lowest confidence, sequential execution
4. **Scope Override**: Never. LLM recommendations are metadata only, flag discrepancies in concerns
5. **Context Integration**: Reuse pattern_match_result, proceed even if truncated
6. **Lazy Init**: Import PlanAnalyzer only when enabled AND triggered
7. **Integration Point**: After deterministic scope, before expansion

---

## Estimated Implementation

- **Lines of Code**: ~180-220 lines
- **Methods to Add**: 7 new methods in ManifestGenerator
- **Integration Points**: 1 location in `generate_manifest()`
- **Test Fixes**: Update import paths in 3 tests

**Risk**: Medium (async boundary, error handling, LLM integration)
**Confidence**: High (clear requirements from tests, clear design guidance)

---

This guidance should enable straightforward Phase D implementation with all 14 tests passing.
