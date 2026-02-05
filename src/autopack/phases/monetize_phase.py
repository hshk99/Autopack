"""Monetize Phase Implementation for Autonomous Build System.

This module implements the MONETIZE phase type, which enables the autonomous
executor to determine monetization strategies for projects.

Monetize phases are used when:
- A project needs to establish a monetization model
- Revenue strategy decisions are required
- Pricing recommendations need to be generated
- Payment integration setup is needed

Design Principles:
- Monetize phases leverage deployment phase outputs
- Results are practical and actionable
- Clear success/failure criteria
- Integration with BUILD_HISTORY for learning
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MonetizeStatus(Enum):
    """Status of a monetize phase."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MonetizeConfig:
    """Configuration for a monetize phase."""

    revenue_model: str = "freemium"  # freemium, subscription, pay_per_use
    enable_payment_integration: bool = True
    payment_provider: str = "stripe"
    save_to_history: bool = True
    max_duration_minutes: Optional[int] = None


@dataclass
class MonetizeInput:
    """Input data for monetize phase."""

    product_name: str
    target_market: str
    value_proposition: str


@dataclass
class MonetizeOutput:
    """Output from monetize phase."""

    strategy_path: Optional[str] = None
    revenue_model: str = "freemium"
    payment_provider: str = "stripe"
    recommendations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class MonetizePhase:
    """Represents a monetize phase with its configuration and state."""

    phase_id: str
    description: str
    config: MonetizeConfig
    input_data: Optional[MonetizeInput] = None
    status: MonetizeStatus = MonetizeStatus.PENDING
    output: Optional[MonetizeOutput] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert phase to dictionary representation."""
        output_dict = None
        if self.output:
            output_dict = {
                "strategy_path": self.output.strategy_path,
                "revenue_model": self.output.revenue_model,
                "payment_provider": self.output.payment_provider,
                "recommendations": self.output.recommendations,
                "warnings": self.output.warnings,
            }

        input_dict = None
        if self.input_data:
            input_dict = {
                "product_name": self.input_data.product_name,
                "target_market": self.input_data.target_market,
                "value_proposition": self.input_data.value_proposition,
            }

        return {
            "phase_id": self.phase_id,
            "description": self.description,
            "status": self.status.value,
            "config": {
                "revenue_model": self.config.revenue_model,
                "enable_payment_integration": self.config.enable_payment_integration,
                "payment_provider": self.config.payment_provider,
                "save_to_history": self.config.save_to_history,
                "max_duration_minutes": self.config.max_duration_minutes,
            },
            "input_data": input_dict,
            "output": output_dict,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class MonetizePhaseExecutor:
    """Executor for monetize phases."""

    def __init__(
        self,
        workspace_path: Optional[Path] = None,
        build_history_path: Optional[Path] = None,
    ):
        """Initialize the executor.

        Args:
            workspace_path: Optional path to workspace for artifact generation
            build_history_path: Optional path to BUILD_HISTORY.md
        """
        self.workspace_path = workspace_path or Path.cwd()
        self.build_history_path = build_history_path

    def execute(self, phase: MonetizePhase) -> MonetizePhase:
        """Execute a monetize phase.

        Args:
            phase: The phase to execute

        Returns:
            The updated phase with results
        """
        logger.info(f"Executing monetize phase: {phase.phase_id}")

        phase.status = MonetizeStatus.IN_PROGRESS
        phase.started_at = datetime.now()
        phase.output = MonetizeOutput()
        phase.error = None

        try:
            # Validate input
            if not phase.input_data:
                phase.status = MonetizeStatus.FAILED
                phase.error = "No input data provided for monetize phase"
                return phase

            # Generate monetize artifacts
            self._generate_strategy(phase)

            # Mark as completed if not already failed
            if phase.status == MonetizeStatus.IN_PROGRESS:
                phase.status = MonetizeStatus.COMPLETED

            # Save to history if configured
            if phase.config.save_to_history and self.build_history_path:
                self._save_to_history(phase)

        except Exception as e:
            logger.error(f"Phase execution failed: {e}", exc_info=True)
            phase.status = MonetizeStatus.FAILED
            phase.error = str(e)

        finally:
            phase.completed_at = datetime.now()

        return phase

    def _generate_strategy(self, phase: MonetizePhase) -> None:
        """Generate monetization strategy.

        Args:
            phase: The phase being executed
        """
        if not phase.output or not phase.input_data:
            return

        strategy_content = self._generate_strategy_content(phase)

        # Write strategy to workspace
        monetize_dir = self.workspace_path / "monetization"
        monetize_dir.mkdir(parents=True, exist_ok=True)
        strategy_path = monetize_dir / "MONETIZE_STRATEGY.md"
        strategy_path.write_text(strategy_content, encoding="utf-8")

        phase.output.strategy_path = str(strategy_path)
        phase.output.revenue_model = phase.config.revenue_model
        phase.output.payment_provider = phase.config.payment_provider

        logger.info(f"Generated monetization strategy: {strategy_path}")

        # Add recommendations
        phase.output.recommendations = self._generate_recommendations(phase)

    def _generate_strategy_content(self, phase: MonetizePhase) -> str:
        """Generate monetization strategy content.

        Args:
            phase: The phase being executed

        Returns:
            Markdown content for strategy
        """
        if not phase.input_data:
            return ""

        content = f"""# Monetization Strategy for {phase.input_data.product_name}

