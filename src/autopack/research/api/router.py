"""Research API router with gated modes (IMP-RES-006, IMP-RES-010).

This router exposes research session management endpoints with a tri-state mode
system for controlled access.

API MODE SYSTEM:
- DISABLED (default in production): All endpoints return 503
- BOOTSTRAP_ONLY: Only bootstrap endpoints are accessible
- FULL: All endpoints accessible (requires explicit opt-in with safety gates)

Bootstrap-only endpoints (accessible in BOOTSTRAP_ONLY mode):
- POST /research/bootstrap - Start a bootstrap research session
- GET /research/bootstrap/{id}/status - Get bootstrap session status
- GET /research/bootstrap/{id}/draft_anchor - Get draft anchor from completed session

Full mode endpoints (accessible only in FULL mode, with safety gates):
- POST /research/full/session - Start a full research session
- POST /research/full/session/{id}/validate - Validate a research session
- POST /research/full/session/{id}/publish - Publish research findings
- GET /research/full/cache/status - Get cache statistics
- DELETE /research/full/cache - Clear research cache
- POST /research/full/invalidate - Invalidate cached session

QUARANTINE STATUS:
- Full mode requires explicit RESEARCH_API_MODE=full
- Safety gates enforce rate limits, request validation, and audit logging
- Bootstrap endpoints remain production-safe with limited scope

See: docs/guides/RESEARCH_QUARANTINE.md for resolution path.
"""

import logging
import os
import time
from collections import defaultdict
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

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


def _is_research_api_enabled() -> bool:
    """Check if Research API is enabled (legacy compatibility function).

    This function provides backward compatibility for code that checks
    the boolean enabled/disabled state. For new code, use
    _get_research_api_mode() instead.

    Returns:
        True if mode is FULL or BOOTSTRAP_ONLY, False if DISABLED
    """
    mode = _get_research_api_mode()
    return mode != ResearchAPIMode.DISABLED


# =============================================================================
# Safety Gates for Full Mode
# =============================================================================


class SafetyGateConfig:
    """Configuration for full mode safety gates."""

    # Rate limiting: requests per minute per endpoint
    RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv("RESEARCH_API_RATE_LIMIT", "30"))

    # Maximum request body size in bytes (10KB default)
    MAX_REQUEST_SIZE_BYTES = int(os.getenv("RESEARCH_API_MAX_REQUEST_SIZE", "10240"))

    # Enable audit logging
    AUDIT_LOGGING_ENABLED = os.getenv("RESEARCH_API_AUDIT_LOGGING", "true").lower() in (
        "1",
        "true",
        "yes",
    )


class RateLimiter:
    """Simple in-memory rate limiter for full mode endpoints."""

    def __init__(self, requests_per_minute: int = 30):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests allowed per minute
        """
        self._requests: Dict[str, List[float]] = defaultdict(list)
        self._limit = requests_per_minute

    def is_allowed(self, key: str) -> bool:
        """Check if request is allowed under rate limit.

        Args:
            key: Identifier for the rate limit bucket (e.g., endpoint name)

        Returns:
            True if request is allowed, False if rate limited
        """
        now = time.time()
        minute_ago = now - 60

        # Clean old entries
        self._requests[key] = [ts for ts in self._requests[key] if ts > minute_ago]

        # Check limit
        if len(self._requests[key]) >= self._limit:
            return False

        # Record this request
        self._requests[key].append(now)
        return True

    def get_remaining(self, key: str) -> int:
        """Get remaining requests for a key.

        Args:
            key: Identifier for the rate limit bucket

        Returns:
            Number of requests remaining in the current window
        """
        now = time.time()
        minute_ago = now - 60
        current_count = len([ts for ts in self._requests[key] if ts > minute_ago])
        return max(0, self._limit - current_count)


# Global rate limiter instance
_rate_limiter = RateLimiter(SafetyGateConfig.RATE_LIMIT_REQUESTS_PER_MINUTE)


def _audit_log(
    endpoint: str,
    action: str,
    details: Optional[Dict[str, Any]] = None,
    success: bool = True,
) -> None:
    """Log audit entry for full mode endpoint access.

    Args:
        endpoint: Name of the endpoint accessed
        action: Description of the action taken
        details: Additional details to log
        success: Whether the action succeeded
    """
    if not SafetyGateConfig.AUDIT_LOGGING_ENABLED:
        return

    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "endpoint": endpoint,
        "action": action,
        "success": success,
        "details": details or {},
    }

    if success:
        logger.info(f"[RESEARCH_API_AUDIT] {log_entry}")
    else:
        logger.warning(f"[RESEARCH_API_AUDIT] {log_entry}")


def full_mode_guard(func):
    """Decorator to guard full mode endpoints with safety gates.

    Requires FULL mode and enforces:
    - Rate limiting
    - Audit logging
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        mode = _get_research_api_mode()
        endpoint_name = func.__name__

        # Check mode
        if mode != ResearchAPIMode.FULL:
            _audit_log(
                endpoint_name,
                "access_denied",
                {"reason": f"mode is {mode.value}"},
                success=False,
            )
            raise HTTPException(
                status_code=503,
                detail=f"Research API is in {mode.value} mode. "
                f"Full mode endpoints require RESEARCH_API_MODE=full.",
            )

        # Check rate limit
        if not _rate_limiter.is_allowed(endpoint_name):
            _audit_log(
                endpoint_name,
                "rate_limited",
                {"remaining": _rate_limiter.get_remaining(endpoint_name)},
                success=False,
            )
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {SafetyGateConfig.RATE_LIMIT_REQUESTS_PER_MINUTE} "
                f"requests per minute. Try again later.",
            )

        # Execute the endpoint
        try:
            result = await func(*args, **kwargs)
            _audit_log(endpoint_name, "success")
            return result
        except HTTPException:
            raise
        except Exception as e:
            _audit_log(
                endpoint_name,
                "error",
                {"error": str(e)},
                success=False,
            )
            raise

    return wrapper


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
                detail=f"Research API is quarantined (mode={mode.value}). "
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
# Full Mode Schemas
# =============================================================================


