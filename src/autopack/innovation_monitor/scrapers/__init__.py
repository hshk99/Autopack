"""
Source scrapers for AI innovations.

All scrapers use HTTP/RSS/APIs only - 0 tokens.
"""

from .arxiv_scraper import ArxivScraper
from .reddit_scraper import RedditScraper
from .hackernews_scraper import HackerNewsScraper
from .huggingface_scraper import HuggingFaceScraper
from .github_scraper import GitHubTrendingScraper
from .base import BaseScraper

__all__ = [
    "BaseScraper",
    "ArxivScraper",
    "RedditScraper",
    "HackerNewsScraper",
    "HuggingFaceScraper",
    "GitHubTrendingScraper",
]
