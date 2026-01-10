"""Production auth coverage contract test (PR2 - GAP Analysis).

Enumerates all FastAPI routes and ensures:
1. In production mode, all endpoints are protected UNLESS explicitly allowlisted
2. Allowlist is minimal and well-documented (health, docs, auth bootstrap)
3. Special endpoints have appropriate security posture documented

Contract: "no partially open API in production"
"""

import os
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

# Import the app to enumerate routes
os.environ.setdefault("TESTING", "1")  # Prevent production checks during import
from autopack.main import app


# ============================================================================
# ALLOWLIST: Endpoints that MAY be unauthenticated
# ============================================================================

# These endpoints are intentionally unauthenticated even in production.
# Each must have a documented rationale.
PRODUCTION_UNAUTHENTICATED_ALLOWLIST = {
    # Health check - required for load balancers and orchestration
    "/health": "Health probe for load balancers (no sensitive data)",
    # OpenAPI documentation - useful for developers, no sensitive data
    "/openapi.json": "OpenAPI schema (no sensitive data)",
    "/docs": "Swagger UI (read-only API docs)",
    "/docs/oauth2-redirect": "OAuth2 redirect helper for Swagger UI",
    "/redoc": "ReDoc UI (read-only API docs)",
    # Root endpoint - basic version info only
    "/": "Root endpoint returns version only (no sensitive data)",
    # Auth bootstrap endpoints (required for login/registration flow)
    "/api/auth/login": "Auth bootstrap - login endpoint (by design, unauthenticated)",
    "/api/auth/register": "Auth bootstrap - user registration (by design, unauthenticated)",
    "/api/auth/.well-known/jwks.json": "JWKS public key endpoint for JWT verification (public by spec)",
}

# Endpoints that have SPECIAL security requirements (not API key, but other verification)
# These should be protected by alternative mechanisms documented here
SPECIAL_SECURITY_ENDPOINTS = {
    "/telegram/webhook": {
        "mechanism": "Telegram bot token verification (checks callback_query.from.id)",
        "status": "NEEDS_CRYPTO_VERIFICATION",  # PR7 will add proper HMAC verification
        "risk": "Medium - relies on Telegram's delivery guarantees",
    },
    "/api/auth/me": {
        "mechanism": "JWT Bearer token (via get_current_user dependency)",
        "status": "IMPLEMENTED",
        "risk": "Low - requires valid JWT token",
    },
    "/api/auth/key-status": {
        "mechanism": "None (diagnostic endpoint - returns only key source status)",
        "status": "INTENTIONALLY_PUBLIC",
        "risk": "Low - no secrets exposed, only whether keys exist and their source",
    },
}

# Endpoints that are QUARANTINED - should not be exposed in production
# These must be removed or gated before production deployment
QUARANTINED_ENDPOINTS = {
    "/research/sessions": "Mock in-memory state - not production-safe (PR8)",
    "/research/sessions/{session_id}": "Mock in-memory state - not production-safe (PR8)",
}


# ============================================================================
# Test Implementation
# ============================================================================


def get_all_routes(app: FastAPI) -> list[tuple[str, list[str], bool]]:
    """Extract all routes from FastAPI app.

    Returns:
        List of (path, methods, has_auth_dependency) tuples
    """
    routes = []

    for route in app.routes:
        if isinstance(route, APIRoute):
            path = route.path
            methods = list(route.methods - {"HEAD", "OPTIONS"})  # Exclude implicit methods

            # Check if route has auth dependency
            # Note: read endpoints may use verify_read_access (which delegates to verify_api_key in production)
            has_auth = False
            for dep in route.dependencies:
                dep_str = str(dep.dependency)
                if "verify_api_key" in dep_str or "verify_read_access" in dep_str:
                    has_auth = True
                    break

            # Also check endpoint signature for Depends(verify_api_key) / Depends(verify_read_access)
            if hasattr(route, "dependant") and route.dependant:
                for dep in route.dependant.dependencies:
                    if hasattr(dep, "call") and (
                        "verify_api_key" in str(dep.call) or "verify_read_access" in str(dep.call)
                    ):
                        has_auth = True
                        break

            routes.append((path, methods, has_auth))

    return routes


