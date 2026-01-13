"""Pytest CI runner for Autopack.

Extracted from autonomous_executor.py as part of PR-EXE-13.
Handles pytest execution with coverage, parallel execution, and result parsing.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Any
from pathlib import Path
import subprocess
import sys
import os
import time
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class PytestRunResult:
    """Result of pytest execution."""

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
    log_path: Optional[str] = None
    skipped: bool = False
    suspicious_zero_tests: bool = False
    collector_error_digest: Optional[Dict] = None


class PytestRunner:
    """Runs pytest for CI validation.

    Responsibilities:
    1. Execute pytest with correct options
    2. Parse pytest output
    3. Extract test results
    4. Handle pytest failures
    """

    def __init__(self, workspace: Path, run_id: str, phase_finalizer=None):
        self.workspace = workspace
        self.run_id = run_id
        self.phase_finalizer = phase_finalizer

    def run(
        self,
        phase_id: str,
        ci_spec: Dict[str, Any],
        project_slug: Optional[str] = None,
    ) -> PytestRunResult:
        """Run pytest tests.

        Args:
            phase_id: Phase identifier
            ci_spec: CI configuration specification
            project_slug: Project slug for path resolution

        Returns:
            PytestRunResult with execution details
        """
        logger.info(f"[{phase_id}] Running CI checks (pytest)...")

        workdir = self.workspace / ci_spec.get("workdir", ".")
        if not workdir.exists():
            logger.warning(
                f"[{phase_id}] CI workdir {workdir} missing, defaulting to workspace root"
            )
            workdir = self.workspace

        pytest_paths = ci_spec.get("paths")
        if not pytest_paths:
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
            return PytestRunResult(
                status="skipped",
                message="No pytest paths found",
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
        ci_dir = self.workspace / ".autonomous_runs" / self.run_id / "ci"
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
            return PytestRunResult(
                status="failed",
                message=f"pytest timed out after {timeout_seconds}s",
                passed=False,
                tests_run=0,
                tests_passed=0,
                tests_failed=0,
                tests_error=0,
                duration_seconds=round(duration, 2),
                output="",
                error=f"pytest timed out after {timeout_seconds}s",
                skipped=False,
                suspicious_zero_tests=False,
            )

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
            if self.phase_finalizer:
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

        return PytestRunResult(
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
            skipped=False,
            suspicious_zero_tests=no_tests_detected,
            collector_error_digest=collector_digest,
        )

    def _parse_pytest_counts(self, output: str) -> tuple[int, int, int]:
        """Parse pytest output to extract test counts."""
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
