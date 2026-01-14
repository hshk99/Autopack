"""FastAPI application for Autopack Supervisor (Chunks A, B, C, D implementation)"""

import logging
import os

from dotenv import load_dotenv

from .sanitizer import sanitize_url

# BUILD-188: Use module-level logger (avoid basicConfig which can override uvicorn/test harness config)
_startup_logger = logging.getLogger("autopack.startup")

# BUILD-188: Diagnostic logging with credential redaction
# Only log masked URLs to prevent secret leakage (debug level - won't show unless explicitly enabled)
_raw_db_url = os.getenv("DATABASE_URL", "NOT SET")
_startup_logger.debug(
    "[API_SERVER_STARTUP] DATABASE_URL from environment: %s",
    sanitize_url(_raw_db_url) if _raw_db_url != "NOT SET" else "NOT SET",
)

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# PR-API-1: Auth + rate limiting deps extracted to api/deps.py
from .api.deps import limiter

from .version import __version__

logger = logging.getLogger(__name__)

# Note: Auth functions (verify_api_key, verify_read_access, get_client_ip) and
# limiter are now imported from api.deps (PR-API-1 seam extraction)

# Load .env but DON'T override existing env vars (e.g., DATABASE_URL from executor)
# This ensures subprocess API server inherits DATABASE_URL from parent process
load_dotenv(override=False)

# BUILD-188: Log only masked URLs to prevent secret leakage
_db_url_after = os.getenv("DATABASE_URL", "NOT SET")
_startup_logger.debug(
    "[API_SERVER_STARTUP] DATABASE_URL after load_dotenv(): %s",
    sanitize_url(_db_url_after) if _db_url_after != "NOT SET" else "NOT SET",
)

# P0 diagnostic: Log actual resolved database URL after normalization (masked)
from autopack.config import get_database_url

resolved_url = get_database_url()
_startup_logger.debug(
    "[API_SERVER_STARTUP] Resolved DATABASE_URL (after normalization): %s",
    sanitize_url(resolved_url) if resolved_url else "NOT SET",
)

# PR-API-2: App factory and wiring extracted to api/app.py
# Note: We still create the app here (not via create_app()) to keep all routes
# defined in main.py until router extraction is complete (PR-API-3+).
# This keeps the canonical entrypoint `uvicorn autopack.main:app` working.
from .api.app import lifespan, global_exception_handler, SecurityHeadersMiddleware

import logging

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Autopack Supervisor",
    description="Supervisor/orchestrator implementing the v7 autonomous build playbook",
    version=__version__,
    lifespan=lifespan,
)

# BUILD-188 P5.3: CORS configuration
# Default: deny all cross-origin requests. Configure CORS_ALLOWED_ORIGINS in env for frontend needs.
_cors_origins = (
    os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if os.getenv("CORS_ALLOWED_ORIGINS") else []
)
if _cors_origins:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        max_age=600,  # Cache preflight responses for 10 minutes
    )

# IMP-S05: Add security headers middleware
# Must be added after CORS to allow CORS preflight to work properly
app.add_middleware(SecurityHeadersMiddleware)

# Add rate limiting to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Register global exception handler (extracted to api/app.py)
app.add_exception_handler(Exception, global_exception_handler)

# Mount authentication router (BUILD-146 P12 Phase 5: migrated to autopack.auth)
from autopack.auth import router as auth_router

app.include_router(auth_router, tags=["authentication"])

# Mount research router
from autopack.research.api.router import research_router

app.include_router(research_router, prefix="/research", tags=["research"])

# PR-API-3a: Health router (root + health endpoints)
from autopack.api.routes.health import router as health_router

app.include_router(health_router)

# PR-API-3b: Files router (upload endpoint)
from autopack.api.routes.files import router as files_router

app.include_router(files_router)

# PR-API-3c: Storage router (storage optimization endpoints)
from autopack.api.routes.storage import router as storage_router

app.include_router(storage_router)

# PR-API-3d: Dashboard router (dashboard metrics and status endpoints)
from autopack.api.routes.dashboard import router as dashboard_router

app.include_router(dashboard_router)

# PR-API-3e: Governance router (governance approval endpoints)
from autopack.api.routes.governance import router as governance_router

app.include_router(governance_router)

# PR-API-3f: Approvals router (approval requests + telegram webhook)
from autopack.api.routes.approvals import router as approvals_router

app.include_router(approvals_router)

# PR-API-3g: Artifacts router (artifact browsing endpoints)
from autopack.api.routes.artifacts import router as artifacts_router

app.include_router(artifacts_router)

# PR-API-3h: Phases router (phase status and result endpoints)
from autopack.api.routes.phases import router as phases_router

app.include_router(phases_router)

# PR-API-3i: Runs router (run management endpoints)
from autopack.api.routes.runs import router as runs_router

app.include_router(runs_router)


# ==============================================================================
# All API routes have been extracted to api/routes/ package:
#
# PR-API-3a: health.py - root + health endpoints
# PR-API-3b: files.py - file upload endpoint
# PR-API-3c: storage.py - storage optimization endpoints
# PR-API-3d: dashboard.py - dashboard metrics and status endpoints
# PR-API-3e: governance.py - governance approval endpoints
# PR-API-3f: approvals.py - approval requests + telegram webhook
# PR-API-3g: artifacts.py - artifact browsing endpoints
# PR-API-3h: phases.py - phase status and result endpoints
# PR-API-3i: runs.py - run management endpoints
# ==============================================================================

# Backwards compatibility re-exports for tests (PR-API-1/PR-API-3 compatibility layer)
# These allow existing tests to continue importing from autopack.main
from .api.deps import (  # noqa: F401
    _is_trusted_proxy,
    get_client_ip,
    verify_api_key,
    verify_read_access,
)
from .api.routes.phases import submit_builder_result  # noqa: F401
from .config import settings  # noqa: F401
from .database import get_db  # noqa: F401
from .file_layout import RunFileLayout  # noqa: F401
from .notifications.telegram_notifier import answer_telegram_callback  # noqa: F401
from .notifications.telegram_webhook_security import (  # noqa: F401
    verify_telegram_webhook as verify_telegram_webhook_crypto,
)