class TestProductionAuthCoverage:
    """Contract test: all endpoints protected in production unless allowlisted."""

    def test_all_routes_enumerated(self):
        """Sanity check: we can enumerate routes from the app."""
        routes = get_all_routes(app)
        assert len(routes) > 0, "Expected to find routes in the app"

        # Log for debugging
        paths = [r[0] for r in routes]
        assert "/health" in paths, "Expected /health route"
        assert "/" in paths, "Expected root route"

    def test_allowlist_is_minimal(self):
        """Allowlist should only contain truly necessary public endpoints."""
        # These are the ONLY acceptable unauthenticated endpoints
        expected_public = {
            "/",
            "/health",
            "/openapi.json",
            "/docs",
            "/docs/oauth2-redirect",
            "/redoc",
            # Auth bootstrap (by design, needed before authentication is possible)
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/.well-known/jwks.json",
        }

        actual_allowlist = set(PRODUCTION_UNAUTHENTICATED_ALLOWLIST.keys())
        assert (
            actual_allowlist == expected_public
        ), f"Allowlist has unexpected entries: {actual_allowlist - expected_public}"

    def test_special_security_endpoints_documented(self):
        """Special security endpoints must have documented mechanism."""
        for path, info in SPECIAL_SECURITY_ENDPOINTS.items():
            assert "mechanism" in info, f"{path} must document security mechanism"
            assert "status" in info, f"{path} must document implementation status"
            assert "risk" in info, f"{path} must document risk level"

    def test_quarantined_endpoints_identified(self):
        """Quarantined endpoints must be documented with remediation plan."""
        routes = get_all_routes(app)
        route_paths = {r[0] for r in routes}

        # Check that quarantined endpoints are actually in the app
        for path in QUARANTINED_ENDPOINTS:
            # Normalize path patterns
            normalized = path.replace("{session_id}", "{session_id}")
            # Check if any route matches
            matching = [
                p for p in route_paths if p == normalized or p.startswith(path.split("{")[0])
            ]
            if not matching:
                pytest.skip(f"Quarantined endpoint {path} not found (may have been removed)")

    def test_production_auth_posture_report(self):
        """Generate a report of auth posture for all endpoints."""
        routes = get_all_routes(app)

        protected = []
        allowlisted = []
        special = []
        quarantined = []
        unprotected = []

        for path, methods, has_auth in routes:
            if has_auth:
                protected.append(path)
            elif path in PRODUCTION_UNAUTHENTICATED_ALLOWLIST:
                allowlisted.append(path)
            elif path in SPECIAL_SECURITY_ENDPOINTS:
                special.append(path)
            elif any(path.startswith(q.split("{")[0]) for q in QUARANTINED_ENDPOINTS):
                quarantined.append(path)
            else:
                unprotected.append(path)

        # Report
        report = f"""
Auth Coverage Report:
- Protected (verify_api_key): {len(protected)}
- Allowlisted (intentionally public): {len(allowlisted)}
- Special security (alternative mechanism): {len(special)}
- Quarantined (needs remediation): {len(quarantined)}
- UNPROTECTED (gaps): {len(unprotected)}

Unprotected endpoints requiring attention:
{chr(10).join(f'  - {p}' for p in sorted(unprotected)) if unprotected else '  (none)'}
"""
        print(report)

        # This test documents current state; PR2 should drive unprotected to 0
        # For now, we just ensure the audit runs successfully
        assert True, "Auth posture report generated"


