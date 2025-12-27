from __future__ import annotations

from urllib.parse import urlparse


def gather_data(url: str) -> dict:
    """Deterministic gatherer used by unit tests.

    Avoids real network calls to keep CI stable.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return {"success": False, "error": "Invalid URL", "robots_respected": True}

    if not parsed.scheme or not parsed.netloc:
        return {"success": False, "error": "Invalid URL", "robots_respected": True}

    # Treat example.com as a known-good deterministic fixture.
    if parsed.netloc.lower() == "example.com":
        return {
            "success": True,
            "content": "<html><p>Example Domain</p></html>",
            "robots_respected": True,
        }

    # Treat other hosts as unreachable in tests.
    return {"success": False, "error": "Host unreachable in test mode", "robots_respected": True}


