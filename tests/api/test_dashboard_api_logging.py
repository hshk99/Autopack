"""Tests for dashboard API route logging (IMP-OPS-008).

Verifies that all dashboard route handlers emit structured logs for request/response
to enable API issue diagnosis.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestDashboardAPILogging:
    """Tests for API logging in dashboard routes."""

    def test_get_run_status_logs_request_and_response(self, caplog):
        """Verify get_dashboard_run_status logs request and success response."""
        import logging

        from autopack.api.routes.dashboard import get_dashboard_run_status

        caplog.set_level(logging.INFO)

        # Create mock run
        mock_run = MagicMock()
        mock_run.id = "test-run-123"
        mock_run.state.value = "IN_PROGRESS"
        mock_run.tokens_used = 500000
        mock_run.token_cap = 1000000
        mock_run.minor_issues_count = 2
        mock_run.major_issues_count = 1

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_run
        mock_db.query.return_value = mock_query

        with patch("autopack.run_progress.calculate_run_progress") as mock_progress:
            mock_progress_result = MagicMock()
            mock_progress_result.current_tier_name = "T1"
            mock_progress_result.current_phase_name = "P1"
            mock_progress_result.current_tier_index = 0
            mock_progress_result.current_phase_index = 0
            mock_progress_result.total_tiers = 3
            mock_progress_result.total_phases = 10
            mock_progress_result.completed_tiers = 0
            mock_progress_result.completed_phases = 2
            mock_progress_result.percent_complete = 20.0
            mock_progress_result.tiers_percent_complete = 0.0
            mock_progress.return_value = mock_progress_result

            with patch(
                "autopack.api.routes.dashboard.get_token_efficiency_stats"
            ) as mock_efficiency:
                mock_efficiency.return_value = None

                get_dashboard_run_status(run_id="test-run-123", db=mock_db, _auth="test")

        # Verify request log (uses %r so run_id is quoted)
        assert any(
            "[API] GET /dashboard/runs/'test-run-123'/status - request received" in record.message
            for record in caplog.records
        )
        # Verify response log (uses %r so run_id is quoted)
        assert any(
            "[API] GET /dashboard/runs/'test-run-123'/status - success" in record.message
            for record in caplog.records
        )

    def test_get_run_status_logs_404_not_found(self, caplog):
        """Verify get_dashboard_run_status logs warning for missing run."""
        import logging

        from fastapi import HTTPException

        from autopack.api.routes.dashboard import get_dashboard_run_status

        caplog.set_level(logging.WARNING)

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_dashboard_run_status(run_id="nonexistent", db=mock_db, _auth="test")

        assert exc_info.value.status_code == 404
        assert any("run not found" in record.message for record in caplog.records)

    def test_get_usage_logs_request_and_response(self, caplog):
        """Verify get_dashboard_usage logs request and success response."""
        import logging

        from autopack.api.routes.dashboard import get_dashboard_usage

        caplog.set_level(logging.INFO)

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.group_by.return_value.all.return_value = []
        mock_db.query.return_value = mock_query

        get_dashboard_usage(period="week", db=mock_db, _auth="test")

        # Verify request log (uses %r so period is quoted)
        assert any(
            "[API] GET /dashboard/usage - request received period='week'" in record.message
            for record in caplog.records
        )
        # Verify response log
        assert any(
            "[API] GET /dashboard/usage - success" in record.message for record in caplog.records
        )

    def test_get_models_logs_request_and_response(self, caplog):
        """Verify get_dashboard_models logs request and success response."""
        import logging

        from autopack.api.routes.dashboard import get_dashboard_models

        caplog.set_level(logging.INFO)

        mock_db = MagicMock()

        with patch("autopack.model_router.ModelRouter") as mock_router_cls:
            mock_router = MagicMock()
            mock_router.get_current_mappings.return_value = {
                "builder": {"code:simple": "claude-3-haiku"},
                "auditor": {"code:simple": "claude-3-haiku"},
            }
            mock_router_cls.return_value = mock_router

            get_dashboard_models(db=mock_db, _auth="test")

        # Verify request log
        assert any(
            "[API] GET /dashboard/models - request received" in record.message
            for record in caplog.records
        )
        # Verify response log
        assert any(
            "[API] GET /dashboard/models - success" in record.message for record in caplog.records
        )

    def test_add_human_note_logs_request_and_response(self, caplog, tmp_path):
        """Verify add_dashboard_human_note logs request and success response."""
        import logging

        from autopack import dashboard_schemas
        from autopack.api.routes.dashboard import add_dashboard_human_note

        caplog.set_level(logging.INFO)

        mock_db = MagicMock()

        note_request = dashboard_schemas.HumanNoteRequest(
            note="Test note content",
            run_id="test-run-123",
        )

        with patch("autopack.api.routes.dashboard.settings") as mock_settings:
            mock_settings.autonomous_runs_dir = str(tmp_path / "runs")

            add_dashboard_human_note(note_request=note_request, db=mock_db, api_key="test-key")

        # Verify request log
        assert any(
            "[API] POST /dashboard/human-notes - request received" in record.message
            for record in caplog.records
        )
        # Verify response log
        assert any(
            "[API] POST /dashboard/human-notes - success" in record.message
            for record in caplog.records
        )

    def test_get_token_efficiency_logs_request_and_response(self, caplog):
        """Verify get_run_token_efficiency logs request and success response."""
        import logging

        from autopack.api.routes.dashboard import get_run_token_efficiency

        caplog.set_level(logging.INFO)

        mock_run = MagicMock()
        mock_run.id = "test-run-123"

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_run
        mock_db.query.return_value = mock_query

        with patch("autopack.api.routes.dashboard.get_token_efficiency_stats") as mock_stats:
            mock_stats.return_value = {
                "run_id": "test-run-123",
                "total_phases": 5,
                "total_tokens_saved": 10000,
                "total_artifact_substitutions": 10,
                "total_tokens_saved_artifacts": 5000,
                "total_budget_used": 100000,
                "total_budget_cap": 500000,
                "total_files_kept": 50,
                "total_files_omitted": 20,
                "semantic_mode_count": 3,
                "lexical_mode_count": 2,
            }

            get_run_token_efficiency(run_id="test-run-123", db=mock_db, api_key="test-key")

        # Verify request log (uses %r so run_id is quoted)
        assert any(
            "[API] GET /dashboard/runs/'test-run-123'/token-efficiency - request received"
            in record.message
            for record in caplog.records
        )
        # Verify response log (uses %r so run_id is quoted)
        assert any(
            "[API] GET /dashboard/runs/'test-run-123'/token-efficiency - success" in record.message
            for record in caplog.records
        )

    def test_get_phase6_stats_logs_request_and_response(self, caplog):
        """Verify get_run_phase6_stats logs request and success response."""
        import logging

        from autopack.api.routes.dashboard import get_run_phase6_stats

        caplog.set_level(logging.INFO)

        mock_run = MagicMock()
        mock_run.id = "test-run-123"

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_run
        mock_db.query.return_value = mock_query

        with patch("autopack.usage_recorder.get_phase6_metrics_summary") as mock_stats:
            mock_stats.return_value = {
                "total_phases": 5,
                "failure_hardening_triggered_count": 2,
                "doctor_calls_skipped": 3,
                "doctor_calls_skipped_count": 3,
                "total_doctor_tokens_avoided_estimate": 15000,
                "intention_context_injected_count": 4,
                "total_intention_context_chars": 5000,
            }

            get_run_phase6_stats(run_id="test-run-123", db=mock_db, api_key="test-key")

        # Verify request log (uses %r so run_id is quoted)
        assert any(
            "[API] GET /dashboard/runs/'test-run-123'/phase6-stats - request received"
            in record.message
            for record in caplog.records
        )
        # Verify response log (uses %r so run_id is quoted)
        assert any(
            "[API] GET /dashboard/runs/'test-run-123'/phase6-stats - success" in record.message
            for record in caplog.records
        )

    def test_model_override_logs_request_and_response(self, caplog):
        """Verify add_dashboard_model_override logs request and success response."""
        import logging

        from autopack import dashboard_schemas
        from autopack.api.routes.dashboard import add_dashboard_model_override

        caplog.set_level(logging.INFO)

        mock_db = MagicMock()

        override_request = dashboard_schemas.ModelOverrideRequest(
            scope="global",
            role="builder",
            category="code",
            complexity="simple",
            model="claude-3-haiku",
        )

        add_dashboard_model_override(
            override_request=override_request, db=mock_db, api_key="test-key"
        )

        # Verify request log
        assert any(
            "[API] POST /dashboard/models/override - request received" in record.message
            for record in caplog.records
        )
        # Verify response log
        assert any(
            "[API] POST /dashboard/models/override - success" in record.message
            for record in caplog.records
        )

    def test_consolidated_metrics_logs_disabled_warning(self, caplog):
        """Verify get_dashboard_consolidated_metrics logs warning when disabled."""
        import logging
        import os

        from fastapi import HTTPException

        from autopack.api.routes.dashboard import get_dashboard_consolidated_metrics

        caplog.set_level(logging.INFO)

        mock_db = MagicMock()

        # Ensure feature is disabled
        with patch.dict(os.environ, {"AUTOPACK_ENABLE_CONSOLIDATED_METRICS": "0"}):
            with pytest.raises(HTTPException) as exc_info:
                get_dashboard_consolidated_metrics(run_id="test-run-123", db=mock_db, _auth="test")

        assert exc_info.value.status_code == 503
        # Verify request log (uses %r so run_id is quoted)
        assert any(
            "[API] GET /dashboard/runs/'test-run-123'/consolidated-metrics - request received"
            in record.message
            for record in caplog.records
        )
        # Verify warning log
        assert any("feature disabled" in record.message for record in caplog.records)
