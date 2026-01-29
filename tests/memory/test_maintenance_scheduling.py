"""Tests for automated memory maintenance scheduling (IMP-LOOP-017).

Tests cover:
- is_maintenance_due() time-based logic
- run_maintenance_if_due() execution flow
- Timestamp file persistence
- Config loading for maintenance settings
- Integration with autonomous loop
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from autopack.memory.maintenance import (
    _get_last_maintenance_time,
    _load_maintenance_config,
    _update_last_maintenance_time,
    is_maintenance_due,
    run_maintenance_if_due,
)


@pytest.fixture
def temp_timestamp_file(tmp_path, monkeypatch):
    """Use a temporary timestamp file for testing."""
    temp_file = tmp_path / ".last_maintenance"
    monkeypatch.setattr("autopack.memory.maintenance.MAINTENANCE_TIMESTAMP_FILE", temp_file)
    return temp_file


@pytest.fixture
def mock_maintenance_config():
    """Mock the maintenance config loading."""
    config = {
        "auto_maintenance_enabled": True,
        "maintenance_interval_hours": 24,
        "max_age_days": 90,
        "prune_threshold": 1000,
        "planning_keep_versions": 3,
    }
    with patch("autopack.memory.maintenance._load_maintenance_config", return_value=config):
        yield config


class TestMaintenanceConfigLoading:
    """Tests for maintenance config loading."""

    def test_load_maintenance_config_returns_defaults(self):
        """Verify default config values when no config file exists."""
        with patch("autopack.memory.maintenance._load_memory_config", return_value={}):
            config = _load_maintenance_config()

            assert config["auto_maintenance_enabled"] is True
            assert config["maintenance_interval_hours"] == 24
            assert config["max_age_days"] == 30  # DEFAULT_TTL_DAYS
            assert config["prune_threshold"] == 1000
            assert config["planning_keep_versions"] == 3

    def test_load_maintenance_config_uses_yaml_values(self):
        """Verify config values are loaded from memory.yaml."""
        yaml_config = {
            "maintenance": {
                "auto_maintenance_enabled": False,
                "maintenance_interval_hours": 12,
                "max_age_days": 60,
                "prune_threshold": 500,
                "planning_keep_versions": 5,
            }
        }
        with patch("autopack.memory.maintenance._load_memory_config", return_value=yaml_config):
            config = _load_maintenance_config()

            assert config["auto_maintenance_enabled"] is False
            assert config["maintenance_interval_hours"] == 12
            assert config["max_age_days"] == 60
            assert config["prune_threshold"] == 500
            assert config["planning_keep_versions"] == 5


class TestTimestampPersistence:
    """Tests for maintenance timestamp file operations."""

    def test_get_last_maintenance_time_returns_none_when_no_file(self, temp_timestamp_file):
        """Verify None returned when timestamp file doesn't exist."""
        assert not temp_timestamp_file.exists()
        result = _get_last_maintenance_time()
        assert result is None

    def test_update_and_get_last_maintenance_time(self, temp_timestamp_file):
        """Verify timestamp can be written and read back."""
        _update_last_maintenance_time()

        result = _get_last_maintenance_time()

        assert result is not None
        assert isinstance(result, datetime)
        # Should be within last few seconds
        assert (datetime.now(timezone.utc) - result).total_seconds() < 5

    def test_get_last_maintenance_time_handles_invalid_content(self, temp_timestamp_file):
        """Verify graceful handling of corrupted timestamp file."""
        temp_timestamp_file.parent.mkdir(parents=True, exist_ok=True)
        temp_timestamp_file.write_text("not-a-valid-timestamp")

        result = _get_last_maintenance_time()

        assert result is None


class TestIsMaintenanceDue:
    """Tests for is_maintenance_due() logic."""

    def test_maintenance_due_when_never_run(self, temp_timestamp_file, mock_maintenance_config):
        """Verify maintenance is due when never run before."""
        assert not temp_timestamp_file.exists()

        result = is_maintenance_due()

        assert result is True

    def test_maintenance_not_due_when_recently_run(
        self, temp_timestamp_file, mock_maintenance_config
    ):
        """Verify maintenance is not due when recently run."""
        _update_last_maintenance_time()

        result = is_maintenance_due()

        assert result is False

    def test_maintenance_due_when_interval_elapsed(self, temp_timestamp_file):
        """Verify maintenance is due after interval has elapsed."""
        # Write timestamp 25 hours ago
        old_time = datetime.now(timezone.utc) - timedelta(hours=25)
        temp_timestamp_file.parent.mkdir(parents=True, exist_ok=True)
        temp_timestamp_file.write_text(old_time.isoformat())

        config = {
            "auto_maintenance_enabled": True,
            "maintenance_interval_hours": 24,
            "max_age_days": 90,
            "prune_threshold": 1000,
            "planning_keep_versions": 3,
        }
        with patch("autopack.memory.maintenance._load_maintenance_config", return_value=config):
            result = is_maintenance_due()

        assert result is True

    def test_maintenance_not_due_when_disabled(self, temp_timestamp_file):
        """Verify maintenance is never due when disabled in config."""
        config = {
            "auto_maintenance_enabled": False,
            "maintenance_interval_hours": 24,
            "max_age_days": 90,
            "prune_threshold": 1000,
            "planning_keep_versions": 3,
        }
        with patch("autopack.memory.maintenance._load_maintenance_config", return_value=config):
            result = is_maintenance_due()

        assert result is False

    def test_custom_interval_override(self, temp_timestamp_file):
        """Verify interval_hours parameter overrides config."""
        # Write timestamp 2 hours ago
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        temp_timestamp_file.parent.mkdir(parents=True, exist_ok=True)
        temp_timestamp_file.write_text(old_time.isoformat())

        config = {
            "auto_maintenance_enabled": True,
            "maintenance_interval_hours": 24,  # Config says 24h
            "max_age_days": 90,
            "prune_threshold": 1000,
            "planning_keep_versions": 3,
        }
        with patch("autopack.memory.maintenance._load_maintenance_config", return_value=config):
            # Override with 1 hour - should be due
            result = is_maintenance_due(interval_hours=1)

        assert result is True


