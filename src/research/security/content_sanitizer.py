"""Content Sanitization Module.

This module provides the ContentSanitizer class for sanitizing and validating
content from external sources to prevent security issues.
"""

import re
from typing import Dict, List, Optional
from urllib.parse import urlparse


class ContentSanitizer:
    """Sanitizes content from external sources."""

    def __init__(self):
        """Initialize the content sanitizer."""
        # Dangerous patterns to detect
        self.dangerous_patterns = [
            r"<script[^>]*>.*?</script>",
            r"javascript:",
            r"on\w+\s*=",  # Event handlers
            r"<iframe[^>]*>",
            r"<object[^>]*>",
            r"<embed[^>]*>",
            r"eval\s*\(",
            r"document\.cookie",
            r"document\.write",
        ]

        # Allowed HTML tags for rich content
        self.allowed_tags = {
            "p",
            "br",
            "strong",
            "em",
            "u",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "ul",
            "ol",
            "li",
            "a",
            "code",
            "pre",
            "blockquote",
            "img",
        }

        # Allowed URL schemes
        self.allowed_schemes = {"http", "https", "ftp"}

        # Maximum content lengths
        self.max_lengths = {"text": 100000, "url": 2048, "title": 500, "snippet": 1000}

    def sanitize_text(self, text: str, max_length: Optional[int] = None) -> str:
        """Sanitize plain text content.

        Args:
            text: Input text
            max_length: Maximum allowed length

        Returns:
            Sanitized text
        """
        if not text:
            return ""

        # Remove null bytes
        text = text.replace("\x00", "")

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        text = text.strip()

        # Truncate if needed
        if max_length:
            text = text[:max_length]
        elif len(text) > self.max_lengths["text"]:
            text = text[: self.max_lengths["text"]]

        return text

    def sanitize_html(self, html_content: str, allow_tags: bool = True) -> str:
        """Sanitize HTML content.

        Args:
            html_content: Input HTML
            allow_tags: Whether to allow safe HTML tags

        Returns:
            Sanitized HTML or plain text
        """
        if not html_content:
            return ""

        # Remove dangerous patterns
        for pattern in self.dangerous_patterns:
            html_content = re.sub(pattern, "", html_content, flags=re.IGNORECASE | re.DOTALL)

        if not allow_tags:
            # Strip all HTML tags
            html_content = re.sub(r"<[^>]+>", "", html_content)
            return self.sanitize_text(html_content)

        # Remove disallowed tags
        html_content = self._filter_tags(html_content)

        # Sanitize attributes
        html_content = self._sanitize_attributes(html_content)

        return html_content

    def sanitize_url(self, url: str) -> Optional[str]:
        """Sanitize and validate a URL.

        Args:
            url: Input URL

        Returns:
            Sanitized URL or None if invalid
        """
        if not url:
            return None

        # Remove whitespace
        url = url.strip()

        # Check length
        if len(url) > self.max_lengths["url"]:
            return None

        # Parse URL
        try:
            parsed = urlparse(url)
        except Exception:
            return None

        # Validate scheme
        if parsed.scheme and parsed.scheme.lower() not in self.allowed_schemes:
            return None

        # Check for dangerous patterns
        if re.search(r"javascript:|data:|vbscript:", url, re.IGNORECASE):
            return None

        return url

    def sanitize_code(self, code: str, language: Optional[str] = None) -> str:
        """Sanitize code snippets.

        Args:
            code: Code snippet
            language: Programming language

        Returns:
            Sanitized code
        """
        if not code:
            return ""

        # Remove null bytes
        code = code.replace("\x00", "")

        # Limit length
        if len(code) > 50000:  # 50KB max for code
            code = code[:50000]

        return code

    def detect_malicious_content(self, content: str) -> Dict[str, List[str]]:
        """Detect potentially malicious content.

        Args:
            content: Content to analyze

        Returns:
            Dictionary of detected issues
        """
        issues = {"dangerous_patterns": [], "suspicious_urls": [], "warnings": []}

        # Check for dangerous patterns
        for pattern in self.dangerous_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
            if matches:
                issues["dangerous_patterns"].append(pattern)

        # Check for suspicious URLs
        url_pattern = r'https?://[^\s<>"]+'
        urls = re.findall(url_pattern, content)
        for url in urls:
            if not self.sanitize_url(url):
                issues["suspicious_urls"].append(url)

        # Check for excessive length
        if len(content) > self.max_lengths["text"]:
            issues["warnings"].append("Content exceeds maximum length")

        return issues

    def _filter_tags(self, html: str) -> str:
        """Filter HTML to only allowed tags.

        Args:
            html: Input HTML

        Returns:
            Filtered HTML
        """

        # Simple tag filtering (in production, use a proper HTML parser)
        def replace_tag(match):
            tag_name = match.group(1).lower().split()[0]
            if tag_name in self.allowed_tags:
                return match.group(0)
            else:
                return ""

        # Remove disallowed tags
        html = re.sub(r"<(/?)([^>]+)>", replace_tag, html)

        return html

    def _sanitize_attributes(self, html: str) -> str:
        """Sanitize HTML attributes.

        Args:
            html: Input HTML

        Returns:
            HTML with sanitized attributes
        """
        # Remove event handlers
        html = re.sub(r'\son\w+\s*=\s*["\'][^"\']*["\']', "", html, flags=re.IGNORECASE)

        # Sanitize href attributes
        def sanitize_href(match):
            url = match.group(1)
            sanitized = self.sanitize_url(url)
            if sanitized:
                return f'href="{html.escape(sanitized)}"'
            else:
                return ""

        html = re.sub(r'href\s*=\s*["\']([^"\']*)["\']', sanitize_href, html, flags=re.IGNORECASE)

        return html

    def sanitize_metadata(self, metadata: Dict) -> Dict:
        """Sanitize metadata dictionary.

        Args:
            metadata: Metadata dictionary

        Returns:
            Sanitized metadata
        """
        sanitized = {}

        for key, value in metadata.items():
            if isinstance(value, str):
                if key == "url":
                    sanitized_value = self.sanitize_url(value)
                    if sanitized_value:
                        sanitized[key] = sanitized_value
                elif key in ["title", "name"]:
                    sanitized[key] = self.sanitize_text(value, self.max_lengths["title"])
                elif key in ["description", "snippet", "summary"]:
                    sanitized[key] = self.sanitize_text(value, self.max_lengths["snippet"])
                else:
                    sanitized[key] = self.sanitize_text(value)
            elif isinstance(value, (int, float, bool)):
                sanitized[key] = value
            elif isinstance(value, list):
                sanitized[key] = [self.sanitize_text(str(item)) for item in value]
            elif isinstance(value, dict):
                sanitized[key] = self.sanitize_metadata(value)

        return sanitized

    def is_safe_content(self, content: str) -> bool:
        """Check if content is safe.

        Args:
            content: Content to check

        Returns:
            True if safe, False otherwise
        """
        issues = self.detect_malicious_content(content)
        return not any(issues.values())
