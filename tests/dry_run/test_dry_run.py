"""Tests for dry-run executor service.

Tests the dry-run workflow: create -> approve -> execute with hash verification.
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from autopack.dry_run import (DryRunApproval, DryRunExecutor, DryRunResult,
                              DryRunStatus)
from autopack.dry_run.models import ExecutionResult, PredictedSideEffect


class TestDryRunResult:
    """Tests for DryRunResult model."""

    def test_compute_payload_hash_deterministic(self):
        """Same payload produces same hash."""
        payload = {"title": "Test", "value": 123}
        hash1 = DryRunResult.compute_payload_hash(payload)
        hash2 = DryRunResult.compute_payload_hash(payload)
        assert hash1 == hash2

    def test_compute_payload_hash_different_payloads(self):
        """Different payloads produce different hashes."""
        hash1 = DryRunResult.compute_payload_hash({"title": "Test1"})
        hash2 = DryRunResult.compute_payload_hash({"title": "Test2"})
        assert hash1 != hash2

    def test_compute_payload_hash_order_independent(self):
        """Key order doesn't affect hash."""
        payload1 = {"a": 1, "b": 2}
        payload2 = {"b": 2, "a": 1}
        assert DryRunResult.compute_payload_hash(payload1) == DryRunResult.compute_payload_hash(
            payload2
        )

    def test_is_valid_no_errors(self):
        """Dry-run with no validation errors is valid."""
        result = DryRunResult(
            dry_run_id="test-123",
            provider="youtube",
            action="publish",
            payload={"title": "Test"},
            payload_hash="abc123",
            predicted_effects=[],
            created_at=datetime.now(timezone.utc),
            status=DryRunStatus.PENDING,
        )
        assert result.is_valid() is True

    def test_is_valid_with_errors(self):
        """Dry-run with validation errors is invalid."""
        result = DryRunResult(
            dry_run_id="test-123",
            provider="youtube",
            action="publish",
            payload={"title": "Test"},
            payload_hash="abc123",
            predicted_effects=[],
            created_at=datetime.now(timezone.utc),
            status=DryRunStatus.PENDING,
            validation_errors=["Missing required field"],
        )
        assert result.is_valid() is False

    def test_to_dict_and_from_dict(self):
        """Round-trip serialization works."""
        original = DryRunResult(
            dry_run_id="test-123",
            provider="youtube",
            action="publish",
            payload={"title": "Test Video"},
            payload_hash="abc123def456",
            predicted_effects=[
                PredictedSideEffect(
                    effect_type="create",
                    target="youtube:video",
                    description="Creates a new video",
                )
            ],
            created_at=datetime.now(timezone.utc),
            status=DryRunStatus.PENDING,
            validation_errors=[],
            warnings=["Consider adding tags"],
            requires_confirmation=True,
            run_id="run-001",
            phase_number=2,
        )

        data = original.to_dict()
        restored = DryRunResult.from_dict(data)

        assert restored.dry_run_id == original.dry_run_id
        assert restored.provider == original.provider
        assert restored.action == original.action
        assert restored.payload == original.payload
        assert restored.status == original.status
        assert len(restored.predicted_effects) == 1
        assert restored.predicted_effects[0].effect_type == "create"


class TestDryRunApproval:
    """Tests for DryRunApproval model."""

    def test_is_expired_false(self):
        """Non-expired approval returns False."""
        approval = DryRunApproval(
            approval_id="approval-123",
            dry_run_id="dryrun-123",
            approved_payload_hash="hash123",
            approved_by="admin",
            approved_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        )
        assert approval.is_expired() is False

    def test_is_expired_true(self):
        """Expired approval returns True."""
        approval = DryRunApproval(
            approval_id="approval-123",
            dry_run_id="dryrun-123",
            approved_payload_hash="hash123",
            approved_by="admin",
            approved_at=datetime.now(timezone.utc) - timedelta(hours=48),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=24),
        )
        assert approval.is_expired() is True

    def test_is_expired_no_expiry(self):
        """Approval without expiry never expires."""
        approval = DryRunApproval(
            approval_id="approval-123",
            dry_run_id="dryrun-123",
            approved_payload_hash="hash123",
            approved_by="admin",
            approved_at=datetime.now(timezone.utc),
            expires_at=None,
        )
        assert approval.is_expired() is False

    def test_matches_payload(self):
        """matches_payload verifies hash."""
        approval = DryRunApproval(
            approval_id="approval-123",
            dry_run_id="dryrun-123",
            approved_payload_hash="correct_hash",
            approved_by="admin",
            approved_at=datetime.now(timezone.utc),
        )
        assert approval.matches_payload("correct_hash") is True
        assert approval.matches_payload("wrong_hash") is False

    def test_to_dict(self):
        """to_dict includes all fields."""
        approval = DryRunApproval(
            approval_id="approval-123",
            dry_run_id="dryrun-123",
            approved_payload_hash="hash123",
            approved_by="admin",
            approved_at=datetime.now(timezone.utc),
            notes="Looks good",
            execution_window_hours=48,
        )
        data = approval.to_dict()
        assert data["approval_id"] == "approval-123"
        assert data["approved_by"] == "admin"
        assert data["notes"] == "Looks good"
        assert data["execution_window_hours"] == 48


