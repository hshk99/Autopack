"""CI Runner - Pytest and custom CI command execution and parsing.

This module extracts CI execution and pytest output parsing logic from
autonomous_executor.py into a testable, standalone module.

Key responsibilities:
- Execute pytest CI checks with proper configuration
- Execute custom CI commands with timeout handling
- Parse pytest output to extract test counts (passed, failed, error)
- Persist CI logs for downstream components
- Trim large CI output to prevent memory issues

Design principles:
- Keep functions pure where possible (subprocess calls isolated)
- Use structured return types for predictable downstream processing
- Support table-driven testing for pytest output parsing
"""

import logging
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


def parse_pytest_counts(output: str) -> Tuple[int, int, int]:
    """Parse pytest output to extract test counts.

    Args:
        output: Raw pytest output (stdout/stderr combined)

    Returns:
        Tuple of (tests_passed, tests_failed, tests_error)

    Examples:
        >>> parse_pytest_counts("===== 5 passed in 0.01s =====")
        (5, 0, 0)
        >>> parse_pytest_counts("===== 3 failed, 2 passed in 1.2s =====")
        (2, 3, 0)
        >>> parse_pytest_counts("===== 1 error, 1 passed =====")
        (1, 0, 1)
    """
    tests_passed = tests_failed = tests_error = 0

    for line in output.split("\n"):
        line_lower = line.lower()

        # Handle collection errors (e.g., "2 errors during collection")
        collection_error = re.search(r"(\d+)\s+errors?\s+during\s+collection", line_lower)
        if collection_error:
            tests_error = int(collection_error.group(1))
            continue

        # Extract passed count
        passed_match = re.search(r"(\d+)\s+passed", line_lower)
        if passed_match:
            tests_passed = int(passed_match.group(1))

        # Extract failed count
        failed_match = re.search(r"(\d+)\s+failed", line_lower)
        if failed_match:
            tests_failed = int(failed_match.group(1))

        # Extract error count (excluding "during collection" which is handled above)
        error_match = re.search(r"(\d+)\s+errors?(?!\s+during)", line_lower)
        if error_match:
            tests_error = int(error_match.group(1))

    return tests_passed, tests_failed, tests_error


