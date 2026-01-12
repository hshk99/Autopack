"""Retrieval injection with SOT budget gating.

Extracted from autonomous_executor.py as part of PR-EXE-5 (god file refactoring).

This module implements budget-aware SOT (Source of Truth) retrieval injection,
ensuring that memory retrieval respects context budget limits and provides
telemetry for observability.

Policy Goals:
1. Gate SOT retrieval based on available context budget
2. Track retrieval usage per run for budget management
3. Provide telemetry for retrieval success/failure
4. Enable testable, deterministic budget decisions

SOT Budget Policy:
- Global kill switch: autopack_sot_retrieval_enabled (default: False)
- Budget check: max_context_chars >= (sot_budget + 2000)
  - sot_budget: autopack_sot_retrieval_max_chars (default: 4000)
  - 2000-char reserve for non-SOT context
- Budget tracking per run_id for multi-phase runs

See docs/SOT_MEMORY_INTEGRATION_EXAMPLE.md for integration pattern.
"""

from dataclasses import dataclass
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class GateDecision:
    """Decision about whether SOT retrieval is allowed.

    Attributes:
        allowed: True if retrieval should proceed
        reason: Human-readable explanation of the decision
        budget_remaining: Estimated remaining budget after this retrieval
        sot_budget: Configured SOT budget limit
        reserve_budget: Reserved budget for non-SOT context
    """
    allowed: bool
    reason: str
    budget_remaining: int
    sot_budget: int
    reserve_budget: int = 2000


