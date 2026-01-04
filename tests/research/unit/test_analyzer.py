"""Unit tests for research analyzer."""


class TestAnalyzer:
    """Test suite for Analyzer class."""

    def test_analyze_simple_data(self):
        """Test analyzing simple research data."""
        from autopack.research.analyzer import Analyzer
        
        analyzer = Analyzer()
        data = [
            {"title": "Article 1", "content": "Machine learning content"},
            {"title": "Article 2", "content": "Deep learning content"}
        ]
        
        result = analyzer.analyze(data)
        
        assert result is not None
        assert "insights" in result or "summary" in result or "analysis" in result

    def test_extract_insights(self):
        """Test insight extraction from data."""
        from autopack.research.analyzer import Analyzer
        
        analyzer = Analyzer()
        data = [
            {"content": "Machine learning is a subset of AI"},
            {"content": "Deep learning uses neural networks"}
        ]
        
        insights = analyzer.extract_insights(data)
        
        assert isinstance(insights, list)
        assert len(insights) > 0

    def test_sentiment_analysis(self):
        """Test sentiment analysis of content."""
        from autopack.research.analyzer import Analyzer
        
        analyzer = Analyzer()
        
        positive_text = "This is excellent and amazing work"
        negative_text = "This is terrible and awful"
        
        pos_sentiment = analyzer.analyze_sentiment(positive_text)
        neg_sentiment = analyzer.analyze_sentiment(negative_text)
        
        assert pos_sentiment is not None
        assert neg_sentiment is not None
        # Positive should be higher than negative
        if isinstance(pos_sentiment, (int, float)) and isinstance(neg_sentiment, (int, float)):
            assert pos_sentiment > neg_sentiment

    def test_topic_extraction(self):
        """Test topic extraction from documents."""
        from autopack.research.analyzer import Analyzer
        
        analyzer = Analyzer()
        documents = [
            "Machine learning algorithms for classification",
            "Deep learning neural networks",
            "Natural language processing techniques"
        ]
        
        topics = analyzer.extract_topics(documents)
        
        assert isinstance(topics, list)
        assert len(topics) > 0

    def test_summarization(self):
        """Test text summarization."""
        from autopack.research.analyzer import Analyzer
        
        analyzer = Analyzer()
        long_text = """Machine learning is a method of data analysis that automates 
        analytical model building. It is a branch of artificial intelligence based on 
        the idea that systems can learn from data, identify patterns and make decisions 
        with minimal human intervention."""
        
        summary = analyzer.summarize(long_text)
        
        assert summary is not None
        assert len(summary) < len(long_text)

    def test_empty_data_handling(self):
        """Test handling of empty data."""
        from autopack.research.analyzer import Analyzer
        
        analyzer = Analyzer()
        result = analyzer.analyze([])
        
        assert result is not None
        # Should return empty structure or default response