def trim_ci_output(output: str, limit: int = 10000) -> str:
    """Trim large CI output to prevent memory issues.

    Keeps first half and last half of output if it exceeds limit.

    Args:
        output: Raw CI output
        limit: Maximum output length in characters

    Returns:
        Trimmed output with truncation indicator if needed
    """
    if len(output) <= limit:
        return output
    return output[: limit // 2] + "\n\n... (truncated) ...\n\n" + output[-limit // 2 :]


def persist_ci_log(
    log_name: str, content: str, phase_id: str, workspace: Path, run_id: str
) -> Optional[Path]:
    """Persist CI log to disk for downstream components.

    Args:
        log_name: Name of the log file (e.g., "pytest_phase1.log")
        content: Full CI output to persist
        phase_id: Phase identifier for logging
        workspace: Workspace root directory
        run_id: Run identifier for organizing logs

    Returns:
        Path to written log file, or None if write failed
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


def run_pytest_ci(
    phase_id: str,
    ci_spec: Dict[str, Any],
    workspace: Path,
    run_id: str,
    project_slug: Optional[str] = None,
    phase_finalizer: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run pytest CI checks based on phase specification.

    Args:
        phase_id: Phase identifier for logging
        ci_spec: CI specification dict with pytest configuration
        workspace: Workspace root directory
        run_id: Run identifier for organizing logs
        project_slug: Project identifier (for path detection heuristics)
        phase_finalizer: Optional phase finalizer for collector error extraction

    Returns:
        Dict with CI result structure:
        {
            "status": "passed" | "failed" | "skipped",
            "message": str,
            "passed": bool,
            "tests_run": int,
            "tests_passed": int,
            "tests_failed": int,
            "tests_error": int,
            "duration_seconds": float,
            "output": str,
            "error": Optional[str],
            "report_path": Optional[str],
            "log_path": Optional[str],
            "skipped": bool,
            "suspicious_zero_tests": bool,
            "collector_error_digest": Optional[List],
        }
    """
    logger.info(f"[{phase_id}] Running CI checks (pytest)...")

    workdir = workspace / ci_spec.get("workdir", ".")
    if not workdir.exists():
        logger.warning(f"[{phase_id}] CI workdir {workdir} missing, defaulting to workspace root")
        workdir = workspace

    # Determine pytest paths
    pytest_paths = ci_spec.get("paths")
    if not pytest_paths:
        # Project-specific path detection
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
                pytest_paths = [path]
                break

    if not pytest_paths:
        logger.warning(f"[{phase_id}] No pytest paths found, skipping CI checks")
        return {
            "status": "skipped",
            "message": "No pytest paths found",
            "passed": True,
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_error": 0,
            "duration_seconds": 0.0,
            "output": "",
            "error": None,
            "skipped": True,
            "suspicious_zero_tests": False,
        }

    # Build pytest command
    per_test_timeout = ci_spec.get("per_test_timeout", 60)
    default_args = [
        "-v",
        "--tb=line",
        "-q",
        "--no-header",
        f"--timeout={per_test_timeout}",
    ]
    pytest_args = ci_spec.get("args", [])

    # Setup JSON report path for structured output
    ci_dir = workspace / ".autonomous_runs" / run_id / "ci"
    ci_dir.mkdir(parents=True, exist_ok=True)
    json_report_path = ci_dir / ci_spec.get("json_report_name", f"pytest_{phase_id}.json")

    cmd = [sys.executable, "-m", "pytest", *pytest_paths, *default_args, *pytest_args]
    if "--json-report" not in cmd:
        cmd.append("--json-report")
    if not any(str(a).startswith("--json-report-file=") for a in cmd):
        cmd.append(f"--json-report-file={json_report_path}")

    # Setup environment
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(workdir / "src"))
    env["TESTING"] = "1"
    env["PYTHONUTF8"] = "1"
    env.update(ci_spec.get("env", {}))

    # Execute pytest with timeout
    timeout_seconds = ci_spec.get("timeout_seconds") or ci_spec.get("timeout") or 300
    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        logger.error(f"[{phase_id}] Pytest timeout after {duration:.1f}s")
        return {
            "status": "failed",
            "message": f"pytest timed out after {timeout_seconds}s",
            "passed": False,
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_error": 0,
            "duration_seconds": round(duration, 2),
            "output": "",
            "error": f"pytest timed out after {timeout_seconds}s",
            "skipped": False,
            "suspicious_zero_tests": False,
        }

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

    # Persist full CI log
    full_output = result.stdout + "\n\n--- STDERR ---\n\n" + result.stderr
    log_name = ci_spec.get("log_name", f"pytest_{phase_id}.log")
    log_path = persist_ci_log(log_name, full_output, phase_id, workspace, run_id)

    # Prefer structured JSON report, fall back to log
    report_path: Optional[Path] = None
    try:
        if json_report_path.exists() and json_report_path.stat().st_size > 0:
            report_path = json_report_path
    except Exception:
        report_path = None
    if report_path is None:
        report_path = log_path

    if not passed and not error_msg:
        error_msg = f"pytest exited with code {result.returncode}"

    # Build result message
    message = ci_spec.get("success_message") if passed else ci_spec.get("failure_message")
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

    # Extract collector error digest if phase_finalizer is available
    collector_digest = None
    if phase_finalizer and (result.returncode == 2 or (no_tests_detected and not passed)):
        try:
            collector_digest = phase_finalizer._extract_collection_error_digest(
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

    return {
        "status": "passed" if passed else "failed",
        "message": message,
        "passed": passed,
        "tests_run": tests_run,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "tests_error": tests_error,
        "duration_seconds": round(duration, 2),
        "output": output,
        "error": error_msg,
        "report_path": str(report_path) if report_path else None,
        "log_path": str(log_path) if log_path else None,
        "skipped": False,
        "suspicious_zero_tests": no_tests_detected,
        "collector_error_digest": collector_digest,
    }


def run_custom_ci(
    phase_id: str,
    ci_spec: Dict[str, Any],
    workspace: Path,
    run_id: str,
) -> Dict[str, Any]:
    """Run custom CI command based on phase specification.

    Args:
        phase_id: Phase identifier for logging
        ci_spec: CI specification dict with custom command configuration
        workspace: Workspace root directory
        run_id: Run identifier for organizing logs

    Returns:
        Dict with CI result structure (same as run_pytest_ci)
    """
    command = ci_spec.get("command")
    if not command:
        logger.warning(f"[{phase_id}] CI spec missing 'command'; skipping")
        return {
            "status": "skipped",
            "message": "CI command not configured",
            "passed": True,
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_error": 0,
            "duration_seconds": 0.0,
            "output": "",
            "error": None,
            "skipped": True,
            "suspicious_zero_tests": False,
        }

    workdir = workspace / ci_spec.get("workdir", ".")
    if not workdir.exists():
        logger.warning(f"[{phase_id}] CI workdir {workdir} missing, defaulting to workspace root")
        workdir = workspace

    # Setup command execution
    timeout_seconds = ci_spec.get("timeout_seconds") or ci_spec.get("timeout") or 600
    env = os.environ.copy()
    env.update(ci_spec.get("env", {}))

    shell = ci_spec.get("shell", isinstance(command, str))
    cmd = command
    if isinstance(command, str) and not shell:
        cmd = shlex.split(command)

    logger.info(f"[{phase_id}] Running custom CI command: {command}")
    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
            shell=shell,
        )
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        logger.error(f"[{phase_id}] CI command timeout after {duration:.1f}s")
        return {
            "status": "failed",
            "message": f"CI command timed out after {timeout_seconds}s",
            "passed": False,
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_error": 0,
            "duration_seconds": round(duration, 2),
            "output": "",
            "error": f"Command timed out after {timeout_seconds}s",
            "skipped": False,
            "suspicious_zero_tests": False,
        }

    duration = time.time() - start_time
    output = trim_ci_output(result.stdout + result.stderr)
    passed = result.returncode == 0

    # Persist full CI log
    full_output = result.stdout + "\n\n--- STDERR ---\n\n" + result.stderr
    log_name = ci_spec.get("log_name", f"ci_{phase_id}.log")
    report_path = persist_ci_log(log_name, full_output, phase_id, workspace, run_id)

    # Build result message
    message = ci_spec.get("success_message") if passed else ci_spec.get("failure_message")
    if not message:
        message = (
            "CI command succeeded" if passed else f"CI command failed (exit {result.returncode})"
        )

    if passed:
        logger.info(f"[{phase_id}] Custom CI command passed in {duration:.1f}s")
    else:
        logger.warning(f"[{phase_id}] Custom CI command failed (exit {result.returncode})")

    return {
        "status": "passed" if passed else "failed",
        "message": message,
        "passed": passed,
        "tests_run": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "tests_error": 0,
        "duration_seconds": round(duration, 2),
        "output": output,
        "error": None if passed else f"Exit code {result.returncode}",
        "report_path": str(report_path) if report_path else None,
        "skipped": False,
        "suspicious_zero_tests": False,
    }


