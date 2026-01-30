"""Intention Memory End-to-End Wiring (Phase 2 of True Autonomy).

Integrates Project Intention Memory into the executor workflow:
- Manifest generation
- Context selection/budgeting
- Builder prompts
- Auditing
- Mid-run replanning / doctor hints

Key principles:
- Compact injection (max 4KB intention context)
- Stable formatting
- Bounded embedding calls (respect caps)
- Goal drift detection includes intention anchor

IMP-CLEAN-002: Updated to use IntentionAnchorV2 instead of deprecated
ProjectIntentionManager (v1 schema).
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .file_layout import RunFileLayout
from .intention_anchor.v2 import IntentionAnchorV2
from .memory import goal_drift
from .memory.memory_service import MemoryService

logger = logging.getLogger(__name__)

# Intention context size cap for prompt injection
MAX_INTENTION_CONTEXT_CHARS = 4096


class IntentionAnchorV2Adapter:
    """Adapter to provide intention context from IntentionAnchorV2.

    IMP-CLEAN-002: This replaces the deprecated ProjectIntentionManager,
    providing a compatible get_intention_context() interface for v2 anchors.
    """

    def __init__(
        self,
        run_id: str,
        project_id: Optional[str] = None,
        memory_service: Optional[MemoryService] = None,
    ):
        """Initialize the v2 anchor adapter.

        Args:
            run_id: Run identifier
            project_id: Project identifier (auto-detected if not provided)
            memory_service: Memory service instance (optional, for future use)
        """
        self.run_id = run_id
        self.layout = RunFileLayout(run_id=run_id, project_id=project_id)
        self.project_id = self.layout.project_id
        self.memory = memory_service
        self._cached_anchor: Optional[IntentionAnchorV2] = None

    def _get_intention_v2_json_path(self) -> Path:
        """Get path to IntentionAnchorV2 JSON artifact."""
        return self.layout.base_dir / "intention" / "intention_anchor_v2.json"

    def _load_anchor(self) -> Optional[IntentionAnchorV2]:
        """Load IntentionAnchorV2 from disk.

        Returns:
            IntentionAnchorV2 if found, None otherwise
        """
        if self._cached_anchor is not None:
            return self._cached_anchor

        v2_json_path = self._get_intention_v2_json_path()
        if not v2_json_path.exists():
            logger.debug(f"[IntentionAnchorV2Adapter] No v2 artifact found: {v2_json_path}")
            return None

        try:
            data = json.loads(v2_json_path.read_text(encoding="utf-8"))
            self._cached_anchor = IntentionAnchorV2.from_json_dict(data)
            logger.debug(
                f"[IntentionAnchorV2Adapter] Loaded v2 anchor: "
                f"project_id={self._cached_anchor.project_id}"
            )
            return self._cached_anchor
        except Exception as exc:
            logger.warning(f"[IntentionAnchorV2Adapter] Failed to load v2 anchor: {exc}")
            return None

    def get_intention_context(self, max_chars: int = 2048) -> str:
        """Get intention context for prompt injection.

        Extracts key intention information from IntentionAnchorV2 and formats
        it for prompt injection, bounded by max_chars.

        Args:
            max_chars: Maximum characters to return

        Returns:
            Formatted intention context (empty string if unavailable)
        """
        anchor = self._load_anchor()
        if not anchor:
            logger.debug("[IntentionAnchorV2Adapter] No intention context available")
            return ""

        # Build context from v2 anchor sections
        lines = ["# Project Intention (v2)", ""]

        # North Star section
        if anchor.pivot_intentions.north_star:
            ns = anchor.pivot_intentions.north_star
            if ns.desired_outcomes:
                lines.append("## Desired Outcomes")
                for outcome in ns.desired_outcomes[:5]:
                    lines.append(f"- {outcome[:150]}")
                lines.append("")

            if ns.non_goals:
                lines.append("## Non-Goals")
                for ng in ns.non_goals[:3]:
                    lines.append(f"- {ng[:150]}")
                lines.append("")

        # Safety/Risk section (abbreviated)
        if anchor.pivot_intentions.safety_risk:
            sr = anchor.pivot_intentions.safety_risk
            if sr.never_allow:
                lines.append("## Safety Constraints")
                for constraint in sr.never_allow[:3]:
                    lines.append(f"- NEVER: {constraint[:100]}")
                lines.append("")

        # Evidence/Verification section (abbreviated)
        if anchor.pivot_intentions.evidence_verification:
            ev = anchor.pivot_intentions.evidence_verification
            if ev.hard_blocks:
                lines.append("## Hard Blocks")
                for block in ev.hard_blocks[:3]:
                    lines.append(f"- {block[:100]}")
                lines.append("")

        # Join and enforce cap
        context = "\n".join(lines)
        if len(context) > max_chars:
            context = context[: max_chars - 20] + "\n\n[truncated...]"

        return context


class IntentionContextInjector:
    """Injects intention context into prompts across executor workflow.

    Responsibilities:
    - Retrieve intention anchor from memory/disk
    - Format for stable prompt injection (bounded size)
    - Cache to avoid repeated retrievals within same run
    """

    def __init__(
        self,
        run_id: str,
        project_id: str,
        memory_service: Optional[MemoryService] = None,
    ):
        """Initialize intention context injector.

        Args:
            run_id: Run identifier
            project_id: Project identifier
            memory_service: Optional memory service for semantic retrieval
        """
        self.run_id = run_id
        self.project_id = project_id
        self.memory = memory_service

        # Lazy-initialized intention adapter
        self._intention_adapter: Optional[IntentionAnchorV2Adapter] = None

        # Cached context (loaded once per run)
        self._cached_context: Optional[str] = None

    @property
    def intention_manager(self) -> IntentionAnchorV2Adapter:
        """Lazy-load intention adapter.

        Note: Property kept as 'intention_manager' for backward compatibility
        with existing tests and code that reference this property.
        """
        if self._intention_adapter is None:
            self._intention_adapter = IntentionAnchorV2Adapter(
                run_id=self.run_id,
                project_id=self.project_id,
                memory_service=self.memory,
            )
        return self._intention_adapter

    def get_intention_context(
        self,
        max_chars: int = MAX_INTENTION_CONTEXT_CHARS,
        include_header: bool = True,
    ) -> str:
        """Get intention context for prompt injection.

        Args:
            max_chars: Maximum characters to return
            include_header: Whether to include formatting header

        Returns:
            Formatted intention context (empty if unavailable)
        """
        # Use cache if available
        if self._cached_context is not None:
            context = self._cached_context
        else:
            # Retrieve from adapter (tries disk)
            context = self.intention_manager.get_intention_context(max_chars=max_chars)
            self._cached_context = context

        if not context:
            return ""

        # Format with header if requested
        if include_header:
            formatted = f"""
