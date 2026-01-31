"""Budget enforcement for research pipeline.

Provides budget tracking and enforcement gates for research phases.
Prevents expensive operations when budget is exhausted.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PhaseType(Enum):
    """Types of research phases with cost implications."""

    MARKET_RESEARCH = "market_research"
    COMPETITIVE_ANALYSIS = "competitive_analysis"
    TECHNICAL_FEASIBILITY = "technical_feasibility"
    COST_EFFECTIVENESS = "cost_effectiveness"
    MONETIZATION_ANALYSIS = "monetization_analysis"
    FOLLOWUP_RESEARCH = "followup_research"
    CUSTOM = "custom"


class BudgetStatus(Enum):
    """Status of budget tracking."""

    HEALTHY = "healthy"
    WARN = "warn"  # >80% used
    CRITICAL = "critical"  # >95% used
    EXHAUSTED = "exhausted"  # 100% used


@dataclass
class PhaseBudget:
    """Budget for a specific research phase."""

    phase: PhaseType
    estimated_cost: float = 0.0
    actual_cost: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def is_complete(self) -> bool:
        """Check if phase is complete."""
        return self.completed_at is not None

    @property
    def cost_delta(self) -> float:
        """Calculate difference between estimated and actual."""
        return self.actual_cost - self.estimated_cost


@dataclass
class BudgetMetrics:
    """Metrics for budget tracking and reporting."""

    total_budget: float = 0.0
    total_spent: float = 0.0
    phases_executed: List[PhaseBudget] = field(default_factory=list)
    budget_buffer_percent: float = 20.0  # Reserve 20% as buffer
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def available_budget(self) -> float:
        """Calculate available budget after buffer."""
        buffer = self.total_budget * (self.budget_buffer_percent / 100.0)
        return self.total_budget - buffer - self.total_spent

    @property
    def utilization_percent(self) -> float:
        """Calculate percentage of budget used (excluding buffer)."""
        if self.total_budget == 0:
            return 0.0
        usable_budget = self.total_budget * ((100 - self.budget_buffer_percent) / 100.0)
        if usable_budget == 0:
            return 100.0
        return (self.total_spent / usable_budget) * 100.0

    @property
    def status(self) -> BudgetStatus:
        """Determine budget status."""
        if self.total_spent >= self.total_budget:
            return BudgetStatus.EXHAUSTED
        utilization = self.utilization_percent
        if utilization >= 95:
            return BudgetStatus.CRITICAL
        if utilization >= 80:
            return BudgetStatus.WARN
        return BudgetStatus.HEALTHY

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_budget": self.total_budget,
            "total_spent": self.total_spent,
            "available_budget": self.available_budget,
            "utilization_percent": round(self.utilization_percent, 2),
            "buffer_percent": self.budget_buffer_percent,
            "status": self.status.value,
            "phases_executed": len(self.phases_executed),
            "timestamp": self.timestamp.isoformat(),
        }


class BudgetEnforcer:
    """Enforces budget constraints for research pipeline.

    Tracks spending across research phases and prevents expensive operations
    when budget is exhausted. Implements the BudgetTracker protocol.
    """

    # Phase cost estimates (in arbitrary units - can be mapped to actual costs)
    DEFAULT_PHASE_COSTS = {
        PhaseType.MARKET_RESEARCH: 100.0,
        PhaseType.COMPETITIVE_ANALYSIS: 150.0,
        PhaseType.TECHNICAL_FEASIBILITY: 150.0,
        PhaseType.COST_EFFECTIVENESS: 50.0,
        PhaseType.MONETIZATION_ANALYSIS: 75.0,
        PhaseType.FOLLOWUP_RESEARCH: 200.0,  # More expensive as triggered dynamically
    }

    def __init__(
        self,
        total_budget: float,
        buffer_percent: float = 20.0,
        phase_costs: Optional[Dict[PhaseType, float]] = None,
    ):
        """Initialize budget enforcer.

        Args:
            total_budget: Total budget for research in USD
            buffer_percent: Percentage of budget to reserve (default: 20%)
            phase_costs: Optional custom phase cost estimates
        """
        self.metrics = BudgetMetrics(
            total_budget=total_budget,
            budget_buffer_percent=buffer_percent,
        )
        self.phase_costs = phase_costs or self.DEFAULT_PHASE_COSTS
        self._phase_history: Dict[str, PhaseBudget] = {}

    def set_budget(self, total_budget: float) -> None:
        """Set or update total budget.

        Args:
            total_budget: New total budget amount
        """
        logger.info(f"Budget updated: ${self.metrics.total_budget} -> ${total_budget}")
        self.metrics.total_budget = total_budget

    def can_proceed(self, phase_name: Optional[str] = None) -> bool:
        """Check if research can proceed based on budget constraints.

        Args:
            phase_name: Optional name of phase to check budget for

        Returns:
            True if budget allows proceeding, False if exhausted
        """
        if self.metrics.total_budget == 0:
            logger.warning("No budget set for research pipeline")
            return False

        # Check overall budget status
        if self.metrics.status == BudgetStatus.EXHAUSTED:
            logger.warning("Research budget exhausted, cannot proceed")
            return False

        # If phase specified, check phase-specific budget
        if phase_name:
            phase_type = self._get_phase_type(phase_name)
            estimated_cost = self.phase_costs.get(phase_type, 100.0)

            if self.metrics.available_budget < estimated_cost:
                logger.warning(
                    f"Insufficient budget for {phase_name}: "
                    f"need ${estimated_cost}, available ${self.metrics.available_budget:.2f}"
                )
                return False

        return True

    def start_phase(self, phase_name: str) -> None:
        """Mark phase as started and track its budget.

        Args:
            phase_name: Name of the phase
        """
        phase_type = self._get_phase_type(phase_name)
        estimated_cost = self.phase_costs.get(phase_type, 100.0)

        phase_budget = PhaseBudget(
            phase=phase_type,
            estimated_cost=estimated_cost,
            started_at=datetime.now(),
        )
        self._phase_history[phase_name] = phase_budget
        logger.info(
            f"Started phase '{phase_name}' with estimated cost: ${estimated_cost:.2f}"
        )

    def complete_phase(self, phase_name: str, actual_cost: Optional[float] = None) -> None:
        """Mark phase as complete and record actual cost.

        Args:
            phase_name: Name of the phase
            actual_cost: Actual cost incurred (if different from estimate)
        """
        if phase_name not in self._phase_history:
            logger.warning(f"Phase '{phase_name}' was not started")
            return

        phase_budget = self._phase_history[phase_name]
        phase_budget.completed_at = datetime.now()

        # Use actual cost if provided, otherwise use estimate
        phase_budget.actual_cost = actual_cost or phase_budget.estimated_cost

        # Update total spent
        self.metrics.total_spent += phase_budget.actual_cost
        self.metrics.phases_executed.append(phase_budget)

        logger.info(
            f"Completed phase '{phase_name}': "
            f"estimated ${phase_budget.estimated_cost:.2f}, "
            f"actual ${phase_budget.actual_cost:.2f}"
        )

    def record_cost(self, phase_name: str, cost: float) -> None:
        """Record an additional cost for a phase.

        Args:
            phase_name: Name of the phase
            cost: Cost amount to record
        """
        self.metrics.total_spent += cost
        logger.debug(f"Recorded cost for '{phase_name}': ${cost:.2f}")

    def get_metrics(self) -> BudgetMetrics:
        """Get current budget metrics.

        Returns:
            BudgetMetrics with current state
        """
        return self.metrics

    def get_status_summary(self) -> Dict[str, Any]:
        """Get human-readable budget status summary.

        Returns:
            Dictionary with status information
        """
        return {
            "status": self.metrics.status.value,
            "total_budget": f"${self.metrics.total_budget:.2f}",
            "total_spent": f"${self.metrics.total_spent:.2f}",
            "available_budget": f"${self.metrics.available_budget:.2f}",
            "utilization": f"{self.metrics.utilization_percent:.1f}%",
            "phases_completed": len(self.metrics.phases_executed),
            "can_proceed": self.can_proceed(),
        }

    def _get_phase_type(self, phase_name: str) -> PhaseType:
        """Convert phase name to PhaseType.

        Args:
            phase_name: Name of the phase

        Returns:
            PhaseType enum value
        """
        # Try to match phase name to PhaseType
        phase_lower = phase_name.lower()
        for phase_type in PhaseType:
            if phase_type.value in phase_lower:
                return phase_type
        return PhaseType.CUSTOM
