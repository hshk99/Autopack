"""
Contract test: JWT algorithm enforcement (CVE-2024-23342 guardrail).

This test ensures that Autopack only accepts RS256 for JWT signing and fails fast
on any attempt to use ECDSA algorithms (ES256/ES384/ES512) or other insecure algorithms.

Background:
- CVE-2024-23342: ECDSA signature malleability in python-jose dependency (via ecdsa package)
- Autopack exclusively uses RS256 (RSA-based) JWT signing, which is not affected
- This test enforces that contract at runtime

See: docs/SECURITY_EXCEPTIONS.md for full CVE-2024-23342 rationale
"""

import os

import pytest
from pydantic import ValidationError


def test_jwt_algorithm_must_be_rs256():
    """
    CONTRACT: jwt_algorithm must be RS256 (fail fast on any other algorithm).

    This test validates the CVE-2024-23342 compensating control:
    - RS256 is the only allowed algorithm
    - Attempts to set ES256, ES384, ES512, HS256, or any other algorithm must fail
    """
    # Import Settings here (not at module level) to avoid config pollution
    from autopack.config import Settings

    # Test 1: Default value should be RS256 (and should succeed)
    settings = Settings()
    assert settings.jwt_algorithm == "RS256", "Default jwt_algorithm must be RS256"

    # Test 2: Explicit RS256 should succeed
    settings_rs256 = Settings(jwt_algorithm="RS256")
    assert settings_rs256.jwt_algorithm == "RS256"

    # Test 3: ECDSA algorithms must be rejected (CVE-2024-23342 mitigation)
    ecdsa_algorithms = ["ES256", "ES384", "ES512"]
    for algo in ecdsa_algorithms:
        with pytest.raises(ValidationError, match="jwt_algorithm must be 'RS256'"):
            Settings(jwt_algorithm=algo)

    # Test 4: Other algorithms (HS256, none, etc.) must also be rejected
    other_algorithms = ["HS256", "HS384", "HS512", "none", "RS384", "RS512"]
    for algo in other_algorithms:
        with pytest.raises(ValidationError, match="jwt_algorithm must be 'RS256'"):
            Settings(jwt_algorithm=algo)


def test_jwt_algorithm_env_override_rejected():
    """
    CONTRACT: Even environment variable overrides must enforce RS256-only.

    This test ensures that the guardrail works even if someone tries to override
    jwt_algorithm via environment variable.
    """
    from autopack.config import Settings

    # Attempt to override via environment (should still fail validation)
    original_value = os.environ.get("JWT_ALGORITHM")
    try:
        os.environ["JWT_ALGORITHM"] = "ES256"
        with pytest.raises(ValidationError, match="jwt_algorithm must be 'RS256'"):
            Settings()
    finally:
        # Restore original env var (or delete if it didn't exist)
        if original_value is None:
            os.environ.pop("JWT_ALGORITHM", None)
        else:
            os.environ["JWT_ALGORITHM"] = original_value


def test_security_exception_reference_in_error_message():
    """
    CONTRACT: Error message must reference docs/SECURITY_EXCEPTIONS.md.

    When the guardrail fails, the error message should guide users to the
    documented security exception for CVE-2024-23342.
    """
    from autopack.config import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(jwt_algorithm="ES256")

    error_message = str(exc_info.value)
    assert "CVE-2024-23342" in error_message, "Error message must mention CVE-2024-23342"
    assert "SECURITY_EXCEPTIONS.md" in error_message, "Error message must reference docs"
    assert "ECDSA" in error_message, "Error message must explain ECDSA is not supported"
