"""Tests for configuration validation."""

import pytest

from autopack.config import Config, ConfigError


class TestConfigValidation:
    """Test suite for Config class validation."""

    def test_config_fails_without_database_url(self, monkeypatch):
        """Verify config validation fails when DATABASE_URL is missing."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")

        with pytest.raises(ConfigError, match="DATABASE_URL is required"):
            Config()

    def test_config_fails_without_redis_url(self, monkeypatch):
        """Verify config validation fails when REDIS_URL is missing."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")

        with pytest.raises(ConfigError, match="REDIS_URL is required"):
            Config()

    def test_config_fails_without_qdrant_url(self, monkeypatch):
        """Verify config validation fails when QDRANT_URL is missing."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.delenv("QDRANT_URL", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")

        with pytest.raises(ConfigError, match="QDRANT_URL is required"):
            Config()

    def test_config_fails_without_anthropic_api_key(self, monkeypatch):
        """Verify config validation fails when ANTHROPIC_API_KEY is missing."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY is required"):
            Config()

    def test_config_fails_with_invalid_log_level(self, monkeypatch):
        """Verify config validation fails when LOG_LEVEL is invalid."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
        monkeypatch.setenv("LOG_LEVEL", "INVALID")

        with pytest.raises(ConfigError, match="Invalid LOG_LEVEL"):
            Config()

    def test_config_validates_port_range_too_high(self, monkeypatch):
        """Verify port validation fails when port is too high."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
        monkeypatch.setenv("PORT", "99999")

        with pytest.raises(ConfigError, match="Invalid PORT"):
            Config()

    def test_config_validates_port_range_too_low(self, monkeypatch):
        """Verify port validation fails when port is too low."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
        monkeypatch.setenv("PORT", "0")

        with pytest.raises(ConfigError, match="Invalid PORT"):
            Config()

    def test_config_validates_port_not_integer(self, monkeypatch):
        """Verify port validation fails when port is not an integer."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
        monkeypatch.setenv("PORT", "not-a-number")

        with pytest.raises(ConfigError, match="Invalid PORT.*must be integer"):
            Config()

    def test_config_succeeds_with_valid_vars(self, monkeypatch):
        """Verify config succeeds with all required vars."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")

        config = Config()  # Should not raise
        assert config.port == 8000
        assert config.log_level == "INFO"

    def test_config_accepts_valid_log_levels(self, monkeypatch):
        """Verify config accepts all valid log levels."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")

        for level in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            monkeypatch.setenv("LOG_LEVEL", level)
            config = Config()
            assert config.log_level == level

    def test_config_accepts_custom_port(self, monkeypatch):
        """Verify config accepts custom port within valid range."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")
        monkeypatch.setenv("PORT", "9000")

        config = Config()
        assert config.port == 9000

    def test_config_accepts_port_1_and_65535(self, monkeypatch):
        """Verify config accepts port boundaries (1 and 65535)."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")

        # Test port 1
        monkeypatch.setenv("PORT", "1")
        config = Config()
        assert config.port == 1

        # Test port 65535
        monkeypatch.setenv("PORT", "65535")
        config = Config()
        assert config.port == 65535

    def test_config_error_message_includes_count(self, monkeypatch):
        """Verify error message includes count of configuration errors."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")

        with pytest.raises(ConfigError, match="2 configuration error"):
            Config()

    def test_config_stderr_output_on_error(self, monkeypatch, capsys):
        """Verify error messages are printed to stderr."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379")
        monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-123")

        with pytest.raises(ConfigError):
            Config()

        captured = capsys.readouterr()
        assert "Configuration errors detected" in captured.err
        assert "DATABASE_URL is required" in captured.err


class TestSettingsDefaults:
    """Test suite for Settings class defaults (IMP-AUTO-001)."""

    def test_sot_retrieval_enabled_by_default(self):
        """Verify SOT memory retrieval is enabled by default.

        IMP-AUTO-001: Enable memory retrieval by default to improve
        learning effectiveness. Each execution should start with
        accumulated knowledge from previous runs.
        """
        from autopack.config import Settings

        settings = Settings()
        assert settings.autopack_sot_retrieval_enabled is True

    def test_sot_memory_indexing_enabled_by_default(self):
        """Verify SOT memory indexing is enabled by default.

        Memory indexing must be enabled for retrieval to work.
        """
        from autopack.config import Settings

        settings = Settings()
        assert settings.autopack_enable_sot_memory_indexing is True

    def test_sot_retrieval_can_be_disabled_via_env(self, monkeypatch):
        """Verify SOT retrieval can be disabled via environment variable."""
        monkeypatch.setenv("AUTOPACK_SOT_RETRIEVAL_ENABLED", "false")

        from autopack.config import Settings

        # Create fresh settings instance
        settings = Settings()
        assert settings.autopack_sot_retrieval_enabled is False


class TestTaskGenerationDefaults:
    """Test suite for task generation configuration defaults (IMP-LOOP-007)."""

    def test_task_generation_enabled_by_default(self):
        """Verify task generation is enabled by default.

        IMP-LOOP-007: Enable task generation by default to enable the
        self-improvement loop. Task generation allows automatic creation
        of improvement tasks from telemetry insights.
        """
        from autopack.config import Settings

        settings = Settings()
        assert settings.task_generation_enabled is True

    def test_task_generation_auto_execute_enabled_by_default(self):
        """Verify task auto-execution is enabled by default.

        IMP-LOOP-007: Auto-execute generated tasks for continuous improvement.
        """
        from autopack.config import Settings

        settings = Settings()
        assert settings.task_generation_auto_execute is True

    def test_task_generation_can_be_disabled_via_env(self, monkeypatch):
        """Verify task generation can be disabled via environment variable."""
        monkeypatch.setenv("AUTOPACK_TASK_GENERATION_ENABLED", "false")

        from autopack.config import Settings

        settings = Settings()
        assert settings.task_generation_enabled is False

    def test_task_generation_auto_execute_can_be_disabled_via_env(self, monkeypatch):
        """Verify task auto-execution can be disabled via environment variable."""
        monkeypatch.setenv("AUTOPACK_TASK_GENERATION_AUTO_EXECUTE", "false")

        from autopack.config import Settings

        settings = Settings()
        assert settings.task_generation_auto_execute is False

    def test_task_generation_property_returns_dict(self):
        """Verify task_generation property returns expected dict structure."""
        from autopack.config import Settings

        settings = Settings()
        task_gen = settings.task_generation

        assert isinstance(task_gen, dict)
        assert task_gen["enabled"] is True
        assert task_gen["max_tasks_per_run"] == 10
        assert task_gen["min_confidence"] == 0.7
        assert task_gen["auto_execute"]["enabled"] is True

    def test_task_generation_max_tasks_default(self):
        """Verify default max tasks per run."""
        from autopack.config import Settings

        settings = Settings()
        assert settings.task_generation_max_tasks_per_run == 10

    def test_task_generation_min_confidence_default(self):
        """Verify default minimum confidence threshold."""
        from autopack.config import Settings

        settings = Settings()
        assert settings.task_generation_min_confidence == 0.7
