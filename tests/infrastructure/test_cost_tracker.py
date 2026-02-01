"""Tests for infrastructure cost tracking utilities."""

from autopack.infrastructure.cost_tracker import (
    CostEstimate,
    InfrastructureCostTracker,
    ProviderType,
    WorkloadType,
)


class TestCostEstimation:
    """Test cost estimation for different workload types."""

    def test_estimate_batch_processing_cost(self):
        """Test cost estimation for batch processing workload."""
        tracker = InfrastructureCostTracker()
        estimate = tracker.estimate_cost(WorkloadType.BATCH_PROCESSING)

        assert estimate is not None
        assert isinstance(estimate, CostEstimate)
        assert estimate.workload_type == WorkloadType.BATCH_PROCESSING
        assert estimate.estimated_duration_hours == 2.0  # Default duration
        assert len(estimate.breakdowns) > 0

    def test_estimate_inference_cost(self):
        """Test cost estimation for inference workload."""
        tracker = InfrastructureCostTracker()
        estimate = tracker.estimate_cost(WorkloadType.INFERENCE)

        assert estimate is not None
        assert estimate.workload_type == WorkloadType.INFERENCE
        assert estimate.estimated_duration_hours == 0.5  # Default duration
        assert len(estimate.breakdowns) > 0

    def test_estimate_custom_duration(self):
        """Test cost estimation with custom duration."""
        tracker = InfrastructureCostTracker()
        custom_duration = 5.0
        estimate = tracker.estimate_cost(
            WorkloadType.BATCH_PROCESSING, duration_hours=custom_duration
        )

        assert estimate.estimated_duration_hours == custom_duration

    def test_recommendation_is_cheapest(self):
        """Test that recommendation points to cheapest option."""
        tracker = InfrastructureCostTracker()
        estimate = tracker.estimate_cost(WorkloadType.BATCH_PROCESSING)

        cheapest = estimate.get_cheapest_option()
        assert cheapest is not None
        assert cheapest.provider == estimate.recommended_provider
        assert cheapest.resource_type == estimate.recommended_resource


class TestCostTracking:
    """Test cost event tracking."""

    def test_record_single_event(self):
        """Test recording a single cost event."""
        tracker = InfrastructureCostTracker()

        tracker.record_event(
            provider=ProviderType.HETZNER,
            resource_id="server123",
            resource_type="cx22",
            event_type="create",
            cost_incurred=10.0,
        )

        assert tracker.cumulative_cost == 10.0
        assert len(tracker.cost_events) == 1

    def test_record_multiple_events(self):
        """Test recording multiple cost events."""
        tracker = InfrastructureCostTracker()

        tracker.record_event(
            provider=ProviderType.HETZNER,
            resource_id="server123",
            resource_type="cx22",
            event_type="create",
            cost_incurred=10.0,
        )

        tracker.record_event(
            provider=ProviderType.RUNPOD,
            resource_id="pod456",
            resource_type="A40",
            event_type="create",
            cost_incurred=20.0,
        )

        assert tracker.cumulative_cost == 30.0
        assert len(tracker.cost_events) == 2

    def test_get_cost_summary(self):
        """Test cost summary generation."""
        tracker = InfrastructureCostTracker()

        tracker.record_event(
            provider=ProviderType.HETZNER,
            resource_id="server123",
            resource_type="cx22",
            event_type="create",
            cost_incurred=10.0,
        )

        tracker.record_event(
            provider=ProviderType.RUNPOD,
            resource_id="pod456",
            resource_type="A40",
            event_type="create",
            cost_incurred=20.0,
        )

        summary = tracker.get_cost_summary()

        assert summary["total_cost"] == 30.0
        assert summary["event_count"] == 2
        assert "by_provider" in summary

    def test_get_provider_comparison(self):
        """Test provider cost comparison."""
        tracker = InfrastructureCostTracker()

        tracker.record_event(
            provider=ProviderType.HETZNER,
            resource_id="server123",
            resource_type="cx22",
            event_type="create",
            cost_incurred=10.0,
        )

        tracker.record_event(
            provider=ProviderType.HETZNER,
            resource_id="server124",
            resource_type="cx32",
            event_type="create",
            cost_incurred=15.0,
        )

        tracker.record_event(
            provider=ProviderType.RUNPOD,
            resource_id="pod456",
            resource_type="A40",
            event_type="create",
            cost_incurred=20.0,
        )

        comparison = tracker.get_provider_comparison()

        assert comparison["hetzner"]["total_cost"] == 25.0
        assert comparison["hetzner"]["event_count"] == 2
        assert comparison["runpod"]["total_cost"] == 20.0
        assert comparison["runpod"]["event_count"] == 1

    def test_get_events_since(self):
        """Test retrieving recent events."""
        tracker = InfrastructureCostTracker()

        tracker.record_event(
            provider=ProviderType.HETZNER,
            resource_id="server123",
            resource_type="cx22",
            event_type="create",
            cost_incurred=10.0,
        )

        recent_events = tracker.get_events_since(hours_ago=1)

        assert len(recent_events) == 1
