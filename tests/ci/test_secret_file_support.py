"""
Tests for *_FILE secret file support (PR-03 G4).

BUILD-198: Ensures secrets can be loaded from files via *_FILE env vars.
This enables Docker secrets and Kubernetes secret mounts.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch


class TestReadSecretFile:
    """Unit tests for _read_secret_file helper."""

    def test_read_secret_file_success(self, tmp_path: Path):
        """Should read secret from file successfully."""
        from autopack.config import _read_secret_file

        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("my-secret-value")

        result = _read_secret_file(str(secret_file), "TEST_SECRET")
        assert result == "my-secret-value"

    def test_read_secret_file_strips_whitespace(self, tmp_path: Path):
        """Should strip whitespace from secret value."""
        from autopack.config import _read_secret_file

        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("  my-secret-value  \n\n")

        result = _read_secret_file(str(secret_file), "TEST_SECRET")
        assert result == "my-secret-value"

    def test_read_secret_file_not_found(self, tmp_path: Path):
        """Should return None if file doesn't exist."""
        from autopack.config import _read_secret_file

        result = _read_secret_file(str(tmp_path / "nonexistent.txt"), "TEST_SECRET")
        assert result is None

    def test_read_secret_file_empty(self, tmp_path: Path):
        """Should raise RuntimeError for empty file."""
        from autopack.config import _read_secret_file

        secret_file = tmp_path / "empty.txt"
        secret_file.write_text("")

        with pytest.raises(RuntimeError) as excinfo:
            _read_secret_file(str(secret_file), "TEST_SECRET")

        assert "empty file" in str(excinfo.value).lower()

    def test_read_secret_file_whitespace_only(self, tmp_path: Path):
        """Should raise RuntimeError for whitespace-only file."""
        from autopack.config import _read_secret_file

        secret_file = tmp_path / "whitespace.txt"
        secret_file.write_text("   \n\n\t  ")

        with pytest.raises(RuntimeError) as excinfo:
            _read_secret_file(str(secret_file), "TEST_SECRET")

        assert "empty file" in str(excinfo.value).lower()


class TestGetSecret:
    """Unit tests for _get_secret helper."""

    def test_get_secret_from_env_var(self):
        """Should read secret from direct env var."""
        from autopack.config import _get_secret

        with patch.dict(os.environ, {"MY_SECRET": "env-value"}, clear=False):
            result = _get_secret("MY_SECRET", default="default")
            assert result == "env-value"

    def test_get_secret_from_file_takes_precedence(self, tmp_path: Path):
        """Should prefer *_FILE over direct env var."""
        from autopack.config import _get_secret

        secret_file = tmp_path / "secret.txt"
        secret_file.write_text("file-value")

        with patch.dict(
            os.environ,
            {
                "MY_SECRET": "env-value",
                "MY_SECRET_FILE": str(secret_file),
            },
            clear=False,
        ):
            result = _get_secret("MY_SECRET", file_env_var="MY_SECRET_FILE", default="default")
            assert result == "file-value"

    def test_get_secret_default_when_not_set(self):
        """Should return default when nothing is set."""
        from autopack.config import _get_secret

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NONEXISTENT_SECRET", None)
            os.environ.pop("NONEXISTENT_SECRET_FILE", None)

            result = _get_secret(
                "NONEXISTENT_SECRET",
                file_env_var="NONEXISTENT_SECRET_FILE",
                default="default-value",
            )
            assert result == "default-value"

    def test_get_secret_required_in_production_fails(self):
        """Should raise RuntimeError in production when required secret missing."""
        from autopack.config import _get_secret

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "production"},
            clear=False,
        ):
            os.environ.pop("REQUIRED_SECRET", None)
            os.environ.pop("REQUIRED_SECRET_FILE", None)

            with pytest.raises(RuntimeError) as excinfo:
                _get_secret(
                    "REQUIRED_SECRET",
                    file_env_var="REQUIRED_SECRET_FILE",
                    default="",
                    required_in_production=True,
                )

            assert "REQUIRED_SECRET" in str(excinfo.value)
            assert "production" in str(excinfo.value).lower()

    def test_get_secret_required_in_development_ok(self):
        """Should not fail in development when required secret missing."""
        from autopack.config import _get_secret

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "development"},
            clear=False,
        ):
            os.environ.pop("OPTIONAL_SECRET", None)
            os.environ.pop("OPTIONAL_SECRET_FILE", None)

            # Should not raise
            result = _get_secret(
                "OPTIONAL_SECRET",
                file_env_var="OPTIONAL_SECRET_FILE",
                default="",
                required_in_production=True,
            )
            assert result == ""


