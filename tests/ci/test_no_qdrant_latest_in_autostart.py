"""
Test Qdrant :latest prevention in autostart code paths.

This test validates that:
1. No :latest image tag appears in autostart fallback paths
2. The CI guardrail script correctly detects violations
3. Current codebase is compliant with determinism policy

Policy enforced:
- Autostart fallback paths MUST use pinned Qdrant images
- The literal 'qdrant/qdrant:latest' MUST NOT appear in src/autopack/
- Images must match docker-compose.yml pinning (v1.12.5)
"""

import subprocess
from pathlib import Path

import pytest

# Files that contain autostart fallback logic
AUTOSTART_FILES = [
    Path("src/autopack/health_checks.py"),
    Path("src/autopack/memory/memory_service.py"),
]

# Expected pinned image version
EXPECTED_PINNED_IMAGE = "qdrant/qdrant:v1.12.5"

# Pattern that indicates a violation
FORBIDDEN_PATTERN = "qdrant/qdrant:latest"


def test_no_qdrant_latest_in_autostart_files():
    """
    Guardrail: verify no :latest appears in autostart code paths.

    This is the primary enforcement test that blocks merges.
    """
    violations = []

    for file_path in AUTOSTART_FILES:
        if not file_path.exists():
            continue

        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        for i, line in enumerate(lines, start=1):
            if FORBIDDEN_PATTERN in line:
                # Skip comments
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                violations.append(f"{file_path}:{i}: {stripped}")

    assert not violations, (
        "qdrant/qdrant:latest found in autostart code paths:\n"
        + "\n".join(f"  - {v}" for v in violations)
        + "\n\nFix: Use pinned image from config/memory.yaml or DEFAULT_QDRANT_IMAGE constant"
    )


def test_ci_script_passes_on_current_codebase():
    """
    Baseline test: CI script should pass on current compliant codebase.
    """
    result = subprocess.run(
        ["python", "scripts/ci/check_no_qdrant_latest_in_autostart.py"],
        capture_output=True,
        text=True,
    )
    assert (
        result.returncode == 0
    ), f"CI script failed on current codebase:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "[OK]" in result.stdout


def test_pinned_image_constant_exists():
    """
    Verify DEFAULT_QDRANT_IMAGE constant is defined in memory_service.
    """
    memory_service = Path("src/autopack/memory/memory_service.py")
    assert memory_service.exists()

    content = memory_service.read_text(encoding="utf-8")
    assert (
        "DEFAULT_QDRANT_IMAGE" in content
    ), "DEFAULT_QDRANT_IMAGE constant not found in memory_service.py"
    assert (
        EXPECTED_PINNED_IMAGE in content
    ), f"Expected pinned image {EXPECTED_PINNED_IMAGE} not found in memory_service.py"


def test_config_memory_yaml_has_pinned_image():
    """
    Verify config/memory.yaml specifies a pinned Qdrant image.
    """
    config_path = Path("config/memory.yaml")
    assert config_path.exists()

    content = config_path.read_text(encoding="utf-8")
    assert "image:" in content, "Qdrant image config not found in config/memory.yaml"
    assert (
        EXPECTED_PINNED_IMAGE in content
    ), f"Expected pinned image {EXPECTED_PINNED_IMAGE} not found in config/memory.yaml"
    assert (
        FORBIDDEN_PATTERN not in content
    ), ":latest tag found in config/memory.yaml - must use pinned version"


def test_docker_compose_matches_pinned_image():
    """
    Verify docker-compose.yml uses the same pinned Qdrant image.

    This ensures consistency between compose and autostart fallback.
    """
    compose_path = Path("docker-compose.yml")
    assert compose_path.exists()

    content = compose_path.read_text(encoding="utf-8")
    assert (
        EXPECTED_PINNED_IMAGE in content
    ), f"docker-compose.yml should use {EXPECTED_PINNED_IMAGE} for Qdrant"
    assert (
        FORBIDDEN_PATTERN not in content
    ), ":latest tag found in docker-compose.yml - must use pinned version"


@pytest.mark.parametrize(
    "file_path",
    AUTOSTART_FILES,
)
def test_autostart_files_use_qdrant_image_variable(file_path: Path):
    """
    Verify autostart files use a variable for the Qdrant image, not hardcoded.

    This ensures the image can be overridden via config or env.
    """
    if not file_path.exists():
        pytest.skip(f"{file_path} does not exist")

    content = file_path.read_text(encoding="utf-8")

    # Check that the file uses qdrant_image variable in docker run command
    # (not a hardcoded string)
    assert (
        "qdrant_image" in content.lower() or "QDRANT_IMAGE" in content
    ), f"{file_path} should use qdrant_image variable for docker run"
