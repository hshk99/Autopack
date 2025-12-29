"""Tests for Reddit gatherer."""

import pytest
from unittest.mock import Mock, patch

from autopack.research.gatherers.reddit_gatherer import RedditGatherer
from autopack.research.models.enums import EvidenceType


@pytest.fixture
def mock_reddit_response():
    """Mock Reddit API response."""
    return {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "abc123",
                        "title": "Research on ML best practices",
                        "selftext": "Detailed findings about machine learning techniques.",
                        "subreddit": "MachineLearning",
                        "author": "researcher123",
                        "created_utc": 1705320000,
                        "score": 150,
                        "num_comments": 25,
                    }
                },
                {
                    "data": {
                        "id": "def456",
                        "title": "AI safety discussion",
                        "selftext": "Important considerations for AI safety.",
                        "subreddit": "artificial",
                        "author": "aiexpert",
                        "created_utc": 1705406400,
                        "score": 200,
                        "num_comments": 40,
                    }
                },
            ]
        }
    }


@pytest.fixture
def gatherer():
    """Create Reddit gatherer with mock credentials."""
    with patch.dict(
        "os.environ",
        {
            "REDDIT_CLIENT_ID": "test_client_id",
            "REDDIT_CLIENT_SECRET": "test_client_secret",
        },
    ):
        return RedditGatherer()


def test_init_with_credentials():
    """Test initialization with credentials."""
    gatherer = RedditGatherer(
        client_id="test_id",
        client_secret="test_secret",
        user_agent="TestBot/1.0",
    )
    assert gatherer.client_id == "test_id"
    assert gatherer.client_secret == "test_secret"
    assert gatherer.user_agent == "TestBot/1.0"


def test_init_without_credentials():
    """Test initialization fails without credentials."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="Reddit credentials required"):
            RedditGatherer()


@patch("requests.post")
def test_get_access_token(mock_post, gatherer):
    """Test OAuth token retrieval."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "test_token_123",
        "expires_in": 3600,
    }
    mock_post.return_value = mock_response

    token = gatherer._get_access_token()

    assert token == "test_token_123"
    assert gatherer.access_token == "test_token_123"
    mock_post.assert_called_once()


@patch("requests.get")
@patch("requests.post")
def test_search_posts(mock_post, mock_get, gatherer, mock_reddit_response):
    """Test searching for posts."""
    # Mock token request
    token_response = Mock()
    token_response.json.return_value = {
        "access_token": "test_token",
        "expires_in": 3600,
    }
    mock_post.return_value = token_response

    # Mock search request
    search_response = Mock()
    search_response.status_code = 200
    search_response.json.return_value = mock_reddit_response
    mock_get.return_value = search_response

    posts = gatherer.search_posts("machine learning", limit=10)

    assert len(posts) == 2
    assert posts[0]["id"] == "abc123"
    assert "ML best practices" in posts[0]["title"]


@patch("requests.get")
@patch("requests.post")
def test_get_subreddit_posts(mock_post, mock_get, gatherer, mock_reddit_response):
    """Test getting posts from subreddit."""
    # Mock token
    token_response = Mock()
    token_response.json.return_value = {
        "access_token": "test_token",
        "expires_in": 3600,
    }
    mock_post.return_value = token_response

    # Mock subreddit posts
    posts_response = Mock()
    posts_response.status_code = 200
    posts_response.json.return_value = mock_reddit_response
    mock_get.return_value = posts_response

    posts = gatherer.get_subreddit_posts("MachineLearning", limit=10)

    assert len(posts) == 2
    assert posts[0]["subreddit"] == "MachineLearning"


def test_extract_findings(gatherer, mock_reddit_response):
    """Test extracting findings from posts."""
    posts = [child["data"] for child in mock_reddit_response["data"]["children"]]
    findings = gatherer.extract_findings(posts, "ML research")

    assert len(findings) == 2

    # Check first finding
    evidence = findings[0]
    assert "Research on ML best practices" in evidence.content
    assert "Detailed findings" in evidence.content
    assert evidence.evidence_type == EvidenceType.ANECDOTAL
    assert evidence.citation.publication == "r/MachineLearning"
    assert "u/researcher123" in evidence.citation.authors
    assert "reddit.com" in evidence.citation.url

    # Check metadata
    assert evidence.metadata["post_id"] == "abc123"
    assert evidence.metadata["score"] == 150
    assert evidence.metadata["num_comments"] == 25
    assert "reddit" in evidence.tags
    assert "MachineLearning" in evidence.tags


def test_extract_findings_skips_empty_posts(gatherer):
    """Test that empty posts are skipped."""
    posts = [
        {
            "id": "123",
            "title": "",
            "selftext": "",
            "subreddit": "test",
            "author": "user",
            "created_utc": 1705320000,
        },
        {
            "id": "456",
            "title": "Valid post",
            "selftext": "Content",
            "subreddit": "test",
            "author": "user",
            "created_utc": 1705320000,
        },
    ]

    findings = gatherer.extract_findings(posts, "test topic")

    assert len(findings) == 1
    assert findings[0].metadata["post_id"] == "456"


@patch("requests.get")
@patch("requests.post")
def test_get_post_comments(mock_post, mock_get, gatherer):
    """Test getting comments from a post."""
    # Mock token
    token_response = Mock()
    token_response.json.return_value = {
        "access_token": "test_token",
        "expires_in": 3600,
    }
    mock_post.return_value = token_response

    # Mock comments response
    comments_response = Mock()
    comments_response.status_code = 200
    comments_response.json.return_value = [
        {},  # Post data
        {
            "data": {
                "children": [
                    {
                        "kind": "t1",
                        "data": {
                            "id": "comment1",
                            "body": "Great post!",
                            "author": "commenter",
                        },
                    }
                ]
            }
        },
    ]
    mock_get.return_value = comments_response

    comments = gatherer.get_post_comments("abc123", "MachineLearning", limit=10)

    assert len(comments) == 1
    assert comments[0]["id"] == "comment1"
    assert comments[0]["body"] == "Great post!"
