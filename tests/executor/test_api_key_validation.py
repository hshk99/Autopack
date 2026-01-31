"""Tests for IMP-SEC-008 - API key regex validation.

This module tests the regex-based API key format validation
for different providers (GLM, Anthropic, OpenAI, Autopack, etc.)
to prevent invalid/malformed keys from being used.
"""

import pytest

from autopack.executor.run_lifecycle_manager import (
    API_KEY_PATTERNS,
    ApiKeyValidationError,
    RunLifecycleManager,
)
from autopack.executor.startup_validation import StartupValidator


class TestAPIKeyPatterns:
    """Test individual API key validation patterns."""

    def test_glm_key_valid(self):
        """Test that valid GLM keys match the pattern."""
        valid_keys = [
            "glm-4-plus-api-key-1234567890",
            "GLM_KEY_1234567890abcdef",
            "my-api-key_with_underscores123",
        ]
        for key in valid_keys:
            assert API_KEY_PATTERNS["glm"].match(key), f"Valid GLM key rejected: {key}"

    def test_glm_key_invalid(self):
        """Test that invalid GLM keys don't match the pattern."""
        invalid_keys = [
            "",  # Empty
            "short",  # Too short
            "glm@key#invalid",  # Invalid characters (@ and # not allowed)
            "123",  # Too short
            "key@with#invalid$chars",  # Invalid characters
        ]
        for key in invalid_keys:
            assert not API_KEY_PATTERNS["glm"].match(key), f"Invalid GLM key accepted: {key}"

    def test_anthropic_key_valid(self):
        """Test that valid Anthropic keys match the pattern."""
        valid_keys = [
            "sk-ant-v1-1234567890abcdef1234567890abcdef",
            "sk-0123456789abcdefghijklmnopqrstuv",
        ]
        for key in valid_keys:
            assert API_KEY_PATTERNS["anthropic"].match(key), f"Valid Anthropic key rejected: {key}"

    def test_anthropic_key_invalid(self):
        """Test that invalid Anthropic keys don't match the pattern."""
        invalid_keys = [
            "",  # Empty
            "no-prefix-key",  # Missing sk- prefix
            "sk-",  # Prefix only
            "sk-short",  # Too short
            "sk-@invalid@chars1234567890",  # Invalid characters
        ]
        for key in invalid_keys:
            assert not API_KEY_PATTERNS["anthropic"].match(
                key
            ), f"Invalid Anthropic key accepted: {key}"

    def test_openai_key_valid(self):
        """Test that valid OpenAI keys match the pattern."""
        valid_keys = [
            "sk-proj-1234567890abcdef1234567890abcdef",
            "sk-0123456789abcdefghijklmnopqrstuv",
        ]
        for key in valid_keys:
            assert API_KEY_PATTERNS["openai"].match(key), f"Valid OpenAI key rejected: {key}"

    def test_openai_key_invalid(self):
        """Test that invalid OpenAI keys don't match the pattern."""
        invalid_keys = [
            "",  # Empty
            "no-prefix-key",  # Missing sk- prefix
            "sk-",  # Prefix only
            "sk-short",  # Too short
        ]
        for key in invalid_keys:
            assert not API_KEY_PATTERNS["openai"].match(key), f"Invalid OpenAI key accepted: {key}"

    def test_autopack_key_valid(self):
        """Test that valid Autopack keys match the pattern."""
        valid_keys = [
            "autopack_key_1234567890",
            "AUTOPACK-API-KEY-123",
            "my_autopack_key_with_dashes-123",
        ]
        for key in valid_keys:
            assert API_KEY_PATTERNS["autopack"].match(key), f"Valid Autopack key rejected: {key}"

    def test_autopack_key_invalid(self):
        """Test that invalid Autopack keys don't match the pattern."""
        invalid_keys = [
            "",  # Empty
            "short",  # Too short
            "key@with#invalid$chars",  # Invalid characters
        ]
        for key in invalid_keys:
            assert not API_KEY_PATTERNS["autopack"].match(
                key
            ), f"Invalid Autopack key accepted: {key}"


