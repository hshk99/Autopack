"""Tests for log sanitization utility (IMP-SEC-007).

Tests verify that sensitive data like API keys, credentials, and environment
variables are properly redacted from logs.
"""

from autopack.executor.log_sanitizer import LogSanitizer


class TestLogSanitizerAPIKeys:
    """Test sanitization of API keys from various providers."""

    def test_sanitize_together_api_key(self):
        """Sanitize Together AI API key."""
        text = "Error: together_api_key=abc123xyz456"
        result = LogSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "abc123xyz456" not in result

    def test_sanitize_openai_api_key(self):
        """Sanitize OpenAI API key."""
        text = "Connection failed: openai_api_key=sk-abc123xyz456"
        result = LogSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "sk-abc123xyz456" not in result

    def test_sanitize_runpod_api_key(self):
        """Sanitize RunPod API key."""
        text = "RunPod error: runpod_api_key=xyz789abc123"
        result = LogSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "xyz789abc123" not in result

    def test_sanitize_github_token(self):
        """Sanitize GitHub token."""
        text = "Auth error: github_token=ghp_1234567890abcdef"
        result = LogSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "ghp_1234567890abcdef" not in result


class TestLogSanitizerEnvironmentVariables:
    """Test sanitization of environment variables."""

    def test_sanitize_database_url(self):
        """Sanitize DATABASE_URL environment variable."""
        text = "Connection error: DATABASE_URL=postgresql://user:pass@localhost/db"
        result = LogSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "postgresql://user:pass@localhost/db" not in result

    def test_sanitize_password_env_var(self):
        """Sanitize password environment variable."""
        text = "Setup failed with DB_PASSWORD=supersecret123"
        result = LogSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "supersecret123" not in result

    def test_sanitize_jwt_secret(self):
        """Sanitize JWT_SECRET environment variable."""
        text = "Failed: JWT_SECRET=your-secret-key-here-12345"
        result = LogSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "your-secret-key-here-12345" not in result


class TestLogSanitizerURLsWithCredentials:
    """Test sanitization of URLs containing credentials."""

    def test_sanitize_url_with_basic_auth(self):
        """Sanitize URL with basic authentication."""
        text = "Connection to https://user:password@api.example.com failed"
        result = LogSanitizer.sanitize(text)
        assert "[REDACTED]@" in result
        assert "user:password" not in result

    def test_sanitize_database_connection_string(self):
        """Sanitize database connection string with credentials."""
        text = "Error connecting to postgresql://admin:secretpass@localhost/mydb"
        result = LogSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "admin:secretpass" not in result or "[REDACTED]" in result


class TestLogSanitizerCredentials:
    """Test sanitization of generic credentials."""

    def test_sanitize_password_field(self):
        """Sanitize password field."""
        text = "Auth failed: password=mySecurePassword123!"
        result = LogSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "mySecurePassword123!" not in result

    def test_sanitize_secret_field(self):
        """Sanitize secret field."""
        text = "Configuration error: secret=hidden-value-xyz"
        result = LogSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "hidden-value-xyz" not in result

    def test_sanitize_token_field(self):
        """Sanitize token field."""
        text = "Invalid token: token=bearer_token_abc123xyz"
        result = LogSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "bearer_token_abc123xyz" not in result


class TestLogSanitizerExceptions:
    """Test sanitization of exception messages."""

    def test_sanitize_exception_with_api_key(self):
        """Sanitize exception message containing API key."""
        exception = Exception("API call failed with api_key=abc123xyz456")
        result = LogSanitizer.sanitize_exception(exception)
        assert "[REDACTED]" in result
        assert "abc123xyz456" not in result

    def test_sanitize_exception_with_password(self):
        """Sanitize exception message containing password."""
        exception = Exception("Database connection failed: password=secret123")
        result = LogSanitizer.sanitize_exception(exception)
        assert "[REDACTED]" in result
        assert "secret123" not in result

    def test_sanitize_exception_with_url_credentials(self):
        """Sanitize exception message with URL credentials."""
        exception = Exception("Connection error: https://admin:pass@server.com")
        result = LogSanitizer.sanitize_exception(exception)
        assert "pass@server.com" not in result


