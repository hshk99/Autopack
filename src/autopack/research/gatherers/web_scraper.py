"""
Web scraper for Chunk 2B (web compilation).

Goals from requirements:
- robots.txt compliance (best-effort; conservative)
- respectful user-agent header
- per-domain rate limiting (1 req/sec)
- content-type filtering (HTML/text/markdown)

This module is structured to be unit-testable via request mocking.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass
from typing import Dict, Optional

import requests

from autopack.research.gatherers.content_extractor import ContentExtractor


@dataclass(frozen=True)
class FetchResult:
    url: str
    status_code: int
    content_type: str
    text: str


class WebScraper:
    DEFAULT_USER_AGENT = "AutopackResearchBot/1.0 (+https://github.com/hshk99/Autopack)"

    def __init__(
        self,
        *,
        user_agent: str | None = None,
        min_seconds_per_domain: float = 1.0,
        timeout_seconds: float = 15.0,
        allow_content_types: Optional[set[str]] = None,
    ):
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.min_seconds_per_domain = float(min_seconds_per_domain)
        self.timeout_seconds = float(timeout_seconds)
        self.allow_content_types = allow_content_types or {
            "text/html",
            "text/plain",
            "text/markdown",
        }

        self._last_request_ts_by_domain: Dict[str, float] = {}
        self._robots_cache: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self.extractor = ContentExtractor()

    def fetch_content(self, url: str) -> str:
        """
        Fetch a URL, validate it's allowed, and return extracted plain text.
        """
        fetch = self._fetch(url)
        return self.parse_content(fetch.text)

    def parse_content(self, html_or_text: str) -> str:
        """
        Convert HTML/text to clean plain text (no tags).
        """
        return self.extractor.extract_from_html(html_or_text)

    def _fetch(self, url: str) -> FetchResult:
        norm = self._validate_and_normalize_url(url)
        domain = urllib.parse.urlparse(norm).netloc.lower()

        self._enforce_rate_limit(domain)
        if not self._allowed_by_robots(norm):
            raise PermissionError(f"robots.txt disallows fetching: {norm}")

        resp = requests.get(
            norm,
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout_seconds,
        )
        # requests doesn't raise on non-2xx unless raise_for_status is called;
        # tests expect an Exception on failure
        if resp.status_code >= 400:
            raise Exception(f"HTTP {resp.status_code} for {norm}")

        content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        if content_type and content_type not in self.allow_content_types:
            raise ValueError(f"Unsupported content-type: {content_type}")

        return FetchResult(
            url=norm, status_code=resp.status_code, content_type=content_type, text=resp.text or ""
        )

    def _validate_and_normalize_url(self, url: str) -> str:
        if url is None:
            raise ValueError("url must not be None")
        if not isinstance(url, str):
            raise ValueError("url must be a string")
        url = url.strip()
        if not url:
            raise ValueError("url must not be empty")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("url must be http(s)")
        if not parsed.netloc:
            raise ValueError("url must include a host")
        return url

    def _enforce_rate_limit(self, domain: str) -> None:
        if self.min_seconds_per_domain <= 0:
            return
        now = time.time()
        last = self._last_request_ts_by_domain.get(domain)
        if last is not None:
            sleep_for = (last + self.min_seconds_per_domain) - now
            if sleep_for > 0:
                time.sleep(sleep_for)
        self._last_request_ts_by_domain[domain] = time.time()

    def _allowed_by_robots(self, url: str) -> bool:
        # Conservative best-effort: if robots cannot be fetched/parsed, allow
        # (real deployments may want the opposite).
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        rp = self._robots_cache.get(domain)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{parsed.scheme}://{domain}/robots.txt")
            try:
                rp.read()
            except Exception:
                self._robots_cache[domain] = rp
                return True
            self._robots_cache[domain] = rp
        try:
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            return True