class FullSessionRequest(BaseModel):
    """Request to start a full research session."""

    title: str = Field(..., min_length=3, max_length=200, description="Research session title")
    description: str = Field(
        ..., min_length=10, max_length=2000, description="Research session description"
    )
    objectives: List[str] = Field(default_factory=list, description="List of research objectives")

    @field_validator("objectives")
    @classmethod
    def validate_objectives(cls, v: List[str]) -> List[str]:
        """Validate objectives list."""
        if len(v) > 10:
            raise ValueError("Maximum 10 objectives allowed")
        return [obj.strip() for obj in v if obj.strip()]


class FullSessionResponse(BaseModel):
    """Response for full research session creation."""

    session_id: str = Field(..., description="Research session ID")
    status: str = Field(..., description="Session status")
    message: str = Field(..., description="Human-readable status message")


class SessionValidationResponse(BaseModel):
    """Response for session validation."""

    session_id: str = Field(..., description="Research session ID")
    validation_status: str = Field(..., description="Validation result")
    message: str = Field(..., description="Validation message")
    checks_passed: List[str] = Field(
        default_factory=list, description="List of passed validation checks"
    )
    checks_failed: List[str] = Field(
        default_factory=list, description="List of failed validation checks"
    )


class SessionPublishResponse(BaseModel):
    """Response for session publication."""

    session_id: str = Field(..., description="Research session ID")
    published: bool = Field(..., description="Whether publication succeeded")
    message: str = Field(..., description="Publication message")


class CacheStatusResponse(BaseModel):
    """Response for cache status."""

    cache_enabled: bool = Field(..., description="Whether caching is enabled")
    cached_sessions: int = Field(..., description="Number of cached sessions")
    cache_ttl_hours: int = Field(..., description="Cache TTL in hours")


class CacheInvalidateRequest(BaseModel):
    """Request to invalidate a cached session."""

    idea_title: str = Field(..., description="Title of the idea to invalidate")
    idea_description: str = Field(..., description="Description of the idea")
    project_type: str = Field(default="other", description="Project type")


class CacheInvalidateResponse(BaseModel):
    """Response for cache invalidation."""

    invalidated: bool = Field(..., description="Whether invalidation succeeded")
    message: str = Field(..., description="Invalidation message")


# =============================================================================
# Full Mode Endpoints (accessible only in FULL mode with safety gates)
# =============================================================================


@research_router.post("/full/session", response_model=FullSessionResponse, status_code=201)
@full_mode_guard
async def start_full_session(request: FullSessionRequest):
    """Start a full research session with comprehensive capabilities.

    This endpoint is only accessible in FULL mode and includes safety gates:
    - Rate limiting (configurable via RESEARCH_API_RATE_LIMIT)
    - Audit logging (configurable via RESEARCH_API_AUDIT_LOGGING)

    Args:
        request: FullSessionRequest with title, description, and objectives

    Returns:
        FullSessionResponse with session_id and status
    """
    if not _bootstrap_available or not _orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Research components not available. Check server logs.",
        )

    try:
        session_id = _orchestrator.start_session(
            intent_title=request.title,
            intent_description=request.description,
            intent_objectives=request.objectives,
        )

        return FullSessionResponse(
            session_id=session_id,
            status="active",
            message=f"Full research session started. Use /full/session/{session_id}/validate to validate.",
        )

    except Exception as e:
        logger.error(f"[FULL_MODE] Error starting session: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start full research session: {str(e)}",
        )