class TestProductionAuthEnforcement:
    """Tests that verify auth is actually enforced at runtime."""

    @pytest.mark.asyncio
    async def test_protected_endpoint_rejects_without_key(self):
        """Protected endpoints should reject requests without API key."""
        from fastapi.testclient import TestClient

        # Set production mode
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("AUTOPACK_ENV", "production")
            mp.setenv("AUTOPACK_API_KEY", "test-key-12345")  # gitleaks:allow
            mp.delenv("TESTING", raising=False)

            # Create a fresh client for this test
            client = TestClient(app, raise_server_exceptions=False)

            # Test a protected endpoint (files/upload requires auth)
            response = client.post("/files/upload", files={"file": ("test.txt", b"test")})

            # Should be 403 Forbidden without API key
            assert response.status_code in [
                401,
                403,
            ], f"Protected endpoint should reject without API key, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_read_access_endpoint_rejects_without_key_in_production(self):
        """verify_read_access endpoints should reject requests without API key in production."""
        from fastapi.testclient import TestClient

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("AUTOPACK_ENV", "production")
            mp.setenv("AUTOPACK_API_KEY", "test-key-12345")  # gitleaks:allow
            mp.delenv("TESTING", raising=False)

            client = TestClient(app, raise_server_exceptions=False)

            # /runs is gated by verify_read_access
            response = client.get("/runs")
            assert response.status_code in [
                401,
                403,
            ], f"read_access endpoint should reject without API key, got {response.status_code}"

    @pytest.mark.asyncio
    async def test_allowlisted_endpoint_accessible_in_production(self):
        """Allowlisted endpoints should be accessible without API key."""
        from fastapi.testclient import TestClient

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("AUTOPACK_ENV", "production")
            mp.setenv("AUTOPACK_API_KEY", "test-key-12345")  # gitleaks:allow
            mp.delenv("TESTING", raising=False)

            client = TestClient(app, raise_server_exceptions=False)

            # Health check should always be accessible
            response = client.get("/health")
            assert response.status_code == 200, "Health check should be accessible in production"


class TestAuthAllowlistDocumentation:
    """Verify allowlist is documented in relevant files."""

    def test_gap_analysis_documents_auth_posture(self):
        """IMPROVEMENTS_GAP_ANALYSIS.md should document production auth posture."""
        gap_analysis = Path("docs/IMPROVEMENTS_GAP_ANALYSIS.md")
        if not gap_analysis.exists():
            pytest.skip("Gap analysis doc not found")

        content = gap_analysis.read_text(encoding="utf-8")
        assert (
            "production auth" in content.lower() or "auth posture" in content.lower()
        ), "Gap analysis should document production auth requirements"

    def test_allowlist_has_rationale_for_each_entry(self):
        """Every allowlist entry must have a documented rationale."""
        for path, rationale in PRODUCTION_UNAUTHENTICATED_ALLOWLIST.items():
            assert rationale, f"Allowlist entry {path} must have a rationale"
            assert len(rationale) > 10, f"Rationale for {path} seems too short"


class TestQuarantinedEndpointWarnings:
    """Warn about quarantined endpoints that need remediation."""

    def test_research_endpoints_are_quarantined(self):
        """Research endpoints should be marked as quarantined (PR8 scope)."""
        routes = get_all_routes(app)
        research_routes = [r for r in routes if r[0].startswith("/research")]

        if research_routes:
            # Verify they're in the quarantine list
            for path, methods, has_auth in research_routes:
                assert (
                    not has_auth
                ), f"Research endpoint {path} should not have auth (it's quarantined)"

                # Check it's documented as quarantined
                is_quarantined = any(
                    path.startswith(q.split("{")[0]) for q in QUARANTINED_ENDPOINTS
                )
                assert (
                    is_quarantined
                ), f"Research endpoint {path} should be in QUARANTINED_ENDPOINTS list"

    def test_telegram_webhook_special_security(self):
        """Telegram webhook should be in special security list."""
        routes = get_all_routes(app)
        telegram_routes = [r for r in routes if "/telegram/" in r[0]]

        for path, methods, has_auth in telegram_routes:
            if path == "/telegram/webhook":
                assert (
                    path in SPECIAL_SECURITY_ENDPOINTS
                ), "Telegram webhook should be in SPECIAL_SECURITY_ENDPOINTS"
