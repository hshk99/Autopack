"""Tests for IMP-SEC-001: Bind address configuration security.

These tests verify that the API server bind address configuration
properly defaults to localhost and rejects non-local addresses
unless explicitly allowed.
"""

import pytest
from pydantic import ValidationError

from autopack.config import Settings, _LOCAL_ADDRESSES


class TestBindAddressDefaults:
    """Test default bind address configuration."""

    def test_default_bind_address_is_localhost(self):
        """Default bind address should be 127.0.0.1 (localhost)."""
        settings = Settings()
        assert settings.autopack_bind_address == "127.0.0.1"

    def test_default_allow_non_local_is_false(self):
        """Non-local binding should be disabled by default."""
        settings = Settings()
        assert settings.autopack_allow_non_local is False


class TestNonLocalBindingRejection:
    """Test that non-local addresses are rejected by default."""

    def test_non_local_binding_rejected_by_default(self):
        """Non-local IP addresses should be rejected without explicit opt-in."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(autopack_bind_address="192.168.1.100")

        error_msg = str(exc_info.value)
        assert "Non-local bind address" in error_msg
        assert "192.168.1.100" in error_msg
        assert "AUTOPACK_ALLOW_NON_LOCAL" in error_msg

    def test_external_ip_rejected_by_default(self):
        """External/public IP addresses should be rejected without opt-in."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(autopack_bind_address="10.0.0.1")

        assert "Non-local bind address" in str(exc_info.value)

    def test_custom_hostname_rejected_by_default(self):
        """Custom hostnames (not localhost) should be rejected without opt-in."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(autopack_bind_address="myserver.local")

        assert "Non-local bind address" in str(exc_info.value)


class TestNonLocalBindingWithFlag:
    """Test that non-local addresses are allowed with explicit flag."""

    def test_non_local_binding_allowed_with_flag(self):
        """Non-local addresses should be allowed when autopack_allow_non_local=True."""
        settings = Settings(
            autopack_bind_address="192.168.1.100",
            autopack_allow_non_local=True,
        )
        assert settings.autopack_bind_address == "192.168.1.100"
        assert settings.autopack_allow_non_local is True

    def test_external_ip_allowed_with_flag(self):
        """External IPs should be allowed with explicit opt-in."""
        settings = Settings(
            autopack_bind_address="10.0.0.1",
            autopack_allow_non_local=True,
        )
        assert settings.autopack_bind_address == "10.0.0.1"

    def test_any_interface_allowed_with_flag(self):
        """Binding to all interfaces (0.0.0.0) with non-local flag should work."""
        # Note: 0.0.0.0 is in _LOCAL_ADDRESSES so it works without the flag too
        settings = Settings(
            autopack_bind_address="0.0.0.0",
            autopack_allow_non_local=True,
        )
        assert settings.autopack_bind_address == "0.0.0.0"


class TestLocalhostVariants:
    """Test that all localhost variants are always allowed."""

    def test_localhost_variants_always_allowed(self):
        """All common localhost variants should be allowed without opt-in."""
        localhost_variants = ["127.0.0.1", "localhost", "::1", "0.0.0.0"]

        for variant in localhost_variants:
            settings = Settings(autopack_bind_address=variant)
            assert settings.autopack_bind_address == variant
            assert settings.autopack_allow_non_local is False  # Shouldn't need this

    def test_localhost_case_insensitive(self):
        """Localhost string should be case-insensitive."""
        settings = Settings(autopack_bind_address="LOCALHOST")
        assert settings.autopack_bind_address == "LOCALHOST"

    def test_localhost_with_whitespace_trimmed(self):
        """Whitespace around localhost variants should be handled."""
        settings = Settings(autopack_bind_address="  127.0.0.1  ")
        # Value is preserved but validation normalizes for comparison
        assert settings.autopack_bind_address == "  127.0.0.1  "


class TestLocalAddressesConstant:
    """Test the _LOCAL_ADDRESSES constant."""

    def test_local_addresses_contains_expected_values(self):
        """_LOCAL_ADDRESSES should contain all expected local address variants."""
        expected = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
        assert _LOCAL_ADDRESSES == expected

    def test_local_addresses_is_frozen(self):
        """_LOCAL_ADDRESSES should be immutable."""
        assert isinstance(_LOCAL_ADDRESSES, frozenset)
