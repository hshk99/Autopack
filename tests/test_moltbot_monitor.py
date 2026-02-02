"""Tests for MOLT-006 Moltbot Monitor with Shadow Mode and Kill Switch.

Tests the safety mechanisms:
1. Shadow Mode: Logs triggers without taking action
2. Kill Switch: moltbot_paused.signal file disables all activity
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from autopack.moltbot_monitor import (
    KILL_SWITCH_SIGNAL_FILE,
    MOLTBOT_SHADOW_MODE_ENV,
    MOLTBOT_SIGNAL_PATH_ENV,
    MoltbotMetrics,
    MoltbotMode,
    MoltbotMonitor,
    ShadowTriggerRecord,
)


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def monitor(temp_workspace):
    """Create a MoltbotMonitor instance with temporary workspace."""
    return MoltbotMonitor(workspace_root=temp_workspace)


class TestMoltbotMode:
    """Tests for MoltbotMode enum."""

    def test_mode_values(self):
        """Verify mode enum values."""
        assert MoltbotMode.ACTIVE.value == "active"
        assert MoltbotMode.SHADOW.value == "shadow"
        assert MoltbotMode.KILLED.value == "killed"


class TestShadowTriggerRecord:
    """Tests for ShadowTriggerRecord dataclass."""

    def test_create_record(self):
        """Test creating a shadow trigger record."""
        record = ShadowTriggerRecord(
            trigger_id="test_123",
            action_type="write_file",
            timestamp="2024-01-15T10:00:00",
            context={"path": "/test/file.txt"},
            would_execute=True,
        )

        assert record.trigger_id == "test_123"
        assert record.action_type == "write_file"
        assert record.context == {"path": "/test/file.txt"}
        assert record.would_execute is True

    def test_record_to_dict(self):
        """Test converting record to dictionary."""
        record = ShadowTriggerRecord(
            trigger_id="test_456",
            action_type="execute_command",
            timestamp="2024-01-15T10:00:00",
            context={"command": "npm test"},
        )

        data = record.to_dict()
        assert data["trigger_id"] == "test_456"
        assert data["action_type"] == "execute_command"
        assert data["context"]["command"] == "npm test"

    def test_record_default_context(self):
        """Test record with default empty context."""
        record = ShadowTriggerRecord(
            trigger_id="test_789",
            action_type="read_file",
            timestamp="2024-01-15T10:00:00",
        )

        assert record.context == {}


class TestMoltbotMetrics:
    """Tests for MoltbotMetrics dataclass."""

    def test_initial_metrics(self):
        """Test initial metrics values."""
        metrics = MoltbotMetrics()

        assert metrics.total_triggers == 0
        assert metrics.shadow_triggers == 0
        assert metrics.executed_actions == 0
        assert metrics.kill_switch_blocks == 0
        assert metrics.mode_transitions == {}

    def test_record_shadow_trigger(self):
        """Test recording shadow triggers."""
        metrics = MoltbotMetrics()
        metrics.record_shadow_trigger()

        assert metrics.total_triggers == 1
        assert metrics.shadow_triggers == 1
        assert metrics.last_trigger_time is not None

    def test_record_executed_action(self):
        """Test recording executed actions."""
        metrics = MoltbotMetrics()
        metrics.record_executed_action()

        assert metrics.total_triggers == 1
        assert metrics.executed_actions == 1
        assert metrics.last_trigger_time is not None

    def test_record_kill_switch_block(self):
        """Test recording kill switch blocks."""
        metrics = MoltbotMetrics()
        metrics.record_kill_switch_block()

        assert metrics.total_triggers == 1
        assert metrics.kill_switch_blocks == 1

    def test_record_mode_transition(self):
        """Test recording mode transitions."""
        metrics = MoltbotMetrics()
        metrics.record_mode_transition(MoltbotMode.ACTIVE, MoltbotMode.SHADOW)
        metrics.record_mode_transition(MoltbotMode.ACTIVE, MoltbotMode.SHADOW)
        metrics.record_mode_transition(MoltbotMode.SHADOW, MoltbotMode.KILLED)

        assert metrics.mode_transitions["active_to_shadow"] == 2
        assert metrics.mode_transitions["shadow_to_killed"] == 1

    def test_metrics_to_dict(self):
        """Test metrics serialization."""
        metrics = MoltbotMetrics(start_time="2024-01-15T10:00:00")
        metrics.record_shadow_trigger()

        data = metrics.to_dict()
        assert data["total_triggers"] == 1
        assert data["shadow_triggers"] == 1
        assert data["start_time"] == "2024-01-15T10:00:00"


class TestMoltbotMonitorInitialization:
    """Tests for MoltbotMonitor initialization."""

    def test_default_initialization(self, temp_workspace):
        """Test default monitor initialization starts in active mode."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace)

        assert monitor.get_mode() == MoltbotMode.ACTIVE
        assert monitor.is_active() is True
        assert monitor.is_shadow_mode() is False
        assert monitor.is_killed() is False

    def test_shadow_mode_initialization(self, temp_workspace):
        """Test monitor initialization in shadow mode."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace, shadow_mode=True)

        assert monitor.get_mode() == MoltbotMode.SHADOW
        assert monitor.is_shadow_mode() is True
        assert monitor.is_active() is False

    def test_custom_signal_file_path(self, temp_workspace):
        """Test custom signal file path."""
        custom_path = temp_workspace / "custom" / "signal.file"
        monitor = MoltbotMonitor(workspace_root=temp_workspace, signal_file_path=custom_path)

        assert monitor.signal_file_path == custom_path

    def test_env_var_shadow_mode_override(self, temp_workspace):
        """Test environment variable forces shadow mode."""
        with patch.dict(os.environ, {MOLTBOT_SHADOW_MODE_ENV: "1"}):
            monitor = MoltbotMonitor(workspace_root=temp_workspace)
            assert monitor.get_mode() == MoltbotMode.SHADOW

    def test_env_var_signal_path_override(self, temp_workspace):
        """Test environment variable overrides signal file path."""
        custom_path = str(temp_workspace / "env_signal.file")
        with patch.dict(os.environ, {MOLTBOT_SIGNAL_PATH_ENV: custom_path}):
            monitor = MoltbotMonitor(workspace_root=temp_workspace)
            assert str(monitor.signal_file_path) == custom_path

    def test_existing_signal_file_at_startup(self, temp_workspace):
        """Test monitor detects existing kill switch signal at startup."""
        signal_file = temp_workspace / KILL_SWITCH_SIGNAL_FILE
        signal_file.write_text('{"reason": "pre-existing"}')

        monitor = MoltbotMonitor(workspace_root=temp_workspace)

        assert monitor.get_mode() == MoltbotMode.KILLED
        assert monitor.is_killed() is True


class TestShadowMode:
    """Tests for Shadow Mode functionality."""

    def test_enable_shadow_mode(self, monitor):
        """Test enabling shadow mode."""
        assert monitor.get_mode() == MoltbotMode.ACTIVE

        monitor.enable_shadow_mode()

        assert monitor.get_mode() == MoltbotMode.SHADOW
        assert monitor.is_shadow_mode() is True

    def test_record_shadow_trigger(self, temp_workspace):
        """Test recording triggers in shadow mode."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace, shadow_mode=True)

        record = monitor.record_shadow_trigger(
            action_type="write_file", context={"path": "/test/file.txt"}
        )

        assert record.action_type == "write_file"
        assert record.context["path"] == "/test/file.txt"
        assert record.would_execute is True
        assert monitor.metrics.shadow_triggers == 1

    def test_multiple_shadow_triggers(self, temp_workspace):
        """Test recording multiple shadow triggers."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace, shadow_mode=True)

        monitor.record_shadow_trigger("action_1")
        monitor.record_shadow_trigger("action_2")
        monitor.record_shadow_trigger("action_3")

        triggers = monitor.get_shadow_triggers()
        assert len(triggers) == 3
        assert monitor.metrics.shadow_triggers == 3

    def test_shadow_triggers_have_unique_ids(self, temp_workspace):
        """Test that shadow triggers have unique IDs."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace, shadow_mode=True)

        record1 = monitor.record_shadow_trigger("action_1")
        record2 = monitor.record_shadow_trigger("action_2")

        assert record1.trigger_id != record2.trigger_id

    def test_enable_active_mode_from_shadow(self, temp_workspace):
        """Test transitioning from shadow to active mode."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace, shadow_mode=True)
        assert monitor.is_shadow_mode() is True

        monitor.enable_active_mode()

        assert monitor.is_active() is True
        assert monitor.metrics.mode_transitions.get("shadow_to_active") == 1


class TestKillSwitch:
    """Tests for Kill Switch functionality."""

    def test_engage_kill_switch(self, monitor, temp_workspace):
        """Test engaging kill switch creates signal file."""
        monitor.engage_kill_switch(reason="Test emergency")

        assert monitor.is_killed() is True
        assert monitor.signal_file_path.exists()

        # Verify signal file content
        data = json.loads(monitor.signal_file_path.read_text())
        assert data["reason"] == "Test emergency"
        assert "engaged_at" in data

    def test_kill_switch_blocks_operations(self, monitor, temp_workspace):
        """Test kill switch blocks should_execute."""
        assert monitor.should_execute("test_action") is True

        monitor.engage_kill_switch("Test pause")

        assert monitor.should_execute("test_action") is False
        assert monitor.metrics.kill_switch_blocks == 1

    def test_disengage_kill_switch(self, monitor, temp_workspace):
        """Test disengaging kill switch removes signal file."""
        monitor.engage_kill_switch("Test")
        assert monitor.is_killed() is True

        monitor.disengage_kill_switch()

        assert monitor.is_killed() is False
        assert not monitor.signal_file_path.exists()
        # Should transition to shadow mode for safety
        assert monitor.is_shadow_mode() is True

    def test_kill_switch_takes_precedence(self, temp_workspace):
        """Test kill switch overrides other modes."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace, shadow_mode=False)
        assert monitor.is_active() is True

        # Create signal file externally
        signal_file = temp_workspace / KILL_SWITCH_SIGNAL_FILE
        signal_file.write_text('{"reason": "external pause"}')

        # Next mode check should detect kill switch
        assert monitor.get_mode() == MoltbotMode.KILLED
        assert monitor.is_killed() is True

    def test_cannot_enable_modes_while_killed(self, monitor):
        """Test mode changes blocked while kill switch is engaged."""
        monitor.engage_kill_switch("Test")

        monitor.enable_shadow_mode()
        assert monitor.is_killed() is True  # Still killed

        monitor.enable_active_mode()
        assert monitor.is_killed() is True  # Still killed

    def test_external_signal_file_removal(self, monitor, temp_workspace):
        """Test monitor detects external signal file removal."""
        monitor.engage_kill_switch("Test")
        assert monitor.is_killed() is True

        # Remove signal file externally
        monitor.signal_file_path.unlink()

        # Next mode check should detect removal
        assert monitor.is_killed() is False
        assert monitor.is_shadow_mode() is True  # Defaults to shadow for safety