@research_router.post(
    "/full/session/{session_id}/validate",
    response_model=SessionValidationResponse,
)
@full_mode_guard
async def validate_full_session(session_id: str):
    """Validate a full research session.

    Runs validation checks including evidence validation, recency validation,
    and quality validation.

    This endpoint is only accessible in FULL mode with safety gates.

    Args:
        session_id: The research session ID

    Returns:
        SessionValidationResponse with validation results
    """
    if not _bootstrap_available or not _orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Research components not available. Check server logs.",
        )

    # Validate session_id
    session_id = SQLSanitizer.validate_parameter(session_id)

    session = _orchestrator.sessions.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Research session {session_id} not found",
        )

    try:
        result_message = _orchestrator.validate_session(session_id)

        # Determine which checks passed/failed based on message
        is_success = "successfully" in result_message.lower()
        checks_passed = []
        checks_failed = []

        if is_success:
            checks_passed = ["evidence_validation", "recency_validation", "quality_validation"]
        else:
            checks_failed = ["validation"]

        return SessionValidationResponse(
            session_id=session_id,
            validation_status="validated" if is_success else "failed",
            message=result_message,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
        )

    except Exception as e:
        logger.error(f"[FULL_MODE] Error validating session: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to validate session: {str(e)}",
        )


@research_router.post(
    "/full/session/{session_id}/publish",
    response_model=SessionPublishResponse,
)
@full_mode_guard
async def publish_full_session(session_id: str):
    """Publish a validated research session.

    The session must be validated before publishing.

    This endpoint is only accessible in FULL mode with safety gates.

    Args:
        session_id: The research session ID

    Returns:
        SessionPublishResponse with publication results
    """
    if not _bootstrap_available or not _orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Research components not available. Check server logs.",
        )

    # Validate session_id
    session_id = SQLSanitizer.validate_parameter(session_id)

    session = _orchestrator.sessions.get(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Research session {session_id} not found",
        )

    try:
        success = _orchestrator.publish_session(session_id)

        if success:
            return SessionPublishResponse(
                session_id=session_id,
                published=True,
                message="Research session published successfully.",
            )
        else:
            return SessionPublishResponse(
                session_id=session_id,
                published=False,
                message="Publication failed. Ensure the session is validated first.",
            )

    except Exception as e:
        logger.error(f"[FULL_MODE] Error publishing session: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to publish session: {str(e)}",
        )


@research_router.get("/full/cache/status", response_model=CacheStatusResponse)
@full_mode_guard
async def get_cache_status():
    """Get research cache status and statistics.

    This endpoint is only accessible in FULL mode with safety gates.

    Returns:
        CacheStatusResponse with cache statistics
    """
    if not _bootstrap_available or not _orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Research components not available. Check server logs.",
        )

    cache = _orchestrator._cache
    return CacheStatusResponse(
        cache_enabled=True,
        cached_sessions=len(cache._cache),
        cache_ttl_hours=cache.ttl_hours,
    )


@research_router.delete("/full/cache", status_code=204)
@full_mode_guard
async def clear_cache():
    """Clear the research cache.

    This endpoint is only accessible in FULL mode with safety gates.
    Use with caution - clears all cached research results.
    """
    if not _bootstrap_available or not _orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Research components not available. Check server logs.",
        )

    _orchestrator._cache.clear()
    logger.info("[FULL_MODE] Research cache cleared via API")
    return None


@research_router.post("/full/invalidate", response_model=CacheInvalidateResponse)
@full_mode_guard
async def invalidate_cached_session(request: CacheInvalidateRequest):
    """Invalidate a specific cached session by idea details.

    This endpoint is only accessible in FULL mode with safety gates.

    Args:
        request: CacheInvalidateRequest with idea details

    Returns:
        CacheInvalidateResponse with invalidation result
    """
    if not _bootstrap_available or not _orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Research components not available. Check server logs.",
        )

    try:
        from autopack.research.models.bootstrap_session import \
            generate_idea_hash

        idea_hash = generate_idea_hash(
            request.idea_title,
            request.idea_description,
            request.project_type,
        )

        invalidated = _orchestrator._cache.invalidate(idea_hash)

        return CacheInvalidateResponse(
            invalidated=invalidated,
            message="Cache entry invalidated." if invalidated else "Cache entry not found.",
        )

    except Exception as e:
        logger.error(f"[FULL_MODE] Error invalidating cache: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to invalidate cache: {str(e)}",
        )


# =============================================================================
# Utility endpoint for checking API mode
# =============================================================================


@research_router.get("/mode")
async def get_api_mode():
    """Get the current Research API mode and safety gate configuration.

    This endpoint is always accessible (not guarded) for diagnostics.

    Returns:
        Current mode, endpoint accessibility, and safety gate configuration
    """
    mode = _get_research_api_mode()
    return {
        "mode": mode.value,
        "bootstrap_endpoints_enabled": mode != ResearchAPIMode.DISABLED,
        "full_endpoints_enabled": mode == ResearchAPIMode.FULL,
        "bootstrap_available": _bootstrap_available,
        "safety_gates": {
            "rate_limit_requests_per_minute": SafetyGateConfig.RATE_LIMIT_REQUESTS_PER_MINUTE,
            "max_request_size_bytes": SafetyGateConfig.MAX_REQUEST_SIZE_BYTES,
            "audit_logging_enabled": SafetyGateConfig.AUDIT_LOGGING_ENABLED,
        },
    }


# Export as 'router' for backwards compatibility with __init__.py
router = research_router
