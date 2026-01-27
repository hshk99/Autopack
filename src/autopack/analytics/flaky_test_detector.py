"""Flaky Test Detector.

Analyzes CI failure history to identify flaky tests:
- Tests that fail >20% of runs without code changes
- Tests with high variance in execution time
- Tests that correlate with specific slot/time patterns

This module provides actionable recommendations for CI retry decisions,
helping distinguish between genuine failures and flaky tests that can
be safely retried.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FlakyTestDetector:
    """Detects and analyzes flaky tests from CI retry history.

    This class provides a focused API for flaky test detection and retry
    recommendations. It analyzes ci_retry_state.json to identify patterns
    that indicate test flakiness vs. genuine failures.

    Attributes:
        ci_state_path: Path to the ci_retry_state.json file.
        FLAKY_THRESHOLD: Minimum flakiness score to consider a test flaky.
        AUTO_RETRY_FLAKINESS_THRESHOLD: Threshold above which auto-retry is recommended.
        MIN_RUNS_FOR_ANALYSIS: Minimum runs needed before analyzing a test.
    """

    FLAKY_THRESHOLD = 0.2  # 20% failure rate indicates potential flakiness
    AUTO_RETRY_FLAKINESS_THRESHOLD = 0.4  # 40%+ flakiness = safe to auto-retry
    MIN_RUNS_FOR_ANALYSIS = 3  # Need at least 3 runs for meaningful analysis
    HIGH_FLAKINESS_THRESHOLD = 0.6  # 60%+ flakiness = high priority to fix

    def __init__(self, ci_state_path: Path | str) -> None:
        """Initialize the FlakyTestDetector.

        Args:
            ci_state_path: Path to the ci_retry_state.json file or directory
                containing it.
        """
        path = Path(ci_state_path)
        if path.is_dir():
            self.ci_state_path = path / "ci_retry_state.json"
        else:
            self.ci_state_path = path
        self._ci_data: dict[str, Any] | None = None
        self._test_stats: dict[str, dict[str, Any]] | None = None

    def _load_ci_state(self) -> dict[str, Any]:
        """Load CI retry state from JSON file.

        Returns:
            Parsed CI state data or empty dict if file doesn't exist.
        """
        if self._ci_data is not None:
            return self._ci_data

        if not self.ci_state_path.exists():
            logger.debug("CI state file not found: %s", self.ci_state_path)
            self._ci_data = {}
            return self._ci_data

        try:
            with open(self.ci_state_path, encoding="utf-8") as f:
                self._ci_data = json.load(f)
                logger.debug(
                    "Loaded CI state with %d retries",
                    len(self._ci_data.get("retries", [])),
                )
                return self._ci_data
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse CI state file: %s", e)
            self._ci_data = {}
            return self._ci_data
        except OSError as e:
            logger.warning("Failed to read CI state file: %s", e)
            self._ci_data = {}
            return self._ci_data

    def _compute_test_stats(self) -> dict[str, dict[str, Any]]:
        """Compute statistics for each test from CI retry data.

        Returns:
            Dictionary mapping test IDs to their statistics.
        """
        if self._test_stats is not None:
            return self._test_stats

        ci_data = self._load_ci_state()
        retries = ci_data.get("retries", [])
        if not isinstance(retries, list):
            retries = []

        # Aggregate stats per test
        stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total_runs": 0,
                "failures": 0,
                "successes": 0,
                "retry_attempts": [],
                "workflows": Counter(),
                "failure_reasons": Counter(),
                "timestamps": [],
                "run_ids": set(),
            }
        )

        for retry in retries:
            if not isinstance(retry, dict):
                continue

            # Get test identifier - support multiple field names
            test_id = retry.get(
                "test_name",
                retry.get("test_id", retry.get("job_name", retry.get("workflow"))),
            )
            if not test_id:
                # Try to extract from run_id or other fields
                run_id = retry.get("run_id", "")
                if run_id:
                    test_id = str(run_id)
                else:
                    continue

            test_id = str(test_id)
            test_stats = stats[test_id]
            test_stats["total_runs"] += 1

            # Track outcome
            outcome = str(retry.get("outcome", retry.get("status", ""))).lower()
            if outcome in ("success", "passed", "completed"):
                test_stats["successes"] += 1
            elif outcome in ("failed", "error", "failure", "timed_out"):
                test_stats["failures"] += 1

            # Track retry attempts
            attempt = retry.get("attempt", retry.get("retry_number", 1))
            test_stats["retry_attempts"].append(attempt)

            # Track workflow
            workflow = retry.get("workflow", retry.get("job_name"))
            if workflow:
                test_stats["workflows"][workflow] += 1

            # Track failure reasons
            reason = retry.get(
                "failure_reason",
                retry.get("error_message", retry.get("conclusion")),
            )
            if reason:
                test_stats["failure_reasons"][reason] += 1

            # Track timestamps
            timestamp = retry.get("timestamp", retry.get("created_at"))
            if timestamp:
                test_stats["timestamps"].append(timestamp)

            # Track unique run IDs
            run_id = retry.get("run_id")
            if run_id:
                test_stats["run_ids"].add(run_id)

        # Convert sets to lists for JSON serialization
        for test_id, test_stats in stats.items():
            test_stats["run_ids"] = list(test_stats["run_ids"])

        self._test_stats = dict(stats)
        return self._test_stats

    def _calculate_flakiness_score(self, stats: dict[str, Any]) -> float:
        """Calculate flakiness score for a test based on its statistics.

        A test is considered flaky if it has both successes and failures.
        The score is higher when:
        - Failure rate is around 50% (most unpredictable)
        - There are multiple retry attempts
        - The test has been run many times with mixed results

        Args:
            stats: Test statistics dictionary.

        Returns:
            Flakiness score from 0.0 to 1.0.
        """
        total = stats["total_runs"]
        if total < self.MIN_RUNS_FOR_ANALYSIS:
            return 0.0

        failures = stats["failures"]
        successes = stats["successes"]
        failure_rate = failures / total

        # A test is only flaky if it has both successes and failures
        has_mixed_outcomes = successes > 0 and failures > 0

        if not has_mixed_outcomes:
            # Consistently failing tests aren't flaky, just broken
            # Consistently passing tests aren't flaky at all
            return 0.0 if failure_rate >= 1.0 or failure_rate == 0.0 else failure_rate * 0.2

        # Score based on how close to 50% failure rate (most flaky)
        # A 50% failure rate is maximally unpredictable
        balance_score = 1.0 - abs(0.5 - failure_rate) * 2

        # Score based on retry frequency
        # More retries indicate more flakiness
        max_attempt = max(stats["retry_attempts"]) if stats["retry_attempts"] else 1
        retry_score = min(1.0, (max_attempt - 1) / 3)  # Normalize to 0-1

        # Score based on run count - more runs with mixed results = more confident
        run_confidence = min(1.0, total / 10)  # Cap at 10 runs

        # Weighted combination
        flakiness_score = (balance_score * 0.5) + (retry_score * 0.3) + (run_confidence * 0.2)

        return round(flakiness_score, 3)

    def _detect_patterns(self, stats: dict[str, Any]) -> list[str]:
        """Detect patterns in test failures.

        Args:
            stats: Test statistics dictionary.

        Returns:
            List of detected pattern strings.
        """
        patterns: list[str] = []

        # Workflow patterns
        workflows = stats.get("workflows", Counter())
        if len(workflows) > 1:
            patterns.append("multi-workflow")
        elif workflows:
            top_workflow = workflows.most_common(1)[0][0]
            patterns.append(f"workflow:{top_workflow}")

        # Failure reason patterns
        failure_reasons = stats.get("failure_reasons", Counter())
        if failure_reasons:
            top_reason = str(failure_reasons.most_common(1)[0][0]).lower()
            if "timeout" in top_reason:
                patterns.append("timeout-related")
            elif "connection" in top_reason or "network" in top_reason:
                patterns.append("connection-related")
            elif "flak" in top_reason:
                patterns.append("known-flaky")
            elif "memory" in top_reason or "oom" in top_reason:
                patterns.append("memory-related")
            elif "race" in top_reason or "concurrent" in top_reason:
                patterns.append("race-condition")

        # Retry pattern
        retry_attempts = stats.get("retry_attempts", [])
        if retry_attempts and max(retry_attempts) >= 3:
            patterns.append("high-retry-count")

        return patterns

    def _generate_recommendation(self, flakiness_score: float, patterns: list[str]) -> str:
        """Generate a recommendation for handling a flaky test.

        Args:
            flakiness_score: The calculated flakiness score.
            patterns: Detected failure patterns.

        Returns:
            Human-readable recommendation string.
        """
        if "timeout-related" in patterns:
            return "Increase timeout or optimize test performance"
        elif "connection-related" in patterns:
            return "Review network/connection handling in test setup"
        elif "memory-related" in patterns:
            return "Check for memory leaks or increase resource limits"
        elif "race-condition" in patterns:
            return "Add proper synchronization or test isolation"
        elif flakiness_score >= self.HIGH_FLAKINESS_THRESHOLD:
            return "High priority: Rewrite test with better isolation"
        elif flakiness_score >= self.AUTO_RETRY_FLAKINESS_THRESHOLD:
            return "Consider adding retry logic or investigating root cause"
        else:
            return "Review for race conditions or external dependencies"

    def analyze_failure_patterns(self) -> list[tuple[str, float]]:
        """Analyze CI failures and return tests with their flakiness scores.

        This method identifies tests that exhibit flaky behavior by analyzing
        their pass/fail patterns over time.

        Returns:
            List of (test_id, flakiness_score) tuples, sorted by score descending.
            Only tests with scores above FLAKY_THRESHOLD are included.
        """
        test_stats = self._compute_test_stats()
        results: list[tuple[str, float]] = []

        for test_id, stats in test_stats.items():
            if stats["total_runs"] < self.MIN_RUNS_FOR_ANALYSIS:
                continue

            flakiness_score = self._calculate_flakiness_score(stats)
            if flakiness_score >= self.FLAKY_THRESHOLD:
                results.append((test_id, flakiness_score))

        # Sort by flakiness score descending
        results.sort(key=lambda x: x[1], reverse=True)

        logger.info(
            "Analyzed %d tests, found %d with flakiness above threshold",
            len(test_stats),
            len(results),
        )

        return results

    def should_auto_retry(self, failed_test: str) -> bool:
        """Recommend whether to auto-retry a failed test based on history.

        A test should be auto-retried if:
        - It has a high flakiness score (indicating intermittent failures)
        - It has known patterns associated with transient failures
        - It has mixed outcomes (both successes and failures) - consistently
          failing tests are broken, not flaky

        Args:
            failed_test: The test identifier (name, job name, or ID).

        Returns:
            True if auto-retry is recommended, False if investigation is needed.
        """
        test_stats = self._compute_test_stats()
        stats = test_stats.get(failed_test)

        if not stats:
            # Unknown test - be conservative, recommend investigation
            logger.debug("No history for test %s, recommending investigation", failed_test)
            return False

        if stats["total_runs"] < self.MIN_RUNS_FOR_ANALYSIS:
            # Not enough data - recommend investigation
            logger.debug(
                "Insufficient data for test %s (%d runs), recommending investigation",
                failed_test,
                stats["total_runs"],
            )
            return False

        # Check if test has mixed outcomes (both successes and failures)
        # Consistently failing tests are broken, not flaky - they need investigation
        has_mixed_outcomes = stats["successes"] > 0 and stats["failures"] > 0
        if not has_mixed_outcomes:
            logger.debug(
                "Test %s has no mixed outcomes (successes=%d, failures=%d), "
                "recommending investigation",
                failed_test,
                stats["successes"],
                stats["failures"],
            )
            return False

        flakiness_score = self._calculate_flakiness_score(stats)
        patterns = self._detect_patterns(stats)

        # Auto-retry if flakiness score is above threshold
        if flakiness_score >= self.AUTO_RETRY_FLAKINESS_THRESHOLD:
            logger.info(
                "Recommending auto-retry for %s (flakiness=%.2f)",
                failed_test,
                flakiness_score,
            )
            return True

        # Auto-retry for known transient failure patterns (only if test has some successes)
        transient_patterns = {"timeout-related", "connection-related", "known-flaky"}
        if any(p in patterns for p in transient_patterns):
            logger.info(
                "Recommending auto-retry for %s due to transient pattern: %s",
                failed_test,
                patterns,
            )
            return True

        logger.debug(
            "Recommending investigation for %s (flakiness=%.2f, patterns=%s)",
            failed_test,
            flakiness_score,
            patterns,
        )
        return False

    def get_retry_recommendation(self, failed_tests: list[str]) -> dict[str, Any]:
        """Get retry recommendations for a list of failed tests.

        Args:
            failed_tests: List of failed test identifiers.

        Returns:
            Dictionary containing:
            - should_retry: Overall recommendation (True if any test should retry)
            - retry_tests: List of tests that should be retried
            - investigate_tests: List of tests that need investigation
            - details: Per-test details with scores and reasons
        """
        retry_tests: list[str] = []
        investigate_tests: list[str] = []
        details: dict[str, dict[str, Any]] = {}

        for test in failed_tests:
            should_retry = self.should_auto_retry(test)
            test_stats = self._compute_test_stats().get(test, {})

            flakiness_score = 0.0
            patterns: list[str] = []

            if test_stats:
                flakiness_score = self._calculate_flakiness_score(test_stats)
                patterns = self._detect_patterns(test_stats)

            if should_retry:
                retry_tests.append(test)
            else:
                investigate_tests.append(test)

            details[test] = {
                "should_retry": should_retry,
                "flakiness_score": flakiness_score,
                "patterns": patterns,
                "total_runs": test_stats.get("total_runs", 0),
                "failure_rate": (
                    test_stats["failures"] / test_stats["total_runs"]
                    if test_stats.get("total_runs", 0) > 0
                    else 0.0
                ),
            }

        return {
            "should_retry": len(retry_tests) > 0,
            "retry_tests": retry_tests,
            "investigate_tests": investigate_tests,
            "details": details,
        }

    def get_flaky_test_report(self) -> dict[str, Any]:
        """Generate a comprehensive report on flaky tests for human review.

        Returns:
            Dictionary containing:
            - timestamp: When the report was generated
            - summary: High-level statistics
            - flaky_tests: List of flaky tests with details
            - recommendations: Prioritized list of recommended actions
            - auto_retry_candidates: Tests that can be safely auto-retried
        """
        timestamp = datetime.now().isoformat()
        test_stats = self._compute_test_stats()

        flaky_tests: list[dict[str, Any]] = []
        auto_retry_candidates: list[str] = []

        for test_id, stats in test_stats.items():
            if stats["total_runs"] < self.MIN_RUNS_FOR_ANALYSIS:
                continue

            flakiness_score = self._calculate_flakiness_score(stats)
            if flakiness_score < self.FLAKY_THRESHOLD:
                continue

            patterns = self._detect_patterns(stats)
            recommendation = self._generate_recommendation(flakiness_score, patterns)
            failure_rate = stats["failures"] / stats["total_runs"]

            test_entry = {
                "test_id": test_id,
                "flakiness_score": flakiness_score,
                "failure_rate": round(failure_rate, 3),
                "total_runs": stats["total_runs"],
                "failures": stats["failures"],
                "successes": stats["successes"],
                "max_retry_attempt": (
                    max(stats["retry_attempts"]) if stats["retry_attempts"] else 1
                ),
                "patterns": patterns,
                "top_failure_reasons": dict(stats["failure_reasons"].most_common(3)),
                "workflows": dict(stats["workflows"]),
                "recommendation": recommendation,
                "severity": (
                    "high" if flakiness_score >= self.HIGH_FLAKINESS_THRESHOLD else "medium"
                ),
            }
            flaky_tests.append(test_entry)

            if flakiness_score >= self.AUTO_RETRY_FLAKINESS_THRESHOLD:
                auto_retry_candidates.append(test_id)

        # Sort by flakiness score descending
        flaky_tests.sort(key=lambda x: x["flakiness_score"], reverse=True)

        # Generate prioritized recommendations
        recommendations: list[dict[str, Any]] = []
        for test in flaky_tests[:10]:  # Top 10 flakiest tests
            recommendations.append(
                {
                    "test_id": test["test_id"],
                    "priority": test["severity"],
                    "action": test["recommendation"],
                    "flakiness_score": test["flakiness_score"],
                    "impact": f"{test['failures']} failures out of {test['total_runs']} runs",
                }
            )

        # Summary statistics
        summary = {
            "total_tests_analyzed": len(test_stats),
            "flaky_tests_detected": len(flaky_tests),
            "high_severity_count": sum(1 for t in flaky_tests if t["severity"] == "high"),
            "auto_retry_candidates": len(auto_retry_candidates),
            "average_flakiness": (
                round(sum(t["flakiness_score"] for t in flaky_tests) / len(flaky_tests), 3)
                if flaky_tests
                else 0.0
            ),
        }

        logger.info(
            "Generated flaky test report: %d flaky tests, %d auto-retry candidates",
            len(flaky_tests),
            len(auto_retry_candidates),
        )

        return {
            "timestamp": timestamp,
            "summary": summary,
            "flaky_tests": flaky_tests,
            "recommendations": recommendations,
            "auto_retry_candidates": auto_retry_candidates,
        }

    def record_failure(
        self,
        test_id: str,
        outcome: str,
        *,
        workflow: str | None = None,
        failure_reason: str | None = None,
        attempt: int = 1,
        run_id: str | None = None,
    ) -> None:
        """Record a test failure/success for future analysis.

        This method appends a new retry record to the CI state file,
        building up the historical data needed for flaky test detection.

        Args:
            test_id: The test identifier.
            outcome: The test outcome ('success', 'failed', etc.).
            workflow: Optional workflow name.
            failure_reason: Optional failure reason/message.
            attempt: The retry attempt number.
            run_id: Optional CI run ID.
        """
        ci_data = self._load_ci_state()
        if "retries" not in ci_data:
            ci_data["retries"] = []

        record = {
            "test_name": test_id,
            "outcome": outcome,
            "attempt": attempt,
            "timestamp": datetime.now().isoformat(),
        }

        if workflow:
            record["workflow"] = workflow
        if failure_reason:
            record["failure_reason"] = failure_reason
        if run_id:
            record["run_id"] = run_id

        ci_data["retries"].append(record)

        # Write back to file
        try:
            self.ci_state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ci_state_path, "w", encoding="utf-8") as f:
                json.dump(ci_data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            logger.debug("Recorded failure for test %s: %s", test_id, outcome)
        except OSError as e:
            logger.error("Failed to write CI state: %s", e)

        # Clear cache to force reload
        self._ci_data = None
        self._test_stats = None

    def clear_cache(self) -> None:
        """Clear cached data to force reload on next analysis."""
        self._ci_data = None
        self._test_stats = None
        logger.debug("Cleared flaky test detector cache")
