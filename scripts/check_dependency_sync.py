#!/usr/bin/env python3
"""
CI Check: Dependency Sync Validation (Linux/CI canonical)

Goal: ensure committed requirements files stay in sync with pyproject.toml:
- requirements.txt (runtime)
- requirements-dev.txt (runtime + dev extras)

Important constraints:
- This repo treats Linux/CI (or WSL) as canonical for requirements generation to avoid
  cross-platform drift. On native Windows, this check is SKIPPED by default.
- This check intentionally does NOT use --generate-hashes because hashes cause
  cross-platform drift and the repo's committed requirements do not include hashes.

Usage:
    python scripts/check_dependency_sync.py

Exit codes:
    0: In sync (or skipped on Windows)
    1: Drift detected - requirements*.txt needs regeneration (run on Linux/WSL)
    2: Runtime error (pip-tools missing, files missing, etc.)
"""

import subprocess
import sys
import tempfile
from pathlib import Path
import os


def main() -> int:
    """Check if requirements*.txt are in sync with pyproject.toml (CI canonical)."""
    repo_root = Path(__file__).parent.parent
    pyproject_path = repo_root / "pyproject.toml"
    requirements_path = repo_root / "requirements.txt"
    requirements_dev_path = repo_root / "requirements-dev.txt"

    # Validate files exist
    if not pyproject_path.exists():
        print(f"[X] ERROR: pyproject.toml not found at {pyproject_path}", file=sys.stderr)
        return 2

    if not requirements_path.exists():
        print(f"[X] ERROR: requirements.txt not found at {requirements_path}", file=sys.stderr)
        return 2

    if not requirements_dev_path.exists():
        print(
            f"[X] ERROR: requirements-dev.txt not found at {requirements_dev_path}", file=sys.stderr
        )
        return 2

    # Policy: skip on native Windows (use WSL/CI for canonical output)
    if os.name == "nt" and not os.getenv("WSL_DISTRO_NAME"):
        print(
            "[SKIP] Dependency sync check skipped on native Windows. "
            "Regenerate requirements on Linux/WSL/CI (see scripts/regenerate_requirements.sh)."
        )
        return 0

    # Check if pip-tools is installed
    try:
        result = subprocess.run(
            ["pip-compile", "--version"], capture_output=True, text=True, check=False
        )
        if result.returncode != 0:
            print("[X] ERROR: pip-compile not found. Install pip-tools:", file=sys.stderr)
            print("  pip install pip-tools", file=sys.stderr)
            return 2
    except FileNotFoundError:
        print("[X] ERROR: pip-compile not found. Install pip-tools:", file=sys.stderr)
        print("  pip install pip-tools", file=sys.stderr)
        return 2

    def _normalize(lines: list[str]) -> list[str]:
        """Normalize requirements lines for comparison.

        Filters out:
        - All comment lines (pip-compile formats these differently with/without constraints)
        - Empty lines
        - Python version-specific backport packages (exceptiongroup, tomli, etc.)
        - Platform-specific packages (colorama on Windows, uvloop on Linux)

        Keeps only package lines with versions (the essential information).
        """
        # Packages that vary by Python version (backports for < 3.11)
        PYTHON_VERSION_PACKAGES = {
            "exceptiongroup",
            "tomli",
            "backports-asyncio-runner",
        }
        # Platform-specific packages (Windows vs Linux)
        PLATFORM_PACKAGES = {
            "colorama",  # Windows-only for click/uvicorn
            "uvloop",  # Linux-only for uvicorn
            "pywin32",  # Windows-only from portalocker (transitive via qdrant-client)
            "python-magic",  # Linux-only (alternative to python-magic-bin)
            "python-magic-bin",  # Windows-only (alternative to python-magic)
        }
        SKIP_PACKAGES = PYTHON_VERSION_PACKAGES | PLATFORM_PACKAGES

        normalized: list[str] = []

        for line in lines:
            stripped = line.strip()

            # Skip empty lines
            if not stripped:
                continue

            # Skip ALL comment lines - pip-compile formats these differently
            # with vs without constraints, so we only compare package lines
            if stripped.startswith("#"):
                continue

            # Skip Python version/platform-specific packages
            # Package lines look like: package==version or package[extra]==version
            pkg_match = stripped.split("==")[0].split("[")[0].lower() if "==" in stripped else None
            if pkg_match and pkg_match in SKIP_PACKAGES:
                continue

            # Keep this package line
            normalized.append(stripped)

        return normalized

    def _compile_to_temp(extra: str | None = None, reference_file: Path | None = None) -> Path:
        """Run pip-compile and write output to a temp file.

        Args:
            extra: Extra dependencies group to include (e.g., "dev")
            reference_file: Existing requirements file to use as version reference
                           (prevents upgrading to newer versions)
        """
        fd, tmp_name = tempfile.mkstemp(suffix=".txt")
        os.close(fd)
        tmp_path = Path(tmp_name)

        args = ["pip-compile", "--output-file", str(tmp_path), "pyproject.toml"]
        if extra:
            args.insert(1, f"--extra={extra}")
        # Use existing requirements as version constraints to prevent version drift
        # This ensures we only check structural changes, not version updates
        if reference_file and reference_file.exists():
            args.insert(1, f"--constraint={reference_file}")

        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=repo_root,
            check=False,
        )
        if result.returncode != 0:
            print("[X] ERROR: pip-compile failed:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError("pip-compile failed")
        return tmp_path

    try:
        print("[INFO] Running pip-compile on pyproject.toml (runtime)...")
        tmp_runtime = _compile_to_temp(reference_file=requirements_path)
        print("[INFO] Running pip-compile on pyproject.toml (dev extras)...")
        tmp_dev = _compile_to_temp(extra="dev", reference_file=requirements_dev_path)

        runtime_compiled = _normalize(tmp_runtime.read_text(encoding="utf-8").splitlines())
        runtime_committed = _normalize(requirements_path.read_text(encoding="utf-8").splitlines())
        dev_compiled = _normalize(tmp_dev.read_text(encoding="utf-8").splitlines())
        dev_committed = _normalize(requirements_dev_path.read_text(encoding="utf-8").splitlines())

        drift: list[str] = []

        # Compare as sets since line order may vary between pip-compile runs
        runtime_compiled_set = set(runtime_compiled)
        runtime_committed_set = set(runtime_committed)
        only_compiled_runtime = runtime_compiled_set - runtime_committed_set
        only_committed_runtime = runtime_committed_set - runtime_compiled_set
        if only_compiled_runtime or only_committed_runtime:
            drift.append("requirements.txt")
            # Debug: show first few differences
            print("[DEBUG] requirements.txt differences:", file=sys.stderr)
            for line in sorted(only_compiled_runtime)[:5]:
                print(f"  + (compiled) {line}", file=sys.stderr)
            for line in sorted(only_committed_runtime)[:5]:
                print(f"  - (committed) {line}", file=sys.stderr)

        dev_compiled_set = set(dev_compiled)
        dev_committed_set = set(dev_committed)
        only_compiled_dev = dev_compiled_set - dev_committed_set
        only_committed_dev = dev_committed_set - dev_compiled_set
        if only_compiled_dev or only_committed_dev:
            drift.append("requirements-dev.txt")
            # Debug: show first few differences
            print("[DEBUG] requirements-dev.txt differences:", file=sys.stderr)
            for line in sorted(only_compiled_dev)[:5]:
                print(f"  + (compiled) {line}", file=sys.stderr)
            for line in sorted(only_committed_dev)[:5]:
                print(f"  - (committed) {line}", file=sys.stderr)

        if not drift:
            print("[OK] SUCCESS: requirements files are in sync with pyproject.toml")
            return 0

        print("[X] DRIFT DETECTED: requirements files do NOT match pyproject.toml", file=sys.stderr)
        print("Out of sync:", ", ".join(drift), file=sys.stderr)
        print("", file=sys.stderr)
        print("To fix this, regenerate requirements on Linux/WSL:", file=sys.stderr)
        print("  bash scripts/regenerate_requirements.sh", file=sys.stderr)
        return 1

    finally:
        # Clean up temp file
        try:
            tmp_runtime.unlink(missing_ok=True)  # type: ignore[name-defined]
        except Exception:
            pass
        try:
            tmp_dev.unlink(missing_ok=True)  # type: ignore[name-defined]
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
