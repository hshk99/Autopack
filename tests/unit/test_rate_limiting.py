"""Tests for rate limiting client IP extraction (PR-06).

Validates:
- X-Forwarded-For header is used when present (from trusted proxy)
- X-Real-IP header is used as fallback (from trusted proxy)
- Direct connection fallback works
- Untrusted proxies cannot spoof X-Forwarded-For
"""

from unittest.mock import MagicMock

import pytest

from autopack.main import get_client_ip, _is_trusted_proxy


class TestIsTrustedProxy:
    """Test trusted proxy detection logic."""

    @pytest.mark.parametrize(
        "ip,expected",
        [
            # Localhost
            ("127.0.0.1", True),
            ("::1", True),
            # Docker bridge network (172.16-31.x.x)
            ("172.17.0.1", True),
            ("172.18.0.2", True),
            ("172.31.255.254", True),
            # Outside Docker bridge range
            ("172.15.0.1", False),
            ("172.32.0.1", False),
            # Public IPs
            ("8.8.8.8", False),
            ("203.0.113.50", False),
            # None
            (None, False),
        ],
    )
    def test_is_trusted_proxy(self, ip, expected: bool) -> None:
        """Test trusted proxy detection with various IPs."""
        assert _is_trusted_proxy(ip) is expected

    def test_localhost_ipv4_trusted(self):
        """127.0.0.1 is trusted by default."""
        assert _is_trusted_proxy("127.0.0.1") is True

    def test_localhost_ipv6_trusted(self):
        """::1 is trusted by default."""
        assert _is_trusted_proxy("::1") is True

    def test_docker_bridge_trusted(self):
        """Docker bridge network (172.16-31.x.x) is trusted."""
        assert _is_trusted_proxy("172.17.0.1") is True
        assert _is_trusted_proxy("172.18.0.2") is True
        assert _is_trusted_proxy("172.31.255.254") is True

    def test_outside_docker_bridge_not_trusted(self):
        """IPs outside Docker bridge range are not trusted."""
        assert _is_trusted_proxy("172.15.0.1") is False
        assert _is_trusted_proxy("172.32.0.1") is False

    def test_public_ip_not_trusted(self):
        """Public IPs are not trusted by default."""
        assert _is_trusted_proxy("8.8.8.8") is False
        assert _is_trusted_proxy("203.0.113.50") is False

    def test_none_not_trusted(self):
        """None client IP is not trusted."""
        assert _is_trusted_proxy(None) is False


class TestGetClientIp:
    """Test get_client_ip function for proxy-aware IP extraction."""

    def _make_request(
        self,
        x_forwarded_for: str | None = None,
        x_real_ip: str | None = None,
        client_host: str | None = None,
    ) -> MagicMock:
        """Create a mock Request with specified headers and client."""
        request = MagicMock()

        headers = {}
        if x_forwarded_for is not None:
            headers["x-forwarded-for"] = x_forwarded_for
        if x_real_ip is not None:
            headers["x-real-ip"] = x_real_ip

        request.headers.get = lambda key, default=None: headers.get(key, default)

        if client_host is not None:
            request.client = MagicMock()
            request.client.host = client_host
        else:
            request.client = None

        return request

    # Tests with trusted proxy (localhost)
    def test_x_forwarded_for_from_localhost(self):
        """X-Forwarded-For from localhost should be trusted."""
        request = self._make_request(
            x_forwarded_for="192.168.1.100",
            client_host="127.0.0.1",
        )
        assert get_client_ip(request) == "192.168.1.100"

    def test_x_forwarded_for_chain_from_trusted(self):
        """X-Forwarded-For chain from trusted proxy returns first IP."""
        request = self._make_request(
            x_forwarded_for="10.0.0.5, 172.16.0.1, 192.168.1.1",
            client_host="127.0.0.1",
        )
        assert get_client_ip(request) == "10.0.0.5"

    def test_x_real_ip_from_docker_bridge(self):
        """X-Real-IP from Docker bridge should be trusted."""
        request = self._make_request(
            x_real_ip="203.0.113.50",
            client_host="172.17.0.2",
        )
        assert get_client_ip(request) == "203.0.113.50"

    # Tests with untrusted proxy (security - spoofing prevention)
    def test_x_forwarded_for_from_untrusted_ignored(self):
        """X-Forwarded-For from untrusted source should be IGNORED."""
        request = self._make_request(
            x_forwarded_for="10.0.0.5",  # Attacker trying to spoof
            client_host="203.0.113.99",  # Untrusted public IP
        )
        # Should return direct IP, not spoofed X-Forwarded-For
        assert get_client_ip(request) == "203.0.113.99"

    def test_x_real_ip_from_untrusted_ignored(self):
        """X-Real-IP from untrusted source should be IGNORED."""
        request = self._make_request(
            x_real_ip="10.0.0.5",  # Attacker trying to spoof
            client_host="8.8.8.8",  # Untrusted public IP
        )
        assert get_client_ip(request) == "8.8.8.8"

    # Direct connection tests
    def test_direct_connection_no_headers(self):
        """Direct connection without headers returns client IP."""
        request = self._make_request(client_host="192.0.2.100")
        assert get_client_ip(request) == "192.0.2.100"

    def test_no_client_returns_localhost(self):
        """When no client info available, should return 127.0.0.1."""
        request = self._make_request()
        assert get_client_ip(request) == "127.0.0.1"

    def test_empty_x_forwarded_for_from_trusted(self):
        """Empty X-Forwarded-For from trusted should fall through to X-Real-IP."""
        request = self._make_request(
            x_forwarded_for="",
            x_real_ip="10.0.0.5",
            client_host="127.0.0.1",
        )
        assert get_client_ip(request) == "10.0.0.5"
