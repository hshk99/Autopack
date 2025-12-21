"""GitHub Gatherer Module

This module provides functionality to gather data from GitHub repositories.
"""

import requests
from .rate_limiter import RateLimiter
from .error_handler import ErrorHandler

class GitHubGatherer:
    """Gathers data from GitHub repositories."""

    BASE_URL = "https://api.github.com"

    def __init__(self, api_token):
        self.api_token = api_token
        self.rate_limiter = RateLimiter()
        self.error_handler = ErrorHandler()

    def _get_headers(self):
        """Returns the headers for GitHub API requests."""
        return {
            "Authorization": f"token {self.api_token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def collect_repository_data(self, repo_name):
        """Collects data from a GitHub repository.

        Args:
            repo_name (str): The full name of the repository (e.g., 'owner/repo').

        Returns:
            dict: A dictionary containing repository data.
        """
        url = f"{self.BASE_URL}/repos/{repo_name}"
        return self.error_handler.handle_error(self._make_request, url)

    def _make_request(self, url):
        """Makes a GET request to the specified URL.

        Args:
            url (str): The URL to request.

        Returns:
            dict: The JSON response from the API.
        """
        self.rate_limiter.wait_for_rate_limit()
        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()
        return response.json()

    def collect_issues(self, repo_name):
        """Collects issues from a GitHub repository.

        Args:
            repo_name (str): The full name of the repository (e.g., 'owner/repo').

        Returns:
            list: A list of issues.
        """
        url = f"{self.BASE_URL}/repos/{repo_name}/issues"
        return self.error_handler.handle_error(self._make_request, url)

    def collect_pull_requests(self, repo_name):
        """Collects pull requests from a GitHub repository.

        Args:
            repo_name (str): The full name of the repository (e.g., 'owner/repo').

        Returns:
            list: A list of pull requests.
        """
        url = f"{self.BASE_URL}/repos/{repo_name}/pulls"
        return self.error_handler.handle_error(self._make_request, url)

    def collect_commits(self, repo_name):
        """Collects commits from a GitHub repository.

        Args:
            repo_name (str): The full name of the repository (e.g., 'owner/repo').

        Returns:
            list: A list of commits.
        """
        url = f"{self.BASE_URL}/repos/{repo_name}/commits"
        return self.error_handler.handle_error(self._make_request, url)
