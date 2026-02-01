"""Tests for startup configuration validation.

This module tests IMP-SCHEMA-009 - comprehensive startup configuration validation.
Validates that required environment variables, API key formats, and database URLs
are checked early at startup to prevent invalid configuration from causing obscure
runtime errors.
"""

import pytest

from autopack.config import Settings, validate_config, validate_startup_config


class TestRequiredEnvironmentVariables:
    """Test validation of required environment variables."""

    def test_missing_database_url(self, monkeypatch):
        """Validate that missing DATABASE_URL is detected."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL_FILE", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef1234567890abcdef12345678")

        config = Settings()
        errors = validate_config(config)

        assert any("DATABASE_URL is required" in error for error in errors)

    def test_missing_anthropic_api_key(self, monkeypatch):
        """Validate that missing ANTHROPIC_API_KEY is detected."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY_FILE", raising=False)
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")

        config = Settings()
        errors = validate_config(config)

        assert any("ANTHROPIC_API_KEY is required" in error for error in errors)

    def test_database_url_file_accepted(self, monkeypatch, tmp_path):
        """Validate that DATABASE_URL_FILE is accepted as alternative."""
        db_file = tmp_path / "db_url.txt"
        db_file.write_text("postgresql://user:pass@localhost/autopack")

        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("DATABASE_URL_FILE", str(db_file))
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef1234567890abcdef12345678")

        config = Settings()
        errors = validate_config(config)

        # Should not have DATABASE_URL missing error (file exists)
        assert not any("DATABASE_URL is required" in error for error in errors)

    def test_anthropic_api_key_file_accepted(self, monkeypatch, tmp_path):
        """Validate that ANTHROPIC_API_KEY_FILE is accepted as alternative."""
        api_key_file = tmp_path / "api_key.txt"
        api_key_file.write_text("sk-test-1234567890abcdef1234567890abcdef12345678")

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY_FILE", str(api_key_file))
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")

        config = Settings()
        errors = validate_config(config)

        # Should not have ANTHROPIC_API_KEY missing error (file exists)
        assert not any("ANTHROPIC_API_KEY is required" in error for error in errors)


class TestApiKeyFormatValidation:
    """Test validation of API key formats."""

    def test_invalid_anthropic_key_format_missing_prefix(self, monkeypatch):
        """Validate that API key without 'sk-' prefix is rejected."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "invalid-key-without-prefix")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")

        config = Settings()
        errors = validate_config(config)

        assert any("must start with 'sk-'" in error for error in errors)

    def test_invalid_anthropic_key_too_short(self, monkeypatch):
        """Validate that API key that's too short is flagged."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-short")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")

        config = Settings()
        errors = validate_config(config)

        assert any("seems too short" in error for error in errors)

    def test_valid_anthropic_key_format(self, monkeypatch):
        """Validate that properly formatted API key is accepted."""
        valid_key = "sk-test-1234567890abcdef1234567890abcdef12345678"
        monkeypatch.setenv("ANTHROPIC_API_KEY", valid_key)
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")

        config = Settings()
        errors = validate_config(config)

        # Should not have API key format errors
        api_key_errors = [
            e for e in errors if "ANTHROPIC_API_KEY format" in e or "seems too short" in e
        ]
        assert len(api_key_errors) == 0


class TestDatabaseUrlFormatValidation:
    """Test validation of database URL formats."""

    def test_valid_postgresql_url(self, monkeypatch):
        """Validate that PostgreSQL URLs are accepted."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/autopack")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef1234567890abcdef12345678")

        config = Settings()
        errors = validate_config(config)

        # Should not have DATABASE_URL format error
        db_errors = [e for e in errors if "DATABASE_URL format invalid" in e]
        assert len(db_errors) == 0

    def test_valid_mysql_url(self, monkeypatch):
        """Validate that MySQL URLs are accepted."""
        monkeypatch.setenv("DATABASE_URL", "mysql://user:pass@localhost:3306/autopack")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef1234567890abcdef12345678")

        config = Settings()
        errors = validate_config(config)

        db_errors = [e for e in errors if "DATABASE_URL format invalid" in e]
        assert len(db_errors) == 0

    def test_valid_sqlite_url(self, monkeypatch):
        """Validate that SQLite URLs are accepted."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///path/to/db.sqlite3")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef1234567890abcdef12345678")

        config = Settings()
        errors = validate_config(config)

        db_errors = [e for e in errors if "DATABASE_URL format invalid" in e]
        assert len(db_errors) == 0

    def test_invalid_database_url_format(self, monkeypatch):
        """Validate that invalid DATABASE_URL format is rejected."""
        monkeypatch.setenv("DATABASE_URL", "invalid://user:pass@host/db")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef1234567890abcdef12345678")

        config = Settings()
        errors = validate_config(config)

        assert any("DATABASE_URL format invalid" in error for error in errors)


