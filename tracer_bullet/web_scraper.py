"""Web scraping module with robots.txt compliance and rate limiting

Implements safe web scraping with:
- robots.txt parsing and compliance
- Configurable rate limits
- User-agent identification
- Error handling and retries
"""

import time
import logging
from typing import Optional, Dict, Any
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import requests
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ScraperConfig:
    """Configuration for web scraper"""
    user_agent: str = "AutopackTracerBot/1.0 (+https://github.com/autopack)"
    rate_limit_seconds: float = 1.0
    timeout_seconds: int = 10
    max_retries: int = 3
    retry_delay_seconds: float = 2.0


class WebScraper:
    """Safe web scraper with robots.txt compliance"""
    
    def __init__(self, config: Optional[ScraperConfig] = None):
        """Initialize scraper with configuration
        
        Args:
            config: Scraper configuration (uses defaults if None)
        """
        self.config = config or ScraperConfig()
        self.last_request_time: Dict[str, float] = {}
        self.robots_cache: Dict[str, RobotFileParser] = {}
        
    def _get_robots_parser(self, url: str) -> RobotFileParser:
        """Get robots.txt parser for domain
        
        Args:
            url: URL to check
            
        Returns:
            RobotFileParser instance
        """
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        
        if domain not in self.robots_cache:
            rp = RobotFileParser()
            robots_url = urljoin(domain, "/robots.txt")
            try:
                rp.set_url(robots_url)
                rp.read()
                logger.info(f"Loaded robots.txt from {robots_url}")
            except Exception as e:
                logger.warning(f"Failed to load robots.txt from {robots_url}: {e}")
                # Create permissive parser on failure
                rp = RobotFileParser()
            self.robots_cache[domain] = rp
            
        return self.robots_cache[domain]
    
    def _can_fetch(self, url: str) -> bool:
        """Check if URL can be fetched per robots.txt
        
        Args:
            url: URL to check
            
        Returns:
            True if allowed, False otherwise
        """
        try:
            rp = self._get_robots_parser(url)
            return rp.can_fetch(self.config.user_agent, url)
        except Exception as e:
            logger.error(f"Error checking robots.txt for {url}: {e}")
            return False
    
    def _enforce_rate_limit(self, domain: str):
        """Enforce rate limiting per domain
        
        Args:
            domain: Domain to rate limit
        """
        if domain in self.last_request_time:
            elapsed = time.time() - self.last_request_time[domain]
            if elapsed < self.config.rate_limit_seconds:
                sleep_time = self.config.rate_limit_seconds - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s for {domain}")
                time.sleep(sleep_time)
        
        self.last_request_time[domain] = time.time()
    
    def fetch(self, url: str) -> Optional[str]:
        """Fetch content from URL with safety checks
        
        Args:
            url: URL to fetch
            
        Returns:
            Page content as string, or None on failure
        """
        # Check robots.txt
        if not self._can_fetch(url):
            logger.warning(f"Blocked by robots.txt: {url}")
            return None
        
        # Extract domain for rate limiting
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        
        # Enforce rate limit
        self._enforce_rate_limit(domain)
        
        # Attempt fetch with retries
        headers = {"User-Agent": self.config.user_agent}
        
        for attempt in range(self.config.max_retries):
            try:
                logger.info(f"Fetching {url} (attempt {attempt + 1}/{self.config.max_retries})")
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=self.config.timeout_seconds
                )
                response.raise_for_status()
                logger.info(f"Successfully fetched {url} ({len(response.text)} bytes)")
                return response.text
                
            except requests.RequestException as e:
                logger.warning(f"Fetch attempt {attempt + 1} failed for {url}: {e}")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_delay_seconds)
                else:
                    logger.error(f"All fetch attempts failed for {url}")
                    return None
        
        return None
