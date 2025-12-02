"""Health check system for pre-run validation.

Implements T0 (quick) and T1 (comprehensive) health checks to validate
system readiness before autonomous execution.
"""

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal

import yaml


@dataclass
class HealthCheckResult:
    """Result of a single health check."""

    check_name: str
    passed: bool
    message: str
    duration_ms: int


class HealthChecker:
    """Performs system health checks at different tiers."""

    def __init__(self, workspace_path: Path, config_dir: Path):
        """
        Initialize health checker.

        Args:
            workspace_path: Path to the workspace directory
            config_dir: Path to the config directory
        """
        self.workspace_path = workspace_path
        self.config_dir = config_dir

    def _time_check(self, check_func) -> HealthCheckResult:
        """
        Execute a check function and time it.

        Args:
            check_func: Function that returns (check_name, passed, message)

        Returns:
            HealthCheckResult with timing information
        """
        start_time = time.time()
        check_name, passed, message = check_func()
        duration_ms = int((time.time() - start_time) * 1000)
        return HealthCheckResult(
            check_name=check_name,
            passed=passed,
            message=message,
            duration_ms=duration_ms,
        )

    # T0 Checks (quick, always run)

    def check_api_keys(self) -> tuple[str, bool, str]:
        """
        Verify required API keys are present.

        Returns:
            Tuple of (check_name, passed, message)
        """
        required_keys = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"]
        missing_keys = []

        for key in required_keys:
            if not os.environ.get(key):
                missing_keys.append(key)

        if missing_keys:
            return (
                "API Keys",
                False,
                f"Missing API keys: {', '.join(missing_keys)}",
            )

        return ("API Keys", True, "All required API keys present")

    def check_database(self) -> tuple[str, bool, str]:
        """
        Verify SQLite database file exists and is writable.

        Returns:
            Tuple of (check_name, passed, message)
        """
        db_path = self.workspace_path / "autopack.db"

        if not db_path.exists():
            return (
                "Database",
                False,
                f"Database file not found: {db_path}",
            )

        if not os.access(db_path, os.W_OK):
            return (
                "Database",
                False,
                f"Database file not writable: {db_path}",
            )

        return ("Database", True, f"Database accessible: {db_path}")

    def check_workspace(self) -> tuple[str, bool, str]:
        """
        Verify workspace path exists and is a git repository.

        Returns:
            Tuple of (check_name, passed, message)
        """
        if not self.workspace_path.exists():
            return (
                "Workspace",
                False,
                f"Workspace path does not exist: {self.workspace_path}",
            )

        git_dir = self.workspace_path / ".git"
        if not git_dir.exists():
            return (
                "Workspace",
                False,
                f"Workspace is not a git repository: {self.workspace_path}",
            )

        return ("Workspace", True, f"Workspace valid: {self.workspace_path}")

    def check_config(self) -> tuple[str, bool, str]:
        """
        Verify models.yaml and pricing.yaml exist and are parseable.

        Returns:
            Tuple of (check_name, passed, message)
        """
        models_path = self.config_dir / "models.yaml"
        pricing_path = self.config_dir / "pricing.yaml"

        if not models_path.exists():
            return (
                "Config",
                False,
                f"models.yaml not found: {models_path}",
            )

        if not pricing_path.exists():
            return (
                "Config",
                False,
                f"pricing.yaml not found: {pricing_path}",
            )

        # Try parsing models.yaml
        try:
            with open(models_path, "r") as f:
                models_data = yaml.safe_load(f)
                if not models_data or "complexity_models" not in models_data:
                    return (
                        "Config",
                        False,
                        "models.yaml missing 'complexity_models' section",
                    )
        except yaml.YAMLError as e:
            return (
                "Config",
                False,
                f"Failed to parse models.yaml: {e}",
            )

        # Try parsing pricing.yaml
        try:
            with open(pricing_path, "r") as f:
                pricing_data = yaml.safe_load(f)
                if not pricing_data:
                    return (
                        "Config",
                        False,
                        "pricing.yaml is empty or invalid",
                    )
        except yaml.YAMLError as e:
            return (
                "Config",
                False,
                f"Failed to parse pricing.yaml: {e}",
            )

        return ("Config", True, "Configuration files valid")

    # T1 Checks (longer, configurable)

    def check_test_suite(self) -> tuple[str, bool, str]:
        """
        Run pytest --collect-only to verify tests exist.

        Returns:
            Tuple of (check_name, passed, message)
        """
        try:
            result = subprocess.run(
                ["pytest", "--collect-only", "-q"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return (
                    "Test Suite",
                    False,
                    f"pytest collection failed: {result.stderr}",
                )

            # Parse output to count tests
            output = result.stdout
            if "no tests ran" in output.lower() or not output.strip():
                return (
                    "Test Suite",
                    False,
                    "No tests found in test suite",
                )

            return ("Test Suite", True, "Test suite collection successful")

        except subprocess.TimeoutExpired:
            return (
                "Test Suite",
                False,
                "pytest collection timed out after 30s",
            )
        except FileNotFoundError:
            return (
                "Test Suite",
                False,
                "pytest not found - install test dependencies",
            )
        except Exception as e:
            return (
                "Test Suite",
                False,
                f"Test collection error: {e}",
            )

    def check_dependencies(self) -> tuple[str, bool, str]:
        """
        Run pip check to verify no missing packages.

        Returns:
            Tuple of (check_name, passed, message)
        """
        try:
            result = subprocess.run(
                ["pip", "check"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return (
                    "Dependencies",
                    False,
                    f"Dependency issues found: {result.stdout}",
                )

            return ("Dependencies", True, "All dependencies satisfied")

        except subprocess.TimeoutExpired:
            return (
                "Dependencies",
                False,
                "pip check timed out after 30s",
            )
        except Exception as e:
            return (
                "Dependencies",
                False,
                f"Dependency check error: {e}",
            )

    def check_git_clean(self) -> tuple[str, bool, str]:
        """
        Verify no uncommitted changes in git.

        Returns:
            Tuple of (check_name, passed, message)
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.stdout.strip():
                return (
                    "Git Clean",
                    False,
                    "Uncommitted changes detected",
                )

            return ("Git Clean", True, "Working directory clean")

        except Exception as e:
            return (
                "Git Clean",
                False,
                f"Git status check error: {e}",
            )

    def check_git_remote(self) -> tuple[str, bool, str]:
        """
        Verify branch is up to date with remote.

        Returns:
            Tuple of (check_name, passed, message)
        """
        try:
            # Fetch remote
            subprocess.run(
                ["git", "fetch"],
                cwd=self.workspace_path,
                capture_output=True,
                timeout=30,
            )

            # Check if branch is behind
            result = subprocess.run(
                ["git", "status", "-sb"],
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                timeout=10,
            )

            output = result.stdout
            if "behind" in output.lower():
                return (
                    "Git Remote",
                    False,
                    "Branch is behind remote",
                )

            return ("Git Remote", True, "Branch up to date with remote")

        except Exception as e:
            return (
                "Git Remote",
                False,
                f"Git remote check error: {e}",
            )


def run_health_checks(
    tier: Literal["t0", "t1"],
    workspace_path: Path | None = None,
    config_dir: Path | None = None,
) -> List[HealthCheckResult]:
    """
    Run health checks at the specified tier.

    Args:
        tier: Check tier to run ("t0" for quick, "t1" for comprehensive)
        workspace_path: Path to workspace (defaults to current directory)
        config_dir: Path to config directory (defaults to ./config)

    Returns:
        List of HealthCheckResult objects
    """
    if workspace_path is None:
        workspace_path = Path.cwd()
    if config_dir is None:
        config_dir = Path.cwd() / "config"

    checker = HealthChecker(workspace_path, config_dir)
    results = []

    # T0 checks (always run)
    t0_checks = [
        checker.check_api_keys,
        checker.check_database,
        checker.check_workspace,
        checker.check_config,
    ]

    for check in t0_checks:
        results.append(checker._time_check(check))

    # T1 checks (only if requested)
    if tier == "t1":
        t1_checks = [
            checker.check_test_suite,
            checker.check_dependencies,
            checker.check_git_clean,
            checker.check_git_remote,
        ]

        for check in t1_checks:
            results.append(checker._time_check(check))

    return results
