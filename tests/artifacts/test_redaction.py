"""Tests for artifact redaction."""

import json
import tempfile
from pathlib import Path

import pytest

from autopack.artifacts import (
    DEFAULT_REDACTION_PATTERNS,
    ArtifactRedactor,
    RedactionPattern,
)
from autopack.artifacts.redaction import RedactionCategory


class TestRedactionCategory:
    """Tests for RedactionCategory enum."""

    def test_all_categories_exist(self):
        """All expected categories exist."""
        assert RedactionCategory.CREDENTIAL
        assert RedactionCategory.PII
        assert RedactionCategory.FINANCIAL
        assert RedactionCategory.SESSION
        assert RedactionCategory.NETWORK


class TestRedactionPattern:
    """Tests for RedactionPattern."""

    def test_create_pattern(self):
        """Can create a redaction pattern."""
        pattern = RedactionPattern(
            name="test_api_key",
            pattern=r"api_key=[\w-]+",
            replacement="api_key=[REDACTED]",
            category=RedactionCategory.CREDENTIAL,
        )
        assert pattern.name == "test_api_key"
        assert pattern.category == RedactionCategory.CREDENTIAL

    def test_compile_pattern(self):
        """Can compile a redaction pattern."""
        pattern = RedactionPattern(
            name="email",
            pattern=r"[\w.-]+@[\w.-]+",
            replacement="[EMAIL]",
            category=RedactionCategory.PII,
            case_insensitive=False,
        )
        compiled = pattern.compile()
        assert compiled is not None
        assert pattern.case_insensitive is False


class TestDefaultPatterns:
    """Tests for default redaction patterns."""

    def test_default_patterns_not_empty(self):
        """Default patterns exist."""
        assert len(DEFAULT_REDACTION_PATTERNS) > 0

    def test_has_credential_patterns(self):
        """Has credential redaction patterns."""
        credential_patterns = [
            p for p in DEFAULT_REDACTION_PATTERNS if p.category == RedactionCategory.CREDENTIAL
        ]
        assert len(credential_patterns) > 0

    def test_has_pii_patterns(self):
        """Has PII redaction patterns."""
        pii_patterns = [
            p for p in DEFAULT_REDACTION_PATTERNS if p.category == RedactionCategory.PII
        ]
        assert len(pii_patterns) > 0


