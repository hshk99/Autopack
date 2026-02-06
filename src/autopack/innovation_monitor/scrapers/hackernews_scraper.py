"""
Hacker News scraper for AI discussions.

Uses HN Algolia API - 0 tokens.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

import aiohttp

from ..models import RawInnovation, SourceType
from .base import BaseScraper

logger = logging.getLogger(__name__)


class HackerNewsScraper(BaseScraper):
    """
    Scrapes Hacker News for AI-related stories.

    Uses HN Algolia API (free, no auth required).
    """

    # Algolia API endpoint
    SEARCH_URL = "https://hn.algolia.com/api/v1/search"

    # Search queries for AI topics
    DEFAULT_QUERIES = [
        "RAG retrieval",
        "LLM agent",
        "vector database",
        "embedding",
        "language model",
    ]

    def __init__(self, queries: List[str] = None):
        """
        Initialize Hacker News scraper.

        Args:
            queries: Search queries for finding relevant stories
        """
        self.queries = queries or self.DEFAULT_QUERIES

    @property
    def source_name(self) -> str:
        return "Hacker News"

    async def scrape(self, since: datetime, keywords: List[str]) -> List[RawInnovation]:
        """
        Fetch recent AI-related stories from Hacker News.

        Args:
            since: Only fetch stories newer than this date
            keywords: Additional keywords to search for

        Returns:
            List of RawInnovation items
        """
        innovations = []
        seen_ids = set()

        # Combine default queries with provided keywords
        all_queries = list(set(self.queries + keywords))

        async with aiohttp.ClientSession() as session:
            for query in all_queries[:5]:  # Limit queries to avoid rate limiting
                try:
                    query_innovations = await self._search(session, query, since)
                    for innov in query_innovations:
                        if innov.id not in seen_ids:
                            seen_ids.add(innov.id)
                            innovations.append(innov)
                except Exception as e:
                    logger.warning(f"[HackerNewsScraper] Failed to search '{query}': {e}")

        logger.info(f"[HackerNewsScraper] Found {len(innovations)} stories from HN")
        return innovations

    async def _search(
        self,
        session: aiohttp.ClientSession,
        query: str,
        since: datetime,
    ) -> List[RawInnovation]:
        """Search HN via Algolia API."""
        # Calculate timestamp for 'since' filter
        since_timestamp = int(since.timestamp())

        params = {
            "query": query,
            "tags": "story",
            "numericFilters": f"created_at_i>{since_timestamp}",
            "hitsPerPage": 30,
        }

        async with session.get(self.SEARCH_URL, params=params, timeout=30) as response:
            if response.status != 200:
                logger.warning(f"[HackerNewsScraper] HTTP {response.status}")
                return []

            data = await response.json()

        return self._parse_hits(data.get("hits", []))

    def _parse_hits(self, hits: List[dict]) -> List[RawInnovation]:
        """Parse Algolia search results."""
        innovations = []

        for hit in hits:
            try:
                innovation = self._parse_hit(hit)
                if innovation:
                    innovations.append(innovation)
            except Exception as e:
                logger.debug(f"[HackerNewsScraper] Failed to parse hit: {e}")

        return innovations

    def _parse_hit(self, hit: dict) -> RawInnovation | None:
        """Parse a single search hit."""
        object_id = hit.get("objectID", "")
        title = hit.get("title", "")
        url = hit.get("url", "")
        points = hit.get("points", 0)
        num_comments = hit.get("num_comments", 0)
        created_at = hit.get("created_at_i", 0)

        if not title:
            return None

        # Use HN URL if no external URL
        if not url:
            url = f"https://news.ycombinator.com/item?id={object_id}"

        pub_date = datetime.fromtimestamp(created_at, tz=timezone.utc)

        # Extract story text (if available from comments or preview)
        story_text = hit.get("story_text", "") or ""

        return RawInnovation(
            id=f"hn:{object_id}",
            title=title,
            source=SourceType.HACKERNEWS,
            url=url,
            published_date=pub_date,
            body_text=story_text[:1000],
            upvotes=points or 0,
            comments=num_comments or 0,
            tags=["hackernews"],
        )
