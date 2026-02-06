"""
Base scraper class for AI innovation sources.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

from ..models import RawInnovation

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """
    Base class for all innovation scrapers.

    All scrapers should use HTTP/RSS/APIs only - 0 tokens.
    """

    @abstractmethod
    async def scrape(self, since: datetime, keywords: List[str]) -> List[RawInnovation]:
        """
        Scrape innovations from the source.

        Args:
            since: Only fetch items newer than this date
            keywords: Keywords to filter by (if supported by source)

        Returns:
            List of raw innovations
        """
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Human-readable name of this source."""
        pass