class TestArtifactRedactor:
    """Tests for ArtifactRedactor."""

    @pytest.fixture
    def redactor(self):
        """Create redactor with default patterns."""
        return ArtifactRedactor()

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_redact_api_key(self, redactor):
        """Redacts API keys."""
        text = "Authorization: Bearer sk-abc123xyz789"
        result, count = redactor.redact_text(text)
        assert "sk-abc123xyz789" not in result
        assert "REDACTED" in result or "[" in result

    def test_redact_password(self, redactor):
        """Redacts passwords."""
        text = 'password="secret123"'
        result, count = redactor.redact_text(text)
        assert "secret123" not in result

    def test_redact_email(self, redactor):
        """Redacts email addresses."""
        text = "Contact: user@example.com"
        result, count = redactor.redact_text(text)
        assert "user@example.com" not in result

    def test_redact_phone(self, redactor):
        """Redacts phone numbers."""
        text = "Call me at 555-123-4567"
        result, count = redactor.redact_text(text)
        assert "555-123-4567" not in result

    def test_redact_credit_card(self, redactor):
        """Redacts credit card numbers."""
        text = "Card: 4111111111111111"  # No dashes - matches CC pattern
        result, count = redactor.redact_text(text)
        assert "4111111111111111" not in result

    def test_redact_ssn(self, redactor):
        """Redacts SSN-like numbers."""
        text = "SSN: 123-45-6789"
        result, count = redactor.redact_text(text)
        assert "123-45-6789" not in result

    def test_redact_multiple_patterns(self, redactor):
        """Redacts multiple patterns in same text."""
        text = """
        api_key=sk-test123abcdefghijkl
        Email: user@example.com
        Password: secret
        """
        result, count = redactor.redact_text(text)
        assert "sk-test123abcdefghijkl" not in result
        assert "user@example.com" not in result

    def test_redact_dict_simple(self, redactor):
        """Redacts sensitive values in dict."""
        data = {
            "api_key": "sk-abc123",
            "email": "user@example.com",
            "name": "John",
        }
        result = redactor.redact_dict(data)
        assert "sk-abc123" not in str(result)
        assert "user@example.com" not in str(result)
        assert result["name"] == "John"  # Non-sensitive preserved

    def test_redact_dict_nested(self, redactor):
        """Redacts nested dict values."""
        data = {
            "user": {
                "credentials": {
                    "api_key": "sk-secret",
                    "token": "bearer_xyz",
                }
            }
        }
        result = redactor.redact_dict(data)
        assert "sk-secret" not in str(result)
        assert "bearer_xyz" not in str(result)

    def test_redact_dict_list(self, redactor):
        """Redacts values in lists within dict."""
        data = {
            "tokens": ["token1", "token2"],
            "emails": ["a@b.com", "c@d.com"],
        }
        result = redactor.redact_dict(data)
        assert "a@b.com" not in str(result)
        assert "c@d.com" not in str(result)

    def test_redact_har_headers(self, redactor):
        """Redacts sensitive headers in HAR."""
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "headers": [
                                {"name": "Authorization", "value": "Bearer secret-token"},
                                {"name": "Content-Type", "value": "application/json"},
                            ]
                        },
                        "response": {
                            "headers": [
                                {"name": "Set-Cookie", "value": "session=abc123"},
                            ]
                        },
                    }
                ]
            }
        }
        result = redactor.redact_har(har)
        # Authorization header should be redacted
        req_headers = result["log"]["entries"][0]["request"]["headers"]
        auth_header = next(h for h in req_headers if h["name"] == "Authorization")
        assert "secret-token" not in auth_header["value"]
        # Content-Type should be preserved
        ct_header = next(h for h in req_headers if h["name"] == "Content-Type")
        assert ct_header["value"] == "application/json"

    def test_redact_har_cookies(self, redactor):
        """Redacts cookies in HAR."""
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "cookies": [
                                {"name": "session_id", "value": "secret123"},
                                {"name": "tracking", "value": "track456"},
                            ]
                        },
                        "response": {
                            "cookies": [
                                {"name": "auth_token", "value": "token789"},
                            ]
                        },
                    }
                ]
            }
        }
        result = redactor.redact_har(har)
        req_cookies = result["log"]["entries"][0]["request"]["cookies"]
        session_cookie = next(c for c in req_cookies if c["name"] == "session_id")
        assert "secret123" not in session_cookie["value"]

    def test_redact_har_query_params(self, redactor):
        """Redacts query params in HAR."""
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "queryString": [
                                {"name": "api_key", "value": "key123"},
                                {"name": "page", "value": "1"},
                            ]
                        }
                    }
                ]
            }
        }
        result = redactor.redact_har(har)
        query_params = result["log"]["entries"][0]["request"]["queryString"]
        api_param = next(p for p in query_params if p["name"] == "api_key")
        assert "key123" not in api_param["value"]
        # Non-sensitive params preserved
        page_param = next(p for p in query_params if p["name"] == "page")
        assert page_param["value"] == "1"

    def test_redact_har_post_data(self, redactor):
        """Redacts POST body in HAR."""
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "postData": {"text": '{"password": "secret", "username": "user"}'}
                        }
                    }
                ]
            }
        }
        result = redactor.redact_har(har)
        post_text = result["log"]["entries"][0]["request"]["postData"]["text"]
        assert "secret" not in post_text

    def test_redact_file_text(self, redactor, temp_dir):
        """Redacts text file."""
        file_path = temp_dir / "test.txt"
        file_path.write_text("api_key=sk-secret123abcdefgh\nEmail: test@example.com")

        output_path = temp_dir / "test_redacted.txt"
        redactor.redact_file(file_path, output_path)

        content = output_path.read_text()
        assert "sk-secret123abcdefgh" not in content
        assert "test@example.com" not in content

    def test_redact_file_json(self, redactor, temp_dir):
        """Redacts JSON file."""
        file_path = temp_dir / "config.json"
        file_path.write_text(
            json.dumps(
                {
                    "api_key": "sk-test",
                    "database": "mydb",
                }
            )
        )

        output_path = temp_dir / "config_redacted.json"
        redactor.redact_file(file_path, output_path)

        content = json.loads(output_path.read_text())
        assert "sk-test" not in str(content)
        assert content["database"] == "mydb"

    def test_redact_file_har(self, redactor, temp_dir):
        """Redacts HAR file."""
        file_path = temp_dir / "trace.har"
        har = {
            "log": {
                "entries": [
                    {
                        "request": {
                            "headers": [{"name": "Authorization", "value": "Bearer token123"}]
                        }
                    }
                ]
            }
        }
        file_path.write_text(json.dumps(har))

        output_path = temp_dir / "trace_redacted.har"
        redactor.redact_file(file_path, output_path)

        content = json.loads(output_path.read_text())
        auth_header = content["log"]["entries"][0]["request"]["headers"][0]
        assert "token123" not in auth_header["value"]

    def test_get_pattern_stats(self, redactor):
        """get_pattern_stats returns pattern info."""
        stats = redactor.get_pattern_stats()
        assert stats["total_patterns"] == len(DEFAULT_REDACTION_PATTERNS)
        assert "by_category" in stats

    def test_custom_patterns(self):
        """Can use custom patterns."""
        custom_patterns = [
            RedactionPattern(
                name="custom_id",
                pattern=r"CUSTOM-\d{6}",
                replacement="[CUSTOM_ID]",
                category=RedactionCategory.PII,
            )
        ]
        redactor = ArtifactRedactor(patterns=custom_patterns)

        text = "ID: CUSTOM-123456"
        result, count = redactor.redact_text(text)
        assert "CUSTOM-123456" not in result
        assert "[CUSTOM_ID]" in result

    def test_add_pattern(self):
        """Can add patterns dynamically."""
        redactor = ArtifactRedactor(patterns=[])
        redactor.add_pattern(
            RedactionPattern(
                name="secret_code",
                pattern=r"SECRET-\w+",
                replacement="[SECRET]",
                category=RedactionCategory.CREDENTIAL,
            )
        )

        text = "Code: SECRET-abc123"
        result, count = redactor.redact_text(text)
        assert "SECRET-abc123" not in result

    def test_redact_preserves_structure(self, redactor):
        """Redaction preserves data structure."""
        data = {
            "users": [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ],
            "settings": {
                "nested": {
                    "api_key": "sk-nested",
                }
            },
        }
        result = redactor.redact_dict(data)

        # Structure preserved
        assert len(result["users"]) == 2
        assert "settings" in result
        assert "nested" in result["settings"]

        # Names preserved (not sensitive)
        assert result["users"][0]["name"] == "Alice"

        # Sensitive values redacted
        assert "alice@example.com" not in str(result)
        assert "sk-nested" not in str(result)


