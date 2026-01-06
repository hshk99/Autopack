"""Mechanical doc drift detection (BUILD-180).

Thin wrapper around existing doc drift check scripts.
Runs actual scripts and captures exit codes for evidence.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class DocDriftResult:
    """Result of a doc drift check."""

    passed: bool
    exit_code: int
    command: str
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None

    @property
    def stdout_hash(self) -> str:
        """Get hash of stdout for evidence."""
        return hashlib.sha256(self.stdout.encode("utf-8")).hexdigest()[:16]


@dataclass
class CommandEvidence:
    """Evidence from a command execution."""

    command: str
    exit_code: int
    stdout_hash: str
    stderr_excerpt: str = ""


def run_doc_drift_check(workspace_root: Path, timeout: int = 30) -> DocDriftResult:
    """Run scripts/check_docs_drift.py and capture result.

    Args:
        workspace_root: Root directory of workspace
        timeout: Command timeout in seconds

    Returns:
        DocDriftResult with exit code and output
    """
    command = "python scripts/check_docs_drift.py"

    try:
        result = subprocess.run(
            ["python", "scripts/check_docs_drift.py"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        passed = result.returncode == 0

        return DocDriftResult(
            passed=passed,
            exit_code=result.returncode,
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    except FileNotFoundError:
        logger.warning("[DocDrift] Script not found: scripts/check_docs_drift.py")
        return DocDriftResult(
            passed=False,
            exit_code=-1,
            command=command,
            error="Script not found: scripts/check_docs_drift.py",
        )

    except subprocess.TimeoutExpired:
        logger.warning(f"[DocDrift] Command timed out after {timeout}s")
        return DocDriftResult(
            passed=False,
            exit_code=-1,
            command=command,
            error=f"Command timed out after {timeout}s",
        )

    except Exception as e:
        logger.error(f"[DocDrift] Unexpected error: {e}")
        return DocDriftResult(
            passed=False,
            exit_code=-1,
            command=command,
            error=str(e),
        )


def run_sot_summary_check(workspace_root: Path, timeout: int = 30) -> DocDriftResult:
    """Run scripts/tidy/sot_summary_refresh.py --check and capture result.

    Args:
        workspace_root: Root directory of workspace
        timeout: Command timeout in seconds

    Returns:
        DocDriftResult with exit code and output
    """
    command = "python scripts/tidy/sot_summary_refresh.py --check"

    try:
        result = subprocess.run(
            ["python", "scripts/tidy/sot_summary_refresh.py", "--check"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        passed = result.returncode == 0

        return DocDriftResult(
            passed=passed,
            exit_code=result.returncode,
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    except FileNotFoundError:
        logger.warning("[DocDrift] Script not found: scripts/tidy/sot_summary_refresh.py")
        return DocDriftResult(
            passed=False,
            exit_code=-1,
            command=command,
            error="Script not found: scripts/tidy/sot_summary_refresh.py",
        )

    except subprocess.TimeoutExpired:
        logger.warning(f"[DocDrift] SOT check timed out after {timeout}s")
        return DocDriftResult(
            passed=False,
            exit_code=-1,
            command=command,
            error=f"Command timed out after {timeout}s",
        )

    except Exception as e:
        logger.error(f"[DocDrift] SOT check unexpected error: {e}")
        return DocDriftResult(
            passed=False,
            exit_code=-1,
            command=command,
            error=str(e),
        )


def run_doc_tests(workspace_root: Path, timeout: int = 60) -> DocDriftResult:
    """Run pytest tests/docs/ to check doc contracts.

    Args:
        workspace_root: Root directory of workspace
        timeout: Command timeout in seconds

    Returns:
        DocDriftResult with exit code and output
    """
    command = "pytest -q tests/docs/"

    # Check if tests/docs exists
    tests_docs = workspace_root / "tests" / "docs"
    if not tests_docs.exists():
        return DocDriftResult(
            passed=True,  # No tests to run = pass
            exit_code=0,
            command=command,
            stdout="No tests/docs/ directory found",
        )

    try:
        result = subprocess.run(
            ["pytest", "-q", "tests/docs/"],
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        passed = result.returncode == 0

        return DocDriftResult(
            passed=passed,
            exit_code=result.returncode,
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    except FileNotFoundError:
        logger.warning("[DocDrift] pytest not found")
        return DocDriftResult(
            passed=False,
            exit_code=-1,
            command=command,
            error="pytest not found",
        )

    except subprocess.TimeoutExpired:
        logger.warning(f"[DocDrift] Doc tests timed out after {timeout}s")
        return DocDriftResult(
            passed=False,
            exit_code=-1,
            command=command,
            error=f"Command timed out after {timeout}s",
        )

    except Exception as e:
        logger.error(f"[DocDrift] Doc tests unexpected error: {e}")
        return DocDriftResult(
            passed=False,
            exit_code=-1,
            command=command,
            error=str(e),
        )


def run_all_doc_drift_checks(workspace_root: Path) -> list[DocDriftResult]:
    """Run all doc drift checks and return results.

    Args:
        workspace_root: Root directory of workspace

    Returns:
        List of DocDriftResult for each check
    """
    results = []

    # Run each check
    results.append(run_doc_drift_check(workspace_root))
    results.append(run_sot_summary_check(workspace_root))
    results.append(run_doc_tests(workspace_root))

    return results