## Executive Summary

This document outlines the monetization strategy for {phase.input_data.product_name}.

**Target Market**: {phase.input_data.target_market}

**Value Proposition**: {phase.input_data.value_proposition}

## Revenue Model

### Selected Model: {phase.config.revenue_model.replace('_', ' ').title()}

"""

        if phase.config.revenue_model == "freemium":
            content += self._generate_freemium_strategy(phase)
        elif phase.config.revenue_model == "subscription":
            content += self._generate_subscription_strategy(phase)
        elif phase.config.revenue_model == "pay_per_use":
            content += self._generate_pay_per_use_strategy(phase)
        else:
            content += "Custom revenue model - to be defined\n"

        # Payment integration
        if phase.config.enable_payment_integration:
            content += f"\n## Payment Integration\n\n"
            content += f"**Provider**: {phase.config.payment_provider.title()}\n\n"
            content += f"Payment integration will be handled through {phase.config.payment_provider}.\n"

        return content

    def _generate_freemium_strategy(self, phase: MonetizePhase) -> str:
        """Generate freemium strategy details.

        Args:
            phase: The phase being executed

        Returns:
            Strategy content for freemium model
        """
        return """
**Overview**: Free tier attracts users, premium tier generates revenue.

**Free Tier**:
- Basic features included
- Community support
- Usage limits (e.g., 10 API calls/day)

**Premium Tier**:
- All free features plus advanced features
- Priority email support
- No usage limits
- Price: TBD (recommend $9-29/month)

**Expected Metrics**:
- Free to paid conversion: 2-5%
- Customer acquisition cost: TBD
- Average monthly revenue per user: TBD
"""

    def _generate_subscription_strategy(self, phase: MonetizePhase) -> str:
        """Generate subscription strategy details.

        Args:
            phase: The phase being executed

        Returns:
            Strategy content for subscription model
        """
        return """
**Overview**: Recurring monthly or annual billing.

**Tiers**:
- Basic: $9/month - Individual developers
- Pro: $29/month - Small teams
- Enterprise: Custom pricing - Large organizations

**Key Metrics**:
- Monthly recurring revenue (MRR): TBD
- Annual recurring revenue (ARR): TBD
- Customer lifetime value (LTV): TBD
- Churn rate target: <5%

**Annual Discount**: 20% off for annual prepayment
"""

    def _generate_pay_per_use_strategy(self, phase: MonetizePhase) -> str:
        """Generate pay-per-use strategy details.

        Args:
            phase: The phase being executed

        Returns:
            Strategy content for pay-per-use model
        """
        return """
