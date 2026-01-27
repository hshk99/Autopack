"""Tests for database connectivity alerting (IMP-OPS-009).

Verifies that OperationalError exceptions trigger CRITICAL alerts
through the telemetry alerting infrastructure.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError


class TestDbConnectivityAlerts:
    """Tests for DB connectivity alerting in runs router."""

    def test_send_db_connectivity_alert_creates_critical_alert(self):
        """Verify _send_db_connectivity_alert creates a CRITICAL alert."""
        from autopack.api.routes.runs import _send_db_connectivity_alert
        from autopack.telemetry import AlertSeverity

        mock_error = OperationalError("statement", {}, Exception("connection refused"))

        with patch("autopack.api.routes.runs._get_alert_router") as mock_get_router:
            mock_router = MagicMock()
            mock_get_router.return_value = mock_router

            _send_db_connectivity_alert(mock_error, "test_operation", run_id="test-run")

            # Verify route_alert was called
            mock_router.route_alert.assert_called_once()

            # Verify alert properties
            alert = mock_router.route_alert.call_args[0][0]
            assert alert.severity == AlertSeverity.CRITICAL
            assert alert.metric == "db_connectivity"
            assert alert.phase_id == "test-run"
            assert alert.current_value == 0.0
            assert alert.threshold == 1.0
            assert "test_operation" in alert.recommendation

    def test_send_db_connectivity_alert_handles_none_run_id(self):
        """Verify _send_db_connectivity_alert works without run_id."""
        from autopack.api.routes.runs import _send_db_connectivity_alert

        mock_error = OperationalError("statement", {}, Exception("connection refused"))

        with patch("autopack.api.routes.runs._get_alert_router") as mock_get_router:
            mock_router = MagicMock()
            mock_get_router.return_value = mock_router

            _send_db_connectivity_alert(mock_error, "test_operation", run_id=None)

            # Verify route_alert was called
            mock_router.route_alert.assert_called_once()

            # Verify alert has None phase_id
            alert = mock_router.route_alert.call_args[0][0]
            assert alert.phase_id is None

    def test_start_run_sends_alert_on_operational_error(self):
        """Verify start_run sends alert when OperationalError occurs."""
        from fastapi import HTTPException
        from starlette.requests import Request

        from autopack import schemas
        from autopack.api.routes.runs import start_run

        mock_db = MagicMock()
        mock_db.query.side_effect = OperationalError(
            "statement", {}, Exception("connection refused")
        )

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/runs/start",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
        }
        request = Request(scope)

        request_data = schemas.RunStartRequest(
            run=schemas.RunCreate(
                run_id="test-run",
                safety_profile="normal",
                run_scope="full",
            ),
            tiers=[],
            phases=[],
        )

        with patch("autopack.api.routes.runs._send_db_connectivity_alert") as mock_send_alert:
            with pytest.raises(HTTPException) as exc_info:
                start_run(request_data=request_data, request=request, db=mock_db)

            # Verify 503 status code
            assert exc_info.value.status_code == 503

            # Verify alert was sent
            mock_send_alert.assert_called_once()
            call_args = mock_send_alert.call_args
            # Args are positional: (error, operation, run_id=...)
            assert call_args[0][1] == "run_start"  # operation is second positional arg
            assert call_args[1]["run_id"] == "test-run"

    def test_get_run_sends_alert_on_operational_error(self):
        """Verify get_run sends alert when OperationalError occurs."""
        from fastapi import HTTPException

        from autopack.api.routes.runs import get_run

        mock_db = MagicMock()
        mock_db.query.side_effect = OperationalError(
            "statement", {}, Exception("connection refused")
        )

        with patch("autopack.api.routes.runs._send_db_connectivity_alert") as mock_send_alert:
            with pytest.raises(HTTPException) as exc_info:
                get_run(run_id="test-run", db=mock_db, _auth="test-key")

            # Verify 503 status code
            assert exc_info.value.status_code == 503

            # Verify alert was sent
            mock_send_alert.assert_called_once()
            call_args = mock_send_alert.call_args
            # Args are positional: (error, operation, run_id=...)
            assert call_args[0][1] == "run_fetch"  # operation is second positional arg
            assert call_args[1]["run_id"] == "test-run"

    def test_alert_router_singleton(self):
        """Verify _get_alert_router returns singleton."""
        # Reset singleton for test isolation
        import autopack.api.routes.runs as runs_module
        from autopack.api.routes.runs import _get_alert_router

        runs_module._alert_router = None

        router1 = _get_alert_router()
        router2 = _get_alert_router()

        assert router1 is router2

    def test_alert_includes_error_message_in_recommendation(self):
        """Verify alert recommendation includes error details."""
        from autopack.api.routes.runs import _send_db_connectivity_alert

        error_message = "FATAL: database 'autopack' does not exist"
        mock_error = OperationalError("statement", {}, Exception(error_message))

        with patch("autopack.api.routes.runs._get_alert_router") as mock_get_router:
            mock_router = MagicMock()
            mock_get_router.return_value = mock_router

            _send_db_connectivity_alert(mock_error, "run_start", run_id="test-run")

            alert = mock_router.route_alert.call_args[0][0]
            # Error message should be included in recommendation (truncated if long)
            assert "database" in alert.recommendation.lower() or "Error:" in alert.recommendation

    def test_alert_logs_critical_message(self, caplog):
        """Verify alert logs CRITICAL level message."""
        import logging

        from autopack.api.routes.runs import _send_db_connectivity_alert

        mock_error = OperationalError("statement", {}, Exception("connection refused"))

        with patch("autopack.api.routes.runs._get_alert_router") as mock_get_router:
            mock_router = MagicMock()
            mock_get_router.return_value = mock_router

            with caplog.at_level(logging.CRITICAL):
                _send_db_connectivity_alert(mock_error, "run_start", run_id="test-run")

            # Verify CRITICAL log was emitted
            assert any("[ALERT:DB_CONNECTIVITY]" in record.message for record in caplog.records)