class TestRunMaintenanceIfDue:
    """Tests for run_maintenance_if_due() execution flow."""

    def test_skips_when_not_due(self, temp_timestamp_file, mock_maintenance_config):
        """Verify no maintenance runs when not due."""
        _update_last_maintenance_time()

        result = run_maintenance_if_due()

        assert result is None

    def test_runs_maintenance_when_due(self, temp_timestamp_file):
        """Verify maintenance runs and returns stats when due."""
        assert not temp_timestamp_file.exists()

        mock_store = MagicMock()

        config = {
            "auto_maintenance_enabled": True,
            "maintenance_interval_hours": 24,
            "max_age_days": 90,
            "prune_threshold": 1000,
            "planning_keep_versions": 3,
        }

        with patch("autopack.memory.maintenance._load_maintenance_config", return_value=config):
            with patch(
                "autopack.memory.maintenance.run_maintenance",
                return_value={
                    "pruned": 5,
                    "planning_tombstoned": 2,
                    "compressed": 0,
                    "errors": [],
                },
            ) as mock_run:
                # Pass store directly to avoid MemoryService creation
                result = run_maintenance_if_due(project_id="test-project", store=mock_store)

        assert result is not None
        assert result["pruned"] == 5
        assert result["planning_tombstoned"] == 2
        mock_run.assert_called_once()

    def test_updates_timestamp_after_success(self, temp_timestamp_file):
        """Verify timestamp is updated after successful maintenance."""
        assert not temp_timestamp_file.exists()

        mock_store = MagicMock()

        config = {
            "auto_maintenance_enabled": True,
            "maintenance_interval_hours": 24,
            "max_age_days": 90,
            "prune_threshold": 1000,
            "planning_keep_versions": 3,
        }

        with patch("autopack.memory.maintenance._load_maintenance_config", return_value=config):
            with patch(
                "autopack.memory.maintenance.run_maintenance",
                return_value={
                    "pruned": 0,
                    "planning_tombstoned": 0,
                    "compressed": 0,
                    "errors": [],
                },
            ):
                # Pass store directly to avoid MemoryService creation
                run_maintenance_if_due(store=mock_store)

        # Timestamp file should now exist
        assert temp_timestamp_file.exists()

    def test_updates_timestamp_after_failure(self, temp_timestamp_file):
        """Verify timestamp is updated even after maintenance failure to prevent retry storm."""
        assert not temp_timestamp_file.exists()

        mock_store = MagicMock()

        config = {
            "auto_maintenance_enabled": True,
            "maintenance_interval_hours": 24,
            "max_age_days": 90,
            "prune_threshold": 1000,
            "planning_keep_versions": 3,
        }

        with patch("autopack.memory.maintenance._load_maintenance_config", return_value=config):
            with patch(
                "autopack.memory.maintenance.run_maintenance",
                side_effect=Exception("Maintenance failed"),
            ):
                # Pass store directly to avoid MemoryService creation
                result = run_maintenance_if_due(store=mock_store)

        # Should return error stats
        assert result is not None
        assert "errors" in result
        assert len(result["errors"]) > 0

        # Timestamp file should still be updated
        assert temp_timestamp_file.exists()

    def test_uses_provided_store(self, temp_timestamp_file):
        """Verify provided store is used instead of creating MemoryService."""
        assert not temp_timestamp_file.exists()

        mock_store = MagicMock()

        config = {
            "auto_maintenance_enabled": True,
            "maintenance_interval_hours": 24,
            "max_age_days": 90,
            "prune_threshold": 1000,
            "planning_keep_versions": 3,
        }

        with patch("autopack.memory.maintenance._load_maintenance_config", return_value=config):
            with patch(
                "autopack.memory.maintenance.run_maintenance",
                return_value={
                    "pruned": 0,
                    "planning_tombstoned": 0,
                    "compressed": 0,
                    "errors": [],
                },
            ) as mock_run:
                run_maintenance_if_due(store=mock_store)

        # Verify run_maintenance was called with our store
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["store"] is mock_store


class TestAutonomousLoopIntegration:
    """Tests for maintenance integration with autonomous loop."""

    def test_loop_has_maintenance_tracking_attributes(self):
        """Verify AutonomousLoop has maintenance tracking attributes."""
        from autopack.executor.autonomous_loop import AutonomousLoop

        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"

        loop = AutonomousLoop(mock_executor)

        assert hasattr(loop, "_last_maintenance_check")
        assert hasattr(loop, "_maintenance_check_interval")
        assert hasattr(loop, "_auto_maintenance_enabled")
        assert loop._last_maintenance_check == 0.0
        assert loop._maintenance_check_interval > 0
