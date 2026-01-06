"""Action executor for safe autopilot execution (BUILD-180).

Provides a bounded executor that only runs safe actions.
Unsafe actions are classified and returned without execution.
"""

import logging
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List

from .action_allowlist import (
    ActionType,
    ActionClassification,
    classify_action,
)

logger = logging.getLogger(__name__)


@dataclass
class ActionExecutionResult:
    """Result of an action execution attempt."""

    action_type: ActionType
    target: str
    classification: ActionClassification
    executed: bool
    success: bool = False
    reason: str = ""
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None


class ActionExecutor(ABC):
    """Abstract base class for action executors."""

    @abstractmethod
    def execute_command(self, command: str) -> ActionExecutionResult:
        """Execute a command.

        Args:
            command: Command string to execute

        Returns:
            ActionExecutionResult
        """
        pass

    @abstractmethod
    def write_artifact(self, path: str, content: str) -> ActionExecutionResult:
        """Write an artifact file.

        Args:
            path: Relative path to write to
            content: Content to write

        Returns:
            ActionExecutionResult
        """
        pass

    @abstractmethod
    def read_file(self, path: str) -> ActionExecutionResult:
        """Read a file.

        Args:
            path: Relative path to read

        Returns:
            ActionExecutionResult with content in stdout
        """
        pass


class SafeActionExecutor(ActionExecutor):
    """Executor that only runs safe actions.

    Actions that require approval are classified but not executed.
    Only read-only commands and run-local artifact writes are executed.
    """

    def __init__(
        self,
        workspace_root: Path,
        command_timeout: int = 30,
        dry_run: bool = False,
    ):
        """Initialize safe action executor.

        Args:
            workspace_root: Root directory for workspace
            command_timeout: Timeout in seconds for commands
            dry_run: If True, don't actually execute anything
        """
        self.workspace_root = workspace_root
        self.command_timeout = command_timeout
        self.dry_run = dry_run

    def execute_command(self, command: str) -> ActionExecutionResult:
        """Execute a command if safe.

        Args:
            command: Command string to execute

        Returns:
            ActionExecutionResult
        """
        classification = classify_action(ActionType.COMMAND, command)

        if classification != ActionClassification.SAFE:
            logger.info(f"[SafeActionExecutor] Command requires approval: {command[:100]}")
            return ActionExecutionResult(
                action_type=ActionType.COMMAND,
                target=command,
                classification=classification,
                executed=False,
                success=False,
                reason=f"Command requires approval (classification: {classification.value})",
            )

        if self.dry_run:
            logger.info(f"[SafeActionExecutor] DRY RUN: Would execute: {command[:100]}")
            return ActionExecutionResult(
                action_type=ActionType.COMMAND,
                target=command,
                classification=classification,
                executed=False,
                success=True,
                reason="Dry run mode - command not executed",
            )

        try:
            logger.info(f"[SafeActionExecutor] Executing: {command[:100]}")
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=self.command_timeout,
            )

            success = result.returncode == 0

            return ActionExecutionResult(
                action_type=ActionType.COMMAND,
                target=command,
                classification=classification,
                executed=True,
                success=success,
                stdout=result.stdout,
                stderr=result.stderr,
                reason="" if success else f"Exit code: {result.returncode}",
            )

        except subprocess.TimeoutExpired:
            logger.warning(f"[SafeActionExecutor] Command timed out: {command[:100]}")
            return ActionExecutionResult(
                action_type=ActionType.COMMAND,
                target=command,
                classification=classification,
                executed=True,
                success=False,
                reason=f"Command timed out after {self.command_timeout}s",
                error="TimeoutExpired",
            )

        except Exception as e:
            logger.error(f"[SafeActionExecutor] Command failed: {e}")
            return ActionExecutionResult(
                action_type=ActionType.COMMAND,
                target=command,
                classification=classification,
                executed=True,
                success=False,
                reason=str(e),
                error=type(e).__name__,
            )

    def write_artifact(self, path: str, content: str) -> ActionExecutionResult:
        """Write an artifact file if path is safe.

        Args:
            path: Relative path to write to
            content: Content to write

        Returns:
            ActionExecutionResult
        """
        classification = classify_action(ActionType.FILE_WRITE, path)

        if classification != ActionClassification.SAFE:
            logger.info(f"[SafeActionExecutor] File write requires approval: {path}")
            return ActionExecutionResult(
                action_type=ActionType.FILE_WRITE,
                target=path,
                classification=classification,
                executed=False,
                success=False,
                reason=f"File write requires approval (classification: {classification.value})",
            )

        if self.dry_run:
            logger.info(f"[SafeActionExecutor] DRY RUN: Would write: {path}")
            return ActionExecutionResult(
                action_type=ActionType.FILE_WRITE,
                target=path,
                classification=classification,
                executed=False,
                success=True,
                reason="Dry run mode - file not written",
            )

        try:
            full_path = self.workspace_root / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")

            logger.info(f"[SafeActionExecutor] Wrote artifact: {path}")
            return ActionExecutionResult(
                action_type=ActionType.FILE_WRITE,
                target=path,
                classification=classification,
                executed=True,
                success=True,
            )

        except Exception as e:
            logger.error(f"[SafeActionExecutor] Write failed: {e}")
            return ActionExecutionResult(
                action_type=ActionType.FILE_WRITE,
                target=path,
                classification=classification,
                executed=True,
                success=False,
                reason=str(e),
                error=type(e).__name__,
            )

    def read_file(self, path: str) -> ActionExecutionResult:
        """Read a file.

        Args:
            path: Relative path to read

        Returns:
            ActionExecutionResult with content in stdout
        """
        classification = classify_action(ActionType.FILE_READ, path)

        # File reads are always safe
        if self.dry_run:
            return ActionExecutionResult(
                action_type=ActionType.FILE_READ,
                target=path,
                classification=classification,
                executed=False,
                success=True,
                reason="Dry run mode - file not read",
            )

        try:
            full_path = self.workspace_root / path
            content = full_path.read_text(encoding="utf-8")

            return ActionExecutionResult(
                action_type=ActionType.FILE_READ,
                target=path,
                classification=classification,
                executed=True,
                success=True,
                stdout=content,
            )

        except FileNotFoundError:
            return ActionExecutionResult(
                action_type=ActionType.FILE_READ,
                target=path,
                classification=classification,
                executed=True,
                success=False,
                reason=f"File not found: {path}",
                error="FileNotFoundError",
            )

        except Exception as e:
            return ActionExecutionResult(
                action_type=ActionType.FILE_READ,
                target=path,
                classification=classification,
                executed=True,
                success=False,
                reason=str(e),
                error=type(e).__name__,
            )


@dataclass
class ExecutionBatch:
    """Batch of action execution results."""

    results: List[ActionExecutionResult] = field(default_factory=list)
    total_actions: int = 0
    executed_actions: int = 0
    successful_actions: int = 0
    requires_approval_actions: int = 0

    def add_result(self, result: ActionExecutionResult) -> None:
        """Add a result to the batch."""
        self.results.append(result)
        self.total_actions += 1

        if result.executed:
            self.executed_actions += 1
            if result.success:
                self.successful_actions += 1
        elif result.classification == ActionClassification.REQUIRES_APPROVAL:
            self.requires_approval_actions += 1

    @property
    def all_successful(self) -> bool:
        """Check if all executed actions were successful."""
        return self.executed_actions == self.successful_actions

    @property
    def has_pending_approvals(self) -> bool:
        """Check if any actions require approval."""
        return self.requires_approval_actions > 0