class TestDryRunExecutor:
    """Tests for DryRunExecutor service."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def executor(self, temp_storage):
        """Create executor with temp storage."""
        return DryRunExecutor(storage_dir=temp_storage)

    def test_create_dry_run(self, executor):
        """create_dry_run returns result with hash."""
        result = executor.create_dry_run(
            provider="youtube",
            action="publish",
            payload={"title": "Test Video"},
            predicted_effects=[
                PredictedSideEffect(
                    effect_type="create",
                    target="youtube:video",
                    description="Creates a video",
                )
            ],
        )

        assert result.dry_run_id.startswith("dryrun-")
        assert result.provider == "youtube"
        assert result.action == "publish"
        assert result.status == DryRunStatus.PENDING
        assert len(result.payload_hash) == 64  # SHA-256 hex

    def test_create_dry_run_with_validation_errors(self, executor):
        """create_dry_run accepts validation errors."""
        result = executor.create_dry_run(
            provider="etsy",
            action="list",
            payload={"title": ""},
            validation_errors=["Title is required"],
        )

        assert result.validation_errors == ["Title is required"]
        assert result.is_valid() is False

    def test_get_dry_run(self, executor):
        """get_dry_run retrieves by ID."""
        created = executor.create_dry_run(
            provider="shopify",
            action="update",
            payload={"id": "123"},
        )

        retrieved = executor.get_dry_run(created.dry_run_id)
        assert retrieved is not None
        assert retrieved.dry_run_id == created.dry_run_id

    def test_get_dry_run_not_found(self, executor):
        """get_dry_run returns None for unknown ID."""
        assert executor.get_dry_run("nonexistent") is None

    def test_approve_dry_run(self, executor):
        """approve creates approval record."""
        result = executor.create_dry_run(
            provider="youtube",
            action="publish",
            payload={"title": "Test"},
        )

        approval = executor.approve(result.dry_run_id, approved_by="operator")

        assert approval.approval_id.startswith("approval-")
        assert approval.dry_run_id == result.dry_run_id
        assert approval.approved_payload_hash == result.payload_hash
        assert approval.approved_by == "operator"

        # Dry-run status should be updated
        updated = executor.get_dry_run(result.dry_run_id)
        assert updated.status == DryRunStatus.APPROVED

    def test_approve_not_found(self, executor):
        """approve raises for unknown dry-run."""
        with pytest.raises(ValueError, match="not found"):
            executor.approve("nonexistent", approved_by="admin")

    def test_approve_with_validation_errors(self, executor):
        """approve raises for dry-run with validation errors."""
        result = executor.create_dry_run(
            provider="youtube",
            action="publish",
            payload={"title": ""},
            validation_errors=["Title required"],
        )

        with pytest.raises(ValueError, match="validation errors"):
            executor.approve(result.dry_run_id, approved_by="admin")

    def test_approve_already_approved(self, executor):
        """approve raises for already approved dry-run."""
        result = executor.create_dry_run(
            provider="youtube",
            action="publish",
            payload={"title": "Test"},
        )
        executor.approve(result.dry_run_id, approved_by="admin")

        with pytest.raises(ValueError, match="not pending"):
            executor.approve(result.dry_run_id, approved_by="admin")

    def test_reject_dry_run(self, executor):
        """reject updates status."""
        result = executor.create_dry_run(
            provider="youtube",
            action="publish",
            payload={"title": "Test"},
        )

        rejected = executor.reject(result.dry_run_id, rejected_by="admin", reason="Not ready")

        assert rejected.status == DryRunStatus.REJECTED

    def test_execute_success(self, executor):
        """execute runs action with matching hash."""
        payload = {"title": "Test Video", "description": "A test"}

        result = executor.create_dry_run(
            provider="youtube",
            action="publish",
            payload=payload,
        )
        approval = executor.approve(result.dry_run_id, approved_by="admin")

        def mock_executor(provider, action, payload):
            return {"video_id": "abc123", "status": "published"}

        execution = executor.execute(
            result.dry_run_id,
            approval.approval_id,
            payload=payload,  # Same payload
            executor_fn=mock_executor,
        )

        assert execution.success is True
        assert execution.dry_run_id == result.dry_run_id
        assert execution.approval_id == approval.approval_id
        assert "abc123" in execution.response_summary

        # Dry-run status should be EXECUTED
        updated = executor.get_dry_run(result.dry_run_id)
        assert updated.status == DryRunStatus.EXECUTED

    def test_execute_hash_mismatch(self, executor):
        """execute raises on payload hash mismatch."""
        original_payload = {"title": "Original"}

        result = executor.create_dry_run(
            provider="youtube",
            action="publish",
            payload=original_payload,
        )
        approval = executor.approve(result.dry_run_id, approved_by="admin")

        modified_payload = {"title": "Modified"}  # Different payload

        with pytest.raises(ValueError, match="hash mismatch"):
            executor.execute(
                result.dry_run_id,
                approval.approval_id,
                payload=modified_payload,
                executor_fn=lambda p, a, pl: {},
            )

        # Status should be HASH_MISMATCH
        updated = executor.get_dry_run(result.dry_run_id)
        assert updated.status == DryRunStatus.HASH_MISMATCH

    def test_execute_expired_approval(self, executor):
        """execute raises on expired approval."""
        payload = {"title": "Test"}

        result = executor.create_dry_run(
            provider="youtube",
            action="publish",
            payload=payload,
        )
        # Approve with very short expiry
        approval = executor.approve(result.dry_run_id, approved_by="admin", expiry_hours=0)
        # Manually expire it
        approval.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        with pytest.raises(ValueError, match="expired"):
            executor.execute(
                result.dry_run_id,
                approval.approval_id,
                payload=payload,
                executor_fn=lambda p, a, pl: {},
            )

    def test_execute_wrong_approval(self, executor):
        """execute raises when approval doesn't match dry-run."""
        payload1 = {"title": "Test1"}
        payload2 = {"title": "Test2"}

        result1 = executor.create_dry_run(provider="youtube", action="publish", payload=payload1)
        result2 = executor.create_dry_run(provider="youtube", action="publish", payload=payload2)

        approval1 = executor.approve(result1.dry_run_id, approved_by="admin")
        executor.approve(result2.dry_run_id, approved_by="admin")

        # Try to use approval1 with result2
        with pytest.raises(ValueError, match="does not match"):
            executor.execute(
                result2.dry_run_id,
                approval1.approval_id,
                payload=payload2,
                executor_fn=lambda p, a, pl: {},
            )

    def test_execute_failure_recorded(self, executor):
        """execute records failure when executor raises."""
        payload = {"title": "Test"}

        result = executor.create_dry_run(
            provider="youtube",
            action="publish",
            payload=payload,
        )
        approval = executor.approve(result.dry_run_id, approved_by="admin")

        def failing_executor(provider, action, payload):
            raise RuntimeError("API error")

        execution = executor.execute(
            result.dry_run_id,
            approval.approval_id,
            payload=payload,
            executor_fn=failing_executor,
        )

        assert execution.success is False
        assert "API error" in execution.error_message

    def test_get_pending_dry_runs(self, executor):
        """get_pending_dry_runs filters correctly."""
        executor.create_dry_run(provider="youtube", action="publish", payload={"a": 1})
        executor.create_dry_run(provider="etsy", action="list", payload={"b": 2})
        result3 = executor.create_dry_run(provider="youtube", action="update", payload={"c": 3})
        executor.approve(result3.dry_run_id, approved_by="admin")

        # All pending
        all_pending = executor.get_pending_dry_runs()
        assert len(all_pending) == 2

        # YouTube only
        youtube_pending = executor.get_pending_dry_runs(provider="youtube")
        assert len(youtube_pending) == 1
        assert youtube_pending[0].provider == "youtube"

    def test_get_approved_dry_runs(self, executor):
        """get_approved_dry_runs returns approved with approvals."""
        result1 = executor.create_dry_run(provider="youtube", action="publish", payload={"a": 1})
        result2 = executor.create_dry_run(provider="etsy", action="list", payload={"b": 2})
        executor.create_dry_run(provider="shopify", action="update", payload={"c": 3})

        executor.approve(result1.dry_run_id, approved_by="admin")
        executor.approve(result2.dry_run_id, approved_by="admin")

        approved = executor.get_approved_dry_runs()
        assert len(approved) == 2

        # Filter by provider
        youtube_approved = executor.get_approved_dry_runs(provider="youtube")
        assert len(youtube_approved) == 1
        assert youtube_approved[0][0].provider == "youtube"

    def test_persistence(self, temp_storage):
        """State persists across executor instances."""
        payload = {"title": "Persistent Test"}

        # Create and approve with first executor
        executor1 = DryRunExecutor(storage_dir=temp_storage)
        result = executor1.create_dry_run(
            provider="youtube",
            action="publish",
            payload=payload,
        )
        approval = executor1.approve(result.dry_run_id, approved_by="admin")

        # Load with new executor instance
        executor2 = DryRunExecutor(storage_dir=temp_storage)

        # Should find the dry-run
        loaded_result = executor2.get_dry_run(result.dry_run_id)
        assert loaded_result is not None
        assert loaded_result.status == DryRunStatus.APPROVED

        # Should find the approval
        loaded_approval = executor2.get_approval(approval.approval_id)
        assert loaded_approval is not None
        assert loaded_approval.approved_by == "admin"

    def test_save_artifact(self, executor, temp_storage):
        """save_artifact creates JSON file."""
        result = executor.create_dry_run(
            provider="youtube",
            action="publish",
            payload={"title": "Artifact Test"},
        )
        approval = executor.approve(result.dry_run_id, approved_by="admin")

        artifact_path = executor.save_artifact(result.dry_run_id)

        assert artifact_path.exists()
        data = json.loads(artifact_path.read_text())
        assert data["dry_run"]["dry_run_id"] == result.dry_run_id
        assert data["approval"]["approval_id"] == approval.approval_id


