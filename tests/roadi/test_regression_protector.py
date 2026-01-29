"""Tests for RegressionProtector (IMP-REG-001).

Tests the regression check and fix verification functionality added to
regression_protector.py.
"""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopack.roadi.regression_protector import (FixVerificationResult,
                                                 RegressionCheckResult,
                                                 RegressionProtector,
                                                 RiskAssessment, RiskSeverity)


class TestRegressionCheckResult:
    """Test RegressionCheckResult dataclass."""

    def test_basic_creation(self):
        """Test creating a basic RegressionCheckResult."""
        result = RegressionCheckResult(
            regression_detected=False,
            before_state={"test_results": {}},
            after_state={"test_results": {}},
        )
        assert result.regression_detected is False
        assert result.differences == []
        assert result.severity == "unknown"

    def test_with_differences(self):
        """Test RegressionCheckResult with detected differences."""
        result = RegressionCheckResult(
            regression_detected=True,
            before_state={"test_results": {"test_a": "pass"}},
            after_state={"test_results": {"test_a": "fail"}},
            differences=["Test 'test_a' regressed: pass -> fail"],
            severity="high",
            pattern_matched="test_failure",
        )
        assert result.regression_detected is True
        assert len(result.differences) == 1
        assert result.severity == "high"


class TestFixVerificationResult:
    """Test FixVerificationResult dataclass."""

    def test_basic_creation(self):
        """Test creating a basic FixVerificationResult."""
        result = FixVerificationResult(
            fix_verified=True,
            original_issue="Test issue",
            fix_description="Fix commit: ABC123",
        )
        assert result.fix_verified is True
        assert result.original_issue == "Test issue"
        assert result.evidence == []
        assert result.stale_indicators == []

    def test_with_evidence(self):
        """Test FixVerificationResult with evidence."""
        result = FixVerificationResult(
            fix_verified=True,
            original_issue="Memory leak in parser",
            fix_description="Fix commit: DEF456",
            verification_method="test_pass",
            evidence=["All tests passing", "No memory leaks detected"],
            stale_indicators=[],
        )
        assert result.verification_method == "test_pass"
        assert len(result.evidence) == 2


class TestCheckForRegression:
    """Test RegressionProtector.check_for_regression method (IMP-REG-001)."""

    @pytest.fixture
    def protector(self, tmp_path):
        """Create a RegressionProtector with a temp test root."""
        return RegressionProtector(tests_root=tmp_path / "tests" / "regression")

    def test_no_regression_when_states_identical(self, protector):
        """Test no regression detected when states are identical."""
        state = {
            "test_results": {"test_a": "pass", "test_b": "pass"},
            "metrics": {"response_time": 100},
            "error_count": 0,
        }
        result = protector.check_for_regression(
            before_state=state,
            after_state=state.copy(),
            issue_pattern="test pattern",
        )
        assert result.regression_detected is False
        assert result.differences == []

    def test_detects_test_regression(self, protector):
        """Test detection of test failures as regression."""
        before_state = {
            "test_results": {"test_a": "pass", "test_b": "pass"},
        }
        after_state = {
            "test_results": {"test_a": "pass", "test_b": "fail"},
        }
        result = protector.check_for_regression(
            before_state=before_state,
            after_state=after_state,
            issue_pattern="test failure",
        )
        assert result.regression_detected is True
        assert len(result.differences) == 1
        assert "test_b" in result.differences[0]
        assert result.severity == "high"

    def test_detects_metric_degradation(self, protector):
        """Test detection of significant metric degradation."""
        before_state = {
            "metrics": {"response_time": 100},
        }
        after_state = {
            "metrics": {"response_time": 150},  # 50% worse
        }
        result = protector.check_for_regression(
            before_state=before_state,
            after_state=after_state,
            issue_pattern="performance",
        )
        assert result.regression_detected is True
        assert any("response_time" in d for d in result.differences)

    def test_ignores_minor_metric_change(self, protector):
        """Test that minor metric changes are not flagged."""
        before_state = {
            "metrics": {"response_time": 100},
        }
        after_state = {
            "metrics": {"response_time": 105},  # Only 5% worse
        }
        result = protector.check_for_regression(
            before_state=before_state,
            after_state=after_state,
            issue_pattern="performance",
        )
        assert result.regression_detected is False

    def test_detects_error_count_increase(self, protector):
        """Test detection of increased error count."""
        before_state = {
            "error_count": 0,
        }
        after_state = {
            "error_count": 5,
        }
        result = protector.check_for_regression(
            before_state=before_state,
            after_state=after_state,
            issue_pattern="error handling",
        )
        assert result.regression_detected is True
        assert any("Error count" in d for d in result.differences)
        assert result.severity == "high"

    def test_detects_pattern_in_output(self, protector):
        """Test detection of issue pattern appearing in output."""
        before_state = {
            "output": "All systems normal",
        }
        after_state = {
            "output": "Error: null pointer exception occurred",
        }
        result = protector.check_for_regression(
            before_state=before_state,
            after_state=after_state,
            issue_pattern="null pointer exception",
        )
        assert result.regression_detected is True
        assert result.pattern_matched == "null pointer exception"

    def test_handles_empty_states(self, protector):
        """Test handling of empty state dictionaries."""
        result = protector.check_for_regression(
            before_state={},
            after_state={},
            issue_pattern="test",
        )
        assert result.regression_detected is False


