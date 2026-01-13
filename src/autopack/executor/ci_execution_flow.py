"""CI execution flow for phase execution.

Extracted from autonomous_executor.py as part of PR-EXE-11.
Handles pytest and custom CI command execution with output parsing and logging.
"""

import logging
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)


class CIExecutionFlow:
    """Orchestrates CI test execution for phase validation.

    Responsibilities:
    1. Execute pytest or custom CI commands
    2. Parse test results and counts
    3. Persist CI logs and JSON reports
    4. Handle timeouts and collection errors
    5. Extract collector error digests
    """

    def __init__(self, executor: "AutonomousExecutor"):
        """Initialize with reference to parent executor.

        Args:
            executor: Parent AutonomousExecutor instance for accessing:
                - run_id: Run identifier for log paths
                - workspace: Workspace root path
                - phase_finalizer: For collector error extraction
        """
        self.executor = executor
        self.run_id = executor.run_id
        self.workspace = executor.workspace
        self.phase_finalizer = executor.phase_finalizer

    def execute_ci_checks(self, phase_id: str, phase: Dict) -> Optional[Dict[str, Any]]:
        """Execute CI checks for a phase.

        Main entry point for CI execution. Routes to pytest or custom CI based on spec.

        Args:
            phase_id: Unique phase identifier
            phase: Phase specification dict

        Returns:
            CI result dict with status, passed, test counts, output, logs, etc.
            Returns None if CI is skipped for telemetry runs.
        """
        # BUILD-141 Part 8: Support AUTOPACK_SKIP_CI=1 for telemetry seeding runs
        # (avoids blocking on unrelated test import errors during telemetry collection)
        # GUARDRAIL: Only honor AUTOPACK_SKIP_CI for telemetry runs to prevent weakening production runs
        if os.getenv("AUTOPACK_SKIP_CI") == "1":
            is_telemetry_run = self.run_id.startswith("telemetry-collection-")
            if is_telemetry_run:
                logger.info(
                    f"[{phase_id}] CI skipped (AUTOPACK_SKIP_CI=1 - telemetry seeding mode)"
                )
                return None  # Return None so PhaseFinalizer doesn't run collection error detection
            else:
                logger.warning(
                    f"[{phase_id}] AUTOPACK_SKIP_CI=1 set but run_id '{self.run_id}' is not a telemetry run - ignoring flag and running CI normally"
                )

        # Phase dict from API does not typically include a top-level "ci". Persisted CI hints live under scope.
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

        ci_type = ci_spec.get("type")
        if ci_spec.get("command") and not ci_type:
            ci_type = "custom"
        if not ci_type:
            ci_type = "pytest"

        if ci_type == "custom":
            return self._run_custom_ci(phase_id, ci_spec)
        else:
            return self._run_pytest_ci(phase_id, ci_spec)

    def _run_pytest_ci(self, phase_id: str, ci_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Execute pytest CI checks.

        Args:
            phase_id: Unique phase identifier
            ci_spec: CI specification dict from phase

        Returns:
            CI result dict with test counts, output, and status
        """
        logger.info(f"[{phase_id}] Running CI checks (pytest)...")

        workdir = Path(self.workspace) / ci_spec.get("workdir", ".")
        if not workdir.exists():
            logger.warning(
                f"[{phase_id}] CI workdir {workdir} missing, defaulting to workspace root"
            )
            workdir = Path(self.workspace)

        pytest_paths = ci_spec.get("paths")
        if not pytest_paths:
            project_slug = self._get_project_slug()
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

        per_test_timeout = ci_spec.get("per_test_timeout", 60)
        default_args = [
            "-v",
            "--tb=line",
            "-q",
            "--no-header",
            f"--timeout={per_test_timeout}",
        ]
        pytest_args = ci_spec.get("args", [])
        # BUILD-127: Emit a structured pytest JSON report so PhaseFinalizer/TestBaselineTracker can
        # compute regressions safely. We still persist a full text log for humans.
        ci_dir = Path(self.workspace) / ".autonomous_runs" / self.run_id / "ci"
        ci_dir.mkdir(parents=True, exist_ok=True)
        json_report_path = ci_dir / ci_spec.get("json_report_name", f"pytest_{phase_id}.json")

        cmd = [sys.executable, "-m", "pytest", *pytest_paths, *default_args, *pytest_args]
        if "--json-report" not in cmd:
            cmd.append("--json-report")
        if not any(str(a).startswith("--json-report-file=") for a in cmd):
            cmd.append(f"--json-report-file={json_report_path}")

        env = os.environ.copy()
        env.setdefault("PYTHONPATH", str(workdir / "src"))
        env["TESTING"] = "1"
        env["PYTHONUTF8"] = "1"
        env.update(ci_spec.get("env", {}))

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
        output = self._trim_ci_output(result.stdout + result.stderr)
        tests_passed, tests_failed, tests_error = self._parse_pytest_counts(output)
        tests_run = tests_passed + tests_failed + tests_error
        passed = result.returncode == 0
        no_tests_detected = tests_run == 0

        error_msg = None
        if no_tests_detected and not passed:
            error_msg = "Possible collection error - no tests detected"
        elif no_tests_detected and passed:
            error_msg = "Warning: pytest reported success but no tests executed"

        # Always persist a CI log so downstream components (dashboard/humans) have a stable artifact.
        full_output = result.stdout + "\n\n--- STDERR ---\n\n" + result.stderr
        log_name = ci_spec.get("log_name", f"pytest_{phase_id}.log")
        log_path = self._persist_ci_log(log_name, full_output, phase_id)

        # Prefer structured JSON report for automated delta computation. Fall back to the log if missing.
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

        message = ci_spec.get("success_message") if passed else ci_spec.get("failure_message")
        if not message:
            if passed:
                message = f"Pytest passed ({tests_passed}/{max(tests_run,1)} tests)"
            else:
                message = error_msg or "Pytest failed"

        if passed:
            logger.info(
                f"[{phase_id}] CI checks PASSED: {tests_passed}/{max(tests_run,1)} tests passed in {duration:.1f}s"
            )
        else:
            logger.warning(f"[{phase_id}] CI checks FAILED: return code {result.returncode}")

        # Extract collector error digest for phase summary and downstream components
        collector_digest = None
        if result.returncode == 2 or (no_tests_detected and not passed):
            # Exitcode 2 typically indicates collection/import errors
            # Extract digest using PhaseFinalizer's helper
            try:
                workspace_path = Path(self.workspace)
                collector_digest = self.phase_finalizer._extract_collection_error_digest(
                    {"report_path": str(report_path) if report_path else None},
                    workspace_path,
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
            "collector_error_digest": collector_digest,  # NEW: Collector error digest
        }

    def _run_custom_ci(self, phase_id: str, ci_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Execute custom CI command.

        Args:
            phase_id: Unique phase identifier
            ci_spec: CI specification dict with custom command

        Returns:
            CI result dict with status and output
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

        workdir = Path(self.workspace) / ci_spec.get("workdir", ".")
        if not workdir.exists():
            logger.warning(
                f"[{phase_id}] CI workdir {workdir} missing, defaulting to workspace root"
            )
            workdir = Path(self.workspace)

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
        output = self._trim_ci_output(result.stdout + result.stderr)
        passed = result.returncode == 0

        # Always persist a CI log so downstream components have a stable report_path.
        full_output = result.stdout + "\n\n--- STDERR ---\n\n" + result.stderr
        log_name = ci_spec.get("log_name", f"ci_{phase_id}.log")
        report_path = self._persist_ci_log(log_name, full_output, phase_id)

        message = ci_spec.get("success_message") if passed else ci_spec.get("failure_message")
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

    def _trim_ci_output(self, output: str, limit: int = 10000) -> str:
        """Trim CI output to prevent excessive log sizes.

        Args:
            output: Raw CI output
            limit: Maximum output length (default 10000 chars)

        Returns:
            Trimmed output with middle section truncated if too long
        """
        if len(output) <= limit:
            return output
        return output[: limit // 2] + "\n\n... (truncated) ...\n\n" + output[-limit // 2 :]

    def _persist_ci_log(self, log_name: str, content: str, phase_id: str) -> Optional[Path]:
        """Persist CI log to disk.

        Args:
            log_name: Name of log file
            content: Log content
            phase_id: Phase identifier for logging

        Returns:
            Path to persisted log, or None if failed
        """
        ci_log_dir = Path(self.workspace) / ".autonomous_runs" / self.run_id / "ci"
        ci_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = ci_log_dir / log_name
        try:
            log_path.write_text(content, encoding="utf-8")
            logger.info(f"[{phase_id}] CI output written to: {log_path}")
            return log_path
        except Exception as log_err:
            logger.warning(f"[{phase_id}] Failed to write CI log ({log_name}): {log_err}")
            return None

    def _parse_pytest_counts(self, output: str) -> tuple[int, int, int]:
        """Parse pytest output for test counts.

        Args:
            output: Pytest output text

        Returns:
            Tuple of (tests_passed, tests_failed, tests_error)
        """
        tests_passed = tests_failed = tests_error = 0
        for line in output.split("\n"):
            line_lower = line.lower()
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

            error_match = re.search(r"(\d+)\s+errors?(?!\s+during)", line_lower)
            if error_match:
                tests_error = int(error_match.group(1))

        return tests_passed, tests_failed, tests_error

    def _get_project_slug(self) -> Optional[str]:
        """Get project slug from executor.

        Returns:
            Project slug if available, None otherwise
        """
        return self.executor._get_project_slug()
