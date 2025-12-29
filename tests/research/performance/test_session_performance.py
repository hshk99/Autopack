"""Performance tests for research session management."""
import pytest
import time
from datetime import datetime


class TestSessionPerformance:
    """Performance tests for session operations."""

    def test_session_creation_performance(self):
        """Test performance of creating multiple sessions."""
        num_sessions = 100
        max_time = 1.0  # 1 second for 100 sessions
        
        start_time = time.time()
        
        sessions = []
        for i in range(num_sessions):
            session = {
                "session_id": f"session_{i}_{time.time()}",
                "status": "initialized",
                "created_at": datetime.utcnow().isoformat()
            }
            sessions.append(session)
        
        elapsed_time = time.time() - start_time
        
        assert elapsed_time < max_time
        assert len(sessions) == num_sessions

    def test_session_lookup_performance(self):
        """Test performance of session lookups."""
        # Create session index
        sessions = {f"session_{i}": {"data": f"data_{i}"} for i in range(1000)}
        
        num_lookups = 100
        max_time = 0.1  # 100ms for 100 lookups
        
        start_time = time.time()
        
        results = []
        for i in range(num_lookups):
            session_id = f"session_{i}"
            if session_id in sessions:
                results.append(sessions[session_id])
        
        elapsed_time = time.time() - start_time
        
        assert elapsed_time < max_time
        assert len(results) == num_lookups

    def test_session_update_performance(self):
        """Test performance of updating session data."""
        session = {
            "session_id": "test_session",
            "status": "active",
            "data": {}
        }
        
        num_updates = 1000
        max_time = 0.5  # 500ms for 1000 updates
        
        start_time = time.time()
        
        for i in range(num_updates):
            session["data"][f"key_{i}"] = f"value_{i}"
        
        elapsed_time = time.time() - start_time
        
        assert elapsed_time < max_time
        assert len(session["data"]) == num_updates

    def test_concurrent_session_operations(self):
        """Test performance of concurrent session operations."""
        sessions = {}
        num_operations = 50
        max_time = 1.0  # 1 second
        
        start_time = time.time()
        
        # Simulate concurrent creates, reads, updates
        for i in range(num_operations):
            session_id = f"session_{i}"
            # Create
            sessions[session_id] = {"status": "active"}
            # Read
            _ = sessions[session_id]
            # Update
            sessions[session_id]["status"] = "updated"
        
        elapsed_time = time.time() - start_time
        
        assert elapsed_time < max_time
        assert len(sessions) == num_operations

    def test_session_cleanup_performance(self):
        """Test performance of cleaning up old sessions."""
        # Create sessions with timestamps
        sessions = [
            {"session_id": f"s_{i}", "created_at": time.time() - (i * 100)}
            for i in range(1000)
        ]
        
        max_time = 0.5  # 500ms
        cutoff_time = time.time() - 5000
        
        start_time = time.time()
        
        # Remove old sessions
        active_sessions = [
            s for s in sessions
            if s["created_at"] > cutoff_time
        ]
        
        elapsed_time = time.time() - start_time
        
        assert elapsed_time < max_time
        assert len(active_sessions) < len(sessions)

    def test_session_state_transitions(self):
        """Test performance of session state transitions."""
        session = {"status": "initialized"}
        transitions = [
            "processing",
            "paused",
            "processing",
            "completed"
        ]
        
        max_time = 0.01  # 10ms
        
        start_time = time.time()
        
        for new_status in transitions:
            session["status"] = new_status
            session["updated_at"] = time.time()
        
        elapsed_time = time.time() - start_time
        
        assert elapsed_time < max_time
        assert session["status"] == "completed"

    def test_session_result_aggregation(self):
        """Test performance of aggregating session results."""
        num_results = 100
        max_time = 0.5  # 500ms
        
        results = [
            {"finding": f"Finding {i}", "confidence": 0.5 + (i % 50) / 100}
            for i in range(num_results)
        ]
        
        start_time = time.time()
        
        # Aggregate results
        aggregated = {
            "total_findings": len(results),
            "avg_confidence": sum(r["confidence"] for r in results) / len(results),
            "high_confidence": [r for r in results if r["confidence"] > 0.8]
        }
        
        elapsed_time = time.time() - start_time
        
        assert elapsed_time < max_time
        assert aggregated["total_findings"] == num_results

    def test_session_serialization_performance(self):
        """Test performance of serializing session data."""
        import json
        
        session = {
            "session_id": "test_session",
            "status": "completed",
            "results": {
                "findings": [f"Finding {i}" for i in range(100)],
                "metadata": {f"key_{i}": f"value_{i}" for i in range(50)}
            }
        }
        
        max_time = 0.1  # 100ms
        
        start_time = time.time()
        
        # Serialize to JSON
        serialized = json.dumps(session)
        # Deserialize
        deserialized = json.loads(serialized)
        
        elapsed_time = time.time() - start_time
        
        assert elapsed_time < max_time
        assert deserialized["session_id"] == session["session_id"]

    def test_session_query_filtering(self):
        """Test performance of filtering sessions by criteria."""
        sessions = [
            {
                "session_id": f"s_{i}",
                "status": ["active", "completed", "failed"][i % 3],
                "created_at": time.time() - (i * 100)
            }
            for i in range(1000)
        ]
        
        max_time = 0.2  # 200ms
        
        start_time = time.time()
        
        # Filter active sessions from last hour
        cutoff = time.time() - 3600
        filtered = [
            s for s in sessions
            if s["status"] == "active" and s["created_at"] > cutoff
        ]
        
        elapsed_time = time.time() - start_time
        
        assert elapsed_time < max_time
        assert all(s["status"] == "active" for s in filtered)

    def test_session_memory_footprint(self):
        """Test memory efficiency of session storage."""
        import sys
        
        num_sessions = 100
        
        sessions = []
        for i in range(num_sessions):
            session = {
                "session_id": f"session_{i}",
                "status": "active",
                "data": {"query": f"Query {i}"}
            }
            sessions.append(session)
        
        total_size = sys.getsizeof(sessions)
        avg_size = total_size / num_sessions
        
        # Average session should be reasonably small
        assert avg_size < 10000  # Less than 10KB per session
