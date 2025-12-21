"""
Test Suite for Reddit Discovery

This module contains unit tests for the RedditDiscovery class.
"""

import unittest
from unittest.mock import patch, MagicMock
from src.autopack.research.discovery.reddit_discovery import RedditDiscovery

class TestRedditDiscovery(unittest.TestCase):

    def setUp(self):
        """
        Set up the test case environment.
        """
        self.reddit_discovery = RedditDiscovery(client_id="fake_id", client_secret="fake_secret", user_agent="fake_agent")

    @patch('src.autopack.research.discovery.reddit_discovery.praw.Reddit')
    def test_search_submissions(self, MockReddit):
        """
        Test searching submissions on Reddit.
        """
        mock_submission = MagicMock(title="Test Submission", url="http://reddit.com/test/submission")
        MockReddit.return_value.subreddit.return_value.search.return_value = [mock_submission]
        results = self.reddit_discovery.search_submissions("test query", "testsub")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['title'], "Test Submission")

    @patch('src.autopack.research.discovery.reddit_discovery.praw.Reddit')
    def test_search_comments(self, MockReddit):
        """
        Test searching comments on Reddit.
        """
        mock_comment = MagicMock(body="Test Comment", permalink="http://reddit.com/test/comment")
        MockReddit.return_value.subreddit.return_value.comments.return_value = [mock_comment]
        results = self.reddit_discovery.search_comments("test query", "testsub")
        self.assertEqual(len(results), 1)
        self.assertIn("Test Comment", results[0]['body'])

    # Additional tests for more complex scenarios can be added here

if __name__ == '__main__':
    unittest.main()