class TestShouldExecute:
    """Tests for should_execute decision logic."""

    def test_should_execute_in_active_mode(self, monitor):
        """Test should_execute returns True in active mode."""
        assert monitor.is_active() is True
        assert monitor.should_execute("test_action") is True

    def test_should_execute_in_shadow_mode(self, temp_workspace):
        """Test should_execute returns False and records trigger in shadow mode."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace, shadow_mode=True)

        result = monitor.should_execute("test_action", {"key": "value"})

        assert result is False
        assert monitor.metrics.shadow_triggers == 1
        triggers = monitor.get_shadow_triggers()
        assert len(triggers) == 1
        assert triggers[0].action_type == "test_action"

    def test_should_execute_when_killed(self, monitor):
        """Test should_execute returns False and records block when killed."""
        monitor.engage_kill_switch("Test")

        result = monitor.should_execute("test_action")

        assert result is False
        assert monitor.metrics.kill_switch_blocks == 1


class TestBaselineCollection:
    """Tests for baseline data collection and storage."""

    def test_get_baseline_summary(self, temp_workspace):
        """Test baseline summary generation."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace, shadow_mode=True)

        monitor.record_shadow_trigger("action_a")
        monitor.record_shadow_trigger("action_b")
        monitor.record_shadow_trigger("action_a")

        summary = monitor.get_baseline_summary()

        assert summary["total_triggers"] == 3
        assert summary["action_type_counts"]["action_a"] == 2
        assert summary["action_type_counts"]["action_b"] == 1

    def test_save_baseline(self, temp_workspace):
        """Test saving baseline data to file."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace, shadow_mode=True)
        monitor.record_shadow_trigger("test_action", {"data": "value"})

        path = monitor.save_baseline()

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["summary"]["total_triggers"] == 1
        assert len(data["triggers"]) == 1

    def test_save_baseline_custom_path(self, temp_workspace):
        """Test saving baseline to custom path."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace, shadow_mode=True)
        monitor.record_shadow_trigger("test_action")

        custom_path = temp_workspace / "custom" / "baseline.json"
        path = monitor.save_baseline(custom_path)

        assert path == custom_path
        assert path.exists()

    def test_load_baseline(self, temp_workspace):
        """Test loading baseline data from file."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace, shadow_mode=True)
        monitor.record_shadow_trigger("test_action", {"key": "value"})
        monitor.save_baseline()

        # Create new monitor and load baseline
        monitor2 = MoltbotMonitor(workspace_root=temp_workspace)
        data = monitor2.load_baseline()

        assert data["summary"]["total_triggers"] == 1
        assert len(data["triggers"]) == 1

    def test_load_baseline_missing_file(self, temp_workspace):
        """Test loading baseline when file doesn't exist."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace)

        data = monitor.load_baseline()

        assert data["summary"] == {}
        assert data["triggers"] == []


