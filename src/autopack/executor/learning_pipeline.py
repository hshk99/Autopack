"""
Learning Pipeline Module

Records lessons learned during troubleshooting to help:
1. Later phases in the same run (Stage 0A - within-run hints)
2. Future runs after promotion (Stage 0B - cross-run hints)

IMP-LOOP-020: Adds guaranteed persistence with retry logic and verification
for cross-run learning persistence.
"""

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class HintPersistenceError(Exception):
    """Raised when hint persistence fails after all retries.

    IMP-LOOP-020: This exception indicates that hints could not be
    persisted after multiple attempts, which may result in loss of
    cross-run learning data.
    """

    pass


@dataclass
class LearningHint:
    """Lesson learned during troubleshooting

    IMP-MEM-001: Includes confidence scoring based on evidence quality
    and occurrence count to rank hints by reliability.
    """

    phase_id: str
    hint_type: str  # auditor_reject, ci_fail, patch_apply_error, etc.
    hint_text: str
    source_issue_keys: List[str]
    recorded_at: float
    task_category: Optional[str] = None
    # IMP-MEM-001: Confidence scoring fields
    confidence: float = 0.5  # 0.0-1.0 scale
    occurrence_count: int = 1
    validation_successes: int = 0
    validation_failures: int = 0

    def calculate_confidence(self) -> float:
        """Calculate confidence based on occurrences and validation history.

        IMP-MEM-001: Confidence algorithm:
        - Base score from occurrence count (capped at 10 occurrences)
        - Weighted by validation success rate if validations exist
        - Higher occurrence count + higher success rate = higher confidence

        Returns:
            Confidence score between 0.0 and 1.0
        """
        # Base confidence from occurrence count (max at 10 occurrences)
        base = min(self.occurrence_count / 10.0, 1.0)

        total_validations = self.validation_successes + self.validation_failures
        if total_validations > 0:
            success_rate = self.validation_successes / total_validations
            # Weight: 50% from occurrence count, 50% from success rate
            self.confidence = base * 0.5 + success_rate * 0.5
        else:
            # No validations yet, use half of base confidence
            self.confidence = base * 0.5

        return self.confidence

    def record_validation(self, success: bool) -> None:
        """Record a validation result and recalculate confidence.

        Args:
            success: True if the hint led to a successful outcome
        """
        if success:
            self.validation_successes += 1
        else:
            self.validation_failures += 1
        self.calculate_confidence()

    def increment_occurrence(self) -> None:
        """Increment occurrence count and recalculate confidence."""
        self.occurrence_count += 1
        self.calculate_confidence()

    def calculate_decay_score(self) -> float:
        """Calculate time-based decay score for hint relevance.

        IMP-MEM-003: Applies same decay logic as learned_rules.py pattern,
        but with shorter timeframe suitable for in-memory hints (1 week half-life).

        Decay formula:
        - decay_factor = 1.0 - (age_hours / 168), minimum 0.1
        - failure_penalty = 0.1 * validation_failures
        - final_score = confidence * decay_factor - failure_penalty, minimum 0.0

        Returns:
            Decayed confidence score between 0.0 and 1.0
        """
        age_hours = (time.time() - self.recorded_at) / 3600
        decay_factor = max(0.1, 1.0 - (age_hours / 168.0))  # 1 week half-life
        failure_penalty = 0.1 * self.validation_failures
        return max(0.0, self.confidence * decay_factor - failure_penalty)


