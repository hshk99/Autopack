"""Tests for Reddit Discovery."""

from unittest.mock import Mock, patch

from autopack.research.discovery.reddit_discovery import (RedditComment,
                                                          RedditDiscovery,
                                                          RedditPost)


class TestRedditDiscovery:
    """Test cases for RedditDiscovery."""

    def setup_method(self):
        """Set up test fixtures."""
        self.discovery = RedditDiscovery()

    @patch("requests.get")
    def test_search_posts(self, mock_get):
        """Test post search."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Test post",
                            "subreddit": "test",
                            "author": "testuser",
                            "url": "https://reddit.com/test",
                            "score": 100,
                            "num_comments": 20,
                            "created_utc": 1234567890,
                            "selftext": "Post content",
                            "permalink": "/r/test/comments/abc123",
                        }
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        results = self.discovery.search_posts("test query")

        assert len(results) == 1
        assert isinstance(results[0], RedditPost)
        assert results[0].title == "Test post"
        assert results[0].subreddit == "test"

    @patch("requests.get")
    def test_get_subreddit_posts(self, mock_get):
        """Test getting posts from subreddit."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Subreddit post",
                            "subreddit": "python",
                            "author": "testuser",
                            "url": "https://reddit.com/test",
                            "score": 50,
                            "num_comments": 10,
                            "created_utc": 1234567890,
                            "selftext": "Content",
                            "permalink": "/r/python/comments/xyz789",
                        }
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        results = self.discovery.get_subreddit_posts("python")

        assert len(results) == 1
        assert results[0].subreddit == "python"

    def test_post_to_dict(self):
        """Test post conversion to dict."""
        post = RedditPost(
            title="Test",
            subreddit="test",
            author="user",
            url="https://reddit.com/test",
            score=100,
            num_comments=20,
            created_utc=1234567890,
            selftext="Content",
            permalink="/r/test/comments/abc",
        )

        result = post.to_dict()

        assert isinstance(result, dict)
        assert result["title"] == "Test"
        assert result["score"] == 100

    def test_comment_to_dict(self):
        """Test comment conversion to dict."""
        comment = RedditComment(
            author="user",
            body="Comment text",
            score=10,
            created_utc=1234567890,
            permalink="/r/test/comments/abc/comment/def",
        )

        result = comment.to_dict()

        assert isinstance(result, dict)
        assert result["author"] == "user"
        assert result["body"] == "Comment text"