class TestRedactionEdgeCases:
    """Edge case tests for redaction."""

    @pytest.fixture
    def redactor(self):
        return ArtifactRedactor()

    def test_empty_text(self, redactor):
        """Empty text returns empty tuple."""
        result, count = redactor.redact_text("")
        assert result == ""
        assert count == 0

    def test_no_matches(self, redactor):
        """Text without sensitive data unchanged."""
        text = "Hello, world!"
        result, count = redactor.redact_text(text)
        assert result == text
        assert count == 0

    def test_empty_dict(self, redactor):
        """Empty dict returns empty."""
        assert redactor.redact_dict({}) == {}

    def test_none_value_in_dict(self, redactor):
        """None values preserved."""
        data = {"user": None, "email": "test@example.com"}
        result = redactor.redact_dict(data)
        assert result["user"] is None

    def test_empty_har(self, redactor):
        """Empty HAR structure handled."""
        har = {"log": {"entries": []}}
        result = redactor.redact_har(har)
        assert result == har

    def test_malformed_har(self, redactor):
        """Malformed HAR handled gracefully."""
        har = {"not_a_log": True}
        result = redactor.redact_har(har)
        assert result == har  # Returns as-is

    def test_unicode_text(self, redactor):
        """Unicode text handled."""
        text = "Email: 用户@例子.中国"
        # Should not crash
        result, count = redactor.redact_text(text)
        assert isinstance(result, str)

    def test_large_text(self, redactor):
        """Large text handled efficiently."""
        text = "api_key=sk-test123abcdefghijkl\n" * 10000
        result, count = redactor.redact_text(text)
        assert "sk-test123abcdefghijkl" not in result
        assert len(result) > 0
