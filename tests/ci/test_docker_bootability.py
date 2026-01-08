"""Docker bootability smoke tests (PR1 - GAP-1.1/1.2).

Contract tests ensuring:
1. Dockerfile builds successfully with required config files
2. Backend can import and boot (validates PYTHONPATH and dependencies)
3. docker-compose.dev.yml is a valid overlay for docker-compose.yml

These tests do NOT require Docker to be running - they validate the
Dockerfile/compose configuration files and simulate the import behavior.
"""

from pathlib import Path

import pytest

# Repo root for file path assertions
REPO_ROOT = Path(__file__).parent.parent.parent


class TestDockerfileConfiguration:
    """Validate Dockerfile copies required runtime files."""

    def test_dockerfile_copies_config_directory(self):
        """Dockerfile must COPY config/ for runtime model routing."""
        dockerfile = REPO_ROOT / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile not found"

        content = dockerfile.read_text(encoding="utf-8")

        # Must copy config directory for model routing, pricing, policies
        assert "COPY ./config /app/config" in content, (
            "Dockerfile must copy config/ directory. "
            "Runtime requires config/models.yaml for model routing."
        )

    def test_dockerfile_copies_src_directory(self):
        """Dockerfile must COPY src/ for application code."""
        dockerfile = REPO_ROOT / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")

        assert "COPY ./src /app/src" in content, "Dockerfile must copy src/ directory"

    def test_dockerfile_sets_pythonpath(self):
        """Dockerfile must set PYTHONPATH=/app/src for imports."""
        dockerfile = REPO_ROOT / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")

        assert (
            "PYTHONPATH=/app/src" in content
        ), "Dockerfile must set PYTHONPATH=/app/src for autopack imports"

    def test_dockerfile_runs_correct_entrypoint(self):
        """Dockerfile CMD must run autopack.main:app."""
        dockerfile = REPO_ROOT / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")

        assert (
            "autopack.main:app" in content
        ), "Dockerfile entrypoint must be autopack.main:app, not legacy targets"


class TestDockerComposeConfiguration:
    """Validate docker-compose files are consistent and valid."""

    def test_docker_compose_uses_correct_service_names(self):
        """docker-compose.yml must use canonical service names."""
        compose_file = REPO_ROOT / "docker-compose.yml"
        assert compose_file.exists(), "docker-compose.yml not found"

        content = compose_file.read_text(encoding="utf-8")

        # Canonical service names
        assert "backend:" in content, "Must have 'backend' service (not 'api')"
        assert "db:" in content, "Must have 'db' service (not 'postgres')"
        assert "frontend:" in content, "Must have 'frontend' service"

        # Should NOT have legacy names as primary services
        lines = content.split("\n")
        service_lines = [
            line
            for line in lines
            if line.strip().endswith(":") and not line.strip().startswith("#")
        ]
        service_names = [line.strip().rstrip(":") for line in service_lines]

        assert "postgres" not in service_names, "Service should be 'db', not 'postgres'"
        assert "api" not in service_names, "Service should be 'backend', not 'api'"

    def test_docker_compose_dev_is_valid_overlay(self):
        """docker-compose.dev.yml must be a valid overlay for docker-compose.yml."""
        dev_compose = REPO_ROOT / "docker-compose.dev.yml"
        assert dev_compose.exists(), "docker-compose.dev.yml not found"

        content = dev_compose.read_text(encoding="utf-8")

        # Dev overlay should reference existing services
        assert "backend:" in content, "Dev overlay must reference 'backend' service"
        assert "db:" in content, "Dev overlay must reference 'db' service"

        # Should NOT reference non-existent services
        assert (
            "postgres:" not in content
        ), "Dev overlay must use 'db' not 'postgres' (must match base compose)"
        assert (
            "api:" not in content
        ), "Dev overlay must use 'backend' not 'api' (must match base compose)"

    def test_docker_compose_dev_uses_correct_app_target(self):
        """docker-compose.dev.yml must use autopack.main:app entrypoint."""
        dev_compose = REPO_ROOT / "docker-compose.dev.yml"
        content = dev_compose.read_text(encoding="utf-8")

        # Check the command uses correct app target
        assert "autopack.main:app" in content, (
            "Dev compose must use autopack.main:app, not legacy targets like "
            "src.backend.main:app or autopack.api.server:app"
        )


class TestConfigFilesExist:
    """Validate required config files exist for Docker runtime."""

    def test_models_yaml_exists(self):
        """config/models.yaml must exist for model routing."""
        models_yaml = REPO_ROOT / "config" / "models.yaml"
        assert (
            models_yaml.exists()
        ), "config/models.yaml is required for deterministic model routing"

    def test_pricing_yaml_exists(self):
        """config/pricing.yaml must exist for cost estimation."""
        pricing_yaml = REPO_ROOT / "config" / "pricing.yaml"
        assert pricing_yaml.exists(), "config/pricing.yaml is required for cost estimation"

    def test_baseline_policy_yaml_exists(self):
        """config/baseline_policy.yaml must exist for gap scanner."""
        baseline_policy = REPO_ROOT / "config" / "baseline_policy.yaml"
        assert (
            baseline_policy.exists()
        ), "config/baseline_policy.yaml is required for baseline policy detection"


class TestBackendImportability:
    """Validate backend can be imported (simulates Docker boot)."""

    def test_autopack_main_importable(self):
        """autopack.main must be importable without errors."""
        # This test runs in the same environment as pytest
        # It validates the module structure is correct
        try:
            from autopack import main

            assert hasattr(main, "app"), "autopack.main must export 'app'"
        except ImportError as e:
            pytest.fail(f"Failed to import autopack.main: {e}")

    def test_autopack_config_loader_importable(self):
        """Config loader must be importable and handle missing files gracefully."""
        try:
            from autopack.config_loader import load_doctor_config, DoctorConfig

            # Should return defaults if file missing (graceful degradation)
            config = load_doctor_config()
            assert isinstance(config, DoctorConfig)
        except ImportError as e:
            pytest.fail(f"Failed to import config_loader: {e}")

    def test_autopack_model_catalog_importable(self):
        """Model catalog must be importable."""
        try:
            from autopack.model_catalog import load_model_catalog

            # Should not raise on import
            catalog = load_model_catalog()
            assert isinstance(catalog, list)
        except ImportError as e:
            pytest.fail(f"Failed to import model_catalog: {e}")


class TestDockerfileSecurityBestPractices:
    """Validate Dockerfile follows security best practices."""

    def test_dockerfile_runs_as_non_root(self):
        """Dockerfile should run as non-root user."""
        dockerfile = REPO_ROOT / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")

        assert "USER" in content, "Dockerfile should specify USER for non-root execution"
        assert (
            "useradd" in content or "adduser" in content
        ), "Dockerfile should create a non-root user"

    def test_dockerfile_uses_slim_base(self):
        """Dockerfile should use slim base image for security."""
        dockerfile = REPO_ROOT / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")

        # Should use slim variant, not full image
        assert (
            "python:3.11-slim" in content or "python:3.12-slim" in content
        ), "Dockerfile should use slim base image (python:X.Y-slim)"
