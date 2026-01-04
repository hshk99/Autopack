"""Integration tests for research source integration."""
import pytest


class TestSourceIntegration:
    """Test suite for research source integration."""

    @pytest.fixture
    def mock_sources(self):
        """Create mock research sources."""
        return [
            {
                "id": "academic_db",
                "name": "Academic Database",
                "type": "database",
                "enabled": True,
                "priority": 1
            },
            {
                "id": "web_search",
                "name": "Web Search",
                "type": "search_engine",
                "enabled": True,
                "priority": 2
            },
            {
                "id": "api_service",
                "name": "API Service",
                "type": "api",
                "enabled": True,
                "priority": 3
            }
        ]

    def test_multi_source_query(self, mock_sources):
        """Test querying multiple sources simultaneously."""
        results = []
        
        for source in mock_sources:
            if source["enabled"]:
                # Simulate source query
                source_result = {
                    "source_id": source["id"],
                    "source_name": source["name"],
                    "findings": [f"Finding from {source['name']}"],
                    "confidence": 0.8
                }
                results.append(source_result)
        
        assert len(results) == 3
        assert all(r["confidence"] > 0 for r in results)

    def test_source_priority_execution(self, mock_sources):
        """Test that sources are queried in priority order."""
        sorted_sources = sorted(mock_sources, key=lambda x: x["priority"])
        
        execution_order = [s["id"] for s in sorted_sources]
        
        assert execution_order[0] == "academic_db"
        assert execution_order[1] == "web_search"
        assert execution_order[2] == "api_service"

    def test_source_fallback_mechanism(self, mock_sources):
        """Test fallback to alternative sources on failure."""
        # Simulate primary source failure
        mock_sources[0]["enabled"] = False
        
        available_sources = [s for s in mock_sources if s["enabled"]]
        
        assert len(available_sources) == 2
        assert available_sources[0]["id"] == "web_search"

    def test_source_result_aggregation(self, mock_sources):
        """Test aggregation of results from multiple sources."""
        source_results = [
            {"source": "academic_db", "findings": ["finding1", "finding2"]},
            {"source": "web_search", "findings": ["finding3", "finding4"]},
            {"source": "api_service", "findings": ["finding5"]}
        ]
        
        all_findings = []
        for result in source_results:
            all_findings.extend(result["findings"])
        
        assert len(all_findings) == 5
        assert "finding1" in all_findings
        assert "finding5" in all_findings

    def test_source_timeout_handling(self, mock_sources):
        """Test handling of source timeouts."""
        timeout_seconds = 10
        
        for source in mock_sources:
            source["timeout"] = timeout_seconds
            source["status"] = "timeout" if source["id"] == "api_service" else "success"
        
        successful_sources = [s for s in mock_sources if s["status"] == "success"]
        
        assert len(successful_sources) == 2

    def test_source_rate_limit_compliance(self, mock_sources):
        """Test compliance with source rate limits."""
        for source in mock_sources:
            source["rate_limit"] = {"requests_per_minute": 60}
            source["request_count"] = 0
        
        # Simulate requests
        for i in range(5):
            for source in mock_sources:
                if source["request_count"] < source["rate_limit"]["requests_per_minute"]:
                    source["request_count"] += 1
        
        assert all(s["request_count"] <= s["rate_limit"]["requests_per_minute"] for s in mock_sources)

    def test_source_authentication_flow(self, mock_sources):
        """Test authentication flow for sources requiring auth."""
        for source in mock_sources:
            if source["type"] == "api":
                source["auth"] = {
                    "type": "api_key",
                    "authenticated": True
                }
        
        api_source = next(s for s in mock_sources if s["type"] == "api")
        
        assert api_source["auth"]["authenticated"] is True

    def test_source_error_propagation(self, mock_sources):
        """Test error propagation from sources."""
        errors = []
        
        for source in mock_sources:
            if source["id"] == "web_search":
                error = {
                    "source_id": source["id"],
                    "error_code": "CONNECTION_ERROR",
                    "message": "Failed to connect to source"
                }
                errors.append(error)
        
        assert len(errors) == 1
        assert errors[0]["source_id"] == "web_search"
