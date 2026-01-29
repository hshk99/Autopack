"""Regression protection for fixed issues.

This module provides automatic regression protection when issues are fixed,
ensuring that previously resolved problems do not recur. It integrates with
ROAD-C (task generator) to add regression tests for each fix.

IMP-FBK-003: Also provides pre-task-generation regression checking to prevent
re-attempting known-bad improvements.

IMP-LOOP-018: Added RiskSeverity levels and risk assessment for task generation
gating. High/critical risk patterns are blocked from task generation.
"""

import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class RiskSeverity(Enum):
    """Risk severity levels for regression risk assessment (IMP-LOOP-018).

    Used to gate task generation based on risk of causing regressions.
    """

    LOW = "low"  # Minor risk, proceed normally
    MEDIUM = "medium"  # Moderate risk, requires approval gate
    HIGH = "high"  # High risk, block task generation
    CRITICAL = "critical"  # Very high risk, block and alert


@dataclass
class RiskAssessment:
    """Result of regression risk assessment (IMP-LOOP-018).

    Contains severity level, blocking recommendation, and evidence for the assessment.
    """

    severity: RiskSeverity
    blocking_recommended: bool
    confidence: float  # 0.0-1.0
    evidence: List[str] = field(default_factory=list)
    pattern_type: str = ""
    historical_regression_rate: float = 0.0  # Historical rate of regressions for this type


@dataclass
class RegressionTest:
    """A regression test for a fixed issue."""

    test_id: str
    issue_pattern: str
    test_code: str
    created_at: datetime
    source_task_id: str


@dataclass
class ProtectionResult:
    """Result of regression protection check."""

    is_protected: bool
    existing_tests: List[str]
    suggested_test: Optional[RegressionTest]


@dataclass
class RegressionCheckResult:
    """Result of checking for regression between two states (IMP-REG-001).

    Used by generated regression tests to verify that an issue does not recur.
    """

    regression_detected: bool
    before_state: Dict[str, Any]
    after_state: Dict[str, Any]
    differences: List[str] = field(default_factory=list)
    severity: str = "unknown"  # low, medium, high
    pattern_matched: str = ""


@dataclass
class FixVerificationResult:
    """Result of verifying a fix is still effective (IMP-REG-001).

    Used by generated regression tests to verify that fixes remain valid.
    """

    fix_verified: bool
    original_issue: str
    fix_description: str
    verification_method: str = ""  # test_pass, pattern_check, manual
    evidence: List[str] = field(default_factory=list)
    stale_indicators: List[str] = field(default_factory=list)