class TestVerifyFix:
    """Test RegressionProtector.verify_fix method (IMP-REG-001)."""

    @pytest.fixture
    def protector(self, tmp_path):
        """Create a RegressionProtector with a temp test root."""
        tests_root = tmp_path / "tests" / "regression"
        tests_root.mkdir(parents=True, exist_ok=True)
        return RegressionProtector(tests_root=tests_root)

    def test_fix_verified_with_passing_tests(self, protector):
        """Test fix verification when all tests pass."""
        current_state = {
            "test_results": {"test_a": "pass", "test_b": "pass"},
            "error_count": 0,
        }
        result = protector.verify_fix(
            fix_commit="abc123",
            original_issue="Memory leak in parser",
            current_state=current_state,
        )
        assert result.fix_verified is True
        assert result.verification_method == "test_pass"
        assert any("tests passing" in e for e in result.evidence)

    def test_fix_not_verified_with_failing_tests(self, protector):
        """Test fix verification fails when tests fail."""
        current_state = {
            "test_results": {"test_a": "pass", "test_b": "fail"},
            "error_count": 0,
        }
        result = protector.verify_fix(
            fix_commit="abc123",
            original_issue="Test failure issue",
            current_state=current_state,
        )
        assert result.fix_verified is False
        assert any("failing" in s for s in result.stale_indicators)

    def test_fix_verified_with_no_errors(self, protector):
        """Test fix verification when no errors in current state."""
        current_state = {
            "error_count": 0,
        }
        result = protector.verify_fix(
            fix_commit="def456",
            original_issue="Error handling issue",
            current_state=current_state,
        )
        assert result.fix_verified is True
        assert any("No errors" in e for e in result.evidence)

    def test_fix_verified_with_regression_tests(self, protector, tmp_path):
        """Test fix verification when regression tests exist."""
        # Create a mock regression test file
        tests_root = tmp_path / "tests" / "regression"
        tests_root.mkdir(parents=True, exist_ok=True)
        test_file = tests_root / "test_regression_abc123.py"
        test_file.write_text('''"""Regression test for memory leak."""
import pytest

def test_no_memory_leak():
    assert True  # Memory leak fixed
''')

        protector_with_tests = RegressionProtector(tests_root=tests_root)
        result = protector_with_tests.verify_fix(
            fix_commit="abc123",
            original_issue="memory leak",
            current_state={},
        )
        assert result.fix_verified is True
        assert any("regression test" in e for e in result.evidence)

    def test_fix_not_verified_without_coverage(self, protector):
        """Test fix verification fails without any coverage."""
        result = protector.verify_fix(
            fix_commit="xyz789",
            original_issue="Some obscure issue with no tests",
            current_state={},
        )
        assert result.fix_verified is False
        assert result.verification_method == "manual"
        assert any("No regression test" in s for s in result.stale_indicators)

    def test_handles_none_current_state(self, protector):
        """Test fix verification with None current_state."""
        result = protector.verify_fix(
            fix_commit="abc123",
            original_issue="test issue",
            current_state=None,
        )
        # Should still work, just with less verification
        assert isinstance(result, FixVerificationResult)


