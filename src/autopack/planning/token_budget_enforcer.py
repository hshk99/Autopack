"""Token budget enforcement for IMP-GENAI-002 and BUILD-129.

Prevents context window overflow by validating budgets before/after LLM calls.
Implements proactive budget enforcement with circuit breaker pattern.

Design:
- Pre-call validation: Ensure budget >= estimated tokens before API call
- Post-call validation: Detect truncation and budget exhaustion
- Circuit breaker: Prevent infinite retry loops on budget failures
- Escalation: 50% budget increase when insufficient (capped at 64k)

Key thresholds:
- WARNING: 85% utilization
- EXCEEDED: >100% utilization
- CRITICAL: >120% utilization
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class BudgetStatus(Enum):
    """Budget enforcement status."""

    OK = "ok"  # Within budget
    WARNING = "warning"  # Approaching limit (>85%)
    EXCEEDED = "exceeded"  # Over budget
    CRITICAL = "critical"  # Far over budget (>120%)


@dataclass
class BudgetValidation:
    """Result of budget validation."""

    status: BudgetStatus
    estimated_tokens: int
    budget_tokens: int
    utilization_pct: float
    recommendation: str
    should_escalate: bool


class TokenBudgetEnforcer:
    """Enforces token budget constraints with circuit breaker pattern.

    Implements three-layer enforcement:
    1. Pre-call validation: Check budget before API call
    2. Post-call validation: Detect truncation and overflow
    3. Circuit breaker: Prevent infinite retry loops
    """

    # Thresholds
    WARNING_THRESHOLD = 0.85  # 85% utilization triggers warning
    CRITICAL_THRESHOLD = 1.20  # 120% utilization is critical

    def __init__(self):
        """Initialize budget enforcer."""
        self.overflow_count = 0  # Track overflows for circuit breaker

    def validate_pre_call(
        self,
        estimated_tokens: int,
        budget_tokens: int,
        complexity: str = "medium",
    ) -> BudgetValidation:
        """Validate budget is sufficient before API call.

        Per IMP-GENAI-002: Prevents context window overflow by ensuring
        estimated tokens fit within allocated budget before making the call.

        Args:
            estimated_tokens: Estimated output tokens from TokenEstimator
            budget_tokens: Allocated max_tokens for this phase
            complexity: Phase complexity (low, medium, high)

        Returns:
            BudgetValidation with status and recommendations
        """
        if budget_tokens <= 0:
            return BudgetValidation(
                status=BudgetStatus.CRITICAL,
                estimated_tokens=estimated_tokens,
                budget_tokens=budget_tokens,
                utilization_pct=0.0,
                recommendation="Budget is zero or negative - cannot proceed",
                should_escalate=True,
            )

        utilization = estimated_tokens / budget_tokens

        if utilization >= self.CRITICAL_THRESHOLD:
            status = BudgetStatus.CRITICAL
            increase_pct = int(utilization * 100 - 100)
            recommendation = (
                f"Estimated tokens ({estimated_tokens}) far exceeds budget ({budget_tokens}). "
                f"Increase budget by {increase_pct}%"
            )
            should_escalate = True
        elif utilization >= 1.0:
            status = BudgetStatus.EXCEEDED
            increase_pct = int(utilization * 100 - 100)
            recommendation = (
                f"Estimated tokens ({estimated_tokens}) exceeds budget ({budget_tokens}). "
                f"Increase budget by {increase_pct}%"
            )
            should_escalate = True
        elif utilization >= self.WARNING_THRESHOLD:
            status = BudgetStatus.WARNING
            recommendation = (
                f"Budget utilization at {utilization * 100:.1f}%. "
                f"Consider increasing buffer for safety"
            )
            should_escalate = False
        else:
            status = BudgetStatus.OK
            recommendation = "Budget is sufficient for estimated tokens"
            should_escalate = False

        logger.info(
            f"[BUDGET_PRE_CALL] status={status.value} estimated={estimated_tokens} "
            f"budget={budget_tokens} utilization={utilization * 100:.1f}% "
            f"complexity={complexity}"
        )

        return BudgetValidation(
            status=status,
            estimated_tokens=estimated_tokens,
            budget_tokens=budget_tokens,
            utilization_pct=utilization,
            recommendation=recommendation,
            should_escalate=should_escalate,
        )

    def validate_post_call(
        self,
        actual_tokens: int,
        budget_tokens: int,
        stop_reason: Optional[str] = None,
    ) -> BudgetValidation:
        """Validate actual usage after API call.

        Per IMP-GENAI-002: Detects if output was truncated due to budget
        exhaustion (stop_reason == "max_tokens") and tracks overflow events
        for circuit breaker logic.

        Args:
            actual_tokens: Actual output tokens used
            budget_tokens: Allocated max_tokens
            stop_reason: Stop reason from Anthropic API

        Returns:
            BudgetValidation with status and recommendations
        """
        was_truncated = stop_reason == "max_tokens"
        utilization = actual_tokens / budget_tokens if budget_tokens > 0 else 0.0

        if was_truncated:
            status = BudgetStatus.EXCEEDED
            recommendation = (
                f"Output truncated at {actual_tokens} tokens. " f"Increase budget by 50% for retry"
            )
            should_escalate = True
            self.overflow_count += 1
        elif utilization >= 0.95:
            status = BudgetStatus.WARNING
            recommendation = (
                f"High utilization ({utilization * 100:.1f}%). " f"May truncate on retry"
            )
            should_escalate = True
        else:
            status = BudgetStatus.OK
            recommendation = "Token usage within acceptable limits"
            should_escalate = False

        logger.info(
            f"[BUDGET_POST_CALL] status={status.value} actual={actual_tokens} "
            f"budget={budget_tokens} utilization={utilization * 100:.1f}% "
            f"truncated={was_truncated} overflows={self.overflow_count}"
        )

        return BudgetValidation(
            status=status,
            estimated_tokens=actual_tokens,
            budget_tokens=budget_tokens,
            utilization_pct=utilization,
            recommendation=recommendation,
            should_escalate=should_escalate,
        )

    def get_escalated_budget(
        self,
        current_budget: int,
        complexity: str = "medium",
    ) -> int:
        """Calculate escalated budget for retry.

        Per IMP-GENAI-002: When budget is insufficient, escalate by 50%
        (per best practices from retry analysis). This prevents repeated
        truncation due to underestimation.

        Args:
            current_budget: Current budget that was insufficient
            complexity: Phase complexity

        Returns:
            Escalated budget (50% increase, capped at 64k)
        """
        escalation_factor = 1.5  # 50% increase
        escalated = int(current_budget * escalation_factor)

        # Cap at Anthropic Sonnet 4.5 max (64k)
        escalated = min(escalated, 64000)

        logger.info(
            f"[BUDGET_ESCALATE] from={current_budget} to={escalated} "
            f"complexity={complexity} factor={escalation_factor}x"
        )

        return escalated

    def should_circuit_break(self, max_overflows: int = 3) -> bool:
        """Check if circuit breaker should trip.

        Per IMP-GENAI-002: Prevents infinite retry loops when budget
        is fundamentally insufficient. After N overflows, fail gracefully
        and request human review.

        Args:
            max_overflows: Maximum allowed overflows before circuit breaks

        Returns:
            True if circuit should break
        """
        should_break = self.overflow_count >= max_overflows

        if should_break:
            logger.error(
                f"[BUDGET_CIRCUIT_BREAKER] Circuit breaker tripped: "
                f"{self.overflow_count} overflows >= {max_overflows} threshold. "
                f"Budget enforcement cannot prevent overflow - phase requires human review"
            )

        return should_break
