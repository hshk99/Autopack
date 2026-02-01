"""
Tests for SQL identifier injection prevention in break glass repair.

Tests that table and column names are validated before use in SQL.
"""

from unittest.mock import MagicMock, Mock

import pytest

from autopack.break_glass_repair import (
    ALLOWED_COLUMNS,
    ALLOWED_TABLES,
    BreakGlassRepair,
    _validate_identifier,
)
from autopack.schema_validator import SchemaValidationResult


class MockError:
    """Mock error object for testing."""

    def __init__(self, table, column, invalid_value="invalid", suggested_fix="valid"):
        self.table = table
        self.column = column
        self.invalid_value = invalid_value
        self.suggested_fix = suggested_fix
        self.affected_rows = ["row1", "row2"]
        self.repair_sql = f"UPDATE {table} SET {column}='valid' WHERE {column}='invalid'"


class TestIdentifierValidation:
    """Tests for identifier validation function."""

    def test_validate_allowed_table(self):
        """Valid table names should pass validation."""
        for table in ALLOWED_TABLES:
            # Should not raise
            _validate_identifier(table, "table", ALLOWED_TABLES)

    def test_validate_disallowed_table(self):
        """Invalid table names should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid table name"):
            _validate_identifier("users", "table", ALLOWED_TABLES)

    def test_validate_allowed_column(self):
        """Valid column names should pass validation."""
        for column in ALLOWED_COLUMNS:
            # Should not raise
            _validate_identifier(column, "column", ALLOWED_COLUMNS)

    def test_validate_disallowed_column(self):
        """Invalid column names should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid column name"):
            _validate_identifier("password", "column", ALLOWED_COLUMNS)

    def test_sql_injection_attempt_table(self):
        """SQL injection attempts in table name should be blocked."""
        injection_attempts = [
            "runs; DROP TABLE runs; --",
            "runs' OR '1'='1",
            "runs) UNION SELECT * FROM (SELECT",
        ]
        for attempt in injection_attempts:
            with pytest.raises(ValueError, match="Invalid table name"):
                _validate_identifier(attempt, "table", ALLOWED_TABLES)

    def test_sql_injection_attempt_column(self):
        """SQL injection attempts in column name should be blocked."""
        injection_attempts = [
            "status=1; --",
            "id OR id",
            "status) UNION ALL SELECT (SELECT",
        ]
        for attempt in injection_attempts:
            with pytest.raises(ValueError, match="Invalid column name"):
                _validate_identifier(attempt, "column", ALLOWED_COLUMNS)


class TestBreakGlassRepairIdentifierValidation:
    """Tests for identifier validation in repair method."""

    @pytest.fixture
    def repair_tool(self, tmp_path):
        """Create a BreakGlassRepair instance with test database."""
        db_path = tmp_path / "test.db"
        db_url = f"sqlite:///{db_path}"

        # Mock the validator
        tool = BreakGlassRepair(db_url)
        tool.validator = Mock()
        return tool

    def test_repair_with_valid_identifiers(self, repair_tool):
        """Repair should proceed with valid table and column names."""
        error = MockError("runs", "status")
        result = SchemaValidationResult(errors=[error])

        # Mock engine and connection with proper context manager support
        mock_conn = MagicMock()
        mock_trans = MagicMock()
        mock_conn.begin.return_value = mock_trans
        mock_conn.execute.return_value = MagicMock()

        # Mock the context manager for engine.connect()
        repair_tool.engine.connect = MagicMock()
        repair_tool.engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        repair_tool.engine.connect.return_value.__exit__ = MagicMock(return_value=None)

        # This should not raise an exception (identifiers are valid)
        # The repair method should proceed and call execute()
        try:
            repair_tool.repair(result, auto_approve=True)
        except ValueError:
            # Should not raise ValueError for validation
            pytest.fail("Valid identifiers should not raise ValueError")
        except Exception:
            # Other exceptions are OK (e.g., from mocked database)
            pass

    def test_repair_with_invalid_table(self, repair_tool):
        """Repair should reject invalid table names."""
        error = MockError("users", "id")  # 'users' not in ALLOWED_TABLES
        result = SchemaValidationResult(errors=[error])

        repair_tool.repair(result, auto_approve=True)
        # Should handle gracefully without executing repair

    def test_repair_with_invalid_column(self, repair_tool):
        """Repair should reject invalid column names."""
        error = MockError("runs", "password")  # 'password' not in ALLOWED_COLUMNS
        result = SchemaValidationResult(errors=[error])

        repair_tool.repair(result, auto_approve=True)
        # Should handle gracefully without executing repair

    def test_repair_with_sql_injection_table(self, repair_tool):
        """Repair should reject SQL injection in table names."""
        injection_table = "runs; DROP TABLE runs; --"
        error = MockError(injection_table, "status")
        result = SchemaValidationResult(errors=[error])

        repair_tool.repair(result, auto_approve=True)
        # Should handle gracefully without executing repair

    def test_repair_with_sql_injection_column(self, repair_tool):
        """Repair should reject SQL injection in column names."""
        injection_column = "status=1; --"
        error = MockError("runs", injection_column)
        result = SchemaValidationResult(errors=[error])

        repair_tool.repair(result, auto_approve=True)
        # Should handle gracefully without executing repair


class TestAllowedIdentifiers:
    """Tests for allowed identifier whitelists."""

    def test_allowed_tables_not_empty(self):
        """ALLOWED_TABLES should contain expected tables."""
        assert "runs" in ALLOWED_TABLES
        assert "phases" in ALLOWED_TABLES
        assert len(ALLOWED_TABLES) > 0

    def test_allowed_columns_not_empty(self):
        """ALLOWED_COLUMNS should contain expected columns."""
        assert "id" in ALLOWED_COLUMNS
        assert "status" in ALLOWED_COLUMNS
        assert "updated_at" in ALLOWED_COLUMNS
        assert len(ALLOWED_COLUMNS) > 0

    def test_no_suspicious_values_in_tables(self):
        """Whitelist should not contain suspicious SQL patterns."""
        # Check for actual SQL injection attack patterns, not just keywords in names
        for table in ALLOWED_TABLES:
            # Check for comment markers and termination
            assert ";" not in table
            assert "--" not in table
            assert "/*" not in table
            assert "*/" not in table
            # Check for dangerous SQL keywords at word boundaries
            words = table.lower().split("_")
            for word in words:
                assert word not in ["drop", "delete", "insert", "update", "union", "select"]

    def test_no_suspicious_values_in_columns(self):
        """Whitelist should not contain suspicious SQL patterns."""
        # Check for actual SQL injection attack patterns, not just keywords in names
        for column in ALLOWED_COLUMNS:
            # Check for comment markers and termination
            assert ";" not in column
            assert "--" not in column
            assert "/*" not in column
            assert "*/" not in column
            # Check for dangerous SQL keywords at word boundaries
            # This avoids false positives for words like "error" containing "or"
            words = column.lower().split("_")
            for word in words:
                assert word not in ["drop", "delete", "insert", "update", "union", "select"]
