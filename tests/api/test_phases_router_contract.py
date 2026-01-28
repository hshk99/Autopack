"""Contract tests for phases router.

These tests verify the phases router behavior contract is preserved
during the extraction from main.py to api/routes/phases.py (PR-API-3h).
"""

import pytest


class TestPhasesRouterContract:
    """Contract tests for phases router configuration."""

    def test_router_has_phases_tag(self):
        """Contract: Phases router is tagged as 'phases'."""
        from autopack.api.routes.phases import router

        assert "phases" in router.tags


class TestUpdatePhaseStatusContract:
    """Contract tests for update_phase_status endpoint."""

    def test_update_status_returns_404_for_missing_phase(self):
        """Contract: /runs/{run_id}/phases/{phase_id}/update_status returns 404 for missing phase."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.phases import update_phase_status
        from autopack.schemas import PhaseStatusUpdate

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        update = PhaseStatusUpdate(state="executing")

        with pytest.raises(HTTPException) as exc_info:
            update_phase_status(
                run_id="test-run",
                phase_id="nonexistent",
                update=update,
                db=mock_db,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_update_status_rejects_invalid_state(self):
        """Contract: /runs/{run_id}/phases/{phase_id}/update_status rejects invalid state."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.phases import update_phase_status
        from autopack.schemas import PhaseStatusUpdate

        mock_phase = MagicMock()
        mock_phase.run_id = "test-run"
        mock_phase.phase_id = "test-phase"

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_phase
        mock_db.query.return_value = mock_query

        update = PhaseStatusUpdate(state="invalid_state")

        with pytest.raises(HTTPException) as exc_info:
            update_phase_status(
                run_id="test-run",
                phase_id="test-phase",
                update=update,
                db=mock_db,
            )

        assert exc_info.value.status_code == 400
        assert "invalid phase state" in exc_info.value.detail.lower()


class TestRecordPhaseIssueContract:
    """Contract tests for record_phase_issue endpoint."""

    def test_record_issue_returns_404_for_missing_phase(self):
        """Contract: /runs/{run_id}/phases/{phase_id}/record_issue returns 404 for missing phase."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.phases import record_phase_issue

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.options.return_value = mock_query  # Support .options() chaining (IMP-PERF-001)
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            record_phase_issue(
                run_id="test-run",
                phase_id="nonexistent",
                issue_key="test-issue",
                severity="minor",
                source="test",
                category="test",
                db=mock_db,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_record_issue_returns_404_for_missing_tier(self):
        """Contract: /runs/{run_id}/phases/{phase_id}/record_issue returns 404 for missing tier."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.phases import record_phase_issue

        mock_phase = MagicMock()
        mock_phase.run_id = "test-run"
        mock_phase.phase_id = "test-phase"
        mock_phase.tier_id = 999
        mock_phase.tier = None  # Eager-loaded tier is None (IMP-PERF-001)

        mock_db = MagicMock()

        # Query returns phase with tier=None (eager-loaded via joinedload)
        mock_query = MagicMock()
        mock_query.options.return_value = mock_query  # Support .options() chaining
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase
        mock_db.query.return_value = mock_query

        with pytest.raises(HTTPException) as exc_info:
            record_phase_issue(
                run_id="test-run",
                phase_id="test-phase",
                issue_key="test-issue",
                severity="minor",
                source="test",
                category="test",
                db=mock_db,
            )

        assert exc_info.value.status_code == 404
        assert "tier not found" in exc_info.value.detail.lower()


