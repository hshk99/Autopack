"""Research API router with gated bootstrap mode (IMP-RES-006).

This router exposes research session management endpoints with a tri-state mode
system for controlled access.

API MODE SYSTEM:
- DISABLED (default in production): All endpoints return 503
- BOOTSTRAP_ONLY: Only bootstrap endpoints are accessible
- FULL: All endpoints accessible (dev/local only)

Bootstrap-only endpoints (accessible in BOOTSTRAP_ONLY mode):
- POST /research/bootstrap - Start a bootstrap research session
- GET /research/bootstrap/{id}/status - Get bootstrap session status
- GET /research/bootstrap/{id}/draft_anchor - Get draft anchor from completed session

QUARANTINE STATUS:
- Non-bootstrap endpoints remain quarantined
- Bootstrap endpoints are production-safe with limited scope

See: docs/guides/RESEARCH_QUARANTINE.md for resolution path.
"""

import logging
import os
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from autopack.sql_sanitizer import SQLSanitizer

from .schemas import CreateResearchSession, ResearchSession

logger = logging.getLogger(__name__)

research_router = APIRouter()


class ResearchAPIMode(str, Enum):
    """Research API access mode.

    Controls which endpoints are accessible:
    - DISABLED: All endpoints return 503 (production default)
    - BOOTSTRAP_ONLY: Only bootstrap endpoints work (limited production use)
    - FULL: All endpoints accessible (development only)
    """

    DISABLED = "disabled"
    BOOTSTRAP_ONLY = "bootstrap_only"
    FULL = "full"


def _get_research_api_mode() -> ResearchAPIMode:
    """Get the current Research API mode.

    Priority:
    1. RESEARCH_API_MODE env var (explicit mode selection)
    2. RESEARCH_API_ENABLED env var (legacy boolean, maps to FULL/DISABLED)
    3. Environment-based defaults:
       - production: DISABLED
       - development: FULL

    Returns:
        ResearchAPIMode enum value
    """
    # Check explicit mode first
    mode_str = os.getenv("RESEARCH_API_MODE", "").lower()
    if mode_str:
        try:
            return ResearchAPIMode(mode_str)
        except ValueError:
            logger.warning(
                f"[RESEARCH_API] Invalid RESEARCH_API_MODE='{mode_str}', "
                f"valid values: {[m.value for m in ResearchAPIMode]}"
            )
            # Fall through to other checks

    # Legacy boolean check
    explicit = os.getenv("RESEARCH_API_ENABLED")
    if explicit is not None:
        if explicit.lower() in ("1", "true", "yes", "enabled"):
            return ResearchAPIMode.FULL
        return ResearchAPIMode.DISABLED

    # Environment-based default
    env = os.getenv("AUTOPACK_ENV", "development").lower()
    if env == "production":
        return ResearchAPIMode.DISABLED
    return ResearchAPIMode.FULL


def research_guard(func):
    """Decorator to guard non-bootstrap research endpoints.

    Requires FULL mode. Returns 503 in DISABLED or BOOTSTRAP_ONLY modes.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        mode = _get_research_api_mode()
        if mode != ResearchAPIMode.FULL:
            logger.warning(
                f"[RESEARCH_API] Endpoint {func.__name__} called but mode is {mode.value}. "
                "Requires FULL mode."
            )
            raise HTTPException(
                status_code=503,
                detail=f"Research API is in {mode.value} mode. "
                f"This endpoint requires mode=full. "
                "Set RESEARCH_API_MODE=full to enable (not recommended for production).",
            )
        return await func(*args, **kwargs)

    return wrapper


def bootstrap_guard(func):
    """Decorator to guard bootstrap endpoints.

    Allows access in BOOTSTRAP_ONLY or FULL modes. Returns 503 in DISABLED mode.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        mode = _get_research_api_mode()
        if mode == ResearchAPIMode.DISABLED:
            logger.warning(
                f"[RESEARCH_API] Bootstrap endpoint {func.__name__} called but mode is DISABLED"
            )
            raise HTTPException(
                status_code=503,
                detail="Research API is disabled. "
                "Set RESEARCH_API_MODE=bootstrap_only or RESEARCH_API_MODE=full to enable.",
            )
        return await func(*args, **kwargs)

    return wrapper


# =============================================================================
# Bootstrap Session Schemas
# =============================================================================


