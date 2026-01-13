"""
Error Analysis Module

Analyzes error patterns to detect approach flaws during phase execution.
Distinguishes 'approach flaw' from 'transient failure' by tracking error patterns.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional
from difflib import SequenceMatcher
import re
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class ErrorRecord:
    """Single error occurrence"""

    attempt: int
    error_type: str
    error_details: str
    timestamp: float


@dataclass
class ErrorPattern:
    """Detected error pattern indicating approach flaw"""

    error_type: str
    consecutive_count: int
    similarity_score: float
    is_fatal: bool


class ErrorAnalyzer:
    """
    Analyzes error patterns to detect approach flaws.

    Distinguishes 'approach flaw' from 'transient failure' by tracking
    error patterns: same error type with similar messages indicates
    the underlying implementation approach is wrong.
    """

    def __init__(
        self,
        trigger_threshold: int = 3,
        similarity_threshold: float = 0.8,
        min_message_length: int = 30,
        fatal_error_types: Optional[List[str]] = None,
        similarity_enabled: bool = True,
    ):
        """
        Initialize ErrorAnalyzer.

        Args:
            trigger_threshold: Number of consecutive same-type errors to trigger replan
            similarity_threshold: Minimum message similarity (0.0-1.0) to consider errors similar
            min_message_length: Minimum message length for similarity checking
            fatal_error_types: Error types that trigger immediate replan
            similarity_enabled: Whether to check message similarity (vs type-only)
        """
        self.trigger_threshold = trigger_threshold
        self.similarity_threshold = similarity_threshold
        self.min_message_length = min_message_length
        self.fatal_error_types = fatal_error_types or []
        self.similarity_enabled = similarity_enabled

        # Phase-level error history
        self._error_history: Dict[str, List[ErrorRecord]] = {}

    def record_error(
        self, phase_id: str, attempt: int, error_type: str, error_details: str
    ):
        """Record an error for approach flaw detection"""
        if phase_id not in self._error_history:
            self._error_history[phase_id] = []

        record = ErrorRecord(
            attempt=attempt,
            error_type=error_type,
            error_details=error_details,
            timestamp=time.time(),
        )

        self._error_history[phase_id].append(record)
        logger.debug(f"[ErrorAnalysis] Recorded {error_type} for {phase_id}")

    def detect_approach_flaw(self, phase_id: str) -> Optional[ErrorPattern]:
        """
        Analyze error history to detect fundamental approach flaws.

        Enhanced with message similarity checking:
        - Checks consecutive same-type failures
        - Verifies message similarity >= threshold
        - Supports fatal error types that trigger immediately

        Returns:
            ErrorPattern if approach flaw detected, None otherwise
        """
        errors = self._error_history.get(phase_id, [])
        if len(errors) == 0:
            return None

        # Check for fatal error types (immediate trigger)
        latest_error = errors[-1]
        if latest_error.error_type in self.fatal_error_types:
            logger.info(
                f"[REPLAN-TRIGGER] reason=fatal_error type={latest_error.error_type} "
                f"phase={phase_id} attempt={len(errors)}"
            )
            return ErrorPattern(
                error_type=latest_error.error_type,
                consecutive_count=1,
                similarity_score=1.0,
                is_fatal=True,
            )

        # Need minimum errors to trigger
        if len(errors) < self.trigger_threshold:
            return None

        # Check consecutive same-type failures with message similarity
        recent_errors = errors[-self.trigger_threshold :]

        # Group by error type
        error_types = [e.error_type for e in recent_errors]
        if len(set(error_types)) != 1:
            # Different error types in recent errors - not a repeated pattern
            return None

        error_type = error_types[0]

        # If similarity checking is disabled, trigger on same type alone
        if not self.similarity_enabled:
            logger.info(
                f"[REPLAN-TRIGGER] reason=repeated_error type={error_type} "
                f"phase={phase_id} attempt={len(errors)} count={self.trigger_threshold}"
            )
            return ErrorPattern(
                error_type=error_type,
                consecutive_count=self.trigger_threshold,
                similarity_score=0.0,  # N/A
                is_fatal=False,
            )

        # Check message similarity between consecutive errors
        messages = [e.error_details for e in recent_errors]

        # Skip if messages are too short
        if all(len(m) < self.min_message_length for m in messages):
            logger.debug(
                f"[ErrorAnalysis] Messages too short for similarity check ({phase_id})"
            )
            # Fall back to type-only check
            logger.info(
                f"[REPLAN-TRIGGER] reason=repeated_error_short_msg type={error_type} "
                f"phase={phase_id} attempt={len(errors)} count={self.trigger_threshold}"
            )
            return ErrorPattern(
                error_type=error_type,
                consecutive_count=self.trigger_threshold,
                similarity_score=0.0,  # N/A
                is_fatal=False,
            )

        # Check pairwise similarity between consecutive errors
        all_similar = True
        min_similarity = 1.0

        for i in range(len(messages) - 1):
            similarity = self._calculate_message_similarity(
                messages[i], messages[i + 1]
            )
            min_similarity = min(min_similarity, similarity)
            logger.debug(
                f"[ErrorAnalysis] Message similarity [{i}]->[{i+1}]: {similarity:.2f}"
            )

            if similarity < self.similarity_threshold:
                all_similar = False
                break

        if all_similar:
            logger.info(
                f"[REPLAN-TRIGGER] reason=similar_errors type={error_type} "
                f"phase={phase_id} attempt={len(errors)} count={self.trigger_threshold} "
                f"similarity_threshold={self.similarity_threshold}"
            )
            return ErrorPattern(
                error_type=error_type,
                consecutive_count=self.trigger_threshold,
                similarity_score=min_similarity,
                is_fatal=False,
            )

        logger.debug(
            f"[ErrorAnalysis] No approach flaw for {phase_id}: messages not similar enough"
        )
        return None

    def get_error_history(self, phase_id: str) -> List[ErrorRecord]:
        """Get error history for a phase"""
        return self._error_history.get(phase_id, [])

    def clear_error_history(self, phase_id: str):
        """Clear error history (after successful replan)"""
        if phase_id in self._error_history:
            self._error_history[phase_id] = []
            logger.debug(f"[ErrorAnalysis] Cleared error history for {phase_id}")

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
        normalized = re.sub(
            r"[/\\][\w\-./\\]+\.(py|js|ts|json|yaml|yml|md)", "[PATH]", normalized
        )
        normalized = re.sub(
            r"[a-z]:\\[\w\-\\]+", "[PATH]", normalized, flags=re.IGNORECASE
        )

        # Strip line numbers (e.g., "line 42", ":42:", "L42")
        normalized = re.sub(r"\bline\s*\d+\b", "line [N]", normalized)
        normalized = re.sub(r":\d+:", ":[N]:", normalized)
        normalized = re.sub(r"\bL\d+\b", "L[N]", normalized)

        # Strip UUIDs
        normalized = re.sub(
            r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}",
            "[UUID]",
            normalized,
        )

        # Strip run IDs (common patterns)
        normalized = re.sub(r"\b[a-z]+-\d{8}(-\d+)?\b", "[RUN_ID]", normalized)

        # Strip timestamps (ISO format and common patterns)
        normalized = re.sub(
            r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "[TIMESTAMP]", normalized
        )
        normalized = re.sub(r"\d{2}:\d{2}:\d{2}", "[TIME]", normalized)

        # Strip stack trace lines
        normalized = re.sub(
            r'file "[^"]+", line \[n\]', "file [PATH], line [N]", normalized
        )
        normalized = re.sub(
            r"traceback \(most recent call last\):", "[TRACEBACK]", normalized
        )

        # Collapse whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()

        return normalized

    def _calculate_message_similarity(self, msg1: str, msg2: str) -> float:
        """
        Calculate similarity between two error messages using difflib.

        Returns:
            Float between 0.0 and 1.0 (1.0 = identical)
        """
        if not msg1 or not msg2:
            return 0.0

        norm1 = self._normalize_error_message(msg1)
        norm2 = self._normalize_error_message(msg2)

        return SequenceMatcher(None, norm1, norm2).ratio()
