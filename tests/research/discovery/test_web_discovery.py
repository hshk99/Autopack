"""Tests for Web Discovery."""

import pytest
from unittest.mock import Mock, patch
from autopack.research.discovery.web_discovery import WebDiscovery, WebResult


class TestWebDiscovery:
    """Test cases for WebDiscovery."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.discovery = WebDiscovery()
    
    def test_web_result_to_dict(self):
        """Test web result conversion to dict."""
        result = WebResult(
            title="Test Result",
            url="https://example.com",
            snippet="Test snippet",
            source="example.com"
        )
        
        result_dict = result.to_dict()
        
        assert isinstance(result_dict, dict)
        assert result_dict["title"] == "Test Result"
        assert result_dict["url"] == "https://example.com"
    
    @patch('requests.post')
    def test_search_duckduckgo(self, mock_post):
        """Test DuckDuckGo search."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '''
        <div class="result__body">
            <a rel="nofollow" class="result__a" href="https://example.com">Test Title</a>
            <a class="result__snippet">Test snippet</a>
        </div>
        '''
        mock_post.return_value = mock_response
        
        results = self.discovery.search("test query")
        
        # Results depend on HTML parsing
        assert isinstance(results, list)
    
    def test_search_documentation(self):
        """Test documentation search."""
        with patch.object(self.discovery, 'search') as mock_search:
            mock_search.return_value = []
            
            results = self.discovery.search_documentation("async", "python")
            
            mock_search.assert_called_once()
            assert isinstance(results, list)
    
    def test_search_stackoverflow(self):
        """Test Stack Overflow search."""
        with patch.object(self.discovery, 'search') as mock_search:
            mock_search.return_value = []
            
            results = self.discovery.search_stackoverflow("error", tags=["python"])
            
            mock_search.assert_called_once()
            assert isinstance(results, list)
    
    @patch('requests.get')
    def test_check_url_accessibility(self, mock_get):
        """Test URL accessibility check."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        result = self.discovery.check_url_accessibility("https://example.com")
        
        assert result is True
        
        mock_response.status_code = 404
        result = self.discovery.check_url_accessibility("https://example.com")
        
        assert result is False
