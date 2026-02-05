import os

import praw

from autopack.research.gatherers.error_handler import error_handler
from autopack.research.gatherers.rate_limiter import RateLimiter


class RedditGatherer:
    """Gathers data from Reddit communities."""

    def __init__(self, client_id=None, client_secret=None, user_agent=None):
        # Get from arguments or environment variables
        self.client_id = client_id or os.getenv("REDDIT_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET")
        self.user_agent = user_agent or os.getenv("REDDIT_USER_AGENT", "AutopackBot/1.0")

        if not self.client_id or not self.client_secret:
            raise ValueError("Reddit credentials required (client_id and client_secret)")

        self.reddit = praw.Reddit(
            client_id=self.client_id, client_secret=self.client_secret, user_agent=self.user_agent
        )
        self.rate_limiter = RateLimiter()

    def fetch_subreddit_data(self, subreddit_name):
        """Fetches data for a given subreddit.

        Args:
            subreddit_name (str): The name of the subreddit.

        Returns:
            list: A list of subreddit posts.
        """
        return error_handler.handle_error(self._get_subreddit_posts, subreddit_name)

    def _get_subreddit_posts(self, subreddit_name):
        """Internal method to get subreddit posts with rate limiting.

        Args:
            subreddit_name (str): The name of the subreddit.

        Returns:
            list: A list of subreddit posts.
        """
        self.rate_limiter.wait()
        subreddit = self.reddit.subreddit(subreddit_name)
        return [post for post in subreddit.hot(limit=10)]

    def _get_access_token(self):
        """Get OAuth access token for API requests.

        Returns:
            str: The access token
        """
        import requests

        auth = (self.client_id, self.client_secret)
        data = {"grant_type": "client_credentials"}
        headers = {"User-Agent": "RedditGatherer/1.0"}

        response = requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=auth,
            data=data,
            headers=headers,
        )
        token_data = response.json()
        self.access_token = token_data["access_token"]
        return self.access_token

    def search_posts(self, query, limit=10):
        """Search for Reddit posts matching a query.

        Args:
            query (str): Search query
            limit (int): Maximum number of posts to return

        Returns:
            list: Posts matching the query
        """
        import requests

        if not hasattr(self, "access_token"):
            self._get_access_token()

        self.rate_limiter.wait()

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "RedditGatherer/1.0",
        }
        params = {"q": query, "sort": "relevance", "limit": limit}

        response = requests.get(
            "https://oauth.reddit.com/r/all/search",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        data = response.json()
        return [post["data"] for post in data["data"]["children"]]

    def get_subreddit_posts(self, subreddit_name, limit=10):
        """Get posts from a specific subreddit.

        Args:
            subreddit_name (str): Name of the subreddit
            limit (int): Maximum number of posts to return

        Returns:
            list: Posts from the subreddit
        """
        import requests

        if not hasattr(self, "access_token"):
            self._get_access_token()

        self.rate_limiter.wait()

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "RedditGatherer/1.0",
        }
        params = {"limit": limit}

        response = requests.get(
            f"https://oauth.reddit.com/r/{subreddit_name}/hot",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        data = response.json()
        return [post["data"] for post in data["data"]["children"]]

    def extract_findings(self, posts, topic):
        """Extract research findings from Reddit posts.

        Args:
            posts (list): List of Reddit post data
            topic (str): Research topic for context

        Returns:
            list: Extracted findings as Evidence objects
        """
        from autopack.research.models.enums import EvidenceType
        from autopack.research.models.evidence import Citation, Evidence

        findings = []
        for post in posts:
            if not post.get("title"):
                continue

            # Combine title and selftext for content
            title = post.get("title", "")
            selftext = post.get("selftext", "")
            content = f"{title}\n\n{selftext}".strip() if selftext else title

            citation = Citation(
                source="Reddit",
                title=title,
                publication=f"r/{post.get('subreddit', 'reddit')}",
                url=f"https://reddit.com{post.get('permalink', '')}",
                authors=[f"u/{post.get('author', 'unknown')}"],
            )

            evidence = Evidence(
                content=content,
                evidence_type=EvidenceType.ANECDOTAL,
                citation=citation,
                metadata={
                    "post_id": post.get("id"),
                    "subreddit": post.get("subreddit"),
                    "author": post.get("author"),
                    "score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                },
                tags=["reddit", post.get("subreddit", "community")],
            )
            findings.append(evidence)

        return findings

    def get_post_comments(self, post_id, subreddit_name, limit=10):
        """Get comments from a specific Reddit post.

        Args:
            post_id (str): ID of the post
            subreddit_name (str): Name of the subreddit
            limit (int): Maximum number of comments to return

        Returns:
            list: Comments on the post
        """
        import requests

        if not hasattr(self, "access_token"):
            self._get_access_token()

        self.rate_limiter.wait()

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "RedditGatherer/1.0",
        }
        params = {"limit": limit}

        response = requests.get(
            f"https://oauth.reddit.com/r/{subreddit_name}/comments/{post_id}",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        data = response.json()

        comments = []
        if len(data) > 1:
            comments_data = data[1].get("data", {}).get("children", [])
            comments = [c["data"] for c in comments_data if c["kind"] == "t1"]

        return comments


if __name__ == "__main__":
    # Example usage (guarded to avoid side effects on import / during pytest collection)
    gatherer = RedditGatherer(
        client_id="your_client_id",
        client_secret="your_client_secret",
        user_agent="your_user_agent",
    )
    posts = gatherer.fetch_subreddit_data("python") or []
    for post in posts:
        print(post.title)
