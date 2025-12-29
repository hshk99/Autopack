"""Tests for LinkedIn gatherer."""

import pytest
from unittest.mock import Mock, patch

from autopack.research.gatherers.linkedin_gatherer import LinkedInGatherer
from autopack.research.models.enums import EvidenceType


@pytest.fixture
def mock_linkedin_response():
    """Mock LinkedIn API response."""
    return {
        "elements": [
            {
                "id": "urn:li:ugcPost:123456",
                "author": "urn:li:person:abc123",
                "created": {"time": 1705320000000},
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {
                            "text": "Insights on AI implementation in enterprise environments."
                        }
                    }
                },
                "socialDetail": {
                    "totalShareStatistics": {
                        "likeCount": 100,
                        "commentCount": 20,
                    }
                },
            },
            {
                "id": "urn:li:ugcPost:789012",
                "author": "urn:li:person:def456",
                "created": {"time": 1705406400000},
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {
                            "text": "Case study: Successful ML deployment at Fortune 500 company."
                        }
                    }
                },
                "socialDetail": {
                    "totalShareStatistics": {
                        "likeCount": 150,
                        "commentCount": 30,
                    }
                },
            },
        ]
    }


@pytest.fixture
def gatherer():
    """Create LinkedIn gatherer with mock token."""
    with patch.dict("os.environ", {"LINKEDIN_ACCESS_TOKEN": "test_token"}):
        return LinkedInGatherer()


def test_init_with_token():
    """Test initialization with access token."""
    gatherer = LinkedInGatherer(access_token="test_token")
    assert gatherer.access_token == "test_token"
    assert gatherer.base_url == "https://api.linkedin.com/v2"


def test_init_without_credentials():
    """Test initialization fails without credentials."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="LinkedIn credentials required"):
            LinkedInGatherer()


def test_get_access_token_not_implemented(gatherer):
    """Test that OAuth refresh is not implemented."""
    gatherer.access_token = None
    gatherer.client_id = "test_id"
    gatherer.client_secret = "test_secret"

    with pytest.raises(NotImplementedError, match="OAuth token refresh not implemented"):
        gatherer._get_access_token()


@patch("requests.get")
def test_search_posts(mock_get, gatherer, mock_linkedin_response):
    """Test searching for posts."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_linkedin_response
    mock_get.return_value = mock_response

    posts = gatherer.search_posts("AI implementation", limit=10)

    assert len(posts) == 2
    assert posts[0]["id"] == "urn:li:ugcPost:123456"
    mock_get.assert_called_once()


@patch("requests.get")
def test_search_posts_access_denied(mock_get, gatherer):
    """Test handling of access denied errors."""
    mock_response = Mock()
    mock_response.status_code = 403
    mock_get.return_value = mock_response

    with pytest.raises(RuntimeError, match="LinkedIn API access denied"):
        gatherer.search_posts("test query")


@patch("requests.get")
def test_get_user_posts(mock_get, gatherer, mock_linkedin_response):
    """Test getting user posts."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_linkedin_response
    mock_get.return_value = mock_response

    posts = gatherer.get_user_posts("urn:li:person:abc123", limit=10)

    assert len(posts) == 2
    mock_get.assert_called_once()


@patch("requests.get")
def test_get_articles(mock_get, gatherer):
    """Test getting articles."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "elements": [
            {
                "id": "article123",
                "title": "AI Best Practices",
                "content": "Detailed article content...",
            }
        ]
    }
    mock_get.return_value = mock_response

    articles = gatherer.get_articles("AI best practices", limit=10)

    assert len(articles) == 1
    assert articles[0]["id"] == "article123"


def test_extract_findings(gatherer, mock_linkedin_response):
    """Test extracting findings from posts."""
    posts = mock_linkedin_response["elements"]
    findings = gatherer.extract_findings(posts, "AI research")

    assert len(findings) == 2

    # Check first finding (short post = anecdotal)
    evidence = findings[0]
    assert "Insights on AI implementation" in evidence.content
    assert evidence.evidence_type == EvidenceType.ANECDOTAL
    assert evidence.citation.publication == "LinkedIn"
    assert evidence.citation.year == 2024
    assert "linkedin.com" in evidence.citation.url
    assert "linkedin" in evidence.tags
    assert "professional" in evidence.tags

    # Check second finding (longer post = case study)
    evidence2 = findings[1]
    assert evidence2.evidence_type == EvidenceType.CASE_STUDY
    assert "Case study" in evidence2.content

    # Check metadata
    assert evidence.metadata["post_id"] == "urn:li:ugcPost:123456"
    assert "engagement" in evidence.metadata


def test_extract_findings_skips_empty_posts(gatherer):
    """Test that empty posts are skipped."""
    posts = [
        {
            "id": "urn:li:ugcPost:123",
            "author": "urn:li:person:abc",
            "created": {"time": 1705320000000},
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {"shareCommentary": {"text": ""}}
            },
        },
        {
            "id": "urn:li:ugcPost:456",
            "author": "urn:li:person:def",
            "created": {"time": 1705320000000},
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": "Valid post content"}
                }
            },
        },
    ]

    findings = gatherer.extract_findings(posts, "test topic")

    assert len(findings) == 1
    assert findings[0].metadata["post_id"] == "urn:li:ugcPost:456"


def test_extract_findings_evidence_type_classification(gatherer):
    """Test evidence type classification based on content length."""
    posts = [
        {
            "id": "short",
            "author": "urn:li:person:abc",
            "created": {"time": 1705320000000},
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": "Short post"}
                }
            },
        },
        {
            "id": "long",
            "author": "urn:li:person:def",
            "created": {"time": 1705320000000},
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": "A" * 300  # Long post (300 chars)
                    }
                }
            },
        },
    ]

    findings = gatherer.extract_findings(posts, "test")

    assert findings[0].evidence_type == EvidenceType.ANECDOTAL  # Short
    assert findings[1].evidence_type == EvidenceType.CASE_STUDY  # Long
