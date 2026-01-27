"""FastAPI app factory with lifespan, middleware, and exception handling.

PR-API-2: Extract from main.py to support router split.

This module provides:
- create_app(): Factory that creates the FastAPI app with proper wiring
- lifespan: Application lifespan context manager
- approval_timeout_cleanup: Background task for approval timeouts
- global_exception_handler: Production-safe error handling

Contract guarantees (tested in tests/api/test_app_wiring_contract.py):
- App includes lifespan with DB init (skipped in TESTING mode)
- CORS only enabled when CORS_ALLOWED_ORIGINS is set
- Rate limiter is attached to app.state
- Exception handler returns error_id for correlation
"""

import asyncio
import logging
import os
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import (CONTENT_TYPE_LATEST, Counter, Histogram,
                               generate_latest)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import get_api_key, is_production, validate_startup_config
from ..database import get_db, init_db
from ..logging_config import correlation_id_var
from ..version import __version__
from .deps import limiter

logger = logging.getLogger(__name__)

# IMP-REL-004: Max iteration limits for polling loops to prevent resource exhaustion
MAX_CLEANUP_ITERATIONS = 100000  # ~69 days at 1 min intervals before warning

# IMP-OPS-010: Prometheus metrics for API observability
# These metrics enable monitoring of API performance and request patterns
REQUEST_COUNT = Counter(
    "autopack_http_requests_total",
    "Total HTTP requests processed by the API",
    ["method", "endpoint", "status"],
)

