"""Contract tests for runs router.

These tests verify the runs router behavior contract is preserved
during the extraction from main.py to api/routes/runs.py (PR-API-3i).
"""

import pytest
from unittest.mock import MagicMock, patch


class TestRunsRouterContract:
    """Contract tests for runs router configuration."""

    def test_router_has_runs_tag(self):
        """Contract: Runs router is tagged as 'runs'."""
        from autopack.api.routes.runs import router

        assert "runs" in router.tags


class TestGetRunContract:
    """Contract tests for get_run endpoint."""

    def test_get_run_returns_404_for_missing_run(self):
        """Contract: GET /runs/{run_id} returns 404 for missing run."""
        from fastapi import HTTPException

        from autopack.api.routes.runs import get_run

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_run(run_id="nonexistent", db=mock_db, _auth="test-key")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_get_run_returns_run_object(self):
        """Contract: GET /runs/{run_id} returns run when found."""
        from autopack.api.routes.runs import get_run

        mock_run = MagicMock()
        mock_run.id = "test-run"

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_run
        mock_db.query.return_value = mock_query

        result = get_run(run_id="test-run", db=mock_db, _auth="test-key")

        assert result == mock_run


class TestGetRunIssueIndexContract:
    """Contract tests for get_run_issue_index endpoint."""

    def test_issue_index_returns_dict(self):
        """Contract: GET /runs/{run_id}/issues/index returns dict."""
        from autopack.api.routes.runs import get_run_issue_index

        with patch("autopack.api.routes.runs.IssueTracker") as MockTracker:
            mock_tracker = MagicMock()
            mock_index = MagicMock()
            mock_index.model_dump.return_value = {"issues": [], "total": 0}
            mock_tracker.load_run_issue_index.return_value = mock_index
            MockTracker.return_value = mock_tracker

            result = get_run_issue_index(run_id="test-run", _auth="test-key")

            assert isinstance(result, dict)
            assert "issues" in result


class TestGetProjectBacklogContract:
    """Contract tests for get_project_backlog endpoint."""

    def test_backlog_returns_dict(self):
        """Contract: GET /project/issues/backlog returns dict."""
        from autopack.api.routes.runs import get_project_backlog

        with patch("autopack.api.routes.runs.IssueTracker") as MockTracker:
            mock_tracker = MagicMock()
            mock_backlog = MagicMock()
            mock_backlog.model_dump.return_value = {"backlog": [], "total": 0}
            mock_tracker.load_project_backlog.return_value = mock_backlog
            MockTracker.return_value = mock_tracker

            result = get_project_backlog(_auth="test-key")

            assert isinstance(result, dict)


class TestGetRunErrorsContract:
    """Contract tests for get_run_errors endpoint."""

    def test_errors_returns_dict_with_run_id(self):
        """Contract: GET /runs/{run_id}/errors returns dict with run_id."""
        from autopack.api.routes.runs import get_run_errors

        # Patch at the source module, not the importing module
        with patch("autopack.error_reporter.get_error_reporter") as mock_get_reporter:
            mock_reporter = MagicMock()
            mock_reporter.get_run_errors.return_value = []
            mock_get_reporter.return_value = mock_reporter

            result = get_run_errors(run_id="test-run", _auth="test-key")

            assert result["run_id"] == "test-run"
            assert "error_count" in result
            assert "errors" in result


class TestGetRunErrorSummaryContract:
    """Contract tests for get_run_error_summary endpoint."""

    def test_error_summary_returns_dict_with_run_id(self):
        """Contract: GET /runs/{run_id}/errors/summary returns dict with run_id."""
        from autopack.api.routes.runs import get_run_error_summary

        # Patch at the source module, not the importing module
        with patch("autopack.error_reporter.get_error_reporter") as mock_get_reporter:
            mock_reporter = MagicMock()
            mock_reporter.generate_run_error_summary.return_value = "No errors"
            mock_get_reporter.return_value = mock_reporter

            result = get_run_error_summary(run_id="test-run", _auth="test-key")

            assert result["run_id"] == "test-run"
            assert "summary" in result


class TestListRunsContract:
    """Contract tests for list_runs endpoint."""

    @pytest.mark.asyncio
    async def test_list_runs_returns_pagination_fields(self):
        """Contract: GET /runs returns dict with pagination fields."""
        from autopack.api.routes.runs import list_runs

        mock_db = MagicMock()
        mock_db.query.return_value.count.return_value = 0
        mock_db.query.return_value.options.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = (
            []
        )

        result = await list_runs(limit=20, offset=0, db=mock_db, _auth="test-key")

        assert "runs" in result
        assert "total" in result
        assert "limit" in result
        assert "offset" in result

    @pytest.mark.asyncio
    async def test_list_runs_clamps_limit(self):
        """Contract: GET /runs clamps limit to [1, 100]."""
        from autopack.api.routes.runs import list_runs

        mock_db = MagicMock()
        mock_db.query.return_value.count.return_value = 0
        mock_db.query.return_value.options.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = (
            []
        )

        # Test upper bound
        result = await list_runs(limit=200, offset=0, db=mock_db, _auth="test-key")
        assert result["limit"] == 100

        # Test lower bound
        result = await list_runs(limit=0, offset=0, db=mock_db, _auth="test-key")
        assert result["limit"] == 1


