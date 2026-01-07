"""
Tests for the sanitizer module.

BUILD-188: Ensures sensitive data is properly redacted before persistence.
"""

import pytest

from autopack.sanitizer import (
    REDACTED,
    sanitize_context,
    sanitize_dict,
    sanitize_headers,
    sanitize_query_params,
    sanitize_stack_frames,
    sanitize_url,
    sanitize_value,
)


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
        params = {"api_key": "sk_live_abc123"}
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
            "password": "secret123",
            "api_key": "sk_live_abc",
            "database_url": "postgresql://user:pass@host/db",
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
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
        result = sanitize_value(jwt)
        assert REDACTED in result
        assert "eyJ" not in result

    def test_redacts_bearer_tokens(self):
        """Bearer tokens in values should be redacted."""
        value = "Bearer sk_live_1234567890abcdef"
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


class TestNoSecretsInPersistedArtifacts:
    """Integration tests ensuring secrets don't leak into persisted artifacts."""

    @pytest.mark.parametrize(
        "secret_key,secret_value",
        [
            ("Authorization", "Bearer sk_live_abc123"),
            ("Cookie", "session=secret_session_id"),
            ("password", "my_super_secret_password"),
            ("api_key", "api_key_12345"),
            ("token", "jwt_token_value"),
            ("secret", "the_secret_value"),
            ("database_url", "postgresql://user:pass@host/db"),
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
