"""
Comprehensive Error Reporting System for Autopack

Provides detailed error context capture and reporting to aid debugging.
Captures:
- Full stack traces
- Phase/run context
- Request/response data
- Database state snapshots
- Environment info

Error reports are written to:
- .autonomous_runs/{run_id}/errors/{timestamp}_{error_type}.json
- Logs with [ERROR_REPORT] prefix for easy grepping
"""

import traceback
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class ErrorContext:
    """Container for error context information."""

    def __init__(
        self,
        error: Exception,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        component: Optional[str] = None,
        operation: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize error context.

        Args:
            error: The exception that occurred
            run_id: Current run ID (if applicable)
            phase_id: Current phase ID (if applicable)
            component: Component where error occurred (e.g., 'api', 'executor', 'builder')
            operation: Operation being performed (e.g., 'apply_patch', 'execute_phase')
            context_data: Additional context data (request params, db state, etc.)
        """
        self.error = error
        self.error_type = type(error).__name__
        self.error_message = str(error)
        self.run_id = run_id
        self.phase_id = phase_id
        self.component = component
        self.operation = operation
        self.context_data = context_data or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()

        # Capture full traceback
        self.traceback = traceback.format_exc()
        self.stack_frames = self._extract_stack_frames()

    def _extract_stack_frames(self) -> List[Dict[str, Any]]:
        """Extract structured stack frame information."""
        frames = []
        tb = sys.exc_info()[2]

        while tb is not None:
            frame = tb.tb_frame
            frames.append({
                "filename": frame.f_code.co_filename,
                "function": frame.f_code.co_name,
                "line_number": tb.tb_lineno,
                "local_vars": {k: repr(v)[:200] for k, v in frame.f_locals.items() if not k.startswith('_')}
            })
            tb = tb.tb_next

        return frames

    def to_dict(self) -> Dict[str, Any]:
        """Convert error context to dictionary."""
        return {
            "timestamp": self.timestamp,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "run_id": self.run_id,
            "phase_id": self.phase_id,
            "component": self.component,
            "operation": self.operation,
            "traceback": self.traceback,
            "stack_frames": self.stack_frames,
            "context_data": self.context_data,
            "python_version": sys.version,
            "platform": sys.platform,
        }

    def format_summary(self) -> str:
        """Format a human-readable summary."""
        lines = [
            "=" * 80,
            f"ERROR REPORT - {self.timestamp}",
            "=" * 80,
            f"Error Type: {self.error_type}",
            f"Error Message: {self.error_message}",
        ]

        if self.run_id:
            lines.append(f"Run ID: {self.run_id}")
        if self.phase_id:
            lines.append(f"Phase ID: {self.phase_id}")
        if self.component:
            lines.append(f"Component: {self.component}")
        if self.operation:
            lines.append(f"Operation: {self.operation}")

        lines.append("")
        lines.append("Stack Trace:")
        lines.append("-" * 80)
        lines.append(self.traceback)

        if self.context_data:
            lines.append("")
            lines.append("Context Data:")
            lines.append("-" * 80)
            for key, value in self.context_data.items():
                value_str = str(value)[:500]  # Limit length
                lines.append(f"{key}: {value_str}")

        lines.append("=" * 80)
        return "\n".join(lines)


class ErrorReporter:
    """Central error reporting service."""

    def __init__(self, workspace: Path = None):
        """
        Initialize error reporter.

        Args:
            workspace: Workspace root path (defaults to current directory)
        """
        self.workspace = workspace or Path.cwd()
        self.base_error_dir = self.workspace / ".autonomous_runs"

    def report_error(
        self,
        error: Exception,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        component: Optional[str] = None,
        operation: Optional[str] = None,
        context_data: Optional[Dict[str, Any]] = None,
        write_to_file: bool = True,
    ) -> ErrorContext:
        """
        Report an error with full context.

        Args:
            error: The exception that occurred
            run_id: Current run ID
            phase_id: Current phase ID
            component: Component where error occurred
            operation: Operation being performed
            context_data: Additional context
            write_to_file: Whether to write error report to file

        Returns:
            ErrorContext object with captured information
        """
        # Create error context
        ctx = ErrorContext(
            error=error,
            run_id=run_id,
            phase_id=phase_id,
            component=component,
            operation=operation,
            context_data=context_data,
        )

        # Log to console
        logger.error(f"[ERROR_REPORT] {ctx.error_type} in {component or 'unknown'}: {ctx.error_message}")
        logger.error(f"[ERROR_REPORT] Full details: {self._get_report_path(ctx) if write_to_file else 'not written to file'}")

        # Write detailed report to file
        if write_to_file:
            try:
                self._write_report(ctx)
            except Exception as e:
                logger.error(f"[ERROR_REPORT] Failed to write error report: {e}")

        return ctx

    def _get_report_path(self, ctx: ErrorContext) -> Path:
        """Get path for error report file."""
        if ctx.run_id:
            error_dir = self.base_error_dir / ctx.run_id / "errors"
        else:
            error_dir = self.base_error_dir / "errors"

        error_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        component_prefix = f"{ctx.component}_" if ctx.component else ""
        filename = f"{timestamp}_{component_prefix}{ctx.error_type}.json"

        return error_dir / filename

    def _write_report(self, ctx: ErrorContext):
        """Write error report to file."""
        report_path = self._get_report_path(ctx)

        # Write JSON report
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(ctx.to_dict(), f, indent=2, default=str)

        # Also write human-readable summary
        summary_path = report_path.with_suffix('.txt')
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(ctx.format_summary())

        logger.info(f"[ERROR_REPORT] Written to {report_path}")

    def get_run_errors(self, run_id: str) -> List[Dict[str, Any]]:
        """
        Get all error reports for a specific run.

        Args:
            run_id: Run ID to get errors for

        Returns:
            List of error report dictionaries
        """
        error_dir = self.base_error_dir / run_id / "errors"

        if not error_dir.exists():
            return []

        errors = []
        for report_file in sorted(error_dir.glob("*.json")):
            try:
                with open(report_file, 'r', encoding='utf-8') as f:
                    errors.append(json.load(f))
            except Exception as e:
                logger.warning(f"[ERROR_REPORT] Failed to load error report {report_file}: {e}")

        return errors

    def generate_run_error_summary(self, run_id: str) -> str:
        """
        Generate a summary of all errors for a run.

        Args:
            run_id: Run ID to summarize

        Returns:
            Formatted error summary
        """
        errors = self.get_run_errors(run_id)

        if not errors:
            return f"No errors reported for run {run_id}"

        lines = [
            f"ERROR SUMMARY FOR RUN: {run_id}",
            f"Total Errors: {len(errors)}",
            "=" * 80,
            ""
        ]

        for i, error in enumerate(errors, 1):
            lines.append(f"{i}. [{error.get('timestamp')}] {error.get('error_type')}")
            lines.append(f"   Component: {error.get('component', 'unknown')}")
            lines.append(f"   Operation: {error.get('operation', 'unknown')}")
            lines.append(f"   Message: {error.get('error_message', 'N/A')[:200]}")
            lines.append("")

        return "\n".join(lines)


# Global error reporter instance
_global_reporter: Optional[ErrorReporter] = None


def get_error_reporter(workspace: Path = None) -> ErrorReporter:
    """Get or create global error reporter instance."""
    global _global_reporter

    if _global_reporter is None:
        _global_reporter = ErrorReporter(workspace)

    return _global_reporter


def report_error(
    error: Exception,
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    component: Optional[str] = None,
    operation: Optional[str] = None,
    context_data: Optional[Dict[str, Any]] = None,
) -> ErrorContext:
    """
    Convenience function to report an error using the global reporter.

    Args:
        error: The exception that occurred
        run_id: Current run ID
        phase_id: Current phase ID
        component: Component where error occurred
        operation: Operation being performed
        context_data: Additional context

    Returns:
        ErrorContext object
    """
    reporter = get_error_reporter()
    return reporter.report_error(
        error=error,
        run_id=run_id,
        phase_id=phase_id,
        component=component,
        operation=operation,
        context_data=context_data,
    )
