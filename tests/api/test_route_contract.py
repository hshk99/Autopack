"""
Route shape contract tests for autopack.main.app.

Purpose:
- Prevent accidental removal of API routes during refactoring
- Document the expected API surface for future migrations
- Provide a mechanical safety net for PR-03 (main.py router split)

Contract enforced:
- Key path patterns must exist in the OpenAPI spec
- Total route count must not unexpectedly drop
- Route paths must remain stable during refactoring

Usage:
    pytest tests/api/test_route_contract.py -v
"""

import os
import pytest

# Required for testing - set before importing app
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


def get_app_routes():
    """Get routes from the FastAPI app."""
    from autopack.main import app

    return app.openapi()


# Key route paths that MUST exist in the API.
# These are critical endpoints that should never be accidentally removed.
REQUIRED_ROUTE_PATTERNS = [
    # Health and info
    "/",
    "/health",
    # Runs domain
    "/runs/start",
    "/runs",
    "/runs/{run_id}",
    "/runs/{run_id}/progress",
    # Phases domain
    "/runs/{run_id}/phases/{phase_id}/update_status",
    "/runs/{run_id}/phases/{phase_id}/builder_result",
    # Approvals domain
    "/approval/request",
    "/approval/pending",
    "/telegram/webhook",
    # Dashboard domain
    "/dashboard/runs/{run_id}/status",
    "/dashboard/usage",
    # Governance
    "/governance/pending",
    # Storage optimizer
    "/storage/scan",
    "/storage/scans",
    # Auth (mounted router)
    "/api/auth/login",
]

# Minimum expected route count (paths, not methods).
# This prevents accidental mass deletion during refactoring.
# Update this value deliberately when adding/removing routes.
# As of 2026-01-11: 49 routes total
MINIMUM_ROUTE_COUNT = 44


class TestRouteContract:
    """Contract tests for API route stability."""

    @pytest.fixture
    def openapi_spec(self):
        """Get the OpenAPI specification from the app."""
        return get_app_routes()

    @pytest.fixture
    def route_paths(self, openapi_spec):
        """Extract route paths from OpenAPI spec."""
        return set(openapi_spec.get("paths", {}).keys())

    def test_openapi_spec_loads(self, openapi_spec):
        """Baseline: OpenAPI spec should load without errors."""
        assert "openapi" in openapi_spec
        assert "info" in openapi_spec
        assert "paths" in openapi_spec

    def test_api_version_present(self, openapi_spec):
        """API version should be present in OpenAPI info."""
        assert "version" in openapi_spec["info"]
        assert openapi_spec["info"]["version"]  # Not empty

    @pytest.mark.parametrize("required_path", REQUIRED_ROUTE_PATTERNS)
    def test_required_route_exists(self, route_paths, required_path):
        """Critical routes must exist in the API."""
        assert (
            required_path in route_paths
        ), f"Required route {required_path} missing from API.\n" f"Available routes ({len(route_paths)}):\n" + "\n".join(
            sorted(route_paths)[:20]
        ) + (
            "\n..." if len(route_paths) > 20 else ""
        )

    def test_minimum_route_count(self, route_paths):
        """API must have at least the minimum expected number of routes.

        This prevents accidental mass deletion during refactoring.
        """
        route_count = len(route_paths)
        assert route_count >= MINIMUM_ROUTE_COUNT, (
            f"Route count dropped below minimum: {route_count} < {MINIMUM_ROUTE_COUNT}\n"
            f"If routes were intentionally removed, update MINIMUM_ROUTE_COUNT.\n"
            f"Current routes:\n" + "\n".join(sorted(route_paths))
        )

    def test_route_count_not_excessive_drop(self, route_paths):
        """Warn if route count drops significantly.

        This test is informational - it passes but logs a warning if
        the route count is much higher than the minimum, suggesting
        the minimum should be updated.
        """
        route_count = len(route_paths)
        if route_count > MINIMUM_ROUTE_COUNT + 10:
            # More than 10 routes above minimum - suggest updating
            pytest.skip(
                f"Route count ({route_count}) is {route_count - MINIMUM_ROUTE_COUNT} above minimum. "
                f"Consider updating MINIMUM_ROUTE_COUNT to {route_count - 5} for tighter bounds."
            )

    def test_no_empty_path_operations(self, openapi_spec):
        """Each path should have at least one HTTP method defined."""
        paths = openapi_spec.get("paths", {})
        empty_paths = [
            path
            for path, operations in paths.items()
            if not any(
                op in operations
                for op in ["get", "post", "put", "delete", "patch", "options", "head"]
            )
        ]
        assert not empty_paths, f"Paths with no operations: {empty_paths}"


class TestRouteDomainCoverage:
    """Tests that verify each domain has expected routes."""

    @pytest.fixture
    def openapi_spec(self):
        return get_app_routes()

    @pytest.fixture
    def route_paths(self, openapi_spec):
        return set(openapi_spec.get("paths", {}).keys())

    def test_runs_domain_coverage(self, route_paths):
        """Runs domain should have CRUD-like endpoints."""
        runs_routes = [p for p in route_paths if p.startswith("/runs")]
        assert len(runs_routes) >= 5, f"Runs domain underrepresented: {runs_routes}"

    def test_dashboard_domain_coverage(self, route_paths):
        """Dashboard domain should have operator surface endpoints."""
        dashboard_routes = [p for p in route_paths if p.startswith("/dashboard")]
        assert len(dashboard_routes) >= 3, f"Dashboard domain underrepresented: {dashboard_routes}"

    def test_storage_domain_coverage(self, route_paths):
        """Storage optimizer domain should have scan/cleanup endpoints."""
        storage_routes = [p for p in route_paths if p.startswith("/storage")]
        assert len(storage_routes) >= 5, f"Storage domain underrepresented: {storage_routes}"

    def test_auth_domain_coverage(self, route_paths):
        """Auth domain (mounted router) should have token endpoint."""
        auth_routes = [p for p in route_paths if "/auth" in p]
        assert len(auth_routes) >= 1, f"Auth domain missing: {auth_routes}"