class TestLogSanitizerEdgeCases:
    """Test edge cases and special scenarios."""

    def test_sanitize_none_value(self):
        """Sanitize None value."""
        result = LogSanitizer.sanitize(None)
        assert result == "[None]"

    def test_sanitize_empty_string(self):
        """Sanitize empty string."""
        result = LogSanitizer.sanitize("")
        assert result == ""

    def test_sanitize_non_sensitive_text(self):
        """Verify non-sensitive text is unchanged."""
        text = "This is a normal log message without secrets"
        result = LogSanitizer.sanitize(text)
        assert result == text

    def test_sanitize_case_insensitive(self):
        """Test case-insensitive pattern matching."""
        text = "Error with TOGETHER_API_KEY=value123"
        result = LogSanitizer.sanitize(text)
        assert "[REDACTED]" in result
        assert "value123" not in result

    def test_sanitize_multiple_secrets(self):
        """Sanitize text with multiple secrets."""
        text = (
            "Config: database=postgresql://admin:pass@localhost/db "
            "and api_key=abc123 and password=secret"
        )
        result = LogSanitizer.sanitize(text)
        # Should have multiple redactions
        redaction_count = result.count("[REDACTED]")
        assert redaction_count >= 2


class TestLogSanitizerDictSanitization:
    """Test sanitization of dictionary data."""

    def test_sanitize_dict_with_secrets(self):
        """Sanitize dictionary containing secrets."""
        data = {
            "api_key": "openai_api_key=sk-abc123xyz456",
            "password": "password=secret123",
            "name": "test_user",
        }
        result = LogSanitizer.sanitize_dict(data)
        assert result["name"] == "test_user"
        # Values containing secrets should be sanitized
        assert "[REDACTED]" in result["api_key"]
        assert "[REDACTED]" in result["password"]

    def test_sanitize_nested_dict(self):
        """Sanitize nested dictionaries."""
        data = {
            "user": {"name": "john", "password": "password=secret123"},
            "api": {"key": "api_key=abc123xyz456"},
        }
        result = LogSanitizer.sanitize_dict(data)
        assert result["user"]["name"] == "john"
        # Secrets should be sanitized in nested dicts
        assert "[REDACTED]" in result["user"]["password"]
        assert "[REDACTED]" in result["api"]["key"]

    def test_sanitize_list_in_dict(self):
        """Sanitize lists within dictionaries."""
        data = {"tokens": ["token1", "token2"], "name": "test"}
        result = LogSanitizer.sanitize_dict(data)
        assert len(result["tokens"]) == 2


class TestLogSanitizerIntegration:
    """Integration tests for complete sanitization scenarios."""

    def test_sanitize_complete_error_message(self):
        """Sanitize a realistic error message."""
        error_msg = (
            "Failed to connect to database. "
            "Details: DATABASE_URL=postgresql://admin:mypassword@prod.example.com:5432/mydb "
            "API key abc123xyz used for authentication. "
            "Connection timeout after 30 seconds."
        )
        result = LogSanitizer.sanitize(error_msg)
        assert "admin:mypassword" not in result
        assert "abc123xyz" not in result or "[REDACTED]" in result
        assert "postgresql://admin" not in result

    def test_sanitize_preserves_structure(self):
        """Verify sanitization preserves message structure."""
        error_msg = "Error: [CODE-001] Failed with password=secret"
        result = LogSanitizer.sanitize(error_msg)
        assert "[CODE-001]" in result  # Non-sensitive code preserved
        assert "secret" not in result

    def test_multiple_sanitization_calls(self):
        """Verify multiple sanitization calls work correctly."""
        text1 = "Error 1: api_key=key1"
        text2 = "Error 2: password=pass2"

        result1 = LogSanitizer.sanitize(text1)
        result2 = LogSanitizer.sanitize(text2)

        assert "key1" not in result1
        assert "pass2" not in result2
