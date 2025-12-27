import praw
from src.autopack.research.gatherers.rate_limiter import RateLimiter
from src.autopack.research.gatherers.error_handler import error_handler

class RedditGatherer:
    """Gathers data from Reddit communities."""

    def __init__(self, client_id, client_secret, user_agent):
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
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
