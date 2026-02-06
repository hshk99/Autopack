"""
Reddit scraper for AI communities.

Uses Reddit's public JSON API - 0 tokens.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

import aiohttp

from ..models import RawInnovation, SourceType
from .base import BaseScraper

logger = logging.getLogger(__name__)


class RedditScraper(BaseScraper):
    """
    Scrapes Reddit AI communities.

    Uses Reddit's public JSON API (no auth required for read-only).
    """

    # AI-related subreddits
    DEFAULT_SUBREDDITS = [
        "MachineLearning",
        "LocalLLaMA",
        "LangChain",
        "artificial",
        "ChatGPT",
        "ClaudeAI",
    ]

    def __init__(self, subreddits: List[str] = None):
        """
        Initialize Reddit scraper.

        Args:
            subreddits: Subreddits to scrape (default: AI-related subs)
        """
        self.subreddits = subreddits or self.DEFAULT_SUBREDDITS
        self.user_agent = "AutopackInnovationMonitor/1.0"

    @property
    def source_name(self) -> str:
        return "Reddit"

    async def scrape(self, since: datetime, keywords: List[str]) -> List[RawInnovation]:
        """
        Fetch recent posts from AI subreddits.

        Args:
            since: Only fetch posts newer than this date
            keywords: Keywords to filter (matched against title/body)

        Returns:
            List of RawInnovation items
        """
        innovations = []

        async with aiohttp.ClientSession() as session:
            for subreddit in self.subreddits:
                try:
                    sub_innovations = await self._scrape_subreddit(
                        session, subreddit, since, keywords
                    )
                    innovations.extend(sub_innovations)
                except Exception as e:
                    logger.warning(f"[RedditScraper] Failed to scrape r/{subreddit}: {e}")

        logger.info(f"[RedditScraper] Found {len(innovations)} posts from Reddit")
        return innovations

    async def _scrape_subreddit(
        self,
        session: aiohttp.ClientSession,
        subreddit: str,
        since: datetime,
        keywords: List[str],
    ) -> List[RawInnovation]:
        """Scrape a single subreddit."""
        url = f"https://www.reddit.com/r/{subreddit}/new.json"
        params = {"limit": 50}
        headers = {"User-Agent": self.user_agent}

        async with session.get(url, params=params, headers=headers, timeout=30) as response:
            if response.status == 429:
                logger.warning(f"[RedditScraper] Rate limited on r/{subreddit}")
                return []

            if response.status != 200:
                logger.warning(f"[RedditScraper] HTTP {response.status} for r/{subreddit}")
                return []

            data = await response.json()

        return self._parse_posts(data, subreddit, since, keywords)

    def _parse_posts(
        self,
        data: dict,
        subreddit: str,
        since: datetime,
        keywords: List[str],
    ) -> List[RawInnovation]:
        """Parse Reddit JSON response."""
        innovations = []

        posts = data.get("data", {}).get("children", [])

        for post in posts:
            try:
                post_data = post.get("data", {})
                innovation = self._parse_post(post_data, subreddit, since, keywords)
                if innovation:
                    innovations.append(innovation)
            except Exception as e:
                logger.debug(f"[RedditScraper] Failed to parse post: {e}")

        return innovations

    def _parse_post(
        self,
        post: dict,
        subreddit: str,
        since: datetime,
        keywords: List[str],
    ) -> RawInnovation | None:
        """Parse a single Reddit post."""
        # Parse timestamp
        created_utc = post.get("created_utc", 0)
        pub_date = datetime.fromtimestamp(created_utc, tz=timezone.utc)

        if pub_date < since:
            return None

        title = post.get("title", "")
        selftext = post.get("selftext", "")
        permalink = post.get("permalink", "")
        post_id = post.get("id", "")
        upvotes = post.get("ups", 0)
        num_comments = post.get("num_comments", 0)

        if not title:
            return None

        # Skip removed/deleted posts
        if selftext in ("[removed]", "[deleted]"):
            selftext = ""

        # Check keyword filter
        text = f"{title} {selftext}".lower()
        if keywords and not any(kw.lower() in text for kw in keywords):
            return None

        # Skip low-quality posts (very short titles, low engagement)
        if len(title) < 10:
            return None

        return RawInnovation(
            id=f"reddit:{post_id}",
            title=title,
            source=SourceType.REDDIT,
            url=f"https://reddit.com{permalink}",
            published_date=pub_date,
            body_text=selftext[:2000],  # Truncate long posts
            upvotes=upvotes,
            comments=num_comments,
            tags=[subreddit],
        )
