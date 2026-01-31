"""Tests for JWT key security and encryption.

Tests environment-aware key encryption, ensuring production mode
requires encrypted keys and development mode handles unencrypted keys safely.
"""

import os
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from autopack.auth.security import get_key_encryption


class TestGetKeyEncryption:
    """Test environment-aware key encryption selection."""

    def test_production_requires_passphrase(self):
        """Test that production mode requires JWT_KEY_PASSPHRASE."""
        with patch("autopack.auth.security.is_production", return_value=True):
            with patch.dict(os.environ, {}, clear=False):
                # Remove passphrase from environment
                os.environ.pop("JWT_KEY_PASSPHRASE", None)
                with pytest.raises(
                    ValueError,
                    match="JWT_KEY_PASSPHRASE environment variable required",
                ):
                    get_key_encryption()

    def test_production_with_passphrase(self):
        """Test that production mode with passphrase returns BestAvailableEncryption."""
        with patch("autopack.auth.security.is_production", return_value=True):
            with patch.dict(
                os.environ,
                {"JWT_KEY_PASSPHRASE": "test-passphrase-123"},
                clear=False,
            ):
                encryption = get_key_encryption()
                assert isinstance(encryption, serialization.BestAvailableEncryption)

    def test_development_mode_no_passphrase(self):
        """Test that development mode works without passphrase."""
        with patch("autopack.auth.security.is_production", return_value=False):
            encryption = get_key_encryption()
            assert isinstance(encryption, serialization.NoEncryption)

    def test_development_mode_logs_warning(self, caplog):
        """Test that development mode logs a warning about unencrypted keys."""
        with patch("autopack.auth.security.is_production", return_value=False):
            get_key_encryption()
            assert "unencrypted JWT keys in development mode" in caplog.text

    def test_production_mode_logs_no_warning(self, caplog):
        """Test that production mode does not log development warnings."""
        with patch("autopack.auth.security.is_production", return_value=True):
            with patch.dict(
                os.environ,
                {"JWT_KEY_PASSPHRASE": "test-passphrase-123"},
                clear=False,
            ):
                get_key_encryption()
                assert "unencrypted JWT keys in development mode" not in caplog.text


class TestEphemeralKeyGeneration:
    """Test that ephemeral key generation uses environment-aware encryption."""

    def test_development_ephemeral_keys_unencrypted(self):
        """Test that ephemeral keys in development are unencrypted."""
        with patch("autopack.auth.security.is_production", return_value=False):
            with patch("autopack.config.is_production", return_value=False):
                encryption = get_key_encryption()

                # Generate key with unencrypted algorithm
                key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                priv_pem = key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=encryption,
                ).decode("utf-8")

                # Verify PEM can be loaded without password
                loaded_key = serialization.load_pem_private_key(
                    priv_pem.encode("utf-8"), password=None
                )
                assert loaded_key is not None

    def test_production_ephemeral_keys_encrypted(self):
        """Test that ephemeral keys in production can be encrypted."""
        with patch("autopack.auth.security.is_production", return_value=True):
            passphrase = "test-passphrase-123"
            with patch.dict(os.environ, {"JWT_KEY_PASSPHRASE": passphrase}, clear=False):
                encryption = get_key_encryption()

                # Generate key with encrypted algorithm
                key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                priv_pem = key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=encryption,
                ).decode("utf-8")

                # Verify PEM cannot be loaded without password
                with pytest.raises(TypeError):
                    serialization.load_pem_private_key(priv_pem.encode("utf-8"), password=None)

                # Verify PEM can be loaded with correct password
                loaded_key = serialization.load_pem_private_key(
                    priv_pem.encode("utf-8"),
                    password=passphrase.encode("utf-8"),
                )
                assert loaded_key is not None

    def test_encrypted_key_with_wrong_passphrase_fails(self):
        """Test that encrypted keys cannot be loaded with wrong passphrase."""
        with patch("autopack.auth.security.is_production", return_value=True):
            passphrase = "test-passphrase-123"
            with patch.dict(os.environ, {"JWT_KEY_PASSPHRASE": passphrase}, clear=False):
                encryption = get_key_encryption()

                # Generate key with encrypted algorithm
                key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                priv_pem = key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=encryption,
                ).decode("utf-8")

                # Verify loading with wrong password fails
                with pytest.raises(ValueError):
                    serialization.load_pem_private_key(
                        priv_pem.encode("utf-8"),
                        password="wrong-passphrase".encode("utf-8"),
                    )


class TestKeyEncryptionIntegration:
    """Integration tests for key encryption in ensure_keys()."""

    @patch("autopack.auth.security.is_production")
    @patch("autopack.config.is_production")
    @patch("autopack.auth.security.settings")
    def test_ensure_keys_development_unencrypted(
        self, mock_settings, mock_config_prod, mock_auth_prod
    ):
        """Test that ensure_keys generates unencrypted keys in development."""
        mock_config_prod.return_value = False
        mock_auth_prod.return_value = False
        mock_settings.jwt_private_key = None
        mock_settings.jwt_public_key = None

        # Import after mocking
        from autopack.auth.security import ensure_keys

        ensure_keys()

        # Verify private key was set
        assert mock_settings.jwt_private_key is not None
        # Verify key can be loaded without password
        serialization.load_pem_private_key(
            mock_settings.jwt_private_key.encode("utf-8"), password=None
        )

    @patch("autopack.auth.security.is_production")
    @patch("autopack.config.is_production")
    @patch("autopack.auth.security.settings")
    def test_ensure_keys_production_requires_keys(
        self, mock_settings, mock_config_prod, mock_auth_prod
    ):
        """Test that ensure_keys fails in production without configured keys."""
        mock_config_prod.return_value = True
        mock_auth_prod.return_value = True
        mock_settings.jwt_private_key = None
        mock_settings.jwt_public_key = None

        # Import after mocking
        from autopack.auth.security import ensure_keys

        with pytest.raises(
            RuntimeError,
            match="JWT keys not configured in production mode",
        ):
            ensure_keys()