REQUEST_LATENCY = Histogram(
    "autopack_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)


async def alert_critical_failure(
    task_name: str,
    error: str,
    severity: str = "critical",
    restart_count: int | None = None,
) -> None:
    """Send alert for critical background task failure.

    IMP-OPS-005: Alerting for background task failures.
    This function is called when background tasks fail critically
    (e.g., exceed max restarts or encounter unrecoverable errors).

    Args:
        task_name: Name of the failed background task
        error: Error message or description
        severity: Alert severity level (critical, high, warning)
        restart_count: Number of restart attempts if applicable

    Alert channels:
        1. Critical log message (always)
        2. Telegram notification (if configured)
    """
    from ..notifications.telegram_notifier import TelegramNotifier

    # Format alert message
    restart_info = f" (after {restart_count} restart attempts)" if restart_count else ""
    alert_message = (
        f"🚨 CRITICAL: Background task '{task_name}' failed{restart_info}\nError: {error}"
    )

    # Always log at critical level
    logger.critical(
        f"[ALERT] {alert_message}",
        extra={
            "task_name": task_name,
            "error": error,
            "severity": severity,
            "restart_count": restart_count,
        },
    )

    # Send Telegram notification if configured
    notifier = TelegramNotifier()
    if notifier.is_configured():
        try:
            # Use send_completion_notice with a custom status for alerts
            notifier.send_completion_notice(
                phase_id=f"task:{task_name}",
                status="error",
                message=f"🚨 *Critical Task Failure*\n\n"
                f"*Task*: `{task_name}`\n"
                f"*Severity*: {severity.upper()}\n"
                f"*Restarts*: {restart_count or 'N/A'}\n"
                f"*Error*: {error[:200]}{'...' if len(error) > 200 else ''}\n\n"
                f"_Immediate attention required_",
            )
            logger.info(f"[ALERT] Telegram notification sent for {task_name} failure")
        except Exception as telegram_error:
            logger.warning(f"[ALERT] Failed to send Telegram notification: {telegram_error}")


class GracefulShutdownManager:
    """Manager for coordinating graceful shutdown of database operations.

    Implements IMP-OPS-003: Graceful shutdown for DB sessions.
    Ensures pending transactions complete before shutdown to prevent data loss.

    Features:
    - Tracks active database transactions
    - Signals shutdown to background tasks
    - Waits for pending transactions with configurable timeout
    - Prevents new transactions from starting during shutdown
    """

    def __init__(self, shutdown_timeout: float = 30.0):
        """Initialize the shutdown manager.

        Args:
            shutdown_timeout: Maximum seconds to wait for pending transactions
        """
        self._shutdown_timeout = shutdown_timeout
        self._shutdown_event = asyncio.Event()
        self._active_transactions = 0
        self._transaction_lock = threading.Lock()
        self._all_transactions_done = asyncio.Event()
        self._all_transactions_done.set()  # Initially no transactions

    def is_shutting_down(self) -> bool:
        """Check if shutdown has been initiated.

        Returns:
            True if shutdown is in progress
        """
        return self._shutdown_event.is_set()

    def begin_transaction(self) -> bool:
        """Register that a new transaction is starting.

        Should be called before starting a database transaction.
        Returns False if shutdown is in progress (transaction should not start).

        Returns:
            True if transaction can proceed, False if shutdown is in progress
        """
        with self._transaction_lock:
            if self._shutdown_event.is_set():
                logger.warning("[GRACEFUL-SHUTDOWN] Rejecting new transaction during shutdown")
                return False

            self._active_transactions += 1
            self._all_transactions_done.clear()
            logger.debug(
                f"[GRACEFUL-SHUTDOWN] Transaction started, "
                f"active count: {self._active_transactions}"
            )
            return True

    def end_transaction(self) -> None:
        """Register that a transaction has completed.

        Should be called after a database transaction commits or rolls back.
        """
        with self._transaction_lock:
            self._active_transactions = max(0, self._active_transactions - 1)
            logger.debug(
                f"[GRACEFUL-SHUTDOWN] Transaction ended, active count: {self._active_transactions}"
            )
            if self._active_transactions == 0:
                self._all_transactions_done.set()

    def get_active_transaction_count(self) -> int:
        """Get the current number of active transactions.

        Returns:
            Number of active transactions
        """
        with self._transaction_lock:
            return self._active_transactions

    async def initiate_shutdown(self) -> bool:
        """Initiate graceful shutdown and wait for pending transactions.

        Sets the shutdown flag and waits for all active transactions to complete,
        up to the configured timeout.

        Returns:
            True if all transactions completed, False if timeout occurred
        """
        logger.info(
            f"[GRACEFUL-SHUTDOWN] Initiating shutdown, waiting up to "
            f"{self._shutdown_timeout}s for pending transactions"
        )

        self._shutdown_event.set()

        active_count = self.get_active_transaction_count()
        if active_count > 0:
            logger.info(f"[GRACEFUL-SHUTDOWN] Waiting for {active_count} active transactions")

        try:
            await asyncio.wait_for(
                self._all_transactions_done.wait(),
                timeout=self._shutdown_timeout,
            )
            logger.info("[GRACEFUL-SHUTDOWN] All transactions completed successfully")
            return True
        except asyncio.TimeoutError:
            remaining = self.get_active_transaction_count()
            logger.warning(
                f"[GRACEFUL-SHUTDOWN] Timeout waiting for transactions. "
                f"{remaining} transactions may be interrupted."
            )
            return False


# Global shutdown manager instance
_shutdown_manager: GracefulShutdownManager | None = None

# IMP-REL-003: Lock for protecting global state during concurrent startup/shutdown
# Using a lazily-created lock to ensure it's bound to the correct event loop
_state_lock: asyncio.Lock | None = None


def _get_state_lock() -> asyncio.Lock:
    """Get or create the state lock for the current event loop.

    IMP-REL-003: Lazy lock creation ensures the lock is bound to the
    correct event loop when used, avoiding issues with module-level
    lock creation before the event loop is running.
    """
    global _state_lock
    if _state_lock is None:
        _state_lock = asyncio.Lock()
    return _state_lock


def get_shutdown_manager() -> GracefulShutdownManager:
    """Get the global shutdown manager instance.

    Returns:
        The GracefulShutdownManager instance

    Raises:
        RuntimeError: If called before lifespan initialization
    """
    global _shutdown_manager
    if _shutdown_manager is None:
        raise RuntimeError(
            "Shutdown manager not initialized. This should only be called after app startup."
        )
    return _shutdown_manager


class BackgroundTaskMonitor:
    """Health monitor for background tasks.

    Implements IMP-OPS-007: Background task health monitoring.
    Provides visibility into whether background tasks are running, hung, or failing.

    Features:
    - Tracks last successful run time for each task
    - Tracks consecutive failure counts
    - Configurable max age threshold for stale detection
    - Health status check for integration with /health endpoint
    """

    def __init__(self, max_age_seconds: float = 300.0, max_failures: int = 3):
        """Initialize task monitor.

        Args:
            max_age_seconds: Maximum seconds since last run before task is unhealthy
            max_failures: Maximum consecutive failures before task is unhealthy
        """
        self._last_run: dict[str, datetime] = {}
        self._failure_counts: dict[str, int] = {}
        self._max_age_seconds = max_age_seconds
        self._max_failures = max_failures
        self._lock = threading.Lock()

    def record_run(self, task_name: str) -> None:
        """Record a successful task run.

        Args:
            task_name: Name of the task that completed successfully
        """
        with self._lock:
            self._last_run[task_name] = datetime.now(timezone.utc)
            self._failure_counts[task_name] = 0
            logger.debug(f"[TASK-MONITOR] Task {task_name} run recorded")

    def record_failure(self, task_name: str) -> None:
        """Record a task failure.

        Args:
            task_name: Name of the task that failed
        """
        with self._lock:
            self._failure_counts[task_name] = self._failure_counts.get(task_name, 0) + 1
            logger.warning(
                f"[TASK-MONITOR] Task {task_name} failure recorded "
                f"(count: {self._failure_counts[task_name]})"
            )

    def _is_healthy_unlocked(self, task_name: str) -> bool:
        """Check if a specific task is healthy (internal, no lock).

        Must be called while holding self._lock.

        Args:
            task_name: Name of the task to check

        Returns:
            True if task is healthy, False otherwise
        """
        # Check failure count
        failures = self._failure_counts.get(task_name, 0)
        if failures >= self._max_failures:
            return False

        # Check last run time (if never run, consider healthy - not yet expected)
        last = self._last_run.get(task_name)
        if last is None:
            return True

        age = (datetime.now(timezone.utc) - last).total_seconds()
        return age < self._max_age_seconds

    def is_healthy(self, task_name: str) -> bool:
        """Check if a specific task is healthy.

        A task is healthy if:
        - It has run within max_age_seconds, OR has never been expected to run yet
        - It has fewer than max_failures consecutive failures

        Args:
            task_name: Name of the task to check

        Returns:
            True if task is healthy, False otherwise
        """
        with self._lock:
            return self._is_healthy_unlocked(task_name)

    def get_task_status(self, task_name: str) -> dict:
        """Get detailed status for a specific task.

        Args:
            task_name: Name of the task

        Returns:
            Dict with health status, last run time, and failure count
        """
        with self._lock:
            last = self._last_run.get(task_name)
            failures = self._failure_counts.get(task_name, 0)

            if last is None:
                age_seconds = None
            else:
                age_seconds = (datetime.now(timezone.utc) - last).total_seconds()

            return {
                "healthy": self._is_healthy_unlocked(task_name),
                "last_run": last.isoformat() if last else None,
                "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
                "failure_count": failures,
                "max_age_seconds": self._max_age_seconds,
                "max_failures": self._max_failures,
            }

    def _get_task_status_unlocked(self, task_name: str) -> dict:
        """Get detailed status for a specific task (internal, no lock).

        Must be called while holding self._lock.

        Args:
            task_name: Name of the task

        Returns:
            Dict with health status, last run time, and failure count
        """
        last = self._last_run.get(task_name)
        failures = self._failure_counts.get(task_name, 0)

        if last is None:
            age_seconds = None
        else:
            age_seconds = (datetime.now(timezone.utc) - last).total_seconds()

        return {
            "healthy": self._is_healthy_unlocked(task_name),
            "last_run": last.isoformat() if last else None,
            "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "failure_count": failures,
            "max_age_seconds": self._max_age_seconds,
            "max_failures": self._max_failures,
        }

    def get_all_status(self) -> dict[str, dict]:
        """Get status for all monitored tasks.

        Returns:
            Dict mapping task names to their status dicts
        """
        with self._lock:
            all_tasks = set(self._last_run.keys()) | set(self._failure_counts.keys())
            return {name: self._get_task_status_unlocked(name) for name in all_tasks}

    def is_all_healthy(self) -> bool:
        """Check if all monitored tasks are healthy.

        Returns:
            True if all tasks are healthy, False otherwise
        """
        with self._lock:
            all_tasks = set(self._last_run.keys()) | set(self._failure_counts.keys())
            return all(self._is_healthy_unlocked(name) for name in all_tasks)


# Global task monitor instance
_task_monitor: BackgroundTaskMonitor | None = None


def get_task_monitor() -> BackgroundTaskMonitor:
    """Get the global task monitor instance.

    Returns:
        The BackgroundTaskMonitor instance

    Raises:
        RuntimeError: If called before lifespan initialization
    """
    global _task_monitor
    if _task_monitor is None:
        raise RuntimeError(
            "Task monitor not initialized. This should only be called after app startup."
        )
    return _task_monitor


class BackgroundTaskSupervisor:
    """Supervisor for background tasks with automatic restart on failure.

    Implements IMP-OPS-001: Background task supervision with restart on failure.
    Prevents background tasks from dying permanently after a single error.

    Features:
    - Automatic task restart on failure with exponential backoff
    - Maximum restart limit to prevent infinite restart loops
    - Detailed logging of restart attempts and failures
    - Graceful shutdown on task cancellation
    """

    def __init__(self, max_restarts: int = 5):
        """Initialize task supervisor.

        Args:
            max_restarts: Maximum number of restart attempts before giving up
        """
        self._tasks: dict[str, asyncio.Task] = {}
        self._restart_counts: dict[str, int] = {}
        self._max_restarts = max_restarts

    async def supervise(self, name: str, coro_factory: Callable) -> None:
        """Supervise a background task, restarting on failure.

        Args:
            name: Unique identifier for the task (used in logs)
            coro_factory: Callable that returns an awaitable coroutine to execute
        """
        while self._restart_counts.get(name, 0) < self._max_restarts:
            try:
                logger.info(f"[TASK-SUPERVISOR] Starting task: {name}")
                await coro_factory()
                logger.info(f"[TASK-SUPERVISOR] Task completed normally: {name}")
                break  # Task completed normally, exit supervision loop

            except asyncio.CancelledError:
                logger.info(f"[TASK-SUPERVISOR] Task cancelled: {name}")
                raise  # Propagate cancellation for graceful shutdown

            except Exception:
                self._restart_counts[name] = self._restart_counts.get(name, 0) + 1
                attempt = self._restart_counts[name]

                logger.error(
                    f"[TASK-SUPERVISOR] Task failed (attempt {attempt}/{self._max_restarts}): {name}",
                    exc_info=True,
                )

                # Exponential backoff: 2s, 4s, 8s, 16s, 32s (capped at 60s)
                backoff_seconds = min(2**attempt, 60)
                logger.info(f"[TASK-SUPERVISOR] Restarting task {name} in {backoff_seconds}s...")
                await asyncio.sleep(backoff_seconds)

        # Check if we exceeded max restarts
        if self._restart_counts.get(name, 0) >= self._max_restarts:
            logger.critical(
                f"[TASK-SUPERVISOR] Task {name} exceeded max restarts "
                f"({self._max_restarts}). Giving up."
            )
            # IMP-OPS-005: Alert on max restarts exceeded
            await alert_critical_failure(
                task_name=name,
                error=f"Task exceeded maximum restart attempts ({self._max_restarts})",
                severity="critical",
                restart_count=self._max_restarts,
            )

    def get_status(self) -> dict[str, dict]:
        """Get status of all supervised tasks.

        Returns:
            Dictionary mapping task names to their restart counts
        """
        return dict(self._restart_counts)

    def reset_restart_count(self, name: str) -> None:
        """Reset restart count for a specific task.

        Args:
            name: Task name to reset
        """
        if name in self._restart_counts:
            self._restart_counts[name] = 0
            logger.info(f"[TASK-SUPERVISOR] Reset restart count for task: {name}")


class StartupError(Exception):
    """Exception raised when a startup phase fails.

    Implements IMP-OPS-012: Provides clear error context for debugging
    initialization failures.
    """

    def __init__(self, phase: str, message: str, cause: Exception | None = None):
        self.phase = phase
        self.message = message
        self.cause = cause
        super().__init__(f"Startup phase '{phase}' failed: {message}")


@dataclass
class StartupPhaseResult:
    """Result of a startup phase execution."""

    name: str
    success: bool
    duration_seconds: float
    error: str | None = None


@dataclass
class StartupPhaseLogger:
    """Logger for tracking startup phase execution with timing.

    Implements IMP-OPS-012: Add startup initialization logging.
    Provides structured logging for each startup phase to make
    initialization failures easier to debug.

    Features:
    - Times each startup phase
    - Logs success/failure with duration
    - Tracks all phase results for summary
    - Raises StartupError on phase failure with clear context
    """

    phases: list[StartupPhaseResult] = field(default_factory=list)
    _start_time: float = field(default=0.0, init=False)

    def begin_startup(self) -> None:
        """Mark the beginning of the startup sequence."""
        self._start_time = time.time()
        logger.info("[STARTUP] Beginning application initialization sequence")

    def run_phase(self, phase_name: str, phase_func: Callable[[], None]) -> None:
        """Execute a synchronous startup phase with timing and logging.

        Args:
            phase_name: Human-readable name for the phase
            phase_func: Synchronous function to execute

        Raises:
            StartupError: If the phase fails
        """
        start = time.time()
        logger.info(f"[STARTUP] Starting phase: {phase_name}")

        try:
            phase_func()
            duration = time.time() - start
            self.phases.append(
                StartupPhaseResult(name=phase_name, success=True, duration_seconds=duration)
            )
            logger.info(f"[STARTUP] Phase '{phase_name}' completed in {duration:.3f}s")

        except Exception as e:
            duration = time.time() - start
            error_msg = str(e)
            self.phases.append(
                StartupPhaseResult(
                    name=phase_name, success=False, duration_seconds=duration, error=error_msg
                )
            )
            logger.error(
                f"[STARTUP] Phase '{phase_name}' FAILED after {duration:.3f}s: {error_msg}",
                exc_info=True,
            )
            raise StartupError(phase_name, error_msg, e) from e

    async def run_phase_async(self, phase_name: str, phase_func: Callable[[], None]) -> None:
        """Execute a startup phase with timing and logging (async wrapper).

        Args:
            phase_name: Human-readable name for the phase
            phase_func: Function to execute (can be sync or return awaitable)

        Raises:
            StartupError: If the phase fails
        """
        start = time.time()
        logger.info(f"[STARTUP] Starting phase: {phase_name}")

        try:
            result = phase_func()
            if asyncio.iscoroutine(result):
                await result
            duration = time.time() - start
            self.phases.append(
                StartupPhaseResult(name=phase_name, success=True, duration_seconds=duration)
            )
            logger.info(f"[STARTUP] Phase '{phase_name}' completed in {duration:.3f}s")

        except Exception as e:
            duration = time.time() - start
            error_msg = str(e)
            self.phases.append(
                StartupPhaseResult(
                    name=phase_name, success=False, duration_seconds=duration, error=error_msg
                )
            )
            logger.error(
                f"[STARTUP] Phase '{phase_name}' FAILED after {duration:.3f}s: {error_msg}",
                exc_info=True,
            )
            raise StartupError(phase_name, error_msg, e) from e

    def complete_startup(self) -> None:
        """Log startup completion summary."""
        total_duration = time.time() - self._start_time
        total = len(self.phases)

        phase_summary = ", ".join(f"{p.name}={p.duration_seconds:.3f}s" for p in self.phases)

        logger.info(
            f"[STARTUP] All {total} startup phases completed successfully "
            f"in {total_duration:.3f}s ({phase_summary})"
        )

    def get_phase_timings(self) -> dict[str, float]:
        """Get timing data for all phases.

        Returns:
            Dictionary mapping phase names to duration in seconds
        """
        return {p.name: p.duration_seconds for p in self.phases}


async def correlation_id_middleware(request: Request, call_next):
    """Add correlation ID to request context for distributed tracing.

    Implements IMP-047: Structured Logging with Correlation IDs.

    - Extracts X-Correlation-ID header from request
    - Generates new UUID if not provided (for distributed tracing)
    - Sets correlation ID in context var (available to all async tasks)
    - Returns correlation ID in response header for client tracking

    Args:
        request: FastAPI request object
        call_next: Next middleware/handler in chain

    Returns:
        Response with X-Correlation-ID header set
    """
    # Get correlation ID from request header or generate new one
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))

    # Set correlation ID in context var (used by structured logging)
    correlation_id_var.set(correlation_id)

    # Process request through next middleware/handler
    response = await call_next(request)

    # Return correlation ID in response header for client to track
    response.headers["X-Correlation-ID"] = correlation_id

    return response


