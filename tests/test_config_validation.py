"""Tests for IMP-OPS-013: Configuration validation at startup.

Verifies that validate_config() catches invalid configuration values
with clear error messages instead of obscure runtime errors.
"""

import os
from unittest.mock import patch

import pytest

from autopack.config import Settings, validate_config, validate_startup_config


def create_settings_with_overrides(**overrides) -> Settings:
    """Create a Settings instance with specified overrides.

    Uses model_construct to bypass Pydantic validation and allow
    setting arbitrary values for testing validation logic.
    """
    # Start with default values
    defaults = {
        "autopack_env": "development",
        "database_url": "postgresql://autopack:autopack@localhost:5432/autopack",
        "autonomous_runs_dir": ".autonomous_runs",
        "repo_path": "/workspace",
        "run_token_cap": 5_000_000,
        "run_max_phases": 25,
        "run_max_duration_minutes": 120,
        "phase_timeout_minutes": 15,
        "phase_token_cap_default": 500_000,
        "phase_token_cap_multipliers_str": "research:1.5,implementation:1.0,verification:0.5,audit:0.3",
        "autopilot_enabled": True,
        "autopilot_gap_scan_frequency": 5,
        "autopilot_max_proposals_per_session": 3,
        "db_pool_monitoring_enabled": True,
        "executor_rollback_enabled": False,
        "artifact_history_pack_enabled": False,
        "db_bootstrap_enabled": False,
        "artifact_history_pack_max_phases": 5,
        "artifact_history_pack_max_tiers": 3,
        "artifact_substitute_sot_docs": False,
        "artifact_extended_contexts_enabled": False,
        "embedding_cache_max_calls_per_phase": 100,
        "context_budget_tokens": 100_000,
        "autopack_enable_sot_memory_indexing": True,
        "autopack_sot_retrieval_enabled": True,
        "autopack_sot_retrieval_max_chars": 4000,
        "autopack_sot_retrieval_top_k": 3,
        "autopack_sot_chunk_max_chars": 1200,
        "autopack_sot_chunk_overlap_chars": 150,
        "jwt_private_key": "",
        "jwt_public_key": "",
        "jwt_algorithm": "RS256",
        "jwt_issuer": "autopack",
        "jwt_audience": "autopack-api",
        "access_token_expire_minutes": 1440,
        "artifact_read_size_cap_bytes": 1_048_576,
        "artifact_redaction_enabled": False,
        "health_check_timeout": 2.0,
        "approval_check_interval": 60.0,
        "db_operation_timeout": 30.0,
        "allowed_external_hosts": [],
        "dual_audit_enabled": True,
        "dual_audit_secondary_model": None,
        "sot_runtime_enforcement_enabled": True,
        "sot_drift_blocks_execution": False,
        "autopack_bind_address": "127.0.0.1",
        "autopack_allow_non_local": False,
        "task_generation_enabled": True,
        "task_generation_max_tasks_per_run": 10,
        "task_generation_min_confidence": 0.7,
        "task_generation_auto_execute": True,
    }
    defaults.update(overrides)
    return Settings.model_construct(**defaults)


