"""
Error Recovery System for Autopack

Provides comprehensive error handling and automatic recovery mechanisms
for all layers of the Autopack system:
- Orchestration layer (autonomous_executor)
- Builder/Auditor pipeline
- API communication
- File I/O operations
- External tool execution

Key Features:
- Automatic retry with exponential backoff
- Error classification (transient vs permanent)
- Self-healing through Builder/Auditor consultation
- Graceful degradation
- Comprehensive error logging
"""

import logging
import time
import traceback
import sys
from typing import Optional, Callable, Any, Dict, List, Set
from enum import Enum
from dataclasses import dataclass

from .debug_journal import log_error, log_fix, log_escalation


logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels"""
    TRANSIENT = "transient"  # Retry automatically
    RECOVERABLE = "recoverable"  # Can be fixed with code changes
    FATAL = "fatal"  # Cannot be recovered


class ErrorCategory(Enum):
    """Error categories for classification"""
    ENCODING = "encoding"  # Unicode, text encoding issues
    NETWORK = "network"  # API calls, timeouts
    FILE_IO = "file_io"  # File read/write errors
    IMPORT = "import"  # Module import errors
    VALIDATION = "validation"  # Schema/data validation
    LOGIC = "logic"  # Business logic errors
    UNKNOWN = "unknown"  # Unclassified


@dataclass
class ErrorContext:
    """Context information for error recovery"""
    error: Exception
    error_type: str
    error_message: str
    traceback_str: str
    category: ErrorCategory
    severity: ErrorSeverity
    retry_count: int = 0
    max_retries: int = 3
    context_data: Dict[str, Any] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging/API"""
        return {
            "error_type": self.error_type,
            "error_message": self.error_message,
            "traceback": self.traceback_str,
            "category": self.category.value,
            "severity": self.severity.value,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "context_data": self.context_data or {}
        }