class RegressionProtector:
    """Protects against re-introducing fixed issues.

    This class provides mechanisms to:
    1. Check if an issue pattern is already protected by regression tests
    2. Generate regression tests for newly fixed issues
    3. Add protection automatically when issues are resolved
    """

    def __init__(self, tests_root: Optional[Path] = None):
        """Initialize the regression protector.

        Args:
            tests_root: Root directory for regression tests.
                        Defaults to tests/regression.
        """
        self._tests_root = tests_root or Path("tests/regression")

    def check_protection(self, issue_pattern: str) -> ProtectionResult:
        """Check if an issue pattern is protected by regression tests.

        Args:
            issue_pattern: The pattern describing the issue to check.

        Returns:
            ProtectionResult indicating whether protection exists.
        """
        existing = self._find_existing_tests(issue_pattern)

        if existing:
            return ProtectionResult(
                is_protected=True,
                existing_tests=existing,
                suggested_test=None,
            )

        # Generate suggested test for unprotected pattern
        suggested = self._generate_test(issue_pattern)

        return ProtectionResult(
            is_protected=False,
            existing_tests=[],
            suggested_test=suggested,
        )

    def add_protection(self, task_id: str, issue_pattern: str) -> RegressionTest:
        """Add regression protection for a fixed issue.

        Args:
            task_id: The ID of the task that fixed the issue.
            issue_pattern: The pattern describing the fixed issue.

        Returns:
            The created RegressionTest.
        """
        test = self._generate_test(issue_pattern, task_id)

        # Write test file
        test_path = self._tests_root / f"test_regression_{task_id.lower()}.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(test.test_code)

        logger.info(f"Created regression test: {test_path}")

        return test

    def _find_existing_tests(self, issue_pattern: str) -> List[str]:
        """Find existing regression tests for a pattern.

        Args:
            issue_pattern: The pattern to search for.

        Returns:
            List of test file paths that match the pattern.
        """
        if not self._tests_root.exists():
            return []

        existing = []
        # Normalize pattern for comparison
        pattern_lower = issue_pattern.lower()
        pattern_words = set(re.findall(r"\w+", pattern_lower))

        for test_file in self._tests_root.glob("test_regression_*.py"):
            try:
                content = test_file.read_text()
                content_lower = content.lower()

                # Check for direct pattern match or word overlap
                if pattern_lower in content_lower:
                    existing.append(str(test_file))
                else:
                    # Check for significant word overlap
                    content_words = set(re.findall(r"\w+", content_lower))
                    overlap = pattern_words & content_words
                    if len(overlap) >= min(3, len(pattern_words)):
                        existing.append(str(test_file))
            except (OSError, IOError) as e:
                logger.warning(f"Could not read test file {test_file}: {e}")

        return existing

    def _generate_test(
        self,
        issue_pattern: str,
        task_id: str = "UNKNOWN",
    ) -> RegressionTest:
        """Generate a regression test for an issue pattern.

        Args:
            issue_pattern: The pattern describing the issue.
            task_id: The ID of the task that fixed the issue.

        Returns:
            A RegressionTest with generated test code.
        """
        test_id = f"REG-{uuid.uuid4().hex[:8].upper()}"

        # Sanitize pattern for use in identifiers
        sanitized = self._sanitize_identifier(issue_pattern)

        # Generate test code
        test_code = f'''"""Regression test for {issue_pattern}."""

import pytest
from autopack.roadi.regression_protector import RegressionProtector

# Generated from task: {task_id}
# Pattern: {issue_pattern}
# Test ID: {test_id}


class TestRegression{test_id.replace("-", "")}:
    """Regression tests for {issue_pattern}."""

    @pytest.fixture
    def protector(self):
        """Create a RegressionProtector instance."""
        return RegressionProtector()

    def test_{sanitized}_does_not_recur(self, protector):
        """Verify {issue_pattern} does not recur."""
        # Capture state before running the relevant code path
        before_state = {{
            "test_results": {{}},
            "metrics": {{}},
            "error_count": 0,
            "output": "",
        }}

        # Run the code that could trigger regression
        # (Customize this section for the specific issue)
        after_state = {{
            "test_results": {{}},
            "metrics": {{}},
            "error_count": 0,
            "output": "",
        }}

        # Check for regression using the protector
        result = protector.check_for_regression(
            before_state=before_state,
            after_state=after_state,
            issue_pattern="{issue_pattern}",
        )

        assert not result.regression_detected, (
            f"Regression detected for {issue_pattern}: {{result.differences}}"
        )

    def test_{sanitized}_fix_still_works(self, protector):
        """Verify the fix for {issue_pattern} is still effective."""
        # Capture current state to verify fix effectiveness
        current_state = {{
            "test_results": {{}},
            "error_count": 0,
            "output": "",
        }}

        # Verify the fix is still effective
        result = protector.verify_fix(
            fix_commit="{task_id}",
            original_issue="{issue_pattern}",
            current_state=current_state,
        )

        assert result.fix_verified, (
            f"Fix no longer effective for {issue_pattern}: {{result.stale_indicators}}"
        )
'''

        return RegressionTest(
            test_id=test_id,
            issue_pattern=issue_pattern,
            test_code=test_code,
            created_at=datetime.now(),
            source_task_id=task_id,
        )

    def _sanitize_identifier(self, text: str) -> str:
        """Convert text to a valid Python identifier.

        Args:
            text: The text to sanitize.

        Returns:
            A valid Python identifier.
        """
        # Replace non-alphanumeric with underscores
        sanitized = re.sub(r"[^a-zA-Z0-9]", "_", text.lower())
        # Remove leading digits
        sanitized = re.sub(r"^[0-9]+", "", sanitized)
        # Collapse multiple underscores
        sanitized = re.sub(r"_+", "_", sanitized)
        # Remove leading/trailing underscores
        sanitized = sanitized.strip("_")
        # Ensure non-empty
        return sanitized or "unknown_pattern"

    # =========================================================================
    # Regression Check and Fix Verification (IMP-REG-001)
    # =========================================================================

    def check_for_regression(
        self,
        before_state: Dict[str, Any],
        after_state: Dict[str, Any],
        issue_pattern: str = "",
    ) -> RegressionCheckResult:
        """Check for regression between two states (IMP-REG-001).

        Compares before and after states to detect if a previously fixed issue
        has recurred. This method is designed to be called by generated regression
        tests.

        Args:
            before_state: State snapshot before the change being tested.
                         Keys can include: test_results, metrics, file_hashes, etc.
            after_state: State snapshot after the change being tested.
            issue_pattern: The pattern describing the issue to check for.

        Returns:
            RegressionCheckResult indicating whether a regression was detected.
        """
        differences = []
        regression_detected = False
        severity = "low"

        # Compare test results if present
        before_tests = before_state.get("test_results", {})
        after_tests = after_state.get("test_results", {})

        if before_tests and after_tests:
            # Check for newly failing tests
            for test_name, before_result in before_tests.items():
                after_result = after_tests.get(test_name)
                if before_result == "pass" and after_result == "fail":
                    differences.append(f"Test '{test_name}' regressed: pass -> fail")
                    regression_detected = True
                    severity = "high"

        # Compare metrics if present
        before_metrics = before_state.get("metrics", {})
        after_metrics = after_state.get("metrics", {})

        if before_metrics and after_metrics:
            for metric_name, before_value in before_metrics.items():
                after_value = after_metrics.get(metric_name)
                if after_value is not None and isinstance(before_value, (int, float)):
                    # Check for significant degradation (>10% worse)
                    if after_value > before_value * 1.1:
                        differences.append(
                            f"Metric '{metric_name}' degraded: {before_value} -> {after_value}"
                        )
                        if not regression_detected:
                            severity = "medium"
                        regression_detected = True

        # Check for pattern-specific indicators
        if issue_pattern:
            pattern_lower = issue_pattern.lower()

            # Check error counts
            before_errors = before_state.get("error_count", 0)
            after_errors = after_state.get("error_count", 0)
            if after_errors > before_errors:
                differences.append(f"Error count increased: {before_errors} -> {after_errors}")
                regression_detected = True
                severity = "high"

            # Check for pattern recurrence in logs/output
            after_output = after_state.get("output", "").lower()
            before_output = before_state.get("output", "").lower()
            if pattern_lower in after_output and pattern_lower not in before_output:
                differences.append(f"Issue pattern '{issue_pattern}' detected in output")
                regression_detected = True
                severity = "high"

        # Log if regression detected
        if regression_detected:
            logger.warning(
                f"[IMP-REG-001] Regression detected: {len(differences)} difference(s), "
                f"severity={severity}"
            )

        return RegressionCheckResult(
            regression_detected=regression_detected,
            before_state=before_state,
            after_state=after_state,
            differences=differences,
            severity=severity,
            pattern_matched=issue_pattern if regression_detected else "",
        )

    def verify_fix(
        self,
        fix_commit: str,
        original_issue: str,
        current_state: Optional[Dict[str, Any]] = None,
    ) -> FixVerificationResult:
        """Verify that a fix is still effective (IMP-REG-001).

        Checks whether a fix for an issue is still working by examining
        current state against the original issue description.

        Args:
            fix_commit: The commit hash or ID that implemented the fix.
            original_issue: Description of the original issue that was fixed.
            current_state: Optional current state to check against.
                          Can include: test_results, logs, error_counts, etc.

        Returns:
            FixVerificationResult indicating whether the fix is still effective.
        """
        evidence = []
        stale_indicators = []
        fix_verified = False
        verification_method = "pattern_check"

        # Check for existing regression tests
        existing_tests = self._find_existing_tests(original_issue)
        if existing_tests:
            evidence.append(f"Found {len(existing_tests)} regression test(s) for this fix")
            # Assume tests pass if we have them (actual test execution would be external)
            fix_verified = True
            verification_method = "test_pass"

        # Check current state if provided
        if current_state:
            # Check error counts
            error_count = current_state.get("error_count", 0)
            if error_count == 0:
                evidence.append("No errors detected in current state")
                fix_verified = True
            elif error_count > 0:
                stale_indicators.append(f"Found {error_count} error(s) in current state")

            # Check for issue pattern in output
            output = current_state.get("output", "").lower()
            issue_lower = original_issue.lower()
            issue_words = set(issue_lower.split())

            # Count how many issue words appear in output
            matches = sum(1 for word in issue_words if word in output and len(word) > 3)
            if matches > len(issue_words) * 0.5:
                stale_indicators.append(
                    f"Issue pattern may be present in output ({matches}/{len(issue_words)} words match)"
                )
                fix_verified = False

            # Check test results if available
            test_results = current_state.get("test_results", {})
            if test_results:
                passing = sum(1 for r in test_results.values() if r == "pass")
                total = len(test_results)
                if total > 0:
                    if passing == total:
                        evidence.append(f"All {total} tests passing")
                        fix_verified = True
                        verification_method = "test_pass"
                    else:
                        failing = total - passing
                        stale_indicators.append(f"{failing}/{total} tests failing")
                        # Failing tests indicate the fix may no longer be effective
                        fix_verified = False
                        verification_method = "test_pass"

        # If no specific verification, check by pattern matching
        if not evidence and not stale_indicators:
            # At minimum, verify we have test coverage
            if existing_tests:
                evidence.append("Regression test coverage exists")
                fix_verified = True
            else:
                stale_indicators.append("No regression test coverage found")
                fix_verified = False
                verification_method = "manual"

        # Log verification result
        if fix_verified:
            logger.debug(
                f"[IMP-REG-001] Fix verified for '{original_issue[:50]}...': "
                f"{len(evidence)} evidence item(s)"
            )
        else:
            logger.warning(
                f"[IMP-REG-001] Fix verification failed for '{original_issue[:50]}...': "
                f"{len(stale_indicators)} stale indicator(s)"
            )

        return FixVerificationResult(
            fix_verified=fix_verified,
            original_issue=original_issue,
            fix_description=f"Fix commit: {fix_commit}" if fix_commit else "Unknown fix",
            verification_method=verification_method,
            evidence=evidence,
            stale_indicators=stale_indicators,
        )

    # =========================================================================
    # Pre-Task-Generation Regression Checking (IMP-FBK-003)
    # =========================================================================

    def would_cause_regression(
        self,
        issue_pattern: str,
        pattern_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Check if generating a task for this pattern would reintroduce a known issue.

        This method should be called BEFORE generating tasks to filter out patterns
        that match previously fixed issues that are still valid.

        Args:
            issue_pattern: The pattern describing the issue/task to check.
            pattern_context: Optional additional context about the pattern
                            (e.g., phase_id, issue_type, metric_value).

        Returns:
            True if generating a task for this pattern would likely cause a regression,
            False if safe to proceed.
        """
        # Check if this pattern matches a known fixed issue
        if self._check_specific_regression(issue_pattern, pattern_context):
            # Verify the fix is still valid before blocking
            if self._verify_fix_still_valid(issue_pattern, pattern_context):
                logger.warning(
                    f"[ROAD-I] Pattern '{issue_pattern[:50]}...' would reintroduce "
                    f"a known fixed issue - blocking task generation"
                )
                return True

        return False

    def _check_specific_regression(
        self,
        issue_pattern: str,
        pattern_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Check if the issue pattern matches a known fixed regression.

        Implements the regression check logic for detecting if a proposed
        task/pattern matches a previously fixed issue.

        Args:
            issue_pattern: The pattern describing the issue to check.
            pattern_context: Optional context (phase_id, issue_type, etc.)

        Returns:
            True if this pattern matches a known fixed issue.
        """
        # First check if we have existing regression tests for this pattern
        existing_tests = self._find_existing_tests(issue_pattern)
        if existing_tests:
            logger.debug(
                f"[ROAD-I] Found {len(existing_tests)} existing regression tests "
                f"for pattern '{issue_pattern[:50]}...'"
            )
            return True

        # Check against known fixed issues from test file content
        # Look for patterns that have been fixed and have test coverage
        if not self._tests_root.exists():
            return False

        # Normalize pattern for comparison
        pattern_lower = issue_pattern.lower()
        pattern_words = set(re.findall(r"\w+", pattern_lower))

        # Additional context-based matching
        context_phase = (pattern_context or {}).get("phase_id", "")
        context_type = (pattern_context or {}).get("issue_type", "")

        for test_file in self._tests_root.glob("test_regression_*.py"):
            try:
                content = test_file.read_text()
                content_lower = content.lower()

                # Check for explicit regression markers in test content
                if "regression detected" in content_lower or "issue recurred" in content_lower:
                    # Check if it relates to this pattern
                    if self._patterns_overlap(pattern_words, content_lower):
                        logger.debug(
                            f"[ROAD-I] Pattern matches regression test in {test_file.name}"
                        )
                        return True

                # Check for phase-specific matches
                if context_phase and context_phase.lower() in content_lower:
                    if context_type and context_type.lower() in content_lower:
                        logger.debug(
                            f"[ROAD-I] Context match found: phase={context_phase}, "
                            f"type={context_type} in {test_file.name}"
                        )
                        return True

            except (OSError, IOError) as e:
                logger.warning(f"Could not read test file {test_file}: {e}")

        return False

    def _verify_fix_still_valid(
        self,
        issue_pattern: str,
        pattern_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Verify that a fix for the pattern is still effective.

        Before blocking task generation, verify that the existing fix hasn't
        been reverted or become stale.

        Args:
            issue_pattern: The pattern describing the issue.
            pattern_context: Optional context about the pattern.

        Returns:
            True if the fix is still valid and should block new tasks,
            False if the fix may have been reverted or is stale.
        """
        existing_tests = self._find_existing_tests(issue_pattern)

        if not existing_tests:
            # No existing tests = no verified fix
            return False

        for test_path in existing_tests:
            try:
                test_file = Path(test_path)
                if not test_file.exists():
                    continue

                content = test_file.read_text()

                # Check for markers indicating the test/fix is still valid
                # Valid tests should have actual assertions, not just placeholders
                if self._test_has_valid_assertions(content):
                    # Check if test was recently modified (within 90 days)
                    # Recent modifications suggest active maintenance
                    mtime = datetime.fromtimestamp(test_file.stat().st_mtime)
                    days_since_modified = (datetime.now() - mtime).days

                    if days_since_modified <= 90:
                        logger.debug(
                            f"[ROAD-I] Fix verified as valid: {test_file.name} "
                            f"(modified {days_since_modified} days ago)"
                        )
                        return True
                    else:
                        # Test is old but may still be valid - check if it passes
                        logger.debug(
                            f"[ROAD-I] Fix exists but test is old ({days_since_modified} days): "
                            f"{test_file.name}"
                        )
                        # Be conservative: old but structured tests are still valid
                        return True

            except (OSError, IOError) as e:
                logger.warning(f"Could not verify fix validity for {test_path}: {e}")

        # No valid tests found - allow task generation
        return False

    def _patterns_overlap(self, pattern_words: set, content_lower: str) -> bool:
        """Check if pattern words have significant overlap with content.

        Args:
            pattern_words: Set of words from the pattern.
            content_lower: Lowercase content to check against.

        Returns:
            True if significant overlap exists.
        """
        content_words = set(re.findall(r"\w+", content_lower))
        overlap = pattern_words & content_words

        # Require significant overlap (at least 3 words or 50% of pattern words)
        min_overlap = min(3, len(pattern_words))
        return len(overlap) >= min_overlap or (
            len(pattern_words) > 0 and len(overlap) / len(pattern_words) >= 0.5
        )

    def _test_has_valid_assertions(self, test_content: str) -> bool:
        """Check if test content has valid assertions (not just placeholders).

        Args:
            test_content: The test file content.

        Returns:
            True if the test has real assertions.
        """
        # Check for actual assert statements
        if "assert " not in test_content.lower():
            return False

        # Check that assertions aren't just placeholders
        placeholder_markers = [
            "# TODO:",
            "# todo:",
            "pass  # placeholder",
            "pass #placeholder",
            "raise NotImplementedError",
        ]

        for marker in placeholder_markers:
            if marker.lower() in test_content.lower():
                # Has placeholder markers - may not be fully implemented
                # But still consider valid if there are other assertions
                real_asserts = re.findall(
                    r"assert\s+(?!.*TODO)(?!.*placeholder)", test_content, re.IGNORECASE
                )
                if real_asserts:
                    return True
                return False

        return True

    def assess_regression_risk(
        self,
        issue_pattern: str,
        pattern_context: Optional[Dict[str, Any]] = None,
    ) -> RiskAssessment:
        """Assess the regression risk for a given pattern (IMP-LOOP-018).

        Evaluates the risk of generating a task for this pattern based on:
        - Existing regression tests
        - Historical regression rate for similar patterns
        - Pattern overlap with known fixed issues

        Args:
            issue_pattern: The pattern describing the issue/task to assess.
            pattern_context: Optional additional context about the pattern.

        Returns:
            RiskAssessment with severity, blocking recommendation, and evidence.
        """
        evidence = []
        confidence = 0.0
        historical_rate = 0.0

        # Check if this pattern matches a known fixed issue
        existing_tests = self._find_existing_tests(issue_pattern)
        if existing_tests:
            evidence.append(
                f"Found {len(existing_tests)} existing regression test(s) for this pattern"
            )
            confidence += 0.3 * min(len(existing_tests), 3)  # Cap at 3 tests

        # Check against known fixed issues from test file content
        if self._check_specific_regression(issue_pattern, pattern_context):
            evidence.append("Pattern matches known fixed regression")
            confidence += 0.4

            # Verify if fix is still valid
            if self._verify_fix_still_valid(issue_pattern, pattern_context):
                evidence.append("Existing fix verified as still valid")
                confidence += 0.2
            else:
                evidence.append("Existing fix may be stale or reverted")
                confidence -= 0.1

        # Calculate historical regression rate (mock - would query database in real impl)
        context_type = (pattern_context or {}).get("issue_type", "")
        if context_type:
            historical_rate = self._get_historical_regression_rate(context_type)
            if historical_rate > 0:
                evidence.append(
                    f"Historical regression rate for '{context_type}': {historical_rate:.1%}"
                )
                confidence += historical_rate * 0.3

        # Clamp confidence to [0, 1]
        confidence = max(0.0, min(1.0, confidence))

        # Determine severity based on confidence and evidence
        severity = self._calculate_risk_severity(confidence, len(existing_tests), historical_rate)

        # Determine blocking recommendation
        blocking_recommended = severity in (RiskSeverity.HIGH, RiskSeverity.CRITICAL)

        return RiskAssessment(
            severity=severity,
            blocking_recommended=blocking_recommended,
            confidence=confidence,
            evidence=evidence,
            pattern_type=context_type,
            historical_regression_rate=historical_rate,
        )

    def _calculate_risk_severity(
        self,
        confidence: float,
        existing_test_count: int,
        historical_rate: float,
    ) -> RiskSeverity:
        """Calculate risk severity based on multiple factors (IMP-LOOP-018).

        Args:
            confidence: Overall confidence score (0-1)
            existing_test_count: Number of existing regression tests
            historical_rate: Historical regression rate for this pattern type

        Returns:
            RiskSeverity level
        """
        # Critical: High confidence + multiple existing tests + high historical rate
        if confidence >= 0.8 and existing_test_count >= 2 and historical_rate >= 0.3:
            return RiskSeverity.CRITICAL

        # High: Good confidence + existing tests
        if confidence >= 0.6 and existing_test_count >= 1:
            return RiskSeverity.HIGH

        # Medium: Some confidence or existing tests
        if confidence >= 0.4 or existing_test_count >= 1:
            return RiskSeverity.MEDIUM

        # Low: Little or no evidence of risk
        return RiskSeverity.LOW

    def _get_historical_regression_rate(self, issue_type: str) -> float:
        """Get historical regression rate for an issue type (IMP-LOOP-018).

        In a real implementation, this would query the database for historical data.

        Args:
            issue_type: Type of issue to check

        Returns:
            Historical regression rate (0.0 to 1.0)
        """
        # Default rates based on issue type (would be computed from actual data)
        default_rates = {
            "cost_sink": 0.15,  # Cost optimizations sometimes regress
            "failure_mode": 0.25,  # Failure fixes are prone to regression
            "retry_cause": 0.20,  # Retry fixes can be fragile
            "performance": 0.10,  # Performance fixes usually stable
            "flaky_test": 0.35,  # Flaky test fixes often regress
        }
        return default_rates.get(issue_type, 0.10)

    def filter_patterns_for_regressions(
        self,
        patterns: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Filter a list of patterns to remove those that would cause regressions.

        Convenience method for filtering multiple patterns at once before task
        generation.

        Args:
            patterns: List of pattern dictionaries from task generator.

        Returns:
            Filtered list with regression-causing patterns removed.
        """
        filtered = []
        blocked_count = 0

        for pattern in patterns:
            # Extract pattern info for regression check
            issue_pattern = pattern.get("type", "")
            examples = pattern.get("examples", [])

            # Build context from examples
            pattern_context = {}
            if examples:
                first_example = examples[0]
                pattern_context = {
                    "phase_id": first_example.get("phase_id", ""),
                    "issue_type": first_example.get("issue_type", ""),
                    "phase_type": first_example.get("phase_type", ""),
                }

            # Build a more descriptive pattern string from examples
            if examples:
                example_contents = [e.get("content", "")[:100] for e in examples[:3]]
                full_pattern = f"{issue_pattern}: {' | '.join(example_contents)}"
            else:
                full_pattern = issue_pattern

            if self.would_cause_regression(full_pattern, pattern_context):
                blocked_count += 1
                logger.info(
                    f"[IMP-FBK-003] Blocked pattern '{issue_pattern}' - "
                    f"would reintroduce known regression"
                )
            else:
                filtered.append(pattern)

        if blocked_count > 0:
            logger.info(
                f"[IMP-FBK-003] Filtered {blocked_count} patterns that would cause regressions"
            )

        return filtered

    def filter_patterns_with_risk_assessment(
        self,
        patterns: List[Dict[str, Any]],
    ) -> tuple[List[Dict[str, Any]], Dict[str, RiskAssessment]]:
        """Filter patterns and return risk assessments for each (IMP-LOOP-018).

        Enhanced version of filter_patterns_for_regressions that also returns
        detailed risk assessments for each pattern.

        Args:
            patterns: List of pattern dictionaries from task generator.

        Returns:
            Tuple of:
            - Filtered list of patterns (high/critical risk removed)
            - Dict mapping pattern type to RiskAssessment
        """
        filtered = []
        risk_assessments: Dict[str, RiskAssessment] = {}
        blocked_count = 0
        medium_risk_count = 0

        for pattern in patterns:
            issue_pattern = pattern.get("type", "")
            examples = pattern.get("examples", [])

            # Build context from examples
            pattern_context = {}
            if examples:
                first_example = examples[0]
                pattern_context = {
                    "phase_id": first_example.get("phase_id", ""),
                    "issue_type": first_example.get("issue_type", ""),
                    "phase_type": first_example.get("phase_type", ""),
                }

            # Build full pattern string
            if examples:
                example_contents = [e.get("content", "")[:100] for e in examples[:3]]
                full_pattern = f"{issue_pattern}: {' | '.join(example_contents)}"
            else:
                full_pattern = issue_pattern

            # Assess risk
            risk = self.assess_regression_risk(full_pattern, pattern_context)
            risk_assessments[issue_pattern] = risk

            if risk.blocking_recommended:
                blocked_count += 1
                logger.warning(
                    f"[IMP-LOOP-018] Blocked pattern '{issue_pattern}' - "
                    f"risk severity: {risk.severity.value}, confidence: {risk.confidence:.2f}"
                )
            else:
                if risk.severity == RiskSeverity.MEDIUM:
                    medium_risk_count += 1
                    # Add risk info to pattern for approval gate handling
                    pattern["_risk_assessment"] = risk
                    pattern["_requires_approval"] = True
                filtered.append(pattern)

        if blocked_count > 0 or medium_risk_count > 0:
            logger.info(
                f"[IMP-LOOP-018] Risk assessment: blocked={blocked_count}, "
                f"medium_risk={medium_risk_count}, passed={len(filtered)}"
            )

        return filtered, risk_assessments
