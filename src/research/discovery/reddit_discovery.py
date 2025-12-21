import requests


class RedditDiscovery:
    """
    The RedditDiscovery class is responsible for discovering relevant posts and discussions on Reddit.
    """

    REDDIT_API_URL = "https://www.reddit.com"

    def __init__(self, user_agent):
        self.user_agent = user_agent

    def search_posts(self, query, subreddit=None):
        """
        Searches for posts on Reddit based on a query.

        :param query: The search query.
        :param subreddit: Optional subreddit to restrict the search.
        :return: A list of posts.
        """
        headers = {"User-Agent": self.user_agent}
        url = f"{self.REDDIT_API_URL}/search.json"
        params = {"q": query, "restrict_sr": subreddit is not None}
        if subreddit:
            params["subreddit"] = subreddit
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return response.json().get("data", {}).get("children", [])
        return []

    def get_post_details(self, post_id):
        """
        Retrieves details of a specific Reddit post.

        :param post_id: The ID of the post.
        :return: Post details.
        """
        headers = {"User-Agent": self.user_agent}
        response = requests.get(
            f"{self.REDDIT_API_URL}/comments/{post_id}.json",
            headers=headers
        )
        return response.json() if response.status_code == 200 else {}