class BootstrapRequest(BaseModel):
    """Request to start a bootstrap research session."""

    idea_text: str = Field(..., description="Raw idea text to parse and research")
    use_cache: bool = Field(default=True, description="Use cached results if available")
    parallel: bool = Field(default=True, description="Execute research phases in parallel")


class BootstrapResponse(BaseModel):
    """Response for bootstrap session creation."""

    session_id: str = Field(..., description="Bootstrap session ID")
    status: str = Field(..., description="Session status")
    message: str = Field(..., description="Human-readable status message")


class BootstrapStatusResponse(BaseModel):
    """Response for bootstrap session status check."""

    session_id: str = Field(..., description="Bootstrap session ID")
    status: str = Field(..., description="Current session status")
    current_phase: str = Field(..., description="Current phase of the bootstrap process")
    is_complete: bool = Field(..., description="Whether all phases are complete")
    completed_phases: List[str] = Field(
        default_factory=list, description="List of completed phases"
    )
    failed_phases: List[str] = Field(default_factory=list, description="List of failed phases")
    synthesis: Optional[dict] = Field(default=None, description="Synthesized research findings")


class DraftAnchorResponse(BaseModel):
    """Response containing draft anchor from completed bootstrap session."""

    session_id: str = Field(..., description="Bootstrap session ID")
    anchor: dict = Field(..., description="Draft IntentionAnchorV2 as dict")
    clarifying_questions: List[str] = Field(
        default_factory=list, description="Questions for low-confidence pivots"
    )
    confidence_report: dict = Field(
        default_factory=dict, description="Confidence scores per pivot type"
    )


# =============================================================================
# In-memory storage for bootstrap sessions (production would use DB)
# =============================================================================

# Import bootstrap session components
try:
    from autopack.research.anchor_mapper import ResearchToAnchorMapper
    from autopack.research.idea_parser import IdeaParser
    from autopack.research.orchestrator import ResearchOrchestrator

    _bootstrap_available = True
    _orchestrator = ResearchOrchestrator()
    _idea_parser = IdeaParser()
    _anchor_mapper = ResearchToAnchorMapper()
except ImportError as e:
    logger.warning(f"[RESEARCH_API] Bootstrap components not available: {e}")
    _bootstrap_available = False
    _orchestrator = None
    _idea_parser = None
    _anchor_mapper = None


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
        session_id=str(uuid4()),
        status="active",
        created_at=datetime.utcnow().isoformat() + "Z",
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


# =============================================================================
# Bootstrap Endpoints (accessible in BOOTSTRAP_ONLY or FULL mode)
# =============================================================================


@research_router.post("/bootstrap", response_model=BootstrapResponse, status_code=201)
@bootstrap_guard
async def start_bootstrap_session(request: BootstrapRequest):
    """Start a bootstrap research session for project initialization.

    This endpoint is accessible in BOOTSTRAP_ONLY or FULL mode.
    Parses the idea, runs research phases, and prepares for anchor generation.

    Args:
        request: BootstrapRequest with idea_text and options

    Returns:
        BootstrapResponse with session_id and status
    """
    if not _bootstrap_available:
        raise HTTPException(
            status_code=503,
            detail="Bootstrap components not available. Check server logs.",
        )

    # Validate input
    if not request.idea_text or len(request.idea_text.strip()) < 10:
        raise HTTPException(
            status_code=400,
            detail="idea_text must be at least 10 characters",
        )

    try:
        # Parse the idea
        parsed_idea = _idea_parser.parse(request.idea_text)
        logger.info(
            f"[BOOTSTRAP] Parsed idea: {parsed_idea.title} ({parsed_idea.detected_project_type.value})"
        )

        # Start bootstrap session
        session = await _orchestrator.start_bootstrap_session(
            parsed_idea=parsed_idea,
            use_cache=request.use_cache,
            parallel=request.parallel,
        )

        # Determine status message
        if session.is_complete():
            message = "Bootstrap session completed successfully. Use /bootstrap/{id}/draft_anchor to get the anchor."
            status = "completed"
        elif session.get_failed_phases():
            failed = [p[0].value for p in session.get_failed_phases()]
            message = f"Bootstrap session completed with failures in: {failed}"
            status = "partial"
        else:
            message = "Bootstrap session started. Research phases in progress."
            status = "in_progress"

        return BootstrapResponse(
            session_id=session.session_id,
            status=status,
            message=message,
        )

    except Exception as e:
        logger.error(f"[BOOTSTRAP] Error starting session: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start bootstrap session: {str(e)}",
        )


