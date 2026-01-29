"""Contract tests for dashboard router.

These tests verify the dashboard router behavior contract is preserved
during the extraction from main.py to api/routes/dashboard.py (PR-API-3d).
"""

import pytest


class TestDashboardRouterContract:
    """Contract tests for dashboard router configuration."""

    def test_router_has_dashboard_prefix(self):
        """Contract: Dashboard router uses /dashboard prefix."""
        from autopack.api.routes.dashboard import router

        assert router.prefix == "/dashboard"

    def test_router_has_dashboard_tag(self):
        """Contract: Dashboard router is tagged as 'dashboard'."""
        from autopack.api.routes.dashboard import router

        assert "dashboard" in router.tags


class TestGetDashboardRunStatusContract:
    """Contract tests for get_dashboard_run_status endpoint."""

    def test_run_status_returns_404_for_missing_run(self):
        """Contract: /dashboard/runs/{run_id}/status returns 404 for missing run."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.dashboard import get_dashboard_run_status

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_dashboard_run_status(run_id="nonexistent", db=mock_db, _auth="test")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail

    def test_run_status_calculates_token_utilization(self):
        """Contract: /dashboard/runs/{run_id}/status calculates token utilization percentage."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.dashboard import get_dashboard_run_status

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

        # Mock calculate_run_progress (imported inside function)
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

            # Mock get_token_efficiency_stats (top-level import in dashboard.py)
            with patch(
                "autopack.api.routes.dashboard.get_token_efficiency_stats"
            ) as mock_efficiency:
                mock_efficiency.return_value = None

                result = get_dashboard_run_status(run_id="test-run-123", db=mock_db, _auth="test")

        # 500000/1000000 * 100 = 50%
        assert result.token_utilization == 50.0
        assert result.tokens_used == 500000
        assert result.token_cap == 1000000


class TestGetDashboardUsageContract:
    """Contract tests for get_dashboard_usage endpoint."""

    def test_usage_returns_empty_when_no_events(self):
        """Contract: /dashboard/usage returns empty lists when no usage events."""
        from unittest.mock import MagicMock

        from autopack.api.routes.dashboard import get_dashboard_usage

        mock_db = MagicMock()
        mock_query = MagicMock()
        # IMP-P04: Updated for SQL GROUP BY query structure
        mock_query.filter.return_value.group_by.return_value.all.return_value = []
        mock_db.query.return_value = mock_query

        result = get_dashboard_usage(period="week", db=mock_db, _auth="test")

        assert result.providers == []
        assert result.models == []

    def test_usage_accepts_valid_periods(self):
        """Contract: /dashboard/usage accepts day/week/month periods."""
        from unittest.mock import MagicMock

        from autopack.api.routes.dashboard import get_dashboard_usage

        mock_db = MagicMock()
        mock_query = MagicMock()
        # IMP-P04: Updated for SQL GROUP BY query structure
        mock_query.filter.return_value.group_by.return_value.all.return_value = []
        mock_db.query.return_value = mock_query

        for period in ["day", "week", "month"]:
            result = get_dashboard_usage(period=period, db=mock_db, _auth="test")
            assert result.providers == []


class TestGetDashboardModelsContract:
    """Contract tests for get_dashboard_models endpoint."""

    def test_models_returns_list(self):
        """Contract: /dashboard/models returns list of model mappings."""
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.dashboard import get_dashboard_models

        mock_db = MagicMock()

        with patch("autopack.model_router.ModelRouter") as mock_router_cls:
            mock_router = MagicMock()
            mock_router.get_current_mappings.return_value = {
                "builder": {"code:simple": "claude-3-haiku"},
                "auditor": {"code:simple": "claude-3-haiku"},
            }
            mock_router_cls.return_value = mock_router

            result = get_dashboard_models(db=mock_db, _auth="test")

        assert isinstance(result, list)
        assert len(result) == 2


class TestAddDashboardHumanNoteContract:
    """Contract tests for add_dashboard_human_note endpoint."""

    def test_human_note_returns_success(self):
        """Contract: /dashboard/human-notes returns success message."""
        import tempfile
        from unittest.mock import MagicMock, patch

        from autopack.api.routes.dashboard import add_dashboard_human_note

        mock_db = MagicMock()
        mock_request = MagicMock()
        mock_request.run_id = "test-run"
        mock_request.note = "Test note content"

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("autopack.api.routes.dashboard.settings") as mock_settings:
                mock_settings.autonomous_runs_dir = tmp_dir

                result = add_dashboard_human_note(
                    note_request=mock_request, db=mock_db, api_key="test"
                )

        assert result["message"] == "Note added successfully"
        assert "timestamp" in result
        assert result["notes_file"] == ".autopack/human_notes.md"


