"""Tests for security headers middleware (IMP-S05).

These tests verify that all security headers are properly set on API responses
to prevent XSS, clickjacking, MIME sniffing, and other client-side attacks.
"""

import os

# Set testing mode before imports
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


class TestSecurityHeaders:
    """Test suite for security headers middleware."""

    def test_security_headers_present_on_health_endpoint(self, client):
        """Verify all security headers are present on health endpoint."""
        response = client.get("/health")

        # All security headers must be present
        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert "Content-Security-Policy" in response.headers
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "Permissions-Policy" in response.headers

    def test_mime_sniffing_prevention(self, client):
        """Verify X-Content-Type-Options prevents MIME sniffing attacks."""
        response = client.get("/health")

        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_clickjacking_prevention(self, client):
        """Verify X-Frame-Options and CSP prevent clickjacking attacks."""
        response = client.get("/health")

        # X-Frame-Options denies framing
        assert response.headers["X-Frame-Options"] == "DENY"

        # CSP also includes frame-ancestors directive
        csp = response.headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp

    def test_xss_protection_headers(self, client):
        """Verify XSS protection headers are set."""
        response = client.get("/health")

        # Legacy XSS protection header for older browsers
        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    def test_csp_comprehensive_policy(self, client):
        """Verify CSP header includes comprehensive protection rules."""
        response = client.get("/health")

        csp = response.headers["Content-Security-Policy"]

        # Check essential CSP directives
        assert "default-src 'self'" in csp
        assert "script-src 'self' 'unsafe-inline'" in csp
        assert "style-src 'self' 'unsafe-inline'" in csp
        assert "img-src 'self' data: https:" in csp
        assert "font-src 'self'" in csp
        assert "connect-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp

    def test_referrer_policy(self, client):
        """Verify Referrer-Policy prevents leaking sensitive URLs."""
        response = client.get("/health")

        # strict-origin-when-cross-origin is a secure default
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_permissions_policy(self, client):
        """Verify Permissions-Policy restricts dangerous APIs."""
        response = client.get("/health")

        permissions_policy = response.headers["Permissions-Policy"]

        # Critical APIs should be disabled
        assert "geolocation=()" in permissions_policy
        assert "microphone=()" in permissions_policy
        assert "camera=()" in permissions_policy

    def test_security_headers_on_root_endpoint(self, client):
        """Verify security headers present on root endpoint."""
        response = client.get("/")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_security_headers_on_non_existent_endpoint(self, client):
        """Verify security headers present even on 404 responses."""
        response = client.get("/nonexistent")

        # Even error responses should have security headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_security_headers_on_post_request(self, client):
        """Verify security headers present on POST requests."""
        # Use a real endpoint that accepts POST
        response = client.post("/api/auth/register", json={"username": "test", "password": "test"})

        # Even on POST, security headers must be present
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_csp_blocks_frame_embedding(self, client):
        """Verify CSP frame-ancestors directive prevents embedding in frames."""
        response = client.get("/health")

        csp = response.headers["Content-Security-Policy"]

        # frame-ancestors 'none' prevents embedding in ANY frame
        assert "frame-ancestors 'none'" in csp

    def test_csp_restricts_script_sources(self, client):
        """Verify CSP script-src restricts where scripts can come from."""
        response = client.get("/health")

        csp = response.headers["Content-Security-Policy"]

        # Scripts can only come from 'self' and 'unsafe-inline'
        # (unsafe-inline is needed for development, can be removed in production)
        assert "script-src 'self' 'unsafe-inline'" in csp

    def test_csp_restricts_connect_sources(self, client):
        """Verify CSP connect-src restricts where API calls can be made."""
        response = client.get("/health")

        csp = response.headers["Content-Security-Policy"]

        # XHR/fetch requests can only connect to 'self'
        # This prevents exfiltration of data to attacker servers
        assert "connect-src 'self'" in csp

    def test_security_headers_on_put_request(self, client):
        """Verify security headers present on PUT requests."""
        # Use a real endpoint that accepts PUT (might return 404 if not found, but headers matter)
        response = client.put("/api/runs/test-id/status", json={"status": "completed"})

        # Even on PUT, security headers must be present
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_security_headers_on_delete_request(self, client):
        """Verify security headers present on DELETE requests."""
        # Use a real endpoint that accepts DELETE
        response = client.delete("/api/runs/test-id")

        # Even on DELETE, security headers must be present
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"


class TestSecurityHeadersIntegration:
    """Integration tests for security headers across different scenarios."""

    def test_security_headers_with_json_response(self, client):
        """Verify security headers present with JSON responses."""
        response = client.get("/health")

        # Verify it's JSON
        assert response.headers["content-type"].lower().startswith("application/json")

        # Verify security headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_all_required_security_headers_present(self, client):
        """Verify all required security headers are present together."""
        required_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options",
            "X-XSS-Protection",
            "Content-Security-Policy",
            "Referrer-Policy",
            "Permissions-Policy",
        ]

        response = client.get("/health")

        for header in required_headers:
            assert header in response.headers, f"Missing security header: {header}"

    def test_security_headers_not_empty(self, client):
        """Verify security header values are not empty."""
        response = client.get("/health")

        headers_to_check = {
            "X-Content-Type-Options": True,
            "X-Frame-Options": True,
            "X-XSS-Protection": True,
            "Content-Security-Policy": True,
            "Referrer-Policy": True,
            "Permissions-Policy": True,
        }

        for header, should_have_value in headers_to_check.items():
            value = response.headers.get(header, "")
            if should_have_value:
                assert value, f"Security header {header} should not be empty"
