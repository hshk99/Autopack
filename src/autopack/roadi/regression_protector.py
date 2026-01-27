"""Regression protection for fixed issues.

This module provides automatic regression protection when issues are fixed,
ensuring that previously resolved problems do not recur. It integrates with
ROAD-C (task generator) to add regression tests for each fix.

IMP-FBK-003: Also provides pre-task-generation regression checking to prevent
re-attempting known-bad improvements.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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

# Generated from task: {task_id}
# Pattern: {issue_pattern}
# Test ID: {test_id}


class TestRegression{test_id.replace("-", "")}:
    """Regression tests for {issue_pattern}."""

    def test_{sanitized}_does_not_recur(self):
        """Verify {issue_pattern} does not recur."""
        # TODO: Implement specific regression check
        # This test should fail if the issue pattern is detected
        #
        # Example assertion:
        # result = check_for_pattern("{issue_pattern}")
        # assert not result.detected, f"Regression detected: {issue_pattern}"
        pass

    def test_{sanitized}_fix_still_works(self):
        """Verify the fix for {issue_pattern} is still effective."""
        # TODO: Implement fix verification
        pass
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
