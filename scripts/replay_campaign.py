"""
ROAD-E: A-B Validation via Replay Campaigns

Implements before/after comparison on same workload.
Only accept changes that improve metrics or fix failures without regressions.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RunOutcome(str, Enum):
    """Outcome of a replay run."""

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


@dataclass
class ReplayRun:
    """Single replay run result."""

    run_id: str
    task_id: str
    outcome: RunOutcome
    duration_seconds: float
    tokens_used: int
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComparisonMetrics:
    """Metrics comparison between baseline and treatment."""

    avg_duration_baseline: float
    avg_duration_treatment: float
    success_rate_baseline: float
    success_rate_treatment: float
    avg_tokens_baseline: int
    avg_tokens_treatment: int
    regression_detected: bool
    improvement_detected: bool

    def summary(self) -> Dict[str, Any]:
        """Get summary of comparison."""
        return {
            "baseline": {
                "avg_duration": self.avg_duration_baseline,
                "success_rate": self.success_rate_baseline,
                "avg_tokens": self.avg_tokens_baseline,
            },
            "treatment": {
                "avg_duration": self.avg_duration_treatment,
                "success_rate": self.success_rate_treatment,
                "avg_tokens": self.avg_tokens_treatment,
            },
            "regression_detected": self.regression_detected,
            "improvement_detected": self.improvement_detected,
        }


class ABComparison:
    """Compare baseline and treatment runs."""

    def __init__(
        self,
        baseline_runs: List[ReplayRun],
        treatment_runs: List[ReplayRun],
        regression_threshold: float = 0.1,
        improvement_threshold: float = 0.05,
    ):
        """Initialize A-B comparison."""
        self.baseline_runs = baseline_runs
        self.treatment_runs = treatment_runs
        self.regression_threshold = regression_threshold
        self.improvement_threshold = improvement_threshold

    def _avg_tokens(self, runs: List[ReplayRun]) -> int:
        """Calculate average tokens used."""
        if not runs:
            return 0
        total = sum(r.tokens_used for r in runs)
        return total // len(runs)

    def _success_rate(self, runs: List[ReplayRun]) -> float:
        """Calculate success rate."""
        if not runs:
            return 0.0
        successes = sum(1 for r in runs if r.outcome == RunOutcome.SUCCESS)
        return successes / len(runs)

    def _avg_duration(self, runs: List[ReplayRun]) -> float:
        """Calculate average duration."""
        if not runs:
            return 0.0
        total = sum(r.duration_seconds for r in runs)
        return total / len(runs)

    def compare_metrics(self) -> ComparisonMetrics:
        """Compare key metrics between baseline and treatment."""
        baseline_success_rate = self._success_rate(self.baseline_runs)
        treatment_success_rate = self._success_rate(self.treatment_runs)

        failure_rate_increase = baseline_success_rate - treatment_success_rate
        regression_detected = failure_rate_increase > self.regression_threshold

        improvement_detected = (
            treatment_success_rate - baseline_success_rate > self.improvement_threshold
        )

        metrics = ComparisonMetrics(
            avg_duration_baseline=self._avg_duration(self.baseline_runs),
            avg_duration_treatment=self._avg_duration(self.treatment_runs),
            success_rate_baseline=baseline_success_rate,
            success_rate_treatment=treatment_success_rate,
            avg_tokens_baseline=self._avg_tokens(self.baseline_runs),
            avg_tokens_treatment=self._avg_tokens(self.treatment_runs),
            regression_detected=regression_detected,
            improvement_detected=improvement_detected,
        )

        return metrics


class ReplayCampaign:
    """Manages A-B replay campaigns."""

    def __init__(self, campaign_id: str):
        """Initialize campaign."""
        self.campaign_id = campaign_id
        self.baseline_runs: List[ReplayRun] = []
        self.treatment_runs: List[ReplayRun] = []

    def add_baseline_run(self, run: ReplayRun) -> None:
        """Add baseline run to campaign."""
        self.baseline_runs.append(run)
        logger.info(f"Added baseline run: {run.run_id}")

    def add_treatment_run(self, run: ReplayRun) -> None:
        """Add treatment run to campaign."""
        self.treatment_runs.append(run)
        logger.info(f"Added treatment run: {run.run_id}")

    def get_comparison(self) -> ABComparison:
        """Get A-B comparison."""
        return ABComparison(self.baseline_runs, self.treatment_runs)

    def should_promote(self) -> bool:
        """Determine if treatment should be promoted."""
        comparison = self.get_comparison()
        metrics = comparison.compare_metrics()

        if metrics.regression_detected:
            logger.warning("Regression detected - cannot promote")
            return False

        success = metrics.improvement_detected or (
            metrics.success_rate_treatment >= metrics.success_rate_baseline
        )

        if success:
            logger.info("✅ Treatment can be promoted")
        else:
            logger.warning("⚠️  Treatment has degradation - not promoting")

        return success

    def save_report(self, output_path: Path) -> None:
        """Save campaign report to file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        comparison = self.get_comparison()
        metrics = comparison.compare_metrics()

        report = {
            "campaign_id": self.campaign_id,
            "baseline_runs": len(self.baseline_runs),
            "treatment_runs": len(self.treatment_runs),
            "metrics": metrics.summary(),
            "recommendation": "promote" if self.should_promote() else "reject",
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Report saved to {output_path}")

        md_path = output_path.with_suffix(".md")
        with open(md_path, "w") as f:
            f.write("# A-B Replay Campaign Report\n\n")
            f.write(f"**Campaign ID**: {self.campaign_id}\n\n")
            f.write(f"- Baseline Runs: {len(self.baseline_runs)}\n")
            f.write(f"- Treatment Runs: {len(self.treatment_runs)}\n\n")
            f.write(f"**Decision**: {'✅ PROMOTE' if self.should_promote() else '❌ REJECT'}\n")

        logger.info(f"Markdown summary saved to {md_path}")


if __name__ == "__main__":
    campaign = ReplayCampaign("test-001")
    for i in range(3):
        campaign.add_baseline_run(ReplayRun(f"b-{i}", f"t-{i}", RunOutcome.SUCCESS, 45.0, 12000))
        campaign.add_treatment_run(ReplayRun(f"t-{i}", f"t-{i}", RunOutcome.SUCCESS, 42.0, 11500))
    print("✅ Campaign ready:", campaign.should_promote())
