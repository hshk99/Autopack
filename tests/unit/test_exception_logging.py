"""Unit tests for exception logging telemetry.

IMP-TELE-003: Tests verifying that previously silent exception handlers
now properly log exceptions with telemetry markers.
"""

import logging
from unittest.mock import patch



class TestMemoryServiceExceptionLogging:
    """Tests for exception logging in memory_service.py."""

    def test_tcp_reachable_logs_connection_failure(self, caplog):
        """TCP connection failure should be logged with IMP-TELE-003 marker."""
        from autopack.memory.memory_service import _tcp_reachable

        with caplog.at_level(logging.DEBUG):
            # Try connecting to a port that definitely won't be open
            result = _tcp_reachable("127.0.0.1", 59999, 0.1)

        assert result is False
        # Verify debug log was generated
        assert any("[IMP-TELE-003]" in record.message for record in caplog.records)
        assert any("TCP connection" in record.message for record in caplog.records)

    def test_docker_available_logs_failure(self, caplog):
        """Docker availability check failure should be logged."""
        from autopack.memory.memory_service import _docker_available

        with caplog.at_level(logging.DEBUG):
            with patch("subprocess.run", side_effect=FileNotFoundError("docker not found")):
                result = _docker_available()

        assert result is False
        assert any("[IMP-TELE-003]" in record.message for record in caplog.records)
        assert any("Docker availability" in record.message for record in caplog.records)

    def test_docker_compose_cmd_logs_failure(self, caplog):
        """Docker compose command check failure should be logged."""
        from autopack.memory.memory_service import _docker_compose_cmd

        with caplog.at_level(logging.DEBUG):
            with patch("subprocess.run", side_effect=FileNotFoundError("not found")):
                result = _docker_compose_cmd()

        assert result is None
        # Both docker compose and docker-compose failures should be logged
        tele003_logs = [r for r in caplog.records if "[IMP-TELE-003]" in r.message]
        assert len(tele003_logs) >= 1


class TestAnomalyDetectorExceptionLogging:
    """Tests for exception logging in anomaly_detector.py."""

    def test_check_duration_anomaly_logs_calculation_failure(self, caplog):
        """P95 calculation failure should be logged."""
        from autopack.telemetry.anomaly_detector import TelemetryAnomalyDetector

        detector = TelemetryAnomalyDetector()
        # Add minimal history that might cause calculation issues
        detector.duration_history["test_phase"] = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]

        with caplog.at_level(logging.DEBUG):
            with patch(
                "autopack.telemetry.anomaly_detector.quantiles",
                side_effect=ValueError("statistics error"),
            ):
                result = detector._check_duration_anomaly("test_phase", 10.0)

        assert result is None
        assert any("[IMP-TELE-003]" in record.message for record in caplog.records)
        assert any("p95" in record.message for record in caplog.records)

    def test_calculate_correlation_logs_failure(self, caplog):
        """Correlation calculation failure should be logged."""
        from autopack.telemetry.anomaly_detector import TelemetryAnomalyDetector

        detector = TelemetryAnomalyDetector()
        outcomes_a = [True, False, True, False, True]
        outcomes_b = [True, True, False, False, True]

        with caplog.at_level(logging.DEBUG):
            with patch(
                "autopack.telemetry.anomaly_detector.stdev",
                side_effect=ValueError("statistics error"),
            ):
                result = detector._calculate_correlation(outcomes_a, outcomes_b)

        assert result == 0.0
        assert any("[IMP-TELE-003]" in record.message for record in caplog.records)
        assert any("correlation" in record.message for record in caplog.records)


class TestExceptionLoggingPreservesReturnValues:
    """Tests ensuring exception handlers still return expected default values."""

    def test_tcp_reachable_returns_false_on_error(self):
        """_tcp_reachable should return False when connection fails."""
        from autopack.memory.memory_service import _tcp_reachable

        # Invalid host should fail
        result = _tcp_reachable("invalid.host.that.does.not.exist", 12345, 0.1)
        assert result is False

    def test_docker_available_returns_false_on_error(self):
        """_docker_available should return False when docker check fails."""
        from autopack.memory.memory_service import _docker_available

        with patch("subprocess.run", side_effect=Exception("simulated error")):
            result = _docker_available()
        assert result is False

    def test_docker_compose_cmd_returns_none_on_error(self):
        """_docker_compose_cmd should return None when command check fails."""
        from autopack.memory.memory_service import _docker_compose_cmd

        with patch("subprocess.run", side_effect=Exception("simulated error")):
            result = _docker_compose_cmd()
        assert result is None