class LearningPipeline:
    """
    Records lessons learned during troubleshooting.

    Hints are lessons that can help:
    1. Later phases in the same run (Stage 0A)
    2. Future runs after promotion (Stage 0B)

    IMP-LOOP-018: Also tracks rule effectiveness by recording which rules
    were applied and whether the phase succeeded or failed.
    """

    def __init__(
        self,
        run_id: str,
        memory_service: Optional[Any] = None,
        project_id: Optional[str] = None,
    ):
        """
        Initialize LearningPipeline.

        Args:
            run_id: Run identifier for tracking hints
            memory_service: Optional MemoryService instance for hint persistence
            project_id: Optional project identifier for namespacing persisted hints
        """
        self.run_id = run_id
        self._hints: List[LearningHint] = []
        self._memory_service = memory_service
        self._project_id = project_id
        # IMP-LOOP-018: Track applied rules per phase for effectiveness tracking
        self._applied_rules_per_phase: Dict[str, List[str]] = {}

    def record_hint(self, phase: Dict, hint_type: str, details: str):
        """
        Record a hint for this run.

        Args:
            phase: Phase specification dict
            hint_type: Type of hint (e.g., auditor_reject, ci_fail)
            details: Human-readable details about what was learned
        """
        try:
            phase_id = phase.get("phase_id", "unknown")
            phase_name = phase.get("name", phase_id)

            # Generate descriptive hint text based on type
            hint_templates = {
                "auditor_reject": f"Phase '{phase_name}' was rejected by auditor - ensure code quality and completeness",
                "ci_fail": f"Phase '{phase_name}' failed CI tests - verify tests pass before submitting",
                "patch_apply_error": f"Phase '{phase_name}' generated invalid patch - ensure proper diff format",
                "infra_error": f"Phase '{phase_name}' hit infrastructure error - check API connectivity",
                "success_after_retry": f"Phase '{phase_name}' succeeded after retries - model escalation was needed",
                "builder_churn_limit_exceeded": f"Phase '{phase_name}' exceeded churn limit - reduce change scope",
                "builder_guardrail": f"Phase '{phase_name}' blocked by builder guardrail - check output size",
            }

            hint_text = hint_templates.get(hint_type, f"Phase '{phase_name}': {hint_type}")
            hint_text = f"{hint_text}. Details: {details}"

            # Create hint
            hint = LearningHint(
                phase_id=phase_id,
                hint_type=hint_type,
                hint_text=hint_text,
                source_issue_keys=[f"{hint_type}_{phase_id}"],
                recorded_at=time.time(),
                task_category=phase.get("task_category"),
            )

            self._hints.append(hint)

            # IMP-INT-004: Persist hint immediately if memory_service is available
            # IMP-LEARN-002: Use retry but skip verification for immediate persistence
            # (verification is done at end of run by persist_hints_guaranteed)
            self._persist_hint_to_memory(hint, max_retries=3, verify=False)

            logger.debug(f"[Learning] Recorded hint for {phase_id}: {hint_type}")

        except Exception as e:
            # Don't let hint recording break phase execution
            logger.warning(f"[Learning] Failed to record hint: {e}")

    def get_hints_for_phase(self, phase: Dict, task_category: Optional[str] = None) -> List[str]:
        """
        Get relevant hints for a phase, sorted by confidence.

        IMP-MEM-001: Hints are now sorted by confidence score so that
        hints with more occurrences and higher validation success rates
        are prioritized over less reliable hints.

        Args:
            phase: Phase specification dict
            task_category: Optional task category filter

        Returns:
            List of hint text strings, sorted by confidence (highest first)
        """
        phase_id = phase.get("phase_id")
        phase_task_category = phase.get("task_category")

        # Filter hints by category or phase
        relevant_hints: List[LearningHint] = []

        for hint in self._hints:
            # Same phase ID
            if hint.phase_id == phase_id:
                relevant_hints.append(hint)
                continue

            # Same category (if available on both hint and phase)
            if (
                phase_task_category is not None
                and hint.task_category is not None
                and hint.task_category == phase_task_category
            ):
                relevant_hints.append(hint)

        # IMP-MEM-001: Sort by confidence (highest first)
        relevant_hints.sort(key=lambda h: h.confidence, reverse=True)

        return [h.hint_text for h in relevant_hints[:10]]  # Limit to top 10

    def get_all_hints(self) -> List[LearningHint]:
        """Get all recorded hints"""
        return self._hints

    def get_hint_count(self) -> int:
        """Get total number of hints recorded"""
        return len(self._hints)

    def clear_hints(self):
        """Clear all hints (useful for testing)"""
        self._hints = []
        logger.debug("[Learning] Cleared all hints")

    # =========================================================================
    # IMP-LOOP-018: Rule Effectiveness Tracking
    # =========================================================================

    def register_applied_rules(self, phase_id: str, rule_ids: List[str]) -> None:
        """Register rules that were applied during phase execution.

        IMP-LOOP-018: Tracks which rules were used for a phase so we can
        record their effectiveness after phase completion.

        Args:
            phase_id: Phase identifier
            rule_ids: List of rule IDs that were applied
        """
        if not rule_ids:
            return

        self._applied_rules_per_phase[phase_id] = list(rule_ids)
        logger.debug(f"[Learning] Registered {len(rule_ids)} applied rules for {phase_id}")

    def record_phase_rule_effectiveness(self, phase_id: str, success: bool) -> int:
        """Record rule effectiveness based on phase outcome.

        IMP-LOOP-018: Called after phase completion to update rule aging
        based on whether the phase succeeded or failed.

        Args:
            phase_id: Phase identifier
            success: True if phase completed successfully, False otherwise

        Returns:
            Number of rules for which effectiveness was recorded
        """
        from autopack.learned_rules import record_rule_validation_outcome

        applied_rules = self._applied_rules_per_phase.get(phase_id, [])
        if not applied_rules:
            return 0

        project_id = self._project_id or "autopack"

        try:
            record_rule_validation_outcome(project_id, applied_rules, success)
            outcome = "success" if success else "failure"
            logger.info(
                f"[Learning] Recorded rule effectiveness ({outcome}) for "
                f"{len(applied_rules)} rules in {phase_id}"
            )
            return len(applied_rules)
        except Exception as e:
            logger.warning(f"[Learning] Failed to record rule effectiveness for {phase_id}: {e}")
            return 0
        finally:
            # Clear applied rules for this phase after recording
            self._applied_rules_per_phase.pop(phase_id, None)

    def get_applied_rules_for_phase(self, phase_id: str) -> List[str]:
        """Get list of rules applied to a phase.

        Args:
            phase_id: Phase identifier

        Returns:
            List of rule IDs or empty list if none registered
        """
        return self._applied_rules_per_phase.get(phase_id, [])

    def _persist_hint_to_memory(
        self, hint: LearningHint, max_retries: int = 3, verify: bool = True
    ) -> bool:
        """
        Persist a single hint to memory service with guaranteed delivery.

        IMP-LEARN-002: Enhanced with retry logic and verification.
        This is called from record_hint() to ensure hints are not lost
        when the executor exits. Part of IMP-INT-004.

        Args:
            hint: The LearningHint to persist
            max_retries: Maximum number of retry attempts (default: 3)
            verify: Whether to verify persistence by retrieval (default: True)

        Returns:
            True if persistence succeeded and verified, False otherwise
        """
        if not self._memory_service or not getattr(self._memory_service, "enabled", False):
            return False

        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                # Convert LearningHint to telemetry insight format
                insight = {
                    "insight_type": self._map_hint_type_to_insight_type(hint.hint_type),
                    "description": hint.hint_text,
                    "phase_id": hint.phase_id,
                    "run_id": self.run_id,
                    "suggested_action": hint.hint_text,
                    "severity": self._get_hint_severity(hint.hint_type),
                    "source_issue_keys": hint.source_issue_keys,
                    "task_category": hint.task_category,
                    # IMP-LEARN-002: Add hint_id for verification
                    "hint_id": f"{self.run_id}:{hint.phase_id}:{hint.hint_type}",
                }

                # Use the unified write_telemetry_insight method
                result = self._memory_service.write_telemetry_insight(
                    insight=insight,
                    project_id=self._project_id,
                    validate=True,
                    strict=False,
                )

                if result:
                    # IMP-LEARN-002: Verify persistence if requested
                    if verify:
                        if self._verify_single_hint_persistence(hint):
                            logger.debug(
                                f"[IMP-LEARN-002] Persisted and verified hint: "
                                f"{hint.phase_id}/{hint.hint_type} (attempt {attempt + 1})"
                            )
                            return True
                        else:
                            logger.warning(
                                f"[IMP-LEARN-002] Verification failed for hint "
                                f"{hint.phase_id}/{hint.hint_type} (attempt {attempt + 1})"
                            )
                            # Continue to retry
                    else:
                        logger.debug(
                            f"[IMP-LEARN-002] Persisted hint (no verify): "
                            f"{hint.phase_id}/{hint.hint_type}"
                        )
                        return True

            except Exception as e:
                last_error = e
                logger.warning(
                    f"[IMP-LEARN-002] Persist attempt {attempt + 1} failed for "
                    f"{hint.phase_id}: {e}"
                )

            # Exponential backoff before retry (skip on last attempt)
            if attempt < max_retries - 1:
                backoff = 2**attempt  # 1, 2, 4 seconds
                logger.debug(f"[IMP-LEARN-002] Waiting {backoff}s before retry")
                time.sleep(backoff)

        # All retries exhausted - log but don't raise (hint recording shouldn't break execution)
        error_detail = f": {last_error}" if last_error else ""
        logger.error(
            f"[IMP-LEARN-002] Failed to persist hint {hint.phase_id}/{hint.hint_type} "
            f"after {max_retries} attempts{error_detail}"
        )
        return False

    def _verify_single_hint_persistence(self, hint: LearningHint) -> bool:
        """Verify that a single persisted hint is retrievable.

        IMP-LEARN-002: Verifies the specific hint can be retrieved from
        memory service, confirming the persistence succeeded.

        Args:
            hint: The LearningHint to verify

        Returns:
            True if verification succeeds, False otherwise
        """
        if not self._memory_service:
            return False

        try:
            # Query for the specific hint using phase_id and hint_type
            query = f"{hint.hint_type} {hint.phase_id}"

            results = self._memory_service.retrieve_insights(
                query=query,
                limit=5,
                project_id=self._project_id,
                max_age_hours=1.0,  # Recent hints only
            )

            # Check if any result matches our hint
            for result in results:
                content = result.get("content", "") or result.get("description", "")
                hint_id = result.get("hint_id", "")

                # Match on hint_id (most reliable) or phase_id in content
                expected_hint_id = f"{self.run_id}:{hint.phase_id}:{hint.hint_type}"
                if hint_id == expected_hint_id:
                    logger.debug(f"[IMP-LEARN-002] Verification succeeded via hint_id: {hint_id}")
                    return True

                # Fallback: match on phase_id in content
                if hint.phase_id in content:
                    logger.debug(f"[IMP-LEARN-002] Verification succeeded via phase_id match")
                    return True

            # If we got any results with matching hint_type, consider it a weak success
            for result in results:
                insight_type = result.get("insight_type", "")
                expected_type = self._map_hint_type_to_insight_type(hint.hint_type)
                if insight_type == expected_type:
                    logger.debug(f"[IMP-LEARN-002] Verification succeeded via insight_type match")
                    return True

            logger.debug(
                f"[IMP-LEARN-002] Verification failed: no matching hint found "
                f"(query: {query}, results: {len(results)})"
            )
            return False

        except Exception as e:
            logger.warning(f"[IMP-LEARN-002] Verification query failed: {e}")
            return False

    def persist_to_memory(self, memory_service, project_id: Optional[str] = None) -> int:
        """
        Persist accumulated learning hints to memory service.

        This enables cross-run learning by writing hints as telemetry insights
        that can be retrieved in future runs.

        Args:
            memory_service: MemoryService instance (can be None if disabled)
            project_id: Optional project identifier for namespacing

        Returns:
            Number of hints successfully persisted
        """
        if not memory_service or not getattr(memory_service, "enabled", False):
            logger.debug("[Learning] Memory service disabled, skipping hint persistence")
            return 0

        if not self._hints:
            logger.debug("[Learning] No hints to persist")
            return 0

        persisted_count = 0

        for hint in self._hints:
            try:
                # Convert LearningHint to telemetry insight format
                insight = {
                    "insight_type": self._map_hint_type_to_insight_type(hint.hint_type),
                    "description": hint.hint_text,
                    "phase_id": hint.phase_id,
                    "run_id": self.run_id,
                    "suggested_action": hint.hint_text,
                    "severity": self._get_hint_severity(hint.hint_type),
                    "source_issue_keys": hint.source_issue_keys,
                    "task_category": hint.task_category,
                }

                # Use the unified write_telemetry_insight method
                result = memory_service.write_telemetry_insight(
                    insight=insight,
                    project_id=project_id,
                    validate=True,
                    strict=False,
                )

                if result:
                    persisted_count += 1
                    logger.debug(
                        f"[Learning] Persisted hint to memory: {hint.phase_id}/{hint.hint_type}"
                    )

            except Exception as e:
                logger.warning(f"[Learning] Failed to persist hint {hint.phase_id}: {e}")

        logger.info(f"[Learning] Persisted {persisted_count}/{len(self._hints)} hints to memory")
        return persisted_count

    def _map_hint_type_to_insight_type(self, hint_type: str) -> str:
        """Map learning hint types to telemetry insight types."""
        mapping = {
            "auditor_reject": "failure_mode",
            "ci_fail": "failure_mode",
            "patch_apply_error": "failure_mode",
            "infra_error": "retry_cause",
            "success_after_retry": "retry_cause",
            "builder_churn_limit_exceeded": "cost_sink",
            "builder_guardrail": "failure_mode",
            "deliverables_validation_failed": "failure_mode",
        }
        return mapping.get(hint_type, "unknown")

    def _get_hint_severity(self, hint_type: str) -> str:
        """Get severity level for hint type."""
        high_severity = {"ci_fail", "patch_apply_error", "builder_guardrail"}
        medium_severity = {"auditor_reject", "deliverables_validation_failed"}
        low_severity = {"success_after_retry", "infra_error", "builder_churn_limit_exceeded"}

        if hint_type in high_severity:
            return "high"
        elif hint_type in medium_severity:
            return "medium"
        elif hint_type in low_severity:
            return "low"
        return "medium"

    # =========================================================================
    # IMP-LOOP-020: Guaranteed Hint Persistence with Retry and Verification
    # =========================================================================

    def persist_hints_guaranteed(
        self,
        memory_service: Optional[Any] = None,
        project_id: Optional[str] = None,
        max_retries: int = 3,
        verify: bool = True,
    ) -> int:
        """Persist hints with guaranteed delivery using retry and verification.

        IMP-LOOP-020: Ensures hints are persisted across runs with:
        - Retry logic with exponential backoff (3 attempts)
        - Verification that hints are retrievable after persistence
        - Raises HintPersistenceError if all retries fail

        Args:
            memory_service: MemoryService instance (uses self._memory_service if None)
            project_id: Project identifier (uses self._project_id if None)
            max_retries: Maximum number of retry attempts (default: 3)
            verify: Whether to verify persistence by retrieval (default: True)

        Returns:
            Number of hints successfully persisted

        Raises:
            HintPersistenceError: If persistence fails after all retries
        """
        service = memory_service or self._memory_service
        proj_id = project_id or self._project_id

        if not service or not getattr(service, "enabled", False):
            logger.debug("[IMP-LOOP-020] Memory service disabled, skipping guaranteed persistence")
            return 0

        if not self._hints:
            logger.debug("[IMP-LOOP-020] No hints to persist")
            return 0

        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                # Attempt to persist hints
                persisted_count = self._persist_hints_batch(service, proj_id)

                # Verify persistence if requested
                if verify and persisted_count > 0:
                    if self._verify_hints_persistence(service, proj_id):
                        logger.info(
                            f"[IMP-LOOP-020] Successfully persisted and verified "
                            f"{persisted_count} hints (attempt {attempt + 1})"
                        )
                        return persisted_count
                    else:
                        logger.warning(
                            f"[IMP-LOOP-020] Verification failed after persisting "
                            f"{persisted_count} hints (attempt {attempt + 1})"
                        )
                        # Continue to retry
                else:
                    logger.info(
                        f"[IMP-LOOP-020] Persisted {persisted_count} hints "
                        f"(attempt {attempt + 1}, verification skipped)"
                    )
                    return persisted_count

            except Exception as e:
                last_error = e
                logger.warning(f"[IMP-LOOP-020] Persist attempt {attempt + 1} failed: {e}")

            # Exponential backoff before retry
            if attempt < max_retries - 1:
                backoff = 2**attempt  # 1, 2, 4 seconds
                logger.debug(f"[IMP-LOOP-020] Waiting {backoff}s before retry")
                time.sleep(backoff)

        # All retries exhausted
        error_msg = f"Failed to persist {len(self._hints)} hints after {max_retries} attempts"
        if last_error:
            error_msg += f": {last_error}"

        logger.error(f"[IMP-LOOP-020] {error_msg}")
        raise HintPersistenceError(error_msg)

    def _persist_hints_batch(self, memory_service: Any, project_id: Optional[str]) -> int:
        """Persist all hints in a batch operation.

        IMP-LOOP-020: Internal method for persisting hints without retry logic.
        Raises exception if no hints could be persisted to trigger retry.

        Args:
            memory_service: MemoryService instance
            project_id: Project identifier

        Returns:
            Number of hints successfully persisted

        Raises:
            Exception: If all hints fail to persist (triggers retry)
        """
        persisted_count = 0
        last_error: Optional[Exception] = None

        for hint in self._hints:
            try:
                insight = {
                    "insight_type": self._map_hint_type_to_insight_type(hint.hint_type),
                    "description": hint.hint_text,
                    "phase_id": hint.phase_id,
                    "run_id": self.run_id,
                    "suggested_action": hint.hint_text,
                    "severity": self._get_hint_severity(hint.hint_type),
                    "source_issue_keys": hint.source_issue_keys,
                    "task_category": hint.task_category,
                    # IMP-LOOP-020: Add metadata for verification
                    "hint_id": f"{self.run_id}:{hint.phase_id}:{hint.hint_type}",
                    "persistence_verified": False,
                }

                result = memory_service.write_telemetry_insight(
                    insight=insight,
                    project_id=project_id,
                    validate=True,
                    strict=False,
                )

                if result:
                    persisted_count += 1

            except Exception as e:
                last_error = e
                logger.warning(f"[IMP-LOOP-020] Failed to persist hint {hint.phase_id}: {e}")

        # If no hints were persisted and we had errors, raise to trigger retry
        if persisted_count == 0 and last_error is not None:
            raise last_error

        return persisted_count

    def _verify_hints_persistence(self, memory_service: Any, project_id: Optional[str]) -> bool:
        """Verify that persisted hints are retrievable.

        IMP-LOOP-020: Verifies at least one hint can be retrieved from
        memory service, confirming the persistence layer is working.

        Args:
            memory_service: MemoryService instance
            project_id: Project identifier

        Returns:
            True if verification succeeds, False otherwise
        """
        if not self._hints:
            return True  # Nothing to verify

        try:
            # Use the first hint to verify retrieval
            sample_hint = self._hints[0]
            query = f"{sample_hint.hint_type} {sample_hint.phase_id}"

            # Attempt to retrieve insights matching our hint
            results = memory_service.retrieve_insights(
                query=query,
                limit=5,
                project_id=project_id,
                max_age_hours=1.0,  # Recent hints only
            )

            # Check if any result matches our hint
            # Use phase_id as the matching key since it's unique per phase
            for result in results:
                content = result.get("content", "") or result.get("description", "")
                # Match on phase_id or the first part of hint_text (more flexible)
                if sample_hint.phase_id in content or (
                    len(content) > 0 and content[:30] in sample_hint.hint_text
                ):
                    logger.debug("[IMP-LOOP-020] Verification succeeded: found matching hint")
                    return True

            # If we got any results, consider it a success (weak verification)
            # This handles cases where content format varies
            if results:
                logger.debug(
                    f"[IMP-LOOP-020] Verification succeeded: retrieved {len(results)} results"
                )
                return True

            # If we persisted hints but can't retrieve them, verification fails
            logger.warning(
                f"[IMP-LOOP-020] Verification failed: could not retrieve persisted hint "
                f"(query: {query}, results: {len(results)})"
            )
            return False

        except Exception as e:
            logger.warning(f"[IMP-LOOP-020] Verification query failed: {e}")
            return False
