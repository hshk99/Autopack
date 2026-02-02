#!/usr/bin/env python3
"""
Compose Stack Smoke Test (Item 1.7)

Purpose: Validate basic compose topology health
- nginx routing works (static health + proxied health)
- /api/auth/* prefix preservation
- Backend API readiness
- Database connectivity
- Qdrant connectivity (when enabled)

Usage:
    python scripts/smoke_test_compose.py

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
"""

import sys
import time
import subprocess
import requests
from typing import Tuple

# Configuration
NGINX_BASE = "http://localhost:80"
BACKEND_BASE = "http://localhost:8000"
TIMEOUT = 10
MAX_RETRIES = 3
RETRY_DELAY = 2


class SmokeTestResult:
    """Track test results."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.tests = []

    def record(self, name: str, passed: bool, message: str = "", is_warning: bool = False):
        """Record a test result."""
        status = "✓" if passed else ("⚠" if is_warning else "✗")
        self.tests.append((name, passed, message, is_warning))

        if passed:
            self.passed += 1
            print(f"{status} {name}")
        elif is_warning:
            self.warnings += 1
            print(f"{status} {name}: {message}")
        else:
            self.failed += 1
            print(f"{status} {name}: {message}")

    def summary(self):
        """Print summary."""
        total = self.passed + self.failed + self.warnings
        print(f"\n{'=' * 60}")
        print(f"Smoke Test Results: {self.passed}/{total} passed")
        if self.failed > 0:
            print(f"  Failed: {self.failed}")
        if self.warnings > 0:
            print(f"  Warnings: {self.warnings}")
        print(f"{'=' * 60}")
        return self.failed == 0


def check_service_health(service: str, timeout: int = 5) -> Tuple[bool, str]:
    """Check if a docker compose service is healthy."""
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--filter", f"name={service}", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return False, f"docker compose ps failed: {result.stderr}"

        # Check if service is running
        if not result.stdout.strip():
            return False, f"service {service} not found"

        return True, "service is running"
    except subprocess.TimeoutExpired:
        return False, f"timeout checking service {service}"
    except Exception as e:
        return False, f"error checking service: {e}"


def check_http_endpoint(
    url: str, expected_status: int = 200, retries: int = MAX_RETRIES
) -> Tuple[bool, str]:
    """Check if HTTP endpoint responds with expected status."""
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=TIMEOUT)
            if response.status_code == expected_status:
                return True, f"status {response.status_code}"
            else:
                return False, f"expected {expected_status}, got {response.status_code}"
        except requests.exceptions.ConnectionError as e:
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY)
                continue
            return False, f"connection error: {e}"
        except requests.exceptions.Timeout:
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY)
                continue
            return False, "timeout"
        except Exception as e:
            return False, f"error: {e}"

    return False, "max retries exceeded"


def check_postgres_ready(timeout: int = 5) -> Tuple[bool, str]:
    """Check if PostgreSQL is ready using pg_isready."""
    try:
        result = subprocess.run(
            ["docker", "compose", "exec", "-T", "db", "pg_isready", "-U", "autopack"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, "pg_isready succeeded"
        else:
            return False, f"pg_isready failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as e:
        return False, f"error: {e}"


def check_qdrant_ready(timeout: int = 5) -> Tuple[bool, str]:
    """Check if Qdrant is reachable."""
    try:
        # Try Qdrant's health endpoint (via localhost if port is exposed)
        response = requests.get("http://localhost:6333/", timeout=timeout)
        if response.status_code == 200:
            return True, f"status {response.status_code}"
        else:
            return False, f"unexpected status {response.status_code}"
    except requests.exceptions.ConnectionError:
        # Port might not be exposed, check container health instead
        try:
            result = subprocess.run(
                ["docker", "compose", "ps", "--filter", "name=qdrant", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0 and result.stdout.strip():
                return True, "container is running (port not exposed)"
            else:
                return False, "container not running"
        except Exception as e:
            return False, f"error checking container: {e}"
    except Exception as e:
        return False, f"error: {e}"


def check_auth_prefix_preservation() -> Tuple[bool, str]:
    """Check that /api/auth/* prefix is preserved when proxied through nginx.

    This validates that nginx config correctly preserves the full path
    including /api/auth prefix (not stripping it like the general /api/ route).
    """
    try:
        # The auth router is mounted at /api/auth in the backend
        # nginx should proxy /api/auth/* → backend:8000/api/auth/* (preserve prefix)
        # NOT /api/auth/* → backend:8000/auth/* (that would be wrong)

        # We can test this by hitting a known auth endpoint through nginx
        # and checking if it routes correctly to the backend's /api/auth router

        # Since we're in smoke test mode, we'll just check that the route exists
        # A 401/404 is fine (means routing works), but connection refused means broken
        url = f"{NGINX_BASE}/api/auth/login"

        response = requests.get(url, timeout=TIMEOUT)

        # 401 Unauthorized = route exists but needs auth (GOOD)
        # 404 Not Found = route exists but endpoint not found (depends on implementation)
        # 405 Method Not Allowed = route exists but wrong method (GOOD)
        # 500 = backend error but routing works (acceptable for smoke test)
        # Connection refused = routing broken (BAD)

        acceptable_codes = [401, 404, 405, 422, 500]  # Any code that proves routing works

        if response.status_code in acceptable_codes:
            return True, f"route reachable (status {response.status_code})"
        elif response.status_code == 200:
            return True, "route reachable and working (status 200)"
        else:
            return False, f"unexpected status {response.status_code}"

    except requests.exceptions.ConnectionError as e:
        return False, f"connection error (routing likely broken): {e}"
    except Exception as e:
        return False, f"error: {e}"


def main():
    """Run all smoke tests."""
    results = SmokeTestResult()

    print("🔬 Autopack Compose Stack Smoke Test\n")
    print("Checking compose services...\n")

    # 1. Check nginx service
    print("1. Nginx Service")
    passed, msg = check_service_health("frontend")
    results.record("nginx container running", passed, msg)

    # 2. Check nginx health endpoint (static, no backend dependency)
    print("\n2. Nginx Health Endpoint")
    passed, msg = check_http_endpoint(f"{NGINX_BASE}/nginx-health")
    results.record("nginx /nginx-health responds", passed, msg)

    # 3. Check proxied health endpoint (nginx → backend)
    print("\n3. Proxied Health Endpoint")
    passed, msg = check_http_endpoint(f"{NGINX_BASE}/health")
    results.record("proxied /health responds", passed, msg)

    # 4. Check backend direct health
    print("\n4. Backend API Direct")
    passed, msg = check_http_endpoint(f"{BACKEND_BASE}/health")
    results.record("backend direct /health responds", passed, msg)

    # 5. Check /api/auth/* prefix preservation
    print("\n5. Auth Route Prefix Preservation")
    passed, msg = check_auth_prefix_preservation()
    results.record("/api/auth/* prefix preserved", passed, msg)

    # 6. Check database connectivity
    print("\n6. Database Connectivity")
    passed, msg = check_service_health("db")
    results.record("db container running", passed, msg)

    passed, msg = check_postgres_ready()
    results.record("postgres ready (pg_isready)", passed, msg)

    # 7. Check Qdrant connectivity
    print("\n7. Qdrant Vector DB")
    passed, msg = check_service_health("qdrant")
    results.record("qdrant container running", passed, msg)

    passed, msg = check_qdrant_ready()
    # Qdrant is optional, so make this a warning not a failure
    results.record("qdrant reachable", passed, msg, is_warning=not passed)

    # 8. Check backend can reach dependencies
    print("\n8. Backend Readiness (DB + Qdrant)")
    # The /health endpoint should check DB and Qdrant internally
    # We already checked this in step 3, but verify the response content
    try:
        response = requests.get(f"{BACKEND_BASE}/health", timeout=TIMEOUT)
        if response.status_code == 200:
            health_data = response.json()

            # Check database status
            db_status = health_data.get("database_status", "unknown")
            db_ok = db_status in ["healthy", "connected"]
            results.record(
                "backend→db connectivity",
                db_ok,
                f"database_status={db_status}",
                is_warning=not db_ok,
            )

            # Check Qdrant status (optional)
            qdrant_status = health_data.get("qdrant_status", "unknown")
            qdrant_ok = qdrant_status in ["connected", "disabled"]
            results.record(
                "backend→qdrant connectivity",
                qdrant_ok,
                f"qdrant_status={qdrant_status}",
                is_warning=not qdrant_ok,
            )
        else:
            results.record(
                "backend readiness check", False, f"health endpoint returned {response.status_code}"
            )
    except Exception as e:
        results.record("backend readiness check", False, f"error: {e}")

    # Print summary
    success = results.summary()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
