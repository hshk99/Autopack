"""Tests for RedditGatherer module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from src.research.gatherers.reddit_gatherer import RedditGatherer


class TestRedditGatherer:
    """Test cases for RedditGatherer."""

    @pytest.fixture
    def mock_reddit(self):
        """Create a mock Reddit instance."""
        with patch('praw.Reddit') as mock:
            reddit = Mock()
            mock.return_value = reddit
            yield reddit

    @pytest.fixture
    def gatherer(self, mock_reddit):
        """Create a RedditGatherer instance with mocked dependencies."""
        with patch('src.research.gatherers.reddit_gatherer.RateLimiter'), \
             patch('src.research.gatherers.reddit_gatherer.ErrorHandler'):
            return RedditGatherer(
                client_id="test_id",
                client_secret="test_secret",
                user_agent="test_agent"
            )

    def test_initialization(self):
        """Test Reddit gatherer initialization."""
        with patch('praw.Reddit'), \
             patch('src.research.gatherers.reddit_gatherer.RateLimiter'), \
             patch('src.research.gatherers.reddit_gatherer.ErrorHandler'):
            gatherer = RedditGatherer(
                client_id="test_id",
                client_secret="test_secret",
                user_agent="test_agent"
            )
            assert gatherer is not None

    def test_gather_subreddit_info(self, gatherer, mock_reddit):
        """Test gathering subreddit information."""
        mock_subreddit = Mock()
        mock_subreddit.display_name = "test"
        mock_subreddit.title = "Test Subreddit"
        mock_subreddit.public_description = "A test subreddit"
        mock_subreddit.subscribers = 1000
        mock_subreddit.created_utc = 1609459200.0  # 2021-01-01
        
        mock_reddit.subreddit.return_value = mock_subreddit
        gatherer.reddit = mock_reddit
        gatherer._execute_with_rate_limit = Mock(return_value={
            "display_name": "test",
            "title": "Test Subreddit",
            "description": "A test subreddit",
            "subscribers": 1000,
            "created_utc": 1609459200.0,
            "url": "https://reddit.com/r/test"
        })
        
        result = gatherer.gather_subreddit_info("test")
        
        assert result["type"] == "subreddit_info"
        assert result["source"] == "reddit"
        assert result["subreddit"] == "test"
        assert result["data"]["name"] == "test"
        assert result["data"]["subscribers"] == 1000
        assert result["citation"]["source_type"] == "reddit_subreddit"

    def test_gather_posts(self, gatherer, mock_reddit):
        """Test gathering posts from a subreddit."""
        mock_post1 = Mock()
        mock_post1.id = "post1"
        mock_post1.title = "Test Post 1"
        mock_post1.selftext = "Post body 1"
        mock_post1.author = Mock()
        mock_post1.author.__str__ = Mock(return_value="testuser")
        mock_post1.score = 100
        mock_post1.upvote_ratio = 0.95
        mock_post1.num_comments = 10
        mock_post1.created_utc = 1609459200.0
        mock_post1.is_self = True
        mock_post1.url = "https://reddit.com/r/test/comments/post1"
        mock_post1.link_flair_text = "Discussion"
        mock_post1.permalink = "/r/test/comments/post1"
        
        mock_post2 = Mock()
        mock_post2.id = "post2"
        mock_post2.title = "Test Post 2"
        mock_post2.selftext = "Post body 2"
        mock_post2.author = Mock()
        mock_post2.author.__str__ = Mock(return_value="testuser2")
        mock_post2.score = 50
        mock_post2.upvote_ratio = 0.85
        mock_post2.num_comments = 5
        mock_post2.created_utc = 1609459200.0
        mock_post2.is_self = False
        mock_post2.url = "https://example.com"
        mock_post2.link_flair_text = None
        mock_post2.permalink = "/r/test/comments/post2"
        
        gatherer._execute_with_rate_limit = Mock(return_value=[mock_post1, mock_post2])
        
        results = gatherer.gather_posts("test", sort="hot", max_posts=10)
        
        assert len(results) == 2
        assert results[0]["type"] == "post"
        assert results[0]["data"]["id"] == "post1"
        assert results[0]["data"]["title"] == "Test Post 1"
        assert results[0]["citation"]["source_type"] == "reddit_post"
        assert results[1]["data"]["url"] == "https://example.com"

    def test_gather_comments(self, gatherer, mock_reddit):
        """Test gathering comments from a post."""
        mock_comment1 = Mock()
        mock_comment1.id = "comment1"
        mock_comment1.body = "Test comment 1"
        mock_comment1.author = Mock()
        mock_comment1.author.__str__ = Mock(return_value="commenter1")
        mock_comment1.score = 10
        mock_comment1.created_utc = 1609459200.0
        mock_comment1.is_submitter = False
        mock_comment1.parent_id = "t3_post1"
        mock_comment1.permalink = "/r/test/comments/post1/comment1"
        
        mock_submission = Mock()
        mock_submission.comments.replace_more = Mock()
        mock_submission.comments.list = Mock(return_value=[mock_comment1])
        
        gatherer._execute_with_rate_limit = Mock(return_value=[mock_comment1])
        
        results = gatherer.gather_comments("test", "post1", max_comments=10)
        
        assert len(results) == 1
        assert results[0]["type"] == "comment"
        assert results[0]["data"]["id"] == "comment1"
        assert results[0]["data"]["body"] == "Test comment 1"
        assert results[0]["citation"]["source_type"] == "reddit_comment"

    def test_search_subreddit(self, gatherer, mock_reddit):
        """Test searching a subreddit."""
        mock_post = Mock()
        mock_post.id = "search1"
        mock_post.title = "Search Result"
        mock_post.selftext = "Result body"
        mock_post.author = Mock()
        mock_post.author.__str__ = Mock(return_value="searchuser")
        mock_post.score = 75
        mock_post.num_comments = 8
        mock_post.created_utc = 1609459200.0
        mock_post.permalink = "/r/test/comments/search1"
        
        gatherer._execute_with_rate_limit = Mock(return_value=[mock_post])
        
        results = gatherer.search_subreddit(
            "test",
            "test query",
            sort="relevance",
            max_results=10
        )
        
        assert len(results) == 1
        assert results[0]["type"] == "search_result"
        assert results[0]["query"] == "test query"
        assert results[0]["data"]["title"] == "Search Result"
        assert results[0]["citation"]["source_type"] == "reddit_search"

    def test_execute_with_rate_limit_uses_rate_limiter(self, gatherer):
        """Test that _execute_with_rate_limit uses the rate limiter."""
        gatherer.rate_limiter.acquire = Mock()
        gatherer.error_handler.execute_with_retry = Mock(return_value="result")
        
        def test_func():
            return "result"
        
        result = gatherer._execute_with_rate_limit(test_func)
        
        gatherer.rate_limiter.acquire.assert_called_once()
        assert result == "result"

    def test_execute_with_rate_limit_uses_error_handler(self, gatherer):
        """Test that _execute_with_rate_limit uses the error handler."""
        gatherer.rate_limiter.acquire = Mock()
        gatherer.error_handler.execute_with_retry = Mock(return_value="result")
        
        def test_func():
            return "result"
        
        result = gatherer._execute_with_rate_limit(test_func)
        
        gatherer.error_handler.execute_with_retry.assert_called_once()
        assert result == "result"

    def test_gather_posts_different_sort_methods(self, gatherer):
        """Test gathering posts with different sort methods."""
        mock_posts = [Mock()]
        gatherer._execute_with_rate_limit = Mock(return_value=mock_posts)
        
        for sort in ["hot", "new", "top", "rising", "controversial"]:
            gatherer._execute_with_rate_limit.reset_mock()
            gatherer.gather_posts("test", sort=sort, max_posts=10)
            gatherer._execute_with_rate_limit.assert_called_once()

    def test_gather_posts_handles_deleted_author(self, gatherer):
        """Test handling posts with deleted authors."""
        mock_post = Mock()
        mock_post.id = "post1"
        mock_post.title = "Test Post"
        mock_post.selftext = "Post body"
        mock_post.author = None  # Deleted author
        mock_post.score = 100
        mock_post.upvote_ratio = 0.95
        mock_post.num_comments = 10
        mock_post.created_utc = 1609459200.0
        mock_post.is_self = True
        mock_post.url = "https://reddit.com/r/test/comments/post1"
        mock_post.link_flair_text = None
        mock_post.permalink = "/r/test/comments/post1"
        
        gatherer._execute_with_rate_limit = Mock(return_value=[mock_post])
        
        results = gatherer.gather_posts("test", max_posts=10)
        
        assert len(results) == 1
        assert results[0]["data"]["author"] == "[deleted]"
