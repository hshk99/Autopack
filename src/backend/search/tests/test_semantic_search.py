"""Tests for semantic search module."""
import pytest
from pathlib import Path
from src.backend.search.semantic_search import SemanticSearchEngine, SearchResult


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace with test files."""
    # Create test files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def main(): pass")
    (tmp_path / "src" / "utils.py").write_text("def helper(): pass")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("def test_main(): pass")
    (tmp_path / "README.md").write_text("# Project README")
    
    return tmp_path


@pytest.fixture
def search_engine(temp_workspace):
    """Create search engine with indexed files."""
    engine = SemanticSearchEngine(temp_workspace)
    
    # Index test files
    engine.index_file("src/main.py", {"type": "python", "size": 100})
    engine.index_file("src/utils.py", {"type": "python", "size": 80})
    engine.index_file("tests/test_main.py", {"type": "test", "size": 120})
    engine.index_file("README.md", {"type": "markdown", "size": 50})
    
    return engine


class TestSemanticSearchEngine:
    """Tests for SemanticSearchEngine."""
    
    def test_initialization(self, temp_workspace):
        """Test engine initialization."""
        engine = SemanticSearchEngine(temp_workspace)
        assert engine.workspace_path == temp_workspace
        assert len(engine._index) == 0
    
    def test_index_file(self, temp_workspace):
        """Test file indexing."""
        engine = SemanticSearchEngine(temp_workspace)
        engine.index_file("test.py", {"type": "python"})
        
        assert "test.py" in engine._index
        assert engine._index["test.py"]["type"] == "python"
    
    def test_search_empty_query(self, search_engine):
        """Test search with empty query."""
        results = search_engine.search("")
        assert len(results) == 0
    
    def test_search_exact_path_match(self, search_engine):
        """Test search with exact path match."""
        results = search_engine.search("main.py")
        
        assert len(results) >= 1
        assert results[0].file_path in ["src/main.py", "tests/test_main.py"]
        assert results[0].confidence >= 0.75
    
    def test_search_partial_match(self, search_engine):
        """Test search with partial match."""
        results = search_engine.search("utils")
        
        assert len(results) >= 1
        assert "utils.py" in results[0].file_path
        assert results[0].confidence >= 0.50
    
    def test_search_metadata_match(self, search_engine):
        """Test search matching metadata."""
        results = search_engine.search("python")
        
        assert len(results) >= 2  # main.py and utils.py
        for result in results[:2]:
            assert result.metadata["type"] == "python"
    
    def test_search_confidence_threshold(self, search_engine):
        """Test confidence threshold filtering."""
        # High threshold should return fewer results
        high_results = search_engine.search("test", min_confidence=0.85)
        low_results = search_engine.search("test", min_confidence=0.50)
        
        assert len(high_results) <= len(low_results)
    
    def test_search_max_results(self, search_engine):
        """Test max results limit."""
        results = search_engine.search("py", max_results=2)
        assert len(results) <= 2
    
    def test_search_sorting(self, search_engine):
        """Test results are sorted by confidence and score."""
        results = search_engine.search("main")
        
        if len(results) > 1:
            # Check confidence is non-increasing
            for i in range(len(results) - 1):
                assert results[i].confidence >= results[i + 1].confidence
    
    def test_snippet_extraction(self, search_engine):
        """Test snippet extraction from files."""
        results = search_engine.search("main")
        
        # At least one result should have a snippet
        assert any(r.snippet is not None for r in results)
    
    def test_confidence_levels(self, search_engine):
        """Test confidence level labels."""
        assert search_engine.get_confidence_level(0.90) == "high"
        assert search_engine.get_confidence_level(0.75) == "medium"
        assert search_engine.get_confidence_level(0.55) == "low"
        assert search_engine.get_confidence_level(0.30) == "very_low"
    
    def test_clear_index(self, search_engine):
        """Test index clearing."""
        assert len(search_engine._index) > 0
        
        search_engine.clear_index()
        
        assert len(search_engine._index) == 0
        assert len(search_engine._embeddings_cache) == 0
    
    def test_nonexistent_file_snippet(self, search_engine):
        """Test snippet extraction for nonexistent file."""
        snippet = search_engine._extract_snippet(
            "nonexistent.py",
            {"test"},
            max_length=100
        )
        assert snippet is None
    
    def test_calculate_match_all_terms_in_path(self, search_engine):
        """Test match calculation with all terms in path."""
        score, confidence = search_engine._calculate_match(
            "src/main.py",
            {"type": "python"},
            {"main", "py"}
        )
        
        assert score > 0
        assert confidence >= 0.85  # High confidence
    
    def test_calculate_match_partial(self, search_engine):
        """Test match calculation with partial match."""
        score, confidence = search_engine._calculate_match(
            "src/utils.py",
            {"type": "python"},
            {"utils", "helper", "test"}
        )
        
        assert score > 0
        assert 0.50 <= confidence < 0.85  # Medium or low confidence
    
    def test_calculate_match_no_match(self, search_engine):
        """Test match calculation with no match."""
        score, confidence = search_engine._calculate_match(
            "src/main.py",
            {"type": "python"},
            {"nonexistent", "missing"}
        )
        
        assert score == 0.0
        assert confidence < 0.50  # Very low confidence
