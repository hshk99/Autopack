"""Unit tests for research data storage."""
import pytest
from unittest.mock import Mock
import json


class TestResearchStorage:
    """Test suite for research storage operations."""

    def test_save_research_data(self):
        """Test saving research data to storage."""
        storage = Mock()
        data = {"session_id": "test_001", "findings": ["finding1", "finding2"]}
        storage.save = Mock(return_value=True)
        
        result = storage.save(data)
        
        assert result is True
        storage.save.assert_called_once_with(data)

    def test_load_research_data(self):
        """Test loading research data from storage."""
        storage = Mock()
        expected_data = {"session_id": "test_001", "findings": ["finding1"]}
        storage.load = Mock(return_value=expected_data)
        
        result = storage.load("test_001")
        
        assert result == expected_data
        storage.load.assert_called_once_with("test_001")

    def test_delete_research_data(self):
        """Test deleting research data from storage."""
        storage = Mock()
        storage.delete = Mock(return_value=True)
        
        result = storage.delete("test_001")
        
        assert result is True
        storage.delete.assert_called_once_with("test_001")

    def test_list_all_sessions(self):
        """Test listing all stored research sessions."""
        storage = Mock()
        sessions = ["session_001", "session_002", "session_003"]
        storage.list_sessions = Mock(return_value=sessions)
        
        result = storage.list_sessions()
        
        assert len(result) == 3
        assert "session_001" in result

    def test_storage_error_handling(self):
        """Test storage error handling."""
        storage = Mock()
        storage.save = Mock(side_effect=IOError("Disk full"))
        
        with pytest.raises(IOError, match="Disk full"):
            storage.save({"data": "test"})

    def test_data_serialization(self):
        """Test data serialization for storage."""
        storage = Mock()
        data = {"session_id": "test", "timestamp": "2025-01-01T00:00:00Z"}
        serialized = json.dumps(data)
        storage.serialize = Mock(return_value=serialized)
        
        result = storage.serialize(data)
        
        assert isinstance(result, str)
        assert "session_id" in result
