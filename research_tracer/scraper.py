"""Web scraping module with robots.txt compliance and rate limiting.

This module provides safe web scraping functionality that:
- Respects robots.txt directives
- Implements rate limiting to avoid overwhelming servers
- Handles common HTTP errors gracefully
- Validates URLs before scraping
"""

import time
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)


class WebScraper:
    """Safe web scraper with robots.txt compliance and rate limiting."""

    def __init__(self, user_agent: str = "AutopackTracerBot/1.0", rate_limit_seconds: float = 1.0):
        """Initialize the web scraper.

        Args:
            user_agent: User agent string to identify the bot
            rate_limit_seconds: Minimum seconds between requests to same domain
        """
        if requests is None:
            raise ImportError("requests library required. Install with: pip install requests")

        self.user_agent = user_agent
        self.rate_limit_seconds = rate_limit_seconds
        self.last_request_time: Dict[str, float] = {}
        self.robots_cache: Dict[str, RobotFileParser] = {}

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _check_robots_txt(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt.

        Args:
            url: URL to check

        Returns:
            True if allowed, False otherwise
        """
        domain = self._get_domain(url)

        if domain not in self.robots_cache:
            rp = RobotFileParser()
            robots_url = f"{domain}/robots.txt"
            try:
                rp.set_url(robots_url)
                rp.read()
                self.robots_cache[domain] = rp
                logger.info(f"Loaded robots.txt from {robots_url}")
            except Exception as e:
                logger.warning(f"Failed to load robots.txt from {robots_url}: {e}")
                # If robots.txt fails to load, assume allowed (permissive)
                rp = RobotFileParser()
                rp.parse([""])  # Empty robots.txt = allow all
                self.robots_cache[domain] = rp

        return self.robots_cache[domain].can_fetch(self.user_agent, url)

    def _apply_rate_limit(self, domain: str) -> None:
        """Apply rate limiting for domain.

        Args:
            domain: Domain to rate limit
        """
        if domain in self.last_request_time:
            elapsed = time.time() - self.last_request_time[domain]
            if elapsed < self.rate_limit_seconds:
                sleep_time = self.rate_limit_seconds - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s for {domain}")
                time.sleep(sleep_time)

        self.last_request_time[domain] = time.time()

    def fetch(self, url: str, timeout: int = 10) -> Optional[str]:
        """Fetch content from URL with safety checks.

        Args:
            url: URL to fetch
            timeout: Request timeout in seconds

        Returns:
            Page content as string, or None if fetch failed
        """
        # Validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                logger.error(f"Invalid URL: {url}")
                return None
        except Exception as e:
            logger.error(f"URL parsing failed for {url}: {e}")
            return None

        # Check robots.txt
        if not self._check_robots_txt(url):
            logger.warning(f"URL blocked by robots.txt: {url}")
            return None

        # Apply rate limiting
        domain = self._get_domain(url)
        self._apply_rate_limit(domain)

        # Fetch content
        try:
            headers = {"User-Agent": self.user_agent}
            response = requests.get(url, headers=headers, timeout=timeout)
            response.raise_for_status()
            logger.info(f"Successfully fetched {url} ({len(response.text)} bytes)")
            return response.text
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error fetching {url}: {e}")
            return None
        except requests.exceptions.Timeout:
            logger.error(f"Timeout fetching {url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return None

    def get_metadata(self, url: str) -> Dict[str, Any]:
        """Get metadata about URL without fetching full content.

        Args:
            url: URL to check

        Returns:
            Dictionary with metadata (allowed, domain, etc.)
        """
        domain = self._get_domain(url)
        allowed = self._check_robots_txt(url)

        return {
            "url": url,
            "domain": domain,
            "allowed_by_robots": allowed,
            "user_agent": self.user_agent,
            "rate_limit_seconds": self.rate_limit_seconds,
        }
