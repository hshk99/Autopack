"""
Replan Trigger Module

Extracted from autonomous_executor.py to detect approach flaws and trigger mid-run replanning.
When a phase repeatedly fails with the same error pattern, this module detects the flaw and
invokes the LLM to revise the implementation approach.

Key responsibilities:
- Detect approach flaws through error pattern analysis
- Normalize error messages for similarity comparison
- Invoke LLM to revise phase approaches
- Maintain goal anchoring during replanning (per GPT_RESPONSE27)
- Track replan attempts and budgets

Related modules:
- phase_orchestrator.py: Uses replan triggers during failure handling
- doctor_integration.py: Doctor can also trigger replanning
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List, Any
import logging
import time
import re
import os

logger = logging.getLogger(__name__)


@dataclass
class ReplanConfig:
    """Configuration for replan triggering."""

    trigger_threshold: int = 3  # Consecutive same-error failures before replan
    similarity_threshold: float = 0.8  # Message similarity threshold (0.0-1.0)
    min_message_length: int = 30  # Minimum message length for similarity check
    similarity_enabled: bool = True  # Whether to check message similarity
    fatal_error_types: List[str] = None  # Error types that trigger immediately

    def __post_init__(self):
        if self.fatal_error_types is None:
            self.fatal_error_types = []


class ReplanTrigger:
    """
    Detects approach flaws and triggers mid-run replanning.

    Uses error pattern analysis with message similarity to distinguish
    'approach flaw' from 'transient failure'.
    """

    def __init__(
        self,
        max_replans_per_phase: int = 2,
        max_replans_per_run: int = 5,
        config: Optional[ReplanConfig] = None,
    ):
        """
        Initialize replan trigger.

        Args:
            max_replans_per_phase: Maximum replans per phase
            max_replans_per_run: Maximum total replans for the run
            config: Replan configuration
        """
        self.max_replans_per_phase = max_replans_per_phase
        self.max_replans_per_run = max_replans_per_run
        self._config_provided = config is not None
        self.config = config or ReplanConfig()

        # Load config from models.yaml only if no custom config was provided
        if not self._config_provided:
            self._load_config_from_yaml()

    def _load_config_from_yaml(self):
        """Load replan configuration from config/models.yaml."""
        try:
            import yaml
            from pathlib import Path

            config_path = Path("config/models.yaml")
            if config_path.exists():
                with open(config_path) as f:
                    yaml_config = yaml.safe_load(f)
                replan_config = yaml_config.get("replan", {})

                # Update config with values from YAML
                self.config.trigger_threshold = replan_config.get(
                    "trigger_threshold", self.config.trigger_threshold
                )
                self.config.similarity_threshold = replan_config.get(
                    "similarity_threshold", self.config.similarity_threshold
                )
                self.config.min_message_length = replan_config.get(
                    "min_message_length", self.config.min_message_length
                )
                self.config.similarity_enabled = replan_config.get(
                    "message_similarity_enabled", self.config.similarity_enabled
                )
                self.config.fatal_error_types = replan_config.get(
                    "fatal_error_types", self.config.fatal_error_types
                )
        except Exception as e:
            logger.debug(f"[ReplanTrigger] Could not load config from YAML: {e}")

    def should_trigger_replan(
        self,
        phase: Dict,
        error_history: List[Dict],
        replan_count: int,
        run_replan_count: int,
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if re-planning should be triggered for a phase.

        Args:
            phase: Phase specification
            error_history: History of errors for this phase
            replan_count: Number of replans for this phase
            run_replan_count: Number of replans for the entire run

        Returns:
            Tuple of (should_replan: bool, detected_flaw_type: str or None)
        """
        phase_id = phase.get("phase_id")

        # Check global run-level replan limit (prevents pathological projects)
        if run_replan_count >= self.max_replans_per_run:
            logger.info(
                f"[Re-Plan] Global max replans ({self.max_replans_per_run}) reached for this run - no more replans allowed"
            )
            return False, None

        # Check if we've exceeded max replans for this specific phase
        if replan_count >= self.max_replans_per_phase:
            logger.info(
                f"[Re-Plan] Max replans ({self.max_replans_per_phase}) reached for {phase_id}"
            )
            return False, None

        # Detect approach flaw
        flaw_type = self.detect_approach_flaw(phase, error_history)
        if flaw_type:
            # DBG-014 / BUILD-049 coordination: deliverables path failures should be handled
            # by the deliverables validator + learning hints loop, not mid-run replanning.
            if flaw_type == "deliverables_validation_failed":
                logger.info(
                    "[Re-Plan] Deferring for deliverables validation failure "
                    "- allowing learning hints to converge"
                )
                return False, None

            return True, flaw_type

        return False, None

    def detect_approach_flaw(self, phase: Dict, error_history: List[Dict]) -> Optional[str]:
        """
        Analyze error history to detect fundamental approach flaws.

        Enhanced with message similarity checking:
        - Checks consecutive same-type failures (not just total count)
        - Verifies message similarity >= threshold
        - Supports fatal error types that trigger immediately

        Args:
            phase: Phase specification
            error_history: History of errors for this phase

        Returns:
            Error type if approach flaw detected, None otherwise
        """
        phase_id = phase.get("phase_id")

        if len(error_history) == 0:
            return None

        # Check for fatal error types (immediate trigger on first occurrence)
        latest_error = error_history[-1]
        if latest_error["error_type"] in self.config.fatal_error_types:
            # Structured REPLAN-TRIGGER logging
            logger.info(
                f"[REPLAN-TRIGGER] reason=fatal_error type={latest_error['error_type']} "
                f"phase={phase_id} attempt={len(error_history)}"
            )
            return latest_error["error_type"]

        if len(error_history) < self.config.trigger_threshold:
            return None

        # Check consecutive same-type failures with message similarity
        # Look at the last N errors (where N = trigger_threshold)
        recent_errors = error_history[-self.config.trigger_threshold :]

        # Group by error type
        error_types = [e["error_type"] for e in recent_errors]
        if len(set(error_types)) != 1:
            # Different error types in recent errors - not a repeated pattern
            return None

        error_type = error_types[0]

        # If similarity checking is disabled, trigger on same type alone
        if not self.config.similarity_enabled:
            logger.info(
                f"[REPLAN-TRIGGER] reason=repeated_error type={error_type} "
                f"phase={phase_id} attempt={len(error_history)} count={self.config.trigger_threshold}"
            )
            return error_type

        # Check message similarity between consecutive errors
        messages = [e.get("error_details", "") for e in recent_errors]

        # Skip if messages are too short
        if all(len(m) < self.config.min_message_length for m in messages):
            logger.debug(f"[Re-Plan] Messages too short for similarity check ({phase_id})")
            # Fall back to type-only check
            logger.info(
                f"[REPLAN-TRIGGER] reason=repeated_error_short_msg type={error_type} "
                f"phase={phase_id} attempt={len(error_history)} count={self.config.trigger_threshold}"
            )
            return error_type

        # Check pairwise similarity between consecutive errors
        all_similar = True
        for i in range(len(messages) - 1):
            similarity = self._calculate_message_similarity(messages[i], messages[i + 1])
            logger.debug(f"[Re-Plan] Message similarity [{i}]->[{i+1}]: {similarity:.2f}")
            if similarity < self.config.similarity_threshold:
                all_similar = False
                break

        if all_similar:
            logger.info(
                f"[REPLAN-TRIGGER] reason=similar_errors type={error_type} "
                f"phase={phase_id} attempt={len(error_history)} count={self.config.trigger_threshold} "
                f"similarity_threshold={self.config.similarity_threshold}"
            )
            return error_type

        logger.debug(f"[Re-Plan] No approach flaw for {phase_id}: messages not similar enough")
        return None

    def _normalize_error_message(self, message: str) -> str:
        """
        Normalize error message for similarity comparison.

        Strips:
        - Absolute/relative paths
        - Line numbers
        - Run IDs / UUIDs
        - Timestamps
        - Stack trace lines
        - Collapses whitespace
        """
        if not message:
            return ""

        normalized = message.lower()

        # Strip file paths (Unix and Windows)
        normalized = re.sub(r"[/\\][\w\-./\\]+\.(py|js|ts|json|yaml|yml|md)", "[PATH]", normalized)
        normalized = re.sub(r"[a-z]:\\[\w\-\\]+", "[PATH]", normalized, flags=re.IGNORECASE)

        # Strip line numbers (e.g., "line 42", ":42:", ":42", "L42")
        normalized = re.sub(r"\bline\s*\d+\b", "line [N]", normalized)

        # Strip timestamps first (before line number colons) to avoid conflicts
        # Note: message is already lowercased, so match 't' not 'T'
        normalized = re.sub(r"\d{4}-\d{2}-\d{2}[t ]\d{2}:\d{2}:\d{2}", "[TIMESTAMP]", normalized)
        normalized = re.sub(r"\d{2}:\d{2}:\d{2}", "[TIME]", normalized)

        # Now safe to strip line number colons (timestamps already handled)
        normalized = re.sub(r":\d+:", ":[N]:", normalized)
        normalized = re.sub(r":\d+\b", ":[N]", normalized)  # Also match :42 at end
        normalized = re.sub(r"\bL\d+\b", "L[N]", normalized)

        # Strip UUIDs
        normalized = re.sub(
            r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", "[UUID]", normalized
        )

        # Strip run IDs (common patterns)
        normalized = re.sub(r"\b[a-z]+-\d{8}(-\d+)?\b", "[RUN_ID]", normalized)

        # Strip stack trace lines
        normalized = re.sub(r'file "[^"]+", line \[n\]', "file [PATH], line [N]", normalized)
        normalized = re.sub(r"traceback \(most recent call last\):", "[TRACEBACK]", normalized)

        # Collapse whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()

        return normalized

    def _calculate_message_similarity(self, msg1: str, msg2: str) -> float:
        """
        Calculate similarity between two error messages using difflib.

        Returns:
            Float between 0.0 and 1.0 (1.0 = identical)
        """
        from difflib import SequenceMatcher

        if not msg1 or not msg2:
            return 0.0

        norm1 = self._normalize_error_message(msg1)
        norm2 = self._normalize_error_message(msg2)

        return SequenceMatcher(None, norm1, norm2).ratio()

    def revise_phase_approach(
        self,
        phase: Dict,
        flaw_type: str,
        error_history: List[Dict],
        original_intent: str,
        llm_service: Any,
    ) -> Optional[Dict]:
        """
        Invoke LLM to revise the phase approach based on failure context.

        This is the core of mid-run re-planning: we ask the LLM to analyze
        what went wrong and provide a revised implementation approach.

        Per GPT_RESPONSE27: Now includes Goal Anchoring to prevent context drift:
        - Stores and references original_intent
        - Includes hard constraint in prompt
        - Classifies alignment of revision

        Args:
            phase: Original phase specification
            flaw_type: Detected flaw type
            error_history: History of errors for this phase
            original_intent: Original intent (before any replanning)
            llm_service: LLM service for revision

        Returns:
            Revised phase specification dict, or None if revision failed
        """
        phase_id = phase.get("phase_id")
        phase_name = phase.get("name", phase_id)
        current_description = phase.get("description", "")

        logger.info(f"[Re-Plan] Revising approach for {phase_id} due to {flaw_type}")
        logger.info(f"[GoalAnchor] Original intent: {original_intent[:100]}...")

        # Build context from error history
        error_summary = "\n".join(
            [
                f"- Attempt {e['attempt'] + 1}: {e['error_type']} - {e['error_details'][:200]}"
                for e in error_history[-5:]  # Last 5 errors
            ]
        )

        # [Goal Anchoring] Per GPT_RESPONSE27: Include original_intent with HARD CONSTRAINT
        replan_prompt = f"""You are a senior software architect. A phase in our automated build system has failed repeatedly with the same error pattern. Your task is to analyze the failures and provide a revised implementation approach.

## Original Phase Specification
**Phase**: {phase_name}
**Description**: {current_description}
**Category**: {phase.get('task_category', 'general')}
**Complexity**: {phase.get('complexity', 'medium')}

## Error Pattern Detected
**Flaw Type**: {flaw_type}
**Recent Errors**:
{error_summary}

## CRITICAL CONSTRAINT - GOAL ANCHORING
The revised approach MUST still achieve this core goal:
**Original Intent**: {original_intent}

Do NOT reduce scope, skip functionality, or change what the phase achieves.
Only change HOW it achieves the goal, not WHAT it achieves.

## Your Task
Analyze why the current approach kept failing and provide a REVISED description that:
1. MAINTAINS the original intent and scope (CRITICAL - no scope reduction)
2. Addresses the root cause of the repeated failures
3. Uses a different implementation strategy if needed
4. Includes specific guidance to avoid the detected error pattern

## Output Format
Provide ONLY the revised description text. Do not include JSON, markdown headers, or explanations.
Just the new description that should replace the current one while preserving the original goal.
"""

        try:
            # Use LlmService to invoke planner (use strongest model for replanning)
            if not llm_service:
                logger.error("[Re-Plan] LlmService not initialized")
                return None

            # NOTE: Re-planning is best-effort. Skip if Anthropic is disabled/unavailable.
            try:
                if hasattr(llm_service, "model_router") and "anthropic" in getattr(
                    llm_service.model_router, "disabled_providers", set()
                ):
                    logger.info(
                        "[Re-Plan] Skipping re-planning because provider 'anthropic' is disabled"
                    )
                    return None
            except Exception:
                pass

            # Current implementation uses Anthropic directly for replanning; require key.
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                logger.info("[Re-Plan] Skipping re-planning because ANTHROPIC_API_KEY is not set")
                return None

            # Use Claude for re-planning (strongest model)
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)

            response = client.messages.create(
                model="claude-sonnet-4-20250514",  # Use strong model for re-planning
                max_tokens=2000,
                messages=[{"role": "user", "content": replan_prompt}],
            )

            # Defensive: ensure response has text content
            content_blocks = getattr(response, "content", None) or []
            first_block = content_blocks[0] if content_blocks else None
            revised_description = (getattr(first_block, "text", "") or "").strip()

            if not revised_description or len(revised_description) < 20:
                logger.error("[Re-Plan] LLM returned empty or too-short revision")
                return None

            # Create revised phase spec
            revised_phase = phase.copy()
            revised_phase["description"] = revised_description
            revised_phase["_original_description"] = current_description
            revised_phase["_original_intent"] = original_intent  # [Goal Anchoring]
            revised_phase["_revision_reason"] = f"Approach flaw: {flaw_type}"
            revised_phase["_revision_timestamp"] = time.time()

            logger.info(f"[Re-Plan] Successfully revised phase {phase_id}")
            logger.info(f"[Re-Plan] Original: {current_description[:100]}...")
            logger.info(f"[Re-Plan] Revised: {revised_description[:100]}...")

            return revised_phase

        except Exception as e:
            logger.error(f"[Re-Plan] Failed to revise phase approach: {e}")
            import traceback

            traceback.print_exc()
            return None
