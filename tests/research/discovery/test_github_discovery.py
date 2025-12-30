"""Tests for GitHub Discovery."""

import pytest
from unittest.mock import Mock, patch
from autopack.research.discovery.github_discovery import GitHubDiscovery, GitHubRepository, GitHubIssue


class TestGitHubDiscovery:
    """Test cases for GitHubDiscovery."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.discovery = GitHubDiscovery()
    
    @patch('requests.get')
    def test_search_repositories(self, mock_get):
        """Test repository search."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "name": "test-repo",
                    "full_name": "user/test-repo",
                    "description": "Test repository",
                    "html_url": "https://github.com/user/test-repo",
                    "stargazers_count": 100,
                    "forks_count": 20,
                    "language": "Python",
                    "topics": ["testing"],
                    "updated_at": "2024-01-01T00:00:00Z"
                }
            ]
        }
        mock_response.headers = {}
        mock_get.return_value = mock_response
        
        results = self.discovery.search_repositories("test", language="python")
        
        assert len(results) == 1
        assert isinstance(results[0], GitHubRepository)
        assert results[0].name == "test-repo"
        assert results[0].language == "Python"
    
    @patch('requests.get')
    def test_search_issues(self, mock_get):
        """Test issue search."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "title": "Test issue",
                    "number": 1,
                    "html_url": "https://github.com/user/repo/issues/1",
                    "state": "open",
                    "repository_url": "https://api.github.com/repos/user/repo",
                    "user": {"login": "testuser"},
                    "created_at": "2024-01-01T00:00:00Z",
                    "comments": 5,
                    "labels": [{"name": "bug"}],
                    "body": "Issue description"
                }
            ]
        }
        mock_response.headers = {}
        mock_get.return_value = mock_response
        
        results = self.discovery.search_issues("bug")
        
        assert len(results) == 1
        assert isinstance(results[0], GitHubIssue)
        assert results[0].title == "Test issue"
        assert results[0].state == "open"
    
    def test_repository_to_dict(self):
        """Test repository conversion to dict."""
        repo = GitHubRepository(
            name="test",
            full_name="user/test",
            description="Test",
            url="https://github.com/user/test",
            stars=100,
            forks=20,
            language="Python",
            topics=["test"],
            updated_at="2024-01-01"
        )
        
        result = repo.to_dict()
        
        assert isinstance(result, dict)
        assert result["name"] == "test"
        assert result["stars"] == 100
    
    def test_issue_to_dict(self):
        """Test issue conversion to dict."""
        issue = GitHubIssue(
            title="Test",
            number=1,
            url="https://github.com/user/repo/issues/1",
            state="open",
            repository="user/repo",
            author="testuser",
            created_at="2024-01-01",
            comments=5,
            labels=["bug"],
            body="Description"
        )
        
        result = issue.to_dict()
        
        assert isinstance(result, dict)
        assert result["title"] == "Test"
        assert result["number"] == 1
