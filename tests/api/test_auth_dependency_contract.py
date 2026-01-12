"""
Contract tests for API authentication dependencies.

PR-API-1: These tests define the behavioral contract for auth functions
extracted from main.py to api/deps.py.

Contract guarantees:
1. TESTING mode bypass: verify_api_key returns 'test-key' when TESTING=1
2. Production mode requires API key: verify_api_key raises 403 without key
3. Dev mode optional: verify_api_key skips if no AUTOPACK_API_KEY configured
4. Trusted proxy logic: get_client_ip only trusts forwarded headers from trusted IPs

These tests prevent auth behavior drift during refactoring.
"""

import os
import pytest
from unittest.mock import MagicMock, patch


# Set testing mode before imports
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


class TestVerifyApiKeyContract:
    """Contract tests for verify_api_key behavior."""

    @pytest.mark.asyncio
    async def test_testing_mode_bypasses_auth(self):
        """Contract: TESTING=1 returns 'test-key' without checking credentials."""
        from autopack.api.deps import verify_api_key

        # Save and remove PYTEST_CURRENT_TEST to ensure TESTING=1 path is used
        saved_pct = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with patch.dict(os.environ, {"TESTING": "1"}, clear=False):
                result = await verify_api_key(None)
                assert result == "test-key"

                # Even with wrong key, should return test-key
                result = await verify_api_key("wrong-key")
                assert result == "test-key"
        finally:
            if saved_pct:
                os.environ["PYTEST_CURRENT_TEST"] = saved_pct

    @pytest.mark.asyncio
    async def test_pytest_current_test_bypasses_auth_in_non_production(self):
        """Contract: PYTEST_CURRENT_TEST set in non-production bypasses auth."""
        from autopack.api.deps import verify_api_key

        with patch.dict(
            os.environ,
            {
                "TESTING": "",
                "AUTOPACK_ENV": "development",
                "PYTEST_CURRENT_TEST": "tests/api/test_foo.py::test_bar",
            },
            clear=False,
        ):
            result = await verify_api_key(None)
            assert result == "test-key"

    @pytest.mark.asyncio
    async def test_production_requires_api_key_configured(self):
        """Contract: Production mode with no key configured raises error.

        Note: get_api_key() in config.py raises RuntimeError for missing key in production,
        which is then handled. The test verifies this behavior via RuntimeError.
        """
        from autopack.api.deps import verify_api_key

        # Clear PYTEST_CURRENT_TEST to disable test bypass
        saved_pct = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with patch.dict(
                os.environ,
                {"TESTING": "", "AUTOPACK_ENV": "production", "AUTOPACK_API_KEY": ""},
                clear=False,
            ):
                # get_api_key() raises RuntimeError when key required but missing
                with pytest.raises(RuntimeError) as exc_info:
                    await verify_api_key("some-key")
                assert "required in production" in str(exc_info.value)
        finally:
            if saved_pct:
                os.environ["PYTEST_CURRENT_TEST"] = saved_pct

    @pytest.mark.asyncio
    async def test_production_rejects_invalid_key(self):
        """Contract: Production mode with configured key rejects wrong key."""
        from autopack.api.deps import verify_api_key
        from fastapi import HTTPException

        # Clear PYTEST_CURRENT_TEST to disable test bypass
        saved_pct = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with patch.dict(
                os.environ,
                {
                    "TESTING": "",
                    "AUTOPACK_ENV": "production",
                    "AUTOPACK_API_KEY": "correct-key",
                },
                clear=False,
            ):
                with pytest.raises(HTTPException) as exc_info:
                    await verify_api_key("wrong-key")

                assert exc_info.value.status_code == 403
                assert "Invalid or missing" in exc_info.value.detail
        finally:
            if saved_pct:
                os.environ["PYTEST_CURRENT_TEST"] = saved_pct

    @pytest.mark.asyncio
    async def test_production_accepts_correct_key(self):
        """Contract: Production mode accepts correct API key."""
        from autopack.api.deps import verify_api_key

        # Clear PYTEST_CURRENT_TEST to disable test bypass
        saved_pct = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with patch.dict(
                os.environ,
                {
                    "TESTING": "",
                    "AUTOPACK_ENV": "production",
                    "AUTOPACK_API_KEY": "correct-key",
                },
                clear=False,
            ):
                result = await verify_api_key("correct-key")
                assert result == "correct-key"
        finally:
            if saved_pct:
                os.environ["PYTEST_CURRENT_TEST"] = saved_pct

    @pytest.mark.asyncio
    async def test_dev_mode_skips_if_no_key_configured(self):
        """Contract: Dev mode without AUTOPACK_API_KEY skips auth."""
        from autopack.api.deps import verify_api_key

        # Clear PYTEST_CURRENT_TEST to disable test bypass
        saved_pct = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with patch.dict(
                os.environ,
                {"TESTING": "", "AUTOPACK_ENV": "development", "AUTOPACK_API_KEY": ""},
                clear=False,
            ):
                result = await verify_api_key(None)
                assert result is None
        finally:
            if saved_pct:
                os.environ["PYTEST_CURRENT_TEST"] = saved_pct

    @pytest.mark.asyncio
    async def test_dev_mode_validates_if_key_configured(self):
        """Contract: Dev mode with AUTOPACK_API_KEY validates it."""
        from autopack.api.deps import verify_api_key
        from fastapi import HTTPException

        # Clear PYTEST_CURRENT_TEST to disable test bypass
        saved_pct = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with patch.dict(
                os.environ,
                {
                    "TESTING": "",
                    "AUTOPACK_ENV": "development",
                    "AUTOPACK_API_KEY": "dev-key",
                },
                clear=False,
            ):
                # Wrong key should raise
                with pytest.raises(HTTPException) as exc_info:
                    await verify_api_key("wrong-key")
                assert exc_info.value.status_code == 403

                # Correct key should pass
                result = await verify_api_key("dev-key")
                assert result == "dev-key"
        finally:
            if saved_pct:
                os.environ["PYTEST_CURRENT_TEST"] = saved_pct


