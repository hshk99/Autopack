"""
HuggingFace scraper for daily papers and trending models.

Uses HuggingFace API - 0 tokens.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

import aiohttp

from ..models import RawInnovation, SourceType
from .base import BaseScraper

logger = logging.getLogger(__name__)


class HuggingFaceScraper(BaseScraper):
    """
    Scrapes HuggingFace for daily papers and trending models.

    Uses HuggingFace Hub API (free, no auth required for public data).
    """

    # API endpoints
    DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"
    PAPERS_API_URL = "https://huggingface.co/api/papers"
    MODELS_API_URL = "https://huggingface.co/api/models"

    def __init__(self, include_models: bool = False):
        """
        Initialize HuggingFace scraper.

        Args:
            include_models: Also scrape trending models (default: False)
        """
        self.include_models = include_models

    @property
    def source_name(self) -> str:
        return "HuggingFace"

    async def scrape(self, since: datetime, keywords: List[str]) -> List[RawInnovation]:
        """
        Fetch daily papers and optionally trending models from HuggingFace.

        Args:
            since: Only fetch items newer than this date
            keywords: Keywords to filter (matched against title/summary)

        Returns:
            List of RawInnovation items
        """
        innovations = []

        async with aiohttp.ClientSession() as session:
            # Scrape daily papers
            try:
                papers = await self._scrape_papers(session, since, keywords)
                innovations.extend(papers)
            except Exception as e:
                logger.warning(f"[HuggingFaceScraper] Failed to scrape papers: {e}")

            # Optionally scrape trending models
            if self.include_models:
                try:
                    models = await self._scrape_models(session, since, keywords)
                    innovations.extend(models)
                except Exception as e:
                    logger.warning(f"[HuggingFaceScraper] Failed to scrape models: {e}")

        logger.info(f"[HuggingFaceScraper] Found {len(innovations)} items from HuggingFace")
        return innovations

    async def _scrape_papers(
        self,
        session: aiohttp.ClientSession,
        since: datetime,
        keywords: List[str],
    ) -> List[RawInnovation]:
        """Scrape daily papers feed."""
        async with session.get(self.DAILY_PAPERS_URL, timeout=30) as response:
            if response.status != 200:
                logger.warning(f"[HuggingFaceScraper] HTTP {response.status} for papers")
                return []

            data = await response.json()

        innovations = []

        for paper in data:
            try:
                innovation = self._parse_paper(paper, since, keywords)
                if innovation:
                    innovations.append(innovation)
            except Exception as e:
                logger.debug(f"[HuggingFaceScraper] Failed to parse paper: {e}")

        return innovations

    def _parse_paper(
        self,
        paper: dict,
        since: datetime,
        keywords: List[str],
    ) -> RawInnovation | None:
        """Parse a daily paper entry."""
        paper_data = paper.get("paper", {})

        paper_id = paper_data.get("id", "")
        title = paper_data.get("title", "")
        summary = paper_data.get("summary", "")
        published_at = paper.get("publishedAt", "")

        if not title:
            return None

        # Parse date
        pub_date = self._parse_date(published_at)
        if pub_date and pub_date < since:
            return None

        # Check keyword filter
        text = f"{title} {summary}".lower()
        if keywords and not any(kw.lower() in text for kw in keywords):
            return None

        # Get upvotes (likes)
        upvotes = paper.get("paper", {}).get("upvotes", 0)

        return RawInnovation(
            id=f"hf:paper:{paper_id}",
            title=title,
            source=SourceType.HUGGINGFACE,
            url=f"https://huggingface.co/papers/{paper_id}",
            published_date=pub_date or datetime.now(timezone.utc),
            body_text=summary[:2000],
            upvotes=upvotes,
            comments=0,
            tags=["paper"],
        )

    async def _scrape_models(
        self,
        session: aiohttp.ClientSession,
        since: datetime,
        keywords: List[str],
    ) -> List[RawInnovation]:
        """Scrape trending models."""
        params = {
            "sort": "trending",
            "limit": 20,
            "full": "true",
        }

        async with session.get(self.MODELS_API_URL, params=params, timeout=30) as response:
            if response.status != 200:
                logger.warning(f"[HuggingFaceScraper] HTTP {response.status} for models")
                return []

            data = await response.json()

        innovations = []

        for model in data:
            try:
                innovation = self._parse_model(model, since, keywords)
                if innovation:
                    innovations.append(innovation)
            except Exception as e:
                logger.debug(f"[HuggingFaceScraper] Failed to parse model: {e}")

        return innovations

    def _parse_model(
        self,
        model: dict,
        since: datetime,
        keywords: List[str],
    ) -> RawInnovation | None:
        """Parse a model entry."""
        model_id = model.get("id", "")
        # Model names are like "organization/model-name"
        title = model_id.split("/")[-1] if "/" in model_id else model_id

        # Get description from card data
        description = model.get("cardData", {}).get("description", "")
        if not description:
            description = f"Model: {model_id}"

        # Parse last modified date
        last_modified = model.get("lastModified", "")
        pub_date = self._parse_date(last_modified)

        if pub_date and pub_date < since:
            return None

        # Check keyword filter
        text = f"{title} {description}".lower()
        if keywords and not any(kw.lower() in text for kw in keywords):
            return None

        # Get likes as upvotes
        upvotes = model.get("likes", 0)
        downloads = model.get("downloads", 0)

        # Extract tags
        tags = model.get("tags", [])[:5]

        return RawInnovation(
            id=f"hf:model:{model_id}",
            title=f"Model: {title}",
            source=SourceType.HUGGINGFACE,
            url=f"https://huggingface.co/{model_id}",
            published_date=pub_date or datetime.now(timezone.utc),
            body_text=f"{description}\n\nDownloads: {downloads:,}",
            upvotes=upvotes,
            comments=0,
            tags=tags,
        )

    def _parse_date(self, date_str: str) -> datetime | None:
        """Parse HuggingFace date format."""
        if not date_str:
            return None

        # Try ISO format
        try:
            # Handle various ISO formats
            if "T" in date_str:
                if date_str.endswith("Z"):
                    date_str = date_str[:-1] + "+00:00"
                return datetime.fromisoformat(date_str)
        except ValueError:
            pass

        return None
