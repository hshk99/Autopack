"""Tests for health check system (PR-05 correctness fixes).

Validates:
- API key check requires at least one key (not all keys)
- Database check uses correct backend (Postgres vs SQLite)
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from autopack.health_checks import HealthChecker


class TestApiKeyCheck:
    """Test API key health check (PR-05: at-least-one semantics)."""

    @pytest.fixture
    def checker(self, tmp_path: Path) -> HealthChecker:
        """Create a HealthChecker instance."""
        return HealthChecker(workspace_path=tmp_path, config_dir=tmp_path / "config")

    def test_no_keys_fails(self, checker: HealthChecker):
        """No API keys should fail the check."""
        with patch.dict(os.environ, {}, clear=True):
            name, passed, message = checker.check_api_keys()

        assert passed is False
        assert "No provider API keys found" in message

    def test_single_anthropic_key_passes(self, checker: HealthChecker):
        """Single ANTHROPIC key should pass."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=True):
            name, passed, message = checker.check_api_keys()

        assert passed is True
        assert "ANTHROPIC_API_KEY" in message

    def test_single_openai_key_passes(self, checker: HealthChecker):
        """Single OPENAI key should pass."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True):
            name, passed, message = checker.check_api_keys()

        assert passed is True
        assert "OPENAI_API_KEY" in message

    def test_single_google_key_passes(self, checker: HealthChecker):
        """Single GOOGLE key should pass."""
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}, clear=True):
            name, passed, message = checker.check_api_keys()

        assert passed is True
        assert "GOOGLE_API_KEY" in message

    def test_multiple_keys_lists_all(self, checker: HealthChecker):
        """Multiple keys should all be listed in message."""
        with patch.dict(
            os.environ,
            {"ANTHROPIC_API_KEY": "sk-a", "OPENAI_API_KEY": "sk-o"},
            clear=True,
        ):
            name, passed, message = checker.check_api_keys()

        assert passed is True
        assert "ANTHROPIC_API_KEY" in message
        assert "OPENAI_API_KEY" in message


class TestDatabaseCheck:
    """Test database health check (PR-05: backend-aware routing)."""

    @pytest.fixture
    def checker(self, tmp_path: Path) -> HealthChecker:
        """Create a HealthChecker instance."""
        return HealthChecker(workspace_path=tmp_path, config_dir=tmp_path / "config")

    def test_sqlite_check_when_no_database_url(self, checker: HealthChecker, tmp_path: Path):
        """Without DATABASE_URL, should check SQLite file."""
        with patch.dict(os.environ, {}, clear=True):
            name, passed, message = checker.check_database()

        assert passed is False
        assert "SQLite database file not found" in message

    def test_sqlite_check_passes_when_file_exists(self, checker: HealthChecker, tmp_path: Path):
        """SQLite check should pass when file exists."""
        db_path = tmp_path / "autopack.db"
        db_path.touch()

        with patch.dict(os.environ, {}, clear=True):
            name, passed, message = checker.check_database()

        assert passed is True
        assert "SQLite database accessible" in message

    def test_postgres_check_when_postgresql_url(self, checker: HealthChecker):
        """With postgresql:// URL, should check Postgres connectivity."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:pass@localhost:5432/db"},
            clear=True,
        ):
            name, passed, message = checker.check_database()

        # Will fail (no Postgres running) but should mention "Postgres"
        assert "Postgres" in message

    def test_postgres_check_when_postgres_url(self, checker: HealthChecker):
        """With postgres:// URL (alternate scheme), should check Postgres."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgres://user:pass@localhost:5432/db"},
            clear=True,
        ):
            name, passed, message = checker.check_database()

        assert "Postgres" in message

    def test_postgres_url_parsing_with_port(self, checker: HealthChecker):
        """Postgres URL parsing should extract host and port."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:pass@myhost:5433/mydb"},
            clear=True,
        ):
            name, passed, message = checker.check_database()

        assert "myhost:5433" in message

    def test_postgres_url_parsing_default_port(self, checker: HealthChecker):
        """Postgres URL without port should default to 5432."""
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://user:pass@myhost/mydb"},
            clear=True,
        ):
            name, passed, message = checker.check_database()

        assert "myhost:5432" in message
