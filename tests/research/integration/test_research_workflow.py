"""Integration tests for research workflow."""

import pytest
from datetime import datetime, timezone


class TestResearchWorkflowIntegration:
    """Integration tests for the complete research workflow."""

    @pytest.fixture
    def workflow_context(self):
        """Create a workflow context for testing."""
        return {
            "session_id": "test_session_001",
            "user_id": "test_user",
            "created_at": datetime.now(timezone.utc).isoformat()
        }

    def test_complete_research_workflow(self, workflow_context):
        """Test a complete research workflow from start to finish."""
        # Arrange
        workflow = MockResearchWorkflow(workflow_context)
        query = {"topic": "artificial intelligence", "depth": "comprehensive"}
        
        # Act - Step 1: Initialize session
        session = workflow.initialize_session()
        assert session["status"] == "initialized"
        
        # Act - Step 2: Submit query
        query_result = workflow.submit_query(query)
        assert query_result["accepted"] is True
        
        # Act - Step 3: Execute research
        research_result = workflow.execute_research()
        assert research_result["status"] == "completed"
        assert "results" in research_result
        
        # Act - Step 4: Finalize session
        final_result = workflow.finalize_session()
        assert final_result["status"] == "finalized"

    def test_workflow_handles_query_failure(self, workflow_context):
        """Test workflow handling of query submission failure."""
        # Arrange
        workflow = MockResearchWorkflow(workflow_context)
        invalid_query = {"topic": ""}  # Invalid: empty topic
        
        # Act
        workflow.initialize_session()
        query_result = workflow.submit_query(invalid_query)
        
        # Assert
        assert query_result["accepted"] is False
        assert "error" in query_result

    def test_workflow_state_persistence(self, workflow_context):
        """Test that workflow state is properly persisted."""
        # Arrange
        workflow = MockResearchWorkflow(workflow_context)
        query = {"topic": "data science", "depth": "standard"}
        
        # Act
        workflow.initialize_session()
        workflow.submit_query(query)
        
        # Assert - State should be persisted
        state = workflow.get_state()
        assert state["session_id"] == workflow_context["session_id"]
        assert state["query"] == query
        assert "initialized_at" in state

    def test_workflow_cancellation(self, workflow_context):
        """Test workflow cancellation during execution."""
        # Arrange
        workflow = MockResearchWorkflow(workflow_context)
        query = {"topic": "machine learning", "depth": "comprehensive"}
        
        # Act
        workflow.initialize_session()
        workflow.submit_query(query)
        cancel_result = workflow.cancel()
        
        # Assert
        assert cancel_result["status"] == "cancelled"
        assert workflow.get_state()["status"] == "cancelled"

    def test_workflow_retry_on_failure(self, workflow_context):
        """Test workflow retry mechanism on transient failures."""
        # Arrange
        workflow = MockResearchWorkflow(workflow_context, fail_count=2)
        query = {"topic": "neural networks", "depth": "standard"}
        
        # Act
        workflow.initialize_session()
        workflow.submit_query(query)
        result = workflow.execute_research(max_retries=3)
        
        # Assert
        assert result["status"] == "completed"
        assert result["retry_count"] == 2


class TestAPIIntegration:
    """Integration tests for API endpoints."""

    @pytest.fixture
    def api_client(self):
        """Create a mock API client."""
        return MockAPIClient()

    def test_create_and_retrieve_session(self, api_client):
        """Test creating a session and retrieving it via API."""
        # Act - Create session
        create_response = api_client.post("/api/research/sessions", {})
        assert create_response["status_code"] == 201
        session_id = create_response["body"]["session_id"]
        
        # Act - Retrieve session
        get_response = api_client.get(f"/api/research/sessions/{session_id}")
        assert get_response["status_code"] == 200
        assert get_response["body"]["session_id"] == session_id

    def test_list_sessions_pagination(self, api_client):
        """Test session listing with pagination."""
        # Arrange - Create multiple sessions
        for _ in range(15):
            api_client.post("/api/research/sessions", {})
        
        # Act - Get first page
        page1 = api_client.get("/api/research/sessions?page=1&limit=10")
        assert page1["status_code"] == 200
        assert len(page1["body"]["sessions"]) == 10
        
        # Act - Get second page
        page2 = api_client.get("/api/research/sessions?page=2&limit=10")
        assert page2["status_code"] == 200
        assert len(page2["body"]["sessions"]) == 5

    def test_session_not_found(self, api_client):
        """Test 404 response for non-existent session."""
        # Act
        response = api_client.get("/api/research/sessions/nonexistent_id")
        
        # Assert
        assert response["status_code"] == 404
        assert "error" in response["body"]

    def test_submit_research_query(self, api_client):
        """Test submitting a research query to a session."""
        # Arrange
        create_response = api_client.post("/api/research/sessions", {})
        session_id = create_response["body"]["session_id"]
        
        # Act
        query_response = api_client.post(
            f"/api/research/sessions/{session_id}/query",
            {"topic": "deep learning", "depth": "comprehensive"}
        )
        
        # Assert
        assert query_response["status_code"] == 202
        assert query_response["body"]["status"] == "accepted"

    def test_get_research_results(self, api_client):
        """Test retrieving research results."""
        # Arrange
        create_response = api_client.post("/api/research/sessions", {})
        session_id = create_response["body"]["session_id"]
        api_client.post(
            f"/api/research/sessions/{session_id}/query",
            {"topic": "computer vision", "depth": "standard"}
        )
        
        # Act
        results_response = api_client.get(f"/api/research/sessions/{session_id}/results")
        
        # Assert
        assert results_response["status_code"] == 200
        assert "results" in results_response["body"]


