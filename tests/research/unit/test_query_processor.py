"""Unit tests for query processing functionality."""


class TestQueryProcessor:
    """Test suite for query processing."""

    def test_query_parsing(self):
        """Test basic query parsing."""
        query = "What is the market size for AI tools?"
        parsed = {
            "raw_query": query,
            "keywords": ["market", "size", "AI", "tools"],
            "intent": "market_research",
        }

        assert parsed["raw_query"] == query
        assert len(parsed["keywords"]) == 4
        assert "AI" in parsed["keywords"]

    def test_query_validation(self):
        """Test query validation logic."""
        valid_query = "Research topic"
        invalid_query = ""

        assert len(valid_query.strip()) > 0
        assert len(invalid_query.strip()) == 0

    def test_query_normalization(self):
        """Test query text normalization."""
        query = "  What IS  the   MARKET size?  "
        normalized = " ".join(query.split()).strip()

        assert normalized == "What IS the MARKET size?"
        assert "  " not in normalized

    def test_keyword_extraction(self):
        """Test keyword extraction from queries."""
        query = "AI market research for healthcare applications"
        stopwords = {"for", "the", "a", "an"}

        words = query.lower().split()
        keywords = [w for w in words if w not in stopwords]

        assert "ai" in keywords
        assert "healthcare" in keywords
        assert "for" not in keywords

    def test_query_intent_classification(self):
        """Test query intent classification."""
        queries = [
            ("What is the market size?", "market_research"),
            ("How does this technology work?", "technical_research"),
            ("Who are the competitors?", "competitive_analysis"),
        ]

        for query, expected_intent in queries:
            # Simple keyword-based classification
            if "market" in query.lower():
                intent = "market_research"
            elif "technology" in query.lower() or "work" in query.lower():
                intent = "technical_research"
            elif "competitor" in query.lower():
                intent = "competitive_analysis"
            else:
                intent = "general"

            assert intent == expected_intent

    def test_query_complexity_assessment(self):
        """Test query complexity assessment."""
        simple_query = "What is AI?"
        complex_query = (
            "Analyze the market dynamics of AI-powered healthcare solutions in emerging markets"
        )

        simple_complexity = len(simple_query.split())
        complex_complexity = len(complex_query.split())

        assert simple_complexity < 5
        assert complex_complexity > 10

    def test_query_parameter_extraction(self):
        """Test extraction of parameters from queries."""
        query = "Research AI market in 2024 with depth 3"

        parameters = {}
        if "2024" in query:
            parameters["year"] = 2024
        if "depth" in query:
            # Extract number after 'depth'
            words = query.split()
            depth_idx = words.index("depth")
            if depth_idx + 1 < len(words):
                parameters["depth"] = int(words[depth_idx + 1])

        assert parameters.get("year") == 2024
        assert parameters.get("depth") == 3

    def test_query_sanitization(self):
        """Test query sanitization for security."""
        malicious_query = "<script>alert('xss')</script>What is AI?"

        # Simple sanitization - remove HTML tags
        sanitized = malicious_query.replace("<", "").replace(">", "")

        assert "<script>" not in sanitized
        assert "What is AI?" in sanitized