class TestGetRunProgressContract:
    """Contract tests for get_run_progress endpoint."""

    @pytest.mark.asyncio
    async def test_progress_returns_404_for_missing_run(self):
        """Contract: GET /runs/{run_id}/progress returns 404 for missing run."""
        from fastapi import HTTPException

        from autopack.api.routes.runs import get_run_progress

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            await get_run_progress(run_id="nonexistent", db=mock_db, _auth="test-key")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_progress_returns_expected_fields(self):
        """Contract: GET /runs/{run_id}/progress returns expected fields."""
        from autopack.api.routes.runs import get_run_progress
        from autopack import models

        mock_run = MagicMock()
        mock_run.id = "test-run"
        mock_run.state = MagicMock()
        mock_run.state.value = "run_created"
        mock_run.started_at = None
        mock_run.completed_at = None
        mock_run.tokens_used = 1000
        mock_run.token_cap = 5000000

        mock_db = MagicMock()

        # First query returns run, second returns phases
        call_count = [0]

        def query_side_effect(model):
            call_count[0] += 1
            mock_query = MagicMock()
            if model == models.Run:
                mock_query.filter.return_value.first.return_value = mock_run
            else:  # Phase
                mock_query.filter.return_value.order_by.return_value.all.return_value = []
            return mock_query

        mock_db.query.side_effect = query_side_effect

        result = await get_run_progress(run_id="test-run", db=mock_db, _auth="test-key")

        assert result["run_id"] == "test-run"
        assert "state" in result
        assert "phases_total" in result
        assert "phases_completed" in result
        assert "phases_in_progress" in result
        assert "phases_pending" in result
        assert "phases" in result


class TestStartRunContract:
    """Contract tests for start_run endpoint."""

    def test_start_run_rejects_duplicate_run_id(self):
        """Contract: POST /runs/start returns 400 for duplicate run_id."""
        from fastapi import HTTPException
        from starlette.requests import Request

        from autopack.api.routes.runs import start_run
        from autopack import schemas

        mock_existing_run = MagicMock()

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_existing_run
        mock_db.query.return_value = mock_query

        # Create a real Starlette Request for rate limiter compatibility
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
                run_id="existing-run",
                safety_profile="normal",
                run_scope="full",
            ),
            tiers=[],
            phases=[],
        )

        with pytest.raises(HTTPException) as exc_info:
            start_run(request_data=request_data, request=request, db=mock_db)

        assert exc_info.value.status_code == 400
        assert "already exists" in exc_info.value.detail.lower()

    def test_start_run_rejects_invalid_tier_reference(self):
        """Contract: POST /runs/start returns 400 for phase with unknown tier_id."""
        from fastapi import HTTPException
        from starlette.requests import Request

        from autopack.api.routes.runs import start_run
        from autopack import schemas

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None  # No existing run
        mock_db.query.return_value = mock_query

        # Create a real Starlette Request for rate limiter compatibility
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
                run_id="new-run",
                safety_profile="normal",
                run_scope="full",
            ),
            tiers=[],  # No tiers defined
            phases=[
                schemas.PhaseCreate(
                    phase_id="phase-1",
                    tier_id="unknown-tier",  # References unknown tier
                    phase_index=0,
                    name="Test Phase",
                    task_category="test",
                    complexity="low",
                    builder_mode="autonomous",
                    scope=None,  # scope is Optional[Dict[str, Any]]
                )
            ],
        )

        with pytest.raises(HTTPException) as exc_info:
            start_run(request_data=request_data, request=request, db=mock_db)

        assert exc_info.value.status_code == 400
        assert "unknown tier" in exc_info.value.detail.lower()

    def test_start_run_rejects_invalid_token_cap(self):
        """Contract: POST /runs/start rejects token_cap < 1."""
        from pydantic import ValidationError

        from autopack import schemas

        # Test that zero token_cap is rejected
        with pytest.raises(ValidationError) as exc_info:
            schemas.RunCreate(
                run_id="test-run",
                safety_profile="normal",
                run_scope="full",
                token_cap=0,
            )

        errors = exc_info.value.errors()
        assert any("greater than or equal to 1" in str(e).lower() for e in errors)

    def test_start_run_rejects_invalid_max_phases(self):
        """Contract: POST /runs/start rejects max_phases < 1."""
        from pydantic import ValidationError

        from autopack import schemas

        # Test that zero max_phases is rejected
        with pytest.raises(ValidationError) as exc_info:
            schemas.RunCreate(
                run_id="test-run",
                safety_profile="normal",
                run_scope="full",
                max_phases=0,
            )

        errors = exc_info.value.errors()
        assert any("greater than or equal to 1" in str(e).lower() for e in errors)

    def test_start_run_rejects_invalid_max_duration(self):
        """Contract: POST /runs/start rejects max_duration_minutes < 1."""
        from pydantic import ValidationError

        from autopack import schemas

        # Test that zero max_duration_minutes is rejected
        with pytest.raises(ValidationError) as exc_info:
            schemas.RunCreate(
                run_id="test-run",
                safety_profile="normal",
                run_scope="full",
                max_duration_minutes=0,
            )

        errors = exc_info.value.errors()
        assert any("greater than or equal to 1" in str(e).lower() for e in errors)