class ErrorRecoverySystem:
    """
    Centralized error recovery system for Autopack.

    Usage:
        recovery = ErrorRecoverySystem()

        # Wrap risky operations
        result = recovery.execute_with_retry(
            func=risky_function,
            func_args=(arg1, arg2),
            operation_name="API call",
            max_retries=3
        )

        # Classify errors
        error_ctx = recovery.classify_error(exception)

        # Attempt self-healing
        fixed = recovery.attempt_self_healing(error_ctx)

    Self-Troubleshoot Enhancement:
        - Tracks error counts by category within a run
        - Escalates to human when threshold exceeded (default: 3 same errors)
        - Logs escalations to debug journal for visibility
    """

    # Escalation thresholds - if same error type occurs this many times, escalate
    ESCALATION_THRESHOLD = 3
    ESCALATION_THRESHOLD_FATAL = 1  # Fatal errors escalate immediately

    def __init__(self):
        """Initialize error recovery system"""
        self.error_history: List[ErrorContext] = []
        self.encoding_fixed = False  # Track if encoding was already fixed
        self._error_counts_by_category: Dict[str, int] = {}  # category -> count
        self._error_counts_by_signature: Dict[str, int] = {}  # signature -> count
        self._escalated_errors: set = set()  # Track which errors have been escalated
        self._escalation_callback: Optional[Callable[[str, str], None]] = None

    def set_escalation_callback(self, callback: Callable[[str, str], None]):
        """
        Set a callback to be invoked when errors are escalated.

        Args:
            callback: Function(error_category, reason) called on escalation
        """
        self._escalation_callback = callback

    def _check_and_escalate(
        self,
        error_ctx: ErrorContext,
        context_data: Dict = None
    ) -> bool:
        """
        Check if error should be escalated based on threshold.

        Returns True if error was escalated (meaning we should stop retrying).
        """
        error_signature = f"{error_ctx.category.value}:{error_ctx.error_type}"
        category_key = error_ctx.category.value

        # Increment counters
        self._error_counts_by_signature[error_signature] = \
            self._error_counts_by_signature.get(error_signature, 0) + 1
        self._error_counts_by_category[category_key] = \
            self._error_counts_by_category.get(category_key, 0) + 1

        count = self._error_counts_by_signature[error_signature]

        # Determine threshold based on severity
        threshold = (
            self.ESCALATION_THRESHOLD_FATAL
            if error_ctx.severity == ErrorSeverity.FATAL
            else self.ESCALATION_THRESHOLD
        )

        # Check if we should escalate
        if count >= threshold and error_signature not in self._escalated_errors:
            self._escalated_errors.add(error_signature)

            reason = (
                f"Error '{error_ctx.error_type}' in category '{category_key}' "
                f"occurred {count} times - manual intervention required"
            )

            logger.critical(f"[Escalation] {reason}")

            # Log to debug journal
            try:
                log_escalation(
                    error_category=category_key,
                    error_count=count,
                    threshold=threshold,
                    reason=reason,
                    run_id=context_data.get("run_id") if context_data else None,
                    phase_id=context_data.get("phase_id") if context_data else None
                )
            except Exception as e:
                logger.warning(f"Failed to log escalation: {e}")

            # Call escalation callback if set
            if self._escalation_callback:
                try:
                    self._escalation_callback(category_key, reason)
                except Exception as e:
                    logger.warning(f"Escalation callback failed: {e}")

            return True

        return False

    def get_escalation_status(self) -> Dict[str, Any]:
        """Get current escalation status for monitoring."""
        return {
            "error_counts_by_category": dict(self._error_counts_by_category),
            "error_counts_by_signature": dict(self._error_counts_by_signature),
            "escalated_errors": list(self._escalated_errors),
            "threshold": self.ESCALATION_THRESHOLD,
            "fatal_threshold": self.ESCALATION_THRESHOLD_FATAL
        }

    def reset_counts(self):
        """Reset error counts (typically between runs)."""
        self._error_counts_by_category.clear()
        self._error_counts_by_signature.clear()
        self._escalated_errors.clear()
        logger.info("[Recovery] Error counts reset")

    def classify_error(self, error: Exception, context_data: Dict = None) -> ErrorContext:
        """
        Classify an error to determine recovery strategy.

        Args:
            error: The exception to classify
            context_data: Additional context about where/how error occurred

        Returns:
            ErrorContext with classification and recovery info
        """
        error_type = type(error).__name__
        error_message = str(error)
        traceback_str = traceback.format_exc()

        # Classify by error type and message patterns
        category, severity = self._determine_category_severity(error, error_message)

        ctx = ErrorContext(
            error=error,
            error_type=error_type,
            error_message=error_message,
            traceback_str=traceback_str,
            category=category,
            severity=severity,
            context_data=context_data or {}
        )

        self.error_history.append(ctx)

        # Log to debug journal if severity is not TRANSIENT
        if severity != ErrorSeverity.TRANSIENT:
            try:
                log_error(
                    error_signature=f"{category.value}: {error_type}",
                    symptom=error_message,
                    run_id=context_data.get("run_id") if context_data else None,
                    phase_id=context_data.get("phase_id") if context_data else None,
                    suspected_cause=f"Classified as {severity.value} {category.value} error",
                    priority="HIGH" if severity == ErrorSeverity.FATAL else "MEDIUM"
                )
            except Exception as journal_error:
                # Don't fail error recovery if journal logging fails
                logger.warning(f"Failed to log error to debug journal: {journal_error}")

        # [Self-Troubleshoot] Check escalation threshold
        self._check_and_escalate(ctx, context_data)

        return ctx

    def _determine_category_severity(
        self,
        error: Exception,
        error_message: str
    ) -> tuple[ErrorCategory, ErrorSeverity]:
        """Determine error category and severity"""

        # Unicode/Encoding errors
        if isinstance(error, UnicodeEncodeError) or isinstance(error, UnicodeDecodeError):
            return ErrorCategory.ENCODING, ErrorSeverity.RECOVERABLE
        if "charmap" in error_message.lower() or "utf-8" in error_message.lower():
            return ErrorCategory.ENCODING, ErrorSeverity.RECOVERABLE

        # Network errors
        if isinstance(error, (ConnectionError, TimeoutError)):
            return ErrorCategory.NETWORK, ErrorSeverity.TRANSIENT
        if "connection" in error_message.lower() or "timeout" in error_message.lower():
            return ErrorCategory.NETWORK, ErrorSeverity.TRANSIENT
        if "429" in error_message or "rate limit" in error_message.lower():
            return ErrorCategory.NETWORK, ErrorSeverity.TRANSIENT

        # File I/O errors
        if isinstance(error, (FileNotFoundError, PermissionError, IOError)):
            return ErrorCategory.FILE_IO, ErrorSeverity.RECOVERABLE

        # Import errors
        if isinstance(error, (ImportError, ModuleNotFoundError)):
            return ErrorCategory.IMPORT, ErrorSeverity.FATAL

        # Validation errors
        if "validation" in error_message.lower() or "schema" in error_message.lower():
            return ErrorCategory.VALIDATION, ErrorSeverity.RECOVERABLE

        # Default
        return ErrorCategory.UNKNOWN, ErrorSeverity.RECOVERABLE

    def attempt_self_healing(self, error_ctx: ErrorContext) -> bool:
        """
        Attempt to automatically fix the error.

        Args:
            error_ctx: Error context with classification

        Returns:
            True if error was fixed, False otherwise
        """
        logger.info(f"[Recovery] Attempting self-healing for {error_ctx.category.value} error")

        success = False
        if error_ctx.category == ErrorCategory.ENCODING:
            success = self._fix_encoding_error(error_ctx)
        elif error_ctx.category == ErrorCategory.NETWORK:
            success = self._fix_network_error(error_ctx)
        elif error_ctx.category == ErrorCategory.FILE_IO:
            success = self._fix_file_io_error(error_ctx)
        else:
            logger.warning(f"[Recovery] No automatic fix available for {error_ctx.category.value}")
            return False

        # Log successful self-healing to debug journal
        if success:
            try:
                log_fix(
                    error_signature=f"{error_ctx.category.value}: {error_ctx.error_type}",
                    fix_description=f"Automatic self-healing applied for {error_ctx.category.value} error",
                    files_changed=[],  # Self-healing typically doesn't change files
                    test_run_id=error_ctx.context_data.get("run_id") if error_ctx.context_data else None,
                    result="success"
                )
            except Exception as journal_error:
                # Don't fail recovery if journal logging fails
                logger.warning(f"Failed to log fix to debug journal: {journal_error}")

        return success

    def _fix_encoding_error(self, error_ctx: ErrorContext) -> bool:
        """Fix Unicode encoding errors"""
        if self.encoding_fixed:
            logger.info("[Recovery] Encoding already fixed in this session")
            return True

        logger.info("[Recovery] Fixing Unicode encoding error...")

        # Set environment variable for UTF-8 encoding
        import os
        os.environ['PYTHONUTF8'] = '1'

        # Try to reconfigure stdout/stderr for UTF-8
        try:
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            if hasattr(sys.stderr, 'reconfigure'):
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')

            self.encoding_fixed = True
            logger.info("[Recovery] SUCCESS: Encoding fixed (UTF-8 enabled)")
            return True
        except Exception as e:
            logger.error(f"[Recovery] Failed to fix encoding: {e}")
            return False

    def _fix_network_error(self, error_ctx: ErrorContext) -> bool:
        """Handle network errors with exponential backoff"""
        if error_ctx.retry_count >= error_ctx.max_retries:
            logger.error("[Recovery] Max retries reached for network error")
            return False

        # Exponential backoff: 1s, 2s, 4s, 8s...
        wait_time = 2 ** error_ctx.retry_count
        logger.info(f"[Recovery] Network error - waiting {wait_time}s before retry...")
        time.sleep(wait_time)
        return True  # Signal that retry should be attempted

    def _fix_file_io_error(self, error_ctx: ErrorContext) -> bool:
        """Handle file I/O errors"""
        error_msg = error_ctx.error_message.lower()

        # Create missing directories
        if "no such file or directory" in error_msg:
            logger.info("[Recovery] Attempting to create missing directory")
            # This would need file path from context_data
            return False  # Cannot fix without knowing path

        logger.warning(f"[Recovery] No automatic fix for file I/O error: {error_msg}")
        return False

    def execute_with_retry(
        self,
        func: Callable,
        func_args: tuple = (),
        func_kwargs: dict = None,
        operation_name: str = "operation",
        max_retries: int = 3,
        retry_on_categories: List[ErrorCategory] = None
    ) -> Any:
        """
        Execute a function with automatic retry and error recovery.

        Args:
            func: Function to execute
            func_args: Positional arguments for function
            func_kwargs: Keyword arguments for function
            operation_name: Human-readable operation name for logging
            max_retries: Maximum number of retry attempts
            retry_on_categories: List of error categories that should trigger retry
                                (default: [TRANSIENT, RECOVERABLE])

        Returns:
            Result of successful function execution

        Raises:
            Last exception if all retries fail
        """
        func_kwargs = func_kwargs or {}
        # Default: retry on all categories if error severity is TRANSIENT or RECOVERABLE
        retry_on_categories = retry_on_categories or [
            ErrorCategory.ENCODING,
            ErrorCategory.NETWORK,
            ErrorCategory.FILE_IO,
            ErrorCategory.VALIDATION,
            ErrorCategory.LOGIC,
            ErrorCategory.UNKNOWN
        ]

        last_error_ctx = None

        for attempt in range(max_retries + 1):
            try:
                # Execute the function
                result = func(*func_args, **func_kwargs)

                # Success
                if attempt > 0:
                    logger.info(f"[Recovery] {operation_name} succeeded on retry {attempt}")
                return result

            except Exception as e:
                # Classify the error
                error_ctx = self.classify_error(
                    e,
                    context_data={
                        "operation": operation_name,
                        "attempt": attempt + 1,
                        "max_attempts": max_retries + 1
                    }
                )
                error_ctx.retry_count = attempt
                error_ctx.max_retries = max_retries
                last_error_ctx = error_ctx

                logger.error(
                    f"[Recovery] {operation_name} failed (attempt {attempt + 1}/{max_retries + 1}): "
                    f"{error_ctx.error_type}: {error_ctx.error_message}"
                )

                # Don't retry on last attempt
                if attempt >= max_retries:
                    logger.error(f"[Recovery] Max retries reached for {operation_name}")
                    break

                # Check if error category is retryable
                if error_ctx.category not in retry_on_categories and error_ctx.severity != ErrorSeverity.TRANSIENT:
                    logger.error(
                        f"[Recovery] Error category {error_ctx.category.value} "
                        f"not retryable for {operation_name}"
                    )
                    break

                # Attempt self-healing
                fixed = self.attempt_self_healing(error_ctx)
                if fixed:
                    logger.info(f"[Recovery] Error fixed, retrying {operation_name}...")
                    continue

                # If not fixed and error is fatal, don't retry
                if error_ctx.severity == ErrorSeverity.FATAL:
                    logger.error(f"[Recovery] Fatal error for {operation_name}, cannot retry")
                    break

                # Wait before retry (if error wasn't self-healed)
                if attempt < max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.info(f"[Recovery] Waiting {wait_time}s before retry...")
                    time.sleep(wait_time)

        # All retries failed
        if last_error_ctx:
            logger.error(
                f"[Recovery] {operation_name} failed permanently after {max_retries + 1} attempts\n"
                f"Error type: {last_error_ctx.error_type}\n"
                f"Error message: {last_error_ctx.error_message}\n"
                f"Category: {last_error_ctx.category.value}\n"
                f"Severity: {last_error_ctx.severity.value}"
            )
            raise last_error_ctx.error
        else:
            raise RuntimeError(f"{operation_name} failed with unknown error")

    def get_error_summary(self) -> Dict:
        """Get summary of all errors encountered"""
        return {
            "total_errors": len(self.error_history),
            "by_category": self._count_by_category(),
            "by_severity": self._count_by_severity(),
            "recent_errors": [
                {
                    "type": ctx.error_type,
                    "message": ctx.error_message,
                    "category": ctx.category.value,
                    "severity": ctx.severity.value
                }
                for ctx in self.error_history[-5:]  # Last 5 errors
            ]
        }

    def _count_by_category(self) -> Dict[str, int]:
        """Count errors by category"""
        counts = {}
        for ctx in self.error_history:
            cat = ctx.category.value
            counts[cat] = counts.get(cat, 0) + 1
        return counts

    def _count_by_severity(self) -> Dict[str, int]:
        """Count errors by severity"""
        counts = {}
        for ctx in self.error_history:
            sev = ctx.severity.value
            counts[sev] = counts.get(sev, 0) + 1
        return counts


# Global error recovery instance
_global_recovery = None

def get_error_recovery() -> ErrorRecoverySystem:
    """Get global error recovery instance (singleton)"""
    global _global_recovery
    if _global_recovery is None:
        _global_recovery = ErrorRecoverySystem()
    return _global_recovery


def safe_execute(
    func: Callable,
    operation_name: str = "operation",
    default_return: Any = None,
    log_errors: bool = True,
    **retry_kwargs
) -> Any:
    """
    Convenience wrapper for safe execution with error recovery.

    Args:
        func: Function to execute
        operation_name: Name for logging
        default_return: Value to return if all retries fail
        log_errors: Whether to log errors
        **retry_kwargs: Additional kwargs for execute_with_retry

    Returns:
        Function result or default_return if failed
    """
    recovery = get_error_recovery()
    try:
        return recovery.execute_with_retry(
            func=func,
            operation_name=operation_name,
            **retry_kwargs
        )
    except Exception as e:
        if log_errors:
            logger.error(f"[SafeExecute] {operation_name} failed permanently: {e}")
        return default_return
