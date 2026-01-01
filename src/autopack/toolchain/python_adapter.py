"""Python toolchain adapter.

Supports:
- pip (requirements.txt)
- uv (pyproject.toml with uv)
- poetry (pyproject.toml with poetry)
- setup.py projects
"""

import logging
from pathlib import Path
from typing import List

from .adapter import ToolchainAdapter, ToolchainDetectionResult

logger = logging.getLogger(__name__)


class PythonAdapter(ToolchainAdapter):
    """Python toolchain adapter."""

    @property
    def name(self) -> str:
        return "python"

    def detect(self, workspace: Path) -> ToolchainDetectionResult:
        """Detect Python project.

        Detection signals:
        - requirements.txt (pip)
        - pyproject.toml (poetry/uv)
        - setup.py
        - *.py files
        """
        confidence = 0.0
        reasons = []
        package_manager = None

        # Check for requirements.txt (high confidence)
        if (workspace / "requirements.txt").exists():
            confidence += 0.5
            reasons.append("requirements.txt")
            package_manager = "pip"

        # Check for pyproject.toml (high confidence)
        pyproject = workspace / "pyproject.toml"
        if pyproject.exists():
            confidence += 0.4
            reasons.append("pyproject.toml")

            # Determine package manager from pyproject.toml
            try:
                content = pyproject.read_text(encoding="utf-8")
                if "poetry" in content.lower():
                    package_manager = "poetry"
                    reasons.append("poetry")
                elif "uv" in content.lower():
                    package_manager = "uv"
                    reasons.append("uv")
                else:
                    package_manager = "pip"  # Generic pip fallback
            except Exception as e:
                logger.debug(f"Failed to read pyproject.toml: {e}")

        # Check for setup.py (medium confidence)
        if (workspace / "setup.py").exists():
            confidence += 0.3
            reasons.append("setup.py")
            if not package_manager:
                package_manager = "pip"

        # Check for .py files (low confidence, many false positives)
        py_files = list(workspace.glob("**/*.py"))
        if py_files:
            confidence += min(0.2, len(py_files) * 0.01)  # Cap at 0.2
            reasons.append(f"{len(py_files)} .py files")

        # Cap total confidence at 1.0
        confidence = min(1.0, confidence)

        detected = confidence >= 0.3  # Require at least medium confidence

        return ToolchainDetectionResult(
            detected=detected,
            confidence=confidence,
            name=self.name,
            package_manager=package_manager or "pip",
            reason=", ".join(reasons) if reasons else "no Python markers found",
        )

    def install_cmds(self, workspace: Path) -> List[str]:
        """Return install commands for Python project."""
        detection = self.detect(workspace)

        if not detection.detected:
            return []

        package_manager = detection.package_manager or "pip"

        if package_manager == "poetry":
            return ["poetry install"]
        elif package_manager == "uv":
            return ["uv pip install -r requirements.txt"]
        elif (workspace / "requirements.txt").exists():
            return ["pip install -r requirements.txt"]
        elif (workspace / "setup.py").exists():
            return ["pip install -e ."]
        else:
            # No clear install target
            return []

    def build_cmds(self, workspace: Path) -> List[str]:
        """Return build commands for Python project.

        Python typically doesn't require explicit build step.
        """
        # Check for setup.py build
        if (workspace / "setup.py").exists():
            return ["python setup.py build"]
        return []

    def test_cmds(self, workspace: Path) -> List[str]:
        """Return test commands for Python project."""
        # Detect test framework
        if (workspace / "pytest.ini").exists() or (workspace / "pyproject.toml").exists():
            # Check for tests directory
            if (workspace / "tests").exists():
                return ["pytest tests/ -v"]
            return ["pytest -v"]
        elif (workspace / "setup.py").exists():
            return ["python setup.py test"]
        else:
            # Fallback: try to run pytest if tests/ exists
            if (workspace / "tests").exists():
                return ["pytest tests/ -v"]
        return []

    def smoke_checks(self, workspace: Path) -> List[str]:
        """Return smoke check commands for Python project."""
        # Collect .py files for syntax check
        py_files = list(workspace.glob("**/*.py"))

        # Limit to first 50 files to avoid command bloat
        py_files = py_files[:50]

        if not py_files:
            return []

        # Use py_compile for syntax checks
        file_paths = " ".join(str(f.relative_to(workspace)) for f in py_files)
        return [f"python -m py_compile {file_paths}"]