class TestGeneratedTestTemplate:
    """Test that generated test templates use the new methods."""

    @pytest.fixture
    def protector(self, tmp_path):
        """Create a RegressionProtector with a temp test root."""
        return RegressionProtector(tests_root=tmp_path / "tests" / "regression")

    def test_generated_test_imports_protector(self, protector):
        """Test that generated tests import RegressionProtector."""
        test = protector._generate_test("test issue", "TASK-001")
        assert (
            "from autopack.roadi.regression_protector import RegressionProtector" in test.test_code
        )

    def test_generated_test_has_protector_fixture(self, protector):
        """Test that generated tests have a protector fixture."""
        test = protector._generate_test("test issue", "TASK-001")
        assert "@pytest.fixture" in test.test_code
        assert "def protector(self)" in test.test_code

    def test_generated_test_uses_check_for_regression(self, protector):
        """Test that generated tests call check_for_regression."""
        test = protector._generate_test("test issue", "TASK-001")
        assert "check_for_regression" in test.test_code
        assert "before_state" in test.test_code
        assert "after_state" in test.test_code

    def test_generated_test_uses_verify_fix(self, protector):
        """Test that generated tests call verify_fix."""
        test = protector._generate_test("test issue", "TASK-001")
        assert "verify_fix" in test.test_code
        assert "fix_commit" in test.test_code

    def test_generated_test_has_assertions(self, protector):
        """Test that generated tests have proper assertions."""
        test = protector._generate_test("test issue", "TASK-001")
        assert "assert not result.regression_detected" in test.test_code
        assert "assert result.fix_verified" in test.test_code


class TestIntegrationWithExistingMethods:
    """Test that new methods integrate with existing functionality."""

    @pytest.fixture
    def protector(self, tmp_path):
        """Create a RegressionProtector with a temp test root."""
        tests_root = tmp_path / "tests" / "regression"
        tests_root.mkdir(parents=True, exist_ok=True)
        return RegressionProtector(tests_root=tests_root)

    def test_check_for_regression_logs_when_detected(self, protector, caplog):
        """Test that regression detection is logged."""
        import logging

        with caplog.at_level(logging.WARNING):
            protector.check_for_regression(
                before_state={"error_count": 0},
                after_state={"error_count": 5},
                issue_pattern="error handling",
            )
        assert "Regression detected" in caplog.text

    def test_verify_fix_uses_find_existing_tests(self, protector, tmp_path):
        """Test that verify_fix uses _find_existing_tests."""
        # Create a test file
        tests_root = tmp_path / "tests" / "regression"
        test_file = tests_root / "test_regression_issue.py"
        test_file.write_text('''"""Test for specific issue."""
import pytest

def test_specific_issue():
    assert True
''')

        result = protector.verify_fix(
            fix_commit="abc",
            original_issue="specific issue",
            current_state={},
        )
        # Should find the existing test
        assert any("regression test" in e for e in result.evidence)

    def test_would_cause_regression_uses_verify_fix_still_valid(self, protector, tmp_path):
        """Test that would_cause_regression uses the verification logic."""
        tests_root = tmp_path / "tests" / "regression"
        test_file = tests_root / "test_regression_pattern.py"
        # Create a test with actual assertions
        # Include "pattern" and "check" as separate words to ensure pattern matching works
        test_file.write_text('''"""Test for pattern check issue."""
import pytest

# This test verifies the pattern check functionality
def test_pattern_does_not_recur():
    # Check that the pattern is not detected
    assert True  # Pattern check verified
''')

        result = protector.would_cause_regression(
            issue_pattern="pattern check",
            pattern_context={"phase_id": "test", "issue_type": "test_type"},
        )
        # Should detect that this pattern has existing protection
        assert result is True


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def protector(self, tmp_path):
        """Create a RegressionProtector with a temp test root."""
        return RegressionProtector(tests_root=tmp_path / "tests" / "regression")

    def test_check_for_regression_with_non_numeric_metrics(self, protector):
        """Test handling of non-numeric metric values."""
        before_state = {
            "metrics": {"status": "ok"},
        }
        after_state = {
            "metrics": {"status": "error"},
        }
        # Should not raise an exception
        result = protector.check_for_regression(
            before_state=before_state,
            after_state=after_state,
        )
        assert isinstance(result, RegressionCheckResult)

    def test_verify_fix_with_empty_commit(self, protector):
        """Test verify_fix with empty commit string."""
        result = protector.verify_fix(
            fix_commit="",
            original_issue="test issue",
            current_state={},
        )
        assert "Unknown fix" in result.fix_description

    def test_check_for_regression_pattern_matching_case_insensitive(self, protector):
        """Test that pattern matching is case-insensitive."""
        before_state = {"output": "Normal operation"}
        after_state = {"output": "ERROR: NULL POINTER EXCEPTION occurred"}

        result = protector.check_for_regression(
            before_state=before_state,
            after_state=after_state,
            issue_pattern="null pointer exception",
        )
        assert result.regression_detected is True
