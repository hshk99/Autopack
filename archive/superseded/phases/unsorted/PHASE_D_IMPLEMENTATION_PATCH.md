# Phase D Implementation Patch

This document contains all changes needed to complete Phase D implementation in `manifest_generator.py`.

## Change 1: Add Missing Imports

**Location**: Lines 44-49

**Current**:
```python
import asyncio
import concurrent.futures
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
```

**New**:
```python
import asyncio
import concurrent.futures
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
```

## Change 2: Add Context Builder Lazy Init in __init__

**Location**: After line 147 (after `self._plan_analyzer = None`)

**Add**:
```python
        self._context_builder = None  # Phase C lazy init (BUILD-124)
```

## Change 3: Modify _enhance_phase to Store match_result

**Location**: Lines 247-332 (entire _enhance_phase method)

**Current** method returns:
```python
return enhanced_phase, match_result.confidence, warnings
```

**Change** to return match_result for Phase D:
```python
# Store match_result in phase metadata for PlanAnalyzer (BUILD-124)
enhanced_phase["metadata"]["_match_result"] = match_result

return enhanced_phase, match_result.confidence, warnings
```

## Change 4: Add Phase D Integration in generate_manifest

**Location**: Between lines 202 and 203 (after collecting enhanced_phases, before building enhanced_plan)

**Add**:
```python
        # BUILD-124 Phase D: Optional PlanAnalyzer integration
        plan_analysis_warnings = []
        if self.enable_plan_analyzer:
            plan_analysis_warnings = self._run_plan_analyzer_on_phases(
                enhanced_phases,
                confidence_scores
            )
            warnings.extend(plan_analysis_warnings)
```

## Change 5: Add All Phase D Helper Methods

**Location**: After line 459 (end of file, add these methods to the ManifestGenerator class)

**Add these 7 new methods**:

