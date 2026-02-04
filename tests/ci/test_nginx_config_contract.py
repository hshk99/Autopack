"""
Tests for nginx configuration contract (PR-02 G6).

BUILD-197: Ensures nginx.conf maintains routing invariants for:
- /api/auth/* routes preserve prefix (auth router mounted at /api/auth)
- /api/* routes strip prefix (general API routes)
- /health proxies to backend (full readiness check)
- /nginx-health is static liveness probe
"""

import os
import re

import pytest


class TestNginxConfigContract:
    """PR-02 G6: Verify nginx.conf routing invariants."""

    @pytest.fixture
    def nginx_config(self) -> str:
        """Load nginx.conf content."""
        config_path = "nginx.conf"
        if not os.path.exists(config_path):
            pytest.skip("nginx.conf not found in project root")

        with open(config_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_auth_location_preserves_prefix(self, nginx_config: str):
        """Auth routes must preserve /api/auth prefix (no trailing slash on proxy_pass)."""
        # Find the /api/auth/ location block
        auth_location_pattern = r"location\s+/api/auth/\s*\{[^}]*\}"
        auth_match = re.search(auth_location_pattern, nginx_config, re.DOTALL)

        assert auth_match, (
            "nginx.conf must have a 'location /api/auth/' block. "
            "The auth router is mounted at /api/auth in the backend."
        )

        auth_block = auth_match.group(0)

        # Verify proxy_pass does NOT have trailing slash (preserves path)
        # Valid: proxy_pass http://backend:8000;
        # Invalid: proxy_pass http://backend:8000/;
        proxy_pass_pattern = r"proxy_pass\s+http://[^;]+;"
        proxy_match = re.search(proxy_pass_pattern, auth_block)

        assert proxy_match, "Auth location must have a proxy_pass directive"

        proxy_pass = proxy_match.group(0)
        # Check it doesn't end with /; (trailing slash before semicolon)
        assert not proxy_pass.rstrip(";").endswith("/"), (
            f"Auth proxy_pass must NOT have trailing slash to preserve /api/auth prefix. "
            f"Found: {proxy_pass}. "
            f"Should be: proxy_pass http://backend:8000; (no trailing slash)"
        )

    def test_api_location_strips_prefix(self, nginx_config: str):
        """General /api/ routes should strip prefix (trailing slash on proxy_pass)."""
        # Find the /api/ location block (but not /api/auth/)
        # This is trickier - we need to find /api/ but exclude /api/auth/
        api_location_pattern = r"location\s+/api/\s*\{[^}]*\}"
        api_matches = re.findall(api_location_pattern, nginx_config, re.DOTALL)

        # Filter out the auth location if it was matched
        general_api_blocks = [block for block in api_matches if "location /api/auth/" not in block]

        assert general_api_blocks, (
            "nginx.conf must have a general 'location /api/' block for non-auth routes"
        )

        api_block = general_api_blocks[0]

        # Verify proxy_pass HAS trailing slash (strips /api prefix)
        proxy_pass_pattern = r"proxy_pass\s+http://[^;]+;"
        proxy_match = re.search(proxy_pass_pattern, api_block)

        assert proxy_match, "API location must have a proxy_pass directive"

        proxy_pass = proxy_match.group(0)
        # Check it ends with /; (trailing slash before semicolon)
        assert proxy_pass.rstrip(";").endswith("/"), (
            f"API proxy_pass must have trailing slash to strip /api prefix. "
            f"Found: {proxy_pass}. "
            f"Should be: proxy_pass http://backend:8000/; (with trailing slash)"
        )

    def test_health_endpoint_proxied(self, nginx_config: str):
        """Health endpoint should proxy to backend for full readiness check."""
        # Find exact /health location
        health_pattern = r"location\s*=\s*/health\s*\{[^}]*\}"
        health_match = re.search(health_pattern, nginx_config, re.DOTALL)

        assert health_match, (
            "nginx.conf must have a 'location = /health' block that proxies to backend. "
            "This provides full readiness checks (DB, Qdrant, kill switches)."
        )

        health_block = health_match.group(0)

        # Verify it proxies to backend /health
        assert "proxy_pass" in health_block, (
            "/health must proxy to backend, not return static content"
        )
        assert "/health" in health_block, (
            "/health proxy_pass should target backend /health endpoint"
        )

    def test_nginx_health_is_static(self, nginx_config: str):
        """nginx-health should be a static liveness probe."""
        # Find /nginx-health location
        nginx_health_pattern = r"location\s*=\s*/nginx-health\s*\{[^}]*\}"
        nginx_health_match = re.search(nginx_health_pattern, nginx_config, re.DOTALL)

        assert nginx_health_match, (
            "nginx.conf must have a 'location = /nginx-health' block for liveness probes. "
            "This allows container orchestrators to check nginx is running without "
            "depending on backend availability."
        )

        nginx_health_block = nginx_health_match.group(0)

        # Verify it returns static content (return directive, not proxy_pass)
        assert "return 200" in nginx_health_block, (
            "/nginx-health must return static 200 response, not proxy to backend"
        )
        assert "proxy_pass" not in nginx_health_block, (
            "/nginx-health must NOT proxy - it's a static liveness check"
        )

    def test_auth_location_before_api_location(self, nginx_config: str):
        """Auth location should be defined to take precedence over general /api/."""
        # nginx uses longest prefix matching, so /api/auth/ matches before /api/
        # regardless of order in config. But we verify both exist.

        auth_pos = nginx_config.find("location /api/auth/")
        api_pos = nginx_config.find("location /api/")

        assert auth_pos != -1, "Must have /api/auth/ location"
        assert api_pos != -1, "Must have /api/ location"

        # Note: In nginx, /api/auth/ will match before /api/ due to longest-prefix
        # matching, regardless of config order. This test just documents the expectation.


class TestNginxConfigSecurity:
    """Security hardening checks for nginx configuration."""

    @pytest.fixture
    def nginx_config(self) -> str:
        """Load nginx.conf content."""
        config_path = "nginx.conf"
        if not os.path.exists(config_path):
            pytest.skip("nginx.conf not found in project root")

        with open(config_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_security_headers_present(self, nginx_config: str):
        """Verify security headers are configured."""
        required_headers = [
            "X-Frame-Options",
            "X-Content-Type-Options",
            "X-XSS-Protection",
            "Content-Security-Policy",
            "Strict-Transport-Security",
        ]

        for header in required_headers:
            assert header in nginx_config, (
                f"Security header {header} must be configured in nginx.conf"
            )

    def test_client_max_body_size_configured(self, nginx_config: str):
        """Verify request size limits are configured."""
        assert "client_max_body_size" in nginx_config, (
            "client_max_body_size must be configured to prevent resource exhaustion"
        )

    def test_request_id_propagation(self, nginx_config: str):
        """Verify X-Request-ID header propagation for tracing."""
        assert "X-Request-ID" in nginx_config, (
            "X-Request-ID header propagation must be configured for distributed tracing"
        )


class TestNginxRoutingDocumentation:
    """Verify routing invariants are documented."""

    def test_deployment_docs_have_routing_section(self):
        """DEPLOYMENT.md should document reverse proxy routing invariants."""
        docs_path = "docs/DEPLOYMENT.md"

        if not os.path.exists(docs_path):
            pytest.skip("DEPLOYMENT.md not found")

        with open(docs_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "Reverse Proxy Routing" in content, (
            "DEPLOYMENT.md must document reverse proxy routing invariants"
        )
        assert "/api/auth" in content, "DEPLOYMENT.md must document /api/auth prefix preservation"
        assert "/nginx-health" in content, (
            "DEPLOYMENT.md must document /nginx-health liveness endpoint"
        )
