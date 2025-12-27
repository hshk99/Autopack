"""Tests for GitHubGatherer module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.research.gatherers.github_gatherer import GitHubGatherer


class TestGitHubGatherer:
    """Test cases for GitHubGatherer."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        with patch('requests.Session') as mock:
            session = Mock()
            mock.return_value = session
            yield session

    @pytest.fixture
    def gatherer(self, mock_session):
        """Create a GitHubGatherer instance with mocked dependencies."""
        with patch('src.research.gatherers.github_gatherer.RateLimiter'), \
             patch('src.research.gatherers.github_gatherer.ErrorHandler'):
            return GitHubGatherer(token="test_token")

    def test_initialization_with_token(self):
        """Test initialization with authentication token."""
        with patch('src.research.gatherers.github_gatherer.RateLimiter'), \
             patch('src.research.gatherers.github_gatherer.ErrorHandler'):
            gatherer = GitHubGatherer(token="test_token")
            assert gatherer.token == "test_token"

    def test_initialization_without_token(self):
        """Test initialization without authentication token."""
        with patch('src.research.gatherers.github_gatherer.RateLimiter'), \
             patch('src.research.gatherers.github_gatherer.ErrorHandler'):
            gatherer = GitHubGatherer()
            assert gatherer.token is None

    def test_gather_repository_info(self, gatherer):
        """Test gathering repository information."""
        mock_data = {
            "name": "test-repo",
            "full_name": "owner/test-repo",
            "description": "Test repository",
            "html_url": "https://github.com/owner/test-repo",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
            "language": "Python",
            "created_at": "2020-01-01T00:00:00Z",
            "updated_at": "2023-01-01T00:00:00Z",
            "topics": ["python", "testing"],
            "license": {"name": "MIT"}
        }
        
        gatherer._make_request = Mock(return_value=mock_data)
        
        result = gatherer.gather_repository_info("owner", "test-repo")
        
        assert result["type"] == "repository_info"
        assert result["source"] == "github"
        assert result["repository"] == "owner/test-repo"
        assert result["data"]["name"] == "test-repo"
        assert result["data"]["stars"] == 100
        assert result["citation"]["source_type"] == "github_repository"

    def test_gather_readme(self, gatherer):
        """Test gathering README content."""
        import base64
        
        readme_content = "# Test README\n\nThis is a test."
        encoded_content = base64.b64encode(readme_content.encode()).decode()
        
        mock_data = {
            "name": "README.md",
            "path": "README.md",
            "content": encoded_content,
            "html_url": "https://github.com/owner/test-repo/blob/main/README.md",
            "size": len(readme_content)
        }
        
        gatherer._make_request = Mock(return_value=mock_data)
        
        result = gatherer.gather_readme("owner", "test-repo")
        
        assert result["type"] == "readme"
        assert result["source"] == "github"
        assert result["data"]["content"] == readme_content
        assert result["citation"]["source_type"] == "github_readme"

    def test_gather_issues(self, gatherer):
        """Test gathering issues."""
        mock_issues = [
            {
                "number": 1,
                "title": "Test issue 1",
                "body": "Issue body 1",
                "state": "open",
                "html_url": "https://github.com/owner/test-repo/issues/1",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-02T00:00:00Z",
                "closed_at": None,
                "labels": [{"name": "bug"}],
                "comments": 3,
                "user": {"login": "testuser"}
            },
            {
                "number": 2,
                "title": "Test issue 2",
                "body": "Issue body 2",
                "state": "closed",
                "html_url": "https://github.com/owner/test-repo/issues/2",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-03T00:00:00Z",
                "closed_at": "2023-01-03T00:00:00Z",
                "labels": [],
                "comments": 0,
                "user": {"login": "testuser2"}
            }
        ]
        
        gatherer._make_request = Mock(return_value=mock_issues)
        
        results = gatherer.gather_issues("owner", "test-repo", max_issues=10)
        
        assert len(results) == 2
        assert results[0]["type"] == "issue"
        assert results[0]["data"]["number"] == 1
        assert results[0]["data"]["title"] == "Test issue 1"
        assert results[0]["citation"]["source_type"] == "github_issue"

    def test_gather_issues_skips_pull_requests(self, gatherer):
        """Test that pull requests are skipped when gathering issues."""
        mock_issues = [
            {
                "number": 1,
                "title": "Test issue",
                "body": "Issue body",
                "state": "open",
                "html_url": "https://github.com/owner/test-repo/issues/1",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-02T00:00:00Z",
                "closed_at": None,
                "labels": [],
                "comments": 0,
                "user": {"login": "testuser"}
            },
            {
                "number": 2,
                "title": "Test PR",
                "body": "PR body",
                "state": "open",
                "html_url": "https://github.com/owner/test-repo/pull/2",
                "pull_request": {"url": "https://api.github.com/repos/owner/test-repo/pulls/2"},
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-02T00:00:00Z",
                "closed_at": None,
                "labels": [],
                "comments": 0,
                "user": {"login": "testuser"}
            }
        ]
        
        gatherer._make_request = Mock(return_value=mock_issues)
        
        results = gatherer.gather_issues("owner", "test-repo", max_issues=10)
        
        # Should only have the issue, not the PR
        assert len(results) == 1
        assert results[0]["data"]["number"] == 1

    def test_gather_pull_requests(self, gatherer):
        """Test gathering pull requests."""
        mock_prs = [
            {
                "number": 1,
                "title": "Test PR 1",
                "body": "PR body 1",
                "state": "open",
                "html_url": "https://github.com/owner/test-repo/pull/1",
                "created_at": "2023-01-01T00:00:00Z",
                "updated_at": "2023-01-02T00:00:00Z",
                "closed_at": None,
                "merged_at": None,
                "labels": [{"name": "enhancement"}],
                "user": {"login": "testuser"},
                "base": {"ref": "main"},
                "head": {"ref": "feature-branch"}
            }
        ]
        
        gatherer._make_request = Mock(return_value=mock_prs)
        
        results = gatherer.gather_pull_requests("owner", "test-repo", max_prs=10)
        
        assert len(results) == 1
        assert results[0]["type"] == "pull_request"
        assert results[0]["data"]["number"] == 1
        assert results[0]["data"]["base_branch"] == "main"
        assert results[0]["citation"]["source_type"] == "github_pull_request"

    def test_make_request_uses_rate_limiter(self, gatherer):
        """Test that _make_request uses the rate limiter."""
        gatherer.rate_limiter.acquire = Mock()
        gatherer.error_handler.execute_with_retry = Mock(return_value={"test": "data"})
        
        gatherer._make_request("test/endpoint")
        
        gatherer.rate_limiter.acquire.assert_called_once()

    def test_make_request_uses_error_handler(self, gatherer):
        """Test that _make_request uses the error handler."""
        gatherer.rate_limiter.acquire = Mock()
        gatherer.error_handler.execute_with_retry = Mock(return_value={"test": "data"})
        
        result = gatherer._make_request("test/endpoint")
        
        gatherer.error_handler.execute_with_retry.assert_called_once()
        assert result == {"test": "data"}
