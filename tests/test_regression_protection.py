"""Tests for ROAD-I Regression Protection System."""

import pytest
from pathlib import Path

from autopack.roadi import RegressionProtector, RegressionTest, ProtectionResult


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
            '"""Tests for TIMEOUT ERROR pattern."""\n' "def test_timeout():\n" "    pass\n"
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
            '"""Tests for memory leak pattern."""\n' "def test_memory_leak():\n" "    pass\n"
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