class TestDatabaseUrlFile:
    """Tests for DATABASE_URL_FILE support."""

    def test_database_url_from_file(self, tmp_path: Path):
        """DATABASE_URL_FILE should take precedence over DATABASE_URL."""
        from autopack import config as config_module

        secret_file = tmp_path / "db_url.txt"
        secret_file.write_text("postgresql://file:secret@localhost/filedb")

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://env:secret@localhost/envdb",
                "DATABASE_URL_FILE": str(secret_file),
                "AUTOPACK_ENV": "development",
            },
            clear=False,
        ):
            # Reload to pick up new env
            url = config_module.get_database_url()
            assert "filedb" in url

    def test_database_url_from_env(self):
        """DATABASE_URL should work when DATABASE_URL_FILE not set."""
        from autopack import config as config_module

        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://env:secret@localhost/envdb",
                "AUTOPACK_ENV": "development",
            },
            clear=False,
        ):
            os.environ.pop("DATABASE_URL_FILE", None)

            url = config_module.get_database_url()
            assert "envdb" in url


class TestJwtKeyFiles:
    """Tests for JWT_*_KEY_FILE support."""

    def test_jwt_private_key_from_file(self, tmp_path: Path):
        """JWT_PRIVATE_KEY_FILE should take precedence."""
        from autopack import config as config_module

        key_file = tmp_path / "private_key.pem"
        key_file.write_text(
            "-----BEGIN RSA PRIVATE KEY-----\nFILE_KEY\n-----END RSA PRIVATE KEY-----"
        )

        with patch.dict(
            os.environ,
            {
                "JWT_PRIVATE_KEY": "ENV_KEY",
                "JWT_PRIVATE_KEY_FILE": str(key_file),
                "AUTOPACK_ENV": "development",
            },
            clear=False,
        ):
            key = config_module.get_jwt_private_key()
            assert "FILE_KEY" in key

    def test_jwt_public_key_from_file(self, tmp_path: Path):
        """JWT_PUBLIC_KEY_FILE should take precedence."""
        from autopack import config as config_module

        key_file = tmp_path / "public_key.pem"
        key_file.write_text(
            "-----BEGIN RSA PUBLIC KEY-----\nFILE_KEY\n-----END RSA PUBLIC KEY-----"
        )

        with patch.dict(
            os.environ,
            {
                "JWT_PUBLIC_KEY": "ENV_KEY",
                "JWT_PUBLIC_KEY_FILE": str(key_file),
                "AUTOPACK_ENV": "development",
            },
            clear=False,
        ):
            key = config_module.get_jwt_public_key()
            assert "FILE_KEY" in key


class TestApiKeyFile:
    """Tests for AUTOPACK_API_KEY_FILE support."""

    def test_api_key_from_file(self, tmp_path: Path):
        """AUTOPACK_API_KEY_FILE should take precedence."""
        from autopack import config as config_module

        key_file = tmp_path / "api_key.txt"
        key_file.write_text("file-api-key-12345")

        with patch.dict(
            os.environ,
            {
                "AUTOPACK_API_KEY": "env-api-key",
                "AUTOPACK_API_KEY_FILE": str(key_file),
                "AUTOPACK_ENV": "development",
            },
            clear=False,
        ):
            key = config_module.get_api_key()
            assert key == "file-api-key-12345"

    def test_api_key_from_env(self):
        """AUTOPACK_API_KEY should work when file not set."""
        from autopack import config as config_module

        with patch.dict(
            os.environ,
            {
                "AUTOPACK_API_KEY": "env-api-key-12345",
                "AUTOPACK_ENV": "development",
            },
            clear=False,
        ):
            os.environ.pop("AUTOPACK_API_KEY_FILE", None)

            key = config_module.get_api_key()
            assert key == "env-api-key-12345"

    def test_api_key_required_in_production(self):
        """Should fail in production without API key."""
        from autopack import config as config_module

        with patch.dict(
            os.environ,
            {"AUTOPACK_ENV": "production"},
            clear=False,
        ):
            os.environ.pop("AUTOPACK_API_KEY", None)
            os.environ.pop("AUTOPACK_API_KEY_FILE", None)

            with pytest.raises(RuntimeError) as excinfo:
                config_module.get_api_key()

            assert "AUTOPACK_API_KEY" in str(excinfo.value)


class TestSecretFileDocumentation:
    """Verify *_FILE support is documented."""

    def test_deployment_docs_mention_file_secrets(self):
        """DEPLOYMENT.md should document *_FILE secret support."""
        docs_path = "docs/DEPLOYMENT.md"

        if not os.path.exists(docs_path):
            pytest.skip("DEPLOYMENT.md not found")

        with open(docs_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for *_FILE documentation
        assert "_FILE" in content, "DEPLOYMENT.md should document *_FILE secret file support"