class TestPredictedSideEffect:
    """Tests for PredictedSideEffect model."""

    def test_to_dict(self):
        """to_dict includes all fields."""
        effect = PredictedSideEffect(
            effect_type="create",
            target="youtube:video",
            description="Creates a video",
            reversible=False,
            estimated_cost=0.50,
            metadata={"platform": "youtube"},
        )
        data = effect.to_dict()
        assert data["effect_type"] == "create"
        assert data["target"] == "youtube:video"
        assert data["reversible"] is False
        assert data["estimated_cost"] == 0.50
        assert data["metadata"] == {"platform": "youtube"}


class TestExecutionResult:
    """Tests for ExecutionResult model."""

    def test_to_dict_success(self):
        """to_dict for successful execution."""
        result = ExecutionResult(
            execution_id="exec-123",
            dry_run_id="dryrun-123",
            approval_id="approval-123",
            executed_at=datetime.now(timezone.utc),
            success=True,
            response_summary="Video published successfully",
            duration_seconds=1.5,
        )
        data = result.to_dict()
        assert data["success"] is True
        assert data["response_summary"] == "Video published successfully"
        assert data["duration_seconds"] == 1.5

    def test_to_dict_failure(self):
        """to_dict for failed execution."""
        result = ExecutionResult(
            execution_id="exec-456",
            dry_run_id="dryrun-456",
            approval_id="approval-456",
            executed_at=datetime.now(timezone.utc),
            success=False,
            error_message="API rate limit exceeded",
            duration_seconds=0.1,
        )
        data = result.to_dict()
        assert data["success"] is False
        assert data["error_message"] == "API rate limit exceeded"
