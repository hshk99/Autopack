"""
ArXiv scraper for AI/ML papers.

Uses ArXiv RSS feed and API - 0 tokens.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import List
from xml.etree import ElementTree

import aiohttp

from ..models import RawInnovation, SourceType
from .base import BaseScraper

logger = logging.getLogger(__name__)


class ArxivScraper(BaseScraper):
    """
    Scrapes ArXiv for AI/ML papers.

    Uses RSS feed for recent papers - completely free, no auth required.
    """

    # ArXiv RSS feeds for AI-related categories
    RSS_FEEDS = {
        "cs.AI": "http://export.arxiv.org/rss/cs.AI",
        "cs.CL": "http://export.arxiv.org/rss/cs.CL",  # Computation and Language
        "cs.LG": "http://export.arxiv.org/rss/cs.LG",  # Machine Learning
        "cs.IR": "http://export.arxiv.org/rss/cs.IR",  # Information Retrieval
    }

    # API endpoint for detailed queries
    API_URL = "http://export.arxiv.org/api/query"

    def __init__(self, categories: List[str] = None):
        """
        Initialize ArXiv scraper.

        Args:
            categories: ArXiv categories to scrape (default: cs.AI, cs.CL, cs.LG)
        """
        self.categories = categories or ["cs.AI", "cs.CL", "cs.LG"]

    @property
    def source_name(self) -> str:
        return "ArXiv"

    async def scrape(self, since: datetime, keywords: List[str]) -> List[RawInnovation]:
        """
        Fetch recent papers from ArXiv RSS feeds.

        Args:
            since: Only fetch papers newer than this date
            keywords: Keywords to filter (matched against title/abstract)

        Returns:
            List of RawInnovation items
        """
        innovations = []

        async with aiohttp.ClientSession() as session:
            for category in self.categories:
                if category not in self.RSS_FEEDS:
                    continue

                try:
                    feed_innovations = await self._scrape_feed(session, category, since, keywords)
                    innovations.extend(feed_innovations)
                except Exception as e:
                    logger.warning(f"[ArxivScraper] Failed to scrape {category}: {e}")

        logger.info(f"[ArxivScraper] Found {len(innovations)} papers from ArXiv")
        return innovations

    async def _scrape_feed(
        self,
        session: aiohttp.ClientSession,
        category: str,
        since: datetime,
        keywords: List[str],
    ) -> List[RawInnovation]:
        """Scrape a single RSS feed."""
        url = self.RSS_FEEDS[category]

        async with session.get(url, timeout=30) as response:
            if response.status != 200:
                logger.warning(f"[ArxivScraper] HTTP {response.status} for {url}")
                return []

            content = await response.text()

        return self._parse_rss(content, category, since, keywords)

    def _parse_rss(
        self,
        content: str,
        category: str,
        since: datetime,
        keywords: List[str],
    ) -> List[RawInnovation]:
        """Parse ArXiv RSS feed XML."""
        innovations = []

        try:
            # ArXiv RSS uses RDF format
            root = ElementTree.fromstring(content)

            # Handle namespaces
            namespaces = {
                "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
                "dc": "http://purl.org/dc/elements/1.1/",
                "": "http://purl.org/rss/1.0/",
            }

            # Find all items
            for item in root.findall(".//item", namespaces) or root.findall(
                ".//{http://purl.org/rss/1.0/}item"
            ):
                try:
                    innovation = self._parse_item(item, category, since, keywords)
                    if innovation:
                        innovations.append(innovation)
                except Exception as e:
                    logger.debug(f"[ArxivScraper] Failed to parse item: {e}")

        except ElementTree.ParseError as e:
            logger.warning(f"[ArxivScraper] Failed to parse RSS: {e}")

        return innovations

    def _parse_item(
        self,
        item: ElementTree.Element,
        category: str,
        since: datetime,
        keywords: List[str],
    ) -> RawInnovation | None:
        """Parse a single RSS item."""

        # Extract fields with namespace handling
        def get_text(tag: str) -> str:
            elem = item.find(tag) or item.find(f"{{http://purl.org/rss/1.0/}}{tag}")
            if elem is None:
                # Try dc namespace
                elem = item.find(f"{{http://purl.org/dc/elements/1.1/}}{tag}")
            return elem.text.strip() if elem is not None and elem.text else ""

        title = get_text("title")
        link = get_text("link")
        description = get_text("description")
        date_str = get_text("date") or get_text("pubDate")

        if not title or not link:
            return None

        # Parse date
        pub_date = self._parse_date(date_str)
        if pub_date and pub_date < since:
            return None

        # Extract ArXiv ID from URL
        arxiv_id = self._extract_arxiv_id(link)

        # Check keyword filter
        text = f"{title} {description}".lower()
        if keywords and not any(kw.lower() in text for kw in keywords):
            return None

        # Clean description (remove HTML)
        clean_description = re.sub(r"<[^>]+>", "", description)

        return RawInnovation(
            id=f"arxiv:{arxiv_id}",
            title=title,
            source=SourceType.ARXIV,
            url=link,
            published_date=pub_date or datetime.now(timezone.utc),
            body_text=clean_description,
            upvotes=0,  # ArXiv doesn't have upvotes
            comments=0,
            tags=[category],
        )

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parse ArXiv date format."""
        if not date_str:
            return None

        # Try common formats
        formats = [
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y %H:%M:%S %z",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue

        return None

    def _extract_arxiv_id(self, url: str) -> str:
        """Extract ArXiv ID from URL."""
        # URLs like: http://arxiv.org/abs/2401.12345
        match = re.search(r"(\d{4}\.\d{4,5})", url)
        if match:
            return match.group(1)

        # Fallback: use URL hash
        import hashlib

        return hashlib.md5(url.encode()).hexdigest()[:12]
