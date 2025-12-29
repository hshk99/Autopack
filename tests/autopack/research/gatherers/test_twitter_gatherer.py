"""Tests for Twitter gatherer."""

import pytest
from unittest.mock import Mock, patch

from autopack.research.gatherers.twitter_gatherer import TwitterGatherer
from autopack.research.models.enums import EvidenceType


@pytest.fixture
def mock_twitter_response():
    """Mock Twitter API response."""
    return {
        "data": [
            {
                "id": "1234567890",
                "text": "Interesting research finding about AI safety measures.",
                "created_at": "2024-01-15T12:00:00.000Z",
                "author_id": "123456",
                "public_metrics": {
                    "retweet_count": 10,
                    "like_count": 50,
                },
            },
            {
                "id": "1234567891",
                "text": "New study shows effectiveness of ML techniques.",
                "created_at": "2024-01-16T14:30:00.000Z",
                "author_id": "123457",
                "public_metrics": {
                    "retweet_count": 5,
                    "like_count": 25,
                },
            },
        ]
    }


@pytest.fixture
def gatherer():
    """Create Twitter gatherer with mock token."""
    with patch.dict("os.environ", {"TWITTER_BEARER_TOKEN": "test_token"}):
        return TwitterGatherer()


def test_init_with_token():
    """Test initialization with bearer token."""
    gatherer = TwitterGatherer(bearer_token="test_token")
    assert gatherer.bearer_token == "test_token"
    assert gatherer.base_url == "https://api.twitter.com/2"


def test_init_without_token():
    """Test initialization fails without token."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="Twitter bearer token required"):
            TwitterGatherer()


@patch("requests.get")
def test_search_tweets(mock_get, gatherer, mock_twitter_response):
    """Test searching for tweets."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = mock_twitter_response
    mock_response.headers = {
        "x-rate-limit-remaining": "100",
        "x-rate-limit-reset": "1234567890",
    }
    mock_get.return_value = mock_response

    tweets = gatherer.search_tweets("AI safety", max_results=10)

    assert len(tweets) == 2
    assert tweets[0]["id"] == "1234567890"
    assert "AI safety" in tweets[0]["text"]
    mock_get.assert_called_once()


@patch("requests.get")
def test_search_tweets_rate_limit(mock_get, gatherer):
    """Test rate limit handling."""
    mock_response = Mock()
    mock_response.status_code = 429
    mock_get.return_value = mock_response

    with pytest.raises(RuntimeError, match="rate limit exceeded"):
        gatherer.search_tweets("test query")


@patch("requests.get")
def test_get_user_tweets(mock_get, gatherer, mock_twitter_response):
    """Test getting user tweets."""
    # Mock user lookup
    user_response = Mock()
    user_response.status_code = 200
    user_response.json.return_value = {"data": {"id": "123456"}}

    # Mock tweets response
    tweets_response = Mock()
    tweets_response.status_code = 200
    tweets_response.json.return_value = mock_twitter_response
    tweets_response.headers = {
        "x-rate-limit-remaining": "100",
        "x-rate-limit-reset": "1234567890",
    }

    mock_get.side_effect = [user_response, tweets_response]

    tweets = gatherer.get_user_tweets("testuser", max_results=10)

    assert len(tweets) == 2
    assert mock_get.call_count == 2


def test_extract_findings(gatherer, mock_twitter_response):
    """Test extracting findings from tweets."""
    tweets = mock_twitter_response["data"]
    findings = gatherer.extract_findings(tweets, "AI research")

    assert len(findings) == 2

    # Check first finding
    evidence = findings[0]
    assert evidence.content == "Interesting research finding about AI safety measures."
    assert evidence.evidence_type == EvidenceType.ANECDOTAL
    assert evidence.citation.publication == "Twitter/X"
    assert evidence.citation.year == 2024
    assert "twitter.com" in evidence.citation.url
    assert "twitter" in evidence.tags

    # Check metadata
    assert evidence.metadata["tweet_id"] == "1234567890"
    assert evidence.metadata["metrics"]["like_count"] == 50


def test_extract_findings_skips_empty_tweets(gatherer):
    """Test that empty tweets are skipped."""
    tweets = [
        {"id": "123", "created_at": "2024-01-15T12:00:00.000Z"},  # No text
        {
            "id": "456",
            "text": "Valid tweet",
            "created_at": "2024-01-15T12:00:00.000Z",
        },
    ]

    findings = gatherer.extract_findings(tweets, "test topic")

    assert len(findings) == 1
    assert findings[0].metadata["tweet_id"] == "456"


def test_rate_limit_tracking(gatherer):
    """Test rate limit tracking updates."""
    mock_response = Mock()
    mock_response.headers = {
        "x-rate-limit-remaining": "50",
        "x-rate-limit-reset": "1234567890",
    }

    gatherer._update_rate_limit(mock_response)

    assert gatherer.rate_limit_remaining == 50
    assert gatherer.rate_limit_reset == 1234567890
