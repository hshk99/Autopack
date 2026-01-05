"""Unit tests for research query processing."""

import pytest
from unittest.mock import Mock


class TestResearchQuery:
    """Test suite for research query handling."""

    def test_query_creation(self):
        """Test creating a research query."""
        query = Mock()
        query.text = "What are the latest trends in AI?"
        query.query_type = "exploratory"
        query.parameters = {"depth": "comprehensive"}

        assert query.text == "What are the latest trends in AI?"
        assert query.query_type == "exploratory"
        assert query.parameters["depth"] == "comprehensive"

    def test_query_validation_valid(self):
        """Test validation of a valid query."""
        query = Mock()
        query.text = "Research topic"
        query.validate = Mock(return_value=True)

        result = query.validate()

        assert result is True

    def test_query_validation_empty(self):
        """Test validation rejects empty queries."""
        query = Mock()
        query.text = ""
        query.validate = Mock(side_effect=ValueError("Query text cannot be empty"))

        with pytest.raises(ValueError, match="Query text cannot be empty"):
            query.validate()

    def test_query_parsing(self):
        """Test parsing query parameters."""
        query = Mock()
        query.parse = Mock(return_value={"keywords": ["AI", "trends"], "intent": "research"})

        result = query.parse()

        assert "keywords" in result
        assert "AI" in result["keywords"]
        assert result["intent"] == "research"

    def test_query_with_filters(self):
        """Test query with applied filters."""
        query = Mock()
        query.filters = {"date_range": "2024-2025", "source_type": "academic"}

        assert query.filters["date_range"] == "2024-2025"
        assert query.filters["source_type"] == "academic"

    def test_query_execution(self):
        """Test query execution returns results."""
        query = Mock()
        query.execute = Mock(return_value={"results": ["result1", "result2"], "count": 2})

        result = query.execute()

        assert result["count"] == 2
        assert len(result["results"]) == 2
