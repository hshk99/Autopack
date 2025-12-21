import requests


class GitHubDiscovery:
    """
    The GitHubDiscovery class is responsible for discovering relevant repositories and information on GitHub.
    """

    GITHUB_API_URL = "https://api.github.com"

    def __init__(self, token):
        self.token = token

    def search_repositories(self, query):
        """
        Searches for repositories on GitHub based on a query.

        :param query: The search query.
        :return: A list of repositories.
        """
        headers = {"Authorization": f"token {self.token}"}
        response = requests.get(
            f"{self.GITHUB_API_URL}/search/repositories",
            headers=headers,
            params={"q": query}
        )
        if response.status_code == 200:
            return response.json().get("items", [])
        return []

    def get_repository_details(self, owner, repo):
        """
        Retrieves details of a specific repository.

        :param owner: The owner of the repository.
        :param repo: The name of the repository.
        :return: Repository details.
        """
        headers = {"Authorization": f"token {self.token}"}
        response = requests.get(
            f"{self.GITHUB_API_URL}/repos/{owner}/{repo}",
            headers=headers
        )
        return response.json() if response.status_code == 200 else {}
