"""Tests for credential masking utility.

IMP-SEC-002: Add credential masking in logging and error outputs.
"""

from autopack.utils.credential_masking import (
    mask_credential,
    mask_dict_credentials,
    mask_url_credentials,
    create_safe_error_message,
)


class TestMaskCredential:
    """Tests for mask_credential function."""

    def test_mask_none_returns_not_set(self):
        """None value should return '<not set>'."""
        assert mask_credential(None) == "<not set>"

    def test_mask_empty_string_returns_empty(self):
        """Empty string should return '<empty>'."""
        assert mask_credential("") == "<empty>"

    def test_mask_short_credential(self):
        """Short credentials (<=8 chars) should be fully masked."""
        assert mask_credential("short") == "*****"
        assert mask_credential("12345678") == "********"

    def test_mask_standard_credential(self):
        """Standard credentials show first and last 4 chars."""
        result = mask_credential("sk-ant-api03-abcdefghijklmnop-xyz123")
        assert result == "sk-a...z123"
        # Verify the middle portion is hidden
        assert "abcdefghijklmnop" not in result

    def test_mask_anthropic_key(self):
        """Anthropic API key format should be properly masked."""
        key = "sk-ant-api03-1234567890abcdef1234567890abcdef-AAAA"
        result = mask_credential(key)
        assert result.startswith("sk-a")
        assert result.endswith("AAAA")
        assert "..." in result
        # Original key should not be recoverable
        assert "1234567890abcdef" not in result

    def test_mask_openai_key(self):
        """OpenAI API key format should be properly masked."""
        key = "sk-proj-abcdefghijklmnopqrstuvwxyz123456789"
        result = mask_credential(key)
        assert result.startswith("sk-p")
        assert "..." in result

    def test_mask_custom_visible_chars(self):
        """Custom visible_chars parameter should work."""
        result = mask_credential("1234567890abcdefghij", visible_chars=2)
        assert result == "12...ij"

        result = mask_credential("1234567890abcdefghij", visible_chars=6)
        # Last 6 chars of "1234567890abcdefghij" are "efghij"
        assert result == "123456...efghij"


class TestMaskDictCredentials:
    """Tests for mask_dict_credentials function."""

    def test_mask_simple_dict(self):
        """Simple dict with api_key should be masked."""
        data = {"api_key": "sk-secret12345678", "name": "test"}
        result = mask_dict_credentials(data)
        assert result["name"] == "test"
        assert result["api_key"] != "sk-secret12345678"
        assert "..." in result["api_key"]

    def test_mask_nested_dict(self):
        """Nested dicts should have credentials masked."""
        data = {
            "config": {
                "auth_token": "token-12345678901234",
                "host": "api.example.com",
            },
            "name": "service",
        }
        result = mask_dict_credentials(data)
        assert result["name"] == "service"
        assert result["config"]["host"] == "api.example.com"
        assert "..." in result["config"]["auth_token"]

    def test_mask_multiple_credentials(self):
        """Multiple credentials in dict should all be masked."""
        data = {
            "api_key": "key-12345678901234",
            "password": "pass-12345678901234",
            "secret": "sec-12345678901234",
            "normal_field": "not masked",
        }
        result = mask_dict_credentials(data)
        assert result["normal_field"] == "not masked"
        assert "..." in result["api_key"]
        assert "..." in result["password"]
        assert "..." in result["secret"]

    def test_mask_custom_sensitive_keys(self):
        """Custom sensitive keys should be masked."""
        data = {
            "custom_secret": "secret12345678901234",
            "api_key": "key-12345678901234",
        }
        result = mask_dict_credentials(data, sensitive_keys={"custom_secret"})
        assert "..." in result["custom_secret"]
        # api_key is not in custom keys, should not be masked
        assert result["api_key"] == "key-12345678901234"


class TestMaskUrlCredentials:
    """Tests for mask_url_credentials function."""

    def test_mask_basic_auth_password(self):
        """Basic auth password in URL should be masked."""
        url = "https://user:secretpassword@api.example.com/v1"
        result = mask_url_credentials(url)
        assert "secretpassword" not in result
        assert "****" in result
        assert "user:" in result

    def test_mask_api_key_param(self):
        """API key query parameter should be masked."""
        url = "https://api.example.com?api_key=sk-12345678901234"
        result = mask_url_credentials(url)
        assert "sk-12345678901234" not in result
        assert "api_key=" in result

    def test_mask_token_param(self):
        """Token query parameter should be masked."""
        url = "https://api.example.com?token=abc12345678901234xyz"
        result = mask_url_credentials(url)
        assert "abc12345678901234xyz" not in result

    def test_preserve_non_credential_params(self):
        """Non-credential query params should not be changed."""
        url = "https://api.example.com?name=test&page=1&api_key=secret123456789012"
        result = mask_url_credentials(url)
        assert "name=test" in result
        assert "page=1" in result
        assert "secret123456789012" not in result


class TestCreateSafeErrorMessage:
    """Tests for create_safe_error_message function."""

    def test_mask_api_key_in_error(self):
        """API keys in error messages should be masked."""
        err = ValueError("Invalid API key: sk-ant-api03-1234567890abcdef1234567890abcdef-AAAA")
        result = create_safe_error_message(err)
        # The full key should not appear in the result
        assert "sk-ant-api03-1234567890abcdef1234567890abcdef-AAAA" not in result
        # The masked version should show first and last parts with "..."
        assert "..." in result

    def test_context_prepended(self):
        """Context should be prepended to message."""
        err = ValueError("Some error")
        result = create_safe_error_message(err, context="API call failed")
        assert result.startswith("API call failed:")
        assert "Some error" in result

    def test_mask_long_hex_string(self):
        """Long hex strings (likely tokens) should be masked."""
        # 32+ char hex strings are suspicious
        err = ValueError("Token: abcdef1234567890abcdef1234567890abcdef1234")
        result = create_safe_error_message(err)
        assert "abcdef1234567890abcdef1234567890abcdef1234" not in result

    def test_preserve_non_credential_content(self):
        """Non-credential content should be preserved."""
        err = ValueError("Connection refused at host api.example.com:443")
        result = create_safe_error_message(err)
        assert "Connection refused" in result
        assert "api.example.com" in result


class TestIntegration:
    """Integration tests for credential masking."""

    def test_notification_channel_error_masking(self):
        """Errors from notification channels should have credentials masked."""
        # Test with API key format that the masking patterns recognize
        error_msg = "API call failed with token: sk-ant-api03-secretsecretsecretsecret-1234"
        err = Exception(error_msg)
        safe_msg = create_safe_error_message(err)
        # API key patterns should be masked
        assert "sk-ant-api03-secretsecretsecretsecret-1234" not in safe_msg
        assert "..." in safe_msg

    def test_telegram_bot_token_masking(self):
        """Telegram bot tokens in errors should be masked."""
        # Bot tokens look like: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
        token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
        result = mask_credential(token)
        assert token not in result
        assert "..." in result

    def test_github_token_masking(self):
        """GitHub tokens should be masked."""
        # GitHub PAT: ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
        token = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        result = mask_credential(token)
        assert token not in result
        assert result.startswith("ghp_")
