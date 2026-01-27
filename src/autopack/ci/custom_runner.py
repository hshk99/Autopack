"""Custom CI runner for Autopack.

Extracted from autonomous_executor.py as part of PR-EXE-13.
Handles custom CI scripts defined in project configuration.
"""

import logging
import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class CustomCIResult:
    """Result of custom CI execution."""

    status: str
    message: str
    passed: bool
    tests_run: int
    tests_passed: int
    tests_failed: int
    tests_error: int
    duration_seconds: float
    output: str
    error: Optional[str] = None
    report_path: Optional[str] = None
    skipped: bool = False
    suspicious_zero_tests: bool = False


class CustomRunner:
    """Runs custom CI scripts.

    Responsibilities:
    1. Execute custom CI commands
    2. Handle script failures
    3. Parse custom output formats
    """

    def __init__(self, workspace: Path, run_id: str):
        self.workspace = workspace
        self.run_id = run_id

    def run(
        self,
        phase_id: str,
        ci_spec: Dict[str, Any],
    ) -> CustomCIResult:
        """Run custom CI script.

        Args:
            phase_id: Phase identifier
            ci_spec: CI configuration specification

        Returns:
            CustomCIResult with execution details
        """
        command = ci_spec.get("command")
        if not command:
            logger.warning(f"[{phase_id}] CI spec missing 'command'; skipping")
            return CustomCIResult(
                status="skipped",
                message="CI command not configured",
                passed=True,
                tests_run=0,
                tests_passed=0,
                tests_failed=0,
                tests_error=0,
                duration_seconds=0.0,
                output="",
                error=None,
                skipped=True,
                suspicious_zero_tests=False,
            )

        workdir = self.workspace / ci_spec.get("workdir", ".")
        if not workdir.exists():
            logger.warning(
                f"[{phase_id}] CI workdir {workdir} missing, defaulting to workspace root"
            )
            workdir = self.workspace

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
            return CustomCIResult(
                status="failed",
                message=f"CI command timed out after {timeout_seconds}s",
                passed=False,
                tests_run=0,
                tests_passed=0,
                tests_failed=0,
                tests_error=0,
                duration_seconds=round(duration, 2),
                output="",
                error=f"Command timed out after {timeout_seconds}s",
                skipped=False,
                suspicious_zero_tests=False,
            )

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

        return CustomCIResult(
            status="passed" if passed else "failed",
            message=message,
            passed=passed,
            tests_run=0,
            tests_passed=0,
            tests_failed=0,
            tests_error=0,
            duration_seconds=round(duration, 2),
            output=output,
            error=None if passed else f"Exit code {result.returncode}",
            report_path=str(report_path) if report_path else None,
            skipped=False,
            suspicious_zero_tests=False,
        )

    def _trim_ci_output(self, output: str, limit: int = 10000) -> str:
        """Trim CI output to reasonable size."""
        if len(output) <= limit:
            return output
        return output[: limit // 2] + "\n\n... (truncated) ...\n\n" + output[-limit // 2 :]

    def _persist_ci_log(self, log_name: str, content: str, phase_id: str) -> Optional[Path]:
        """Persist CI log to file."""
        ci_log_dir = self.workspace / ".autonomous_runs" / self.run_id / "ci"
        ci_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = ci_log_dir / log_name
        try:
            log_path.write_text(content, encoding="utf-8")
            logger.info(f"[{phase_id}] CI output written to: {log_path}")
            return log_path
        except Exception as log_err:
            logger.warning(f"[{phase_id}] Failed to write CI log ({log_name}): {log_err}")
            return None