# Project Intention Context

{context}

---
""".strip()
            return formatted[:max_chars]

        return context[:max_chars]

    def inject_into_manifest_prompt(self, base_prompt: str) -> str:
        """Inject intention context into manifest generation prompt.

        Args:
            base_prompt: Base manifest generation prompt

        Returns:
            Enhanced prompt with intention context
        """
        context = self.get_intention_context(max_chars=2048)
        if not context:
            return base_prompt

        # Inject at the beginning for maximum visibility
        return f"{context}\n\n{base_prompt}"

    def inject_into_builder_prompt(
        self,
        base_prompt: str,
        phase_id: str,
        phase_description: str,
    ) -> str:
        """Inject intention context into builder phase prompt.

        Args:
            base_prompt: Base builder prompt
            phase_id: Phase identifier
            phase_description: Phase description

        Returns:
            Enhanced prompt with intention context
        """
        context = self.get_intention_context(max_chars=1536)
        if not context:
            return base_prompt

        # Inject after phase header but before instructions
        header_section = f"""
{context}

Current Phase: {phase_id}
Phase Goal: {phase_description}

---
""".strip()

        return f"{header_section}\n\n{base_prompt}"

    def inject_into_doctor_prompt(
        self,
        base_prompt: str,
        error_context: str,
    ) -> str:
        """Inject intention context into doctor/recovery prompt.

        Args:
            base_prompt: Base doctor prompt
            error_context: Error/failure context

        Returns:
            Enhanced prompt with intention context
        """
        context = self.get_intention_context(max_chars=1024)
        if not context:
            return base_prompt

        # Inject as "original goal" reminder
        reminder = f"""
# Original Project Intention

{context}

# Current Error Context

{error_context}