def run_ci_checks(
    phase_id: str,
    phase: Dict[str, Any],
    workspace: Path,
    run_id: str,
    project_slug: Optional[str] = None,
    phase_finalizer: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """Run CI checks based on phase specification.

    Main entry point for CI execution. Delegates to pytest or custom CI runner.

    Args:
        phase_id: Phase identifier for logging
        phase: Full phase dict from API
        workspace: Workspace root directory
        run_id: Run identifier for organizing logs
        project_slug: Project identifier (for path detection heuristics)
        phase_finalizer: Optional phase finalizer for collector error extraction

    Returns:
        CI result dict, or None if CI should be skipped
    """
    # Support AUTOPACK_SKIP_CI=1 for telemetry seeding runs
    if os.getenv("AUTOPACK_SKIP_CI") == "1":
        is_telemetry_run = run_id.startswith("telemetry-collection-")
        if is_telemetry_run:
            logger.info(f"[{phase_id}] CI skipped (AUTOPACK_SKIP_CI=1 - telemetry seeding mode)")
            return None
        else:
            logger.warning(
                f"[{phase_id}] AUTOPACK_SKIP_CI=1 set but run_id '{run_id}' is not a telemetry run - ignoring flag and running CI normally"
            )

    # Extract CI spec from phase
    scope = phase.get("scope") or {}
    ci_spec = phase.get("ci") or scope.get("ci") or {}

    if ci_spec.get("skip"):
        reason = ci_spec.get("reason", "CI skipped per phase configuration")
        logger.info(f"[{phase_id}] CI skipped: {reason}")
        return {
            "status": "skipped",
            "message": reason,
            "passed": True,
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_error": 0,
            "duration_seconds": 0.0,
            "output": "",
            "error": None,
            "skipped": True,
            "suspicious_zero_tests": False,
        }

    # Determine CI type
    ci_type = ci_spec.get("type")
    if ci_spec.get("command") and not ci_type:
        ci_type = "custom"
    if not ci_type:
        ci_type = "pytest"

    # Delegate to appropriate runner
    if ci_type == "custom":
        return run_custom_ci(phase_id, ci_spec, workspace, run_id)
    else:
        return run_pytest_ci(phase_id, ci_spec, workspace, run_id, project_slug, phase_finalizer)