class TestVerifyReadAccessContract:
    """Contract tests for verify_read_access behavior."""

    @pytest.mark.asyncio
    async def test_testing_mode_bypasses_auth(self):
        """Contract: TESTING=1 returns 'test-key' for read access."""
        from autopack.api.deps import verify_read_access

        # Save and remove PYTEST_CURRENT_TEST to ensure TESTING=1 path is used
        saved_pct = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with patch.dict(os.environ, {"TESTING": "1"}, clear=False):
                result = await verify_read_access(None)
                assert result == "test-key"
        finally:
            if saved_pct:
                os.environ["PYTEST_CURRENT_TEST"] = saved_pct

    @pytest.mark.asyncio
    async def test_dev_mode_public_read_allows_access(self):
        """Contract: AUTOPACK_PUBLIC_READ=1 in dev mode allows unauthenticated read."""
        from autopack.api.deps import verify_read_access

        # Clear PYTEST_CURRENT_TEST to disable test bypass
        saved_pct = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with patch.dict(
                os.environ,
                {
                    "TESTING": "",
                    "AUTOPACK_ENV": "development",
                    "AUTOPACK_PUBLIC_READ": "1",
                },
                clear=False,
            ):
                result = await verify_read_access(None)
                assert result is None  # Public access
        finally:
            if saved_pct:
                os.environ["PYTEST_CURRENT_TEST"] = saved_pct

    @pytest.mark.asyncio
    async def test_production_requires_auth_even_with_public_read(self):
        """Contract: Production ignores AUTOPACK_PUBLIC_READ.

        Note: get_api_key() raises RuntimeError when key is required but not set.
        """
        from autopack.api.deps import verify_read_access

        # Clear PYTEST_CURRENT_TEST to disable test bypass
        saved_pct = os.environ.pop("PYTEST_CURRENT_TEST", None)
        try:
            with patch.dict(
                os.environ,
                {
                    "TESTING": "",
                    "AUTOPACK_ENV": "production",
                    "AUTOPACK_PUBLIC_READ": "1",
                    "AUTOPACK_API_KEY": "",  # No key configured
                },
                clear=False,
            ):
                # get_api_key() raises RuntimeError when key required but missing
                with pytest.raises(RuntimeError) as exc_info:
                    await verify_read_access(None)
                assert "required in production" in str(exc_info.value)
        finally:
            if saved_pct:
                os.environ["PYTEST_CURRENT_TEST"] = saved_pct


