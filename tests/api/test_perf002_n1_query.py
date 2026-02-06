"""Tests for N+1 query optimization in runs API routes (IMP-PERF-002).

This module verifies that the runs API routes use joinedload to eagerly
fetch related data in a single query, avoiding the N+1 query pattern.
"""

from unittest.mock import MagicMock

import pytest


class TestGetRunJoinedLoad:
    """Tests that get_run uses joinedload to avoid N+1 queries."""

    def test_get_run_uses_joinedload_for_tiers_and_phases(self):
        """Verify get_run uses joinedload to eagerly load tiers and phases."""
        from autopack.api.routes.runs import get_run

        mock_run = MagicMock()
        mock_run.id = "test-run"

        mock_db = MagicMock()
        # Set up the mock chain: query -> filter -> options -> first
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_options = MagicMock()
        mock_options.first.return_value = mock_run

        mock_query.filter.return_value = mock_filter
        mock_filter.options.return_value = mock_options
        mock_db.query.return_value = mock_query

        result = get_run(run_id="test-run", db=mock_db, _auth="test-key")

        # Verify options() was called (which contains joinedload)
        mock_filter.options.assert_called_once()
        assert result == mock_run

    def test_get_run_returns_404_when_not_found(self):
        """Verify get_run returns 404 when run is not found."""
        from fastapi import HTTPException

        from autopack.api.routes.runs import get_run

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_options = MagicMock()
        mock_options.first.return_value = None

        mock_query.filter.return_value = mock_filter
        mock_filter.options.return_value = mock_options
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            get_run(run_id="nonexistent", db=mock_db, _auth="test-key")

        assert exc_info.value.status_code == 404


class TestGetRunProgressJoinedLoad:
    """Tests that get_run_progress uses joinedload to avoid N+1 queries."""

    @pytest.mark.asyncio
    async def test_get_run_progress_uses_joinedload_for_phases(self):
        """Verify get_run_progress uses joinedload to eagerly load phases."""
        from autopack import models
        from autopack.api.routes.runs import get_run_progress

        # Create mock phases
        mock_phase1 = MagicMock()
        mock_phase1.phase_id = "phase-1"
        mock_phase1.name = "Phase 1"
        mock_phase1.state = models.PhaseState.COMPLETE
        mock_phase1.phase_index = 0
        mock_phase1.tokens_used = 100
        mock_phase1.builder_attempts = 1

        mock_phase2 = MagicMock()
        mock_phase2.phase_id = "phase-2"
        mock_phase2.name = "Phase 2"
        mock_phase2.state = models.PhaseState.QUEUED
        mock_phase2.phase_index = 1
        mock_phase2.tokens_used = 0
        mock_phase2.builder_attempts = 0

        # Create mock run with phases
        mock_run = MagicMock()
        mock_run.id = "test-run"
        mock_run.state = MagicMock()
        mock_run.state.value = "run_created"
        mock_run.started_at = None
        mock_run.completed_at = None
        mock_run.tokens_used = 100
        mock_run.token_cap = 5000000
        mock_run.phases = [mock_phase1, mock_phase2]

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_options = MagicMock()
        mock_options.first.return_value = mock_run

        mock_query.filter.return_value = mock_filter
        mock_filter.options.return_value = mock_options
        mock_db.query.return_value = mock_query

        result = await get_run_progress(run_id="test-run", db=mock_db, _auth="test-key")

        # Verify options() was called (which contains joinedload)
        mock_filter.options.assert_called_once()

        # Verify the result contains expected fields
        assert result["run_id"] == "test-run"
        assert result["phases_total"] == 2
        assert result["phases_completed"] == 1
        assert len(result["phases"]) == 2

    @pytest.mark.asyncio
    async def test_get_run_progress_single_query_for_run_and_phases(self):
        """Verify get_run_progress makes only one query for run and phases."""
        from autopack.api.routes.runs import get_run_progress

        mock_run = MagicMock()
        mock_run.id = "test-run"
        mock_run.state = MagicMock()
        mock_run.state.value = "run_created"
        mock_run.started_at = None
        mock_run.completed_at = None
        mock_run.tokens_used = 0
        mock_run.token_cap = 5000000
        mock_run.phases = []

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_options = MagicMock()
        mock_options.first.return_value = mock_run

        mock_query.filter.return_value = mock_filter
        mock_filter.options.return_value = mock_options
        mock_db.query.return_value = mock_query

        await get_run_progress(run_id="test-run", db=mock_db, _auth="test-key")

        # Verify only ONE query was made (query() called only once)
        # Before the fix, there were TWO queries: one for run, one for phases
        assert mock_db.query.call_count == 1

    @pytest.mark.asyncio
    async def test_get_run_progress_returns_404_when_not_found(self):
        """Verify get_run_progress returns 404 when run is not found."""
        from fastapi import HTTPException

        from autopack.api.routes.runs import get_run_progress

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_options = MagicMock()
        mock_options.first.return_value = None

        mock_query.filter.return_value = mock_filter
        mock_filter.options.return_value = mock_options
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            await get_run_progress(run_id="nonexistent", db=mock_db, _auth="test-key")

        assert exc_info.value.status_code == 404


