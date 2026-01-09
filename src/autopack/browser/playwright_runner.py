"""Playwright-based browser automation runner.

Implements browser automation with safety constraints:
- Bounded actions (max clicks, navigation, typing)
- Deterministic artifact capture (screenshots, videos, HAR logs)
- Automatic credential/PII redaction
- Timeout enforcement

Usage:
    runner = PlaywrightRunner(
        max_actions=50,
        timeout_seconds=120,
        capture_screenshots=True,
    )

    async with runner.session(url="https://example.com") as session:
        await session.click("button.submit")
        await session.fill("input[name='search']", "query")
        screenshot = await session.screenshot()
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class BrowserAction(str, Enum):
    """Types of browser actions for tracking."""

    NAVIGATE = "navigate"
    CLICK = "click"
    FILL = "fill"
    SELECT = "select"
    SCREENSHOT = "screenshot"
    WAIT = "wait"
    SCROLL = "scroll"
    HOVER = "hover"
    PRESS_KEY = "press_key"


@dataclass
class ActionRecord:
    """Record of a browser action."""

    action_type: BrowserAction
    selector: Optional[str]
    value: Optional[str]
    timestamp: datetime
    success: bool
    duration_ms: float
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type.value,
            "selector": self.selector,
            "value": self.value if self.action_type != BrowserAction.FILL else "[REDACTED]",
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


@dataclass
class BrowserSessionConfig:
    """Configuration for a browser session."""

    max_actions: int = 50
    timeout_seconds: int = 120
    action_timeout_ms: int = 10000
    capture_screenshots: bool = True
    capture_video: bool = False
    capture_har: bool = True
    headless: bool = True
    viewport_width: int = 1280
    viewport_height: int = 720
    user_agent: Optional[str] = None
    extra_http_headers: dict = field(default_factory=dict)


class ActionLimitExceededError(Exception):
    """Raised when action limit is exceeded."""

    pass


class BrowserSessionError(Exception):
    """General browser session error."""

    pass


class PlaywrightSession:
    """A browser automation session with safety constraints.

    Tracks all actions and enforces limits to prevent runaway automation.
    """

    def __init__(
        self,
        page: Any,  # playwright.async_api.Page
        context: Any,  # playwright.async_api.BrowserContext
        config: BrowserSessionConfig,
        artifacts_dir: Path,
    ):
        """Initialize session.

        Args:
            page: Playwright page instance
            context: Playwright browser context
            config: Session configuration
            artifacts_dir: Directory for storing artifacts
        """
        self._page = page
        self._context = context
        self._config = config
        self._artifacts_dir = artifacts_dir
        self._action_count = 0
        self._actions: list[ActionRecord] = []
        self._start_time = datetime.now(timezone.utc)
        self._har_path: Optional[Path] = None

    @property
    def action_count(self) -> int:
        """Number of actions performed."""
        return self._action_count

    @property
    def remaining_actions(self) -> int:
        """Number of actions remaining before limit."""
        return max(0, self._config.max_actions - self._action_count)

    def _check_action_limit(self) -> None:
        """Check if action limit exceeded."""
        if self._action_count >= self._config.max_actions:
            raise ActionLimitExceededError(
                f"Action limit exceeded: {self._action_count}/{self._config.max_actions}"
            )

    def _record_action(
        self,
        action_type: BrowserAction,
        selector: Optional[str],
        value: Optional[str],
        success: bool,
        duration_ms: float,
        error: Optional[str] = None,
    ) -> ActionRecord:
        """Record an action."""
        record = ActionRecord(
            action_type=action_type,
            selector=selector,
            value=value,
            timestamp=datetime.now(timezone.utc),
            success=success,
            duration_ms=duration_ms,
            error=error,
        )
        self._actions.append(record)
        self._action_count += 1
        return record

    async def navigate(self, url: str, wait_until: str = "load") -> None:
        """Navigate to a URL.

        Args:
            url: URL to navigate to
            wait_until: Wait condition ('load', 'domcontentloaded', 'networkidle')
        """
        self._check_action_limit()
        start = asyncio.get_event_loop().time()

        try:
            await self._page.goto(
                url,
                wait_until=wait_until,
                timeout=self._config.action_timeout_ms,
            )
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.NAVIGATE, None, url, True, duration)
            logger.debug(f"Navigated to {url}")
        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.NAVIGATE, None, url, False, duration, str(e))
            raise BrowserSessionError(f"Navigation failed: {e}") from e

    async def click(self, selector: str, force: bool = False) -> None:
        """Click an element.

        Args:
            selector: CSS selector for element
            force: Force click even if element is not visible
        """
        self._check_action_limit()
        start = asyncio.get_event_loop().time()

        try:
            await self._page.click(
                selector,
                force=force,
                timeout=self._config.action_timeout_ms,
            )
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.CLICK, selector, None, True, duration)
            logger.debug(f"Clicked {selector}")
        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.CLICK, selector, None, False, duration, str(e))
            raise BrowserSessionError(f"Click failed on {selector}: {e}") from e

    async def fill(self, selector: str, value: str) -> None:
        """Fill an input field.

        Args:
            selector: CSS selector for input element
            value: Value to fill (will be redacted in logs)
        """
        self._check_action_limit()
        start = asyncio.get_event_loop().time()

        try:
            await self._page.fill(
                selector,
                value,
                timeout=self._config.action_timeout_ms,
            )
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.FILL, selector, "[REDACTED]", True, duration)
            logger.debug(f"Filled {selector}")
        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.FILL, selector, "[REDACTED]", False, duration, str(e))
            raise BrowserSessionError(f"Fill failed on {selector}: {e}") from e

    async def select(self, selector: str, value: str) -> None:
        """Select an option from a dropdown.

        Args:
            selector: CSS selector for select element
            value: Value to select
        """
        self._check_action_limit()
        start = asyncio.get_event_loop().time()

        try:
            await self._page.select_option(
                selector,
                value,
                timeout=self._config.action_timeout_ms,
            )
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.SELECT, selector, value, True, duration)
            logger.debug(f"Selected {value} in {selector}")
        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.SELECT, selector, value, False, duration, str(e))
            raise BrowserSessionError(f"Select failed on {selector}: {e}") from e

    async def wait_for_selector(self, selector: str, state: str = "visible") -> None:
        """Wait for an element.

        Args:
            selector: CSS selector to wait for
            state: State to wait for ('attached', 'detached', 'visible', 'hidden')
        """
        self._check_action_limit()
        start = asyncio.get_event_loop().time()

        try:
            await self._page.wait_for_selector(
                selector,
                state=state,
                timeout=self._config.action_timeout_ms,
            )
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.WAIT, selector, state, True, duration)
            logger.debug(f"Waited for {selector} ({state})")
        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.WAIT, selector, state, False, duration, str(e))
            raise BrowserSessionError(f"Wait failed for {selector}: {e}") from e

    async def screenshot(
        self,
        name: Optional[str] = None,
        full_page: bool = False,
    ) -> Path:
        """Take a screenshot.

        Args:
            name: Name for the screenshot file
            full_page: Capture full page

        Returns:
            Path to the saved screenshot
        """
        self._check_action_limit()
        start = asyncio.get_event_loop().time()

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{name or 'screenshot'}_{timestamp}.png"
        path = self._artifacts_dir / "screenshots" / filename
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            await self._page.screenshot(path=str(path), full_page=full_page)
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.SCREENSHOT, None, filename, True, duration)
            logger.debug(f"Screenshot saved: {path}")
            return path
        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.SCREENSHOT, None, filename, False, duration, str(e))
            raise BrowserSessionError(f"Screenshot failed: {e}") from e

    async def scroll(self, x: int = 0, y: int = 0, selector: Optional[str] = None) -> None:
        """Scroll the page or an element.

        Args:
            x: Horizontal scroll amount
            y: Vertical scroll amount
            selector: Optional element to scroll within
        """
        self._check_action_limit()
        start = asyncio.get_event_loop().time()

        try:
            if selector:
                await self._page.locator(selector).scroll_into_view_if_needed()
            else:
                await self._page.evaluate(f"window.scrollBy({x}, {y})")
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.SCROLL, selector, f"({x}, {y})", True, duration)
        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(
                BrowserAction.SCROLL, selector, f"({x}, {y})", False, duration, str(e)
            )
            raise BrowserSessionError(f"Scroll failed: {e}") from e

    async def hover(self, selector: str) -> None:
        """Hover over an element.

        Args:
            selector: CSS selector for element
        """
        self._check_action_limit()
        start = asyncio.get_event_loop().time()

        try:
            await self._page.hover(selector, timeout=self._config.action_timeout_ms)
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.HOVER, selector, None, True, duration)
        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.HOVER, selector, None, False, duration, str(e))
            raise BrowserSessionError(f"Hover failed on {selector}: {e}") from e

    async def press_key(self, key: str, selector: Optional[str] = None) -> None:
        """Press a keyboard key.

        Args:
            key: Key to press (e.g., 'Enter', 'Tab', 'Escape')
            selector: Optional element to focus first
        """
        self._check_action_limit()
        start = asyncio.get_event_loop().time()

        try:
            if selector:
                await self._page.locator(selector).press(key)
            else:
                await self._page.keyboard.press(key)
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.PRESS_KEY, selector, key, True, duration)
        except Exception as e:
            duration = (asyncio.get_event_loop().time() - start) * 1000
            self._record_action(BrowserAction.PRESS_KEY, selector, key, False, duration, str(e))
            raise BrowserSessionError(f"Key press failed: {e}") from e

    async def get_text(self, selector: str) -> str:
        """Get text content of an element.

        Args:
            selector: CSS selector for element

        Returns:
            Text content
        """
        return await self._page.text_content(selector) or ""

    async def get_attribute(self, selector: str, attribute: str) -> Optional[str]:
        """Get attribute value of an element.

        Args:
            selector: CSS selector for element
            attribute: Attribute name

        Returns:
            Attribute value or None
        """
        return await self._page.get_attribute(selector, attribute)

    def get_action_log(self) -> list[dict]:
        """Get log of all actions performed."""
        return [action.to_dict() for action in self._actions]

    def get_session_summary(self) -> dict:
        """Get summary of the session."""
        end_time = datetime.now(timezone.utc)
        duration = (end_time - self._start_time).total_seconds()

        successful = sum(1 for a in self._actions if a.success)
        failed = sum(1 for a in self._actions if not a.success)

        return {
            "start_time": self._start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "total_actions": self._action_count,
            "successful_actions": successful,
            "failed_actions": failed,
            "remaining_actions": self.remaining_actions,
            "config": {
                "max_actions": self._config.max_actions,
                "timeout_seconds": self._config.timeout_seconds,
                "headless": self._config.headless,
            },
        }


class PlaywrightRunner:
    """Browser automation runner with Playwright.

    Provides session management with automatic resource cleanup and
    artifact capture.

    Usage:
        runner = PlaywrightRunner()
        async with runner.session(url="https://example.com") as session:
            await session.click("button")
            await session.screenshot()
    """

    def __init__(
        self,
        artifacts_dir: Optional[Path] = None,
        config: Optional[BrowserSessionConfig] = None,
    ):
        """Initialize the runner.

        Args:
            artifacts_dir: Directory for storing artifacts
            config: Default session configuration
        """
        self._artifacts_dir = artifacts_dir or Path(".autonomous_runs/browser_artifacts")
        self._config = config or BrowserSessionConfig()
        self._playwright = None
        self._browser = None

    async def _ensure_playwright(self) -> None:
        """Ensure Playwright is initialized."""
        if self._playwright is None:
            try:
                from playwright.async_api import async_playwright

                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(
                    headless=self._config.headless
                )
            except ImportError:
                raise BrowserSessionError(
                    "Playwright is not installed. "
                    "Install with: pip install playwright && playwright install"
                )

    async def close(self) -> None:
        """Close browser and cleanup resources."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    class _SessionContext:
        """Context manager for browser sessions."""

        def __init__(
            self,
            runner: "PlaywrightRunner",
            url: Optional[str],
            config: BrowserSessionConfig,
            session_id: str,
        ):
            self._runner = runner
            self._url = url
            self._config = config
            self._session_id = session_id
            self._session: Optional[PlaywrightSession] = None
            self._context = None

        async def __aenter__(self) -> PlaywrightSession:
            await self._runner._ensure_playwright()

            # Create artifacts directory for this session
            artifacts_dir = self._runner._artifacts_dir / self._session_id
            artifacts_dir.mkdir(parents=True, exist_ok=True)

            # Setup HAR recording if enabled
            har_path = None
            if self._config.capture_har:
                har_path = artifacts_dir / "network.har"

            # Create browser context
            context_options = {
                "viewport": {
                    "width": self._config.viewport_width,
                    "height": self._config.viewport_height,
                },
            }

            if self._config.user_agent:
                context_options["user_agent"] = self._config.user_agent

            if self._config.capture_video:
                context_options["record_video_dir"] = str(artifacts_dir / "videos")

            if har_path:
                context_options["record_har_path"] = str(har_path)

            self._context = await self._runner._browser.new_context(**context_options)

            # Create page
            page = await self._context.new_page()

            # Create session
            self._session = PlaywrightSession(
                page=page,
                context=self._context,
                config=self._config,
                artifacts_dir=artifacts_dir,
            )
            self._session._har_path = har_path

            # Navigate to initial URL if provided
            if self._url:
                await self._session.navigate(self._url)

            return self._session

        async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
            if self._session:
                # Save session summary
                summary_path = (
                    self._runner._artifacts_dir / self._session_id / "session_summary.json"
                )
                import json

                summary = self._session.get_session_summary()
                summary["actions"] = self._session.get_action_log()
                summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

            if self._context:
                await self._context.close()

    def session(
        self,
        url: Optional[str] = None,
        config: Optional[BrowserSessionConfig] = None,
        session_id: Optional[str] = None,
    ) -> _SessionContext:
        """Create a new browser session.

        Args:
            url: Initial URL to navigate to
            config: Session configuration (uses default if not provided)
            session_id: Unique session identifier

        Returns:
            Async context manager yielding PlaywrightSession
        """
        import uuid

        session_id = session_id or f"session_{uuid.uuid4().hex[:8]}"
        config = config or self._config

        return self._SessionContext(self, url, config, session_id)

    async def run_automation(
        self,
        url: str,
        actions: list[dict],
        config: Optional[BrowserSessionConfig] = None,
    ) -> dict:
        """Run a predefined automation sequence.

        Args:
            url: Starting URL
            actions: List of actions to perform
                Each action is a dict with 'type' and action-specific parameters
            config: Session configuration

        Returns:
            Automation result including success status and artifacts

        Example:
            result = await runner.run_automation(
                url="https://example.com",
                actions=[
                    {"type": "click", "selector": "button.login"},
                    {"type": "fill", "selector": "input[name='user']", "value": "test"},
                    {"type": "screenshot", "name": "after_fill"},
                ],
            )
        """
        import uuid

        session_id = f"automation_{uuid.uuid4().hex[:8]}"
        artifacts = []
        errors = []

        async with self.session(url=url, config=config, session_id=session_id) as session:
            for i, action in enumerate(actions):
                action_type = action.get("type")
                try:
                    if action_type == "click":
                        await session.click(action["selector"], force=action.get("force", False))
                    elif action_type == "fill":
                        await session.fill(action["selector"], action["value"])
                    elif action_type == "select":
                        await session.select(action["selector"], action["value"])
                    elif action_type == "wait":
                        await session.wait_for_selector(
                            action["selector"], action.get("state", "visible")
                        )
                    elif action_type == "screenshot":
                        path = await session.screenshot(
                            name=action.get("name"),
                            full_page=action.get("full_page", False),
                        )
                        artifacts.append(str(path))
                    elif action_type == "navigate":
                        await session.navigate(action["url"])
                    elif action_type == "scroll":
                        await session.scroll(
                            action.get("x", 0),
                            action.get("y", 0),
                            action.get("selector"),
                        )
                    elif action_type == "hover":
                        await session.hover(action["selector"])
                    elif action_type == "press_key":
                        await session.press_key(action["key"], action.get("selector"))
                    else:
                        errors.append(
                            {"action_index": i, "error": f"Unknown action type: {action_type}"}
                        )

                except (ActionLimitExceededError, BrowserSessionError) as e:
                    errors.append({"action_index": i, "error": str(e)})
                    if action.get("stop_on_error", True):
                        break

            summary = session.get_session_summary()

        return {
            "session_id": session_id,
            "success": len(errors) == 0,
            "summary": summary,
            "artifacts": artifacts,
            "errors": errors,
        }