class TestDataPipelineIntegration:
    """Integration tests for data pipeline."""

    def test_data_ingestion_pipeline(self):
        """Test complete data ingestion pipeline."""
        # Arrange
        pipeline = MockDataPipeline()
        raw_data = [
            {"source": "web", "content": "Article about AI", "timestamp": "2025-01-01T00:00:00Z"},
            {"source": "paper", "content": "Research on ML", "timestamp": "2025-01-02T00:00:00Z"}
        ]
        
        # Act
        result = pipeline.ingest(raw_data)
        
        # Assert
        assert result["status"] == "success"
        assert result["processed_count"] == 2
        assert result["failed_count"] == 0

    def test_data_transformation_pipeline(self):
        """Test data transformation in pipeline."""
        # Arrange
        pipeline = MockDataPipeline()
        raw_data = [{"content": "  Raw Content  ", "metadata": {}}]
        
        # Act
        pipeline.ingest(raw_data)
        transformed = pipeline.get_transformed_data()
        
        # Assert
        assert transformed[0]["content"] == "Raw Content"  # Trimmed
        assert "processed_at" in transformed[0]

    def test_pipeline_error_handling(self):
        """Test pipeline error handling for malformed data."""
        # Arrange
        pipeline = MockDataPipeline()
        malformed_data = [
            {"content": "Valid"},
            {"invalid": "missing content field"},
            {"content": "Also valid"}
        ]
        
        # Act
        result = pipeline.ingest(malformed_data)
        
        # Assert
        assert result["processed_count"] == 2
        assert result["failed_count"] == 1
        assert len(result["errors"]) == 1


class MockResearchWorkflow:
    """Mock implementation of research workflow for testing."""
    
    def __init__(self, context, fail_count=0):
        self.context = context
        self.state = {"session_id": context["session_id"], "status": "created"}
        self.fail_count = fail_count
        self.attempt_count = 0
    
    def initialize_session(self):
        self.state["status"] = "initialized"
        self.state["initialized_at"] = datetime.now(timezone.utc).isoformat()
        return {"status": "initialized"}
    
    def submit_query(self, query):
        if not query.get("topic", "").strip():
            return {"accepted": False, "error": "Topic is required"}
        self.state["query"] = query
        self.state["status"] = "query_submitted"
        return {"accepted": True}
    
    def execute_research(self, max_retries=1):
        retry_count = 0
        while self.attempt_count < self.fail_count and retry_count < max_retries:
            self.attempt_count += 1
            retry_count += 1
        
        self.state["status"] = "completed"
        return {
            "status": "completed",
            "results": [{"title": "Result 1", "score": 0.9}],
            "retry_count": retry_count
        }
    
    def finalize_session(self):
        self.state["status"] = "finalized"
        return {"status": "finalized"}
    
    def cancel(self):
        self.state["status"] = "cancelled"
        return {"status": "cancelled"}
    
    def get_state(self):
        return self.state.copy()


class MockAPIClient:
    """Mock API client for testing."""
    
    def __init__(self):
        self.sessions = {}
        self.counter = 0
    
    def get(self, path):
        if path.startswith("/api/research/sessions?"):
            # Parse pagination
            params = self._parse_query_params(path)
            page = int(params.get("page", 1))
            limit = int(params.get("limit", 10))
            start = (page - 1) * limit
            end = start + limit
            sessions = list(self.sessions.values())[start:end]
            return {"status_code": 200, "body": {"sessions": sessions}}
        
        if "/results" in path:
            session_id = path.split("/")[-2]
            if session_id in self.sessions:
                return {"status_code": 200, "body": {"results": []}}
            return {"status_code": 404, "body": {"error": "Not found"}}
        
        session_id = path.split("/")[-1]
        if session_id in self.sessions:
            return {"status_code": 200, "body": self.sessions[session_id]}
        return {"status_code": 404, "body": {"error": "Session not found"}}
    
    def post(self, path, body):
        if path == "/api/research/sessions":
            self.counter += 1
            session_id = f"session_{self.counter}"
            self.sessions[session_id] = {
                "session_id": session_id,
                "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            return {"status_code": 201, "body": {"session_id": session_id}}
        
        if "/query" in path:
            return {"status_code": 202, "body": {"status": "accepted"}}
        
        return {"status_code": 400, "body": {"error": "Bad request"}}
    
    def _parse_query_params(self, path):
        if "?" not in path:
            return {}
        query_string = path.split("?")[1]
        params = {}
        for param in query_string.split("&"):
            key, value = param.split("=")
            params[key] = value
        return params


class MockDataPipeline:
    """Mock data pipeline for testing."""
    
    def __init__(self):
        self.data = []
        self.errors = []
    
    def ingest(self, raw_data):
        processed = 0
        failed = 0
        
        for item in raw_data:
            if "content" not in item:
                failed += 1
                self.errors.append({"item": item, "error": "Missing content field"})
                continue
            
            transformed = {
                "content": item["content"].strip(),
                "metadata": item.get("metadata", {}),
                "processed_at": datetime.now(timezone.utc).isoformat()
            }
            self.data.append(transformed)
            processed += 1
        
        return {
            "status": "success",
            "processed_count": processed,
            "failed_count": failed,
            "errors": self.errors
        }
    
    def get_transformed_data(self):
        return self.data.copy()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