class TestGetRunTokenEfficiencyContract:
    """Contract tests for get_run_token_efficiency endpoint."""

    def test_token_efficiency_returns_404_for_missing_run(self):
        """Contract: /dashboard/runs/{run_id}/token-efficiency returns 404 for missing run."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.dashboard import get_run_token_efficiency

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_run_token_efficiency(run_id="nonexistent", db=mock_db, api_key="test")

        assert exc_info.value.status_code == 404


class TestGetRunPhase6StatsContract:
    """Contract tests for get_run_phase6_stats endpoint."""

    def test_phase6_stats_returns_404_for_missing_run(self):
        """Contract: /dashboard/runs/{run_id}/phase6-stats returns 404 for missing run."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.dashboard import get_run_phase6_stats

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_run_phase6_stats(run_id="nonexistent", db=mock_db, api_key="test")

        assert exc_info.value.status_code == 404


class TestGetDashboardConsolidatedMetricsContract:
    """Contract tests for get_dashboard_consolidated_metrics endpoint."""

    def test_consolidated_metrics_requires_kill_switch(self):
        """Contract: /dashboard/runs/{run_id}/consolidated-metrics requires kill switch."""
        import os
        from unittest.mock import MagicMock, patch

        from fastapi import HTTPException

        from autopack.api.routes.dashboard import \
            get_dashboard_consolidated_metrics

        mock_db = MagicMock()

        # Ensure kill switch is off
        with patch.dict(os.environ, {"AUTOPACK_ENABLE_CONSOLIDATED_METRICS": "0"}, clear=False):
            with pytest.raises(HTTPException) as exc_info:
                get_dashboard_consolidated_metrics(run_id="test", db=mock_db, _auth="test")

        assert exc_info.value.status_code == 503
        assert "disabled" in exc_info.value.detail.lower()

    def test_consolidated_metrics_validates_pagination(self):
        """Contract: /dashboard/runs/{run_id}/consolidated-metrics validates pagination."""
        import os
        from unittest.mock import MagicMock, patch

        from fastapi import HTTPException

        from autopack.api.routes.dashboard import \
            get_dashboard_consolidated_metrics

        mock_db = MagicMock()

        with patch.dict(os.environ, {"AUTOPACK_ENABLE_CONSOLIDATED_METRICS": "1"}, clear=False):
            # Test limit > 10000
            with pytest.raises(HTTPException) as exc_info:
                get_dashboard_consolidated_metrics(
                    run_id="test", limit=20000, db=mock_db, _auth="test"
                )
            assert exc_info.value.status_code == 400
            assert "10000" in exc_info.value.detail

            # Test negative offset
            with pytest.raises(HTTPException) as exc_info:
                get_dashboard_consolidated_metrics(
                    run_id="test", offset=-1, db=mock_db, _auth="test"
                )
            assert exc_info.value.status_code == 400
            assert "negative" in exc_info.value.detail.lower()


class TestAddDashboardModelOverrideContract:
    """Contract tests for add_dashboard_model_override endpoint."""

    def test_model_override_accepts_global_scope(self):
        """Contract: /dashboard/models/override accepts global scope."""
        from unittest.mock import MagicMock

        from autopack.api.routes.dashboard import add_dashboard_model_override

        mock_db = MagicMock()
        mock_request = MagicMock()
        mock_request.scope = "global"
        mock_request.role = "builder"
        mock_request.category = "code"
        mock_request.complexity = "simple"
        mock_request.model = "claude-3-haiku"

        result = add_dashboard_model_override(
            override_request=mock_request, db=mock_db, api_key="test"
        )

        assert result["scope"] == "global"
        assert result["message"] == "Global model mapping updated"

    def test_model_override_accepts_run_scope(self):
        """Contract: /dashboard/models/override accepts run scope."""
        from unittest.mock import MagicMock

        from autopack.api.routes.dashboard import add_dashboard_model_override

        mock_db = MagicMock()
        mock_request = MagicMock()
        mock_request.scope = "run"
        mock_request.run_id = "test-run"

        result = add_dashboard_model_override(
            override_request=mock_request, db=mock_db, api_key="test"
        )

        assert result["scope"] == "run"
        assert "coming soon" in result["message"].lower()

    def test_model_override_rejects_invalid_scope(self):
        """Contract: /dashboard/models/override rejects invalid scope."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.dashboard import add_dashboard_model_override

        mock_db = MagicMock()
        mock_request = MagicMock()
        mock_request.scope = "invalid"

        with pytest.raises(HTTPException) as exc_info:
            add_dashboard_model_override(override_request=mock_request, db=mock_db, api_key="test")

        assert exc_info.value.status_code == 400
        assert "Invalid scope" in exc_info.value.detail
