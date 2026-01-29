"""Context preparation cost tracking for IMP-COST-004 and budget gating for IMP-COST-001.

Tracks previously invisible context preparation overhead:
- File reads (count and bytes)
- Embedding API calls and token usage
- Artifact loads (bytes)
- Scope analysis duration
- Estimated token equivalent of prep work

This enables visibility into 20-40% hidden overhead in context assembly phase.

IMP-COST-001: Budget status tracking for task generation gating.
Provides real-time budget status to pre-filter high-cost tasks when budget is constrained.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class ContextPrepCost:
    """Tracks context preparation costs."""

    phase_id: str
    file_reads_count: int
    file_reads_bytes: int
    embedding_calls: int
    embedding_tokens: int
    artifact_loads: int
    artifact_bytes: int
    scope_analysis_ms: float
    total_prep_ms: float

    @property
    def estimated_token_equivalent(self) -> int:
        """Estimate token equivalent of context prep work.

        Rough estimate: 1 token ≈ 4 bytes, plus embedding tokens directly.
        """
        # Bytes to token conversion
        bytes_total = self.file_reads_bytes + self.artifact_bytes
        bytes_as_tokens = bytes_total // 4
        return bytes_as_tokens + self.embedding_tokens


class ContextPrepTracker:
    """Tracks context preparation costs.

    Records file reads, embedding API calls, artifact loads, and scope analysis
    duration to measure previously invisible context preparation overhead.
    """

    def __init__(self, phase_id: str):
        """Initialize context preparation tracker.

        Args:
            phase_id: Identifier for the phase being tracked
        """
        self.phase_id = phase_id
        self._start_time: float | None = None
        self._file_reads: List[Dict[str, int]] = []
        self._embedding_calls: List[Dict[str, int]] = []
        self._artifact_loads: List[Dict[str, int]] = []
        self._scope_analysis_ms: float = 0.0

    def start(self) -> None:
        """Start tracking."""
        self._start_time = time.time()

    def record_file_read(self, path: str, bytes_read: int) -> None:
        """Record a file read operation.

        Args:
            path: File path that was read
            bytes_read: Number of bytes read
        """
        self._file_reads.append({"path": path, "bytes": bytes_read})

    def record_embedding_call(self, tokens: int) -> None:
        """Record an embedding API call.

        Args:
            tokens: Number of tokens used in the embedding call
        """
        self._embedding_calls.append({"tokens": tokens})

    def record_artifact_load(self, artifact_id: str, bytes_loaded: int) -> None:
        """Record an artifact load.

        Args:
            artifact_id: Identifier for the artifact
            bytes_loaded: Number of bytes loaded
        """
        self._artifact_loads.append({"id": artifact_id, "bytes": bytes_loaded})

    def record_scope_analysis(self, duration_ms: float) -> None:
        """Record scope analysis duration.

        Args:
            duration_ms: Duration of scope analysis in milliseconds
        """
        self._scope_analysis_ms = duration_ms

    def finalize(self) -> ContextPrepCost:
        """Finalize and return cost summary.

        Returns:
            ContextPrepCost object with aggregated metrics
        """
        total_ms = (time.time() - self._start_time) * 1000 if self._start_time else 0

        return ContextPrepCost(
            phase_id=self.phase_id,
            file_reads_count=len(self._file_reads),
            file_reads_bytes=sum(r["bytes"] for r in self._file_reads),
            embedding_calls=len(self._embedding_calls),
            embedding_tokens=sum(e["tokens"] for e in self._embedding_calls),
            artifact_loads=len(self._artifact_loads),
            artifact_bytes=sum(a["bytes"] for a in self._artifact_loads),
            scope_analysis_ms=self._scope_analysis_ms,
            total_prep_ms=total_ms,
        )


# =============================================================================
# IMP-COST-001: Budget Status Tracking for Task Generation Gating
# =============================================================================

# Default thresholds for budget gating
DEFAULT_DAILY_TOKEN_BUDGET = 5_000_000  # 5M tokens per day
DEFAULT_LOW_COST_TASK_THRESHOLD = 50_000  # Tasks estimated below this are "low cost"
DEFAULT_BUDGET_CONSTRAINT_THRESHOLD = 0.5  # Constrain when < 50% remaining


@dataclass
class BudgetStatus:
    """Current budget status for task generation gating (IMP-COST-001).

    Provides real-time budget information to enable task generation to
    pre-filter high-cost tasks when budget is constrained.
    """

    total_budget: int  # Total daily token budget
    used: int  # Tokens used today
    remaining: int  # Tokens remaining
    remaining_percentage: float  # Remaining as percentage (0.0 to 1.0)
    low_cost_threshold: int  # Tasks below this estimated cost are "low cost"
    constrained: bool  # True when remaining_percentage < constraint threshold


class CostTracker:
    """Tracks token usage and budget status for task generation gating (IMP-COST-001).

    Aggregates token usage from the database and provides budget status
    to inform task generation decisions. When budget is constrained,
    task generation should pre-filter high-cost tasks.
    """

    def __init__(
        self,
        db_session: Optional["Session"] = None,
        daily_token_budget: int = DEFAULT_DAILY_TOKEN_BUDGET,
        low_cost_task_threshold: int = DEFAULT_LOW_COST_TASK_THRESHOLD,
        budget_constraint_threshold: float = DEFAULT_BUDGET_CONSTRAINT_THRESHOLD,
    ):
        """Initialize cost tracker.

        Args:
            db_session: SQLAlchemy session for querying usage data
            daily_token_budget: Maximum tokens allowed per day
            low_cost_task_threshold: Estimated cost threshold for "low cost" tasks
            budget_constraint_threshold: Remaining percentage below which budget is constrained
        """
        self._db_session = db_session
        self._daily_token_budget = daily_token_budget
        self._low_cost_task_threshold = low_cost_task_threshold
        self._budget_constraint_threshold = budget_constraint_threshold

    def _get_tokens_used_today(self) -> int:
        """Query total tokens used today from database.

        Returns:
            Total tokens used since midnight UTC today
        """
        if self._db_session is None:
            logger.warning("[IMP-COST-001] No database session available, returning 0 tokens used")
            return 0

        try:
            from sqlalchemy import func

            from ..usage_recorder import LlmUsageEvent

            # Calculate start of today in UTC
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            # Sum total_tokens from all usage events since today start
            result = (
                self._db_session.query(func.sum(LlmUsageEvent.total_tokens))
                .filter(LlmUsageEvent.created_at >= today_start)
                .scalar()
            )

            tokens_used = result or 0
            logger.debug(f"[IMP-COST-001] Tokens used today: {tokens_used:,}")
            return tokens_used

        except Exception as e:
            logger.warning(f"[IMP-COST-001] Failed to query tokens used: {e}")
            return 0

    def get_budget_status(self) -> BudgetStatus:
        """Return current budget status for task generation gating (IMP-COST-001).

        Queries token usage from the database and computes budget status
        including remaining tokens and whether budget is constrained.

        Returns:
            BudgetStatus with current budget information
        """
        total_budget = self._daily_token_budget
        used = self._get_tokens_used_today()
        remaining = max(0, total_budget - used)

        # Calculate remaining percentage (avoid division by zero)
        remaining_percentage = remaining / total_budget if total_budget > 0 else 0.0

        # Determine if budget is constrained
        constrained = remaining_percentage < self._budget_constraint_threshold

        status = BudgetStatus(
            total_budget=total_budget,
            used=used,
            remaining=remaining,
            remaining_percentage=remaining_percentage,
            low_cost_threshold=self._low_cost_task_threshold,
            constrained=constrained,
        )

        if constrained:
            logger.info(
                f"[IMP-COST-001] Budget constrained: {remaining_percentage:.1%} remaining "
                f"({remaining:,}/{total_budget:,} tokens)"
            )

        return status
