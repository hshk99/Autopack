"""Quality Gate with Automated Validation and Git-Based Rollback.

Provides quality assessment with checkpoint/rollback capabilities for safe phase execution.

Architecture:
- Git checkpoint creation before phase execution
- Validation test execution after phase completion
- Rollback mechanism on validation failure
- Risk-based enforcement with configurable thresholds

Usage:
    gate = QualityGate(repo_root=Path("."))
    
    # Create checkpoint before phase
    checkpoint_id = gate.create_checkpoint(phase_id="phase-1")
    
    # Execute phase...
    
    # Run validation tests
    if not gate.run_validation_tests(["tests/test_feature.py"]):
        # Rollback on failure
        gate.rollback_to_checkpoint(checkpoint_id)
    
    # Enforce quality gate
    report = gate.assess_phase(...)
    if report.is_blocked():
        gate.rollback_to_checkpoint(checkpoint_id)
"""

import logging
import subprocess
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class QualityReport:
    """Quality assessment report."""
    quality_level: str = "PASS"
    is_blocking: bool = False
    issues: List[str] = field(default_factory=list)
    risk_assessment: Optional[Dict] = None

    def is_blocked(self) -> bool:
        """Check if quality gate blocks execution."""
        return self.is_blocking


@dataclass
class ValidationResult:
    """Validation test execution result."""
    success: bool
    tests_run: int
    tests_passed: int
    tests_failed: int
    output: str
    error: Optional[str] = None


@dataclass
class CheckpointInfo:
    """Git checkpoint information."""
    checkpoint_id: str
    phase_id: str
    commit_sha: str
    branch: str
    timestamp: str
    stash_ref: Optional[str] = None


