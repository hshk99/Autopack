"""Tests for Telegram webhook PR callback handling.

Per IMPLEMENTATION_PLAN_PR_APPROVAL_PIPELINE.md minimal test coverage:
- PR callback parsing
- Approval request update by approval_id
- Idempotent callback handling
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from autopack.database import Base, get_db
from autopack.main import app
from autopack.models import ApprovalRequest


@pytest.fixture
def test_db():
    """Create in-memory test database (thread-safe for TestClient)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def db_session(test_db):
    """Create database session for direct DB access."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(test_db):
    """Create TestClient with DB dependency overridden to use in-memory DB."""
    import os

    # Save current state for cleanup
    old_testing = os.environ.get("TESTING")
    old_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    old_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")

    # Ensure app lifespan does not attempt production init_db() checks
    os.environ["TESTING"] = "1"
    # Clear any TELEGRAM_WEBHOOK_SECRET to avoid verification in tests
    os.environ.pop("TELEGRAM_WEBHOOK_SECRET", None)
    # Set bot token so answer_telegram_callback code path is triggered
    os.environ["TELEGRAM_BOT_TOKEN"] = "test-bot-token"  # gitleaks:allow

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_db)

    def override_get_db():
        try:
            db = SessionLocal()
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        # Restore environment
        if old_testing is not None:
            os.environ["TESTING"] = old_testing
        else:
            os.environ.pop("TESTING", None)
        if old_secret is not None:
            os.environ["TELEGRAM_WEBHOOK_SECRET"] = old_secret
        if old_bot_token is not None:
            os.environ["TELEGRAM_BOT_TOKEN"] = old_bot_token
        else:
            os.environ.pop("TELEGRAM_BOT_TOKEN", None)


@pytest.fixture
def approval_request(db_session):
    """Create a test approval request."""
    req = ApprovalRequest(
        run_id="test-run-pr",
        phase_id="pr-create-test-run-pr",
        context="PR_CREATE",
        decision_info={
            "type": "PR_CREATE",
            "branch": "feat/test",
            "title": "Test PR",
        },
        status="pending",
        requested_at=datetime.now(timezone.utc),
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)
    return req


def test_pr_approve_callback(client, db_session, approval_request):
    """Test pr_approve callback updates approval request."""

    # Mock Telegram callback payload
    callback_payload = {
        "callback_query": {
            "id": "test-callback-123",
            "data": f"pr_approve:{approval_request.id}",
            "from": {
                "id": 12345,
                "username": "testuser",
            },
            "message": {
                "message_id": 42,
                "chat": {"id": 12345},
            },
        }
    }

    # Mock answer_telegram_callback to avoid actual Telegram API calls
    with patch("autopack.main.answer_telegram_callback"):
        response = client.post("/telegram/webhook", json=callback_payload)

    # Verify response
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["action"] == "approve"

    # Verify database update
    db_session.refresh(approval_request)
    assert approval_request.status == "approved"
    assert approval_request.response_method == "telegram"
    assert approval_request.approval_reason == "Approved by Telegram user @testuser"
    assert approval_request.responded_at is not None


def test_pr_reject_callback(client, db_session, approval_request):
    """Test pr_reject callback updates approval request."""
    callback_payload = {
        "callback_query": {
            "id": "test-callback-456",
            "data": f"pr_reject:{approval_request.id}",
            "from": {
                "id": 12345,
                "username": "testuser",
            },
            "message": {
                "message_id": 42,
                "chat": {"id": 12345},
            },
        }
    }

    with patch("autopack.main.answer_telegram_callback"):
        response = client.post("/telegram/webhook", json=callback_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["action"] == "reject"

    db_session.refresh(approval_request)
    assert approval_request.status == "rejected"
    assert approval_request.response_method == "telegram"
    assert approval_request.rejected_reason == "Rejected by Telegram user @testuser"


def test_pr_callback_nonexistent_approval(client, db_session):
    """Test PR callback with non-existent approval_id."""

    callback_payload = {
        "callback_query": {
            "id": "test-callback-999",
            "data": "pr_approve:99999",  # Non-existent ID
            "from": {
                "id": 12345,
                "username": "testuser",
            },
            "message": {
                "message_id": 42,
                "chat": {"id": 12345},
            },
        }
    }

    with patch("autopack.main.answer_telegram_callback") as mock_answer:
        response = client.post("/telegram/webhook", json=callback_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data.get("error") == "approval_not_found"

    # Verify callback was answered with error
    mock_answer.assert_called_once()
    # call args: (bot_token, callback_id, text, ...)
    assert "not found" in mock_answer.call_args[0][2].lower()


def test_pr_callback_already_processed(client, db_session, approval_request):
    """Test PR callback is idempotent (already processed)."""
    # Mark approval as already approved
    approval_request.status = "approved"
    approval_request.responded_at = datetime.now(timezone.utc)
    db_session.commit()

    callback_payload = {
        "callback_query": {
            "id": "test-callback-dup",
            "data": f"pr_approve:{approval_request.id}",
            "from": {
                "id": 12345,
                "username": "testuser",
            },
            "message": {
                "message_id": 42,
                "chat": {"id": 12345},
            },
        }
    }

    with patch("autopack.main.answer_telegram_callback"):
        response = client.post("/telegram/webhook", json=callback_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data.get("error") == "approval_not_found"  # Not found in "pending" status

    # Verify status unchanged
    db_session.refresh(approval_request)
    assert approval_request.status == "approved"  # Still approved


def test_pr_callback_uses_approval_id_not_phase_id(client, db_session):
    """Test that PR callbacks use approval_id, not phase_id, avoiding collisions."""
    # Create two approval requests with same phase_id but different approval_id
    req1 = ApprovalRequest(
        run_id="run1",
        phase_id="pr-create-shared-phase",
        context="PR_CREATE",
        decision_info={"type": "PR_CREATE"},
        status="pending",
        requested_at=datetime.now(timezone.utc),
    )
    req2 = ApprovalRequest(
        run_id="run2",
        phase_id="pr-create-shared-phase",  # Same phase_id
        context="PR_CREATE",
        decision_info={"type": "PR_CREATE"},
        status="pending",
        requested_at=datetime.now(timezone.utc),
    )
    db_session.add_all([req1, req2])
    db_session.commit()
    db_session.refresh(req1)
    db_session.refresh(req2)

    # Approve req1 only (by approval_id)
    callback_payload = {
        "callback_query": {
            "id": "test-callback-specific",
            "data": f"pr_approve:{req1.id}",
            "from": {
                "id": 12345,
                "username": "testuser",
            },
            "message": {
                "message_id": 42,
                "chat": {"id": 12345},
            },
        }
    }

    with patch("autopack.main.answer_telegram_callback"):
        response = client.post("/telegram/webhook", json=callback_payload)

    assert response.status_code == 200

    # Verify only req1 was approved
    db_session.refresh(req1)
    db_session.refresh(req2)
    assert req1.status == "approved"
    assert req2.status == "pending"  # Unchanged


def test_telegram_notifier_send_pr_approval_request():
    """Test TelegramNotifier.send_pr_approval_request formats message correctly."""
    from autopack.notifications.telegram_notifier import TelegramNotifier

    notifier = TelegramNotifier()

    # Mock configuration
    notifier.bot_token = "fake-token"
    notifier.chat_id = "12345"

    with patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200

        success = notifier.send_pr_approval_request(
            approval_id=42,
            run_id="test-run",
            branch="feat/test",
            summary_md="Test summary",
            risk_score=50,
            files_changed=5,
            loc_added=100,
            loc_removed=20,
        )

    assert success is True

    # Verify request payload
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args[1]
    payload = call_kwargs["json"]

    assert payload["chat_id"] == "12345"
    assert "🔀 *PR Creation Approval Needed*" in payload["text"]
    assert "`test-run`" in payload["text"]
    assert "`feat/test`" in payload["text"]
    assert "⚠️ 50/100" in payload["text"]  # Medium risk emoji
    assert "5 files (+100/-20 lines)" in payload["text"]

    # Verify buttons use approval_id
    keyboard = payload["reply_markup"]["inline_keyboard"]
    assert keyboard[0][0]["callback_data"] == "pr_approve:42"
    assert keyboard[0][1]["callback_data"] == "pr_reject:42"