class TestListRunsJoinedLoad:
    """Tests that list_runs uses joinedload to avoid N+1 queries."""

    @pytest.mark.asyncio
    async def test_list_runs_uses_joinedload_for_phases(self):
        """Verify list_runs uses joinedload to eagerly load phases."""
        from autopack.api.routes.runs import list_runs

        mock_db = MagicMock()
        mock_db.query.return_value.count.return_value = 0

        # Set up the mock chain: query -> options -> order_by -> offset -> limit -> all
        mock_query = MagicMock()
        mock_options = MagicMock()
        mock_order_by = MagicMock()
        mock_offset = MagicMock()
        mock_limit = MagicMock()
        mock_limit.all.return_value = []

        mock_query.options.return_value = mock_options
        mock_options.order_by.return_value = mock_order_by
        mock_order_by.offset.return_value = mock_offset
        mock_offset.limit.return_value = mock_limit

        # First call is for count, second is for the actual query
        mock_db.query.return_value.count.return_value = 0
        mock_db.query.return_value.options.return_value = mock_options

        await list_runs(limit=20, offset=0, db=mock_db, _auth="test-key")

        # Verify options() was called
        mock_db.query.return_value.options.assert_called()

    @pytest.mark.asyncio
    async def test_list_runs_single_query_for_runs_and_phases(self):
        """Verify list_runs fetches runs and phases in optimized query count."""
        from autopack import models
        from autopack.api.routes.runs import list_runs

        # Create mock run with phases
        mock_phase = MagicMock()
        mock_phase.state = models.PhaseState.COMPLETE
        mock_phase.phase_index = 0
        mock_phase.name = "Test Phase"

        mock_run = MagicMock()
        mock_run.id = "test-run"
        mock_run.state = MagicMock()
        mock_run.state.value = "run_created"
        mock_run.created_at = None
        mock_run.tokens_used = 0
        mock_run.token_cap = 5000000
        mock_run.phases = [mock_phase]

        mock_db = MagicMock()
        mock_db.query.return_value.count.return_value = 1
        mock_db.query.return_value.options.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            mock_run
        ]

        result = await list_runs(limit=20, offset=0, db=mock_db, _auth="test-key")

        # Verify we got the expected result
        assert result["total"] == 1
        assert len(result["runs"]) == 1
        assert result["runs"][0]["id"] == "test-run"
        assert result["runs"][0]["phases_total"] == 1
        assert result["runs"][0]["phases_completed"] == 1


class TestN1QueryPatternPrevention:
    """Integration-style tests verifying N+1 pattern is prevented."""

    @pytest.mark.asyncio
    async def test_list_runs_no_loop_queries_for_phases(self):
        """Verify list_runs doesn't query phases in a loop."""
        from autopack import models
        from autopack.api.routes.runs import list_runs

        # Create multiple mock runs with phases
        runs = []
        for i in range(5):
            mock_phase = MagicMock()
            mock_phase.state = models.PhaseState.COMPLETE
            mock_phase.phase_index = 0
            mock_phase.name = f"Phase {i}"

            mock_run = MagicMock()
            mock_run.id = f"run-{i}"
            mock_run.state = MagicMock()
            mock_run.state.value = "run_created"
            mock_run.created_at = None
            mock_run.tokens_used = 0
            mock_run.token_cap = 5000000
            mock_run.phases = [mock_phase]
            runs.append(mock_run)

        mock_db = MagicMock()
        mock_db.query.return_value.count.return_value = 5
        mock_db.query.return_value.options.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = (
            runs
        )

        result = await list_runs(limit=20, offset=0, db=mock_db, _auth="test-key")

        # Verify we got all runs
        assert len(result["runs"]) == 5

        # Key assertion: query() should only be called twice:
        # 1. Once for count
        # 2. Once for the runs query (with joinedload for phases)
        # If N+1 existed, query() would be called 7 times (2 + 5 phase queries)
        assert mock_db.query.call_count == 2

    @pytest.mark.asyncio
    async def test_get_run_progress_phases_from_run_object(self):
        """Verify get_run_progress accesses phases from run object, not separate query."""
        from autopack import models
        from autopack.api.routes.runs import get_run_progress

        mock_phase = MagicMock()
        mock_phase.phase_id = "phase-1"
        mock_phase.name = "Phase 1"
        mock_phase.state = models.PhaseState.QUEUED
        mock_phase.phase_index = 0
        mock_phase.tokens_used = 0
        mock_phase.builder_attempts = 0

        mock_run = MagicMock()
        mock_run.id = "test-run"
        mock_run.state = MagicMock()
        mock_run.state.value = "run_created"
        mock_run.started_at = None
        mock_run.completed_at = None
        mock_run.tokens_used = 0
        mock_run.token_cap = 5000000
        mock_run.phases = [mock_phase]

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_options = MagicMock()
        mock_options.first.return_value = mock_run

        mock_query.filter.return_value = mock_filter
        mock_filter.options.return_value = mock_options
        mock_db.query.return_value = mock_query

        result = await get_run_progress(run_id="test-run", db=mock_db, _auth="test-key")

        # Verify phases came from run.phases (loaded via joinedload)
        assert len(result["phases"]) == 1
        assert result["phases"][0]["phase_id"] == "phase-1"

        # Verify only ONE db.query() call was made
        assert mock_db.query.call_count == 1