class QualityGate:
    """Quality Gate with validation and rollback capabilities.

    Provides:
    - Git checkpoint management
    - Validation test execution
    - Automated rollback on failure
    - Risk-based quality assessment
    """

    def __init__(self, repo_root: Path, config: Optional[Dict] = None):
        """Initialize quality gate.

        Args:
            repo_root: Repository root path
            config: Configuration dict with optional settings:
                - test_timeout: Test execution timeout in seconds (default: 300)
                - checkpoint_prefix: Git tag prefix for checkpoints (default: "autopack-checkpoint")
                - auto_rollback: Enable automatic rollback on validation failure (default: True)
        """
        self.repo_root = repo_root
        self.config = config or {}
        self.test_timeout = self.config.get("test_timeout", 300)
        self.checkpoint_prefix = self.config.get("checkpoint_prefix", "autopack-checkpoint")
        self.auto_rollback = self.config.get("auto_rollback", True)
        self._checkpoints: Dict[str, CheckpointInfo] = {}

    def create_checkpoint(self, phase_id: str) -> str:
        """Create git checkpoint before phase execution.

        Creates a git tag and optionally stashes uncommitted changes.

        Args:
            phase_id: Phase identifier

        Returns:
            Checkpoint ID for later rollback

        Raises:
            RuntimeError: If checkpoint creation fails
        """
        try:
            # Get current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            branch = result.stdout.strip()

            # Get current commit SHA
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            commit_sha = result.stdout.strip()

            # Check for uncommitted changes
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            has_changes = bool(result.stdout.strip())

            # Stash uncommitted changes if present
            stash_ref = None
            if has_changes:
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                stash_message = f"{self.checkpoint_prefix}-{phase_id}-{timestamp}"
                result = subprocess.run(
                    ["git", "stash", "push", "-m", stash_message],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=30
                )
                # Get stash reference
                result = subprocess.run(
                    ["git", "stash", "list"],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=10
                )
                stash_lines = result.stdout.strip().split("\n")
                if stash_lines and stash_message in stash_lines[0]:
                    stash_ref = stash_lines[0].split(":")[0]
                logger.info(f"[QualityGate] Stashed uncommitted changes: {stash_ref}")

            # Create checkpoint tag
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            checkpoint_id = f"{self.checkpoint_prefix}-{phase_id}-{timestamp}"
            subprocess.run(
                ["git", "tag", "-a", checkpoint_id, "-m", f"Checkpoint for phase {phase_id}"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )

            # Store checkpoint info
            checkpoint_info = CheckpointInfo(
                checkpoint_id=checkpoint_id,
                phase_id=phase_id,
                commit_sha=commit_sha,
                branch=branch,
                timestamp=timestamp,
                stash_ref=stash_ref
            )
            self._checkpoints[checkpoint_id] = checkpoint_info

            logger.info(f"[QualityGate] Created checkpoint: {checkpoint_id} (commit: {commit_sha[:8]})")
            return checkpoint_id

        except subprocess.CalledProcessError as e:
            error_msg = f"Failed to create checkpoint: {e.stderr}"
            logger.error(f"[QualityGate] {error_msg}")
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error creating checkpoint: {str(e)}"
            logger.error(f"[QualityGate] {error_msg}")
            raise RuntimeError(error_msg)

    def run_validation_tests(self, test_paths: List[str]) -> bool:
        """Run validation tests after phase completion.

        Args:
            test_paths: List of test file/directory paths to execute

        Returns:
            True if all tests pass, False otherwise
        """
        if not test_paths:
            logger.warning("[QualityGate] No validation tests specified, skipping")
            return True

        try:
            # Run pytest with specified paths
            cmd = ["pytest", "-v", "--tb=short"] + test_paths
            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=self.test_timeout
            )

            # Parse pytest output
            output = result.stdout + result.stderr
            success = result.returncode == 0

            # Extract test counts from output
            tests_run = 0
            tests_passed = 0
            tests_failed = 0
            for line in output.split("\n"):
                if "passed" in line.lower():
                    # Parse "X passed" or "X passed, Y failed"
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "passed" and i > 0:
                            try:
                                tests_passed = int(parts[i-1])
                            except ValueError:
                                pass
                        elif part == "failed" and i > 0:
                            try:
                                tests_failed = int(parts[i-1])
                            except ValueError:
                                pass
            tests_run = tests_passed + tests_failed

            validation_result = ValidationResult(
                success=success,
                tests_run=tests_run,
                tests_passed=tests_passed,
                tests_failed=tests_failed,
                output=output,
                error=None if success else f"Tests failed: {tests_failed}/{tests_run}"
            )

            if success:
                logger.info(f"[QualityGate] Validation tests passed: {tests_passed}/{tests_run}")
            else:
                logger.error(f"[QualityGate] Validation tests failed: {tests_failed}/{tests_run}")
                logger.debug(f"[QualityGate] Test output:\n{output}")

            return success

        except subprocess.TimeoutExpired:
            logger.error(f"[QualityGate] Validation tests timed out after {self.test_timeout}s")
            return False
        except Exception as e:
            logger.error(f"[QualityGate] Error running validation tests: {str(e)}")
            return False

    def rollback_to_checkpoint(self, checkpoint_id: str) -> bool:
        """Rollback to a previous checkpoint.

        Resets git state to checkpoint commit and restores stashed changes if present.

        Args:
            checkpoint_id: Checkpoint ID from create_checkpoint()

        Returns:
            True if rollback successful, False otherwise
        """
        if checkpoint_id not in self._checkpoints:
            logger.error(f"[QualityGate] Unknown checkpoint: {checkpoint_id}")
            return False

        checkpoint = self._checkpoints[checkpoint_id]

        try:
            # Reset to checkpoint commit
            subprocess.run(
                ["git", "reset", "--hard", checkpoint.commit_sha],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            logger.info(f"[QualityGate] Reset to checkpoint commit: {checkpoint.commit_sha[:8]}")

            # Restore stashed changes if present
            if checkpoint.stash_ref:
                try:
                    subprocess.run(
                        ["git", "stash", "pop", checkpoint.stash_ref],
                        cwd=self.repo_root,
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=30
                    )
                    logger.info(f"[QualityGate] Restored stashed changes: {checkpoint.stash_ref}")
                except subprocess.CalledProcessError as e:
                    logger.warning(f"[QualityGate] Failed to restore stash (may have conflicts): {e.stderr}")

            # Delete checkpoint tag
            try:
                subprocess.run(
                    ["git", "tag", "-d", checkpoint_id],
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=10
                )
                logger.info(f"[QualityGate] Deleted checkpoint tag: {checkpoint_id}")
            except subprocess.CalledProcessError:
                logger.warning(f"[QualityGate] Failed to delete checkpoint tag: {checkpoint_id}")

            # Remove from tracking
            del self._checkpoints[checkpoint_id]

            logger.info(f"[QualityGate] Rollback to checkpoint {checkpoint_id} completed")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"[QualityGate] Rollback failed: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"[QualityGate] Unexpected error during rollback: {str(e)}")
            return False

    def enforce_quality_gate(
        self,
        phase_id: str,
        checkpoint_id: str,
        validation_tests: List[str],
        phase_spec: Any,
        auditor_result: Dict,
        ci_result: Dict,
        coverage_delta: float,
        patch_content: str,
        files_changed: Optional[List[str]] = None,
    ) -> QualityReport:
        """Enforce quality gate with automated validation and rollback.

        Workflow:
        1. Run validation tests
        2. Assess phase quality
        3. Rollback if validation fails or quality blocked

        Args:
            phase_id: Phase identifier
            checkpoint_id: Checkpoint ID from create_checkpoint()
            validation_tests: List of test paths to validate
            phase_spec: Phase specification
            auditor_result: Auditor review result
            ci_result: CI test results
            coverage_delta: Code coverage change
            patch_content: Patch content
            files_changed: List of changed files

        Returns:
            QualityReport with assessment and rollback status
        """
        # Run validation tests
        validation_passed = self.run_validation_tests(validation_tests)

        # Assess phase quality
        report = self.assess_phase(
            phase_id=phase_id,
            phase_spec=phase_spec,
            auditor_result=auditor_result,
            ci_result=ci_result,
            coverage_delta=coverage_delta,
            patch_content=patch_content,
            files_changed=files_changed
        )

        # Check if rollback needed
        should_rollback = False
        if not validation_passed:
            report.issues.append("Validation tests failed")
            report.is_blocking = True
            should_rollback = True

        if report.is_blocked():
            should_rollback = True

        # Perform rollback if needed and auto_rollback enabled
        if should_rollback and self.auto_rollback:
            logger.warning(f"[QualityGate] Quality gate blocked, initiating rollback for phase {phase_id}")
            rollback_success = self.rollback_to_checkpoint(checkpoint_id)
            if rollback_success:
                report.issues.append("Rolled back to checkpoint")
            else:
                report.issues.append("Rollback failed - manual intervention required")

        return report

    def assess_phase(
        self,
        phase_id: str,
        phase_spec: Any,
        auditor_result: Dict,
        ci_result: Dict,
        coverage_delta: float,
        patch_content: str,
        files_changed: Optional[List[str]] = None,
    ) -> QualityReport:
        """Assess phase quality (basic implementation).

        Args:
            phase_id: Phase identifier
            phase_spec: Phase specification
            auditor_result: Auditor review result
            ci_result: CI test results
            coverage_delta: Code coverage change
            patch_content: Patch content
            files_changed: List of changed files

        Returns:
            QualityReport with assessment
        """
        issues = []
        is_blocking = False

        # Check auditor approval
        if auditor_result.get("approved") is False:
            issues.append("Auditor rejected changes")
            is_blocking = True

        # Check CI results
        if ci_result.get("success") is False:
            issues.append("CI tests failed")
            is_blocking = True

        # Check coverage delta (warn if decreased)
        if coverage_delta < -5.0:
            issues.append(f"Code coverage decreased by {abs(coverage_delta):.1f}%")
            # Not blocking by default, but logged

        # Determine quality level
        if is_blocking:
            quality_level = "BLOCKED"
        elif issues:
            quality_level = "WARNING"
        else:
            quality_level = "PASS"

        return QualityReport(
            quality_level=quality_level,
            is_blocking=is_blocking,
            issues=issues,
            risk_assessment={
                "auditor_approved": auditor_result.get("approved", False),
                "ci_passed": ci_result.get("success", False),
                "coverage_delta": coverage_delta,
                "files_changed_count": len(files_changed) if files_changed else 0,
            }
        )

    def format_report(self, report: QualityReport) -> str:
        """Format quality report for display.

        Args:
            report: Quality report to format

        Returns:
            Formatted report string
        """
        lines = [
            f"Quality Gate: {report.quality_level}",
            f"Blocking: {report.is_blocking}",
        ]

        if report.issues:
            lines.append("\nIssues:")
            for issue in report.issues:
                lines.append(f"  - {issue}")

        if report.risk_assessment:
            lines.append("\nRisk Assessment:")
            for key, value in report.risk_assessment.items():
                lines.append(f"  {key}: {value}")

        return "\n".join(lines)


def integrate_with_auditor(
    auditor_result: Dict,
    quality_report: QualityReport
) -> Dict:
    """Integrate quality gate report with auditor result.

    Args:
        auditor_result: Auditor result
        quality_report: Quality gate report

    Returns:
        Combined result dict
    """
    return {
        **auditor_result,
        "quality_gate": {
            "level": quality_report.quality_level,
            "is_blocking": quality_report.is_blocking,
            "issues": quality_report.issues,
            "risk_assessment": quality_report.risk_assessment,
        }
    }
