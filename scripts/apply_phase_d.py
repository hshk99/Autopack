#!/usr/bin/env python3
"""
Apply Phase D changes to manifest_generator.py

This script applies all Phase D changes in one atomic operation.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

MANIFEST_GEN_PATH = Path(__file__).parent.parent / "src" / "autopack" / "manifest_generator.py"

def main():
    print("Reading manifest_generator.py...")
    with open(MANIFEST_GEN_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    print(f"Current file has {len(lines)} lines")

    # Change 1: Update imports (lines 44-49, 0-indexed: 43-48)
    print("\n1. Updating imports...")
    if lines[43].strip() == "import asyncio":
        lines[46] = "from datetime import datetime\n"  # Insert after logging
        lines[48] = "from typing import Dict, List, Optional, Any, Tuple\n"  # Update typing
        print("   ✓ Imports updated")
    else:
        print("   ✗ Warning: Import section not at expected location")

    # Change 2: Add context_builder lazy init (after line 147, 0-indexed: 146)
    print("\n2. Adding context_builder lazy init...")
    for i, line in enumerate(lines):
        if "self._plan_analyzer = None" in line and i > 140:
            # Insert after this line
            indent = "        "
            lines.insert(i + 1, f"{indent}self._context_builder = None  # Phase C lazy init (BUILD-124)\n")
            print(f"   ✓ Added at line {i+2}")
            break
    else:
        print("   ✗ Warning: Could not find _plan_analyzer = None")

    # Change 3: Modify _enhance_phase to store match_result (before return statement ~line 332)
    print("\n3. Modifying _enhance_phase to store match_result...")
    for i in range(len(lines) - 1, -1, -1):
        if "return enhanced_phase, match_result.confidence, warnings" in lines[i]:
            indent = "        "
            # Insert before return
            lines.insert(i, f"{indent}# Store match_result in phase metadata for PlanAnalyzer (BUILD-124)\n")
            lines.insert(i + 1, f'{indent}enhanced_phase["metadata"]["_match_result"] = match_result\n')
            lines.insert(i + 2, "\n")
            print(f"   ✓ Added at line {i+1}")
            break
    else:
        print("   ✗ Warning: Could not find return statement in _enhance_phase")

    # Change 4: Add Phase D integration in generate_manifest (after collecting enhanced_phases)
    print("\n4. Adding Phase D integration in generate_manifest...")
    for i, line in enumerate(lines):
        if '"phases": enhanced_phases' in line:
            # Insert after the closing }
            if i + 1 < len(lines) and lines[i + 1].strip() == "}":
                indent = "        "
                insert_pos = i + 2
                phase_d_code = f"""
{indent}# BUILD-124 Phase D: Optional PlanAnalyzer integration
{indent}plan_analysis_warnings = []
{indent}if self.enable_plan_analyzer:
{indent}    plan_analysis_warnings = self._run_plan_analyzer_on_phases(
{indent}        enhanced_phases,
{indent}        confidence_scores
{indent}    )
{indent}    warnings.extend(plan_analysis_warnings)

"""
                lines.insert(insert_pos, phase_d_code)
                print(f"   ✓ Added at line {insert_pos}")
                break
    else:
        print("   ✗ Warning: Could not find insertion point for Phase D integration")

    # Change 5: Add all Phase D methods at end of file
    print("\n5. Adding Phase D helper methods at end of file...")

    phase_d_methods = '''
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
'''

    lines.append(phase_d_methods)
    print("   ✓ Added 7 Phase D methods (~220 lines)")

    # Write back
    print(f"\nWriting updated file ({len(lines)} lines)...")
    with open(MANIFEST_GEN_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print("\n✅ Phase D implementation complete!")
    print(f"   Final file: {len(lines)} lines")
    print(f"   Added: ~233 lines")

if __name__ == "__main__":
    main()