class TestStartupValidatorValidation:
    """Test API key validation in StartupValidator."""

    def test_valid_glm_key_only(self):
        """Test that valid GLM key alone passes validation."""
        validator = StartupValidator(glm_key="glm-api-key-1234567890")
        # Should not raise
        validator.validate_api_keys()

    def test_valid_anthropic_key_only(self):
        """Test that valid Anthropic key alone passes validation."""
        validator = StartupValidator(anthropic_key="sk-ant-v1-1234567890abcdef1234567890abcdef")
        # Should not raise
        validator.validate_api_keys()

    def test_valid_openai_key_only(self):
        """Test that valid OpenAI key alone passes validation."""
        validator = StartupValidator(openai_key="sk-proj-1234567890abcdef1234567890abcdef")
        # Should not raise
        validator.validate_api_keys()

    def test_no_llm_keys_raises_error(self):
        """Test that missing all LLM keys raises error."""
        validator = StartupValidator()
        with pytest.raises(ValueError, match="At least one LLM API key required"):
            validator.validate_api_keys()

    def test_invalid_glm_key_raises_error(self):
        """Test that invalid GLM key format raises error."""
        validator = StartupValidator(glm_key="key@with#invalid$chars")
        with pytest.raises(ValueError, match="GLM_API_KEY.*invalid format"):
            validator.validate_api_keys()

    def test_invalid_anthropic_key_raises_error(self):
        """Test that invalid Anthropic key format raises error."""
        validator = StartupValidator(anthropic_key="no-prefix-key")
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY.*invalid format"):
            validator.validate_api_keys()

    def test_invalid_openai_key_raises_error(self):
        """Test that invalid OpenAI key format raises error."""
        validator = StartupValidator(openai_key="no-prefix-key")
        with pytest.raises(ValueError, match="OPENAI_API_KEY.*invalid format"):
            validator.validate_api_keys()

    def test_valid_autopack_key(self):
        """Test that valid Autopack key passes validation."""
        validator = StartupValidator(
            anthropic_key="sk-ant-v1-1234567890abcdef1234567890abcdef",
            autopack_key="autopack_key_1234567890",
        )
        # Should not raise
        validator.validate_api_keys()

    def test_invalid_autopack_key_raises_error(self):
        """Test that invalid Autopack key format raises error."""
        validator = StartupValidator(
            anthropic_key="sk-ant-v1-1234567890abcdef1234567890abcdef",
            autopack_key="invalid",
        )
        with pytest.raises(ValueError, match="AUTOPACK_API_KEY.*invalid format"):
            validator.validate_api_keys()

    def test_whitespace_autopack_key_raises_error(self):
        """Test that whitespace-only Autopack key raises error."""
        validator = StartupValidator(
            anthropic_key="sk-ant-v1-1234567890abcdef1234567890abcdef",
            autopack_key="   ",  # Whitespace only
        )
        with pytest.raises(ValueError, match="AUTOPACK_API_KEY.*empty or invalid format"):
            validator.validate_api_keys()

    def test_multiple_keys_with_one_invalid(self):
        """Test that validation catches the first invalid key in multiple keys."""
        validator = StartupValidator(
            glm_key="glm-valid-key-1234567890",
            anthropic_key="invalid_no_prefix",
            openai_key="sk-valid-openai-key-1234567890abcdef",
        )
        with pytest.raises(ValueError, match="Invalid API key"):
            validator.validate_api_keys()


class TestRunLifecycleManagerValidation:
    """Test API key validation in RunLifecycleManager."""

    def test_valid_glm_key_only(self):
        """Test that valid GLM key alone passes validation."""
        manager = RunLifecycleManager(
            run_id="test-run",
            glm_key="glm-api-key-1234567890",
        )
        # Should not raise
        manager.validate_api_keys()

    def test_valid_anthropic_key_only(self):
        """Test that valid Anthropic key alone passes validation."""
        manager = RunLifecycleManager(
            run_id="test-run",
            anthropic_key="sk-ant-v1-1234567890abcdef1234567890abcdef",
        )
        # Should not raise
        manager.validate_api_keys()

    def test_no_llm_keys_raises_error(self):
        """Test that missing all LLM keys raises error."""
        manager = RunLifecycleManager(run_id="test-run")
        with pytest.raises(ApiKeyValidationError, match="At least one LLM API key required"):
            manager.validate_api_keys()

    def test_invalid_glm_key_raises_error(self):
        """Test that invalid GLM key format raises error."""
        manager = RunLifecycleManager(
            run_id="test-run",
            glm_key="key@with#invalid$chars",
        )
        with pytest.raises(ApiKeyValidationError, match="GLM_API_KEY.*invalid format"):
            manager.validate_api_keys()

    def test_valid_autopack_key(self):
        """Test that valid Autopack key passes validation."""
        manager = RunLifecycleManager(
            run_id="test-run",
            anthropic_key="sk-ant-v1-1234567890abcdef1234567890abcdef",
            autopack_key="autopack_key_1234567890",
        )
        # Should not raise
        manager.validate_api_keys()

    def test_invalid_autopack_key_raises_error(self):
        """Test that invalid Autopack key format raises error."""
        manager = RunLifecycleManager(
            run_id="test-run",
            anthropic_key="sk-ant-v1-1234567890abcdef1234567890abcdef",
            autopack_key="invalid",
        )
        with pytest.raises(ApiKeyValidationError, match="AUTOPACK_API_KEY.*invalid format"):
            manager.validate_api_keys()