class TestGetClientIpContract:
    """Contract tests for get_client_ip trusted proxy behavior."""

    def _make_mock_request(
        self, client_ip: str, forwarded_for: str = None, real_ip: str = None
    ) -> MagicMock:
        """Create a mock Request with specified IP and headers."""
        request = MagicMock()
        request.client = MagicMock()
        request.client.host = client_ip
        headers = {}
        if forwarded_for:
            headers["x-forwarded-for"] = forwarded_for
        if real_ip:
            headers["x-real-ip"] = real_ip
        request.headers = headers
        return request

    def test_localhost_is_trusted_proxy(self):
        """Contract: 127.0.0.1 is trusted by default."""
        from autopack.api.deps import get_client_ip

        with patch.dict(os.environ, {"AUTOPACK_TRUSTED_PROXIES": ""}):
            request = self._make_mock_request(
                client_ip="127.0.0.1", forwarded_for="203.0.113.50, 10.0.0.1"
            )
            result = get_client_ip(request)
            # Should trust X-Forwarded-For and return first IP
            assert result == "203.0.113.50"

    def test_ipv6_localhost_is_trusted_proxy(self):
        """Contract: ::1 (IPv6 localhost) is trusted by default."""
        from autopack.api.deps import get_client_ip

        with patch.dict(os.environ, {"AUTOPACK_TRUSTED_PROXIES": ""}):
            request = self._make_mock_request(client_ip="::1", forwarded_for="192.168.1.100")
            result = get_client_ip(request)
            assert result == "192.168.1.100"

    def test_docker_bridge_is_trusted_proxy(self):
        """Contract: Docker bridge network (172.16-31.x.x) is trusted."""
        from autopack.api.deps import get_client_ip

        with patch.dict(os.environ, {"AUTOPACK_TRUSTED_PROXIES": ""}):
            request = self._make_mock_request(client_ip="172.18.0.1", forwarded_for="8.8.8.8")
            result = get_client_ip(request)
            assert result == "8.8.8.8"

    def test_untrusted_proxy_ignores_forwarded_headers(self):
        """Contract: Untrusted direct IP ignores X-Forwarded-For (spoofing defense)."""
        from autopack.api.deps import get_client_ip

        with patch.dict(os.environ, {"AUTOPACK_TRUSTED_PROXIES": ""}):
            # 8.8.8.8 is not a trusted proxy
            request = self._make_mock_request(
                client_ip="8.8.8.8", forwarded_for="192.168.1.1, 10.0.0.1"
            )
            result = get_client_ip(request)
            # Should ignore X-Forwarded-For and return direct IP
            assert result == "8.8.8.8"

    def test_custom_trusted_proxies_via_env(self):
        """Contract: AUTOPACK_TRUSTED_PROXIES adds custom trusted IPs."""
        from autopack.api.deps import get_client_ip

        with patch.dict(os.environ, {"AUTOPACK_TRUSTED_PROXIES": "10.0.0.1, 10.0.0.2"}):
            request = self._make_mock_request(client_ip="10.0.0.1", forwarded_for="203.0.113.99")
            result = get_client_ip(request)
            assert result == "203.0.113.99"

    def test_real_ip_header_fallback(self):
        """Contract: X-Real-IP is used when X-Forwarded-For absent."""
        from autopack.api.deps import get_client_ip

        with patch.dict(os.environ, {"AUTOPACK_TRUSTED_PROXIES": ""}):
            request = self._make_mock_request(client_ip="127.0.0.1", real_ip="192.0.2.50")
            result = get_client_ip(request)
            assert result == "192.0.2.50"

    def test_x_forwarded_for_takes_precedence_over_real_ip(self):
        """Contract: X-Forwarded-For takes precedence over X-Real-IP."""
        from autopack.api.deps import get_client_ip

        with patch.dict(os.environ, {"AUTOPACK_TRUSTED_PROXIES": ""}):
            request = self._make_mock_request(
                client_ip="127.0.0.1", forwarded_for="1.2.3.4", real_ip="5.6.7.8"
            )
            result = get_client_ip(request)
            assert result == "1.2.3.4"

    def test_no_client_returns_localhost(self):
        """Contract: Request with no client returns 127.0.0.1."""
        from autopack.api.deps import get_client_ip

        request = MagicMock()
        request.client = None
        request.headers = {}
        result = get_client_ip(request)
        assert result == "127.0.0.1"


class TestLimiterContract:
    """Contract tests for rate limiter configuration."""

    def test_limiter_uses_get_client_ip(self):
        """Contract: Limiter key_func is get_client_ip."""
        from autopack.api.deps import limiter, get_client_ip

        # The limiter should use our get_client_ip function
        assert limiter._key_func == get_client_ip
