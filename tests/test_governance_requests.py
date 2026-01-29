"""
Unit tests for BUILD-127 Phase 2: Governance Request Handler.

Tests:
- Auto-approval policy
- Request creation
- Request approval/denial
- Structured error generation
"""

import json
from datetime import datetime, timezone
from unittest.mock import Mock

from autopack.governance_requests import (approve_request, assess_risk_level,
                                          can_auto_approve,
                                          create_governance_request,
                                          create_protected_path_error,
                                          deny_request, get_pending_requests)


class TestAutoApprovalPolicy:
    """Test conservative auto-approval policy."""

    def test_auto_approve_test_files(self):
        """Test files should be auto-approved for low/medium risk."""
        assert can_auto_approve("tests/test_foo.py", "low") is True
        assert can_auto_approve("tests/test_bar.py", "medium") is True  # Medium is OK for tests
        assert can_auto_approve("tests/test_baz.py", "low", {"lines_changed": 50}) is True
        assert can_auto_approve("tests/test_high.py", "high") is False  # High risk blocked

    def test_auto_approve_documentation(self):
        """Documentation files should be auto-approved for low risk."""
        assert can_auto_approve("docs/README.md", "low") is True
        assert can_auto_approve("docs/BUILD_HISTORY.md", "low") is True

    def test_block_core_files(self):
        """Core autopack files should never be auto-approved."""
        assert can_auto_approve("src/autopack/models.py", "low") is False
        assert can_auto_approve("src/autopack/governed_apply.py", "low") is False
        assert can_auto_approve("src/autopack/autonomous_executor.py", "low") is False

    def test_block_high_risk(self):
        """High/critical risk should never be auto-approved."""
        assert can_auto_approve("tests/test_foo.py", "high") is False
        assert can_auto_approve("docs/README.md", "critical") is False

    def test_block_large_changes(self):
        """Large changes (>100 lines) should not be auto-approved."""
        assert can_auto_approve("tests/test_foo.py", "low", {"lines_changed": 150}) is False

    def test_block_by_default(self):
        """Unknown paths should be blocked by default."""
        assert can_auto_approve("src/my_project/foo.py", "low") is False
        assert can_auto_approve("backend/routes.py", "low") is False


class TestRiskAssessment:
    """Test risk level assessment."""

    def test_critical_risk_patterns(self):
        """Critical files should be assessed as critical risk."""
        assert assess_risk_level("src/autopack/models.py") == "critical"
        assert assess_risk_level("src/autopack/governed_apply.py") == "critical"
        assert assess_risk_level("alembic/versions/001_migration.py") == "critical"

    def test_high_risk_autopack_files(self):
        """Other autopack files should be high risk."""
        assert assess_risk_level("src/autopack/utils.py") == "high"
        assert assess_risk_level("src/autopack/helpers.py") == "high"

    def test_low_risk_test_docs(self):
        """Test and documentation files should be low risk."""
        assert assess_risk_level("tests/test_foo.py") == "low"
        assert assess_risk_level("docs/README.md") == "low"

    def test_medium_risk_default(self):
        """Unknown paths should default to medium risk."""
        assert assess_risk_level("src/my_project/foo.py") == "medium"


class TestRequestOperations:
    """Test governance request CRUD operations."""

    def test_create_request(self):
        """Test creating a governance request."""
        db_mock = Mock()
        db_mock.add = Mock()
        db_mock.commit = Mock()

        request = create_governance_request(
            db_session=db_mock,
            run_id="test-run",
            phase_id="phase-1",
            violated_paths=["tests/test_new_feature.py"],
            justification="Adding new test coverage",
            risk_scorer=None,
        )

        assert request.run_id == "test-run"
        assert request.phase_id == "phase-1"
        assert request.requested_paths == ["tests/test_new_feature.py"]
        assert request.justification == "Adding new test coverage"
        assert request.risk_level == "low"
        assert request.auto_approved is True  # Test files are auto-approved
        assert request.approved is True  # Auto-approved → immediately approved
        assert request.approved_by == "auto"

    def test_create_request_high_risk(self):
        """Test creating a high-risk request (not auto-approved)."""
        db_mock = Mock()
        db_mock.add = Mock()
        db_mock.commit = Mock()

        request = create_governance_request(
            db_session=db_mock,
            run_id="test-run",
            phase_id="phase-1",
            violated_paths=["src/autopack/models.py"],
            justification="Critical schema change",
            risk_scorer=None,
        )

        assert request.risk_level == "critical"
        assert request.auto_approved is False
        assert request.approved is None  # Pending approval
        assert request.approved_by is None

    def test_approve_request_success(self):
        """Test approving a governance request."""
        db_mock = Mock()
        request_mock = Mock()
        request_mock.request_id = "test-req-123"
        request_mock.approved = None

        db_mock.query.return_value.filter.return_value.first.return_value = request_mock
        db_mock.commit = Mock()

        success = approve_request(db_mock, "test-req-123", approved_by="human")

        assert success is True
        assert request_mock.approved is True
        assert request_mock.approved_by == "human"
        db_mock.commit.assert_called_once()

    def test_approve_request_not_found(self):
        """Test approving a non-existent request."""
        db_mock = Mock()
        db_mock.query.return_value.filter.return_value.first.return_value = None

        success = approve_request(db_mock, "nonexistent", approved_by="human")

        assert success is False

    def test_deny_request_success(self):
        """Test denying a governance request."""
        db_mock = Mock()
        request_mock = Mock()
        request_mock.request_id = "test-req-123"
        request_mock.approved = None

        db_mock.query.return_value.filter.return_value.first.return_value = request_mock
        db_mock.commit = Mock()

        success = deny_request(db_mock, "test-req-123", denied_by="human")

        assert success is True
        assert request_mock.approved is False
        assert request_mock.approved_by == "human"
        db_mock.commit.assert_called_once()

    def test_get_pending_requests(self):
        """Test fetching pending requests."""
        db_mock = Mock()
        request_mock1 = Mock()
        request_mock1.request_id = "req-1"
        request_mock1.run_id = "run-1"
        request_mock1.phase_id = "phase-1"
        request_mock1.requested_paths = json.dumps(["path1"])
        request_mock1.justification = "Test"
        request_mock1.risk_level = "low"
        request_mock1.auto_approved = False
        request_mock1.approved = None
        request_mock1.approved_by = None
        request_mock1.created_at = datetime.now(timezone.utc)

        db_mock.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            request_mock1
        ]

        pending = get_pending_requests(db_mock)

        assert len(pending) == 1
        assert pending[0].request_id == "req-1"
        assert pending[0].approved is None  # Pending


class TestStructuredError:
    """Test structured error message generation."""

    def test_create_protected_path_error(self):
        """Test creating structured error for protected paths."""
        error_json = create_protected_path_error(
            violated_paths=["src/autopack/models.py", "config/settings.py"],
            justification="Adding new field",
        )

        error_data = json.loads(error_json)

        assert error_data["error_type"] == "protected_path_violation"
        assert error_data["violated_paths"] == ["src/autopack/models.py", "config/settings.py"]
        assert error_data["justification"] == "Adding new field"
        assert error_data["requires_approval"] is True

    def test_structured_error_parsing(self):
        """Test that structured error can be parsed back."""
        error_json = create_protected_path_error(
            violated_paths=["tests/test_foo.py"], justification="Test justification"
        )

        # This is how autonomous_executor.py will parse it
        error_data = json.loads(error_json)
        assert error_data.get("error_type") == "protected_path_violation"
        assert len(error_data.get("violated_paths", [])) == 1