@research_router.get("/bootstrap/{session_id}/status", response_model=BootstrapStatusResponse)
@bootstrap_guard
async def get_bootstrap_status(session_id: str):
    """Get the status of a bootstrap session.

    This endpoint is accessible in BOOTSTRAP_ONLY or FULL mode.

    Args:
        session_id: The bootstrap session ID

    Returns:
        BootstrapStatusResponse with current status and phase info
    """
    if not _bootstrap_available:
        raise HTTPException(
            status_code=503,
            detail="Bootstrap components not available. Check server logs.",
        )

    # Validate session_id
    session_id = SQLSanitizer.validate_parameter(session_id)

    session = _orchestrator.get_bootstrap_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Bootstrap session {session_id} not found",
        )

    # Determine status
    if session.is_complete():
        status = "completed"
    elif session.get_failed_phases():
        status = "partial"
    else:
        status = "in_progress"

    completed_phases = [p.value for p in session.get_completed_phases()]
    failed_phases = [p[0].value for p in session.get_failed_phases()]

    return BootstrapStatusResponse(
        session_id=session.session_id,
        status=status,
        current_phase=session.current_phase.value,
        is_complete=session.is_complete(),
        completed_phases=completed_phases,
        failed_phases=failed_phases,
        synthesis=session.synthesis if session.is_complete() else None,
    )


@research_router.get("/bootstrap/{session_id}/draft_anchor", response_model=DraftAnchorResponse)
@bootstrap_guard
async def get_draft_anchor(session_id: str):
    """Get the draft IntentionAnchorV2 from a completed bootstrap session.

    This endpoint is accessible in BOOTSTRAP_ONLY or FULL mode.
    The session must be complete before an anchor can be generated.

    Args:
        session_id: The bootstrap session ID

    Returns:
        DraftAnchorResponse with anchor, questions, and confidence report
    """
    if not _bootstrap_available:
        raise HTTPException(
            status_code=503,
            detail="Bootstrap components not available. Check server logs.",
        )

    # Validate session_id
    session_id = SQLSanitizer.validate_parameter(session_id)

    session = _orchestrator.get_bootstrap_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Bootstrap session {session_id} not found",
        )

    if not session.is_complete():
        incomplete = set(
            ["market_research", "competitive_analysis", "technical_feasibility"]
        ) - set(p.value for p in session.get_completed_phases())
        raise HTTPException(
            status_code=400,
            detail=f"Bootstrap session is not complete. Incomplete phases: {list(incomplete)}",
        )

    try:
        # Map to anchor (parsed_idea is not stored, but we can recreate minimal version)
        # Note: In production, we'd store the parsed_idea with the session
        anchor, questions = _anchor_mapper.map_to_anchor(session, parsed_idea=None)

        # Get confidence report
        mappings = _anchor_mapper._map_all_pivots(session, None)
        confidence_report = {
            m.pivot_type.value: {
                "score": m.confidence.score,
                "reasoning": m.confidence.reasoning,
            }
            for m in mappings
        }

        return DraftAnchorResponse(
            session_id=session.session_id,
            anchor=anchor.model_dump(mode="json"),
            clarifying_questions=questions,
            confidence_report=confidence_report,
        )

    except Exception as e:
        logger.error(f"[BOOTSTRAP] Error generating anchor: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate draft anchor: {str(e)}",
        )


# =============================================================================
# Utility endpoint for checking API mode
# =============================================================================


@research_router.get("/mode")
async def get_api_mode():
    """Get the current Research API mode.

    This endpoint is always accessible (not guarded) for diagnostics.

    Returns:
        Current mode and which endpoint groups are accessible
    """
    mode = _get_research_api_mode()
    return {
        "mode": mode.value,
        "bootstrap_endpoints_enabled": mode != ResearchAPIMode.DISABLED,
        "full_endpoints_enabled": mode == ResearchAPIMode.FULL,
        "bootstrap_available": _bootstrap_available,
    }


# Export as 'router' for backwards compatibility with __init__.py
router = research_router