**Overview**: Users pay for consumption (API calls, storage, compute).

**Pricing Structure**:
- API Calls: $0.001 per call (adjust based on cost)
- Storage: $0.02 per GB/month
- Compute: $0.50 per CPU-hour

**Key Metrics**:
- Expected average usage per user: TBD
- Revenue per user per month: TBD
- Scaling efficiency: TBD

**Billing**: Monthly invoices based on actual usage
"""

    def _generate_recommendations(self, phase: MonetizePhase) -> List[str]:
        """Generate recommendations for monetization.

        Args:
            phase: The phase being executed

        Returns:
            List of recommendations
        """
        recommendations = [
            "Validate pricing assumptions with target market via surveys",
            "Start with simple pricing structure and iterate based on feedback",
            "Implement usage tracking and analytics early",
            "Plan payment processor integration (recommended: Stripe)",
            "Define clear refund and cancellation policies",
            "Ensure compliance with applicable tax regulations",
        ]

        if phase.config.revenue_model == "freemium":
            recommendations.extend([
                "Design clear feature differentiation between free and paid tiers",
                "Optimize free-to-paid conversion funnel",
            ])
        elif phase.config.revenue_model == "subscription":
            recommendations.extend([
                "Offer annual billing with discount for better cash flow",
                "Implement trial period (14 days recommended)",
                "Set up billing escalation procedures",
            ])
        elif phase.config.revenue_model == "pay_per_use":
            recommendations.extend([
                "Implement usage tracking and alerts for cost control",
                "Provide cost estimator tool for users",
                "Set up usage-based scaling infrastructure",
            ])

        return recommendations

    def _save_to_history(self, phase: MonetizePhase) -> None:
        """Save phase results to BUILD_HISTORY.

        Args:
            phase: The phase to save
        """
        if not self.build_history_path:
            return

        entry = self._format_history_entry(phase)

        try:
            with open(self.build_history_path, "a", encoding="utf-8") as f:
                f.write("\n" + entry + "\n")
        except Exception as e:
            logger.warning(f"Failed to save to build history: {e}")

    def _format_history_entry(self, phase: MonetizePhase) -> str:
        """Format phase as BUILD_HISTORY entry.

        Args:
            phase: The phase to format

        Returns:
            Formatted markdown entry
        """
        lines = [
            f"## Monetize Phase: {phase.phase_id}",
            f"**Description**: {phase.description}",
            f"**Status**: {phase.status.value}",
            f"**Started**: {phase.started_at}",
            f"**Completed**: {phase.completed_at}",
            "",
        ]

        if phase.output:
            lines.append("### Monetization Strategy")
            lines.append(f"- **Revenue Model**: {phase.output.revenue_model}")
            lines.append(f"- **Payment Provider**: {phase.output.payment_provider}")
            if phase.output.recommendations:
                lines.append(f"- **Recommendations**: {len(phase.output.recommendations)} items")
            lines.append("")

        if phase.error:
            lines.append(f"**Error**: {phase.error}")
            lines.append("")

        return "\n".join(lines)


def create_monetize_phase(
    phase_id: str,
    product_name: str,
    target_market: str,
    value_proposition: str,
    **kwargs,
) -> MonetizePhase:
    """Factory function to create a monetize phase.

    Args:
        phase_id: Unique phase identifier
        product_name: Name of the product
        target_market: Target market description
        value_proposition: Value proposition of the product
        **kwargs: Additional configuration options

    Returns:
        Configured MonetizePhase instance
    """
    config = MonetizeConfig(**kwargs)
    input_data = MonetizeInput(
        product_name=product_name,
        target_market=target_market,
        value_proposition=value_proposition,
    )

    return MonetizePhase(
        phase_id=phase_id,
        description=f"Monetize phase: {phase_id}",
        config=config,
        input_data=input_data,
    )
