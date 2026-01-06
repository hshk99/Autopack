"""Project Intention Memory: Compact semantic intention artifacts.

Phase 0 of True Autonomy roadmap (per IMPLEMENTATION_PLAN_TRUE_AUTONOMY.md).

Provides a first-class contract for storing and retrieving project intention:
- Compact intention anchor (<= 2KB) for prompt injection
- Structured intention JSON (v1 schema)
- Stable digest-based identification
- Memory service integration via planning collection

Key principles:
- Deterministic-first (stable hashing, no LLM required)
- Token-efficient (bounded sizes, no content dumps in logs)
- Backward compatible (optional usage, degrades gracefully)
- Path resolution via RunFileLayout (no hardcoded paths)
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from .file_layout import RunFileLayout
from .memory.memory_service import MemoryService
from .intention_anchor.v2 import IntentionAnchorV2, create_from_inputs as create_v2_anchor

logger = logging.getLogger(__name__)

# Intention anchor size cap (for prompt injection safety)
MAX_INTENTION_ANCHOR_CHARS = 2048

# Intention artifact version
INTENTION_SCHEMA_VERSION = "v1"


@dataclass
class ProjectIntention:
    """Project Intention v1 schema.

    Compact, semantic representation of project goals, constraints, and hypotheses.
    Designed to be stable, queryable, and safe for prompt injection.
    """

    project_id: str
    created_at: str
    raw_input_digest: str
    intent_anchor: str

    # Optional structured fields
    intent_facts: List[str] = field(default_factory=list)
    non_goals: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)
    toolchain_hypotheses: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)

    schema_version: str = field(default=INTENTION_SCHEMA_VERSION)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (for JSON serialization)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectIntention":
        """Create from dictionary."""
        # Filter to known fields to avoid TypeErrors
        known_fields = {
            "project_id",
            "created_at",
            "raw_input_digest",
            "intent_anchor",
            "intent_facts",
            "non_goals",
            "acceptance_criteria",
            "constraints",
            "toolchain_hypotheses",
            "open_questions",
            "schema_version",
        }
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


class ProjectIntentionManager:
    """Manages project intention artifacts and memory integration.

    Responsibilities:
    - Create intention artifacts from raw input
    - Write artifacts to run-specific paths (via RunFileLayout)
    - Store intention in memory service (planning collection)
    - Retrieve intention for context injection
    """

    def __init__(
        self,
        run_id: str,
        project_id: Optional[str] = None,
        memory_service: Optional[MemoryService] = None,
    ):
        """Initialize intention manager.

        Args:
            run_id: Run identifier
            project_id: Project identifier (auto-detected if not provided)
            memory_service: Memory service instance (optional)
        """
        self.run_id = run_id
        self.layout = RunFileLayout(run_id=run_id, project_id=project_id)
        self.project_id = self.layout.project_id
        self.memory = memory_service

    def _compute_digest(self, raw_input: str) -> str:
        """Compute stable digest of raw input.

        Args:
            raw_input: Raw unstructured plan/intention text

        Returns:
            SHA256 hash (first 16 chars)
        """
        return hashlib.sha256(raw_input.encode("utf-8", errors="ignore")).hexdigest()[:16]

    def _create_anchor(
        self,
        raw_input: str,
        intent_facts: Optional[List[str]] = None,
        max_chars: int = MAX_INTENTION_ANCHOR_CHARS,
    ) -> str:
        """Create compact intention anchor from raw input.

        The anchor is a condensed, stable summary suitable for prompt injection.

        Args:
            raw_input: Raw unstructured plan/intention text
            intent_facts: Optional structured facts to include
            max_chars: Maximum characters (default: 2048)

        Returns:
            Intention anchor text (<= max_chars)
        """
        # Start with a header
        lines = ["# Project Intention", ""]

        # Add truncated raw input
        if raw_input:
            truncated_input = raw_input[: max_chars // 2].strip()
            lines.append("## Original Input")
            lines.append(truncated_input)
            lines.append("")

        # Add intent facts if provided
        if intent_facts:
            lines.append("## Key Facts")
            for fact in intent_facts[:5]:  # Limit to 5 facts
                lines.append(f"- {fact[:150]}")  # Truncate each fact
            lines.append("")

        # Join and enforce cap
        anchor = "\n".join(lines)
        if len(anchor) > max_chars:
            anchor = anchor[: max_chars - 20] + "\n\n[truncated...]"

        return anchor

    def _get_intention_dir(self) -> Path:
        """Get intention artifacts directory.

        Uses RunFileLayout to ensure consistent path resolution.

        Returns:
            Path to intention directory
        """
        return self.layout.base_dir / "intention"

    def _get_intention_json_path(self) -> Path:
        """Get path to intention JSON artifact."""
        return self._get_intention_dir() / f"intent_{INTENTION_SCHEMA_VERSION}.json"

    def _get_intention_anchor_path(self) -> Path:
        """Get path to intention anchor artifact."""
        return self._get_intention_dir() / "intent_anchor.txt"

    def create_intention(
        self,
        raw_input: str,
        intent_facts: Optional[List[str]] = None,
        non_goals: Optional[List[str]] = None,
        acceptance_criteria: Optional[List[str]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        toolchain_hypotheses: Optional[List[str]] = None,
        open_questions: Optional[List[str]] = None,
    ) -> ProjectIntention:
        """Create project intention from inputs.

        Args:
            raw_input: Raw unstructured plan/intention text
            intent_facts: Normalized facts/requirements
            non_goals: Explicit non-goals
            acceptance_criteria: High-level success criteria
            constraints: Budget/safety/technical constraints
            toolchain_hypotheses: Detected/guessed toolchains
            open_questions: Questions that must be resolved

        Returns:
            ProjectIntention instance
        """
        # Compute stable digest
        digest = self._compute_digest(raw_input)

        # Create compact anchor
        anchor = self._create_anchor(
            raw_input=raw_input,
            intent_facts=intent_facts,
            max_chars=MAX_INTENTION_ANCHOR_CHARS,
        )

        # Create timestamp
        created_at = datetime.now(timezone.utc).isoformat()

        # Build intention object
        intention = ProjectIntention(
            project_id=self.project_id,
            created_at=created_at,
            raw_input_digest=digest,
            intent_anchor=anchor,
            intent_facts=intent_facts or [],
            non_goals=non_goals or [],
            acceptance_criteria=acceptance_criteria or [],
            constraints=constraints or {},
            toolchain_hypotheses=toolchain_hypotheses or [],
            open_questions=open_questions or [],
        )

        logger.info(
            f"[ProjectIntention] Created intention for project={self.project_id}, "
            f"digest={digest}, anchor_size={len(anchor)} chars"
        )

        return intention

    def write_intention_artifacts(self, intention: ProjectIntention) -> Dict[str, Path]:
        """Write intention artifacts to disk.

        Args:
            intention: ProjectIntention to persist

        Returns:
            Dict mapping artifact type to path
        """
        # Ensure directory exists
        intention_dir = self._get_intention_dir()
        intention_dir.mkdir(parents=True, exist_ok=True)

        paths = {}

        # Write JSON artifact
        json_path = self._get_intention_json_path()
        json_path.write_text(
            json.dumps(intention.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        paths["json"] = json_path
        logger.debug(f"[ProjectIntention] Wrote JSON: {json_path}")

        # Write anchor artifact
        anchor_path = self._get_intention_anchor_path()
        anchor_path.write_text(intention.intent_anchor, encoding="utf-8")
        paths["anchor"] = anchor_path
        logger.debug(f"[ProjectIntention] Wrote anchor: {anchor_path}")

        return paths

    def write_intention_to_memory(
        self,
        intention: ProjectIntention,
        run_id: Optional[str] = None,
    ) -> Optional[str]:
        """Write intention to memory service (planning collection).

        Args:
            intention: ProjectIntention to store
            run_id: Optional run_id override

        Returns:
            Memory point ID if successful, None if memory disabled
        """
        if not self.memory or not self.memory.enabled:
            logger.debug("[ProjectIntention] Memory disabled; skipping memory write")
            return None

        # Use planning artifact API to embed intention
        point_id = self.memory.write_planning_artifact(
            path=f"intention/{self.project_id}",
            content=intention.intent_anchor,
            project_id=self.project_id,
            version=1,
            author="ProjectIntentionManager",
            reason="Initial project intention capture",
            summary=f"Project intention: {len(intention.intent_facts)} facts, "
            f"{len(intention.acceptance_criteria)} criteria",
            status="active",
            timestamp=intention.created_at,
        )

        logger.info(
            f"[ProjectIntention] Stored in memory: point_id={point_id}, "
            f"project_id={self.project_id}"
        )

        return point_id

    def read_intention_from_disk(self) -> Optional[ProjectIntention]:
        """Read intention from disk artifacts.

        Returns:
            ProjectIntention if found, None otherwise
        """
        json_path = self._get_intention_json_path()
        if not json_path.exists():
            logger.debug(f"[ProjectIntention] No intention artifact found: {json_path}")
            return None

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            intention = ProjectIntention.from_dict(data)
            logger.debug(
                f"[ProjectIntention] Loaded from disk: "
                f"project_id={intention.project_id}, "
                f"digest={intention.raw_input_digest}"
            )
            return intention
        except Exception as exc:
            logger.warning(f"[ProjectIntention] Failed to read intention: {exc}")
            return None

    def retrieve_intention_from_memory(
        self,
        query: Optional[str] = None,
        limit: int = 1,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve intention from memory service.

        Args:
            query: Optional semantic query (defaults to project_id-based retrieval)
            limit: Max results

        Returns:
            Memory result dict if found, None otherwise
        """
        if not self.memory or not self.memory.enabled:
            logger.debug("[ProjectIntention] Memory disabled; skipping retrieval")
            return None

        query = query or f"Project intention for {self.project_id}"

        try:
            results = self.memory.search_planning(
                query=query,
                project_id=self.project_id,
                limit=limit,
                types=["planning_artifact"],
            )
        except Exception as e:
            logger.warning(f"[ProjectIntention] Memory search failed: {e}")
            return None

        if not results:
            logger.debug(f"[ProjectIntention] No intention found in memory for {self.project_id}")
            return None

        # Return the top result
        result = results[0]
        logger.debug(
            f"[ProjectIntention] Retrieved from memory: "
            f"score={result.get('score', 'N/A')}, "
            f"payload_summary={result.get('payload', {}).get('summary', 'N/A')[:100]}"
        )

        return result

    def get_intention_context(
        self,
        max_chars: int = 2048,
    ) -> str:
        """Get intention context for prompt injection.

        This retrieves the intention anchor (from disk or memory) and formats it
        for safe inclusion in prompts. Size is bounded to avoid prompt bloat.

        Args:
            max_chars: Maximum characters to return

        Returns:
            Formatted intention context (empty string if unavailable)
        """
        # Try disk first (faster)
        intention = self.read_intention_from_disk()
        if intention:
            anchor = intention.intent_anchor
            if len(anchor) <= max_chars:
                return anchor
            return anchor[: max_chars - 20] + "\n\n[truncated...]"

        # Try memory fallback
        result = self.retrieve_intention_from_memory()
        if result:
            payload = result.get("payload", {})
            content_preview = payload.get("content_preview", "")
            if content_preview:
                if len(content_preview) <= max_chars:
                    return content_preview
                return content_preview[: max_chars - 20] + "\n\n[truncated...]"

        logger.debug("[ProjectIntention] No intention context available")
        return ""

    # V2 methods (IntentionAnchorV2 support)

    def _get_intention_v2_json_path(self) -> Path:
        """Get path to IntentionAnchorV2 JSON artifact."""
        return self._get_intention_dir() / "intention_anchor_v2.json"

    def create_intention_v2(
        self,
        raw_input: str,
        north_star: Optional[Dict[str, Any]] = None,
        safety_risk: Optional[Dict[str, Any]] = None,
        evidence_verification: Optional[Dict[str, Any]] = None,
        scope_boundaries: Optional[Dict[str, Any]] = None,
        budget_cost: Optional[Dict[str, Any]] = None,
        memory_continuity: Optional[Dict[str, Any]] = None,
        governance_review: Optional[Dict[str, Any]] = None,
        parallelism_isolation: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IntentionAnchorV2:
        """Create IntentionAnchorV2 from inputs.

        Args:
            raw_input: Raw unstructured plan/intention text
            north_star: NorthStar intention dict
            safety_risk: SafetyRisk intention dict
            evidence_verification: EvidenceVerification intention dict
            scope_boundaries: ScopeBoundaries intention dict
            budget_cost: BudgetCost intention dict
            memory_continuity: MemoryContinuity intention dict
            governance_review: GovernanceReview intention dict
            parallelism_isolation: ParallelismIsolation intention dict
            metadata: Metadata dict

        Returns:
            IntentionAnchorV2 instance
        """
        anchor_v2 = create_v2_anchor(
            project_id=self.project_id,
            raw_input=raw_input,
            north_star=north_star,
            safety_risk=safety_risk,
            evidence_verification=evidence_verification,
            scope_boundaries=scope_boundaries,
            budget_cost=budget_cost,
            memory_continuity=memory_continuity,
            governance_review=governance_review,
            parallelism_isolation=parallelism_isolation,
            metadata=metadata,
        )

        logger.info(
            f"[ProjectIntention] Created IntentionAnchorV2 for project={self.project_id}, "
            f"digest={anchor_v2.raw_input_digest}"
        )

        return anchor_v2

    def write_intention_v2_artifacts(self, anchor_v2: IntentionAnchorV2) -> Dict[str, Path]:
        """Write IntentionAnchorV2 artifacts to disk.

        Args:
            anchor_v2: IntentionAnchorV2 to persist

        Returns:
            Dict mapping artifact type to path
        """
        # Ensure directory exists
        intention_dir = self._get_intention_dir()
        intention_dir.mkdir(parents=True, exist_ok=True)

        paths = {}

        # Validate before writing
        anchor_v2.validate_against_schema()

        # Write v2 JSON artifact
        v2_json_path = self._get_intention_v2_json_path()
        v2_json_path.write_text(
            json.dumps(anchor_v2.to_json_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        paths["v2_json"] = v2_json_path
        logger.debug(f"[ProjectIntention] Wrote v2 JSON: {v2_json_path}")

        return paths

    def read_intention_v2_from_disk(self) -> Optional[IntentionAnchorV2]:
        """Read IntentionAnchorV2 from disk artifacts.

        Returns:
            IntentionAnchorV2 if found, None otherwise
        """
        v2_json_path = self._get_intention_v2_json_path()
        if not v2_json_path.exists():
            logger.debug(f"[ProjectIntention] No v2 intention artifact found: {v2_json_path}")
            return None

        try:
            data = json.loads(v2_json_path.read_text(encoding="utf-8"))
            anchor_v2 = IntentionAnchorV2.from_json_dict(data)
            logger.debug(
                f"[ProjectIntention] Loaded v2 from disk: "
                f"project_id={anchor_v2.project_id}, "
                f"digest={anchor_v2.raw_input_digest}"
            )
            return anchor_v2
        except Exception as exc:
            logger.warning(f"[ProjectIntention] Failed to read v2 intention: {exc}")
            return None


def create_and_store_intention(
    run_id: str,
    raw_input: str,
    project_id: Optional[str] = None,
    memory_service: Optional[MemoryService] = None,
    **kwargs,
) -> ProjectIntention:
    """Convenience function: create, write, and store intention.

    Args:
        run_id: Run identifier
        raw_input: Raw unstructured plan/intention text
        project_id: Optional project identifier
        memory_service: Optional memory service instance
        **kwargs: Additional intention fields (intent_facts, non_goals, etc.)

    Returns:
        Created ProjectIntention
    """
    manager = ProjectIntentionManager(
        run_id=run_id,
        project_id=project_id,
        memory_service=memory_service,
    )

    intention = manager.create_intention(raw_input=raw_input, **kwargs)
    manager.write_intention_artifacts(intention)
    manager.write_intention_to_memory(intention)

    return intention