async def metrics_middleware(request: Request, call_next):
    """Record Prometheus metrics for each HTTP request.

    Implements IMP-OPS-010: API metrics collection for observability.

    Tracks:
    - Total request count by method, endpoint, and status code
    - Request latency distribution by method and endpoint

    Args:
        request: FastAPI request object
        call_next: Next middleware/handler in chain

    Returns:
        Response from the next handler, with metrics recorded
    """
    # Skip metrics endpoint to avoid self-instrumentation noise
    if request.url.path == "/metrics":
        return await call_next(request)

    # Normalize endpoint path to reduce cardinality
    # Replace numeric IDs with placeholders
    endpoint = _normalize_endpoint(request.url.path)

    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    # Record metrics
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=endpoint,
        status=str(response.status_code),
    ).inc()

    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=endpoint,
    ).observe(duration)

    return response


def _normalize_endpoint(path: str) -> str:
    """Normalize endpoint path to reduce metric cardinality.

    Replaces variable path segments (UUIDs, numeric IDs) with placeholders
    to prevent high-cardinality metrics explosion.

    Args:
        path: Raw request path like /runs/abc-123/phases/1

    Returns:
        Normalized path like /runs/{id}/phases/{id}
    """
    import re

    # Replace UUIDs (with or without hyphens)
    path = re.sub(
        r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}",
        "{id}",
        path,
        flags=re.IGNORECASE,
    )

    # Replace numeric IDs in path segments
    path = re.sub(r"/\d+(?=/|$)", "/{id}", path)

    return path


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses.

    Implements defense against:
    - MIME sniffing (X-Content-Type-Options)
    - Clickjacking (X-Frame-Options, frame-ancestors CSP directive)
    - XSS attacks (X-XSS-Protection, Content-Security-Policy)
    - Referrer leakage (Referrer-Policy)
    - Unintended feature access (Permissions-Policy)
    """

    async def dispatch(self, request: Request, call_next):
        """Process request and add security headers to response."""
        response = await call_next(request)

        # Prevent MIME sniffing attacks
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # XSS protection (legacy header for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Content Security Policy - comprehensive protection against XSS and injection
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )

        # Referrer policy - prevent leaking sensitive URL information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions policy - restrict browser APIs
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return response


async def approval_timeout_cleanup():
    """Background task to handle approval request timeouts.

    Runs every minute to check for expired approval requests and apply
    the configured default behavior (approve or reject).

    IMP-OPS-003: Respects graceful shutdown by checking shutdown flag
    and registering active transactions to prevent data loss.

    IMP-OPS-007: Records run success/failure for health monitoring.
    """
    from .. import models
    from ..notifications.telegram_notifier import TelegramNotifier

    logger.info("[APPROVAL-TIMEOUT] Background task started")

    # IMP-REL-004: Add iteration counter to prevent unbounded loops
    iteration = 0
    while iteration < MAX_CLEANUP_ITERATIONS:
        iteration += 1
        try:
            # IMP-OPS-003: Check shutdown flag before sleeping
            shutdown_mgr = get_shutdown_manager()
            if shutdown_mgr.is_shutting_down():
                logger.info("[APPROVAL-TIMEOUT] Shutdown detected, exiting cleanly")
                break

            await asyncio.sleep(60)  # Check every minute

            # IMP-OPS-003: Check shutdown again after sleep
            if shutdown_mgr.is_shutting_down():
                logger.info("[APPROVAL-TIMEOUT] Shutdown detected, exiting cleanly")
                break

            # IMP-OPS-003: Register transaction start, reject if shutting down
            if not shutdown_mgr.begin_transaction():
                logger.info("[APPROVAL-TIMEOUT] Shutdown in progress, skipping cleanup cycle")
                break

            # Get database session
            db = next(get_db())

            try:
                # Find expired pending requests
                now = datetime.now(timezone.utc)
                expired_requests = (
                    db.query(models.ApprovalRequest)
                    .filter(
                        models.ApprovalRequest.status == "pending",
                        models.ApprovalRequest.timeout_at <= now,
                    )
                    .all()
                )

                if expired_requests:
                    logger.info(
                        f"[APPROVAL-TIMEOUT] Found {len(expired_requests)} expired requests"
                    )

                    default_action = os.getenv("APPROVAL_DEFAULT_ON_TIMEOUT", "reject")

                    for req in expired_requests:
                        req.status = "timeout"
                        req.responded_at = now
                        req.response_method = "timeout"

                        if default_action == "approve":
                            req.approval_reason = "Auto-approved after timeout"
                            final_status = "approved"
                        else:
                            req.rejected_reason = "Auto-rejected after timeout"
                            final_status = "rejected"

                        logger.warning(
                            f"[APPROVAL-TIMEOUT] Request #{req.id} (phase={req.phase_id}) "
                            f"expired, applying default: {final_status}"
                        )

                        # Send Telegram notification about timeout
                        notifier = TelegramNotifier()
                        if notifier.is_configured() and req.telegram_sent:
                            notifier.send_completion_notice(
                                phase_id=req.phase_id,
                                status="timeout",
                                message=f"⏱️ Approval timed out. Default action: {final_status}",
                            )

                    db.commit()

                # IMP-OPS-007: Record successful run
                try:
                    monitor = get_task_monitor()
                    monitor.record_run("approval_timeout_cleanup")
                except RuntimeError:
                    pass  # Monitor not initialized yet

            finally:
                db.close()
                # IMP-OPS-003: Signal transaction complete
                shutdown_mgr.end_transaction()

        except Exception as e:
            logger.error(f"[APPROVAL-TIMEOUT] Error in cleanup task: {e}", exc_info=True)
            # IMP-OPS-005: Alert on background task failure
            await alert_critical_failure(
                task_name="approval_timeout_cleanup",
                error=str(e),
                severity="high",
            )
            # IMP-OPS-007: Record failure
            try:
                monitor = get_task_monitor()
                monitor.record_failure("approval_timeout_cleanup")
            except RuntimeError:
                pass  # Monitor not initialized yet
            # IMP-OPS-003: Ensure transaction counter is decremented on error
            try:
                shutdown_mgr = get_shutdown_manager()
                shutdown_mgr.end_transaction()
            except RuntimeError:
                pass  # Shutdown manager not initialized yet
            # Continue running despite errors
            await asyncio.sleep(60)
    else:
        # IMP-REL-004: Max iterations reached - log warning
        logger.warning(
            f"[APPROVAL-TIMEOUT] Reached max iterations ({MAX_CLEANUP_ITERATIONS}), "
            "stopping cleanup task to prevent resource exhaustion"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.

    Handles:
    - Production API key validation (security requirement)
    - Database initialization (skipped in testing)
    - Background task lifecycle with supervision (IMP-OPS-001)
    - IMP-OPS-003: Graceful shutdown for DB sessions
    - IMP-OPS-004: Readiness state signaling for /ready endpoint
    - IMP-OPS-007: Background task health monitoring
    - IMP-OPS-012: Structured startup logging with timing for each phase
    """
    global _shutdown_manager, _task_monitor
    from .routes.health import mark_app_initialized, mark_initialization_failed

    # IMP-OPS-012: Initialize startup phase logger for structured initialization logging
    startup_logger = StartupPhaseLogger()
    startup_logger.begin_startup()

    # Variables for cleanup in shutdown
    supervisor = None
    timeout_task = None

    try:
        # Phase 1: Configuration validation
        def validate_config():
            nonlocal autopack_env, api_key
            # IMP-OPS-013: Validate configuration at startup
            # This catches invalid config values early with clear error messages
            validate_startup_config()

            # P0 Security: In production mode, require AUTOPACK_API_KEY to be set
            # This prevents accidentally running an unauthenticated API in production
            # PR-03 (R-03 G4): get_api_key() supports AUTOPACK_API_KEY_FILE for Docker secrets
            autopack_env = os.getenv("AUTOPACK_ENV", "development").lower()

            # get_api_key() will raise RuntimeError if required in production and not set
            api_key = get_api_key()

            if autopack_env == "production" and not api_key:
                raise RuntimeError(
                    "FATAL: AUTOPACK_ENV=production but AUTOPACK_API_KEY is not set. "
                    "For security, the API requires authentication in production mode. "
                    "Set AUTOPACK_API_KEY or AUTOPACK_API_KEY_FILE environment variable, "
                    "or use AUTOPACK_ENV=development."
                )

        autopack_env = None
        api_key = None
        startup_logger.run_phase("config_validation", validate_config)

        # Phase 2: Database initialization (skipped in testing)
        def init_database():
            if os.getenv("TESTING") != "1":
                init_db()
            else:
                logger.info("[STARTUP] Skipping database init in TESTING mode")

        startup_logger.run_phase("database", init_database)

        # Phase 3: Shutdown manager initialization
        # IMP-REL-003: Use async lock for global state protection
        async def init_shutdown_manager():
            global _shutdown_manager
            async with _get_state_lock():
                # IMP-OPS-003: Initialize graceful shutdown manager
                # Configurable via GRACEFUL_SHUTDOWN_TIMEOUT env var (default 30 seconds)
                shutdown_timeout = float(os.getenv("GRACEFUL_SHUTDOWN_TIMEOUT", "30"))
                if _shutdown_manager is None:
                    _shutdown_manager = GracefulShutdownManager(shutdown_timeout=shutdown_timeout)
                    logger.debug(f"Shutdown timeout configured: {shutdown_timeout}s")

        await startup_logger.run_phase_async("shutdown_manager", init_shutdown_manager)

        # Phase 4: Task monitor initialization
        # IMP-REL-003: Use async lock for global state protection
        async def init_task_monitor():
            global _task_monitor
            async with _get_state_lock():
                # IMP-OPS-007: Initialize background task health monitor
                # Configurable via TASK_MONITOR_MAX_AGE env var (default 300 seconds / 5 minutes)
                task_monitor_max_age = float(os.getenv("TASK_MONITOR_MAX_AGE", "300"))
                task_monitor_max_failures = int(os.getenv("TASK_MONITOR_MAX_FAILURES", "3"))
                if _task_monitor is None:
                    _task_monitor = BackgroundTaskMonitor(
                        max_age_seconds=task_monitor_max_age,
                        max_failures=task_monitor_max_failures,
                    )
                    logger.debug(
                        f"Task monitor configured: max_age={task_monitor_max_age}s, "
                        f"max_failures={task_monitor_max_failures}"
                    )

        await startup_logger.run_phase_async("task_monitor", init_task_monitor)

        # Phase 5: Background tasks initialization
        def init_background_tasks():
            nonlocal supervisor, timeout_task
            # IMP-OPS-001: Create supervisor for background tasks with automatic restart
            supervisor = BackgroundTaskSupervisor(max_restarts=5)

            # Start supervised background task for approval timeout cleanup
            timeout_task = asyncio.create_task(
                supervisor.supervise("approval_timeout_cleanup", approval_timeout_cleanup)
            )

        startup_logger.run_phase("background_tasks", init_background_tasks)

        # IMP-OPS-012: Log startup completion summary
        startup_logger.complete_startup()

        # IMP-OPS-004: Mark application as ready for traffic
        mark_app_initialized()
        logger.info("[STARTUP] Application ready for traffic")

    except StartupError as e:
        mark_initialization_failed(f"Startup phase '{e.phase}' failed: {e.message}")
        raise
    except RuntimeError as e:
        logger.critical(str(e))
        mark_initialization_failed(f"Configuration validation failed: {e}")
        raise
    except Exception as e:
        mark_initialization_failed(f"Unexpected startup error: {e}")
        raise

    yield

    # IMP-OPS-003: Graceful shutdown - wait for pending DB transactions
    logger.info("[SHUTDOWN] Initiating graceful shutdown...")
    if _shutdown_manager is not None:
        shutdown_success = await _shutdown_manager.initiate_shutdown()

        if not shutdown_success:
            logger.warning("[SHUTDOWN] Graceful shutdown timed out, some transactions may be lost")

    # Stop background tasks
    if timeout_task is not None:
        timeout_task.cancel()
        try:
            await timeout_task
        except asyncio.CancelledError:
            pass

    # Log supervisor status on shutdown
    if supervisor is not None:
        logger.info(f"[SHUTDOWN] Task supervisor status: {supervisor.get_status()}")

    # IMP-OPS-007: Log task monitor status on shutdown
    if _task_monitor:
        logger.info(f"[TASK-MONITOR] Final status: {_task_monitor.get_all_status()}")

    # IMP-REL-003: Cleanup global state with lock protection
    async with _get_state_lock():
        # IMP-OPS-003: Cleanup shutdown manager
        _shutdown_manager = None
        # IMP-OPS-007: Cleanup task monitor
        _task_monitor = None
    logger.info("[SHUTDOWN] Application shutdown complete")


