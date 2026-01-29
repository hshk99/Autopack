"""Tests for external action ledger idempotency guarantees.

Validates gap analysis requirements 6.1 and 6.9:
- Restarting mid-run cannot duplicate external writes
- Operators can query what happened for any idempotency key
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.database import Base
from autopack.external_actions import (ExternalActionLedger,
                                       ExternalActionStatus)


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def ledger(db_session):
    """Create a ledger instance for testing."""
    return ExternalActionLedger(db_session)


class TestIdempotencyGuarantees:
    """Test that duplicate actions are prevented."""

    def test_register_same_key_twice_returns_existing(self, ledger):
        """Registering the same idempotency key twice returns the existing action."""
        # First registration
        action1 = ledger.register_action(
            idempotency_key="test-publish-1",
            provider="youtube",
            action="publish",
            payload={"title": "My Video"},
        )

        # Second registration with same key
        action2 = ledger.register_action(
            idempotency_key="test-publish-1",
            provider="youtube",
            action="publish",
            payload={"title": "My Video"},
        )

        # Should return same action
        assert action1.idempotency_key == action2.idempotency_key
        assert action1.created_at == action2.created_at

    def test_completed_action_is_idempotent(self, ledger):
        """A completed action reports as completed on restart."""
        # Register and complete action
        ledger.register_action(
            idempotency_key="test-publish-2",
            provider="youtube",
            action="publish",
            payload={"title": "Video 2"},
        )
        ledger.approve_action("test-publish-2", approval_id="approval-1")
        ledger.start_execution("test-publish-2")
        ledger.complete_action("test-publish-2", response_summary="Published successfully")

        # Simulate restart: check if completed
        assert ledger.is_completed("test-publish-2") is True

        # Get action details
        action = ledger.get_action("test-publish-2")
        assert action.status == ExternalActionStatus.COMPLETED
        assert action.response_summary == "Published successfully"

    def test_in_progress_action_detected(self, ledger):
        """An executing action is detected to prevent concurrent execution."""
        ledger.register_action(
            idempotency_key="test-publish-3",
            provider="youtube",
            action="publish",
            payload={"title": "Video 3"},
        )
        ledger.start_execution("test-publish-3")

        # Should detect in-progress
        assert ledger.is_in_progress("test-publish-3") is True
        assert ledger.is_completed("test-publish-3") is False


class TestPayloadHashVerification:
    """Test that payload hash verification works correctly."""

    def test_payload_hash_computed_correctly(self, ledger):
        """Payload hash is computed deterministically."""
        payload = {"title": "Test", "tags": ["a", "b"]}

        hash1 = ledger.compute_payload_hash(payload)
        hash2 = ledger.compute_payload_hash(
            {"tags": ["a", "b"], "title": "Test"}
        )  # Different key order

        # Same content should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex length

    def test_approval_verifies_payload_hash(self, ledger):
        """Approval can verify payload hash matches."""
        action = ledger.register_action(
            idempotency_key="test-publish-4",
            provider="etsy",
            action="list",
            payload={"title": "Product"},
        )

        # Approve with correct hash
        ledger.approve_action(
            "test-publish-4",
            approval_id="approval-2",
            payload_hash=action.payload_hash,
        )

        assert ledger.get_action("test-publish-4").status == ExternalActionStatus.APPROVED

    def test_approval_rejects_mismatched_hash(self, ledger):
        """Approval fails if payload hash doesn't match."""
        ledger.register_action(
            idempotency_key="test-publish-5",
            provider="etsy",
            action="list",
            payload={"title": "Product"},
        )

        # Try to approve with wrong hash
        with pytest.raises(ValueError, match="Payload hash mismatch"):
            ledger.approve_action(
                "test-publish-5",
                approval_id="approval-3",
                payload_hash="wrong_hash",
            )


class TestQueryCapabilities:
    """Test that operators can query action history."""

    def test_query_by_provider(self, ledger):
        """Can filter actions by provider."""
        ledger.register_action(
            idempotency_key="yt-1", provider="youtube", action="publish", payload={}
        )
        ledger.register_action(idempotency_key="etsy-1", provider="etsy", action="list", payload={})

        youtube_actions = ledger.query_actions(provider="youtube")
        assert len(youtube_actions) == 1
        assert youtube_actions[0].provider == "youtube"

    def test_query_by_status(self, ledger):
        """Can filter actions by status."""
        ledger.register_action(
            idempotency_key="pending-1", provider="youtube", action="publish", payload={}
        )
        ledger.register_action(
            idempotency_key="completed-1", provider="youtube", action="publish", payload={}
        )
        ledger.start_execution("completed-1")
        ledger.complete_action("completed-1", response_summary="Done")

        pending = ledger.query_actions(status=ExternalActionStatus.PENDING)
        completed = ledger.query_actions(status=ExternalActionStatus.COMPLETED)

        assert len(pending) == 1
        assert len(completed) == 1

    def test_query_by_run_id(self, ledger):
        """Can filter actions by run ID."""
        ledger.register_action(
            idempotency_key="run1-action",
            provider="youtube",
            action="publish",
            payload={},
            run_id="run-123",
        )
        ledger.register_action(
            idempotency_key="run2-action",
            provider="youtube",
            action="publish",
            payload={},
            run_id="run-456",
        )

        run1_actions = ledger.query_actions(run_id="run-123")
        assert len(run1_actions) == 1
        assert run1_actions[0].idempotency_key == "run1-action"


class TestRetryBehavior:
    """Test that retry tracking works correctly."""

    def test_retry_count_increments(self, ledger):
        """Retry count increments on each execution attempt."""
        ledger.register_action(
            idempotency_key="retry-test",
            provider="trading",
            action="place_order",
            payload={},
            max_retries=3,
        )

        # First attempt
        ledger.start_execution("retry-test")
        assert ledger.get_action("retry-test").retry_count == 1

        # Fail and retry
        ledger.fail_action("retry-test", error_message="Network error")

        # Action should allow retry
        action = ledger.get_action("retry-test")
        assert action.can_retry() is True

        # Second attempt (status must be reset to allow start_execution)
        action.status = ExternalActionStatus.PENDING
        ledger.db.commit()
        ledger.start_execution("retry-test")
        assert ledger.get_action("retry-test").retry_count == 2

    def test_max_retries_respected(self, ledger):
        """Action cannot retry after max retries exceeded."""
        ledger.register_action(
            idempotency_key="max-retry-test",
            provider="trading",
            action="place_order",
            payload={},
            max_retries=1,
        )

        # First attempt fails
        ledger.start_execution("max-retry-test")
        ledger.fail_action("max-retry-test", error_message="Error 1")

        # Should not allow retry (retry_count=1, max_retries=1)
        action = ledger.get_action("max-retry-test")
        assert action.can_retry() is False