class TestSubmitBuilderResultContract:
    """Contract tests for submit_builder_result endpoint."""

    def test_builder_result_returns_404_for_missing_phase(self):
        """Contract: /runs/{run_id}/phases/{phase_id}/builder_result returns 404 for missing phase."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.phases import submit_builder_result
        from autopack.builder_schemas import BuilderResult

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.options.return_value = mock_query  # Support .options() chaining (IMP-PERF-001)
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = None
        mock_db.query.return_value = mock_query

        builder_result = BuilderResult(
            run_id="test-run",
            phase_id="nonexistent",
            status="success",
            builder_attempts=1,
            tokens_used=100,
        )

        with pytest.raises(HTTPException) as exc_info:
            submit_builder_result(
                run_id="test-run",
                phase_id="nonexistent",
                builder_result=builder_result,
                db=mock_db,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_builder_result_updates_phase_tokens(self):
        """Contract: /runs/{run_id}/phases/{phase_id}/builder_result updates phase tokens."""
        from unittest.mock import MagicMock

        from autopack.api.routes.phases import submit_builder_result
        from autopack.builder_schemas import BuilderResult

        mock_phase = MagicMock()
        mock_phase.run_id = "test-run"
        mock_phase.phase_id = "test-phase"
        mock_phase.tier_id = 1
        mock_phase.tier = MagicMock()  # Eager-loaded tier (IMP-PERF-001)
        mock_phase.tier.tier_id = "T1"
        mock_phase.state = MagicMock()
        mock_phase.state.value = "complete"

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.options.return_value = mock_query  # Support .options() chaining (IMP-PERF-001)
        mock_query.filter.return_value = mock_query
        mock_query.first.return_value = mock_phase
        mock_db.query.return_value = mock_query

        builder_result = BuilderResult(
            run_id="test-run",
            phase_id="test-phase",
            status="success",
            builder_attempts=3,
            tokens_used=5000,
        )

        result = submit_builder_result(
            run_id="test-run",
            phase_id="test-phase",
            builder_result=builder_result,
            db=mock_db,
        )

        # Verify phase was updated
        assert mock_phase.builder_attempts == 3
        assert mock_phase.tokens_used == 5000
        assert "message" in result
        assert "phase_id" in result


class TestSubmitAuditorResultContract:
    """Contract tests for submit_auditor_result endpoint."""

    def test_auditor_result_rejects_mismatched_ids(self):
        """Contract: /runs/{run_id}/phases/{phase_id}/auditor_result rejects mismatched IDs."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.phases import submit_auditor_result
        from autopack.builder_schemas import AuditorResult

        mock_db = MagicMock()

        auditor_result = AuditorResult(
            run_id="different-run",  # Doesn't match path
            phase_id="test-phase",
            review_notes="Test review",
            recommendation="approve",
            issues_found=[],
        )

        with pytest.raises(HTTPException) as exc_info:
            submit_auditor_result(
                run_id="test-run",
                phase_id="test-phase",
                auditor_result=auditor_result,
                db=mock_db,
            )

        assert exc_info.value.status_code == 400
        assert "must match" in exc_info.value.detail.lower()

    def test_auditor_result_returns_404_for_missing_phase(self):
        """Contract: /runs/{run_id}/phases/{phase_id}/auditor_result returns 404 for missing phase."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from autopack.api.routes.phases import submit_auditor_result
        from autopack.builder_schemas import AuditorResult

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        auditor_result = AuditorResult(
            run_id="test-run",
            phase_id="nonexistent",
            review_notes="Test review",
            recommendation="approve",
            issues_found=[],
        )

        with pytest.raises(HTTPException) as exc_info:
            submit_auditor_result(
                run_id="test-run",
                phase_id="nonexistent",
                auditor_result=auditor_result,
                db=mock_db,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_auditor_result_returns_success_message(self):
        """Contract: /runs/{run_id}/phases/{phase_id}/auditor_result returns success message."""
        from unittest.mock import MagicMock

        from autopack.api.routes.phases import submit_auditor_result
        from autopack.builder_schemas import AuditorResult

        mock_phase = MagicMock()
        mock_phase.run_id = "test-run"
        mock_phase.phase_id = "test-phase"
        mock_phase.auditor_attempts = 0
        mock_phase.tokens_used = 0

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_phase
        mock_db.query.return_value = mock_query

        auditor_result = AuditorResult(
            run_id="test-run",
            phase_id="test-phase",
            review_notes="Test review",
            recommendation="approve",
            issues_found=[],
            auditor_attempts=1,
            tokens_used=500,
        )

        result = submit_auditor_result(
            run_id="test-run",
            phase_id="test-phase",
            auditor_result=auditor_result,
            db=mock_db,
        )

        assert "message" in result
        assert "auditor result submitted" in result["message"].lower()
