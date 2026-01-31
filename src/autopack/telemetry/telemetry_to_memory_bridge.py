"""Bridge component for persisting telemetry insights to memory service.

IMP-REL-011: Implements circuit breaker pattern with file-based fallback queue
to prevent telemetry pipeline stoppage when memory service fails.
"""

import atexit
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from autopack.circuit_breaker import (CircuitBreaker, CircuitBreakerConfig,
                                      CircuitBreakerOpenError)

try:
    from autopack.memory.memory_service import MemoryService
except ImportError:
    MemoryService = None

logger = logging.getLogger(__name__)

# Default path for fallback queue persistence
DEFAULT_FALLBACK_QUEUE_PATH = ".autopack/telemetry_fallback_queue.json"


class TelemetryToMemoryBridge:
    """Bridges telemetry insights to memory service for persistent storage.

    IMP-LOOP-020: This bridge is MANDATORY and cannot be disabled.
    The feedback loop requires telemetry to flow to memory for self-improvement.

    IMP-REL-011: Implements circuit breaker pattern with:
    - Exponential backoff retry (3 attempts)
    - Circuit breaker that opens after 3 consecutive failures
    - File-based fallback queue for when circuit is open
    - Automatic recovery and queue draining when circuit closes
    """

    def __init__(
        self,
        memory_service: Optional["MemoryService"] = None,
        fallback_queue_path: str = DEFAULT_FALLBACK_QUEUE_PATH,
    ):
        self.memory_service = memory_service
        self._persisted_insights: set = set()  # For deduplication

        # IMP-REL-011: Circuit breaker for memory service resilience
        self._circuit_breaker = CircuitBreaker(
            name="telemetry_to_memory",
            config=CircuitBreakerConfig(
                failure_threshold=3,  # Open after 3 failures
                success_threshold=2,  # Close after 2 successes in half-open
                timeout=60.0,  # Wait 60s before trying again
                half_open_timeout=30.0,
            ),
        )

        # IMP-REL-011: File-based fallback queue
        self._fallback_queue_path = Path(fallback_queue_path)
        self._fallback_queue: List[Dict[str, Any]] = []
        self._load_fallback_queue()

        # Register cleanup on process exit
        atexit.register(self._cleanup)

    def persist_insights(
        self, ranked_issues: List[Dict[str, Any]], run_id: str, project_id: Optional[str] = None
    ) -> int:
        """Persist ranked issues to memory service.

        IMP-REL-011: Uses circuit breaker pattern with fallback queue.

        Args:
            ranked_issues: List of ranked issues from TelemetryAnalyzer
            run_id: Current run ID for correlation
            project_id: Optional project ID for namespacing

        Returns:
            Number of insights persisted (or queued if circuit is open)
        """
        if not self.memory_service or not self.memory_service.enabled:
            return 0

        # IMP-REL-011: Try to drain fallback queue first if circuit is available
        if self._circuit_breaker.is_available() and self._fallback_queue:
            self._drain_fallback_queue()

        persisted_count = 0

        for issue in ranked_issues:
            insight = self._convert_to_insight(issue, run_id)
            insight_key = f"{insight['insight_type']}:{insight['insight_id']}"

            # Deduplication: don't persist same insight multiple times
            if insight_key in self._persisted_insights:
                continue

            # IMP-REL-011: Use circuit breaker protected persistence
            if self._persist_with_circuit_breaker(insight, project_id):
                self._persisted_insights.add(insight_key)
                persisted_count += 1

        return persisted_count

    def _convert_to_insight(self, issue: Dict[str, Any], run_id: str) -> Dict[str, Any]:
        """Convert issue dict to TelemetryInsight object."""
        insight_type = issue.get("issue_type", "unknown")
        insight_id = f"{run_id}_{insight_type}_{issue.get('rank', 0)}"

        return {
            "insight_id": insight_id,
            "insight_type": insight_type,
            "phase_id": issue.get("phase_id"),
            "severity": issue.get("severity", "medium"),
            "description": issue.get("details", ""),
            "metric_value": issue.get("metric_value", 0.0),
            "occurrences": issue.get("occurrences", 1),
            "suggested_action": issue.get("suggested_action"),
        }

    def _persist_with_circuit_breaker(
        self, insight: Dict[str, Any], project_id: Optional[str] = None
    ) -> bool:
        """Persist insight with circuit breaker protection.

        IMP-REL-011: Uses circuit breaker to protect against memory service failures.
        Falls back to queue if circuit is open.

        Args:
            insight: Insight data to persist
            project_id: Optional project ID

        Returns:
            True if persisted (or queued), False on failure
        """
        try:
            # Try to persist through circuit breaker
            self._circuit_breaker.call(self._persist_single_insight_with_retry, insight, project_id)
            return True
        except CircuitBreakerOpenError:
            # Circuit is open, queue for later
            logger.warning(
                f"[IMP-REL-011] Circuit breaker open, queuing insight: "
                f"{insight.get('insight_type', 'unknown')}"
            )
            self._queue_to_fallback(insight, project_id)
            return True
        except Exception as e:
            # Unexpected error after retries
            logger.error(f"[IMP-REL-011] Failed to persist insight after retries: {e}")
            self._queue_to_fallback(insight, project_id)
            return True

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _persist_single_insight_with_retry(
        self, insight: Dict[str, Any], project_id: Optional[str] = None
    ) -> None:
        """Persist single insight with retry logic.

        IMP-REL-011: Implements exponential backoff retry.

        Args:
            insight: Insight data to persist
            project_id: Optional project ID

        Raises:
            Exception: If persistence fails
        """
        self._persist_single_insight(insight, project_id)

    def _persist_single_insight(
        self, insight: Dict[str, Any], project_id: Optional[str] = None
    ) -> None:
        """Persist single insight to appropriate memory collection."""
        if not self.memory_service:
            return

        # Use the unified write_telemetry_insight method that routes appropriately
        self.memory_service.write_telemetry_insight(insight, project_id)

    # -------------------------------------------------------------------------
    # IMP-REL-011: Fallback Queue Management
    # -------------------------------------------------------------------------

    def _load_fallback_queue(self) -> None:
        """Load fallback queue from file on startup."""
        if self._fallback_queue_path.exists():
            try:
                with open(self._fallback_queue_path, "r", encoding="utf-8") as f:
                    self._fallback_queue = json.load(f)
                logger.info(
                    f"[IMP-REL-011] Loaded {len(self._fallback_queue)} items from fallback queue"
                )
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"[IMP-REL-011] Failed to load fallback queue: {e}")
                self._fallback_queue = []
        else:
            self._fallback_queue = []

    def _save_fallback_queue(self) -> None:
        """Save fallback queue to file."""
        try:
            # Ensure directory exists
            self._fallback_queue_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self._fallback_queue_path, "w", encoding="utf-8") as f:
                json.dump(self._fallback_queue, f, indent=2, default=str)
            logger.debug(f"[IMP-REL-011] Saved {len(self._fallback_queue)} items to fallback queue")
        except IOError as e:
            logger.error(f"[IMP-REL-011] Failed to save fallback queue: {e}")

    def _queue_to_fallback(self, insight: Dict[str, Any], project_id: Optional[str] = None) -> None:
        """Queue insight to fallback for later persistence.

        Args:
            insight: Insight data to queue
            project_id: Optional project ID
        """
        queue_entry = {
            "insight": insight,
            "project_id": project_id,
        }
        self._fallback_queue.append(queue_entry)
        self._save_fallback_queue()
        logger.info(
            f"[IMP-REL-011] Queued insight to fallback (queue size: {len(self._fallback_queue)})"
        )

    def _drain_fallback_queue(self) -> int:
        """Attempt to drain the fallback queue.

        Called when circuit breaker is available to retry queued insights.

        Returns:
            Number of items successfully drained
        """
        if not self._fallback_queue:
            return 0

        drained_count = 0
        remaining_queue: List[Dict[str, Any]] = []

        logger.info(
            f"[IMP-REL-011] Attempting to drain {len(self._fallback_queue)} items from fallback queue"
        )

        for entry in self._fallback_queue:
            insight = entry.get("insight", {})
            project_id = entry.get("project_id")

            try:
                self._circuit_breaker.call(
                    self._persist_single_insight_with_retry, insight, project_id
                )
                drained_count += 1
            except CircuitBreakerOpenError:
                # Circuit opened during drain, stop and keep remaining
                remaining_queue.append(entry)
                remaining_queue.extend(
                    self._fallback_queue[self._fallback_queue.index(entry) + 1 :]
                )
                break
            except Exception as e:
                # Keep failed items for next attempt
                logger.warning(f"[IMP-REL-011] Failed to drain queued insight: {e}")
                remaining_queue.append(entry)

        self._fallback_queue = remaining_queue
        self._save_fallback_queue()

        if drained_count > 0:
            logger.info(
                f"[IMP-REL-011] Drained {drained_count} items from fallback queue "
                f"({len(self._fallback_queue)} remaining)"
            )

        return drained_count

    def get_fallback_queue_size(self) -> int:
        """Get current size of the fallback queue.

        Returns:
            Number of items in fallback queue
        """
        return len(self._fallback_queue)

    def get_circuit_breaker_state(self) -> str:
        """Get current circuit breaker state.

        Returns:
            State name (closed, open, half_open)
        """
        return self._circuit_breaker.get_state().value

    def _cleanup(self) -> None:
        """Cleanup on process exit - ensure fallback queue is saved."""
        if self._fallback_queue:
            logger.info(
                f"[IMP-REL-011] Saving {len(self._fallback_queue)} items to fallback queue on exit"
            )
            self._save_fallback_queue()

    def clear_cache(self) -> None:
        """Clear deduplication cache (call between runs)."""
        self._persisted_insights.clear()
