"""Tests for Intent Clarification Agent."""

from autopack.research.agents.intent_clarifier import IntentClarifier, ResearchIntent


class TestIntentClarifier:
    """Test cases for IntentClarifier."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.clarifier = IntentClarifier()
    
    def test_clarify_basic_query(self):
        """Test clarifying a basic query."""
        result = self.clarifier.clarify("How to use Python decorators")
        
        assert isinstance(result, ResearchIntent)
        assert result.raw_input == "How to use Python decorators"
        assert len(result.questions) > 0
        assert "python" in [k.lower() for k in result.keywords]
    
    def test_extract_topics(self):
        """Test topic extraction."""
        text = "Learn about React hooks and TypeScript integration"
        topics = self.clarifier._extract_topics(text)
        
        assert "React" in topics or "TypeScript" in topics
    
    def test_extract_questions(self):
        """Test question extraction."""
        text = "How does async/await work? What are the benefits?"
        questions = self.clarifier._extract_questions(text)
        
        assert len(questions) >= 1
    
    def test_extract_keywords(self):
        """Test keyword extraction."""
        text = "Python async programming with asyncio library"
        keywords = self.clarifier._extract_keywords(text)
        
        assert "python" in keywords
        assert "async" in keywords or "asyncio" in keywords
    
    def test_extract_constraints(self):
        """Test constraint extraction."""
        text = "How to build a web app using Python with Django framework"
        constraints = self.clarifier._extract_constraints(text)
        
        assert "language" in constraints
        assert constraints["language"] == "python"
        assert "framework" in constraints
        assert constraints["framework"] == "django"
    
    def test_determine_scope(self):
        """Test scope determination."""
        comprehensive = self.clarifier._determine_scope(
            "I need a comprehensive guide to machine learning"
        )
        assert comprehensive == "comprehensive"
        
        quick = self.clarifier._determine_scope(
            "Quick overview of REST APIs"
        )
        assert quick == "quick"
    
    def test_determine_priority(self):
        """Test priority determination."""
        high = self.clarifier._determine_priority(
            "Urgent: need to fix production bug"
        )
        assert high == "high"
        
        low = self.clarifier._determine_priority(
            "Nice to have: optional feature"
        )
        assert low == "low"
    
    def test_refine_intent(self):
        """Test intent refinement."""
        intent = self.clarifier.clarify("Python web development")
        
        feedback = {
            "add_topics": ["FastAPI", "REST"],
            "scope": "comprehensive",
            "priority": "high"
        }
        
        refined = self.clarifier.refine_intent(intent, feedback)
        
        assert "FastAPI" in refined.topics
        assert "REST" in refined.topics
        assert refined.scope == "comprehensive"
        assert refined.priority == "high"
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        intent = self.clarifier.clarify("Test query")
        result = intent.to_dict()
        
        assert isinstance(result, dict)
        assert "raw_input" in result
        assert "topics" in result
        assert "keywords" in result
