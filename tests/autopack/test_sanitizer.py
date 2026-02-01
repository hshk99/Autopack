"""
Tests for the sanitizer module.

BUILD-188: Ensures sensitive data is properly redacted before persistence.
"""

import pytest

from autopack.sanitizer import (REDACTED, sanitize_context, sanitize_dict,
                                sanitize_headers, sanitize_query_params,
                                sanitize_stack_frames, sanitize_url,
                                sanitize_value)


class TestSanitizeHeaders:
    """Tests for header sanitization."""

    def test_redacts_authorization_header(self):
        """Authorization header should be redacted."""
        headers = {"Authorization": "Bearer sk_live_abc123xyz"}
        result = sanitize_headers(headers)
        assert result["Authorization"] == REDACTED

    def test_redacts_cookie_header(self):
        """Cookie header should be redacted."""
        headers = {"Cookie": "session=abc123; auth_token=secret"}
        result = sanitize_headers(headers)
        assert result["Cookie"] == REDACTED

    def test_redacts_x_api_key_header(self):
        """X-API-Key header should be redacted."""
        headers = {"X-API-Key": "my-secret-api-key"}
        result = sanitize_headers(headers)
        assert result["X-API-Key"] == REDACTED

    def test_preserves_safe_headers(self):
        """Safe headers should be preserved."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Autopack/1.0",
            "Accept": "application/json",
        }
        result = sanitize_headers(headers)
        assert result["Content-Type"] == "application/json"
        assert result["User-Agent"] == "Autopack/1.0"
        assert result["Accept"] == "application/json"

    def test_case_insensitive_header_matching(self):
        """Header matching should be case-insensitive."""
        headers = {
            "authorization": "Bearer secret",
            "COOKIE": "session=abc",
            "x-api-KEY": "key123",
        }
        result = sanitize_headers(headers)
        assert result["authorization"] == REDACTED
        assert result["COOKIE"] == REDACTED
        assert result["x-api-KEY"] == REDACTED


class TestSanitizeQueryParams:
    """Tests for query parameter sanitization."""

    def test_redacts_token_param(self):
        """Token parameter should be redacted."""
        params = {"token": "secret_token_value"}
        result = sanitize_query_params(params)
        assert result["token"] == REDACTED

    def test_redacts_api_key_param(self):
        """API key parameter should be redacted."""
        params = {
            "api_key": "sk_live_abc123"  # gitleaks:allow (intentional fake key for sanitizer test)
        }
        result = sanitize_query_params(params)
        assert result["api_key"] == REDACTED

    def test_redacts_password_param(self):
        """Password parameter should be redacted."""
        params = {"password": "my_secret_password"}
        result = sanitize_query_params(params)
        assert result["password"] == REDACTED

    def test_preserves_safe_params(self):
        """Safe parameters should be preserved."""
        params = {"page": "1", "limit": "10", "sort": "created_at"}
        result = sanitize_query_params(params)
        assert result["page"] == "1"
        assert result["limit"] == "10"
        assert result["sort"] == "created_at"


class TestSanitizeDict:
    """Tests for dictionary sanitization."""

    def test_redacts_sensitive_keys(self):
        """Dictionaries with sensitive keys should have values redacted."""
        data = {
            "username": "john",
            "password": "secret123",  # gitleaks:allow (intentional fake password for sanitizer test)
            "api_key": "sk_live_abc",  # gitleaks:allow (intentional fake key for sanitizer test)
            "database_url": "postgresql://user:pass@host/db",  # gitleaks:allow (intentional fake URL for sanitizer test)
        }
        result = sanitize_dict(data)
        assert result["username"] == "john"
        assert result["password"] == REDACTED
        assert result["api_key"] == REDACTED
        assert result["database_url"] == REDACTED

    def test_handles_nested_dicts(self):
        """Nested dictionaries should be sanitized recursively."""
        data = {
            "user": {
                "name": "john",
                "credentials": {"token": "secret", "email": "test@example.com"},
            },
        }
        result = sanitize_dict(data)
        assert result["user"]["name"] == "john"
        # "credentials" is a sensitive key, so it should be redacted entirely
        assert result["user"]["credentials"] == REDACTED

    def test_nested_safe_keys_with_sensitive_values(self):
        """Nested dicts with safe keys but sensitive nested values should be handled."""
        data = {
            "config": {"db_settings": {"password": "secret", "host": "localhost"}},
        }
        result = sanitize_dict(data)
        assert result["config"]["db_settings"]["password"] == REDACTED
        assert result["config"]["db_settings"]["host"] == "localhost"

    def test_limits_nesting_depth(self):
        """Deeply nested structures should be limited."""
        # Create deeply nested dict
        data = {"level1": {"level2": {"level3": {"level4": {"level5": {"level6": "deep"}}}}}}
        result = sanitize_dict(data)
        # Should handle depth limit gracefully
        assert isinstance(result, dict)


class TestSanitizeValue:
    """Tests for value sanitization."""

    def test_redacts_jwt_tokens(self):
        """JWT tokens in values should be redacted."""
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"  # gitleaks:allow (intentional fake JWT for sanitizer test)
        result = sanitize_value(jwt)
        assert REDACTED in result
        assert "eyJ" not in result

    def test_redacts_bearer_tokens(self):
        """Bearer tokens in values should be redacted."""
        value = "Bearer sk_live_1234567890abcdef"  # gitleaks:allow (intentional fake token for sanitizer test)
        result = sanitize_value(value)
        assert REDACTED in result

    def test_redacts_database_urls(self):
        """Database URLs with credentials should be redacted."""
        db_url = "postgresql://myuser:mypassword@localhost:5432/mydb"
        result = sanitize_value(db_url)
        assert REDACTED in result
        assert "mypassword" not in result

    def test_truncates_long_values(self):
        """Long values should be truncated."""
        long_value = "x" * 500
        result = sanitize_value(long_value)
        assert len(result) < len(long_value)
        assert "truncated" in result


class TestSanitizeStackFrames:
    """Tests for stack frame sanitization."""

    def test_redacts_local_vars_by_default(self):
        """Local variables should be redacted by default."""
        frames = [
            {
                "filename": "/app/main.py",
                "function": "process_request",
                "line_number": 42,
                "local_vars": {
                    "request": "Request()",
                    "api_key": "secret_key_value",
                    "password": "secret_password",
                },
            }
        ]
        result = sanitize_stack_frames(frames, redact_locals=True)
        assert result[0]["local_vars"] == "[REDACTED_BY_POLICY]"

    def test_preserves_frame_metadata(self):
        """Frame metadata (filename, function, line) should be preserved."""
        frames = [
            {
                "filename": "/app/main.py",
                "function": "process_request",
                "line_number": 42,
                "local_vars": {"x": "1"},
            }
        ]
        result = sanitize_stack_frames(frames, redact_locals=True)
        assert result[0]["filename"] == "/app/main.py"
        assert result[0]["function"] == "process_request"
        assert result[0]["line_number"] == 42


class TestSanitizeUrl:
    """Tests for URL sanitization."""

    def test_redacts_password_in_postgresql_url(self):
        """PostgreSQL URL credentials should be redacted."""
        url = "postgresql://user:secret_password@localhost:5432/db"
        result = sanitize_url(url)
        assert "secret_password" not in result
        assert REDACTED in result
        assert "user:" in result  # Username part is preserved in pattern
        assert "@localhost" in result

    def test_redacts_password_in_mysql_url(self):
        """MySQL URL credentials should be redacted."""
        url = "mysql://admin:p@ssw0rd@db.example.com/mydb"
        result = sanitize_url(url)
        assert "p@ssw0rd" not in result
        assert REDACTED in result

    def test_preserves_url_without_credentials(self):
        """URLs without credentials should be preserved."""
        url = "https://api.example.com/v1/endpoint"
        result = sanitize_url(url)
        assert result == url


class TestSanitizeContext:
    """Tests for the main sanitize_context function."""

    def test_sanitizes_all_components(self):
        """All components should be sanitized when provided."""
        result = sanitize_context(
            context_data={"api_key": "secret", "user": "john"},
            headers={"Authorization": "Bearer token"},
            query_params={"token": "secret_token"},
            stack_frames=[
                {
                    "filename": "test.py",
                    "function": "test",
                    "line_number": 1,
                    "local_vars": {"x": "1"},
                }
            ],
        )

        assert result["context_data"]["api_key"] == REDACTED
        assert result["context_data"]["user"] == "john"
        assert result["headers"]["Authorization"] == REDACTED
        assert result["query_params"]["token"] == REDACTED
        assert result["stack_frames"][0]["local_vars"] == "[REDACTED_BY_POLICY]"

    def test_handles_none_values(self):
        """None values should be handled gracefully."""
        result = sanitize_context(
            context_data=None,
            headers=None,
            query_params=None,
            stack_frames=None,
        )
        assert result == {}


class TestHyphenatedHeaderRedaction:
    """P0 Security: Tests for hyphenated header key redaction (BUILD-189).

    This test class specifically verifies that sensitive headers with hyphens
    (like X-API-Key, Set-Cookie) are properly redacted regardless of:
    - hyphen vs underscore variants
    - mixed case variants
    - original HTTP header capitalization conventions
    """

    @pytest.mark.parametrize(
        "header_name",
        [
            # Hyphenated variants (original HTTP header format)
            "X-API-Key",
            "x-api-key",
            "X-Api-Key",
            "Set-Cookie",
            "set-cookie",
            "SET-COOKIE",
            "X-GitHub-Token",
            "x-github-token",
            "X-Auth-Token",
            "X-Access-Token",
            "X-Refresh-Token",
            "X-Session-ID",
            "X-CSRF-Token",
            "Proxy-Authorization",
            "WWW-Authenticate",
            # Underscore variants (some clients normalize to underscores)
            "X_API_Key",
            "x_api_key",
            "Set_Cookie",
            "X_GitHub_Token",
        ],
    )
    def test_hyphenated_headers_redacted(self, header_name):
        """All hyphenated sensitive headers must be redacted regardless of case/separator."""
        secret_value = "super_secret_value_12345"
        result = sanitize_headers({header_name: secret_value})
        assert (
            result[header_name] == REDACTED
        ), f"Header '{header_name}' was not redacted! Got: {result[header_name]}"

    @pytest.mark.parametrize(
        "header_name,secret_value",
        [
            (
                "X-API-Key",
                "sk_live_1234567890abcdef",
            ),  # gitleaks:allow (intentional fake token for sanitizer test)
            ("Set-Cookie", "session=abc123; HttpOnly; Secure"),
            (
                "X-GitHub-Token",
                "ghp_abcdefghijklmnop1234567890",
            ),  # gitleaks:allow (intentional fake token for sanitizer test)
            ("Authorization", "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"),
            ("Cookie", "auth_token=secret123; session_id=xyz"),
        ],
    )
    def test_secret_values_never_in_output(self, header_name, secret_value):
        """Secret values must never appear in sanitized output."""
        result = sanitize_headers({header_name: secret_value})
        serialized = str(result)
        # The actual secret value should not appear anywhere in the output
        assert secret_value not in serialized, (
            f"Secret value leaked for header '{header_name}'! "
            f"Found '{secret_value}' in output: {serialized}"
        )

    def test_all_security_headers_covered(self):
        """Verify that all common security-sensitive headers are redacted."""
        # These headers commonly contain credentials or session tokens
        security_headers = {
            "Authorization": "Bearer token123",
            "Cookie": "session=abc123",
            "Set-Cookie": "auth=secret; HttpOnly",
            "X-API-Key": "api-key-value",  # gitleaks:allow (intentional fake key for sanitizer test)
            "X-Auth-Token": "auth-token-value",  # gitleaks:allow (intentional fake token for sanitizer test)
            "X-GitHub-Token": "github-token-value",  # gitleaks:allow (intentional fake token for sanitizer test)
            "X-Access-Token": "access-token-value",  # gitleaks:allow (intentional fake token for sanitizer test)
            "X-Refresh-Token": "refresh-token-value",  # gitleaks:allow (intentional fake token for sanitizer test)
            "X-Session-ID": "session-id-value",  # gitleaks:allow (intentional fake ID for sanitizer test)
            "X-CSRF-Token": "csrf-token-value",  # gitleaks:allow (intentional fake token for sanitizer test)
            "Proxy-Authorization": "proxy-auth-value",  # gitleaks:allow (intentional fake auth for sanitizer test)
            "WWW-Authenticate": "www-auth-value",  # gitleaks:allow (intentional fake auth for sanitizer test)
        }

        result = sanitize_headers(security_headers)

        for header_name in security_headers:
            assert (
                result[header_name] == REDACTED
            ), f"Security header '{header_name}' was not redacted!"


class TestSanitizerKeyNormalization:
    """Tests verifying key normalization handles edge cases correctly."""

    def test_dict_keys_hyphen_underscore_equivalence(self):
        """Dict keys with hyphens and underscores should both match sensitive patterns."""
        # These should all be redacted
        test_cases = [
            {"api-key": "secret"},
            {"api_key": "secret"},
            {"API-KEY": "secret"},
            {"API_KEY": "secret"},
            {"database-url": "secret"},
            {"database_url": "secret"},
        ]

        for data in test_cases:
            result = sanitize_dict(data)
            key = list(data.keys())[0]
            assert result[key] == REDACTED, f"Key '{key}' was not redacted"

    def test_safe_hyphenated_headers_preserved(self):
        """Non-sensitive hyphenated headers should be preserved."""
        safe_headers = {
            "Content-Type": "application/json",
            "Accept-Language": "en-US",
            "Cache-Control": "no-cache",
            "X-Request-ID": "req-123",
            "X-Correlation-ID": "corr-456",
        }

        result = sanitize_headers(safe_headers)

        for header_name, value in safe_headers.items():
            assert (
                result[header_name] == value
            ), f"Safe header '{header_name}' was incorrectly modified"


class TestNoSecretsInPersistedArtifacts:
    """Integration tests ensuring secrets don't leak into persisted artifacts."""

    @pytest.mark.parametrize(
        "secret_key,secret_value",
        [
            (
                "Authorization",
                "Bearer sk_live_abc123",
            ),  # gitleaks:allow (intentional fake token for sanitizer test)
            (
                "Cookie",
                "session=secret_session_id",
            ),  # gitleaks:allow (intentional fake cookie for sanitizer test)
            (
                "password",
                "my_super_secret_password",
            ),  # gitleaks:allow (intentional fake password for sanitizer test)
            (
                "api_key",
                "api_key_12345",
            ),  # gitleaks:allow (intentional fake key for sanitizer test)
            (
                "token",
                "jwt_token_value",
            ),  # gitleaks:allow (intentional fake token for sanitizer test)
            (
                "secret",
                "the_secret_value",
            ),  # gitleaks:allow (intentional fake secret for sanitizer test)
            (
                "database_url",
                "postgresql://user:pass@host/db",
            ),  # gitleaks:allow (intentional fake URL for sanitizer test)
            # P0 Security: Add hyphenated header test cases
            (
                "X-API-Key",
                "x_api_key_secret_value",
            ),  # gitleaks:allow (intentional fake key for sanitizer test)
            (
                "Set-Cookie",
                "session=leaked_session_id",
            ),  # gitleaks:allow (intentional fake cookie for sanitizer test)
            (
                "X-GitHub-Token",
                "ghp_leaked_github_token",
            ),  # gitleaks:allow (intentional fake token for sanitizer test)
        ],
    )
    def test_secret_not_in_sanitized_output(self, secret_key, secret_value):
        """Secrets should never appear in sanitized output."""
        # Test in headers
        headers_result = sanitize_headers({secret_key: secret_value})
        serialized = str(headers_result)
        assert secret_value not in serialized

        # Test in query params
        params_result = sanitize_query_params({secret_key: secret_value})
        serialized = str(params_result)
        assert secret_value not in serialized

        # Test in dict
        dict_result = sanitize_dict({secret_key: secret_value})
        serialized = str(dict_result)
        assert secret_value not in serialized