async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler with production-safe error responses.

    BUILD-188 P5.3: In production mode, returns opaque error IDs without internal details.
    In development/debug mode, returns full exception info for debugging.
    """
    from ..error_reporter import report_error

    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    error_id = str(uuid.uuid4())[:8]  # Short unique ID for log correlation

    # Extract run_id and phase_id from request path if available
    path_parts = request.url.path.split("/")
    run_id = None
    phase_id = None

    try:
        if "runs" in path_parts:
            run_idx = path_parts.index("runs")
            if len(path_parts) > run_idx + 1:
                run_id = path_parts[run_idx + 1]
        if "phases" in path_parts:
            phase_idx = path_parts.index("phases")
            if len(path_parts) > phase_idx + 1:
                phase_id = path_parts[phase_idx + 1]
    except (ValueError, IndexError):
        pass

    # Report error with full context (always, for server-side debugging)
    report_error(
        error=exc,
        run_id=run_id,
        phase_id=phase_id,
        component="api",
        operation=f"{request.method} {request.url.path}",
        context_data={
            "error_id": error_id,
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "query_params": dict(request.query_params),
        },
    )

    # BUILD-188 P5.3 + Security hardening: Never expose stack traces in API responses
    # All internal details stay server-side (logs + error reports)
    # Client receives only error_id for correlation
    #
    # In production: opaque error message
    # In development: slightly more context but still no tracebacks
    if is_production():
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "error_id": error_id,
                "message": "An unexpected error occurred. Reference this error_id when reporting issues.",
            },
        )
    else:
        # Development mode: include error type for debugging, but no traceback
        # Traceback is logged server-side and in error report files
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "Internal server error",
                "error_id": error_id,
                "error_type": type(exc).__name__,
                "message": f"Check server logs for error_id={error_id}",
                "error_report": (
                    f"Error report saved to .autonomous_runs/{run_id or 'errors'}/errors/"
                    if run_id
                    else "Error report saved"
                ),
            },
        )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    This is the primary app factory. It:
    - Creates the FastAPI instance with metadata
    - Attaches lifespan context manager
    - Adds correlation ID middleware for distributed tracing (IMP-047)
    - Configures CORS (when CORS_ALLOWED_ORIGINS is set)
    - Attaches rate limiter
    - Registers global exception handler
    - Includes auth and research routers

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="Autopack Supervisor",
        description="Supervisor/orchestrator implementing the v7 autonomous build playbook",
        version=__version__,
        lifespan=lifespan,
    )

    # IMP-047: Add correlation ID middleware for distributed tracing
    @app.middleware("http")
    async def add_correlation_id_middleware(request: Request, call_next):
        """Middleware wrapper for correlation ID handling."""
        return await correlation_id_middleware(request, call_next)

    # IMP-OPS-010: Add metrics middleware for API observability
    @app.middleware("http")
    async def add_metrics_middleware(request: Request, call_next):
        """Middleware wrapper for Prometheus metrics collection."""
        return await metrics_middleware(request, call_next)

    # IMP-OPS-010: Add /metrics endpoint for Prometheus scraping
    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics():
        """Expose Prometheus metrics for scraping.

        Returns metrics in Prometheus text format for monitoring systems.
        This endpoint is excluded from the OpenAPI schema to reduce clutter.
        """
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # BUILD-188 P5.3: CORS configuration
    # Default: deny all cross-origin requests. Configure CORS_ALLOWED_ORIGINS in env for frontend needs.
    cors_origins_str = os.getenv("CORS_ALLOWED_ORIGINS", "")
    cors_origins = [o.strip() for o in cors_origins_str.split(",") if o.strip()]
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            allow_headers=["*"],
            max_age=600,  # Cache preflight responses for 10 minutes
        )

    # IMP-S05: Add security headers middleware
    # Must be added after CORS to allow CORS preflight to work properly
    app.add_middleware(SecurityHeadersMiddleware)

    # IMP-045: Add gzip compression middleware
    # Compresses responses larger than 1KB to reduce bandwidth by 60-80% on large JSON responses
    # Only applied when client sends Accept-Encoding: gzip header
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Add rate limiting to app
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Register global exception handler
    app.add_exception_handler(Exception, global_exception_handler)

    # Mount authentication router (BUILD-146 P12 Phase 5: migrated to autopack.auth)
    from ..auth import router as auth_router

    app.include_router(auth_router, tags=["authentication"])

    # Mount research router
    from ..research.api.router import research_router

    app.include_router(research_router, prefix="/research", tags=["research"])

    # Mount health router (PR-API-3a)
    from .routes.health import router as health_router

    app.include_router(health_router)

    return app
