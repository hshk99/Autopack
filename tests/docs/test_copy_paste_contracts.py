"""
Docs contract tests: copy/paste correctness guardrails.

Goal: block the highest-risk doc regressions that cause immediate operator failures:
- Wrong DB bootstrap/migration instructions (init_db misuse)
- Legacy/non-existent paths (src/backend/, src/autopack/alembic/)
- Invalid Docker build commands (docker build --target frontend)
- Workstation-specific paths (C:\\dev\\Autopack, cd c:/dev/Autopack)
- Non-canonical env template paths

Important: This test intentionally scans a small allowlist of operator-facing docs
to avoid false positives from historical ledgers (BUILD_HISTORY, DEBUG_LOG, etc.).
"""

from __future__ import annotations

from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).parents[2]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_copy_paste_contracts_forbidden_patterns():
    repo_root = _repo_root()

    allowlist = [
        repo_root / "docs" / "DEPLOYMENT.md",
        repo_root / "docs" / "DOCKER_DEPLOYMENT_GUIDE.md",
        repo_root / "docs" / "CONFIG_GUIDE.md",
        repo_root / "docs" / "TROUBLESHOOTING.md",
        repo_root / "docs" / "QUICKSTART.md",
        repo_root / "docs" / "CONTRIBUTING.md",
        repo_root / "docs" / "PROJECT_INDEX.json",
        repo_root / "docs" / "AUTHENTICATION.md",  # PR-A: auth doc truth (DEC-050)
    ]

    missing = [str(p) for p in allowlist if not p.exists()]
    assert not missing, f"Copy/paste contract allowlist contains missing files: {missing}"

    forbidden_literals = [
        # Non-canonical DB bootstrap/migrations (should not be recommended as migrations)
        "from autopack.database import init_db; init_db()",
        "from src.autopack.database import init_db; init_db()",
        # Legacy backend tree (non-existent in current repo)
        "src/backend/",
        "src\\backend\\",
        # Invalid Docker build target for this repo's Dockerfile
        "docker build --target frontend",
        "--target frontend",
        # Non-existent Alembic dir claim (there is no src/autopack/alembic/)
        "src/autopack/alembic/",
        # Workstation-specific absolute paths (use $REPO_ROOT notation)
        "cd c:/dev/Autopack",
        "cd C:/dev/Autopack",
        "cd C:\\dev\\Autopack",
        "C:\\dev\\Autopack",
        # Non-canonical env template path
        "cp docs/templates/env.example .env",
    ]

    violations: list[str] = []
    for path in allowlist:
        raw = _read_text(path)
        for lit in forbidden_literals:
            if lit in raw:
                violations.append(f"{path.as_posix()}: contains forbidden literal: {lit!r}")

    assert not violations, "Forbidden copy/paste patterns detected:\n" + "\n".join(violations)


def test_copy_paste_contracts_required_canonical_strings_exist():
    repo_root = _repo_root()

    deployment = repo_root / "docs" / "DEPLOYMENT.md"
    quickstart = repo_root / "docs" / "QUICKSTART.md"
    config_guide = repo_root / "docs" / "CONFIG_GUIDE.md"
    project_index = repo_root / "docs" / "PROJECT_INDEX.json"

    # Canonical backend entrypoint must exist somewhere operator-facing.
    entrypoint_ok = False
    for p in [deployment, quickstart]:
        raw = _read_text(p)
        if "uvicorn autopack.main:app" in raw and "--port 8000" in raw:
            entrypoint_ok = True
            break
    assert entrypoint_ok, (
        "Canonical entrypoint missing (expected uvicorn autopack.main:app --port 8000)"
    )

    # Canonical env template path must be present in CONFIG_GUIDE and PROJECT_INDEX.
    assert "cp .env.example .env" in _read_text(config_guide), (
        "CONFIG_GUIDE must include: cp .env.example .env"
    )
    assert "cp .env.example .env" in _read_text(project_index), (
        "PROJECT_INDEX must include: cp .env.example .env"
    )

    # Compose topology (if described in DEPLOYMENT) must include qdrant.
    dep_raw = _read_text(deployment)
    assert "qdrant" in dep_raw, (
        "DEPLOYMENT.md must mention qdrant (compose includes qdrant service)"
    )
