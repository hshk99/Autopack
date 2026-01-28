"""Tests for BuilderResultPoster async sleep behavior.

Tests that retry logic uses asyncio.sleep instead of blocking time.sleep.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autopack.api.builder_result_poster import BuilderResultPoster
from autopack.llm_client import BuilderResult


class TestBuilderResultPosterAsyncSleep:
    """Tests for async sleep in retry logic."""

    @pytest.fixture
    def mock_executor(self):
        """Create a mock executor with required attributes."""
        executor = MagicMock()
        executor.run_id = "test-run-123"
        executor.run_type = "standard"
        executor.workspace = "/tmp/test-workspace"
        executor._run_http_500_count = 0
        executor.MAX_HTTP_500_PER_RUN = 10
        executor.api_client = MagicMock()
        executor._payload_correction_tracker = MagicMock()
        return executor

    @pytest.fixture
    def mock_builder_result(self):
        """Create a mock builder result."""
        return BuilderResult(
            success=True,
            patch_content="",
            tokens_used=100,
            builder_messages=[],
            model_used="test-model",
            error=None,
        )

    @pytest.mark.asyncio
    async def test_post_result_is_async(self, mock_executor, mock_builder_result):
        """Verify post_result is an async coroutine."""
        poster = BuilderResultPoster(mock_executor)

        # Mock the API client to succeed
        mock_executor.api_client.submit_builder_result = MagicMock()

        # Call the async method
        result = poster.post_result("phase-1", mock_builder_result)

        # Verify it returns a coroutine
        assert asyncio.iscoroutine(result)

        # Await it to complete
        await result

    @pytest.mark.asyncio
    async def test_retry_uses_asyncio_sleep_not_time_sleep(
        self, mock_executor, mock_builder_result
    ):
        """Verify retry logic uses asyncio.sleep for non-blocking backoff."""
        from autopack.supervisor.api_client import SupervisorApiHttpError

        poster = BuilderResultPoster(mock_executor)

        # Create a mock that raises HTTP 500 on first call, succeeds on second
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise SupervisorApiHttpError(500, "Server Error", None)
            return None

        mock_executor.api_client.submit_builder_result = MagicMock(side_effect=side_effect)

        # Patch asyncio.sleep to verify it's called
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await poster.post_result("phase-1", mock_builder_result)

            # asyncio.sleep should have been called for the retry backoff
            mock_sleep.assert_called_once()
            # Verify backoff value (1 * 2^0 = 1 second for first retry)
            mock_sleep.assert_called_with(1)

    @pytest.mark.asyncio
    async def test_no_sleep_on_success(self, mock_executor, mock_builder_result):
        """Verify no sleep is called when request succeeds immediately."""
        poster = BuilderResultPoster(mock_executor)

        # Mock the API client to succeed immediately
        mock_executor.api_client.submit_builder_result = MagicMock()

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await poster.post_result("phase-1", mock_builder_result)

            # asyncio.sleep should not have been called
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_exponential_backoff_values(self, mock_executor, mock_builder_result):
        """Verify exponential backoff calculation in retries."""
        from autopack.supervisor.api_client import SupervisorApiHttpError

        poster = BuilderResultPoster(mock_executor)

        # Create a mock that always raises HTTP 500
        def always_fail(*args, **kwargs):
            raise SupervisorApiHttpError(500, "Server Error", None)

        mock_executor.api_client.submit_builder_result = MagicMock(side_effect=always_fail)

        sleep_values = []

        async def capture_sleep(seconds):
            sleep_values.append(seconds)

        with patch("asyncio.sleep", side_effect=capture_sleep):
            # Method swallows exception after retries, just returns
            await poster.post_result("phase-1", mock_builder_result)

        # Verify exponential backoff: 1*2^0=1, 1*2^1=2
        assert sleep_values == [1, 2]
