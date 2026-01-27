"""Tests for IMP-SEC-001: Bind address configuration security.

These tests verify that the API server bind address configuration
properly defaults to localhost and rejects non-local addresses
unless explicitly allowed.

Note: Settings uses pydantic-settings which loads from env vars.
We use monkeypatch to set env vars before creating Settings instances.
"""

import os

import pytest
from pydantic import ValidationError

from autopack.config import _LOCAL_ADDRESSES, Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Clean bind address related env vars before each test."""
    for key in list(os.environ.keys()):
        if "BIND" in key or "ALLOW_NON_LOCAL" in key:
            monkeypatch.delenv(key, raising=False)
    # Also clean the specific vars we use
    monkeypatch.delenv("AUTOPACK_BIND_ADDRESS", raising=False)
    monkeypatch.delenv("AUTOPACK_ALLOW_NON_LOCAL", raising=False)


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

    def test_non_local_binding_rejected_by_default(self, monkeypatch):
        """Non-local IP addresses should be rejected without explicit opt-in."""
        monkeypatch.setenv("AUTOPACK_BIND_ADDRESS", "192.168.1.100")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        error_msg = str(exc_info.value)
        assert "Non-local bind address" in error_msg
        assert "192.168.1.100" in error_msg
        assert "AUTOPACK_ALLOW_NON_LOCAL" in error_msg

    def test_external_ip_rejected_by_default(self, monkeypatch):
        """External/public IP addresses should be rejected without opt-in."""
        monkeypatch.setenv("AUTOPACK_BIND_ADDRESS", "10.0.0.1")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "Non-local bind address" in str(exc_info.value)

    def test_custom_hostname_rejected_by_default(self, monkeypatch):
        """Custom hostnames (not localhost) should be rejected without opt-in."""
        monkeypatch.setenv("AUTOPACK_BIND_ADDRESS", "myserver.local")

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "Non-local bind address" in str(exc_info.value)


class TestNonLocalBindingWithFlag:
    """Test that non-local addresses are allowed with explicit flag."""

    def test_non_local_binding_allowed_with_flag(self, monkeypatch):
        """Non-local addresses should be allowed when autopack_allow_non_local=True."""
        monkeypatch.setenv("AUTOPACK_BIND_ADDRESS", "192.168.1.100")
        monkeypatch.setenv("AUTOPACK_ALLOW_NON_LOCAL", "true")

        settings = Settings()
        assert settings.autopack_bind_address == "192.168.1.100"
        assert settings.autopack_allow_non_local is True

    def test_external_ip_allowed_with_flag(self, monkeypatch):
        """External IPs should be allowed with explicit opt-in."""
        monkeypatch.setenv("AUTOPACK_BIND_ADDRESS", "10.0.0.1")
        monkeypatch.setenv("AUTOPACK_ALLOW_NON_LOCAL", "true")

        settings = Settings()
        assert settings.autopack_bind_address == "10.0.0.1"

    def test_any_interface_allowed_with_flag(self, monkeypatch):
        """Binding to all interfaces (0.0.0.0) with non-local flag should work."""
        # Note: 0.0.0.0 is in _LOCAL_ADDRESSES so it works without the flag too
        monkeypatch.setenv("AUTOPACK_BIND_ADDRESS", "0.0.0.0")
        monkeypatch.setenv("AUTOPACK_ALLOW_NON_LOCAL", "true")

        settings = Settings()
        assert settings.autopack_bind_address == "0.0.0.0"


class TestLocalhostVariants:
    """Test that all localhost variants are always allowed."""

    def test_localhost_variants_always_allowed(self, monkeypatch):
        """All common localhost variants should be allowed without opt-in."""
        localhost_variants = ["127.0.0.1", "localhost", "::1", "0.0.0.0"]

        for variant in localhost_variants:
            monkeypatch.setenv("AUTOPACK_BIND_ADDRESS", variant)
            settings = Settings()
            assert settings.autopack_bind_address == variant
            assert settings.autopack_allow_non_local is False  # Shouldn't need this

    def test_localhost_case_insensitive(self, monkeypatch):
        """Localhost string should be case-insensitive."""
        monkeypatch.setenv("AUTOPACK_BIND_ADDRESS", "LOCALHOST")
        settings = Settings()
        assert settings.autopack_bind_address == "LOCALHOST"

    def test_localhost_with_whitespace_trimmed(self, monkeypatch):
        """Whitespace around localhost variants should be handled."""
        monkeypatch.setenv("AUTOPACK_BIND_ADDRESS", "  127.0.0.1  ")
        settings = Settings()
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
