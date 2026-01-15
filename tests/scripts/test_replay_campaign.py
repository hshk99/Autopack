"""Tests for ROAD-E: A-B Replay Validation"""

import pytest
from scripts.replay_campaign import (
    ReplayCampaign,
    ReplayRun,
    RunOutcome,
    ABComparison,
)


class TestReplayCampaign:
    """Test A-B replay campaigns."""

    def test_create_campaign(self):
        """Test campaign creation."""
        campaign = ReplayCampaign("test-001")
        assert campaign.campaign_id == "test-001"
        assert len(campaign.baseline_runs) == 0
        assert len(campaign.treatment_runs) == 0

    def test_add_runs(self):
        """Test adding runs to campaign."""
        campaign = ReplayCampaign("test-002")

        baseline = ReplayRun("b-001", "task-1", RunOutcome.SUCCESS, 45.0, 12000)
        campaign.add_baseline_run(baseline)

        treatment = ReplayRun("t-001", "task-1", RunOutcome.SUCCESS, 42.0, 11500)
        campaign.add_treatment_run(treatment)

        assert len(campaign.baseline_runs) == 1
        assert len(campaign.treatment_runs) == 1

    def test_promotion_without_regression(self):
        """Test promotion when there's no regression."""
        campaign = ReplayCampaign("test-003")

        for i in range(5):
            campaign.add_baseline_run(
                ReplayRun(f"b-{i}", f"t-{i}", RunOutcome.SUCCESS, 45.0, 12000)
            )
            campaign.add_treatment_run(
                ReplayRun(f"t-{i}", f"t-{i}", RunOutcome.SUCCESS, 42.0, 11500)
            )

        assert campaign.should_promote() is True

    def test_rejection_with_regression(self):
        """Test rejection when regression is detected."""
        campaign = ReplayCampaign("test-004")

        # Baseline: all success
        for i in range(5):
            campaign.add_baseline_run(
                ReplayRun(f"b-{i}", f"t-{i}", RunOutcome.SUCCESS, 45.0, 12000)
            )

        # Treatment: 4 successes, 1 failure (20% failure rate, exceeds 10% threshold)
        for i in range(4):
            campaign.add_treatment_run(
                ReplayRun(f"t-{i}", f"t-{i}", RunOutcome.SUCCESS, 42.0, 11500)
            )
        campaign.add_treatment_run(ReplayRun("t-fail", "t-fail", RunOutcome.FAILED, 60.0, 15000))

        assert campaign.should_promote() is False

    def test_metrics_comparison(self):
        """Test metrics comparison calculation."""
        baseline_runs = [
            ReplayRun(f"b-{i}", f"t-{i}", RunOutcome.SUCCESS, 45.0, 12000) for i in range(5)
        ]
        treatment_runs = [
            ReplayRun(f"t-{i}", f"t-{i}", RunOutcome.SUCCESS, 42.0, 11500) for i in range(5)
        ]

        comparison = ABComparison(baseline_runs, treatment_runs)
        metrics = comparison.compare_metrics()

        assert metrics.success_rate_baseline == 1.0
        assert metrics.success_rate_treatment == 1.0
        assert metrics.regression_detected is False
        assert metrics.avg_duration_treatment < metrics.avg_duration_baseline


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