---
""".strip()

        return f"{reminder}\n\n{base_prompt}"


class IntentionGoalDriftDetector:
    """Extended goal drift detector that includes intention anchor.

    Enhances existing goal_drift functions to also check if phases are
    deviating from the original project intention.
    """

    def __init__(
        self,
        run_id: str,
        project_id: str,
        memory_service: Optional[MemoryService] = None,
    ):
        """Initialize intention-aware goal drift detector.

        Args:
            run_id: Run identifier
            project_id: Project identifier
            memory_service: Optional memory service
        """
        self.run_id = run_id
        self.project_id = project_id
        self.memory = memory_service

        # Intention adapter for anchor retrieval
        self.intention_manager = IntentionAnchorV2Adapter(
            run_id=run_id,
            project_id=project_id,
            memory_service=memory_service,
        )

    def check_drift(
        self,
        run_goal: str,
        phase_description: str,
        phase_deliverables: List[str],
        threshold: float = 0.5,
    ) -> Dict[str, Any]:
        """Check for goal drift including intention anchor.

        Args:
            run_goal: Run-level goal
            phase_description: Phase description
            phase_deliverables: Phase deliverables
            threshold: Drift threshold (0.0-1.0, lower = stricter)

        Returns:
            Dict with drift detection results
        """
        # Check base goal drift (run_goal vs phase) using goal_drift module
        is_aligned, similarity, message = goal_drift.check_goal_drift(
            goal_anchor=run_goal,
            change_intent=phase_description,
            threshold=threshold,
        )

        base_result = {
            "has_drift": not is_aligned,
            "drift_score": 1.0 - similarity,
            "similarity": similarity,
            "message": message,
            "warnings": [] if is_aligned else [message],
        }

        # Retrieve intention anchor
        intention_context = self.intention_manager.get_intention_context(max_chars=2048)

        if not intention_context:
            # No intention available; return base result
            return {
                "has_drift": base_result["has_drift"],
                "drift_score": base_result["drift_score"],
                "base_drift": base_result,
                "intention_drift": None,
                "warnings": base_result["warnings"],
            }

        # Check intention drift (semantic similarity between intention and phase)
        intention_drift_score = self._compute_intention_drift(
            intention_context=intention_context,
            phase_description=phase_description,
            phase_deliverables=phase_deliverables,
        )

        # Combined drift: flag if EITHER base or intention drift exceeds threshold
        has_drift = base_result["has_drift"] or intention_drift_score > threshold

        warnings = list(base_result["warnings"])
        if intention_drift_score > threshold:
            warnings.append(
                f"Phase may be deviating from original project intention "
                f"(drift score: {intention_drift_score:.2f})"
            )

        return {
            "has_drift": has_drift,
            "drift_score": max(
                base_result["drift_score"],
                intention_drift_score,
            ),
            "base_drift": base_result,
            "intention_drift": {
                "score": intention_drift_score,
                "has_drift": intention_drift_score > threshold,
            },
            "warnings": warnings,
        }

    def _compute_intention_drift(
        self,
        intention_context: str,
        phase_description: str,
        phase_deliverables: List[str],
    ) -> float:
        """Compute semantic drift between intention and phase.

        Args:
            intention_context: Intention anchor text
            phase_description: Phase description
            phase_deliverables: Phase deliverables

        Returns:
            Drift score (0.0 = perfect alignment, 1.0 = complete drift)
        """
        # Simple heuristic: check keyword overlap
        # (In production, this could use embeddings for semantic similarity)

        intention_lower = intention_context.lower()
        phase_lower = f"{phase_description} {' '.join(phase_deliverables)}".lower()

        # Extract key terms from intention (simple approach)
        intention_terms = set(
            word for word in intention_lower.split() if len(word) > 4 and word.isalpha()
        )

        # Extract key terms from phase
        phase_terms = set(word for word in phase_lower.split() if len(word) > 4 and word.isalpha())

        if not intention_terms or not phase_terms:
            return 0.0  # No drift if no terms

        # Compute Jaccard similarity
        intersection = len(intention_terms & phase_terms)
        union = len(intention_terms | phase_terms)

        if union == 0:
            return 0.0

        similarity = intersection / union

        # Drift = 1 - similarity
        drift = 1.0 - similarity

        logger.debug(
            f"[IntentionDrift] Similarity: {similarity:.2f}, Drift: {drift:.2f}, "
            f"Shared terms: {intersection}/{union}"
        )

        return drift


def inject_intention_into_prompt(
    prompt: str,
    run_id: str,
    project_id: str,
    memory_service: Optional[MemoryService] = None,
    prompt_type: str = "general",
    **kwargs,
) -> str:
    """Convenience function: inject intention context into any prompt.

    Args:
        prompt: Base prompt
        run_id: Run identifier
        project_id: Project identifier
        memory_service: Optional memory service
        prompt_type: Type of prompt ("manifest", "builder", "doctor", "general")
        **kwargs: Additional args for specific prompt types

    Returns:
        Enhanced prompt with intention context
    """
    injector = IntentionContextInjector(
        run_id=run_id,
        project_id=project_id,
        memory_service=memory_service,
    )

    if prompt_type == "manifest":
        return injector.inject_into_manifest_prompt(prompt)
    elif prompt_type == "builder":
        return injector.inject_into_builder_prompt(
            prompt,
            phase_id=kwargs.get("phase_id", "unknown"),
            phase_description=kwargs.get("phase_description", ""),
        )
    elif prompt_type == "doctor":
        return injector.inject_into_doctor_prompt(
            prompt,
            error_context=kwargs.get("error_context", ""),
        )
    else:
        # General injection
        return injector.inject_into_manifest_prompt(prompt)
