"""
Reddit Discovery Module

This module defines the RedditDiscovery class, which mines Reddit threads and comments
to gather community insights and opinions relevant to research topics.
"""

from typing import List, Dict
import praw


class RedditDiscovery:
    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        """
        Initialize the RedditDiscovery with API credentials.

        :param client_id: Reddit API client ID.
        :param client_secret: Reddit API client secret.
        :param user_agent: User agent for the Reddit API.
        """
        self.reddit = praw.Reddit(
            client_id=client_id, client_secret=client_secret, user_agent=user_agent
        )

    def search_submissions(self, query: str, subreddit: str) -> List[Dict[str, str]]:
        """
        Search Reddit submissions based on a query.

        :param query: The search query.
        :param subreddit: The subreddit to search within.
        :return: A list of submissions matching the query.
        """
        submissions = self.reddit.subreddit(subreddit).search(query)
        return [{"title": submission.title, "url": submission.url} for submission in submissions]

    def search_comments(self, query: str, subreddit: str) -> List[Dict[str, str]]:
        """
        Search Reddit comments based on a query.

        :param query: The search query.
        :param subreddit: The subreddit to search within.
        :return: A list of comments matching the query.
        """
        comments = self.reddit.subreddit(subreddit).comments()
        matching_comments = [
            comment for comment in comments if query.lower() in comment.body.lower()
        ]
        return [{"body": comment.body, "url": comment.permalink} for comment in matching_comments]

    # Additional methods for more specific Reddit mining tasks can be added here


# Backward compatibility shims
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass
class RedditPost:
    """Compat shim for RedditPost."""

    title: str
    url: str
    subreddit: str = ""
    author: str = ""
    score: int = 0
    created_at: Optional[datetime] = None


@dataclass
class RedditComment:
    """Compat shim for RedditComment."""

    body: str
    author: str = ""
    score: int = 0
    created_at: Optional[datetime] = None
