"""
Test Baseline Tracker for BUILD-127 Phase 1.

Captures test baseline at T0, computes regression deltas, and manages flaky test retries.
Uses pytest-json-report for structured output (no text parsing).

Per BUILD-127 Final Plan design.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional
import json
import subprocess
import logging

logger = logging.getLogger(__name__)


@dataclass
class TestBaseline:
    """Baseline test results for a specific commit."""

    run_id: str
    commit_sha: str
    timestamp: datetime
    total_tests: int
    passing_tests: int
    failing_tests: int
    error_tests: int
    skipped_tests: int
    failing_test_ids: List[str] = field(default_factory=list)
    error_signatures: Dict[str, str] = field(default_factory=dict)  # nodeid → error type + first line

    def to_json(self) -> str:
        """Serialize for caching."""
        data = {
            "run_id": self.run_id,
            "commit_sha": self.commit_sha,
            "timestamp": self.timestamp.isoformat(),
            "total_tests": self.total_tests,
            "passing_tests": self.passing_tests,
            "failing_tests": self.failing_tests,
            "error_tests": self.error_tests,
            "skipped_tests": self.skipped_tests,
            "failing_test_ids": self.failing_test_ids,
            "error_signatures": self.error_signatures
        }
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> 'TestBaseline':
        """Deserialize from cache."""
        data = json.loads(json_str)
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)


@dataclass
class TestDelta:
    """Delta between baseline and current test results."""

    newly_failing: List[str] = field(default_factory=list)
    newly_failing_persistent: List[str] = field(default_factory=list)  # Failed twice (after retry)
    newly_passing: List[str] = field(default_factory=list)
    new_collection_errors: List[str] = field(default_factory=list)
    new_collection_errors_persistent: List[str] = field(default_factory=list)  # Failed twice
    flaky_suspects: List[str] = field(default_factory=list)  # Passed on retry
    regression_severity: str = "none"  # "none", "low", "medium", "high", "critical"

    def calculate_severity(self) -> str:
        """Calculate regression severity based on failures."""
        persistent_failures = len(self.newly_failing_persistent)
        persistent_errors = len(self.new_collection_errors_persistent)
        total_persistent = persistent_failures + persistent_errors

        if total_persistent == 0:
            return "none"
        elif total_persistent >= 10:
            return "critical"
        elif total_persistent >= 5:
            return "high"
        elif total_persistent >= 2:
            return "medium"
        else:
            return "low"


class TestBaselineTracker:
    """
    Tracks test baselines and computes regression deltas.

    Key features:
    - Commit-hash based caching (avoid repeated pytest runs)
    - Structured JSON output (no text parsing)
    - Flaky test detection (retry once, track passes)
    - Pre-existing error tolerance (ignore baseline failures)
    """

    def __init__(self, workspace: Path, run_id: Optional[str] = None):
        """Initialize tracker.

        Args:
            workspace: Repository workspace path
            run_id: Run identifier for scoped artifacts (optional for backward compatibility)
        """
        from .config import settings

        self.workspace = workspace
        self.run_id = run_id

        # Use run-scoped cache directory if run_id provided (P2.1 parallel-run safety)
        # P2.2: Respect configured autonomous_runs_dir
        if run_id:
            self.cache_dir = Path(settings.autonomous_runs_dir) / run_id / "baselines"
        else:
            # Legacy: global cache dir (not safe for parallel runs)
            self.cache_dir = Path(settings.autonomous_runs_dir) / "baselines"

        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def capture_baseline(
        self,
        run_id: str,
        commit_sha: str,
        timeout: int = 120
    ) -> TestBaseline:
        """
        Capture test baseline using structured output.

        Args:
            run_id: Current run ID
            commit_sha: Git commit SHA
            timeout: Pytest timeout in seconds

        Returns:
            TestBaseline with all results
        """
        # Check cache first
        cache_file = self.cache_dir / f"{commit_sha}.json"
        if cache_file.exists():
            logger.info(f"[Baseline] Using cached baseline for commit {commit_sha[:8]}")
            return TestBaseline.from_json(cache_file.read_text(encoding='utf-8'))

        logger.info(f"[Baseline] Capturing baseline for commit {commit_sha[:8]}")

        # Run pytest with JSON reporter
        # Use run-scoped path to prevent collision with parallel runs (P2.1)
        if self.run_id:
            report_file = self.workspace / ".autonomous_runs" / self.run_id / "ci" / "baseline.json"
            report_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            # Legacy: global report file (not safe for parallel runs)
            report_file = self.workspace / ".autonomous_runs" / "baseline.json"

        try:
            subprocess.run(
                [
                    "pytest",
                    "--json-report",
                    f"--json-report-file={report_file}",
                    "--tb=line",
                    "-q",
                    "tests/"
                ],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout
            )
        except subprocess.TimeoutExpired:
            logger.error(f"[Baseline] Pytest timed out after {timeout}s")
            raise

        # Parse structured JSON output
        if not report_file.exists():
            logger.error("[Baseline] JSON report not generated")
            raise FileNotFoundError(f"JSON report missing: {report_file}")

        report = json.loads(report_file.read_text(encoding='utf-8'))

        # Extract baseline data
        summary = report.get("summary", {})
        tests = report.get("tests", [])
        collectors = report.get("collectors", [])

        # Collection/import errors are represented as failed collectors in pytest-json-report
        # even when "tests" is empty (exitcode=2).
        failed_collectors = [
            c for c in collectors
            if c.get("outcome") not in (None, "passed")
        ]

        failing_test_ids = [
            test["nodeid"] for test in tests
            if test.get("outcome") in ["failed", "error"]
        ]

        error_signatures = {}
        for test in tests:
            if test.get("outcome") == "error":
                error_signatures[test["nodeid"]] = self._extract_error_signature(test)

        # Include collection errors (failed collectors) as error signatures keyed by collector nodeid.
        for collector in failed_collectors:
            nodeid = collector.get("nodeid")
            if not nodeid:
                continue
            longrepr = collector.get("longrepr", "") or ""
            first_line = (longrepr.splitlines()[0] if longrepr else "Collection error")[:200]
            error_signatures[nodeid] = f"COLLECT:{first_line}"

        # Prefer pytest summary counts when present; otherwise compute from the test list.
        total_tests = summary.get("total", len(tests) if isinstance(tests, list) else 0)
        passed_tests = summary.get("passed")
        failed_tests = summary.get("failed")
        skipped_tests = summary.get("skipped")
        # pytest-json-report commonly uses "error" (singular) for test errors; keep both for robustness
        error_tests_summary = summary.get("error", summary.get("errors"))

        if passed_tests is None:
            passed_tests = sum(1 for t in tests if t.get("outcome") == "passed")
        if failed_tests is None:
            failed_tests = sum(1 for t in tests if t.get("outcome") == "failed")
        if skipped_tests is None:
            skipped_tests = sum(1 for t in tests if t.get("outcome") == "skipped")
        if error_tests_summary is None:
            error_tests_summary = sum(1 for t in tests if t.get("outcome") == "error")

        # Count failed collectors as errors as well (collection/import errors)
        error_tests_total = int(error_tests_summary) + len(failed_collectors)

        baseline = TestBaseline(
            run_id=run_id,
            commit_sha=commit_sha,
            timestamp=datetime.now(timezone.utc),
            total_tests=int(total_tests),
            passing_tests=int(passed_tests),
            failing_tests=int(failed_tests),
            error_tests=int(error_tests_total),
            skipped_tests=int(skipped_tests),
            failing_test_ids=failing_test_ids,
            error_signatures=error_signatures
        )

        # Cache for this commit
        cache_file.write_text(baseline.to_json(), encoding='utf-8')
        logger.info(
            f"[Baseline] Captured: {baseline.passing_tests}/{baseline.total_tests} passing, "
            f"{baseline.failing_tests} failing, {baseline.error_tests} errors"
        )

        return baseline

    def diff(
        self,
        baseline: TestBaseline,
        current_report_path: Path
    ) -> TestDelta:
        """
        Compute regression delta between baseline and current.

        Args:
            baseline: Baseline test results
            current_report_path: Path to current pytest-json-report output

        Returns:
            TestDelta with all changes
        """
        # Parse current results
        current_report = json.loads(current_report_path.read_text(encoding='utf-8'))
        current_tests = current_report.get("tests", [])
        current_collectors = current_report.get("collectors", [])

        current_failed_or_error = set(
            test["nodeid"] for test in current_tests
            if test.get("outcome") in ("failed", "error")
        )

        # pytest-json-report represents collection/import errors as failed collectors.
        current_collection_errors = set(
            c.get("nodeid") for c in current_collectors
            if c.get("nodeid") and c.get("outcome") not in (None, "passed")
        )

        current_passing = set(
            test["nodeid"] for test in current_tests
            if test.get("outcome") == "passed"
        )

        baseline_failing = set(baseline.failing_test_ids)
        baseline_errors = set(baseline.error_signatures.keys())

        # Compute deltas
        # P0.1: Sort for deterministic output (prevents replay variability)
        newly_failing = sorted(list(current_failed_or_error - baseline_failing))
        newly_passing = sorted(list(current_passing & baseline_failing))  # Was failing, now passing
        new_collection_errors = sorted(list(current_collection_errors - baseline_errors))

        delta = TestDelta(
            newly_failing=newly_failing,
            newly_passing=newly_passing,
            new_collection_errors=new_collection_errors
        )

        return delta

    def retry_newly_failing(
        self,
        newly_failing: List[str],
        workspace: Path,
        timeout: int = 60
    ) -> Dict[str, str]:
        """
        Retry tests once. Returns {nodeid: 'passed'|'failed'}.

        Args:
            newly_failing: List of test node IDs
            workspace: Workspace path
            timeout: Retry timeout

        Returns:
            Dict mapping test ID to retry outcome
        """
        if not newly_failing:
            return {}

        logger.info(f"[Baseline] Retrying {len(newly_failing)} newly failing tests")

        # Use run-scoped path to prevent collision with parallel runs (P2.1)
        if self.run_id:
            report_file = workspace / ".autonomous_runs" / self.run_id / "ci" / "retry.json"
            report_file.parent.mkdir(parents=True, exist_ok=True)
        else:
            # Legacy: global report file (not safe for parallel runs)
            report_file = workspace / ".autonomous_runs" / "retry.json"

        try:
            subprocess.run(
                [
                    "pytest",
                    *newly_failing,
                    "--json-report",
                    f"--json-report-file={report_file}",
                    "--tb=line",
                    "-q"
                ],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=timeout
            )
        except subprocess.TimeoutExpired:
            logger.error(f"[Baseline] Retry timed out after {timeout}s")
            # Treat timeout as persistent failure
            return {nodeid: "failed" for nodeid in newly_failing}

        # Parse retry results
        if not report_file.exists():
            logger.error("[Baseline] Retry JSON report missing")
            return {nodeid: "failed" for nodeid in newly_failing}

        retry_report = json.loads(report_file.read_text(encoding='utf-8'))
        retry_tests = retry_report.get("tests", [])

        outcomes = {}
        for test in retry_tests:
            nodeid = test.get("nodeid")
            outcome = test.get("outcome")
            if outcome == "passed":
                outcomes[nodeid] = "passed"
            else:
                outcomes[nodeid] = "failed"

        # Any tests not in report are assumed failed
        for nodeid in newly_failing:
            if nodeid not in outcomes:
                outcomes[nodeid] = "failed"

        passed_count = sum(1 for v in outcomes.values() if v == "passed")
        logger.info(f"[Baseline] Retry results: {passed_count}/{len(newly_failing)} passed")

        return outcomes

    def compute_full_delta(
        self,
        baseline: TestBaseline,
        current_report_path: Path,
        workspace: Path
    ) -> TestDelta:
        """
        Compute full delta with flaky test retry.

        Per BUILD-127: Retry newly failing tests once, track flaky suspects.

        Args:
            baseline: Test baseline
            current_report_path: Current pytest JSON report
            workspace: Workspace path

        Returns:
            TestDelta with persistent failures and flaky suspects
        """
        # Initial delta
        delta = self.diff(baseline, current_report_path)

        # Retry newly failing tests
        if delta.newly_failing:
            retry_outcomes = self.retry_newly_failing(
                delta.newly_failing,
                workspace
            )

            # Classify based on retry
            for nodeid in delta.newly_failing:
                outcome = retry_outcomes.get(nodeid, "failed")
                if outcome == "passed":
                    # Flaky suspect (failed first, passed on retry)
                    delta.flaky_suspects.append(nodeid)
                else:
                    # Persistent failure (failed twice)
                    delta.newly_failing_persistent.append(nodeid)

        # Retry new collection errors
        if delta.new_collection_errors:
            retry_outcomes = self.retry_newly_failing(
                delta.new_collection_errors,
                workspace
            )

            for nodeid in delta.new_collection_errors:
                outcome = retry_outcomes.get(nodeid, "failed")
                if outcome != "passed":
                    # Persistent error (failed twice)
                    delta.new_collection_errors_persistent.append(nodeid)

        # Calculate severity
        delta.regression_severity = delta.calculate_severity()

        return delta

    def _extract_error_signature(self, test: Dict) -> str:
        """
        Extract error signature from test result.

        Signature = error type + first line of error message
        """
        call = test.get("call", {})
        longrepr = call.get("longrepr", "")

        # Extract first line
        lines = longrepr.split("\n")
        first_line = lines[0] if lines else "Unknown error"

        # Limit length
        return first_line[:200]
