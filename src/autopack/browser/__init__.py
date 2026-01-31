"""
Browser Automation Harness (BUILD-189 Phase 5)

Playwright-based browser automation with safety constraints:
- No credential leaks (cookie/token redaction)
- Bounded actions (max clicks, max navigation)
- Deterministic artifacts (screenshots, videos, HAR logs)

Use cases:
- Web scraping when APIs unavailable
- Form automation
- Testing/verification

Installation:
    pip install playwright && playwright install

Usage:
    from autopack.browser import PlaywrightRunner, BrowserSessionConfig

    runner = PlaywrightRunner()
    async with runner.session(url="https://example.com") as session:
        await session.click("button.submit")
        await session.screenshot()
"""

from .artifacts import BrowserArtifactManager, BrowserArtifactPolicy
from .playwright_runner import (ActionLimitExceededError, ActionRecord,
                                BrowserAction, BrowserSessionConfig,
                                BrowserSessionError, PlaywrightRunner,
                                PlaywrightSession)

__all__ = [
    # Runner
    "PlaywrightRunner",
    "PlaywrightSession",
    "BrowserSessionConfig",
    # Actions
    "BrowserAction",
    "ActionRecord",
    # Errors
    "ActionLimitExceededError",
    "BrowserSessionError",
    # Artifacts
    "BrowserArtifactManager",
    "BrowserArtifactPolicy",
]
