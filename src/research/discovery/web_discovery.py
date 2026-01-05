"""Web Discovery Module.

This module provides the WebDiscovery class for discovering relevant
information on the web through search engines and web scraping.
"""

import requests
from typing import Dict, List, Optional
from dataclasses import dataclass
from urllib.parse import urlparse
import time
import re


@dataclass
class WebResult:
    """Represents a web search result."""

    title: str
    url: str
    snippet: str
    source: str

    def to_dict(self) -> Dict:
        """Convert to dictionary representation."""
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
        }


class WebDiscovery:
    """Discovers relevant information on the web."""

    def __init__(self, search_engine: str = "duckduckgo"):
        """Initialize web discovery.

        Args:
            search_engine: Search engine to use (duckduckgo, google)
        """
        self.search_engine = search_engine
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.last_request_time = 0
        self.min_request_interval = 1  # Seconds between requests

    def search(
        self, query: str, max_results: int = 10, site: Optional[str] = None
    ) -> List[WebResult]:
        """Search the web for the given query.

        Args:
            query: Search query
            max_results: Maximum number of results to return
            site: Limit search to specific site (e.g., 'stackoverflow.com')

        Returns:
            List of web search results
        """
        if site:
            query = f"site:{site} {query}"

        if self.search_engine == "duckduckgo":
            return self._search_duckduckgo(query, max_results)
        elif self.search_engine == "google":
            return self._search_google(query, max_results)
        else:
            return []

    def _search_duckduckgo(self, query: str, max_results: int) -> List[WebResult]:
        """Search using DuckDuckGo.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of search results
        """
        self._rate_limit()

        # DuckDuckGo HTML search
        url = "https://html.duckduckgo.com/html/"

        data = {"q": query, "kl": "us-en"}

        try:
            response = requests.post(url, headers=self.headers, data=data, timeout=10)

            if response.status_code == 200:
                return self._parse_duckduckgo_html(response.text, max_results)
            else:
                return []

        except requests.RequestException:
            return []

    def _parse_duckduckgo_html(self, html: str, max_results: int) -> List[WebResult]:
        """Parse DuckDuckGo HTML results.

        Args:
            html: HTML content
            max_results: Maximum number of results to extract

        Returns:
            List of parsed results
        """
        results = []

        # Simple regex-based parsing (in production, use BeautifulSoup)
        # Extract result blocks
        result_pattern = r'<div class="result__body">.*?<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>.*?<a class="result__snippet".*?>(.*?)</a>'

        matches = re.finditer(result_pattern, html, re.DOTALL)

        for match in matches:
            if len(results) >= max_results:
                break

            url = match.group(1)
            title = re.sub(r"<.*?>", "", match.group(2))  # Remove HTML tags
            snippet = re.sub(r"<.*?>", "", match.group(3))  # Remove HTML tags

            # Extract domain from URL
            domain = urlparse(url).netloc

            result = WebResult(
                title=title.strip(), url=url.strip(), snippet=snippet.strip(), source=domain
            )
            results.append(result)

        return results

    def _search_google(self, query: str, max_results: int) -> List[WebResult]:
        """Search using Google Custom Search API.

        Note: Requires API key and search engine ID.
        This is a placeholder implementation.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of search results
        """
        # Placeholder - would require Google API credentials
        return []

    def search_documentation(self, query: str, technology: str) -> List[WebResult]:
        """Search for documentation on a specific technology.

        Args:
            query: Search query
            technology: Technology name (e.g., 'python', 'react')

        Returns:
            List of documentation results
        """
        # Map technologies to their documentation sites
        doc_sites = {
            "python": "docs.python.org",
            "javascript": "developer.mozilla.org",
            "react": "react.dev",
            "vue": "vuejs.org",
            "django": "docs.djangoproject.com",
            "flask": "flask.palletsprojects.com",
            "fastapi": "fastapi.tiangolo.com",
            "rust": "doc.rust-lang.org",
            "go": "go.dev",
            "typescript": "typescriptlang.org",
        }

        site = doc_sites.get(technology.lower())
        if site:
            return self.search(query, site=site, max_results=10)
        else:
            return self.search(f"{technology} {query} documentation", max_results=10)

    def search_stackoverflow(
        self, query: str, tags: Optional[List[str]] = None, max_results: int = 10
    ) -> List[WebResult]:
        """Search Stack Overflow for questions and answers.

        Args:
            query: Search query
            tags: List of tags to filter by
            max_results: Maximum number of results

        Returns:
            List of Stack Overflow results
        """
        search_query = query

        if tags:
            tag_string = " ".join([f"[{tag}]" for tag in tags])
            search_query = f"{query} {tag_string}"

        return self.search(search_query, site="stackoverflow.com", max_results=max_results)

    def search_blogs(self, query: str, max_results: int = 10) -> List[WebResult]:
        """Search for blog posts and articles.

        Args:
            query: Search query
            max_results: Maximum number of results

        Returns:
            List of blog post results
        """
        # Add blog-specific terms to improve results
        blog_query = f"{query} (blog OR tutorial OR guide OR article)"
        return self.search(blog_query, max_results=max_results)

    def extract_content(self, url: str) -> Optional[str]:
        """Extract main content from a web page.

        Args:
            url: URL to extract content from

        Returns:
            Extracted text content or None if failed
        """
        self._rate_limit()

        try:
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code == 200:
                # Simple content extraction (in production, use readability or newspaper3k)
                html = response.text

                # Remove script and style tags
                html = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL)
                html = re.sub(r"<style.*?</style>", "", html, flags=re.DOTALL)

                # Extract text from body
                body_match = re.search(r"<body.*?>(.*?)</body>", html, re.DOTALL)
                if body_match:
                    body = body_match.group(1)
                    # Remove all HTML tags
                    text = re.sub(r"<.*?>", " ", body)
                    # Clean up whitespace
                    text = re.sub(r"\s+", " ", text)
                    return text.strip()
                else:
                    return None
            else:
                return None

        except requests.RequestException:
            return None

    def check_url_accessibility(self, url: str) -> bool:
        """Check if a URL is accessible.

        Args:
            url: URL to check

        Returns:
            True if accessible, False otherwise
        """
        try:
            # Use GET instead of HEAD for maximum compatibility and to align with unit tests
            # that patch `requests.get`.
            response = requests.get(url, headers=self.headers, timeout=5, allow_redirects=True)
            return int(getattr(response, "status_code", 0) or 0) < 400

        except requests.RequestException:
            return False

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)

        self.last_request_time = time.time()
