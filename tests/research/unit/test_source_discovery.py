"""Unit tests for source discovery strategies."""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from autopack.research.source_discovery import (
    SourceDiscoveryStrategy,
    WebSearchStrategy,
    AcademicSearchStrategy,
    DocumentationSearchStrategy,
    DiscoveredSource,
)
from autopack.research.intent_clarification import ClarifiedIntent


class TestSourceDiscoveryStrategy:
    """Test suite for base SourceDiscoveryStrategy."""

    def test_strategy_interface(self):
        """Test that strategy defines required interface."""
        strategy = SourceDiscoveryStrategy()

        assert hasattr(strategy, "discover")
        assert callable(strategy.discover)


class TestWebSearchStrategy:
    """Test suite for WebSearchStrategy."""

    @pytest.fixture
    def strategy(self):
        """Create web search strategy instance."""
        return WebSearchStrategy()

    @pytest.fixture
    def sample_intent(self):
        """Create sample clarified intent."""
        return ClarifiedIntent(
            original_query="API design best practices",
            clarified_aspects=["RESTful API design", "API versioning", "API documentation"],
            key_concepts=["REST", "API", "design patterns"],
            key_questions=["What are REST principles?", "How to version APIs?"],
            scope=Mock(),
        )

    @pytest.mark.asyncio
    async def test_discover_sources(self, strategy, sample_intent):
        """Test discovering sources from web search."""
        with patch.object(strategy, "_execute_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [
                {
                    "url": "https://example.com/1",
                    "title": "API Design Guide",
                    "snippet": "Best practices...",
                },
                {
                    "url": "https://example.com/2",
                    "title": "REST API Tutorial",
                    "snippet": "Learn REST...",
                },
            ]

            sources = await strategy.discover(sample_intent)

            assert len(sources) == 2
            assert all(isinstance(s, DiscoveredSource) for s in sources)
            mock_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_source_ranking(self, strategy, sample_intent):
        """Test that sources are ranked by relevance."""
        with patch.object(strategy, "_execute_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [
                {"url": "https://example.com/1", "title": "Relevant", "snippet": "API design REST"},
                {
                    "url": "https://example.com/2",
                    "title": "Less relevant",
                    "snippet": "General programming",
                },
            ]

            sources = await strategy.discover(sample_intent)

            # First source should have higher relevance score
            assert sources[0].relevance_score >= sources[1].relevance_score

    @pytest.mark.asyncio
    async def test_deduplication(self, strategy, sample_intent):
        """Test that duplicate sources are removed."""
        with patch.object(strategy, "_execute_search", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = [
                {"url": "https://example.com/1", "title": "Guide", "snippet": "..."},
                {"url": "https://example.com/1", "title": "Guide", "snippet": "..."},  # Duplicate
                {"url": "https://example.com/2", "title": "Tutorial", "snippet": "..."},
            ]

            sources = await strategy.discover(sample_intent)

            # Should have only 2 unique sources
            assert len(sources) == 2
            urls = [s.url for s in sources]
            assert len(urls) == len(set(urls))  # All unique


class TestAcademicSearchStrategy:
    """Test suite for AcademicSearchStrategy."""

    @pytest.fixture
    def strategy(self):
        """Create academic search strategy instance."""
        return AcademicSearchStrategy()

    @pytest.fixture
    def academic_intent(self):
        """Create intent suitable for academic search."""
        return ClarifiedIntent(
            original_query="Machine learning optimization algorithms",
            clarified_aspects=["gradient descent", "Adam optimizer", "convergence analysis"],
            key_concepts=["optimization", "machine learning", "algorithms"],
            key_questions=["What are modern optimization methods?"],
            scope=Mock(),
        )

    @pytest.mark.asyncio
    async def test_discover_academic_sources(self, strategy, academic_intent):
        """Test discovering academic sources."""
        with patch.object(
            strategy, "_search_academic_databases", new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = [
                {
                    "url": "https://arxiv.org/abs/1234.5678",
                    "title": "Novel Optimization Algorithm",
                    "authors": ["Smith, J.", "Doe, J."],
                    "abstract": "We propose a new optimization method...",
                    "year": 2024,
                }
            ]

            sources = await strategy.discover(academic_intent)

            assert len(sources) > 0
            assert sources[0].source_type == "academic"
            assert "arxiv" in sources[0].url

    @pytest.mark.asyncio
    async def test_citation_metadata(self, strategy, academic_intent):
        """Test that academic sources include citation metadata."""
        with patch.object(
            strategy, "_search_academic_databases", new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = [
                {
                    "url": "https://arxiv.org/abs/1234.5678",
                    "title": "Research Paper",
                    "authors": ["Author, A."],
                    "abstract": "Abstract text",
                    "year": 2024,
                    "citations": 42,
                }
            ]

            sources = await strategy.discover(academic_intent)

            assert sources[0].metadata.get("authors") is not None
            assert sources[0].metadata.get("year") == 2024


class TestDocumentationSearchStrategy:
    """Test suite for DocumentationSearchStrategy."""

    @pytest.fixture
    def strategy(self):
        """Create documentation search strategy instance."""
        return DocumentationSearchStrategy()

    @pytest.fixture
    def technical_intent(self):
        """Create intent for technical documentation."""
        return ClarifiedIntent(
            original_query="How to use Python asyncio",
            clarified_aspects=["async/await syntax", "event loop", "coroutines"],
            key_concepts=["asyncio", "Python", "asynchronous programming"],
            key_questions=["What is the event loop?", "How to create coroutines?"],
            scope=Mock(),
        )

    @pytest.mark.asyncio
    async def test_discover_documentation(self, strategy, technical_intent):
        """Test discovering official documentation."""
        with patch.object(
            strategy, "_search_documentation_sites", new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = [
                {
                    "url": "https://docs.python.org/3/library/asyncio.html",
                    "title": "asyncio — Asynchronous I/O",
                    "snippet": "Official Python documentation for asyncio",
                }
            ]

            sources = await strategy.discover(technical_intent)

            assert len(sources) > 0
            assert sources[0].source_type == "documentation"
            assert "docs.python.org" in sources[0].url

    @pytest.mark.asyncio
    async def test_prioritize_official_docs(self, strategy, technical_intent):
        """Test that official documentation is prioritized."""
        with patch.object(
            strategy, "_search_documentation_sites", new_callable=AsyncMock
        ) as mock_search:
            mock_search.return_value = [
                {
                    "url": "https://docs.python.org/3/library/asyncio.html",
                    "title": "Official",
                    "snippet": "...",
                },
                {
                    "url": "https://realpython.com/async-io-python/",
                    "title": "Tutorial",
                    "snippet": "...",
                },
            ]

            sources = await strategy.discover(technical_intent)

            # Official docs should have higher relevance
            official = [s for s in sources if "docs.python.org" in s.url][0]
            tutorial = [s for s in sources if "realpython.com" in s.url][0]
            assert official.relevance_score >= tutorial.relevance_score
