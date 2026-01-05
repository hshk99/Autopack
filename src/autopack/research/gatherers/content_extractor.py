"""
Content extractor for Chunk 2B (web compilation).

This module is intentionally lightweight and testable: it focuses on turning
raw HTML/text into clean text, extracting links, and preserving code blocks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ExtractedContent:
    text: str
    links: List[str]
    code_blocks: List[str]


_RE_WS = re.compile(r"\s+")
_RE_URL = re.compile(r"https?://[^\s)\"'>]+")


class ContentExtractor:
    """
    Extract and sanitize content.

    Design goals:
    - deterministic output
    - no external network calls
    - works even if readability-lxml is missing (falls back to BeautifulSoup)
    """

    def extract_from_html(self, html: str) -> str:
        if html is None:
            raise ValueError("html must not be None")
        if not isinstance(html, str):
            raise ValueError("html must be a string")
        # Basic well-formedness check for the common "<html> ... </html>" wrapper.
        # This is intentionally conservative and only triggers when an <html> tag is present.
        lower = html.lower()
        if "<html" in lower and "</html>" not in lower:
            raise ValueError("invalid html: missing </html> closing tag")
        if html and "<" not in html:
            # treat as plain text; keep behavior stable for tests
            return self._normalize_text(html)

        soup = self._bs4_soup(html)

        # Preserve code blocks first (before stripping everything)
        [c.get_text("\n") for c in soup.find_all("code")]
        # Remove scripts/styles/navigation-ish
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text("\n")
        text = self._normalize_text(text)
        return text

    def extract_from_text(self, text: str) -> str:
        if text is None:
            raise ValueError("text must not be None")
        if not isinstance(text, str):
            raise ValueError("text must be a string")
        return self._normalize_text(text)

    def extract_from_json(self, json_content: str) -> str:
        if json_content is None:
            raise ValueError("json_content must not be None")
        if not isinstance(json_content, str):
            raise ValueError("json_content must be a string")
        try:
            obj = json.loads(json_content)
        except json.JSONDecodeError as e:
            raise ValueError("invalid json") from e
        if isinstance(obj, dict):
            if "content" in obj and isinstance(obj["content"], str):
                return self._normalize_text(obj["content"])
            # best-effort: return first string value
            for v in obj.values():
                if isinstance(v, str):
                    return self._normalize_text(v)
        return ""

    def extract_links(self, html: str) -> List[str]:
        if html is None:
            raise ValueError("html must not be None")
        if not isinstance(html, str):
            raise ValueError("html must be a string")
        # fast path for already-plain text
        if "<" not in html:
            return sorted(set(_RE_URL.findall(html)))

        soup = self._bs4_soup(html)
        links: List[str] = []
        for a in soup.find_all("a"):
            href = (a.get("href") or "").strip()
            if href.startswith("http://") or href.startswith("https://"):
                links.append(href)
        return sorted(set(links))

    def extract_code_blocks(self, html: str) -> List[str]:
        if html is None:
            raise ValueError("html must not be None")
        if not isinstance(html, str):
            raise ValueError("html must be a string")
        if "<" not in html:
            return []
        soup = self._bs4_soup(html)
        blocks = [c.get_text("\n").strip() for c in soup.find_all("code")]
        return [b for b in blocks if b]

    def extract(self, html: str, *, source_url: Optional[str] = None) -> ExtractedContent:
        # source_url is currently informational; kept for future citation work
        _ = source_url
        text = self.extract_from_html(html)
        return ExtractedContent(
            text=text,
            links=self.extract_links(html),
            code_blocks=self.extract_code_blocks(html),
        )

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # keep newlines but remove excessive whitespace
        lines = [line.strip() for line in text.split("\n")]
        lines = [line for line in lines if line]
        return "\n".join(lines).strip()

    def _bs4_soup(self, html: str):
        try:
            from bs4 import BeautifulSoup  # type: ignore
        except Exception as e:  # pragma: no cover
            raise ModuleNotFoundError(
                "beautifulsoup4 is required for HTML parsing. Install from requirements.txt"
            ) from e

        return BeautifulSoup(html, "html.parser")
