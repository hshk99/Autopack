"""Tests for centralized event logger."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from telemetry.event_logger import EventLogger, get_logger


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def logger(temp_log_dir):
    """Create an EventLogger instance with temp directory."""
    return EventLogger(log_dir=temp_log_dir)


class TestEventLogger:
    """Tests for EventLogger class."""

    def test_init_creates_log_directory(self, temp_log_dir):
        """Test that initialization creates the log directory."""
        log_dir = Path(temp_log_dir) / "subdir" / "logs"
        logger = EventLogger(log_dir=str(log_dir))

        assert log_dir.exists()
        assert log_dir.is_dir()

    def test_init_uses_env_var_when_no_path_provided(self, temp_log_dir, monkeypatch):
        """Test that AUTOPACK_LOG_DIR env var is used when no path given."""
        monkeypatch.setenv("AUTOPACK_LOG_DIR", temp_log_dir)

        logger = EventLogger()

        assert logger.log_dir == Path(temp_log_dir)

    def test_log_writes_json_event(self, logger, temp_log_dir):
        """Test that log() writes a valid JSON event."""
        logger.log(
            event_type="test_event",
            data={"key": "value", "number": 42},
            slot=1,
        )

        log_file = logger.current_log
        assert log_file.exists()

        with open(log_file) as f:
            line = f.readline()
            event = json.loads(line)

        assert event["type"] == "test_event"
        assert event["slot"] == 1
        assert event["data"]["key"] == "value"
        assert event["data"]["number"] == 42
        assert "timestamp" in event

    def test_log_appends_to_file(self, logger):
        """Test that multiple log calls append to the same file."""
        logger.log("event1", {"a": 1})
        logger.log("event2", {"b": 2})
        logger.log("event3", {"c": 3})

        with open(logger.current_log) as f:
            lines = f.readlines()

        assert len(lines) == 3

        events = [json.loads(line) for line in lines]
        assert events[0]["type"] == "event1"
        assert events[1]["type"] == "event2"
        assert events[2]["type"] == "event3"

    def test_log_with_none_slot(self, logger):
        """Test that logging with no slot sets slot to None."""
        logger.log("test_event", {"data": "value"})

        with open(logger.current_log) as f:
            event = json.loads(f.readline())

        assert event["slot"] is None

    def test_log_file_named_with_date(self, logger):
        """Test that log file is named with current date."""
        expected_date = datetime.now().strftime("%Y%m%d")
        expected_name = f"events_{expected_date}.jsonl"

        assert logger.current_log.name == expected_name

    def test_log_pr_event(self, logger):
        """Test log_pr_event() convenience method."""
        logger.log_pr_event(
            action="merged",
            pr_number=123,
            details={"merge_time_hours": 2.5},
            slot=1,
        )

        with open(logger.current_log) as f:
            event = json.loads(f.readline())

        assert event["type"] == "pr_merged"
        assert event["data"]["pr_number"] == 123
        assert event["data"]["merge_time_hours"] == 2.5
        assert event["slot"] == 1

    def test_log_slot_operation(self, logger):
        """Test log_slot_operation() convenience method."""
        logger.log_slot_operation(
            operation="filled",
            slot=5,
            details={"task_id": "IMP-TEL-001"},
        )

        with open(logger.current_log) as f:
            event = json.loads(f.readline())

        assert event["type"] == "slot_filled"
        assert event["slot"] == 5
        assert event["data"]["task_id"] == "IMP-TEL-001"

    def test_log_ci_failure(self, logger):
        """Test log_ci_failure() convenience method."""
        logger.log_ci_failure(
            run_id="run-123",
            failure_category="flaky_test",
            details={"failed_jobs": "lint, test"},
            slot=2,
        )

        with open(logger.current_log) as f:
            event = json.loads(f.readline())

        assert event["type"] == "ci_failure"
        assert event["data"]["run_id"] == "run-123"
        assert event["data"]["category"] == "flaky_test"
        assert event["data"]["failed_jobs"] == "lint, test"
        assert event["slot"] == 2

    def test_log_nudge(self, logger):
        """Test log_nudge() convenience method."""
        logger.log_nudge(
            template_id="stuck_pr",
            slot=3,
            context={"pr_age_hours": 48},
        )

        with open(logger.current_log) as f:
            event = json.loads(f.readline())

        assert event["type"] == "nudge_sent"
        assert event["data"]["template_id"] == "stuck_pr"
        assert event["data"]["context"]["pr_age_hours"] == 48
        assert event["slot"] == 3

    def test_log_state_transition(self, logger):
        """Test log_state_transition() convenience method."""
        logger.log_state_transition(
            from_state="pending",
            to_state="in_progress",
            details={"trigger": "auto_fill"},
            slot=4,
        )

        with open(logger.current_log) as f:
            event = json.loads(f.readline())

        assert event["type"] == "state_transition"
        assert event["data"]["from_state"] == "pending"
        assert event["data"]["to_state"] == "in_progress"
        assert event["data"]["trigger"] == "auto_fill"
        assert event["slot"] == 4

    def test_log_connection_error(self, logger):
        """Test log_connection_error() convenience method."""
        logger.log_connection_error(
            error_type="timeout",
            details={"operation": "ocr_request", "attempt": 2},
            slot=6,
        )

        with open(logger.current_log) as f:
            event = json.loads(f.readline())

        assert event["type"] == "connection_error"
        assert event["data"]["error_type"] == "timeout"
        assert event["data"]["operation"] == "ocr_request"
        assert event["data"]["attempt"] == 2
        assert event["slot"] == 6


class TestGetLogger:
    """Tests for get_logger() function."""

    def test_get_logger_returns_event_logger(self, temp_log_dir):
        """Test that get_logger returns an EventLogger instance."""
        logger = get_logger(log_dir=temp_log_dir)

        assert isinstance(logger, EventLogger)

    def test_get_logger_returns_same_instance(self, temp_log_dir):
        """Test that repeated calls return the same instance."""
        # Reset the global logger
        import telemetry.event_logger as module

        module._default_logger = None

        logger1 = get_logger(log_dir=temp_log_dir)
        logger2 = get_logger()

        assert logger1 is logger2

    def test_get_logger_with_new_dir_creates_new_instance(self, temp_log_dir):
        """Test that providing a new dir creates a new instance."""
        import telemetry.event_logger as module

        module._default_logger = None

        logger1 = get_logger(log_dir=temp_log_dir)

        with tempfile.TemporaryDirectory() as new_dir:
            logger2 = get_logger(log_dir=new_dir)

            assert logger1 is not logger2
            assert logger2.log_dir == Path(new_dir)
