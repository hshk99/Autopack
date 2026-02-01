"""
Tests for API Availability Checker.

Tests the APIAvailabilityChecker class for validating APIs before recommendation.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import Response

from autopack.research.discovery.api_availability_checker import (
    APIAvailabilityCheck, APIAvailabilityChecker, APIStatus)


@pytest.fixture
def checker():
    """Create an APIAvailabilityChecker instance."""
    return APIAvailabilityChecker(timeout=5.0, retries=1)


@pytest.fixture
def checker_with_tokens():
    """Create an APIAvailabilityChecker with API tokens."""
    return APIAvailabilityChecker(
        timeout=5.0,
        retries=1,
        api_tokens={
            "openai": "sk-test-token",
            "github": "ghp-test-token",
        },
    )


class TestAPIAvailabilityCheck:
    """Test APIAvailabilityCheck dataclass."""

    def test_create_check_minimal(self):
        """Test creating a minimal APIAvailabilityCheck."""
        check = APIAvailabilityCheck(
            api_name="openai",
            is_available=True,
            status=APIStatus.AVAILABLE,
        )
        assert check.api_name == "openai"
        assert check.is_available is True
        assert check.status == APIStatus.AVAILABLE
        assert check.last_checked is not None
        assert isinstance(check.last_checked, datetime)

    def test_create_check_with_quota(self):
        """Test creating check with quota information."""
        check = APIAvailabilityCheck(
            api_name="github",
            is_available=True,
            status=APIStatus.AVAILABLE,
            http_status=200,
            quota_limit=5000,
            quota_remaining=4999,
            response_time_ms=150.5,
        )
        assert check.quota_limit == 5000
        assert check.quota_remaining == 4999
        assert check.response_time_ms == 150.5

    def test_check_to_dict(self):
        """Test converting APIAvailabilityCheck to dictionary."""
        check = APIAvailabilityCheck(
            api_name="openai",
            is_available=True,
            status=APIStatus.AVAILABLE,
            http_status=200,
            quota_limit=100,
            quota_remaining=50,
        )
        result_dict = check.to_dict()

        assert result_dict["api_name"] == "openai"
        assert result_dict["is_available"] is True
        assert result_dict["status"] == "available"
        assert result_dict["http_status"] == 200
        assert result_dict["quota_limit"] == 100
        assert result_dict["quota_remaining"] == 50
        assert isinstance(result_dict["last_checked"], str)

    def test_check_to_dict_with_error(self):
        """Test converting failed check to dictionary."""
        check = APIAvailabilityCheck(
            api_name="stripe",
            is_available=False,
            status=APIStatus.TIMEOUT,
            error_message="Request timeout",
        )
        result_dict = check.to_dict()

        assert result_dict["is_available"] is False
        assert result_dict["status"] == "timeout"
        assert result_dict["error_message"] == "Request timeout"


class TestAPIAvailabilityChecker:
    """Test APIAvailabilityChecker class."""

    def test_initialization(self):
        """Test checker initialization."""
        checker = APIAvailabilityChecker(timeout=15.0, retries=3)
        assert checker._timeout == 15.0
        assert checker._retries == 3
        assert checker._api_tokens == {}

    def test_initialization_with_tokens(self):
        """Test checker initialization with API tokens."""
        tokens = {"openai": "test-token"}
        checker = APIAvailabilityChecker(api_tokens=tokens)
        assert checker._api_tokens == tokens

    @pytest.mark.asyncio
    async def test_check_availability_success(self, checker):
        """Test successful availability check."""
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {
            "x-ratelimit-limit": "5000",
            "x-ratelimit-remaining": "4999",
        }
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds = MagicMock(return_value=0.15)

        with patch("autopack.research.discovery.api_availability_checker.httpx") as _:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.is_closed = False
            checker._client = mock_client

            result = await checker.check_availability("github")

            assert result.api_name == "github"
            assert result.is_available is True
            assert result.status == APIStatus.AVAILABLE
            assert result.http_status == 200
            assert result.response_time_ms == 150.0

    @pytest.mark.asyncio
    async def test_check_availability_unavailable(self, checker):
        """Test checking unavailable API."""
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 503
        mock_response.headers = {}
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds = MagicMock(return_value=0.1)

        with patch("autopack.research.discovery.api_availability_checker.httpx") as _:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.is_closed = False
            checker._client = mock_client

            result = await checker.check_availability("github")

            assert result.is_available is False
            assert result.status == APIStatus.UNAVAILABLE
            assert result.http_status == 503

    @pytest.mark.asyncio
    async def test_check_availability_timeout(self, checker):
        """Test timeout during availability check."""
        import httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
        mock_client.is_closed = False
        checker._client = mock_client

        result = await checker.check_availability("github")

        assert result.is_available is False
        assert result.status == APIStatus.TIMEOUT
        assert "Timeout" in result.error_message

    @pytest.mark.asyncio
    async def test_check_availability_with_custom_endpoint(self, checker):
        """Test checking custom API endpoint."""
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds = MagicMock(return_value=0.1)

        with patch("autopack.research.discovery.api_availability_checker.httpx") as _:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.is_closed = False
            checker._client = mock_client

            result = await checker.check_availability(
                "custom_api",
                custom_endpoint="https://example.com/api/health",
            )

            assert result.api_name == "custom_api"
            assert result.is_available is True
            mock_client.get.assert_called_with(
                "https://example.com/api/health",
                headers={},
                follow_redirects=True,
            )

    @pytest.mark.asyncio
    async def test_check_availability_authentication_required(self, checker):
        """Test API that requires authentication."""
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 401
        mock_response.headers = {}
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds = MagicMock(return_value=0.1)

        with patch("autopack.research.discovery.api_availability_checker.httpx") as _:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.is_closed = False
            checker._client = mock_client

            result = await checker.check_availability("openai")

            assert result.is_available is True
            assert result.authentication_required is True
            assert result.can_authenticate is True

    @pytest.mark.asyncio
    async def test_check_availability_unknown_api(self, checker):
        """Test checking unknown API."""
        result = await checker.check_availability("unknown_api")

        assert result.is_available is False
        assert result.status == APIStatus.UNAVAILABLE
        assert "not in known endpoints" in result.error_message

    @pytest.mark.asyncio
    async def test_check_multiple_apis(self, checker):
        """Test checking multiple APIs concurrently."""
        mock_response_200 = MagicMock(spec=Response)
        mock_response_200.status_code = 200
        mock_response_200.headers = {}
        mock_response_200.elapsed = MagicMock()
        mock_response_200.elapsed.total_seconds = MagicMock(return_value=0.1)

        mock_response_503 = MagicMock(spec=Response)
        mock_response_503.status_code = 503
        mock_response_503.headers = {}
        mock_response_503.elapsed = MagicMock()
        mock_response_503.elapsed.total_seconds = MagicMock(return_value=0.2)

        with patch("autopack.research.discovery.api_availability_checker.httpx") as _:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=[mock_response_200, mock_response_503],
            )
            mock_client.is_closed = False
            checker._client = mock_client

            results = await checker.check_multiple(["github", "stripe"])

            assert len(results) == 2
            assert results[0].api_name == "github"
            assert results[0].is_available is True
            assert results[1].api_name == "stripe"
            assert results[1].is_available is False

    @pytest.mark.asyncio
    async def test_get_health_status(self, checker):
        """Test getting detailed health status."""
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {
            "x-ratelimit-limit": "5000",
            "x-ratelimit-remaining": "4999",
        }
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds = MagicMock(return_value=0.1)

        with patch("autopack.research.discovery.api_availability_checker.httpx") as _:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.is_closed = False
            checker._client = mock_client

            status = await checker.get_health_status("github")

            assert status["api_name"] == "github"
            assert status["healthy"] is True
            assert status["status"] == "available"
            assert "details" in status

    @pytest.mark.asyncio
    async def test_validate_apis_for_recommendation(self, checker):
        """Test validating APIs for recommendation."""
        mock_response_200 = MagicMock(spec=Response)
        mock_response_200.status_code = 200
        mock_response_200.headers = {
            "x-ratelimit-limit": "1000",
            "x-ratelimit-remaining": "500",
        }
        mock_response_200.elapsed = MagicMock()
        mock_response_200.elapsed.total_seconds = MagicMock(return_value=0.1)

        mock_response_503 = MagicMock(spec=Response)
        mock_response_503.status_code = 503
        mock_response_503.headers = {}
        mock_response_503.elapsed = MagicMock()
        mock_response_503.elapsed.total_seconds = MagicMock(return_value=0.1)

        with patch("autopack.research.discovery.api_availability_checker.httpx") as _:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=[mock_response_200, mock_response_503],
            )
            mock_client.is_closed = False
            checker._client = mock_client

            result = await checker.validate_apis_for_recommendation(
                ["github", "stripe"],
                min_quota_remaining=100,
            )

            assert "valid_apis" in result
            assert "unavailable_apis" in result
            assert "quota_exhausted" in result
            assert "github" in result["valid_apis"]
            assert "stripe" in result["unavailable_apis"]
            assert result["recommendation"] == "proceed"

    @pytest.mark.asyncio
    async def test_validate_apis_quota_exhausted(self, checker):
        """Test validation when quota is exhausted."""
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {
            "x-ratelimit-limit": "1000",
            "x-ratelimit-remaining": "10",
        }
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds = MagicMock(return_value=0.1)

        with patch("autopack.research.discovery.api_availability_checker.httpx") as _:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.is_closed = False
            checker._client = mock_client

            result = await checker.validate_apis_for_recommendation(
                ["github"],
                min_quota_remaining=100,
            )

            assert len(result["quota_exhausted"]) == 1
            assert result["quota_exhausted"][0]["api"] == "github"
            assert result["quota_exhausted"][0]["remaining"] == 10

    @pytest.mark.asyncio
    async def test_check_with_api_tokens(self, checker_with_tokens):
        """Test checking API with authentication headers."""
        mock_response = MagicMock(spec=Response)
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.elapsed = MagicMock()
        mock_response.elapsed.total_seconds = MagicMock(return_value=0.1)

        with patch("autopack.research.discovery.api_availability_checker.httpx") as _:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.is_closed = False
            checker_with_tokens._client = mock_client

            result = await checker_with_tokens.check_availability("openai")

            assert result.is_available is True
            # Verify that Authorization header was included
            call_args = mock_client.get.call_args
            assert call_args is not None
            headers = call_args.kwargs.get("headers", {})
            assert "Authorization" in headers
            assert "Bearer sk-test-token" in headers["Authorization"]

    @pytest.mark.asyncio
    async def test_close_client(self, checker):
        """Test closing the HTTP client."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        checker._client = mock_client

        await checker.close()

        mock_client.aclose.assert_called_once()

    def test_api_endpoints_configuration(self, checker):
        """Test that API endpoints are properly configured."""
        assert "github" in checker.API_ENDPOINTS
        assert "openai" in checker.API_ENDPOINTS
        assert "stripe" in checker.API_ENDPOINTS

        github_config = checker.API_ENDPOINTS["github"]
        assert github_config["base_url"] == "https://api.github.com"
        assert github_config["authentication_required"] is False
        assert "quota_header" in github_config
