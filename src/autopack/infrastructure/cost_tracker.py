"""Infrastructure cost tracking and comparison utilities.

Provides cost estimation and tracking for Hetzner CPU and RunPod GPU compute.
Helps with decision-making for infrastructure provisioning based on workload type.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ProviderType(Enum):
    """Infrastructure provider types."""

    HETZNER = "hetzner"
    RUNPOD = "runpod"


class WorkloadType(Enum):
    """Types of workloads for cost optimization."""

    BATCH_PROCESSING = "batch_processing"  # CPU-intensive, long-running
    INFERENCE = "inference"  # GPU-intensive, variable duration
    TRAINING = "training"  # GPU-intensive, long-running
    DATA_PREP = "data_prep"  # CPU-intensive, medium-duration


@dataclass
class CostBreakdown:
    """Cost breakdown for a compute resource."""

    provider: ProviderType
    resource_type: str  # e.g., "cx22", "A40"
    hourly_rate: float
    estimated_hours: float
    total_cost: float = 0.0

    def __post_init__(self) -> None:
        """Calculate total cost."""
        self.total_cost = self.hourly_rate * self.estimated_hours


@dataclass
class CostEstimate:
    """Cost estimate comparison between providers."""

    workload_type: WorkloadType
    estimated_duration_hours: float
    breakdowns: List[CostBreakdown] = field(default_factory=list)
    recommended_provider: Optional[ProviderType] = None
    recommended_resource: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def get_cheapest_option(self) -> Optional[CostBreakdown]:
        """Get the cheapest option from available breakdowns."""
        if not self.breakdowns:
            return None
        return min(self.breakdowns, key=lambda x: x.total_cost)


@dataclass
class CostEvent:
    """Record of a cost event (service creation, deletion, etc.)."""

    timestamp: datetime
    provider: ProviderType
    resource_id: str
    resource_type: str
    event_type: str  # "create", "delete", "job_submit", etc.
    cost_incurred: float = 0.0
    cumulative_cost: float = 0.0


class InfrastructureCostTracker:
    """Tracks and estimates infrastructure costs.

    Provides cost comparison between Hetzner CPU and RunPod GPU options
    to help select the most cost-effective provider for each workload.
    """

    # Hetzner pricing (EUR/hour, approximate)
    HETZNER_PRICING = {
        "cx22": 0.005,  # 2vCPU, 4GB RAM
        "cx32": 0.010,  # 4vCPU, 8GB RAM
        "cx42": 0.015,  # 8vCPU, 16GB RAM
        "cx52": 0.020,  # 16vCPU, 32GB RAM
    }

    # RunPod pricing (USD/hour, approximate)
    RUNPOD_PRICING = {
        "A100": 0.75,  # Full A100 GPU
        "A40": 0.40,  # A40 GPU
        "RTX_A6000": 0.35,  # RTX A6000
        "RTX_4090": 0.35,  # RTX 4090
        "RTX_4080": 0.30,  # RTX 4080
        "H100": 1.75,  # Full H100 GPU
        "L40S": 0.55,  # L40S GPU
    }

    # Estimated task durations (hours)
    ESTIMATED_DURATIONS = {
        WorkloadType.BATCH_PROCESSING: 2.0,
        WorkloadType.INFERENCE: 0.5,
        WorkloadType.TRAINING: 8.0,
        WorkloadType.DATA_PREP: 1.0,
    }

    def __init__(self) -> None:
        """Initialize cost tracker."""
        self.cost_events: List[CostEvent] = []
        self.cumulative_cost: float = 0.0

    def estimate_cost(
        self,
        workload_type: WorkloadType,
        duration_hours: Optional[float] = None,
    ) -> CostEstimate:
        """Estimate and compare costs for a workload.

        Args:
            workload_type: Type of workload to estimate.
            duration_hours: Optional override for estimated duration.

        Returns:
            CostEstimate with breakdown of options.
        """
        estimated_hours = duration_hours or self.ESTIMATED_DURATIONS[workload_type]

        breakdowns: List[CostBreakdown] = []

        # Add Hetzner options (CPU-heavy workloads)
        if workload_type in (WorkloadType.BATCH_PROCESSING, WorkloadType.DATA_PREP):
            for resource_type, hourly_rate in self.HETZNER_PRICING.items():
                breakdown = CostBreakdown(
                    provider=ProviderType.HETZNER,
                    resource_type=resource_type,
                    hourly_rate=hourly_rate,
                    estimated_hours=estimated_hours,
                )
                breakdowns.append(breakdown)

        # Add RunPod options (GPU-heavy workloads)
        if workload_type in (WorkloadType.INFERENCE, WorkloadType.TRAINING):
            for resource_type, hourly_rate in self.RUNPOD_PRICING.items():
                breakdown = CostBreakdown(
                    provider=ProviderType.RUNPOD,
                    resource_type=resource_type,
                    hourly_rate=hourly_rate,
                    estimated_hours=estimated_hours,
                )
                breakdowns.append(breakdown)

        # If no provider-specific options, add both
        if not breakdowns:
            for resource_type, hourly_rate in self.HETZNER_PRICING.items():
                breakdown = CostBreakdown(
                    provider=ProviderType.HETZNER,
                    resource_type=resource_type,
                    hourly_rate=hourly_rate,
                    estimated_hours=estimated_hours,
                )
                breakdowns.append(breakdown)

        # Sort by cost
        breakdowns.sort(key=lambda x: x.total_cost)

        estimate = CostEstimate(
            workload_type=workload_type,
            estimated_duration_hours=estimated_hours,
            breakdowns=breakdowns,
        )

        # Set recommendation
        if breakdowns:
            cheapest = breakdowns[0]
            estimate.recommended_provider = cheapest.provider
            estimate.recommended_resource = cheapest.resource_type

        return estimate

    def record_event(
        self,
        provider: ProviderType,
        resource_id: str,
        resource_type: str,
        event_type: str,
        cost_incurred: float = 0.0,
    ) -> None:
        """Record a cost event.

        Args:
            provider: Infrastructure provider.
            resource_id: ID of the resource.
            resource_type: Type of resource (e.g., "cx22", "A40").
            event_type: Type of event (e.g., "create", "delete").
            cost_incurred: Cost associated with this event.
        """
        self.cumulative_cost += cost_incurred

        event = CostEvent(
            timestamp=datetime.now(),
            provider=provider,
            resource_id=resource_id,
            resource_type=resource_type,
            event_type=event_type,
            cost_incurred=cost_incurred,
            cumulative_cost=self.cumulative_cost,
        )

        self.cost_events.append(event)

        logger.info(
            f"Cost event recorded: {provider.value} {resource_type} "
            f"({event_type}): ${cost_incurred:.2f}, "
            f"Total: ${self.cumulative_cost:.2f}"
        )

    def get_cost_summary(self) -> Dict[str, Any]:
        """Get summary of costs and events.

        Returns:
            Dictionary with cost summary.
        """
        events_by_provider = {}
        for event in self.cost_events:
            provider_name = event.provider.value
            if provider_name not in events_by_provider:
                events_by_provider[provider_name] = []
            events_by_provider[provider_name].append(event)

        provider_totals = {}
        for provider_name, events in events_by_provider.items():
            provider_totals[provider_name] = sum(e.cost_incurred for e in events)

        return {
            "total_cost": self.cumulative_cost,
            "event_count": len(self.cost_events),
            "by_provider": provider_totals,
            "last_event": (self.cost_events[-1].timestamp if self.cost_events else None),
        }

    def get_events_since(self, hours_ago: int) -> List[CostEvent]:
        """Get cost events from the last N hours.

        Args:
            hours_ago: Number of hours to look back.

        Returns:
            List of recent cost events.
        """
        cutoff_time = datetime.now() - timedelta(hours=hours_ago)
        return [e for e in self.cost_events if e.timestamp >= cutoff_time]

    def get_provider_comparison(self) -> Dict[str, Any]:
        """Get detailed provider comparison.

        Returns:
            Dictionary comparing providers by cost.
        """
        hetzner_cost = sum(e.cost_incurred for e in self.cost_events if e.provider == ProviderType.HETZNER)
        runpod_cost = sum(e.cost_incurred for e in self.cost_events if e.provider == ProviderType.RUNPOD)

        return {
            "hetzner": {
                "total_cost": hetzner_cost,
                "event_count": sum(1 for e in self.cost_events if e.provider == ProviderType.HETZNER),
                "average_event_cost": (
                    hetzner_cost / sum(1 for e in self.cost_events if e.provider == ProviderType.HETZNER)
                    if sum(1 for e in self.cost_events if e.provider == ProviderType.HETZNER) > 0
                    else 0.0
                ),
            },
            "runpod": {
                "total_cost": runpod_cost,
                "event_count": sum(1 for e in self.cost_events if e.provider == ProviderType.RUNPOD),
                "average_event_cost": (
                    runpod_cost / sum(1 for e in self.cost_events if e.provider == ProviderType.RUNPOD)
                    if sum(1 for e in self.cost_events if e.provider == ProviderType.RUNPOD) > 0
                    else 0.0
                ),
            },
        }
