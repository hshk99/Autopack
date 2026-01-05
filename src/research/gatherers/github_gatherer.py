"""GitHub Gatherer Module

This module provides functionality to gather data from GitHub repositories.
"""

import requests
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from .rate_limiter import RateLimiter
from .error_handler import ErrorHandler

logger = logging.getLogger(__name__)


class GitHubGatherer:
    """Gathers data from GitHub repositories with rate limiting and error handling."""

    BASE_URL = "https://api.github.com"

    def __init__(
        self, token: Optional[str] = None, max_requests_per_hour: int = 5000, max_retries: int = 3
    ):
        """Initialize GitHub gatherer.

        Args:
            token: GitHub API token for authentication
            max_requests_per_hour: Maximum API requests per hour
            max_retries: Maximum number of retry attempts for failed requests
        """
        self.token = token
        self.rate_limiter = RateLimiter(max_requests_per_hour)
        self.error_handler = ErrorHandler(max_retries)
        self.session = requests.Session()

        if token:
            self.session.headers.update({"Authorization": f"token {token}"})

        logger.info("GitHubGatherer initialized")

    def _make_request(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make a rate-limited API request with error handling.

        Args:
            endpoint: API endpoint path
            params: Optional query parameters

        Returns:
            JSON response as dictionary
        """
        self.rate_limiter.acquire()

        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"

        def _request():
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()

        return self.error_handler.execute_with_retry(_request)

    def gather_repository_info(self, owner: str, repo: str) -> Dict[str, Any]:
        """Gather information about a GitHub repository.

        Args:
            owner: Repository owner username
            repo: Repository name

        Returns:
            Dictionary containing repository information with citation
        """
        logger.info(f"Gathering info for repository {owner}/{repo}")

        try:
            data = self._make_request(f"repos/{owner}/{repo}")

            finding = {
                "type": "repository_info",
                "source": "github",
                "repository": f"{owner}/{repo}",
                "url": data.get("html_url"),
                "gathered_at": datetime.utcnow().isoformat(),
                "data": {
                    "name": data.get("name"),
                    "full_name": data.get("full_name"),
                    "description": data.get("description"),
                    "stars": data.get("stargazers_count"),
                    "forks": data.get("forks_count"),
                    "open_issues": data.get("open_issues_count"),
                    "language": data.get("language"),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                    "topics": data.get("topics", []),
                    "license": data.get("license", {}).get("name") if data.get("license") else None,
                },
                "citation": {
                    "source_type": "github_repository",
                    "repository": f"{owner}/{repo}",
                    "url": data.get("html_url"),
                    "accessed_at": datetime.utcnow().isoformat(),
                },
            }

            logger.info(f"Successfully gathered info for {owner}/{repo}")
            return finding

        except Exception as e:
            self.error_handler.handle_error(e, f"gathering repository info for {owner}/{repo}")
            raise

    def gather_readme(self, owner: str, repo: str) -> Dict[str, Any]:
        """Gather README content from a repository.

        Args:
            owner: Repository owner username
            repo: Repository name

        Returns:
            Dictionary containing README content with citation
        """
        logger.info(f"Gathering README for {owner}/{repo}")

        try:
            data = self._make_request(f"repos/{owner}/{repo}/readme")

            # Decode base64 content
            import base64

            content = base64.b64decode(data.get("content", "")).decode("utf-8")

            finding = {
                "type": "readme",
                "source": "github",
                "repository": f"{owner}/{repo}",
                "url": data.get("html_url"),
                "gathered_at": datetime.utcnow().isoformat(),
                "data": {
                    "content": content,
                    "name": data.get("name"),
                    "path": data.get("path"),
                    "size": data.get("size"),
                },
                "citation": {
                    "source_type": "github_readme",
                    "repository": f"{owner}/{repo}",
                    "file": data.get("path"),
                    "url": data.get("html_url"),
                    "accessed_at": datetime.utcnow().isoformat(),
                },
            }

            logger.info(f"Successfully gathered README for {owner}/{repo}")
            return finding

        except Exception as e:
            self.error_handler.handle_error(e, f"gathering README for {owner}/{repo}")
            raise

    def gather_issues(
        self, owner: str, repo: str, state: str = "open", max_issues: int = 100
    ) -> List[Dict[str, Any]]:
        """Gather issues from a repository.

        Args:
            owner: Repository owner username
            repo: Repository name
            state: Issue state (open, closed, all)
            max_issues: Maximum number of issues to gather

        Returns:
            List of dictionaries containing issue information with citations
        """
        logger.info(f"Gathering issues for {owner}/{repo} (state={state}, max={max_issues})")

        findings = []
        page = 1
        per_page = min(100, max_issues)

        try:
            while len(findings) < max_issues:
                params = {"state": state, "page": page, "per_page": per_page}

                issues = self._make_request(f"repos/{owner}/{repo}/issues", params)

                if not issues:
                    break

                for issue in issues:
                    if len(findings) >= max_issues:
                        break

                    # Skip pull requests (they appear in issues endpoint)
                    if "pull_request" in issue:
                        continue

                    finding = {
                        "type": "issue",
                        "source": "github",
                        "repository": f"{owner}/{repo}",
                        "url": issue.get("html_url"),
                        "gathered_at": datetime.utcnow().isoformat(),
                        "data": {
                            "number": issue.get("number"),
                            "title": issue.get("title"),
                            "body": issue.get("body"),
                            "state": issue.get("state"),
                            "created_at": issue.get("created_at"),
                            "updated_at": issue.get("updated_at"),
                            "closed_at": issue.get("closed_at"),
                            "labels": [label.get("name") for label in issue.get("labels", [])],
                            "comments": issue.get("comments"),
                            "author": issue.get("user", {}).get("login"),
                        },
                        "citation": {
                            "source_type": "github_issue",
                            "repository": f"{owner}/{repo}",
                            "issue_number": issue.get("number"),
                            "url": issue.get("html_url"),
                            "accessed_at": datetime.utcnow().isoformat(),
                        },
                    }

                    findings.append(finding)

                page += 1

            logger.info(f"Successfully gathered {len(findings)} issues for {owner}/{repo}")
            return findings

        except Exception as e:
            self.error_handler.handle_error(e, f"gathering issues for {owner}/{repo}")
            raise

    def gather_pull_requests(
        self, owner: str, repo: str, state: str = "open", max_prs: int = 100
    ) -> List[Dict[str, Any]]:
        """Gather pull requests from a repository.

        Args:
            owner: Repository owner username
            repo: Repository name
            state: PR state (open, closed, all)
            max_prs: Maximum number of PRs to gather

        Returns:
            List of dictionaries containing PR information with citations
        """
        logger.info(f"Gathering pull requests for {owner}/{repo} (state={state}, max={max_prs})")

        findings = []
        page = 1
        per_page = min(100, max_prs)

        try:
            while len(findings) < max_prs:
                params = {"state": state, "page": page, "per_page": per_page}

                prs = self._make_request(f"repos/{owner}/{repo}/pulls", params)

                if not prs:
                    break

                for pr in prs:
                    if len(findings) >= max_prs:
                        break

                    finding = {
                        "type": "pull_request",
                        "source": "github",
                        "repository": f"{owner}/{repo}",
                        "url": pr.get("html_url"),
                        "gathered_at": datetime.utcnow().isoformat(),
                        "data": {
                            "number": pr.get("number"),
                            "title": pr.get("title"),
                            "body": pr.get("body"),
                            "state": pr.get("state"),
                            "created_at": pr.get("created_at"),
                            "updated_at": pr.get("updated_at"),
                            "closed_at": pr.get("closed_at"),
                            "merged_at": pr.get("merged_at"),
                            "labels": [label.get("name") for label in pr.get("labels", [])],
                            "author": pr.get("user", {}).get("login"),
                            "base_branch": pr.get("base", {}).get("ref"),
                            "head_branch": pr.get("head", {}).get("ref"),
                        },
                        "citation": {
                            "source_type": "github_pull_request",
                            "repository": f"{owner}/{repo}",
                            "pr_number": pr.get("number"),
                            "url": pr.get("html_url"),
                            "accessed_at": datetime.utcnow().isoformat(),
                        },
                    }

                    findings.append(finding)

                page += 1

            logger.info(f"Successfully gathered {len(findings)} pull requests for {owner}/{repo}")
            return findings

        except Exception as e:
            self.error_handler.handle_error(e, f"gathering pull requests for {owner}/{repo}")
            raise
