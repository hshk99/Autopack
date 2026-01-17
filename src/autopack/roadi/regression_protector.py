"""Regression protection for fixed issues.

This module provides automatic regression protection when issues are fixed,
ensuring that previously resolved problems do not recur. It integrates with
ROAD-C (task generator) to add regression tests for each fix.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

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