class RetrievalInjection:
    """Budget-aware SOT retrieval injection.

    This class implements the SOT budget gating logic extracted from
    autonomous_executor.py. It provides deterministic methods for deciding
    whether retrieval should be included based on budget availability.

    Configuration:
        sot_budget_limit: Maximum characters for SOT retrieval (default: 4000)
        telemetry_enabled: Whether to record telemetry (default: False)
        reserve_budget: Characters reserved for non-SOT context (default: 2000)
        enabled: Global kill switch for SOT retrieval (default: False)

    Usage:
        injection = RetrievalInjection(
            sot_budget_limit=4000,
            telemetry_enabled=True,
            enabled=True
        )

        # Gate retrieval decision
        gate = injection.gate_sot_retrieval(
            max_context_chars=10000,
            phase_id="phase_1"
        )

        if gate.allowed:
            # Proceed with retrieval
            ...

        # Record telemetry
        injection.record_retrieval_telemetry(
            run_id="run_123",
            phase_id="phase_1",
            entries=3,
            success=True
        )
    """

    def __init__(
        self,
        sot_budget_limit: int = 4000,
        telemetry_enabled: bool = False,
        reserve_budget: int = 2000,
        enabled: bool = False,
    ):
        """Initialize retrieval injection manager.

        Args:
            sot_budget_limit: Maximum characters for SOT retrieval
            telemetry_enabled: Whether to record telemetry
            reserve_budget: Characters reserved for non-SOT context
            enabled: Global kill switch for SOT retrieval
        """
        self.sot_budget_limit = sot_budget_limit
        self.telemetry_enabled = telemetry_enabled
        self.reserve_budget = reserve_budget
        self.enabled = enabled

        # Track usage per run for multi-phase budget management
        self._run_usage: Dict[str, int] = {}

    def gate_sot_retrieval(
        self,
        max_context_chars: int,
        phase_id: str = None,
        requested_entries: int = 3,
    ) -> GateDecision:
        """Gate SOT retrieval based on budget availability.

        This implements the budget gating logic from autonomous_executor.py:
        - Global kill switch: if not enabled, deny immediately
        - Budget check: max_context_chars >= (sot_budget + reserve_budget)
        - The reserve ensures room for other context sections

        Args:
            max_context_chars: Total context budget allocated for this retrieval
            phase_id: Optional phase identifier for logging
            requested_entries: Number of entries to retrieve (for logging)

        Returns:
            GateDecision with verdict and budget details
        """
        prefix = f"[{phase_id}] " if phase_id else ""

        # Global kill switch
        if not self.enabled:
            logger.info(
                f"{prefix}[SOT] Retrieval disabled by config "
                f"(enabled={self.enabled})"
            )
            return GateDecision(
                allowed=False,
                reason="SOT retrieval disabled by configuration",
                budget_remaining=max_context_chars,
                sot_budget=self.sot_budget_limit,
            )

        # Budget gating: ensure we have enough headroom
        min_required_budget = self.sot_budget_limit + self.reserve_budget

        if max_context_chars < min_required_budget:
            logger.info(
                f"{prefix}[SOT] Skipping retrieval - insufficient budget "
                f"(available: {max_context_chars}, needs: {min_required_budget}, "
                f"sot_cap={self.sot_budget_limit}, reserve={self.reserve_budget})"
            )
            return GateDecision(
                allowed=False,
                reason=f"Insufficient budget: {max_context_chars} < {min_required_budget}",
                budget_remaining=max_context_chars,
                sot_budget=self.sot_budget_limit,
            )

        # Budget check passed
        budget_remaining = max_context_chars - self.sot_budget_limit
        logger.info(
            f"{prefix}[SOT] Including retrieval (budget: {max_context_chars}, "
            f"sot_cap={self.sot_budget_limit}, entries: {requested_entries}, "
            f"remaining: {budget_remaining})"
        )

        return GateDecision(
            allowed=True,
            reason="Budget available for SOT retrieval",
            budget_remaining=budget_remaining,
            sot_budget=self.sot_budget_limit,
        )

    def record_retrieval_telemetry(
        self,
        run_id: str,
        phase_id: str,
        entries: int,
        success: bool,
        chars_retrieved: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Record SOT retrieval telemetry.

        This method tracks retrieval attempts for observability and budget
        management. When telemetry is enabled, it logs detailed metrics about
        each retrieval operation.

        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            entries: Number of entries retrieved
            success: Whether retrieval succeeded
            chars_retrieved: Number of characters retrieved
            error: Error message if retrieval failed

        Notes:
            - Only logs when telemetry_enabled=True
            - Failures are logged as warnings and do not crash execution
            - Tracks cumulative usage per run_id for budget management
        """
        if not self.telemetry_enabled:
            return

        # Update run usage tracking
        if success:
            current_usage = self._run_usage.get(run_id, 0)
            self._run_usage[run_id] = current_usage + chars_retrieved

        status = "SUCCESS" if success else "FAILURE"
        error_msg = f", error={error}" if error else ""

        logger.info(
            f"[{phase_id}] [SOT] Telemetry: run_id={run_id}, "
            f"status={status}, entries={entries}, "
            f"chars={chars_retrieved}, "
            f"cumulative={self._run_usage.get(run_id, 0)}"
            f"{error_msg}"
        )

    def get_remaining_budget(self, run_id: str, total_budget: int = 50000) -> int:
        """Calculate remaining SOT budget for a run.

        This method tracks cumulative usage across phases within a run,
        enabling multi-phase budget management.

        Args:
            run_id: Run identifier
            total_budget: Total budget allocated for this run (default: 50K)

        Returns:
            Remaining budget in characters
        """
        used = self._run_usage.get(run_id, 0)
        remaining = max(0, total_budget - used)

        logger.debug(
            f"[{run_id}] Budget: used={used}, remaining={remaining}/{total_budget}"
        )

        return remaining

    def reset_run_budget(self, run_id: str) -> None:
        """Reset budget tracking for a run.

        This is useful for testing or when starting a new run with the same ID.

        Args:
            run_id: Run identifier to reset
        """
        if run_id in self._run_usage:
            logger.info(f"[{run_id}] Resetting budget tracking")
            del self._run_usage[run_id]

    def get_budget_utilization(self, run_id: str, total_budget: int = 50000) -> float:
        """Calculate budget utilization percentage for a run.

        Args:
            run_id: Run identifier
            total_budget: Total budget allocated for this run

        Returns:
            Utilization percentage (0-100)
        """
        used = self._run_usage.get(run_id, 0)
        if total_budget <= 0:
            return 0.0
        return (used / total_budget) * 100

    def should_warn_budget(
        self,
        run_id: str,
        total_budget: int = 50000,
        warning_threshold: float = 80.0
    ) -> bool:
        """Check if budget utilization warrants a warning.

        Args:
            run_id: Run identifier
            total_budget: Total budget allocated for this run
            warning_threshold: Percentage threshold for warning (default: 80%)

        Returns:
            True if utilization exceeds warning threshold
        """
        utilization = self.get_budget_utilization(run_id, total_budget)
        return utilization >= warning_threshold

    @classmethod
    def from_settings(cls, settings) -> "RetrievalInjection":
        """Create instance from application settings.

        Args:
            settings: Application settings object with SOT configuration

        Returns:
            Configured RetrievalInjection instance
        """
        return cls(
            sot_budget_limit=getattr(settings, 'autopack_sot_retrieval_max_chars', 4000),
            telemetry_enabled=getattr(settings, 'TELEMETRY_DB_ENABLED', False),
            reserve_budget=2000,
            enabled=getattr(settings, 'autopack_sot_retrieval_enabled', False),
        )
