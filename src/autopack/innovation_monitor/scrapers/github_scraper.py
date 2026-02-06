"""
GitHub scraper for trending AI repositories.

Uses GitHub API and trending page - 0 tokens.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List

import aiohttp

from ..models import RawInnovation, SourceType
from .base import BaseScraper

logger = logging.getLogger(__name__)


class GitHubTrendingScraper(BaseScraper):
    """
    Scrapes GitHub for trending AI/ML repositories.

    Uses GitHub's public API (limited rate without auth, but sufficient).
    """

    # GitHub search API
    SEARCH_API = "https://api.github.com/search/repositories"

    # Topics to search for
    DEFAULT_TOPICS = [
        "rag",
        "retrieval-augmented-generation",
        "llm-agent",
        "vector-database",
        "embedding",
        "langchain",
        "llama",
    ]

    def __init__(self, topics: List[str] = None):
        """
        Initialize GitHub scraper.

        Args:
            topics: GitHub topics to search for
        """
        self.topics = topics or self.DEFAULT_TOPICS

    @property
    def source_name(self) -> str:
        return "GitHub"

    async def scrape(self, since: datetime, keywords: List[str]) -> List[RawInnovation]:
        """
        Fetch trending repositories related to AI/ML.

        Args:
            since: Only fetch repos created/updated after this date
            keywords: Additional keywords to search for

        Returns:
            List of RawInnovation items
        """
        innovations = []
        seen_ids = set()

        # Combine topics with keywords
        search_terms = list(set(self.topics + keywords))

        async with aiohttp.ClientSession() as session:
            for term in search_terms[:5]:  # Limit to avoid rate limiting
                try:
                    term_innovations = await self._search_repos(session, term, since)
                    for innov in term_innovations:
                        if innov.id not in seen_ids:
                            seen_ids.add(innov.id)
                            innovations.append(innov)
                except Exception as e:
                    logger.warning(f"[GitHubScraper] Failed to search '{term}': {e}")

        logger.info(f"[GitHubScraper] Found {len(innovations)} repos from GitHub")
        return innovations

    async def _search_repos(
        self,
        session: aiohttp.ClientSession,
        term: str,
        since: datetime,
    ) -> List[RawInnovation]:
        """Search GitHub repositories."""
        # Build query with date filter
        date_str = since.strftime("%Y-%m-%d")
        query = f"{term} pushed:>{date_str}"

        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": 20,
        }

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AutopackInnovationMonitor/1.0",
        }

        async with session.get(
            self.SEARCH_API, params=params, headers=headers, timeout=30
        ) as response:
            if response.status == 403:
                logger.warning("[GitHubScraper] Rate limited")
                return []

            if response.status != 200:
                logger.warning(f"[GitHubScraper] HTTP {response.status}")
                return []

            data = await response.json()

        return self._parse_repos(data.get("items", []), since)

    def _parse_repos(
        self,
        repos: List[dict],
        since: datetime,
    ) -> List[RawInnovation]:
        """Parse GitHub search results."""
        innovations = []

        for repo in repos:
            try:
                innovation = self._parse_repo(repo, since)
                if innovation:
                    innovations.append(innovation)
            except Exception as e:
                logger.debug(f"[GitHubScraper] Failed to parse repo: {e}")

        return innovations

    def _parse_repo(
        self,
        repo: dict,
        since: datetime,
    ) -> RawInnovation | None:
        """Parse a single repository."""
        full_name = repo.get("full_name", "")
        name = repo.get("name", "")
        description = repo.get("description", "") or ""
        html_url = repo.get("html_url", "")
        stars = repo.get("stargazers_count", 0)
        forks = repo.get("forks_count", 0)
        pushed_at = repo.get("pushed_at", "")
        topics = repo.get("topics", [])

        if not full_name or not html_url:
            return None

        # Parse date
        pub_date = self._parse_date(pushed_at)
        if pub_date and pub_date < since:
            return None

        # Build body text
        body_text = description
        if topics:
            body_text += f"\n\nTopics: {', '.join(topics[:10])}"
        body_text += f"\n\nStars: {stars:,} | Forks: {forks:,}"

        return RawInnovation(
            id=f"github:{full_name}",
            title=f"{name}: {description[:100]}" if description else name,
            source=SourceType.GITHUB,
            url=html_url,
            published_date=pub_date or datetime.now(timezone.utc),
            body_text=body_text,
            upvotes=stars,
            comments=forks,  # Use forks as a proxy for "engagement"
            tags=topics[:5],
        )

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parse GitHub date format."""
        if not date_str:
            return None

        try:
            # GitHub uses ISO 8601 format
            if date_str.endswith("Z"):
                date_str = date_str[:-1] + "+00:00"
            return datetime.fromisoformat(date_str)
        except ValueError:
            return None
