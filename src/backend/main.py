"""DEPRECATED: Backend server entrypoint (DO NOT USE)

BUILD-146 P12 API Consolidation - Phase 3:
This backend server entrypoint is DEPRECATED and should not be used.

USE THE CANONICAL SERVER INSTEAD:
    PYTHONPATH=src uvicorn autopack.main:app --host 0.0.0.0 --port 8000

The backend package remains as a LIBRARY for auth functionality until Phase 5
migration is complete, but this server entrypoint is non-functional.

See docs/CANONICAL_API_CONSOLIDATION_PLAN.md for migration details.
"""

import sys
import os


def _raise_deprecation_error():
    """Raise clear error directing users to canonical server."""
    error_message = """
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║  ERROR: Backend server is DEPRECATED and cannot be run.                  ║
║                                                                           ║
║  BUILD-146 P12 API Consolidation:                                        ║
║  The backend server has been consolidated into the canonical Autopack    ║
║  supervisor server. All endpoints are now served by autopack.main:app.   ║
║                                                                           ║
║  ┌─────────────────────────────────────────────────────────────────────┐ ║
║  │  USE THIS INSTEAD:                                                  │ ║
║  │                                                                     │ ║
║  │  PYTHONPATH=src uvicorn autopack.main:app --host 0.0.0.0 --port 8000 │ ║
║  └─────────────────────────────────────────────────────────────────────┘ ║
║                                                                           ║
║  The canonical server provides all functionality:                        ║
║    ✓ Run lifecycle endpoints (executor)                                  ║
║    ✓ Dashboard endpoints                                                 ║
║    ✓ Health check with DB identity + kill switches                       ║
║    ✓ Consolidated metrics (kill switch OFF by default)                   ║
║    ✓ Authentication (X-API-Key + Bearer)                                 ║
║    ✓ Approval workflows                                                  ║
║    ✓ Governance requests                                                 ║
║                                                                           ║
║  See docs/CANONICAL_API_CONTRACT.md for endpoint documentation.          ║
║  See docs/CANONICAL_API_CONSOLIDATION_PLAN.md for migration details.     ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
"""
    print(error_message, file=sys.stderr)
    sys.exit(1)


# Immediately error if someone tries to import this as a server
if __name__ == "__main__" or os.getenv("AUTOPACK_ALLOW_DEPRECATED_BACKEND") != "1":
    # Allow import for library usage (auth router), but block server startup
    if __name__ == "__main__":
        _raise_deprecation_error()

# The rest of this file is kept for backward compatibility with library imports
# (e.g., backend.api.auth is still imported by autopack.main until Phase 5)
from fastapi import FastAPI
from .api.auth import router as auth_router
from .api.search import include_router as include_search_router
from .api.runs import router as runs_router
from .api.approvals import router as approvals_router
from .api.health import router as health_router
from .api.dashboard import router as dashboard_router
from .database import Base, engine

# Create app instance for backward compatibility, but it should not be used
app = FastAPI(
    title="Autopack Backend (DEPRECATED - Use autopack.main:app)",
    description="DEPRECATED: This server is deprecated. Use autopack.main:app instead.",
    version="0.1.0-deprecated"
)

@app.on_event("startup")
def on_startup():
    """Startup handler - warns about deprecation."""
    import warnings
    warnings.warn(
        "Backend server is DEPRECATED. Use 'uvicorn autopack.main:app' instead.",
        DeprecationWarning,
        stacklevel=2
    )
    # Only create tables if explicitly allowed (for testing)
    if os.getenv("AUTOPACK_ALLOW_DEPRECATED_BACKEND") == "1":
        Base.metadata.create_all(bind=engine)

# Include routers (for backward compatibility only)
app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(auth_router)
app.include_router(runs_router)
app.include_router(approvals_router)
include_search_router(app)
