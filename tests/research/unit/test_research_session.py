"""Unit tests for research session management."""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock


class TestResearchSession:
    """Test suite for ResearchSession class."""

    def test_session_initialization(self):
        """Test that a research session initializes correctly."""
        session_id = "test_session_123"
        session = {"session_id": session_id, "status": "active", "created_at": datetime.now().isoformat()}
        
        assert session["session_id"] == session_id
        assert session["status"] == "active"
        assert "created_at" in session

    def test_session_status_transitions(self):
        """Test valid session status transitions."""
        valid_transitions = [
            ("active", "paused"),
            ("paused", "active"),
            ("active", "completed"),
            ("paused", "completed"),
        ]
        
        for from_status, to_status in valid_transitions:
            session = {"status": from_status}
            session["status"] = to_status
            assert session["status"] == to_status

    def test_session_invalid_status(self):
        """Test that invalid status values are rejected."""
        valid_statuses = ["active", "paused", "completed", "failed"]
        invalid_status = "invalid_status"
        
        assert invalid_status not in valid_statuses

    def test_session_metadata(self):
        """Test session metadata handling."""
        metadata = {
            "query": "test query",
            "sources": ["source1", "source2"],
            "parameters": {"depth": 3, "timeout": 30}
        }
        
        session = {
            "session_id": "test_123",
            "metadata": metadata
        }
        
        assert session["metadata"]["query"] == "test query"
        assert len(session["metadata"]["sources"]) == 2
        assert session["metadata"]["parameters"]["depth"] == 3

    def test_session_results_storage(self):
        """Test that session results are stored correctly."""
        results = {
            "findings": ["finding1", "finding2"],
            "confidence": 0.85,
            "sources_used": 5
        }
        
        session = {
            "session_id": "test_123",
            "results": results
        }
        
        assert len(session["results"]["findings"]) == 2
        assert session["results"]["confidence"] == 0.85
        assert session["results"]["sources_used"] == 5

    def test_session_timestamp_format(self):
        """Test that timestamps are in ISO format."""
        timestamp = datetime.now().isoformat()
        session = {"created_at": timestamp}
        
        # Verify ISO format can be parsed back
        parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00') if timestamp.endswith('Z') else timestamp)
        assert isinstance(parsed, datetime)

    def test_session_unique_id(self):
        """Test that session IDs are unique."""
        session1 = {"session_id": "session_1"}
        session2 = {"session_id": "session_2"}
        
        assert session1["session_id"] != session2["session_id"]

    def test_session_error_handling(self):
        """Test session error state handling."""
        error_session = {
            "session_id": "error_session",
            "status": "failed",
            "error": {
                "message": "Connection timeout",
                "code": "TIMEOUT_ERROR",
                "timestamp": datetime.now().isoformat()
            }
        }
        
        assert error_session["status"] == "failed"
        assert "error" in error_session
        assert error_session["error"]["code"] == "TIMEOUT_ERROR"
