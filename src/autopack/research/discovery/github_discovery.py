"""
GitHub Discovery Module

This module defines the GitHubDiscovery class, which searches GitHub repositories and issues
to find relevant code and discussions for research purposes.
"""

from typing import List, Dict
from github import Github

class GitHubDiscovery:
    def __init__(self, access_token: str):
        """
        Initialize the GitHubDiscovery with an access token.

        :param access_token: GitHub access token for authentication.
        """
        self.github = Github(access_token)

    def search_repositories(self, query: str) -> List[Dict[str, str]]:
        """
        Search GitHub repositories based on a query.

        :param query: The search query.
        :return: A list of repositories matching the query.
        """
        repos = self.github.search_repositories(query)
        return [{"name": repo.full_name, "url": repo.html_url} for repo in repos]

    def search_issues(self, query: str) -> List[Dict[str, str]]:
        """
        Search GitHub issues based on a query.

        :param query: The search query.
        :return: A list of issues matching the query.
        """
        issues = self.github.search_issues(query)
        return [{"title": issue.title, "url": issue.html_url} for issue in issues]

    def search_code(self, query: str) -> List[Dict[str, str]]:
        """
        Search GitHub code based on a query.

        :param query: The search query.
        :return: A list of code results matching the query.
        """
        code_results = self.github.search_code(query)
        return [{"name": result.name, "path": result.path, "url": result.html_url} for result in code_results]


# Backward compatibility shims
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime

@dataclass
class GitHubRepository:
    """Compat shim for GitHubRepository."""
    name: str
    owner: str
    url: str = ""
    stars: int = 0
    description: str = ""
    
@dataclass
class GitHubIssue:
    """Compat shim for GitHubIssue."""
    title: str
    url: str
    number: int = 0
    state: str = "open"
    created_at: Optional[datetime] = None