```python
    # BUILD-124 Phase D: PlanAnalyzer Integration Methods

    MAX_PHASES_TO_ANALYZE = 3  # Cost control limit

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

    def _should_trigger_plan_analyzer(
        self,
        confidence: float,
        scope: List[str],
        category: str
    ) -> bool:
        """
        Determine if PlanAnalyzer should run for this phase.

        Trigger logic (per Phase D guidance):
        - High confidence (>= 0.70): Skip (deterministic is working well)
        - Low confidence (< 0.15) + empty scope: Always trigger
        - Medium confidence (0.15-0.30) + small scope/unknown category: Trigger
        """
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

    def _select_phases_for_analysis(
        self,
        phases: List[Dict],
        confidence_scores: Dict[str, float]
    ) -> List[Dict]:
        """
        Select up to MAX_PHASES_TO_ANALYZE phases, prioritizing lowest confidence.

        Returns list of phases to analyze, sorted by confidence (lowest first).
        """
        # Filter phases that should trigger PlanAnalyzer
        candidates = []
        for phase in phases:
            phase_id = phase.get("phase_id", "")
            confidence = confidence_scores.get(phase_id, 1.0)
            scope = phase.get("scope", {}).get("paths", [])
            category = phase.get("metadata", {}).get("category", "unknown")

            if self._should_trigger_plan_analyzer(confidence, scope, category):
                candidates.append((phase, confidence))

        # Sort by confidence (lowest first)
        candidates.sort(key=lambda x: x[1])

        # Take top MAX_PHASES_TO_ANALYZE
        selected = [phase for phase, _ in candidates[:self.MAX_PHASES_TO_ANALYZE]]

        # Log if we skipped any
        if len(candidates) > self.MAX_PHASES_TO_ANALYZE:
            skipped = len(candidates) - self.MAX_PHASES_TO_ANALYZE
            logger.info(
                f"Selected {self.MAX_PHASES_TO_ANALYZE} lowest-confidence phases for analysis, "
                f"skipped {skipped} additional candidates"
            )

        return selected

    async def _run_plan_analyzer_with_timeout(
        self,
        analyzer: Any,
        phase: Dict,
        grounded_context: Any
    ) -> Optional[Any]:
        """
        Run PlanAnalyzer with 30-second timeout protection.

        Returns analysis result on success, None on timeout/error.
        """
        try:
            # 30 second timeout (per Phase D guidance)
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

    def _attach_plan_analysis_metadata(
        self,
        phase: Dict,
        analysis: Optional[Any],
        status: str,
        error: Optional[str] = None
    ) -> None:
        """
        Attach PlanAnalyzer results as metadata (NEVER override deterministic scope).

        Status values: "ran", "failed", "timeout", "skipped", "disabled"
        """
        metadata = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
        }

        if status == "ran" and analysis:
            metadata.update({
                "feasible": getattr(analysis, "feasible", True),
                "confidence": getattr(analysis, "confidence", 0.0),
                "llm_recommended_scope": getattr(analysis, "recommended_scope", []),  # Advisory only
                "concerns": getattr(analysis, "concerns", []),
                "recommendations": getattr(analysis, "recommendations", []),
            })

            # Flag discrepancies between deterministic and LLM scope
            deterministic_scope = set(phase.get("scope", {}).get("paths", []))
            llm_scope = set(getattr(analysis, "recommended_scope", []) or [])

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

    def _run_plan_analyzer_on_phases(
        self,
        phases: List[Dict],
        confidence_scores: Dict[str, float]
    ) -> List[str]:
        """
        Run PlanAnalyzer on selected low-confidence phases.

        Returns list of warnings encountered during analysis.
        """
        warnings = []

        # Select phases to analyze (max 3, lowest confidence first)
        selected_phases = self._select_phases_for_analysis(phases, confidence_scores)

        if not selected_phases:
            logger.info("No phases selected for PlanAnalyzer (all high confidence)")
            return warnings

        logger.info(f"Running PlanAnalyzer on {len(selected_phases)} phases")

        # Get lazy-initialized components
        analyzer = self._get_or_create_plan_analyzer()
        context_builder = self._get_or_create_context_builder()

        # Analyze each selected phase sequentially
        for phase in selected_phases:
            phase_id = phase.get("phase_id", "unknown")

            try:
                # Get stored match_result from phase metadata
                match_result = phase.get("metadata", {}).get("_match_result")

                # Build grounded context (reuse match_result if available)
                grounded_context = context_builder.build_context(
                    goal=phase.get("goal", ""),
                    phase_id=phase_id,
                    description=phase.get("description", ""),
                    match_result=match_result
                )

                if grounded_context.truncated:
                    logger.info(
                        f"Grounded context truncated for phase {phase_id} "
                        f"({grounded_context.total_chars} chars)"
                    )

                # Run PlanAnalyzer with timeout using Phase B helper
                analysis = run_async_safe(
                    self._run_plan_analyzer_with_timeout(
                        analyzer,
                        phase,
                        grounded_context
                    )
                )

                if analysis is None:
                    # Timeout or error occurred
                    self._attach_plan_analysis_metadata(
                        phase,
                        None,
                        "failed",
                        "LLM timeout or error (see logs)"
                    )
                    warnings.append(f"Phase '{phase_id}' PlanAnalyzer failed")
                else:
                    # Success
                    self._attach_plan_analysis_metadata(
                        phase,
                        analysis,
                        "ran"
                    )
                    logger.info(f"PlanAnalyzer completed for phase {phase_id}")

            except Exception as e:
                # Unexpected error (shouldn't happen due to internal error handling)
                error_msg = str(e)[:200]
                logger.error(f"Unexpected error analyzing phase {phase_id}: {error_msg}")
                self._attach_plan_analysis_metadata(
                    phase,
                    None,
                    "failed",
                    f"Unexpected error: {error_msg}"
                )
                warnings.append(f"Phase '{phase_id}' PlanAnalyzer failed unexpectedly")

        # Clean up match_result from metadata (temporary storage)
        for phase in phases:
            if "_match_result" in phase.get("metadata", {}):
                del phase["metadata"]["_match_result"]

        return warnings
```

## Summary of Changes

1. **Imports**: Added `datetime`, `Any`, `Tuple` types
2. **Init**: Added `_context_builder` lazy init
3. **_enhance_phase**: Store match_result in metadata for PlanAnalyzer
4. **generate_manifest**: Call `_run_plan_analyzer_on_phases()` after phase enhancement
5. **7 New Methods**:
   - `_get_or_create_plan_analyzer()`
   - `_get_or_create_context_builder()`
   - `_should_trigger_plan_analyzer()`
   - `_select_phases_for_analysis()`
   - `_run_plan_analyzer_with_timeout()` (async)
   - `_attach_plan_analysis_metadata()`
   - `_run_plan_analyzer_on_phases()` (main orchestrator)

## Lines of Code Added

- Imports: +2 lines
- Init: +1 line
- _enhance_phase: +3 lines
- generate_manifest: +7 lines
- New methods: ~220 lines
- **Total: ~233 lines added**

## Implementation Notes

- All PlanAnalyzer logic is conditional on `enable_plan_analyzer` flag
- Max 3 phases analyzed per run (cost control)
- 30-second timeout per phase
- Deterministic scope NEVER overridden (LLM results are metadata only)
- Grounded context reuses pattern_match_result (no duplicate work)
- Sequential execution (not parallel)
- Graceful error handling with fallback to deterministic scope