class TestProductionModeValidation:
    """Test production-specific validation requirements."""

    def test_production_requires_api_key(self, monkeypatch):
        """Validate that API key is required in production mode."""
        monkeypatch.setenv("AUTOPACK_ENV", "production")
        monkeypatch.delenv("AUTOPACK_API_KEY", raising=False)
        monkeypatch.delenv("AUTOPACK_API_KEY_FILE", raising=False)
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/autopack")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef1234567890abcdef12345678")

        config = Settings()
        errors = validate_config(config)

        assert any("AUTOPACK_API_KEY is required in production" in error for error in errors)


class TestValidateStartupConfigFunction:
    """Test the validate_startup_config() function behavior."""

    def test_startup_config_success_with_valid_env(self, monkeypatch):
        """Validate that startup succeeds with all required env vars."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef1234567890abcdef12345678")
        monkeypatch.setenv("AUTOPACK_ENV", "development")

        # Should not raise
        try:
            validate_startup_config()
        except SystemExit:
            pytest.fail("validate_startup_config() should not raise SystemExit with valid config")

    def test_startup_config_failure_with_missing_vars(self, monkeypatch):
        """Validate that startup fails with missing required env vars."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL_FILE", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef1234567890abcdef12345678")

        with pytest.raises(SystemExit):
            validate_startup_config()

    def test_startup_config_failure_with_invalid_format(self, monkeypatch):
        """Validate that startup fails with invalid config formats."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "invalid-key")  # Missing sk- prefix

        with pytest.raises(SystemExit):
            validate_startup_config()


class TestNumericConfigValidation:
    """Test validation of numeric configuration values."""

    def test_run_token_cap_minimum(self, monkeypatch):
        """Validate that run_token_cap has a minimum."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef1234567890abcdef12345678")
        monkeypatch.setenv("AUTOPACK_RUN_TOKEN_CAP", "5000000")  # Valid value

        config = Settings()
        errors = validate_config(config)

        # Should not have errors with valid config
        assert len(errors) == 0

    def test_phase_timeout_minutes_minimum(self, monkeypatch):
        """Validate that phase_timeout_minutes has a minimum via Pydantic validation."""
        from pydantic_core import ValidationError

        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef1234567890abcdef12345678")
        monkeypatch.setenv("AUTOPACK_PHASE_TIMEOUT_MINUTES", "0")  # Invalid

        # Pydantic should reject during Settings initialization
        with pytest.raises(ValidationError):
            Settings()

    def test_valid_numeric_config(self, monkeypatch):
        """Validate that valid numeric config is accepted."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef1234567890abcdef12345678")
        monkeypatch.setenv("AUTOPACK_RUN_TOKEN_CAP", "5000000")
        monkeypatch.setenv("AUTOPACK_PHASE_TIMEOUT_MINUTES", "15")

        config = Settings()
        errors = validate_config(config)

        # Filter out non-numeric errors for this test
        numeric_errors = [
            e
            for e in errors
            if any(
                x in e
                for x in ["run_token_cap", "phase_timeout_minutes", "phase_token_cap_default"]
            )
        ]
        assert len(numeric_errors) == 0


class TestValidationErrorMessages:
    """Test that error messages are clear and actionable."""

    def test_missing_database_url_has_guidance(self, monkeypatch):
        """Validate that missing DATABASE_URL error includes guidance."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL_FILE", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-1234567890abcdef1234567890abcdef12345678")

        config = Settings()
        errors = validate_config(config)

        missing_db_error = [e for e in errors if "DATABASE_URL is required" in e][0]
        assert "DATABASE_URL_FILE" in missing_db_error  # Mention the _FILE alternative

    def test_invalid_api_key_format_has_guidance(self, monkeypatch):
        """Validate that invalid API key error includes guidance."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "bad-key")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")

        config = Settings()
        errors = validate_config(config)

        format_error = [e for e in errors if "ANTHROPIC_API_KEY format invalid" in e][0]
        assert "sk-" in format_error  # Mention the expected prefix
