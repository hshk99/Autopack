"""
Tests for artifact boundary hardening (PR-06 G5).

BUILD-199: Ensures artifact endpoints enforce size caps, optional redaction,
and return safe metadata for UI/operator consumption.
"""

import os
import pytest
from datetime import datetime, timezone
from unittest.mock import patch


class TestArtifactSizeCaps:
    """PR-06 G5: Verify artifact size cap enforcement."""

    @pytest.fixture
    def run_with_large_artifact(self, client, db_session, tmp_path):
        """Create a run with a large artifact file."""
        from autopack import models

        run_id = "test-run-size-cap"

        run = models.Run(
            id=run_id,
            state=models.RunState.DONE_SUCCESS,
            safety_profile="normal",
            run_scope="multi_tier",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        # Create artifact directory
        run_dir = tmp_path / "autopack" / "runs" / run_id / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Create a file larger than default cap (1MB)
        large_file = run_dir / "large_artifact.txt"
        # Create 1.5MB file
        content = "x" * (1_500_000)
        large_file.write_text(content)

        # Create a small file for comparison
        small_file = run_dir / "small_artifact.txt"
        small_file.write_text("Small content for testing")

        return run_id, run_dir

    def test_large_file_truncated(self, client, run_with_large_artifact, tmp_path):
        """Large files are truncated at size cap."""
        run_id, run_dir = run_with_large_artifact

        with patch("autopack.main.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            # Set a small cap for testing (100 bytes)
            with patch("autopack.main.settings") as mock_settings:
                mock_settings.artifact_read_size_cap_bytes = 100
                mock_settings.artifact_redaction_enabled = False

                response = client.get(f"/runs/{run_id}/artifacts/file?path=large_artifact.txt")
                assert response.status_code == 200

                # Check truncation header
                assert response.headers.get("X-Artifact-Truncated") == "true"
                assert int(response.headers.get("X-Artifact-Original-Size")) == 1_500_000

                # Content should contain truncation marker
                assert "[TRUNCATED:" in response.text

    def test_small_file_not_truncated(self, client, run_with_large_artifact, tmp_path):
        """Small files are returned in full."""
        run_id, run_dir = run_with_large_artifact

        with patch("autopack.main.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            with patch("autopack.main.settings") as mock_settings:
                mock_settings.artifact_read_size_cap_bytes = 1_048_576  # 1MB
                mock_settings.artifact_redaction_enabled = False

                response = client.get(f"/runs/{run_id}/artifacts/file?path=small_artifact.txt")
                assert response.status_code == 200

                # Check not truncated
                assert response.headers.get("X-Artifact-Truncated") == "false"
                assert "Small content for testing" in response.text
                assert "[TRUNCATED:" not in response.text

    def test_size_cap_zero_disables_truncation(self, client, run_with_large_artifact, tmp_path):
        """Size cap of 0 disables truncation (dev mode)."""
        run_id, run_dir = run_with_large_artifact

        with patch("autopack.main.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            # Patch the settings module's settings object directly
            from autopack import config

            original_cap = config.settings.artifact_read_size_cap_bytes
            original_redact = config.settings.artifact_redaction_enabled
            try:
                config.settings.artifact_read_size_cap_bytes = 0  # Unlimited
                config.settings.artifact_redaction_enabled = False

                response = client.get(f"/runs/{run_id}/artifacts/file?path=large_artifact.txt")
                assert response.status_code == 200

                # Should not be truncated
                assert response.headers.get("X-Artifact-Truncated") == "false"
                assert "[TRUNCATED:" not in response.text
            finally:
                config.settings.artifact_read_size_cap_bytes = original_cap
                config.settings.artifact_redaction_enabled = original_redact


class TestArtifactRedaction:
    """PR-06 G5: Verify artifact redaction functionality."""

    @pytest.fixture
    def run_with_sensitive_artifact(self, client, db_session, tmp_path):
        """Create a run with a sensitive artifact file."""
        from autopack import models

        run_id = "test-run-redaction"

        run = models.Run(
            id=run_id,
            state=models.RunState.DONE_SUCCESS,
            safety_profile="normal",
            run_scope="multi_tier",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        # Create artifact directory
        run_dir = tmp_path / "autopack" / "runs" / run_id / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Create a file with sensitive data
        # Note: Using obviously fake test values to avoid triggering secret scanners
        sensitive_file = run_dir / "config_dump.txt"
        sensitive_content = """
        Configuration dump:
        api_key = "sk_test_FAKE_KEY_FOR_TESTING_ONLY_1234567890"
        password = "super_secret_password_123"
        Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U
        Email: user@example.com
        Phone: 555-123-4567
        """
        sensitive_file.write_text(sensitive_content)

        return run_id, run_dir

    def test_redaction_via_query_param(self, client, run_with_sensitive_artifact, tmp_path):
        """Redaction can be enabled via query parameter."""
        run_id, run_dir = run_with_sensitive_artifact

        with patch("autopack.main.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            with patch("autopack.main.settings") as mock_settings:
                mock_settings.artifact_read_size_cap_bytes = 0  # Unlimited
                mock_settings.artifact_redaction_enabled = False  # Off by default

                response = client.get(
                    f"/runs/{run_id}/artifacts/file?path=config_dump.txt&redact=true"
                )
                assert response.status_code == 200

                # Check redaction header
                assert response.headers.get("X-Artifact-Redacted") == "true"
                redaction_count = int(response.headers.get("X-Artifact-Redaction-Count", "0"))
                assert redaction_count > 0

                # Sensitive content should be redacted
                assert "sk_test_FAKE_KEY" not in response.text
                assert "super_secret_password" not in response.text
                assert "[REDACTED" in response.text

    def test_redaction_via_config(self, client, run_with_sensitive_artifact, tmp_path):
        """Redaction can be enabled via config setting."""
        run_id, run_dir = run_with_sensitive_artifact

        with patch("autopack.main.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            # Patch the settings module's settings object directly
            from autopack import config

            original_cap = config.settings.artifact_read_size_cap_bytes
            original_redact = config.settings.artifact_redaction_enabled
            try:
                config.settings.artifact_read_size_cap_bytes = 0  # Unlimited
                config.settings.artifact_redaction_enabled = True  # On by default

                response = client.get(f"/runs/{run_id}/artifacts/file?path=config_dump.txt")
                assert response.status_code == 200

                # Should be redacted
                assert response.headers.get("X-Artifact-Redacted") == "true"
                assert "[REDACTED" in response.text
            finally:
                config.settings.artifact_read_size_cap_bytes = original_cap
                config.settings.artifact_redaction_enabled = original_redact

    def test_redaction_disabled_shows_original(self, client, run_with_sensitive_artifact, tmp_path):
        """With redaction disabled, original content is returned."""
        run_id, run_dir = run_with_sensitive_artifact

        with patch("autopack.main.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            with patch("autopack.main.settings") as mock_settings:
                mock_settings.artifact_read_size_cap_bytes = 0  # Unlimited
                mock_settings.artifact_redaction_enabled = False

                response = client.get(f"/runs/{run_id}/artifacts/file?path=config_dump.txt")
                assert response.status_code == 200

                # Should not be redacted
                assert response.headers.get("X-Artifact-Redacted") == "false"
                # Original sensitive content visible
                assert "api_key" in response.text


class TestArtifactResponseMetadata:
    """PR-06 G5: Verify response metadata for UI consumption."""

    @pytest.fixture
    def run_with_artifact(self, client, db_session, tmp_path):
        """Create a run with an artifact file."""
        from autopack import models

        run_id = "test-run-metadata"

        run = models.Run(
            id=run_id,
            state=models.RunState.DONE_SUCCESS,
            safety_profile="normal",
            run_scope="multi_tier",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

        # Create artifact directory
        run_dir = tmp_path / "autopack" / "runs" / run_id / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Create test file
        test_file = run_dir / "test_artifact.txt"
        test_file.write_text("Test content for metadata checks")

        return run_id, run_dir

    def test_response_includes_original_size_header(self, client, run_with_artifact, tmp_path):
        """Response includes X-Artifact-Original-Size header."""
        run_id, run_dir = run_with_artifact

        with patch("autopack.main.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            with patch("autopack.main.settings") as mock_settings:
                mock_settings.artifact_read_size_cap_bytes = 0
                mock_settings.artifact_redaction_enabled = False

                response = client.get(f"/runs/{run_id}/artifacts/file?path=test_artifact.txt")
                assert response.status_code == 200

                # Check size header exists and is valid
                original_size = response.headers.get("X-Artifact-Original-Size")
                assert original_size is not None
                assert int(original_size) > 0

    def test_response_includes_truncated_header(self, client, run_with_artifact, tmp_path):
        """Response includes X-Artifact-Truncated header."""
        run_id, run_dir = run_with_artifact

        with patch("autopack.main.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            with patch("autopack.main.settings") as mock_settings:
                mock_settings.artifact_read_size_cap_bytes = 0
                mock_settings.artifact_redaction_enabled = False

                response = client.get(f"/runs/{run_id}/artifacts/file?path=test_artifact.txt")
                assert response.status_code == 200

                # Check truncated header
                truncated = response.headers.get("X-Artifact-Truncated")
                assert truncated in ("true", "false")

    def test_response_includes_redacted_header(self, client, run_with_artifact, tmp_path):
        """Response includes X-Artifact-Redacted header."""
        run_id, run_dir = run_with_artifact

        with patch("autopack.main.RunFileLayout") as MockLayout:
            mock_instance = MockLayout.return_value
            mock_instance.base_dir = run_dir

            with patch("autopack.main.settings") as mock_settings:
                mock_settings.artifact_read_size_cap_bytes = 0
                mock_settings.artifact_redaction_enabled = False

                response = client.get(f"/runs/{run_id}/artifacts/file?path=test_artifact.txt")
                assert response.status_code == 200

                # Check redacted header
                redacted = response.headers.get("X-Artifact-Redacted")
                assert redacted in ("true", "false")


class TestArtifactBoundaryConfigContract:
    """Contract tests for artifact boundary configuration."""

    def test_config_has_size_cap_setting(self):
        """Settings class has artifact_read_size_cap_bytes."""
        from autopack.config import Settings

        settings = Settings()
        assert hasattr(settings, "artifact_read_size_cap_bytes")
        assert isinstance(settings.artifact_read_size_cap_bytes, int)

    def test_config_has_redaction_setting(self):
        """Settings class has artifact_redaction_enabled."""
        from autopack.config import Settings

        settings = Settings()
        assert hasattr(settings, "artifact_redaction_enabled")
        assert isinstance(settings.artifact_redaction_enabled, bool)

    def test_default_size_cap_is_1mb(self):
        """Default size cap is 1MB (safe for hosted usage)."""
        from autopack.config import Settings

        with patch.dict(os.environ, {}, clear=True):
            # Clear any existing env vars that might override
            for key in list(os.environ.keys()):
                if "ARTIFACT" in key:
                    del os.environ[key]

        # Fresh settings with defaults
        settings = Settings()
        # Default should be 1MB (1,048,576 bytes)
        assert settings.artifact_read_size_cap_bytes == 1_048_576

    def test_size_cap_configurable_via_env(self):
        """Size cap can be configured via environment variable."""
        with patch.dict(os.environ, {"AUTOPACK_ARTIFACT_READ_SIZE_CAP": "500000"}):
            from autopack.config import Settings

            settings = Settings()
            assert settings.artifact_read_size_cap_bytes == 500000

    def test_redaction_configurable_via_env(self):
        """Redaction can be enabled via environment variable."""
        with patch.dict(os.environ, {"AUTOPACK_ARTIFACT_REDACTION": "true"}):
            from autopack.config import Settings

            settings = Settings()
            assert settings.artifact_redaction_enabled is True


class TestArtifactSecurityInvariants:
    """Verify artifact endpoint security invariants remain intact."""

    @pytest.fixture
    def run_exists(self, client, db_session):
        """Create a minimal run for security tests."""
        from autopack import models

        run_id = "test-run-security"
        run = models.Run(
            id=run_id,
            state=models.RunState.DONE_SUCCESS,
            safety_profile="normal",
            run_scope="single_tier",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()
        return run_id

    def test_path_traversal_still_blocked(self, client, run_exists):
        """Path traversal attacks are still blocked after hardening."""
        run_id = run_exists

        # Test various traversal attempts
        traversal_paths = [
            "../secrets.txt",
            "..%2Fsecrets.txt",
            "phases/../../../etc/passwd",
            "..\\secrets.txt",
        ]

        for path in traversal_paths:
            response = client.get(f"/runs/{run_id}/artifacts/file?path={path}")
            assert response.status_code == 400, f"Should block path: {path}"

    def test_absolute_paths_still_blocked(self, client, run_exists):
        """Absolute paths are still blocked after hardening."""
        run_id = run_exists

        response = client.get(f"/runs/{run_id}/artifacts/file?path=/etc/passwd")
        assert response.status_code == 400
        assert "absolute" in response.json()["detail"].lower()

    def test_windows_drive_paths_still_blocked(self, client, run_exists):
        """Windows drive paths are still blocked after hardening."""
        run_id = run_exists

        response = client.get(f"/runs/{run_id}/artifacts/file?path=C:/Windows/System32/config")
        assert response.status_code == 400
        assert "drive" in response.json()["detail"].lower()
