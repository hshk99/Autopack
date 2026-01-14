"""Research API router (QUARANTINED - PR8).

This router exposes research session management endpoints.

QUARANTINE STATUS:
- The research subsystem has API drift and is not production-ready
- Tests are marker-excluded by default (see RESEARCH_QUARANTINE.md)
- These endpoints are experimental and may change or be removed

Production Behavior:
- RESEARCH_API_ENABLED=false (default in production) returns 503 for all endpoints
- RESEARCH_API_ENABLED=true enables the endpoints (dev mode default)

See: docs/guides/RESEARCH_QUARANTINE.md for resolution path.
"""

import logging
import os
from functools import wraps

from fastapi import APIRouter, HTTPException
from typing import List
from .schemas import ResearchSession, CreateResearchSession
from autopack.sql_sanitizer import SQLSanitizer

logger = logging.getLogger(__name__)

research_router = APIRouter()


def _is_research_api_enabled() -> bool:
    """Check if research API is enabled.

    Defaults to:
    - True in development (AUTOPACK_ENV != 'production')
    - False in production (AUTOPACK_ENV == 'production')

    Can be overridden with RESEARCH_API_ENABLED env var.
    """
    explicit = os.getenv("RESEARCH_API_ENABLED")
    if explicit is not None:
        return explicit.lower() in ("1", "true", "yes", "enabled")

    env = os.getenv("AUTOPACK_ENV", "development").lower()
    return env != "production"


def research_guard(func):
    """Decorator to guard research endpoints in production."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        if not _is_research_api_enabled():
            logger.warning(
                f"[RESEARCH_API] Endpoint {func.__name__} called but research API is disabled"
            )
            raise HTTPException(
                status_code=503,
                detail="Research API is quarantined and disabled in production. "
                "Set RESEARCH_API_ENABLED=true to enable (not recommended for production).",
            )
        return await func(*args, **kwargs)

    return wrapper


# Mock database
research_sessions = []


@research_router.get("/sessions", response_model=List[ResearchSession])
@research_guard
async def get_research_sessions():
    """Retrieve all research sessions.

    QUARANTINE: This endpoint is disabled in production.
    """
    return research_sessions


@research_router.post("/sessions", response_model=ResearchSession, status_code=201)
@research_guard
async def create_research_session(session: CreateResearchSession):
    """Create a new research session.

    QUARANTINE: This endpoint is disabled in production.
    """
    new_session = ResearchSession(
        session_id="session_" + str(len(research_sessions) + 1),
        status="active",
        created_at="2025-12-20T12:00:00Z",
        topic=session.topic,
        description=session.description,
    )
    research_sessions.append(new_session)
    return new_session


@research_router.get("/sessions/{session_id}", response_model=ResearchSession)
@research_guard
async def get_research_session(session_id: str):
    """Retrieve a specific research session by ID.

    QUARANTINE: This endpoint is disabled in production.
    """
    # Validate session_id to prevent SQL injection
    session_id = SQLSanitizer.validate_parameter(session_id)

    for session in research_sessions:
        if session.session_id == session_id:
            return session
    raise HTTPException(status_code=404, detail="Session not found")


# Export as 'router' for backwards compatibility with __init__.py
router = research_router
