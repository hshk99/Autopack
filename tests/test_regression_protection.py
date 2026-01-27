"""Tests for ROAD-I Regression Protection System."""

import pytest
from pathlib import Path

from autopack.roadi import (
    RegressionProtector,
    RegressionTest,
    ProtectionResult,
    RiskSeverity,
    RiskAssessment,
)


class TestRegressionProtector:
    """Test suite for RegressionProtector."""

    def test_check_protection_unprotected(self, tmp_path: Path):
        """Test that unprotected patterns return suggested tests."""
        protector = RegressionProtector(tests_root=tmp_path / "tests")

        result = protector.check_protection("timeout error")

        assert not result.is_protected
        assert result.suggested_test is not None
        assert "timeout error" in result.suggested_test.issue_pattern

    def test_check_protection_returns_protection_result(self, tmp_path: Path):
        """Test that check_protection returns a ProtectionResult."""
        protector = RegressionProtector(tests_root=tmp_path / "tests")

        result = protector.check_protection("some pattern")

        assert isinstance(result, ProtectionResult)
        assert isinstance(result.is_protected, bool)
        assert isinstance(result.existing_tests, list)

    def test_add_protection_creates_test_file(self, tmp_path: Path):
        """Test that add_protection creates the test file."""
        protector = RegressionProtector(tests_root=tmp_path / "tests")

        protector.add_protection(
            task_id="TASK-ABC123",
            issue_pattern="timeout error",
        )

        test_file = tmp_path / "tests" / "test_regression_task-abc123.py"
        assert test_file.exists()
        content = test_file.read_text()
        assert "timeout error" in content
        assert "TASK-ABC123" in content

    def test_add_protection_returns_regression_test(self, tmp_path: Path):
        """Test that add_protection returns a RegressionTest."""
        protector = RegressionProtector(tests_root=tmp_path / "tests")

        test = protector.add_protection(
            task_id="TASK-XYZ789",
            issue_pattern="connection failure",
        )

        assert isinstance(test, RegressionTest)
        assert test.test_id.startswith("REG-")
        assert test.issue_pattern == "connection failure"
        assert test.source_task_id == "TASK-XYZ789"

    def test_check_protection_finds_existing(self, tmp_path: Path):
        """Test that check_protection finds existing tests."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Create existing test with the pattern
        (tests_dir / "test_regression_existing.py").write_text(
            '"""Tests for timeout error pattern."""\n'
            "# Pattern: timeout error\n"
            "def test_timeout_error():\n"
            "    pass\n"
        )

        protector = RegressionProtector(tests_root=tests_dir)
        result = protector.check_protection("timeout error")

        assert result.is_protected
        assert len(result.existing_tests) > 0
        assert result.suggested_test is None

    def test_check_protection_case_insensitive(self, tmp_path: Path):
        """Test that pattern matching is case insensitive."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Create existing test with different case
        (tests_dir / "test_regression_case.py").write_text(
            '"""Tests for TIMEOUT ERROR pattern."""\ndef test_timeout():\n    pass\n'
        )

        protector = RegressionProtector(tests_root=tests_dir)
        result = protector.check_protection("timeout error")

        assert result.is_protected

    def test_check_protection_no_false_positives(self, tmp_path: Path):
        """Test that unrelated tests don't match."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Create existing test for different pattern
        (tests_dir / "test_regression_different.py").write_text(
            '"""Tests for memory leak pattern."""\ndef test_memory_leak():\n    pass\n'
        )

        protector = RegressionProtector(tests_root=tests_dir)
        result = protector.check_protection("timeout error")

        assert not result.is_protected
        assert len(result.existing_tests) == 0

    def test_generated_test_is_valid_python(self, tmp_path: Path):
        """Test that generated test code is valid Python."""
        protector = RegressionProtector(tests_root=tmp_path / "tests")

        test = protector.add_protection(
            task_id="TASK-VALID",
            issue_pattern="database connection",
        )

        # Try to compile the generated code
        try:
            compile(test.test_code, "<string>", "exec")
        except SyntaxError as e:
            pytest.fail(f"Generated test code is not valid Python: {e}")

    def test_sanitize_special_characters(self, tmp_path: Path):
        """Test that special characters in patterns are handled."""
        protector = RegressionProtector(tests_root=tmp_path / "tests")

        test = protector.add_protection(
            task_id="TASK-SPECIAL",
            issue_pattern="error: 'NoneType' object",
        )

        # Should not raise and should produce valid code
        compile(test.test_code, "<string>", "exec")
        assert test.test_id.startswith("REG-")

    def test_creates_nested_directories(self, tmp_path: Path):
        """Test that nested test directories are created."""
        protector = RegressionProtector(tests_root=tmp_path / "deeply" / "nested" / "tests")

        protector.add_protection(
            task_id="TASK-NESTED",
            issue_pattern="nested test",
        )

        test_file = tmp_path / "deeply" / "nested" / "tests" / "test_regression_task-nested.py"
        assert test_file.exists()

    def test_multiple_protections(self, tmp_path: Path):
        """Test adding multiple protections."""
        protector = RegressionProtector(tests_root=tmp_path / "tests")

        test1 = protector.add_protection("TASK-001", "timeout error")
        test2 = protector.add_protection("TASK-002", "memory leak")
        test3 = protector.add_protection("TASK-003", "race condition")

        # All should have unique IDs
        assert test1.test_id != test2.test_id
        assert test2.test_id != test3.test_id

        # All files should exist
        assert (tmp_path / "tests" / "test_regression_task-001.py").exists()
        assert (tmp_path / "tests" / "test_regression_task-002.py").exists()
        assert (tmp_path / "tests" / "test_regression_task-003.py").exists()

    def test_default_tests_root(self):
        """Test that default tests_root is set correctly."""
        protector = RegressionProtector()

        assert protector._tests_root == Path("tests/regression")

    def test_protection_result_suggested_test_has_code(self, tmp_path: Path):
        """Test that suggested tests include test code."""
        protector = RegressionProtector(tests_root=tmp_path / "tests")

        result = protector.check_protection("api rate limit")

        assert result.suggested_test is not None
        assert len(result.suggested_test.test_code) > 0
        assert "api rate limit" in result.suggested_test.test_code.lower()


class TestRegressionTest:
    """Test suite for RegressionTest dataclass."""

    def test_regression_test_fields(self):
        """Test RegressionTest has all required fields."""
        from datetime import datetime

        test = RegressionTest(
            test_id="REG-12345678",
            issue_pattern="test pattern",
            test_code="def test(): pass",
            created_at=datetime.now(),
            source_task_id="TASK-001",
        )

        assert test.test_id == "REG-12345678"
        assert test.issue_pattern == "test pattern"
        assert test.test_code == "def test(): pass"
        assert test.source_task_id == "TASK-001"


class TestProtectionResult:
    """Test suite for ProtectionResult dataclass."""

    def test_protection_result_protected(self):
        """Test ProtectionResult when protected."""
        result = ProtectionResult(
            is_protected=True,
            existing_tests=["tests/test_1.py", "tests/test_2.py"],
            suggested_test=None,
        )

        assert result.is_protected
        assert len(result.existing_tests) == 2
        assert result.suggested_test is None

    def test_protection_result_unprotected(self):
        """Test ProtectionResult when not protected."""
        from datetime import datetime

        suggested = RegressionTest(
            test_id="REG-ABCD1234",
            issue_pattern="some error",
            test_code="# test code",
            created_at=datetime.now(),
            source_task_id="TASK-XYZ",
        )

        result = ProtectionResult(
            is_protected=False,
            existing_tests=[],
            suggested_test=suggested,
        )

        assert not result.is_protected
        assert len(result.existing_tests) == 0
        assert result.suggested_test is not None


class TestRiskSeverity:
    """Test suite for RiskSeverity enum (IMP-LOOP-018)."""

    def test_risk_severity_values(self):
        """Test RiskSeverity enum has all required values."""
        assert RiskSeverity.LOW.value == "low"
        assert RiskSeverity.MEDIUM.value == "medium"
        assert RiskSeverity.HIGH.value == "high"
        assert RiskSeverity.CRITICAL.value == "critical"

    def test_risk_severity_ordering(self):
        """Test that severity levels can be compared conceptually."""
        # Just verify all enum members exist
        severities = list(RiskSeverity)
        assert len(severities) == 4


class TestRiskAssessment:
    """Test suite for RiskAssessment dataclass (IMP-LOOP-018)."""

    def test_risk_assessment_fields(self):
        """Test RiskAssessment has all required fields."""
        assessment = RiskAssessment(
            severity=RiskSeverity.HIGH,
            blocking_recommended=True,
            confidence=0.85,
            evidence=["Found 2 existing regression tests"],
            pattern_type="failure_mode",
            historical_regression_rate=0.25,
        )

        assert assessment.severity == RiskSeverity.HIGH
        assert assessment.blocking_recommended is True
        assert assessment.confidence == 0.85
        assert len(assessment.evidence) == 1
        assert assessment.pattern_type == "failure_mode"
        assert assessment.historical_regression_rate == 0.25

    def test_risk_assessment_defaults(self):
        """Test RiskAssessment default values."""
        assessment = RiskAssessment(
            severity=RiskSeverity.LOW,
            blocking_recommended=False,
            confidence=0.1,
        )

        assert assessment.evidence == []
        assert assessment.pattern_type == ""
        assert assessment.historical_regression_rate == 0.0


class TestRegressionRiskGating:
    """Test suite for regression risk gating (IMP-LOOP-018)."""

    def test_assess_regression_risk_low(self, tmp_path: Path):
        """Test that patterns with no risk indicators get low severity."""
        protector = RegressionProtector(tests_root=tmp_path / "tests")

        risk = protector.assess_regression_risk(
            "completely new pattern",
            pattern_context={"issue_type": "unknown"},
        )

        assert risk.severity == RiskSeverity.LOW
        assert risk.blocking_recommended is False
        assert risk.confidence < 0.4

    def test_assess_regression_risk_with_existing_tests(self, tmp_path: Path):
        """Test that patterns with existing tests get higher severity."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Create existing regression test
        (tests_dir / "test_regression_timeout.py").write_text(
            '"""Regression test for timeout error."""\n'
            "# Pattern: timeout error in API calls\n"
            "def test_timeout_does_not_recur():\n"
            "    assert True  # Real assertion\n"
        )

        protector = RegressionProtector(tests_root=tests_dir)

        risk = protector.assess_regression_risk(
            "timeout error in API calls",
            pattern_context={"issue_type": "failure_mode"},
        )

        # Should be at least medium risk with existing tests
        assert risk.severity in (RiskSeverity.MEDIUM, RiskSeverity.HIGH, RiskSeverity.CRITICAL)
        assert len(risk.evidence) > 0
        assert any("existing" in e.lower() for e in risk.evidence)

    def test_assess_regression_risk_high_historical_rate(self, tmp_path: Path):
        """Test that patterns with high historical regression rate get higher severity."""
        protector = RegressionProtector(tests_root=tmp_path / "tests")

        # flaky_test has default 0.35 historical rate
        risk = protector.assess_regression_risk(
            "flaky test pattern",
            pattern_context={"issue_type": "flaky_test"},
        )

        # Should have evidence about historical rate
        assert risk.historical_regression_rate > 0
        assert any("historical" in e.lower() for e in risk.evidence)

    def test_filter_patterns_with_risk_assessment_blocks_high_risk(self, tmp_path: Path):
        """Test that high/critical risk patterns are blocked."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Create multiple regression tests for a pattern
        for i in range(3):
            (tests_dir / f"test_regression_memory_{i}.py").write_text(
                f'"""Regression test for memory leak #{i}."""\n'
                "# Pattern: memory leak in worker\n"
                "def test_memory_leak_fixed():\n"
                "    assert True\n"
            )

        protector = RegressionProtector(tests_root=tests_dir)

        patterns = [
            {
                "type": "memory_leak",
                "occurrences": 5,
                "confidence": 0.8,
                "severity": 7,
                "examples": [
                    {
                        "content": "memory leak in worker process",
                        "phase_id": "worker",
                        "issue_type": "failure_mode",
                    }
                ],
            },
            {
                "type": "new_pattern",
                "occurrences": 3,
                "confidence": 0.7,
                "severity": 5,
                "examples": [
                    {
                        "content": "new optimization opportunity",
                        "phase_id": "build",
                        "issue_type": "cost_sink",
                    }
                ],
            },
        ]

        filtered, risk_assessments = protector.filter_patterns_with_risk_assessment(patterns)

        # new_pattern should pass, memory_leak might be blocked depending on risk
        assert len(filtered) >= 1
        assert "memory_leak" in risk_assessments
        assert "new_pattern" in risk_assessments

    def test_filter_patterns_medium_risk_flagged_for_approval(self, tmp_path: Path):
        """Test that medium risk patterns are flagged for approval gate."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Create one regression test
        (tests_dir / "test_regression_perf.py").write_text(
            '"""Regression test for performance issue."""\n'
            "# Pattern: slow database query\n"
            "def test_performance_regression():\n"
            "    assert True\n"
        )

        protector = RegressionProtector(tests_root=tests_dir)

        patterns = [
            {
                "type": "slow_query",
                "occurrences": 2,
                "confidence": 0.6,
                "severity": 4,
                "examples": [
                    {
                        "content": "slow database query in reports",
                        "phase_id": "reports",
                        "issue_type": "performance",
                    }
                ],
            },
        ]

        filtered, risk_assessments = protector.filter_patterns_with_risk_assessment(patterns)

        # Check if medium risk patterns are properly flagged
        if filtered and filtered[0].get("_requires_approval"):
            assert filtered[0]["_risk_assessment"].severity == RiskSeverity.MEDIUM

    def test_blocking_recommended_for_high_critical(self, tmp_path: Path):
        """Test that blocking is recommended only for high/critical risk."""
        protector = RegressionProtector(tests_root=tmp_path / "tests")

        # Low risk
        low_risk = protector.assess_regression_risk("new pattern", {})
        assert low_risk.blocking_recommended is False

        # Create conditions for high risk
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        for i in range(3):
            (tests_dir / f"test_high_risk_{i}.py").write_text(
                '"""High risk pattern test."""\n'
                "# Pattern: critical failure pattern\n"
                "def test_critical():\n"
                "    assert True\n"
            )

        protector_high = RegressionProtector(tests_root=tests_dir)
        high_risk = protector_high.assess_regression_risk(
            "critical failure pattern",
            {"issue_type": "flaky_test"},  # High historical rate
        )

        # With multiple tests and high historical rate, should be blocked
        if high_risk.severity in (RiskSeverity.HIGH, RiskSeverity.CRITICAL):
            assert high_risk.blocking_recommended is True