class TestMetricsTracking:
    """Tests for metrics tracking functionality."""

    def test_metrics_track_shadow_triggers(self, temp_workspace):
        """Test metrics track shadow triggers correctly."""
        monitor = MoltbotMonitor(workspace_root=temp_workspace, shadow_mode=True)

        for _ in range(5):
            monitor.record_shadow_trigger("action")

        metrics = monitor.get_metrics()
        assert metrics.total_triggers == 5
        assert metrics.shadow_triggers == 5
        assert metrics.executed_actions == 0

    def test_metrics_track_executed_actions(self, monitor):
        """Test metrics track executed actions correctly."""
        for _ in range(3):
            monitor.record_action_executed("action")

        metrics = monitor.get_metrics()
        assert metrics.total_triggers == 3
        assert metrics.executed_actions == 3
        assert metrics.shadow_triggers == 0

    def test_metrics_track_mode_transitions(self, monitor):
        """Test metrics track mode transitions."""
        monitor.enable_shadow_mode()
        monitor.enable_active_mode()
        monitor.enable_shadow_mode()

        metrics = monitor.get_metrics()
        assert metrics.mode_transitions["active_to_shadow"] == 2
        assert metrics.mode_transitions["shadow_to_active"] == 1


class TestSerialization:
    """Tests for monitor state serialization."""

    def test_to_dict(self, monitor):
        """Test monitor state serialization."""
        monitor.enable_shadow_mode()
        monitor.record_shadow_trigger("test_action")

        data = monitor.to_dict()

        assert data["mode"] == "shadow"
        assert data["shadow_trigger_count"] == 1
        assert "signal_file_path" in data
        assert "metrics" in data


