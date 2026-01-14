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
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from ..config import get_api_key, is_production
from ..database import get_db, init_db
from ..version import __version__
from .deps import limiter

logger = logging.getLogger(__name__)


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
    """
    from ..notifications.telegram_notifier import TelegramNotifier
    from .. import models

    logger.info("[APPROVAL-TIMEOUT] Background task started")

    while True:
        try:
            await asyncio.sleep(60)  # Check every minute

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

            finally:
                db.close()

        except Exception as e:
            logger.error(f"[APPROVAL-TIMEOUT] Error in cleanup task: {e}", exc_info=True)
            # Continue running despite errors
            await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager.

    Handles:
    - Production API key validation (security requirement)
    - Database initialization (skipped in testing)
    - Background task lifecycle (approval timeout cleanup)
    """
    # P0 Security: In production mode, require AUTOPACK_API_KEY to be set
    # This prevents accidentally running an unauthenticated API in production
    # PR-03 (R-03 G4): get_api_key() supports AUTOPACK_API_KEY_FILE for Docker secrets
    autopack_env = os.getenv("AUTOPACK_ENV", "development").lower()

    # get_api_key() will raise RuntimeError if required in production and not set
    try:
        api_key = get_api_key()
    except RuntimeError as e:
        logger.critical(str(e))
        raise

    if autopack_env == "production" and not api_key:
        error_msg = (
            "FATAL: AUTOPACK_ENV=production but AUTOPACK_API_KEY is not set. "
            "For security, the API requires authentication in production mode. "
            "Set AUTOPACK_API_KEY or AUTOPACK_API_KEY_FILE environment variable, "
            "or use AUTOPACK_ENV=development."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    # Skip DB init during testing (tests use their own DB setup)
    if os.getenv("TESTING") != "1":
        init_db()

    # Start background task for approval timeout cleanup
    timeout_task = asyncio.create_task(approval_timeout_cleanup())

    yield

    # Stop background tasks
    timeout_task.cancel()
    try:
        await timeout_task
    except asyncio.CancelledError:
        pass


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
