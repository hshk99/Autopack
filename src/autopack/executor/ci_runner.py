"""CI runner module for executing test and verification commands.

Extracted from autonomous_executor.py for PR-EXE-3.
Provides CI execution for:
- Pytest test runs with JSON report generation
- Custom CI commands (lint, build, etc.)

Supports configurable timeouts, output truncation, and log persistence.
"""

import logging
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CIResult:
    """Result of a CI execution."""

    status: str  # "passed", "failed", "skipped"
    message: str
    passed: bool
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_error: int = 0
    duration_seconds: float = 0.0
    output: str = ""
    error: Optional[str] = None
    report_path: Optional[str] = None
    log_path: Optional[str] = None
    skipped: bool = False
    suspicious_zero_tests: bool = False
    collector_error_digest: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API/JSON serialization."""
        return {
            "status": self.status,
            "message": self.message,
            "passed": self.passed,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests_error": self.tests_error,
            "duration_seconds": self.duration_seconds,
            "output": self.output,
            "error": self.error,
            "report_path": self.report_path,
            "log_path": self.log_path,
            "skipped": self.skipped,
            "suspicious_zero_tests": self.suspicious_zero_tests,
            "collector_error_digest": self.collector_error_digest,
        }


@dataclass
class CISpec:
    """CI specification from phase configuration."""

    ci_type: str = "pytest"  # "pytest" or "custom"
    skip: bool = False
    skip_reason: Optional[str] = None
    command: Optional[str] = None  # For custom CI
    paths: Optional[List[str]] = None  # For pytest
    args: List[str] = field(default_factory=list)
    workdir: str = "."
    timeout_seconds: int = 300
    per_test_timeout: int = 60  # For pytest
    env: Dict[str, str] = field(default_factory=dict)
    shell: bool = False
    json_report_name: Optional[str] = None
    log_name: Optional[str] = None
    success_message: Optional[str] = None
    failure_message: Optional[str] = None

    @classmethod
    def from_dict(cls, spec: Dict[str, Any], phase_id: str) -> "CISpec":
        """Create CISpec from a dictionary configuration."""
        ci_type = spec.get("type")
        if spec.get("command") and not ci_type:
            ci_type = "custom"
        if not ci_type:
            ci_type = "pytest"

        timeout = spec.get("timeout_seconds") or spec.get("timeout")
        default_timeout = 600 if ci_type == "custom" else 300

        return cls(
            ci_type=ci_type,
            skip=spec.get("skip", False),
            skip_reason=spec.get("reason"),
            command=spec.get("command"),
            paths=spec.get("paths"),
            args=spec.get("args", []),
            workdir=spec.get("workdir", "."),
            timeout_seconds=timeout or default_timeout,
            per_test_timeout=spec.get("per_test_timeout", 60),
            env=spec.get("env", {}),
            shell=spec.get("shell", False),
            json_report_name=spec.get("json_report_name", f"pytest_{phase_id}.json"),
            log_name=spec.get("log_name"),
            success_message=spec.get("success_message"),
            failure_message=spec.get("failure_message"),
        )


def create_skipped_result(reason: str = "CI skipped per phase configuration") -> CIResult:
    """Create a skipped CI result."""
    return CIResult(
        status="skipped",
        message=reason,
        passed=True,
        skipped=True,
    )


def trim_ci_output(output: str, limit: int = 10000) -> str:
    """Trim CI output to a reasonable size.

    Args:
        output: Raw CI output
        limit: Maximum character limit

    Returns:
        Trimmed output with truncation marker if needed
    """
    if len(output) <= limit:
        return output
    return output[: limit // 2] + "\n\n... (truncated) ...\n\n" + output[-limit // 2 :]


def persist_ci_log(
    workspace: Path,
    run_id: str,
    log_name: str,
    content: str,
    phase_id: str,
) -> Optional[Path]:
    """Persist CI log to disk.

    Args:
        workspace: Workspace root path
        run_id: Run identifier
        log_name: Log filename
        content: Log content
        phase_id: Phase identifier (for logging)

    Returns:
        Path to the written log file, or None on failure
    """
    ci_log_dir = workspace / ".autonomous_runs" / run_id / "ci"
    ci_log_dir.mkdir(parents=True, exist_ok=True)
    log_path = ci_log_dir / log_name

    try:
        log_path.write_text(content, encoding="utf-8")
        logger.info(f"[{phase_id}] CI output written to: {log_path}")
        return log_path
    except Exception as log_err:
        logger.warning(f"[{phase_id}] Failed to write CI log ({log_name}): {log_err}")
        return None


def parse_pytest_counts(output: str) -> Tuple[int, int, int]:
    """Parse pytest output for test counts.

    Args:
        output: Pytest stdout/stderr output

    Returns:
        Tuple of (passed, failed, error) counts
    """
    tests_passed = tests_failed = tests_error = 0

    for line in output.split("\n"):
        line_lower = line.lower()

        # Collection errors first (special pattern)
        collection_error = re.search(r"(\d+)\s+errors?\s+during\s+collection", line_lower)
        if collection_error:
            tests_error = int(collection_error.group(1))
            continue

        passed_match = re.search(r"(\d+)\s+passed", line_lower)
        if passed_match:
            tests_passed = int(passed_match.group(1))

        failed_match = re.search(r"(\d+)\s+failed", line_lower)
        if failed_match:
            tests_failed = int(failed_match.group(1))

        # Error count (but not "during collection")
        error_match = re.search(r"(\d+)\s+errors?(?!\s+during)", line_lower)
        if error_match:
            tests_error = int(error_match.group(1))

    return tests_passed, tests_failed, tests_error


def discover_pytest_paths(
    workdir: Path,
    project_slug: Optional[str] = None,
) -> Optional[List[str]]:
    """Discover pytest paths from project structure.

    Args:
        workdir: Working directory
        project_slug: Optional project identifier for custom discovery

    Returns:
        List of pytest paths or None if not found
    """
    if project_slug == "file-organizer-app-v1":
        candidate_paths = [
            "fileorganizer/backend/tests/",
            "src/backend/tests/",
            "tests/backend/",
        ]
    else:
        candidate_paths = ["tests/"]

    for path in candidate_paths:
        if (workdir / path).exists():
            return [path]

    return None


def run_pytest(
    phase_id: str,
    spec: CISpec,
    workspace: Path,
    run_id: str,
    project_slug: Optional[str] = None,
    collector_digest_extractor: Optional[Callable] = None,
) -> CIResult:
    """Run pytest CI checks.

    Args:
        phase_id: Phase identifier
        spec: CI specification
        workspace: Workspace root path
        run_id: Run identifier
        project_slug: Optional project identifier for path discovery
        collector_digest_extractor: Optional callback to extract collection error digest

    Returns:
        CIResult with test execution details
    """
    logger.info(f"[{phase_id}] Running CI checks (pytest)...")

    workdir = workspace / spec.workdir
    if not workdir.exists():
        logger.warning(
            f"[{phase_id}] CI workdir {workdir} missing, defaulting to workspace root"
        )
        workdir = workspace

    # Discover test paths
    pytest_paths = spec.paths
    if not pytest_paths:
        pytest_paths = discover_pytest_paths(workdir, project_slug)

    if not pytest_paths:
        logger.warning(f"[{phase_id}] No pytest paths found, skipping CI checks")
        return create_skipped_result("No pytest paths found")

    # Build pytest command
    default_args = [
        "-v",
        "--tb=line",
        "-q",
        "--no-header",
        f"--timeout={spec.per_test_timeout}",
    ]

    ci_dir = workspace / ".autonomous_runs" / run_id / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    json_report_path = ci_dir / spec.json_report_name

    cmd = [sys.executable, "-m", "pytest", *pytest_paths, *default_args, *spec.args]
    if "--json-report" not in cmd:
        cmd.append("--json-report")
    if not any(str(a).startswith("--json-report-file=") for a in cmd):
        cmd.append(f"--json-report-file={json_report_path}")

    # Setup environment
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(workdir / "src"))
    env["TESTING"] = "1"
    env["PYTHONUTF8"] = "1"
    env.update(spec.env)

    # Execute pytest
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        logger.error(f"[{phase_id}] Pytest timeout after {duration:.1f}s")
        return CIResult(
            status="failed",
            message=f"pytest timed out after {spec.timeout_seconds}s",
            passed=False,
            duration_seconds=round(duration, 2),
            error=f"pytest timed out after {spec.timeout_seconds}s",
        )

    duration = time.time() - start_time
    output = trim_ci_output(result.stdout + result.stderr)
    tests_passed, tests_failed, tests_error = parse_pytest_counts(output)
    tests_run = tests_passed + tests_failed + tests_error
    passed = result.returncode == 0
    no_tests_detected = tests_run == 0

    # Determine error message
    error_msg = None
    if no_tests_detected and not passed:
        error_msg = "Possible collection error - no tests detected"
    elif no_tests_detected and passed:
        error_msg = "Warning: pytest reported success but no tests executed"
    elif not passed:
        error_msg = f"pytest exited with code {result.returncode}"

    # Persist logs
    full_output = result.stdout + "\n\n--- STDERR ---\n\n" + result.stderr
    log_name = spec.log_name or f"pytest_{phase_id}.log"
    log_path = persist_ci_log(workspace, run_id, log_name, full_output, phase_id)

    # Determine report path (prefer JSON, fallback to log)
    report_path: Optional[Path] = None
    try:
        if json_report_path.exists() and json_report_path.stat().st_size > 0:
            report_path = json_report_path
    except Exception:
        report_path = None
    if report_path is None:
        report_path = log_path

    # Build message
    message = spec.success_message if passed else spec.failure_message
    if not message:
        if passed:
            message = f"Pytest passed ({tests_passed}/{max(tests_run, 1)} tests)"
        else:
            message = error_msg or "Pytest failed"

    if passed:
        logger.info(
            f"[{phase_id}] CI checks PASSED: {tests_passed}/{max(tests_run, 1)} tests passed in {duration:.1f}s"
        )
    else:
        logger.warning(f"[{phase_id}] CI checks FAILED: return code {result.returncode}")

    # Extract collector error digest if applicable
    collector_digest = None
    if collector_digest_extractor and (
        result.returncode == 2 or (no_tests_detected and not passed)
    ):
        try:
            collector_digest = collector_digest_extractor(
                {"report_path": str(report_path) if report_path else None},
                workspace,
                max_errors=5,
            )
            if collector_digest:
                logger.warning(
                    f"[{phase_id}] Collection errors detected: {len(collector_digest)} failures"
                )
        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to extract collector digest: {e}")

    return CIResult(
        status="passed" if passed else "failed",
        message=message,
        passed=passed,
        tests_run=tests_run,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        tests_error=tests_error,
        duration_seconds=round(duration, 2),
        output=output,
        error=error_msg,
        report_path=str(report_path) if report_path else None,
        log_path=str(log_path) if log_path else None,
        suspicious_zero_tests=no_tests_detected,
        collector_error_digest=collector_digest,
    )


def run_custom_ci(
    phase_id: str,
    spec: CISpec,
    workspace: Path,
    run_id: str,
) -> CIResult:
    """Run custom CI command.

    Args:
        phase_id: Phase identifier
        spec: CI specification
        workspace: Workspace root path
        run_id: Run identifier

    Returns:
        CIResult with command execution details
    """
    command = spec.command
    if not command:
        logger.warning(f"[{phase_id}] CI spec missing 'command'; skipping")
        return create_skipped_result("CI command not configured")

    workdir = workspace / spec.workdir
    if not workdir.exists():
        logger.warning(
            f"[{phase_id}] CI workdir {workdir} missing, defaulting to workspace root"
        )
        workdir = workspace

    # Setup environment
    env = os.environ.copy()
    env.update(spec.env)

    # Prepare command
    shell = spec.shell or isinstance(command, str)
    cmd = command
    if isinstance(command, str) and not shell:
        cmd = shlex.split(command)

    logger.info(f"[{phase_id}] Running custom CI command: {command}")

    # Execute command
    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
            env=env,
            shell=shell,
        )
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        logger.error(f"[{phase_id}] CI command timeout after {duration:.1f}s")
        return CIResult(
            status="failed",
            message=f"CI command timed out after {spec.timeout_seconds}s",
            passed=False,
            duration_seconds=round(duration, 2),
            error=f"Command timed out after {spec.timeout_seconds}s",
        )

    duration = time.time() - start_time
    output = trim_ci_output(result.stdout + result.stderr)
    passed = result.returncode == 0

    # Persist logs
    full_output = result.stdout + "\n\n--- STDERR ---\n\n" + result.stderr
    log_name = spec.log_name or f"ci_{phase_id}.log"
    report_path = persist_ci_log(workspace, run_id, log_name, full_output, phase_id)

    # Build message
    message = spec.success_message if passed else spec.failure_message
    if not message:
        message = (
            "CI command succeeded"
            if passed
            else f"CI command failed (exit {result.returncode})"
        )

    if passed:
        logger.info(f"[{phase_id}] Custom CI command passed in {duration:.1f}s")
    else:
        logger.warning(f"[{phase_id}] Custom CI command failed (exit {result.returncode})")

    return CIResult(
        status="passed" if passed else "failed",
        message=message,
        passed=passed,
        duration_seconds=round(duration, 2),
        output=output,
        error=None if passed else f"Exit code {result.returncode}",
        report_path=str(report_path) if report_path else None,
    )


def run_ci_checks(
    phase_id: str,
    phase: Dict[str, Any],
    workspace: Path,
    run_id: str,
    project_slug: Optional[str] = None,
    collector_digest_extractor: Optional[Callable] = None,
    is_telemetry_run: bool = False,
) -> Optional[CIResult]:
    """Run CI checks based on phase configuration.

    Main entry point for CI execution. Routes to pytest or custom CI
    based on the phase's CI specification.

    Args:
        phase_id: Phase identifier
        phase: Phase configuration dictionary
        workspace: Workspace root path
        run_id: Run identifier
        project_slug: Optional project identifier for path discovery
        collector_digest_extractor: Optional callback for collection error extraction
        is_telemetry_run: Whether this is a telemetry seeding run

    Returns:
        CIResult or None if CI was skipped for telemetry mode
    """
    # BUILD-141 Part 8: Support AUTOPACK_SKIP_CI=1 for telemetry seeding runs
    if os.getenv("AUTOPACK_SKIP_CI") == "1":
        if is_telemetry_run:
            logger.info(
                f"[{phase_id}] CI skipped (AUTOPACK_SKIP_CI=1 - telemetry seeding mode)"
            )
            return None
        else:
            logger.warning(
                f"[{phase_id}] AUTOPACK_SKIP_CI=1 set but run_id '{run_id}' is not a telemetry run - ignoring flag and running CI normally"
            )

    # Extract CI spec from phase
    scope = phase.get("scope") or {}
    ci_spec_dict = phase.get("ci") or scope.get("ci") or {}
    spec = CISpec.from_dict(ci_spec_dict, phase_id)

    # Check for skip flag
    if spec.skip:
        reason = spec.skip_reason or "CI skipped per phase configuration"
        logger.info(f"[{phase_id}] CI skipped: {reason}")
        return create_skipped_result(reason)

    # Route to appropriate CI runner
    if spec.ci_type == "custom":
        return run_custom_ci(phase_id, spec, workspace, run_id)
    else:
        return run_pytest(
            phase_id,
            spec,
            workspace,
            run_id,
            project_slug=project_slug,
            collector_digest_extractor=collector_digest_extractor,
        )
