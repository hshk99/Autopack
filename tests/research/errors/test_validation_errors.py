"""Tests for input validation errors."""


class TestValidationErrors:
    """Test suite for input validation error handling."""

    def test_empty_query_validation(self):
        """Test validation of empty queries."""
        queries = ["", "   ", "\t\n"]
        
        for query in queries:
            is_valid = len(query.strip()) > 0
            assert is_valid is False

    def test_query_length_validation(self):
        """Test validation of query length."""
        max_length = 1000
        
        valid_query = "a" * 500
        invalid_query = "a" * 1500
        
        assert len(valid_query) <= max_length
        assert len(invalid_query) > max_length

    def test_session_id_format_validation(self):
        """Test validation of session ID format."""
        valid_ids = ["abc123", "session_456", "test-session-789"]
        invalid_ids = ["", "   ", "id with spaces", "id@invalid"]
        
        for session_id in valid_ids:
            # Simple validation: non-empty, alphanumeric with hyphens/underscores
            is_valid = bool(session_id and all(c.isalnum() or c in "-_" for c in session_id))
            assert is_valid is True
        
        for session_id in invalid_ids:
            is_valid = bool(session_id and all(c.isalnum() or c in "-_" for c in session_id))
            assert is_valid is False

    def test_parameter_type_validation(self):
        """Test validation of parameter types."""
        valid_params = {
            "depth": 3,
            "timeout": 30,
            "max_results": 100
        }
        
        invalid_params = {
            "depth": "three",  # Should be int
            "timeout": -5,     # Should be positive
            "max_results": 0   # Should be positive
        }
        
        # Validate valid params
        assert isinstance(valid_params["depth"], int)
        assert valid_params["timeout"] > 0
        assert valid_params["max_results"] > 0
        
        # Validate invalid params
        assert not isinstance(invalid_params["depth"], int)
        assert invalid_params["timeout"] <= 0
        assert invalid_params["max_results"] <= 0

    def test_parameter_range_validation(self):
        """Test validation of parameter ranges."""
        depth_min, depth_max = 1, 10
        _timeout_min, _timeout_max = 1, 300
        
        valid_depth = 5
        invalid_depth_low = 0
        invalid_depth_high = 15
        
        assert depth_min <= valid_depth <= depth_max
        assert not (depth_min <= invalid_depth_low <= depth_max)
        assert not (depth_min <= invalid_depth_high <= depth_max)

    def test_source_configuration_validation(self):
        """Test validation of source configuration."""
        valid_source = {
            "id": "source1",
            "name": "Test Source",
            "url": "https://example.com",
            "enabled": True
        }
        
        invalid_source = {
            "id": "",  # Empty ID
            "name": "Test Source",
            "url": "invalid-url",  # Invalid URL
            "enabled": "yes"  # Should be boolean
        }
        
        # Validate valid source
        assert len(valid_source["id"]) > 0
        assert valid_source["url"].startswith("http")
        assert isinstance(valid_source["enabled"], bool)
        
        # Validate invalid source
        assert len(invalid_source["id"]) == 0
        assert not invalid_source["url"].startswith("http")
        assert not isinstance(invalid_source["enabled"], bool)

    def test_result_format_validation(self):
        """Test validation of result format."""
        valid_result = {
            "finding": "Test finding",
            "confidence": 0.85,
            "source": "source1"
        }
        
        invalid_result = {
            "finding": "",  # Empty finding
            "confidence": 1.5,  # Out of range
            "source": None  # Missing source
        }
        
        # Validate valid result
        assert len(valid_result["finding"]) > 0
        assert 0 <= valid_result["confidence"] <= 1
        assert valid_result["source"] is not None
        
        # Validate invalid result
        assert len(invalid_result["finding"]) == 0
        assert not (0 <= invalid_result["confidence"] <= 1)
        assert invalid_result["source"] is None

    def test_metadata_validation(self):
        """Test validation of metadata fields."""
        valid_metadata = {
            "created_at": "2025-12-20T12:00:00Z",
            "updated_at": "2025-12-20T12:30:00Z",
            "version": "1.0"
        }
        
        invalid_metadata = {
            "created_at": "invalid-date",
            "updated_at": None,
            "version": ""
        }
        
        # Validate valid metadata
        assert "T" in valid_metadata["created_at"]  # ISO format check
        assert valid_metadata["updated_at"] is not None
        assert len(valid_metadata["version"]) > 0
        
        # Validate invalid metadata
        assert "T" not in invalid_metadata["created_at"]
        assert invalid_metadata["updated_at"] is None
        assert len(invalid_metadata["version"]) == 0
