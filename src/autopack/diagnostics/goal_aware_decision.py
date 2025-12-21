"""Goal-Aware Decision Making

Analyzes evidence against phase deliverables and constraints to make autonomous
decisions. Uses goal-oriented reasoning to determine if a fix is safe to auto-apply
or requires human intervention.

Design Goals:
- Goal alignment (does fix meet deliverables?)
- Risk assessment (low/medium/high based on impact)
- Rationale generation (explain the decision)
- Alternative tracking (what else was considered?)
- Conservative approach (prefer escalation over bad fix)
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Any

from autopack.diagnostics.diagnostics_models import (
    Decision,
    DecisionType,
    FixStrategy,
    PhaseSpec,
    RiskLevel,
)

logger = logging.getLogger(__name__)


class GoalAwareDecisionMaker:
    """
    Makes goal-aware decisions based on evidence and phase constraints.

    Responsibilities:
    - Analyze evidence against deliverables
    - Generate fix strategies
    - Assess risk level (LOW/MEDIUM/HIGH)
    - Produce rationale with alternatives
    - Decide: CLEAR_FIX, NEED_MORE_EVIDENCE, AMBIGUOUS, or RISKY
    """

    def __init__(
        self,
        low_risk_threshold: int = 100,
        medium_risk_threshold: int = 200,
        min_confidence_for_auto_fix: float = 0.7,
    ):
        """
        Initialize decision maker.

        Args:
            low_risk_threshold: Max lines for low risk (default: 100)
            medium_risk_threshold: Max lines for medium risk (default: 200)
            min_confidence_for_auto_fix: Min confidence for auto-apply (default: 0.7)
        """
        self.low_risk_threshold = low_risk_threshold
        self.medium_risk_threshold = medium_risk_threshold
        self.min_confidence_for_auto_fix = min_confidence_for_auto_fix

    def make_decision(
        self,
        evidence: Dict[str, Any],
        phase_spec: PhaseSpec
    ) -> Decision:
        """
        Make goal-aware decision based on evidence and constraints.

        Args:
            evidence: All collected evidence (diagnostics, probes, files)
            phase_spec: Deliverables, acceptance criteria, path constraints

        Returns:
            Decision object with type, rationale, risk assessment
        """
        logger.info(f"[GoalAwareDecisionMaker] Analyzing evidence for {phase_spec.phase_id}")

        # Extract key information from evidence
        failure_class = evidence.get("failure_context", {}).get("failure_class", "unknown")
        error_message = evidence.get("failure_context", {}).get("error_message", "")

        # Check if we have sufficient evidence
        if not self._has_sufficient_evidence(evidence):
            logger.info("[GoalAwareDecisionMaker] Insufficient evidence, requesting more")
            return Decision(
                type=DecisionType.NEED_MORE_EVIDENCE,
                fix_strategy="",
                rationale="Insufficient evidence to determine root cause. Need more diagnostic data.",
                alternatives_considered=[],
                risk_level=RiskLevel.UNKNOWN.value,
                deliverables_met=[],
                files_modified=[],
                net_deletion=0,
            )

        # Generate fix strategies based on evidence
        strategies = self._generate_fix_strategies(evidence, phase_spec)

        if not strategies:
            # No clear fix strategy identified
            logger.info("[GoalAwareDecisionMaker] No clear fix strategy, escalating")
            return Decision(
                type=DecisionType.AMBIGUOUS,
                fix_strategy="",
                rationale=f"No clear fix strategy identified for {failure_class}. "
                          f"Evidence collected but root cause unclear.",
                alternatives_considered=[
                    "Continue investigation (rejected: already collected standard evidence)",
                    "Escalate to human (selected: requires human judgment)"
                ],
                risk_level=RiskLevel.UNKNOWN.value,
                deliverables_met=[],
                files_modified=[],
                net_deletion=0,
                questions_for_human=[
                    f"What is the root cause of this {failure_class}?",
                    "What approach should be taken to fix it?",
                ]
            )

        # Rank strategies by confidence and risk
        best_strategy = max(strategies, key=lambda s: s.confidence)

        # Assess risk
        risk_level = self._assess_risk(best_strategy, phase_spec)

        # Check goal alignment
        goal_alignment = self._check_goal_alignment(
            best_strategy,
            phase_spec.deliverables,
            phase_spec.acceptance_criteria
        )

        # Generate alternatives list
        alternatives = self._generate_alternatives(strategies, best_strategy)

        # Decide based on risk, confidence, and goal alignment
        if risk_level == RiskLevel.HIGH:
            # High risk - always block
            logger.info("[GoalAwareDecisionMaker] HIGH RISK - blocking for approval")
            return Decision(
                type=DecisionType.RISKY,
                fix_strategy=best_strategy.description,
                rationale=self._generate_rationale(
                    best_strategy, risk_level, goal_alignment, "HIGH_RISK"
                ),
                alternatives_considered=alternatives,
                risk_level=risk_level.value,
                deliverables_met=best_strategy.meets_deliverables,
                files_modified=best_strategy.files_to_modify,
                net_deletion=self._estimate_net_deletion(best_strategy),
                confidence=best_strategy.confidence,
                questions_for_human=[
                    "Approve high-risk fix?",
                    f"Fix will modify {len(best_strategy.files_to_modify)} files "
                    f"({best_strategy.estimated_lines_changed} lines)"
                ]
            )

        if best_strategy.confidence < self.min_confidence_for_auto_fix:
            # Low confidence - escalate
            logger.info(f"[GoalAwareDecisionMaker] Low confidence ({best_strategy.confidence:.2f}), escalating")
            return Decision(
                type=DecisionType.AMBIGUOUS,
                fix_strategy=best_strategy.description,
                rationale=self._generate_rationale(
                    best_strategy, risk_level, goal_alignment, "LOW_CONFIDENCE"
                ),
                alternatives_considered=alternatives,
                risk_level=risk_level.value,
                deliverables_met=best_strategy.meets_deliverables,
                files_modified=best_strategy.files_to_modify,
                net_deletion=self._estimate_net_deletion(best_strategy),
                confidence=best_strategy.confidence,
                questions_for_human=[
                    f"Is this the correct approach? (confidence: {best_strategy.confidence:.0%})",
                    "Are there alternative solutions?"
                ]
            )

        if not goal_alignment["meets_deliverables"]:
            # Doesn't meet deliverables - escalate
            logger.info("[GoalAwareDecisionMaker] Does not meet deliverables, escalating")
            return Decision(
                type=DecisionType.AMBIGUOUS,
                fix_strategy=best_strategy.description,
                rationale=self._generate_rationale(
                    best_strategy, risk_level, goal_alignment, "MISSING_DELIVERABLES"
                ),
                alternatives_considered=alternatives,
                risk_level=risk_level.value,
                deliverables_met=best_strategy.meets_deliverables,
                files_modified=best_strategy.files_to_modify,
                net_deletion=self._estimate_net_deletion(best_strategy),
                confidence=best_strategy.confidence,
                questions_for_human=[
                    "Fix does not create all required deliverables - proceed anyway?",
                    f"Missing: {goal_alignment['missing_deliverables']}"
                ]
            )

        # Low/Medium risk, high confidence, meets deliverables - CLEAR_FIX
        logger.info(f"[GoalAwareDecisionMaker] CLEAR_FIX - {risk_level.value} risk, {best_strategy.confidence:.0%} confidence")
        return Decision(
            type=DecisionType.CLEAR_FIX,
            fix_strategy=best_strategy.description,
            rationale=self._generate_rationale(
                best_strategy, risk_level, goal_alignment, "CLEAR"
            ),
            alternatives_considered=alternatives,
            risk_level=risk_level.value,
            deliverables_met=best_strategy.meets_deliverables,
            files_modified=best_strategy.files_to_modify,
            net_deletion=self._estimate_net_deletion(best_strategy),
            confidence=best_strategy.confidence,
            patch=self._generate_patch_stub(best_strategy),  # Stub for now
        )

    def _has_sufficient_evidence(self, evidence: Dict[str, Any]) -> bool:
        """
        Check if we have sufficient evidence to make a decision.

        Heuristic: Need at least one of:
        - Error message with stack trace
        - Test output showing failures
        - File content from relevant modules
        - Probe results with actionable information
        """
        failure_context = evidence.get("failure_context", {})
        error_message = failure_context.get("error_message", "")

        # Check for error message
        if error_message and len(error_message) > 50:
            return True

        # Check for diagnostics results
        initial_diag = evidence.get("initial_diagnostics", {})
        if initial_diag.get("probe_count", 0) > 0:
            return True

        # Check for any round results
        round_keys = [k for k in evidence.keys() if k.startswith("round_")]
        if len(round_keys) > 0:
            return True

        return False

    def _generate_fix_strategies(
        self,
        evidence: Dict[str, Any],
        phase_spec: PhaseSpec
    ) -> List[FixStrategy]:
        """
        Generate potential fix strategies based on evidence.

        Strategy generation is heuristic-based for common failure patterns.
        """
        strategies: List[FixStrategy] = []
        failure_class = evidence.get("failure_context", {}).get("failure_class", "unknown").lower()
        error_message = evidence.get("failure_context", {}).get("error_message", "")

        # Strategy 1: Import error -> add missing import
        if "import" in failure_class or "ImportError" in error_message or "ModuleNotFoundError" in error_message:
            # Extract module name from error message
            module_match = re.search(r"cannot import name '(\w+)'", error_message)
            if module_match:
                module_name = module_match.group(1)

                # Find __init__.py file from deliverables (most common case)
                target_files = [d for d in phase_spec.deliverables if d.endswith('__init__.py')]

                if not target_files:
                    # Fallback: derive from phase_id
                    target_files = [f"src/autopack/{phase_spec.phase_id.replace('-', '/')}/__init__.py"]

                # Use the first __init__.py file as the target
                target_file = target_files[0]

                # Match all deliverables that are __init__.py files
                # (since adding import satisfies the requirement to create/update __init__.py)
                met_deliverables = [d for d in phase_spec.deliverables if d.endswith('__init__.py')]

                strategies.append(FixStrategy(
                    description=f"Add missing import for '{module_name}' to __init__.py",
                    files_to_modify=[target_file],
                    estimated_lines_changed=1,
                    touches_protected_paths=False,
                    meets_deliverables=met_deliverables,
                    passes_acceptance_criteria=[c for c in phase_spec.acceptance_criteria if "import" in c.lower()],
                    side_effects=[],
                    confidence=0.85,
                ))

        # Strategy 2: Test failure -> fix test or implementation
        if "test" in failure_class or "ci_fail" in failure_class:
            strategies.append(FixStrategy(
                description="Fix failing tests by correcting implementation",
                files_to_modify=[],  # Will be determined from test output
                estimated_lines_changed=10,
                touches_protected_paths=False,
                meets_deliverables=phase_spec.deliverables,
                passes_acceptance_criteria=[c for c in phase_spec.acceptance_criteria if "test" in c.lower()],
                side_effects=["May affect existing functionality"],
                confidence=0.6,
            ))

        # Strategy 3: Patch failure -> resolve conflicts
        if "patch" in failure_class:
            strategies.append(FixStrategy(
                description="Resolve git conflicts and reapply patch",
                files_to_modify=[],
                estimated_lines_changed=5,
                touches_protected_paths=False,
                meets_deliverables=phase_spec.deliverables,
                passes_acceptance_criteria=[],
                side_effects=[],
                confidence=0.7,
            ))

        logger.info(f"[GoalAwareDecisionMaker] Generated {len(strategies)} fix strategies")
        return strategies

    def _assess_risk(
        self,
        fix_strategy: FixStrategy,
        phase_spec: PhaseSpec
    ) -> RiskLevel:
        """
        Assess risk level of a fix strategy.

        Risk factors:
        - HIGH: >200 lines, protected paths, breaking changes
        - MEDIUM: 100-200 lines, multiple files
        - LOW: <100 lines, within allowed_paths, no side effects
        """
        # Check protected paths
        if fix_strategy.touches_protected_paths:
            logger.info("[GoalAwareDecisionMaker] HIGH RISK: touches protected paths")
            return RiskLevel.HIGH

        for file_path in fix_strategy.files_to_modify:
            for protected in phase_spec.protected_paths:
                if file_path.startswith(protected):
                    logger.info(f"[GoalAwareDecisionMaker] HIGH RISK: {file_path} in protected path {protected}")
                    return RiskLevel.HIGH

        # Check line count
        if fix_strategy.estimated_lines_changed > self.medium_risk_threshold:
            logger.info(f"[GoalAwareDecisionMaker] HIGH RISK: {fix_strategy.estimated_lines_changed} lines (>{self.medium_risk_threshold})")
            return RiskLevel.HIGH

        if fix_strategy.estimated_lines_changed > self.low_risk_threshold:
            logger.info(f"[GoalAwareDecisionMaker] MEDIUM RISK: {fix_strategy.estimated_lines_changed} lines")
            return RiskLevel.MEDIUM

        # Check side effects
        if fix_strategy.side_effects:
            logger.info(f"[GoalAwareDecisionMaker] MEDIUM RISK: has side effects")
            return RiskLevel.MEDIUM

        # Low risk
        logger.info(f"[GoalAwareDecisionMaker] LOW RISK: {fix_strategy.estimated_lines_changed} lines, no side effects")
        return RiskLevel.LOW

    def _check_goal_alignment(
        self,
        fix_strategy: FixStrategy,
        deliverables: List[str],
        acceptance_criteria: List[str]
    ) -> Dict[str, Any]:
        """
        Verify fix advances toward goals.

        Returns:
            Dictionary with:
            - meets_deliverables: bool
            - missing_deliverables: List[str]
            - passes_acceptance: bool
            - missing_acceptance: List[str]
        """
        # Check deliverables (simplified heuristic)
        met_deliverables = set(fix_strategy.meets_deliverables)
        all_deliverables = set(deliverables)
        missing = all_deliverables - met_deliverables

        # Check acceptance criteria
        passed_criteria = set(fix_strategy.passes_acceptance_criteria)
        all_criteria = set(acceptance_criteria)
        missing_criteria = all_criteria - passed_criteria

        return {
            "meets_deliverables": len(missing) == 0,
            "missing_deliverables": list(missing),
            "passes_acceptance": len(missing_criteria) == 0,
            "missing_acceptance": list(missing_criteria),
        }

    def _generate_rationale(
        self,
        strategy: FixStrategy,
        risk_level: RiskLevel,
        goal_alignment: Dict[str, Any],
        reason: str
    ) -> str:
        """Generate detailed rationale for the decision."""
        parts = []

        # Lead with the decision reason
        if reason == "CLEAR":
            parts.append(
                f"Clear fix identified with {strategy.confidence:.0%} confidence. "
                f"Strategy: {strategy.description}"
            )
        elif reason == "HIGH_RISK":
            parts.append(
                f"High-risk fix requiring approval. "
                f"Strategy: {strategy.description}"
            )
        elif reason == "LOW_CONFIDENCE":
            parts.append(
                f"Low confidence ({strategy.confidence:.0%}) in fix strategy. "
                f"Strategy: {strategy.description}"
            )
        elif reason == "MISSING_DELIVERABLES":
            parts.append(
                f"Fix does not meet all deliverables. "
                f"Strategy: {strategy.description}"
            )

        # Add goal alignment
        if goal_alignment["meets_deliverables"]:
            parts.append(
                f"Meets deliverables: {', '.join(strategy.meets_deliverables)}"
            )
        else:
            parts.append(
                f"Missing deliverables: {', '.join(goal_alignment['missing_deliverables'])}"
            )

        # Add risk assessment
        parts.append(
            f"Risk: {risk_level.value} "
            f"({strategy.estimated_lines_changed} lines, "
            f"{len(strategy.files_to_modify)} files)"
        )

        # Add side effects if any
        if strategy.side_effects:
            parts.append(f"Side effects: {', '.join(strategy.side_effects)}")
        else:
            parts.append("No side effects detected")

        return ". ".join(parts) + "."

    def _generate_alternatives(
        self,
        all_strategies: List[FixStrategy],
        selected: FixStrategy
    ) -> List[str]:
        """Generate list of alternatives considered."""
        alternatives = []

        for strategy in all_strategies:
            if strategy == selected:
                alternatives.append(
                    f"{strategy.description} (SELECTED: {strategy.confidence:.0%} confidence)"
                )
            else:
                alternatives.append(
                    f"{strategy.description} (rejected: {strategy.confidence:.0%} confidence, "
                    f"{len(strategy.side_effects)} side effects)"
                )

        if not alternatives:
            alternatives.append("No alternative strategies identified")

        return alternatives

    def _estimate_net_deletion(self, strategy: FixStrategy) -> int:
        """
        Estimate net line deletion (lines removed - lines added).

        For now, use simple heuristic based on strategy type.
        """
        # Import additions are typically net negative (adding lines)
        if "import" in strategy.description.lower():
            return -1

        # Default: assume balanced changes
        return 0

    def _generate_patch_stub(self, strategy: FixStrategy) -> Optional[str]:
        """
        Generate patch for auto-fix.

        Generates actual diff by reading file content and creating the modified version.
        """
        # For import fixes, generate import addition patch
        if "import" in strategy.description.lower():
            # Extract module name
            match = re.search(r"'(\w+)'", strategy.description)
            if match and strategy.files_to_modify:
                module_name = match.group(1)
                file_path = strategy.files_to_modify[0]

                # Read current file content (if exists)
                from pathlib import Path
                full_path = Path(file_path)

                if full_path.exists():
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            current_content = f.read()
                    except Exception as e:
                        logger.warning(f"[GoalAwareDecisionMaker] Could not read {file_path}: {e}")
                        current_content = ""
                else:
                    # File doesn't exist - create new content
                    current_content = ""

                # Generate new content with import added
                import_line = f"from .{module_name.lower()} import {module_name}\n"

                if current_content:
                    # Add import at the beginning (after any existing imports)
                    lines = current_content.split('\n')

                    # Find last import line
                    last_import_idx = -1
                    for i, line in enumerate(lines):
                        if line.strip().startswith(('from ', 'import ')):
                            last_import_idx = i

                    # Insert after last import, or at beginning
                    if last_import_idx >= 0:
                        lines.insert(last_import_idx + 1, import_line.rstrip())
                    else:
                        lines.insert(0, import_line.rstrip())

                    new_content = '\n'.join(lines)
                else:
                    # Empty file - just add the import
                    new_content = import_line

                # Generate unified diff
                import difflib
                current_lines = current_content.splitlines(keepends=True)
                new_lines = new_content.splitlines(keepends=True)

                diff = difflib.unified_diff(
                    current_lines,
                    new_lines,
                    fromfile=f"a/{file_path}",
                    tofile=f"b/{file_path}",
                    lineterm=''
                )

                patch_content = ''.join(diff)
                if patch_content:
                    return patch_content
                else:
                    logger.warning("[GoalAwareDecisionMaker] Generated patch is empty")
                    return None

        return None
