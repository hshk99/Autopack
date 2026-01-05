"""GitHub Discovery Module.

This module provides the GitHubDiscovery class for discovering relevant
repositories, issues, and discussions on GitHub.
"""

import requests
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class GitHubRepository:
    """Represents a GitHub repository."""

    name: str
    full_name: str
    description: Optional[str]
    url: str
    stars: int
    forks: int
    language: Optional[str]
    topics: List[str]
    updated_at: str

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "full_name": self.full_name,
            "description": self.description,
            "url": self.url,
            "stars": self.stars,
            "forks": self.forks,
            "language": self.language,
            "topics": self.topics,
            "updated_at": self.updated_at,
        }


@dataclass
class GitHubIssue:
    """Represents a GitHub issue."""

    title: str
    number: int
    url: str
    state: str
    repository: str
    author: str
    created_at: str
    comments: int
    labels: List[str]
    body: Optional[str]

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "title": self.title,
            "number": self.number,
            "url": self.url,
            "state": self.state,
            "repository": self.repository,
            "author": self.author,
            "created_at": self.created_at,
            "comments": self.comments,
            "labels": self.labels,
            "body": self.body,
        }


class GitHubDiscovery:
    """Discovers relevant repositories and issues on GitHub."""

    def __init__(self, api_token: Optional[str] = None):
        """Initialize GitHub discovery.

        Args:
            api_token: Optional GitHub API token for authenticated requests
        """
        self.api_token = api_token
        self.base_url = "https://api.github.com"
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if api_token:
            self.headers["Authorization"] = f"token {api_token}"

        self.rate_limit_remaining = None
        self.rate_limit_reset = None

    def search_repositories(
        self, query: str, language: Optional[str] = None, min_stars: int = 0, max_results: int = 30
    ) -> List[GitHubRepository]:
        """Search for repositories matching the query.

        Args:
            query: Search query
            language: Filter by programming language
            min_stars: Minimum number of stars
            max_results: Maximum number of results to return

        Returns:
            List of matching repositories
        """
        search_query = query

        if language:
            search_query += f" language:{language}"

        if min_stars > 0:
            search_query += f" stars:>={min_stars}"

        params = {
            "q": search_query,
            "sort": "stars",
            "order": "desc",
            "per_page": min(max_results, 100),
        }

        try:
            response = requests.get(
                f"{self.base_url}/search/repositories",
                headers=self.headers,
                params=params,
                timeout=10,
            )

            self._update_rate_limit(response)

            if response.status_code == 200:
                data = response.json()
                repositories = []

                for item in data.get("items", [])[:max_results]:
                    repo = GitHubRepository(
                        name=item["name"],
                        full_name=item["full_name"],
                        description=item.get("description"),
                        url=item["html_url"],
                        stars=item["stargazers_count"],
                        forks=item["forks_count"],
                        language=item.get("language"),
                        topics=item.get("topics", []),
                        updated_at=item["updated_at"],
                    )
                    repositories.append(repo)

                return repositories
            else:
                return []

        except requests.RequestException:
            return []

    def search_issues(
        self,
        query: str,
        repository: Optional[str] = None,
        state: str = "open",
        max_results: int = 30,
    ) -> List[GitHubIssue]:
        """Search for issues matching the query.

        Args:
            query: Search query
            repository: Filter by repository (format: owner/repo)
            state: Issue state (open, closed, all)
            max_results: Maximum number of results to return

        Returns:
            List of matching issues
        """
        search_query = query

        if repository:
            search_query += f" repo:{repository}"

        search_query += f" is:issue state:{state}"

        params = {
            "q": search_query,
            "sort": "comments",
            "order": "desc",
            "per_page": min(max_results, 100),
        }

        try:
            response = requests.get(
                f"{self.base_url}/search/issues", headers=self.headers, params=params, timeout=10
            )

            self._update_rate_limit(response)

            if response.status_code == 200:
                data = response.json()
                issues = []

                for item in data.get("items", [])[:max_results]:
                    # Extract repository name from URL
                    repo_url = item["repository_url"]
                    repo_name = "/".join(repo_url.split("/")[-2:])

                    issue = GitHubIssue(
                        title=item["title"],
                        number=item["number"],
                        url=item["html_url"],
                        state=item["state"],
                        repository=repo_name,
                        author=item["user"]["login"],
                        created_at=item["created_at"],
                        comments=item["comments"],
                        labels=[label["name"] for label in item.get("labels", [])],
                        body=item.get("body"),
                    )
                    issues.append(issue)

                return issues
            else:
                return []

        except requests.RequestException:
            return []

    def get_repository_details(self, owner: str, repo: str) -> Optional[GitHubRepository]:
        """Get detailed information about a specific repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Repository details or None if not found
        """
        try:
            response = requests.get(
                f"{self.base_url}/repos/{owner}/{repo}", headers=self.headers, timeout=10
            )

            self._update_rate_limit(response)

            if response.status_code == 200:
                item = response.json()
                return GitHubRepository(
                    name=item["name"],
                    full_name=item["full_name"],
                    description=item.get("description"),
                    url=item["html_url"],
                    stars=item["stargazers_count"],
                    forks=item["forks_count"],
                    language=item.get("language"),
                    topics=item.get("topics", []),
                    updated_at=item["updated_at"],
                )
            else:
                return None

        except requests.RequestException:
            return None

    def get_trending_repositories(
        self, language: Optional[str] = None, since: str = "daily"
    ) -> List[GitHubRepository]:
        """Get trending repositories.

        Args:
            language: Filter by programming language
            since: Time period (daily, weekly, monthly)

        Returns:
            List of trending repositories
        """
        # GitHub doesn't have an official trending API, so we simulate it
        # by searching for recently updated popular repositories
        query = "stars:>100"

        if language:
            query += f" language:{language}"

        # Adjust date range based on 'since' parameter
        if since == "daily":
            query += " pushed:>" + self._get_date_string(1)
        elif since == "weekly":
            query += " pushed:>" + self._get_date_string(7)
        elif since == "monthly":
            query += " pushed:>" + self._get_date_string(30)

        return self.search_repositories(query, max_results=30)

    def _update_rate_limit(self, response: requests.Response):
        """Update rate limit information from response headers.

        Args:
            response: HTTP response object
        """
        if "X-RateLimit-Remaining" in response.headers:
            self.rate_limit_remaining = int(response.headers["X-RateLimit-Remaining"])

        if "X-RateLimit-Reset" in response.headers:
            self.rate_limit_reset = int(response.headers["X-RateLimit-Reset"])

    def _get_date_string(self, days_ago: int) -> str:
        """Get ISO date string for days ago.

        Args:
            days_ago: Number of days in the past

        Returns:
            ISO formatted date string
        """
        from datetime import datetime, timedelta

        date = datetime.now() - timedelta(days=days_ago)
        return date.strftime("%Y-%m-%d")

    def check_rate_limit(self) -> Dict:
        """Check current rate limit status.

        Returns:
            Dictionary with rate limit information
        """
        try:
            response = requests.get(f"{self.base_url}/rate_limit", headers=self.headers, timeout=10)

            if response.status_code == 200:
                return response.json()
            else:
                return {}

        except requests.RequestException:
            return {}
