"""Tests for PlaywrightRunner and browser automation.

Tests the browser automation harness without requiring actual Playwright
installation by mocking the Playwright API.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from autopack.browser.playwright_runner import (
    PlaywrightRunner,
    PlaywrightSession,
    BrowserSessionConfig,
    BrowserAction,
    ActionRecord,
    ActionLimitExceededError,
    BrowserSessionError,
)


class TestBrowserSessionConfig:
    """Tests for BrowserSessionConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BrowserSessionConfig()
        assert config.max_actions == 50
        assert config.timeout_seconds == 120
        assert config.action_timeout_ms == 10000
        assert config.capture_screenshots is True
        assert config.capture_video is False
        assert config.capture_har is True
        assert config.headless is True
        assert config.viewport_width == 1280
        assert config.viewport_height == 720

    def test_custom_config(self):
        """Test custom configuration."""
        config = BrowserSessionConfig(
            max_actions=100,
            timeout_seconds=60,
            headless=False,
            capture_video=True,
        )
        assert config.max_actions == 100
        assert config.timeout_seconds == 60
        assert config.headless is False
        assert config.capture_video is True


class TestActionRecord:
    """Tests for ActionRecord."""

    def test_action_record_to_dict(self):
        """Test action record serialization."""
        now = datetime.now(timezone.utc)
        record = ActionRecord(
            action_type=BrowserAction.CLICK,
            selector="button.submit",
            value=None,
            timestamp=now,
            success=True,
            duration_ms=150.5,
        )

        d = record.to_dict()
        assert d["action_type"] == "click"
        assert d["selector"] == "button.submit"
        assert d["success"] is True
        assert d["duration_ms"] == 150.5

    def test_fill_action_redacts_value(self):
        """Test that FILL action values are redacted."""
        record = ActionRecord(
            action_type=BrowserAction.FILL,
            selector="input[name='password']",
            value="secret123",
            timestamp=datetime.now(timezone.utc),
            success=True,
            duration_ms=50,
        )

        d = record.to_dict()
        # Value should be redacted for FILL actions
        assert d["value"] == "[REDACTED]"


class TestPlaywrightSession:
    """Tests for PlaywrightSession."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_page = MagicMock()
        self.mock_context = MagicMock()
        self.config = BrowserSessionConfig(max_actions=5)
        self.artifacts_dir = Path("/tmp/test_artifacts")

        self.session = PlaywrightSession(
            page=self.mock_page,
            context=self.mock_context,
            config=self.config,
            artifacts_dir=self.artifacts_dir,
        )

    def test_initial_state(self):
        """Test initial session state."""
        assert self.session.action_count == 0
        assert self.session.remaining_actions == 5

    def test_action_limit_exceeded(self):
        """Test action limit enforcement."""
        # Exhaust action limit
        for i in range(5):
            self.session._record_action(BrowserAction.CLICK, f"btn{i}", None, True, 10)

        assert self.session.action_count == 5
        assert self.session.remaining_actions == 0

        with pytest.raises(ActionLimitExceededError):
            self.session._check_action_limit()

    def test_record_action(self):
        """Test action recording."""
        self.session._record_action(
            BrowserAction.CLICK,
            "button",
            None,
            True,
            100,
        )

        assert self.session.action_count == 1
        log = self.session.get_action_log()
        assert len(log) == 1
        assert log[0]["action_type"] == "click"

    def test_session_summary(self):
        """Test session summary generation."""
        self.session._record_action(BrowserAction.CLICK, "btn", None, True, 10)
        self.session._record_action(BrowserAction.FILL, "inp", "val", False, 20, "Error")

        summary = self.session.get_session_summary()
        assert summary["total_actions"] == 2
        assert summary["successful_actions"] == 1
        assert summary["failed_actions"] == 1
        assert summary["remaining_actions"] == 3

    @pytest.mark.asyncio
    async def test_navigate(self):
        """Test navigation action."""
        self.mock_page.goto = AsyncMock()

        await self.session.navigate("https://example.com")

        self.mock_page.goto.assert_called_once()
        assert self.session.action_count == 1

    @pytest.mark.asyncio
    async def test_navigate_error(self):
        """Test navigation error handling."""
        self.mock_page.goto = AsyncMock(side_effect=Exception("Network error"))

        with pytest.raises(BrowserSessionError):
            await self.session.navigate("https://example.com")

        # Action should still be recorded
        log = self.session.get_action_log()
        assert len(log) == 1
        assert log[0]["success"] is False

    @pytest.mark.asyncio
    async def test_click(self):
        """Test click action."""
        self.mock_page.click = AsyncMock()

        await self.session.click("button.submit")

        self.mock_page.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_fill(self):
        """Test fill action."""
        self.mock_page.fill = AsyncMock()

        await self.session.fill("input[name='user']", "testuser")

        self.mock_page.fill.assert_called_once()
        # Check that value is redacted in log
        log = self.session.get_action_log()
        assert log[0]["value"] == "[REDACTED]"


class TestPlaywrightRunner:
    """Tests for PlaywrightRunner."""

    def test_runner_initialization(self):
        """Test runner initialization."""
        runner = PlaywrightRunner()
        assert runner._config is not None
        assert runner._artifacts_dir == Path(".autonomous_runs/browser_artifacts")

    def test_custom_artifacts_dir(self):
        """Test custom artifacts directory."""
        custom_dir = Path("/custom/artifacts")
        runner = PlaywrightRunner(artifacts_dir=custom_dir)
        assert runner._artifacts_dir == custom_dir

    def test_custom_config(self):
        """Test custom configuration."""
        config = BrowserSessionConfig(max_actions=100)
        runner = PlaywrightRunner(config=config)
        assert runner._config.max_actions == 100

    def test_runner_has_session_method(self):
        """Test runner has session method for context manager."""
        runner = PlaywrightRunner()
        assert hasattr(runner, "session")
        assert callable(runner.session)

    def test_runner_has_close_method(self):
        """Test runner has close method."""
        runner = PlaywrightRunner()
        assert hasattr(runner, "close")

    def test_runner_has_run_automation_method(self):
        """Test runner has run_automation method."""
        runner = PlaywrightRunner()
        assert hasattr(runner, "run_automation")
