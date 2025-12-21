"""Reddit Gatherer Module

This module provides functionality to gather data from Reddit communities.
"""

import praw
from .rate_limiter import RateLimiter
from .error_handler import ErrorHandler

class RedditGatherer:
    """Gathers data from Reddit communities."""

    def __init__(self, client_id, client_secret, user_agent):
        self.reddit = praw.Reddit(client_id=client_id,
                                  client_secret=client_secret,
                                  user_agent=user_agent)
        self.rate_limiter = RateLimiter()
        self.error_handler = ErrorHandler()

    def collect_subreddit_data(self, subreddit_name):
        """Collects data from a subreddit.

        Args:
            subreddit_name (str): The name of the subreddit.

        Returns:
            dict: A dictionary containing subreddit data.
        """
        return self.error_handler.handle_error(self._get_subreddit_info, subreddit_name)

    def _get_subreddit_info(self, subreddit_name):
        """Retrieves subreddit information.

        Args:
            subreddit_name (str): The name of the subreddit.

        Returns:
            dict: Subreddit information.
        """
        self.rate_limiter.wait_for_rate_limit()
        subreddit = self.reddit.subreddit(subreddit_name)
        return {
            "name": subreddit.display_name,
            "title": subreddit.title,
            "description": subreddit.description,
            "subscribers": subreddit.subscribers
        }

    def collect_posts(self, subreddit_name, limit=10):
        """Collects posts from a subreddit.

        Args:
            subreddit_name (str): The name of the subreddit.
            limit (int): The number of posts to retrieve.

        Returns:
            list: A list of posts.
        """
        return self.error_handler.handle_error(self._get_posts, subreddit_name, limit)

    def _get_posts(self, subreddit_name, limit):
        """Retrieves posts from a subreddit.

        Args:
            subreddit_name (str): The name of the subreddit.
            limit (int): The number of posts to retrieve.

        Returns:
            list: A list of posts.
        """
        self.rate_limiter.wait_for_rate_limit()
        subreddit = self.reddit.subreddit(subreddit_name)
        return [{
            "title": post.title,
            "score": post.score,
            "url": post.url,
            "num_comments": post.num_comments
        } for post in subreddit.hot(limit=limit)]

    def collect_comments(self, post_id):
        """Collects comments from a Reddit post.

        Args:
            post_id (str): The ID of the post.

        Returns:
            list: A list of comments.
        """
        return self.error_handler.handle_error(self._get_comments, post_id)

    def _get_comments(self, post_id):
        """Retrieves comments from a Reddit post.

        Args:
            post_id (str): The ID of the post.

        Returns:
            list: A list of comments.
        """
        self.rate_limiter.wait_for_rate_limit()
        submission = self.reddit.submission(id=post_id)
        submission.comments.replace_more(limit=0)
        return [comment.body for comment in submission.comments.list()]