class TestEnvironmentVariableIsolation:
    """Tests for environment variable isolation."""

    def test_shadow_mode_env_isolation(self, temp_workspace):
        """Test shadow mode env var doesn't leak between tests."""
        # Test 1: Without env var
        with patch.dict(os.environ, {}, clear=False):
            if MOLTBOT_SHADOW_MODE_ENV in os.environ:
                del os.environ[MOLTBOT_SHADOW_MODE_ENV]

            monitor1 = MoltbotMonitor(workspace_root=temp_workspace)
            assert monitor1.is_active() is True

        # Test 2: With env var
        with patch.dict(os.environ, {MOLTBOT_SHADOW_MODE_ENV: "1"}):
            monitor2 = MoltbotMonitor(workspace_root=temp_workspace)
            assert monitor2.is_shadow_mode() is True

    def test_signal_path_env_isolation(self, temp_workspace):
        """Test signal path env var doesn't leak between tests."""
        default_monitor = MoltbotMonitor(workspace_root=temp_workspace)
        default_path = default_monitor.signal_file_path

        custom_path = str(temp_workspace / "custom_signal.file")
        with patch.dict(os.environ, {MOLTBOT_SIGNAL_PATH_ENV: custom_path}):
            env_monitor = MoltbotMonitor(workspace_root=temp_workspace)
            assert str(env_monitor.signal_file_path) == custom_path
            assert str(env_monitor.signal_file_path) != str(default_path)


class TestThreadSafety:
    """Tests for thread safety of monitor operations."""

    def test_concurrent_shadow_triggers(self, temp_workspace):
        """Test concurrent shadow trigger recording."""
        import threading

        monitor = MoltbotMonitor(workspace_root=temp_workspace, shadow_mode=True)

        def record_triggers():
            for _ in range(100):
                monitor.record_shadow_trigger("concurrent_action")

        threads = [threading.Thread(target=record_triggers) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        triggers = monitor.get_shadow_triggers()
        assert len(triggers) == 500
        assert monitor.metrics.shadow_triggers == 500

    def test_concurrent_mode_checks(self, temp_workspace):
        """Test concurrent mode checks don't cause race conditions."""
        import threading

        monitor = MoltbotMonitor(workspace_root=temp_workspace)
        results = []

        def check_mode():
            for _ in range(100):
                mode = monitor.get_mode()
                results.append(mode)

        threads = [threading.Thread(target=check_mode) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 500
        # All should be ACTIVE since no state changes
        assert all(m == MoltbotMode.ACTIVE for m in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
