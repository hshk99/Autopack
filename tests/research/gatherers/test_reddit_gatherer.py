"""Tests for Reddit Gatherer Module"""

import pytest
from unittest.mock import Mock, patch

# BUILD-146: Skip tests if praw is not installed
pytest.importorskip("praw")

from autopack.research.gatherers.reddit_gatherer import RedditGatherer
from autopack.research.gatherers.rate_limiter import RateLimiter
from autopack.research.gatherers.error_handler import ErrorHandler


class TestRedditGatherer:
    """Test cases for RedditGatherer class."""

    @pytest.fixture
    def mock_rate_limiter(self):
        """Create a mock rate limiter."""
        limiter = Mock(spec=RateLimiter)
        limiter.acquire = Mock()
        return limiter

    @pytest.fixture
    def mock_error_handler(self):
        """Create a mock error handler."""
        handler = Mock(spec=ErrorHandler)
        handler.execute_with_retry = Mock(side_effect=lambda f, retry_on: f())
        return handler

    @pytest.fixture
    def mock_reddit(self):
        """Create a mock Reddit instance."""
        with patch("praw.Reddit") as mock:
            yield mock

    @pytest.fixture
    def gatherer(self, mock_reddit, mock_rate_limiter, mock_error_handler):
        """Create a Reddit gatherer with mocked dependencies."""
        return RedditGatherer(
            client_id="test_id",
            client_secret="test_secret",
            user_agent="test_agent",
            rate_limiter=mock_rate_limiter,
            error_handler=mock_error_handler,
        )

    def test_initialization(self, gatherer, mock_reddit):
        """Test Reddit gatherer initialization."""
        assert gatherer.rate_limiter is not None
        assert gatherer.error_handler is not None
        mock_reddit.assert_called_once()

    def test_gather_subreddit_info(self, gatherer):
        """Test gathering subreddit information."""
        mock_subreddit = Mock()
        mock_subreddit.display_name = "test"
        mock_subreddit.title = "Test Subreddit"
        mock_subreddit.public_description = "A test subreddit"
        mock_subreddit.subscribers = 1000
        mock_subreddit.created_utc = 1609459200.0

        gatherer.reddit.subreddit = Mock(return_value=mock_subreddit)

        result = gatherer.gather_subreddit_info("test")

        assert result["type"] == "subreddit_info"
        assert result["subreddit"] == "r/test"
        assert result["data"]["display_name"] == "test"
        assert result["data"]["subscribers"] == 1000
        assert result["citation"]["source"] == "Reddit API"

    def test_gather_subreddit_posts_hot(self, gatherer):
        """Test gathering hot posts from a subreddit."""
        mock_post1 = Mock()
        mock_post1.id = "post1"
        mock_post1.title = "Test Post 1"
        mock_post1.selftext = "Content 1"
        mock_post1.author = "author1"
        mock_post1.score = 100
        mock_post1.upvote_ratio = 0.95
        mock_post1.num_comments = 10
        mock_post1.created_utc = 1609459200.0
        mock_post1.url = "https://reddit.com/r/test/post1"
        mock_post1.permalink = "/r/test/comments/post1"
        mock_post1.is_self = True
        mock_post1.link_flair_text = "Discussion"

        mock_post2 = Mock()
        mock_post2.id = "post2"
        mock_post2.title = "Test Post 2"
        mock_post2.selftext = "Content 2"
        mock_post2.author = "author2"
        mock_post2.score = 50
        mock_post2.upvote_ratio = 0.90
        mock_post2.num_comments = 5
        mock_post2.created_utc = 1609459300.0
        mock_post2.url = "https://reddit.com/r/test/post2"
        mock_post2.permalink = "/r/test/comments/post2"
        mock_post2.is_self = True
        mock_post2.link_flair_text = None

        mock_subreddit = Mock()
        mock_subreddit.hot = Mock(return_value=[mock_post1, mock_post2])
        gatherer.reddit.subreddit = Mock(return_value=mock_subreddit)

        results = gatherer.gather_subreddit_posts("test", sort="hot", max_posts=10)

        assert len(results) == 2
        assert results[0]["type"] == "subreddit_post"
        assert results[0]["data"]["id"] == "post1"
        assert results[0]["data"]["title"] == "Test Post 1"
        assert results[1]["data"]["id"] == "post2"

    def test_gather_subreddit_posts_top(self, gatherer):
        """Test gathering top posts from a subreddit."""
        mock_post = Mock()
        mock_post.id = "post1"
        mock_post.title = "Top Post"
        mock_post.selftext = "Top content"
        mock_post.author = "author1"
        mock_post.score = 1000
        mock_post.upvote_ratio = 0.98
        mock_post.num_comments = 100
        mock_post.created_utc = 1609459200.0
        mock_post.url = "https://reddit.com/r/test/post1"
        mock_post.permalink = "/r/test/comments/post1"
        mock_post.is_self = True
        mock_post.link_flair_text = "Popular"

        mock_subreddit = Mock()
        mock_subreddit.top = Mock(return_value=[mock_post])
        gatherer.reddit.subreddit = Mock(return_value=mock_subreddit)

        results = gatherer.gather_subreddit_posts(
            "test", sort="top", time_filter="week", max_posts=10
        )

        assert len(results) == 1
        assert results[0]["data"]["title"] == "Top Post"
        mock_subreddit.top.assert_called_once_with(time_filter="week", limit=10)

    def test_gather_post_comments(self, gatherer):
        """Test gathering comments from a post."""
        mock_comment1 = Mock()
        mock_comment1.id = "comment1"
        mock_comment1.body = "Test comment 1"
        mock_comment1.author = "commenter1"
        mock_comment1.score = 10
        mock_comment1.created_utc = 1609459200.0
        mock_comment1.permalink = "/r/test/comments/post1/comment1"
        mock_comment1.is_submitter = False

        mock_comment2 = Mock()
        mock_comment2.id = "comment2"
        mock_comment2.body = "Test comment 2"
        mock_comment2.author = "commenter2"
        mock_comment2.score = 5
        mock_comment2.created_utc = 1609459300.0
        mock_comment2.permalink = "/r/test/comments/post1/comment2"
        mock_comment2.is_submitter = True

        mock_submission = Mock()
        mock_submission.comments.replace_more = Mock()
        mock_submission.comments.list = Mock(return_value=[mock_comment1, mock_comment2])

        gatherer.reddit.submission = Mock(return_value=mock_submission)

        results = gatherer.gather_post_comments("test", "post1", max_comments=10)

        assert len(results) == 2
        assert results[0]["type"] == "post_comment"
        assert results[0]["data"]["id"] == "comment1"
        assert results[0]["data"]["body"] == "Test comment 1"
        assert results[1]["data"]["is_submitter"] is True

    def test_search_subreddit(self, gatherer):
        """Test searching a subreddit."""
        mock_post = Mock()
        mock_post.id = "search1"
        mock_post.title = "Search Result"
        mock_post.selftext = "Matching content"
        mock_post.author = "author1"
        mock_post.score = 50
        mock_post.num_comments = 10
        mock_post.created_utc = 1609459200.0
        mock_post.permalink = "/r/test/comments/search1"

        mock_subreddit = Mock()
        mock_subreddit.search = Mock(return_value=[mock_post])
        gatherer.reddit.subreddit = Mock(return_value=mock_subreddit)

        results = gatherer.search_subreddit("test", "query", sort="relevance", max_results=10)

        assert len(results) == 1
        assert results[0]["type"] == "search_result"
        assert results[0]["query"] == "query"
        assert results[0]["data"]["title"] == "Search Result"
        mock_subreddit.search.assert_called_once_with(
            "query", sort="relevance", time_filter="all", limit=10
        )

    def test_rate_limiting_applied(self, gatherer, mock_rate_limiter):
        """Test that rate limiting is applied to requests."""
        mock_subreddit = Mock()
        mock_subreddit.display_name = "test"
        mock_subreddit.title = "Test"
        mock_subreddit.public_description = "Test"
        mock_subreddit.subscribers = 100
        mock_subreddit.created_utc = 1609459200.0

        gatherer.reddit.subreddit = Mock(return_value=mock_subreddit)

        gatherer.gather_subreddit_info("test")

        # Verify rate limiter was called
        mock_rate_limiter.acquire.assert_called()

    def test_error_handling(self, gatherer):
        """Test error handling for failed requests."""
        gatherer.reddit.subreddit = Mock(side_effect=Exception("API Error"))

        with pytest.raises(Exception):
            gatherer.gather_subreddit_info("test")
