"""Tests for context-enriched escalation reports (IMP-ESC-001)."""

import sys
from datetime import datetime
from unittest.mock import MagicMock, patch


# Add src to path for imports
sys.path.insert(0, "src")
sys.path.insert(0, "scripts")

from handle_connection_errors_ocr import generate_escalation_report


class TestGenerateEscalationReport:
    """Tests for generate_escalation_report function."""

    def test_basic_report_structure(self):
        """Test that basic report contains required fields."""
        report = generate_escalation_report(
            slot_id=1,
            level=2,
            error_message="Connection timeout",
        )

        assert report["slot_id"] == 1
        assert report["level"] == 2
        assert report["message"] == "Connection timeout"
        assert "timestamp" in report
        assert "context" in report
        assert "analysis" in report

    def test_report_with_full_context(self):
        """Test report generation with all context parameters."""
        error_history = [
            {"error": "timeout", "timestamp": "2025-01-01T10:00:00"},
            {"error": "connection_reset", "timestamp": "2025-01-01T10:01:00"},
            {"error": "timeout", "timestamp": "2025-01-01T10:02:00"},
        ]

        report = generate_escalation_report(
            slot_id=3,
            level=4,
            error_message="Slot 3 stuck Level 4",
            phase_id="phase_build_001",
            imp_id="IMP-ESC-001",
            error_history=error_history,
            ocr_screenshot_path="/screenshots/slot3_error.png",
        )

        assert report["slot_id"] == 3
        assert report["level"] == 4
        assert report["message"] == "Slot 3 stuck Level 4"
        assert report["context"]["phase_id"] == "phase_build_001"
        assert report["context"]["imp_id"] == "IMP-ESC-001"
        assert report["context"]["error_count"] == 3
        assert len(report["context"]["recent_errors"]) == 3
        assert report["context"]["ocr_screenshot"] == "/screenshots/slot3_error.png"

    def test_context_defaults_to_none(self):
        """Test that optional context fields default to None."""
        report = generate_escalation_report(
            slot_id=1,
            level=1,
            error_message="Test error",
        )

        assert report["context"]["phase_id"] is None
        assert report["context"]["imp_id"] is None
        assert report["context"]["error_count"] == 0
        assert report["context"]["recent_errors"] == []
        assert report["context"]["ocr_screenshot"] is None

    def test_error_history_limited_to_last_5(self):
        """Test that error history is limited to last 5 entries."""
        error_history = [
            {"error": f"error_{i}", "timestamp": f"2025-01-01T10:0{i}:00"} for i in range(10)
        ]

        report = generate_escalation_report(
            slot_id=1,
            level=2,
            error_message="Test error",
            error_history=error_history,
        )

        assert report["context"]["error_count"] == 10
        assert len(report["context"]["recent_errors"]) == 5
        # Should contain the last 5 errors (indices 5-9)
        assert report["context"]["recent_errors"][0]["error"] == "error_5"
        assert report["context"]["recent_errors"][4]["error"] == "error_9"

    def test_analysis_section_structure(self):
        """Test that analysis section has correct structure."""
        report = generate_escalation_report(
            slot_id=1,
            level=1,
            error_message="Test error",
        )

        assert "analysis" in report
        assert "pattern_match" in report["analysis"]
        assert "suggested_root_cause" in report["analysis"]
        assert "recommended_action" in report["analysis"]

    def test_timestamp_is_valid_iso_format(self):
        """Test that timestamp is valid ISO format."""
        report = generate_escalation_report(
            slot_id=1,
            level=1,
            error_message="Test error",
        )

        # Should not raise an exception
        parsed = datetime.fromisoformat(report["timestamp"])
        assert isinstance(parsed, datetime)

    def test_all_escalation_levels(self):
        """Test reports can be generated for all escalation levels."""
        for level in range(1, 5):
            report = generate_escalation_report(
                slot_id=1,
                level=level,
                error_message=f"Level {level} error",
            )
            assert report["level"] == level

    def test_report_with_empty_error_history(self):
        """Test report generation with empty error history list."""
        report = generate_escalation_report(
            slot_id=1,
            level=1,
            error_message="Test error",
            error_history=[],
        )

        assert report["context"]["error_count"] == 0
        assert report["context"]["recent_errors"] == []

    def test_analysis_integration_with_telemetry(self):
        """Test that analysis integrates with telemetry when available."""
        # Create mock event with pattern
        mock_event = MagicMock()
        mock_event.event_type = "connection_timeout"

        # Create multiple events to trigger pattern detection
        mock_events = [mock_event] * 5

        mock_event_log = MagicMock()
        mock_event_log.query.return_value = mock_events

        mock_unified_event_log_module = MagicMock()
        mock_unified_event_log_module.UnifiedEventLog.return_value = mock_event_log

        # Patch the import inside the function by modifying sys.modules
        original_modules = sys.modules.copy()
        try:
            sys.modules["telemetry.unified_event_log"] = mock_unified_event_log_module

            report = generate_escalation_report(
                slot_id=1,
                level=2,
                error_message="Connection error",
            )

            # Should detect pattern from mocked events
            assert report["analysis"]["pattern_match"] == "connection_timeout"
            assert "connection_timeout" in report["analysis"]["suggested_root_cause"]
            assert "slot_1" in report["analysis"]["recommended_action"]
        finally:
            # Restore original modules
            sys.modules.clear()
            sys.modules.update(original_modules)

    def test_graceful_degradation_without_telemetry(self):
        """Test that report generation works even if telemetry is unavailable."""
        # This test verifies the except ImportError path
        with patch.dict(sys.modules, {"telemetry.unified_event_log": None}):
            # Force the import to fail by patching __import__
            original_import = (
                __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__
            )

            def failing_import(name, *args, **kwargs):
                if name == "telemetry.unified_event_log":
                    raise ImportError("No module named 'telemetry.unified_event_log'")
                return original_import(name, *args, **kwargs)

            # Even if telemetry fails, report should still be generated
            report = generate_escalation_report(
                slot_id=1,
                level=1,
                error_message="Test error",
            )

            # Basic report should still work
            assert report["slot_id"] == 1
            assert report["level"] == 1
            assert report["message"] == "Test error"


class TestEscalationReportIntegration:
    """Integration tests for escalation reports with ConnectionErrorHandler."""

    def test_report_can_be_logged(self):
        """Test that generated report can be serialized for logging."""
        import json

        report = generate_escalation_report(
            slot_id=1,
            level=2,
            error_message="Test error",
            phase_id="test_phase",
            imp_id="IMP-TEST-001",
            error_history=[{"error": "test"}],
            ocr_screenshot_path="/path/to/screenshot.png",
        )

        # Should be JSON serializable
        json_str = json.dumps(report)
        assert isinstance(json_str, str)

        # Should be deserializable
        parsed = json.loads(json_str)
        assert parsed == report