class TestValidateConfig:
    """Tests for the validate_config function."""

    def test_valid_config_returns_empty_list(self):
        """Default settings should pass validation."""
        config = create_settings_with_overrides()
        errors = validate_config(config)
        assert errors == []

    def test_invalid_run_token_cap(self):
        """run_token_cap < 1000 should fail validation."""
        config = create_settings_with_overrides(run_token_cap=500)
        errors = validate_config(config)
        assert any("run_token_cap must be >= 1000" in e for e in errors)

    def test_invalid_phase_token_cap_default(self):
        """phase_token_cap_default < 100 should fail validation."""
        config = create_settings_with_overrides(phase_token_cap_default=50)
        errors = validate_config(config)
        assert any("phase_token_cap_default must be >= 100" in e for e in errors)

    def test_invalid_context_budget_tokens(self):
        """context_budget_tokens < 1000 should fail validation."""
        config = create_settings_with_overrides(context_budget_tokens=500)
        errors = validate_config(config)
        assert any("context_budget_tokens must be >= 1000" in e for e in errors)

    def test_invalid_run_max_phases(self):
        """run_max_phases < 1 should fail validation."""
        config = create_settings_with_overrides(run_max_phases=0)
        errors = validate_config(config)
        assert any("run_max_phases must be >= 1" in e for e in errors)

    def test_invalid_run_max_duration_minutes(self):
        """run_max_duration_minutes < 1 should fail validation."""
        config = create_settings_with_overrides(run_max_duration_minutes=0)
        errors = validate_config(config)
        assert any("run_max_duration_minutes must be >= 1" in e for e in errors)

    def test_invalid_phase_timeout_minutes(self):
        """phase_timeout_minutes < 1 should fail validation."""
        config = create_settings_with_overrides(phase_timeout_minutes=0)
        errors = validate_config(config)
        assert any("phase_timeout_minutes must be >= 1" in e for e in errors)

    def test_invalid_health_check_timeout(self):
        """health_check_timeout <= 0 should fail validation."""
        config = create_settings_with_overrides(health_check_timeout=0)
        errors = validate_config(config)
        assert any("health_check_timeout must be > 0" in e for e in errors)

    def test_invalid_approval_check_interval(self):
        """approval_check_interval <= 0 should fail validation."""
        config = create_settings_with_overrides(approval_check_interval=0)
        errors = validate_config(config)
        assert any("approval_check_interval must be > 0" in e for e in errors)

    def test_invalid_db_operation_timeout(self):
        """db_operation_timeout <= 0 should fail validation."""
        config = create_settings_with_overrides(db_operation_timeout=-1)
        errors = validate_config(config)
        assert any("db_operation_timeout must be > 0" in e for e in errors)

    def test_invalid_sot_retrieval_max_chars(self):
        """autopack_sot_retrieval_max_chars < 100 should fail validation."""
        config = create_settings_with_overrides(autopack_sot_retrieval_max_chars=50)
        errors = validate_config(config)
        assert any("autopack_sot_retrieval_max_chars must be >= 100" in e for e in errors)

    def test_invalid_sot_retrieval_top_k(self):
        """autopack_sot_retrieval_top_k < 1 should fail validation."""
        config = create_settings_with_overrides(autopack_sot_retrieval_top_k=0)
        errors = validate_config(config)
        assert any("autopack_sot_retrieval_top_k must be >= 1" in e for e in errors)

    def test_invalid_sot_chunk_max_chars(self):
        """autopack_sot_chunk_max_chars < 100 should fail validation."""
        config = create_settings_with_overrides(autopack_sot_chunk_max_chars=50)
        errors = validate_config(config)
        assert any("autopack_sot_chunk_max_chars must be >= 100" in e for e in errors)

    def test_invalid_autopilot_gap_scan_frequency(self):
        """autopilot_gap_scan_frequency < 1 should fail validation."""
        config = create_settings_with_overrides(autopilot_gap_scan_frequency=0)
        errors = validate_config(config)
        assert any("autopilot_gap_scan_frequency must be >= 1" in e for e in errors)

    def test_invalid_autopilot_max_proposals(self):
        """autopilot_max_proposals_per_session < 0 should fail validation."""
        config = create_settings_with_overrides(autopilot_max_proposals_per_session=-1)
        errors = validate_config(config)
        assert any("autopilot_max_proposals_per_session must be >= 0" in e for e in errors)

    def test_invalid_task_generation_max_tasks(self):
        """task_generation_max_tasks_per_run < 0 should fail validation."""
        config = create_settings_with_overrides(task_generation_max_tasks_per_run=-1)
        errors = validate_config(config)
        assert any("task_generation_max_tasks_per_run must be >= 0" in e for e in errors)

    def test_invalid_task_generation_min_confidence_high(self):
        """task_generation_min_confidence > 1.0 should fail validation."""
        config = create_settings_with_overrides(task_generation_min_confidence=1.5)
        errors = validate_config(config)
        assert any(
            "task_generation_min_confidence must be between 0.0 and 1.0" in e for e in errors
        )

    def test_invalid_task_generation_min_confidence_low(self):
        """task_generation_min_confidence < 0.0 should fail validation."""
        config = create_settings_with_overrides(task_generation_min_confidence=-0.5)
        errors = validate_config(config)
        assert any(
            "task_generation_min_confidence must be between 0.0 and 1.0" in e for e in errors
        )

    def test_invalid_access_token_expire_minutes(self):
        """access_token_expire_minutes < 1 should fail validation."""
        config = create_settings_with_overrides(access_token_expire_minutes=0)
        errors = validate_config(config)
        assert any("access_token_expire_minutes must be >= 1" in e for e in errors)

    def test_production_requires_api_key(self):
        """Production mode without API key should fail validation."""
        config = create_settings_with_overrides(autopack_env="production")

        # Unset API key env vars
        with patch.dict(os.environ, {}, clear=True):
            errors = validate_config(config)
            assert any("AUTOPACK_API_KEY is required in production mode" in e for e in errors)

    def test_production_with_api_key_passes(self):
        """Production mode with API key should pass validation."""
        config = create_settings_with_overrides(autopack_env="production")

        with patch.dict(os.environ, {"AUTOPACK_API_KEY": "test-key"}, clear=True):
            errors = validate_config(config)
            # Should not have the API key error
            assert not any("AUTOPACK_API_KEY is required" in e for e in errors)

    def test_production_with_api_key_file_passes(self):
        """Production mode with API key file should pass validation."""
        config = create_settings_with_overrides(autopack_env="production")

        with patch.dict(os.environ, {"AUTOPACK_API_KEY_FILE": "/path/to/key"}, clear=True):
            errors = validate_config(config)
            # Should not have the API key error
            assert not any("AUTOPACK_API_KEY is required" in e for e in errors)

    def test_development_mode_does_not_require_api_key(self):
        """Development mode should not require API key."""
        config = create_settings_with_overrides(autopack_env="development")

        with patch.dict(os.environ, {}, clear=True):
            errors = validate_config(config)
            assert not any("AUTOPACK_API_KEY is required" in e for e in errors)

    def test_multiple_validation_errors(self):
        """Multiple invalid values should return multiple errors."""
        config = create_settings_with_overrides(
            run_token_cap=500,
            phase_token_cap_default=50,
            run_max_phases=0,
        )
        errors = validate_config(config)
        assert len(errors) >= 3


class TestValidateStartupConfig:
    """Tests for the validate_startup_config function."""

    def test_valid_config_logs_success(self, caplog):
        """Valid config should log success message."""
        import logging

        with caplog.at_level(logging.INFO):
            validate_startup_config()
        assert "Configuration validated successfully" in caplog.text

    def test_invalid_config_raises_system_exit(self):
        """Invalid config should raise SystemExit."""
        from autopack.config import settings

        # Temporarily make config invalid
        original_value = settings.run_token_cap
        try:
            # Use object.__setattr__ to bypass Pydantic's setter
            object.__setattr__(settings, "run_token_cap", 100)
            with pytest.raises(SystemExit) as exc_info:
                validate_startup_config()
            assert "Invalid configuration" in str(exc_info.value)
        finally:
            object.__setattr__(settings, "run_token_cap", original_value)
