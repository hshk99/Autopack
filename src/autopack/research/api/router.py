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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from autopack.schema_validation.json_schema import (
    SchemaValidationError,
    validate_intention_anchor_v2,
)
from autopack.sql_sanitizer import SQLSanitizer

from .schemas import (
    AnalysisResultsAggregation,
    BuildVsBuyAnalysisResponse,
    BuildVsBuyDecision,
    ComponentCostDecision,
    ConfidenceMetric,
    ConfidenceReport,
    CostEffectivenessResponse,
    CostEffectivenessSummary,
    CreateResearchSession,
    FollowupTrigger,
    FollowupTriggerResponse,
    ResearchGap,
    ResearchSession,
    ResearchStateResponse,
)

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
       - development: BOOTSTRAP_ONLY

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
    return ResearchAPIMode.BOOTSTRAP_ONLY


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
# Objective Validation (IMP-SCHEMA-008)
# =============================================================================


def validate_objective_format(objective: str, index: int) -> None:
    """Validate the format and content of a single objective.

    Args:
        objective: The objective string to validate
        index: Index of the objective in the list (for error messages)

    Raises:
        ValueError: If the objective format is invalid
    """
    if not isinstance(objective, str):
        raise ValueError(
            f"Objective at index {index}: Must be a string, got {type(objective).__name__}"
        )

    stripped = objective.strip()
    if not stripped:
        raise ValueError(f"Objective at index {index}: Cannot be empty or whitespace only")

    # Check for meaningful content (no single words, must have substance)
    words = stripped.split()
    if len(words) < 2:
        raise ValueError(
            f"Objective at index {index}: Must contain at least 2 words for meaningful content"
        )


def _infer_research_type(title: str, description: str) -> str:
    """Infer the research type from title and description.

    Args:
        title: Research session title
        description: Research session description

    Returns:
        Inferred research type (general, technical, market, competitive, feasibility)
    """
    combined = (title + " " + description).lower()

    # Check for research type keywords in priority order
    # Competitive research is checked first to avoid conflict with market
    if any(kw in combined for kw in ["competitor", "competitive", "comparison", "vs "]):
        return "competitive"

    # Market research
    if any(kw in combined for kw in ["market", "customer", "demand", "growth", "size", "user"]):
        return "market"

    # Feasibility research is checked before technical to avoid conflict with "implement"
    if any(kw in combined for kw in ["feasibility", "viable", "capability", "complexity"]):
        return "feasibility"

    # Technical research (checked last to avoid conflicts)
    if any(
        kw in combined
        for kw in ["technical", "architecture", "implementation", "build", "technology"]
    ):
        return "technical"

    return "general"


def validate_objective_compatibility(
    objectives: List[str], research_type: str = "general"
) -> List[str]:
    """Validate objectives for compatibility with research type.

    Args:
        objectives: List of objective strings to validate
        research_type: Type of research (general, technical, market, competitive, etc.)

    Returns:
        List of validation warnings if any

    Raises:
        ValueError: If objectives are incompatible with research type
    """
    warnings = []

    if not objectives:
        return warnings

    # Basic research type validation
    valid_types = {"general", "technical", "market", "competitive", "feasibility"}
    research_type = research_type.lower() if research_type else "general"

    if research_type not in valid_types:
        logger.warning(
            f"Unknown research type '{research_type}'. Valid types: {valid_types}. "
            f"Defaulting to 'general' validation."
        )
        research_type = "general"

    # Validate based on research type
    if research_type == "technical":
        # Technical research should have specific keywords
        tech_keywords = {"implement", "build", "develop", "architecture", "design", "technical"}
        tech_count = sum(1 for obj in objectives if any(kw in obj.lower() for kw in tech_keywords))
        if tech_count == 0 and len(objectives) > 0:
            warnings.append(
                "Technical research detected but objectives lack technical keywords "
                "(implement, build, develop, architecture, design, technical). "
                "Ensure objectives align with technical research."
            )

    elif research_type == "market":
        # Market research should reference market, customers, size, etc.
        market_keywords = {"market", "customer", "user", "demand", "size", "growth"}
        market_count = sum(
            1 for obj in objectives if any(kw in obj.lower() for kw in market_keywords)
        )
        if market_count == 0 and len(objectives) > 0:
            warnings.append(
                "Market research detected but objectives lack market-related keywords "
                "(market, customer, user, demand, size, growth). "
                "Ensure objectives align with market research."
            )

    elif research_type == "competitive":
        # Competitive research should reference competitors, alternatives, etc.
        competitive_keywords = {"competitor", "alternative", "competitive", "market", "position"}
        competitive_count = sum(
            1 for obj in objectives if any(kw in obj.lower() for kw in competitive_keywords)
        )
        if competitive_count == 0 and len(objectives) > 0:
            warnings.append(
                "Competitive research detected but objectives lack competitive keywords "
                "(competitor, alternative, competitive, market, position). "
                "Ensure objectives align with competitive research."
            )

    return warnings


# =============================================================================
# Anchor Serialization Validation
# =============================================================================


def validate_anchor_serialization(anchor) -> dict:
    """Validate and serialize an IntentionAnchorV2 object to JSON-safe dict.

    Args:
        anchor: IntentionAnchorV2 object to validate and serialize

    Returns:
        JSON-serializable dict representation of the anchor

    Raises:
        HTTPException: If validation fails with detailed error information
    """
    try:
        # Serialize the anchor to dict with JSON-safe mode
        anchor_dict = anchor.model_dump(mode="json")

        # Validate the serialized anchor against the schema
        validate_intention_anchor_v2(anchor_dict)

        logger.debug(
            f"[BOOTSTRAP] Anchor serialization validated successfully "
            f"(format_version={anchor_dict.get('format_version')}, "
            f"project_id={anchor_dict.get('project_id')})"
        )

        return anchor_dict

    except SchemaValidationError as e:
        logger.error(f"[BOOTSTRAP] Anchor serialization validation failed: {e}")
        logger.error(f"[BOOTSTRAP] Validation errors: {e.errors}")
        raise HTTPException(
            status_code=500,
            detail=f"Anchor serialization validation failed: {str(e)}. "
            f"Errors: {'; '.join(e.errors[:3])}",
        )
    except Exception as e:
        logger.error(f"[BOOTSTRAP] Unexpected error during anchor serialization: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to serialize anchor: {str(e)}",
        )


# =============================================================================
# Confidence Report Validation (IMP-SCHEMA-013)
# =============================================================================


def validate_confidence_report(confidence_data: Dict[str, Any]) -> ConfidenceReport:
    """Validate and construct a ConfidenceReport from raw data.

    Validates:
    - All pivot type fields have valid ConfidenceMetric objects
    - Score ranges are 0-100 for all metrics
    - Confidence metrics are internally consistent
    - Report structure matches expected schema

    Args:
        confidence_data: Dictionary containing confidence metrics

    Returns:
        Validated ConfidenceReport object

    Raises:
        HTTPException: If validation fails with detailed error information
    """
    try:
        # Extract individual metrics, allowing None values
        report_dict = {}

        # Process market_research if present
        if "market_research" in confidence_data and confidence_data["market_research"]:
            mr_data = confidence_data["market_research"]
            if isinstance(mr_data, dict):
                report_dict["market_research"] = ConfidenceMetric(
                    score=mr_data.get("score", 0),
                    reasoning=mr_data.get("reasoning", ""),
                )

        # Process competitive_analysis if present
        if "competitive_analysis" in confidence_data and confidence_data["competitive_analysis"]:
            ca_data = confidence_data["competitive_analysis"]
            if isinstance(ca_data, dict):
                report_dict["competitive_analysis"] = ConfidenceMetric(
                    score=ca_data.get("score", 0),
                    reasoning=ca_data.get("reasoning", ""),
                )

        # Process technical_feasibility if present
        if "technical_feasibility" in confidence_data and confidence_data["technical_feasibility"]:
            tf_data = confidence_data["technical_feasibility"]
            if isinstance(tf_data, dict):
                report_dict["technical_feasibility"] = ConfidenceMetric(
                    score=tf_data.get("score", 0),
                    reasoning=tf_data.get("reasoning", ""),
                )

        # Calculate overall confidence as average of populated metrics
        populated_scores = [
            m.score for m in report_dict.values() if isinstance(m, ConfidenceMetric)
        ]
        if populated_scores:
            report_dict["overall_confidence"] = sum(populated_scores) / len(populated_scores)

        # Create the ConfidenceReport
        report = ConfidenceReport(**report_dict)

        # Validate internal consistency
        consistency_warnings = report.validate_consistency()
        if consistency_warnings:
            for warning in consistency_warnings:
                logger.warning(f"[BOOTSTRAP] Confidence report consistency warning: {warning}")

        logger.debug(
            f"[BOOTSTRAP] Confidence report validated successfully "
            f"(overall_confidence={report.overall_confidence:.1f}, "
            f"metrics_count={len(populated_scores)})"
        )

        return report

    except ValueError as e:
        logger.error(f"[BOOTSTRAP] Confidence report validation failed: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Confidence report validation failed: {str(e)}",
        )
    except Exception as e:
        logger.error(f"[BOOTSTRAP] Unexpected error validating confidence report: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to validate confidence report: {str(e)}",
        )


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
    """Response containing draft anchor from completed bootstrap session.

    This response includes the draft IntentionAnchorV2, clarifying questions
    for low-confidence areas, and a structured confidence report with validation.
    """

    session_id: str = Field(..., description="Bootstrap session ID")
    anchor: dict = Field(..., description="Draft IntentionAnchorV2 as dict")
    clarifying_questions: List[str] = Field(
        default_factory=list, description="Questions for low-confidence pivots"
    )
    confidence_report: ConfidenceReport = Field(
        ..., description="Confidence scores per pivot type with validation"
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

        # Validate anchor serialization before transmitting
        # This ensures the anchor meets schema requirements (all required fields, correct format, etc.)
        validated_anchor = validate_anchor_serialization(anchor)

        # Get confidence report data from mappings
        mappings = _anchor_mapper._map_all_pivots(session, None)
        confidence_data = {
            m.pivot_type.value: {
                "score": m.confidence.score,
                "reasoning": m.confidence.reasoning,
            }
            for m in mappings
        }

        # Validate confidence report with typed schema
        # This validates:
        # - Score ranges (0-100)
        # - Metric consistency
        # - Overall coherence of confidence scores
        validated_confidence_report = validate_confidence_report(confidence_data)

        return DraftAnchorResponse(
            session_id=session.session_id,
            anchor=validated_anchor,
            clarifying_questions=questions,
            confidence_report=validated_confidence_report,
        )

    except HTTPException:
        # Re-raise HTTPException from validation
        raise
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
        """Validate objectives list.

        Validates:
        - Minimum of 1 objective when objectives are provided
        - Maximum of 10 objectives
        - Each objective is a non-empty string with 10-500 characters
        - No duplicate objectives

        Returns:
            Cleaned and validated list of objectives

        Raises:
            ValueError: If validation fails
        """
        # Return empty list if not provided
        if not v:
            return []

        # Check maximum count
        if len(v) > 10:
            raise ValueError("Maximum 10 objectives allowed")

        # Validate each objective
        cleaned_objectives = []
        seen_objectives = set()

        for i, obj in enumerate(v):
            # Strip whitespace
            obj_stripped = obj.strip() if isinstance(obj, str) else str(obj).strip()

            # Validate non-empty
            if not obj_stripped:
                raise ValueError(f"Objective at index {i}: Cannot be empty or whitespace only")

            # Validate length
            if len(obj_stripped) < 10:
                raise ValueError(
                    f"Objective at index {i}: Must be at least 10 characters long "
                    f"(got {len(obj_stripped)})"
                )

            if len(obj_stripped) > 500:
                raise ValueError(
                    f"Objective at index {i}: Must not exceed 500 characters "
                    f"(got {len(obj_stripped)})"
                )

            # Check for duplicates (case-insensitive, whitespace-normalized)
            # Normalize whitespace for duplicate detection: convert multiple spaces to single space
            obj_normalized = " ".join(obj_stripped.split()).lower()
            if obj_normalized in seen_objectives:
                raise ValueError(
                    f"Objective at index {i}: Duplicate objective detected. "
                    f"Each objective must be unique"
                )

            seen_objectives.add(obj_normalized)
            cleaned_objectives.append(obj_stripped)

        return cleaned_objectives


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
    - Objective field validation (format, structure, and compatibility)

    Args:
        request: FullSessionRequest with title, description, and objectives

    Returns:
        FullSessionResponse with session_id and status

    Raises:
        HTTPException: If objectives fail validation (status 400)
        HTTPException: If session creation fails (status 500)
    """
    if not _bootstrap_available or not _orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Research components not available. Check server logs.",
        )

    # Validate objective field structure
    try:
        # Check if objectives are provided
        if not request.objectives:
            logger.warning(
                f"[FULL_MODE] Session start attempt with no objectives: title='{request.title}'"
            )
            raise HTTPException(
                status_code=400,
                detail="At least one objective is required for a research session. "
                "Objectives help guide the research direction and focus.",
            )

        # Validate each objective format
        for i, objective in enumerate(request.objectives):
            try:
                validate_objective_format(objective, i)
            except ValueError as e:
                logger.warning(f"[FULL_MODE] Objective format validation failed: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Objective validation failed: {str(e)}",
                )

        # Check objective compatibility with session context
        # (inferred from title and description)
        research_type = _infer_research_type(request.title, request.description)
        compatibility_warnings = validate_objective_compatibility(request.objectives, research_type)

        # Log warnings but don't fail on them
        for warning in compatibility_warnings:
            logger.info(f"[FULL_MODE] Objective compatibility warning: {warning}")

        # Log successful objective validation
        logger.info(
            f"[FULL_MODE] Objectives validated successfully: "
            f"count={len(request.objectives)}, "
            f"research_type={research_type}"
        )

    except HTTPException:
        # Re-raise HTTP exceptions (validation errors)
        raise
    except Exception as e:
        logger.error(f"[FULL_MODE] Unexpected error during objective validation: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to validate objectives: {str(e)}",
        )

    # Create the research session
    try:
        session_id = _orchestrator.start_session(
            intent_title=request.title,
            intent_description=request.description,
            intent_objectives=request.objectives,
        )

        logger.info(
            f"[FULL_MODE] Full research session created: "
            f"session_id={session_id}, "
            f"title='{request.title[:50]}...', "
            f"objectives={len(request.objectives)}"
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
        from autopack.research.models.bootstrap_session import generate_idea_hash

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
# Analysis Results Endpoints (accessible only in FULL mode with safety gates)
# =============================================================================


@research_router.get(
    "/full/session/{session_id}/analysis/cost-effectiveness",
    response_model=CostEffectivenessResponse,
)
@full_mode_guard
async def get_cost_effectiveness_analysis(
    session_id: str, include_optimization_roadmap: bool = True
):
    """Get cost effectiveness analysis for a research session.

    This endpoint is only accessible in FULL mode with safety gates.
    Returns comprehensive cost projections, component decisions, and optimization strategies.

    Args:
        session_id: The research session ID
        include_optimization_roadmap: Include optimization strategies (default: true)

    Returns:
        CostEffectivenessResponse with cost analysis results
    """
    if not _bootstrap_available or not _orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Research components not available. Check server logs.",
        )

    # Validate session_id
    session_id = SQLSanitizer.validate_parameter(session_id)

    # Get bootstrap session by session_id
    session = _orchestrator.get_bootstrap_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Bootstrap session {session_id} not found",
        )

    if not session.is_complete():
        raise HTTPException(
            status_code=400,
            detail="Bootstrap session is not complete. Cannot run analysis.",
        )

    try:
        # Run cost effectiveness analysis
        analysis_result = _orchestrator.run_cost_effectiveness_analysis(session)

        # Extract executive summary
        executive_summary = CostEffectivenessSummary(
            total_year_1_cost=analysis_result.get("executive_summary", {}).get(
                "total_year_1_cost", 0
            ),
            total_year_3_cost=analysis_result.get("executive_summary", {}).get(
                "total_year_3_cost", 0
            ),
            total_year_5_cost=analysis_result.get("executive_summary", {}).get(
                "total_year_5_cost", 0
            ),
            primary_cost_drivers=analysis_result.get("executive_summary", {}).get(
                "primary_cost_drivers", []
            ),
            key_recommendations=analysis_result.get("executive_summary", {}).get(
                "key_recommendations", []
            ),
            cost_confidence=analysis_result.get("executive_summary", {}).get(
                "cost_confidence", "medium"
            ),
        )

        # Extract component analysis
        component_analysis = []
        for comp in analysis_result.get("component_analysis", []):
            component_analysis.append(
                ComponentCostDecision(
                    component=comp.get("component", ""),
                    decision=comp.get("decision", ""),
                    service=comp.get("service", ""),
                    year_1_cost=comp.get("year_1_cost", 0),
                    year_5_cost=comp.get("year_5_cost", 0),
                    vs_build_savings=comp.get("vs_build_savings", 0),
                    rationale=comp.get("rationale", ""),
                )
            )

        # Build response
        cost_optimization_roadmap = (
            analysis_result.get("cost_optimization_roadmap", [])
            if include_optimization_roadmap
            else []
        )

        response = CostEffectivenessResponse(
            session_id=session_id,
            executive_summary=executive_summary,
            component_analysis=component_analysis,
            ai_token_projection=analysis_result.get("ai_token_projection"),
            infrastructure_projection=analysis_result.get("infrastructure_projection"),
            development_costs=analysis_result.get("development_costs"),
            total_cost_of_ownership=analysis_result.get("total_cost_of_ownership"),
            cost_optimization_roadmap=cost_optimization_roadmap,
            risk_adjusted_costs=analysis_result.get("risk_adjusted_costs"),
            break_even_analysis=analysis_result.get("break_even_analysis"),
            vendor_lock_in_assessment=analysis_result.get("vendor_lock_in_assessment", []),
            generated_at=datetime.utcnow().isoformat() + "Z",
        )

        _audit_log(
            "get_cost_effectiveness_analysis",
            "analysis_complete",
            {"session_id": session_id},
        )

        return response

    except Exception as e:
        logger.error(f"[FULL_MODE] Error getting cost effectiveness analysis: {e}")
        _audit_log(
            "get_cost_effectiveness_analysis",
            "error",
            {"session_id": session_id, "error": str(e)},
            success=False,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get cost effectiveness analysis: {str(e)}",
        )


@research_router.get(
    "/full/session/{session_id}/analysis/build-vs-buy",
    response_model=BuildVsBuyAnalysisResponse,
)
@full_mode_guard
async def get_build_vs_buy_analysis(session_id: str, include_risks: bool = True):
    """Get build vs buy analysis for a research session.

    This endpoint is only accessible in FULL mode with safety gates.
    Returns component-level decisions and strategic recommendations.

    Args:
        session_id: The research session ID
        include_risks: Include risk assessment details (default: true)

    Returns:
        BuildVsBuyAnalysisResponse with build vs buy decisions
    """
    if not _bootstrap_available or not _orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Research components not available. Check server logs.",
        )

    # Validate session_id
    session_id = SQLSanitizer.validate_parameter(session_id)

    # Get bootstrap session
    session = _orchestrator.get_bootstrap_session(session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail=f"Bootstrap session {session_id} not found",
        )

    if not session.is_complete():
        raise HTTPException(
            status_code=400,
            detail="Bootstrap session is not complete. Cannot run analysis.",
        )

    try:
        # Get build vs buy analysis from orchestrator
        analysis_result = getattr(_orchestrator, "_build_vs_buy_results", {})

        # If not cached, try to generate from session data
        if not analysis_result:
            # Extract component decisions from cost analysis
            cost_analysis = _orchestrator.run_cost_effectiveness_analysis(session)
            analysis_result = {}
            decisions = []

            for comp in cost_analysis.get("component_analysis", []):
                decision = BuildVsBuyDecision(
                    component=comp.get("component", ""),
                    recommendation=comp.get("decision", "BUILD").upper(),
                    confidence=0.75,  # Default confidence
                    build_cost={
                        "initial_cost": comp.get("year_1_cost", 0),
                        "monthly_recurring": 0,
                        "year_1_total": comp.get("year_1_cost", 0),
                    },
                    buy_cost={
                        "initial_cost": 0,
                        "monthly_recurring": 0,
                        "year_1_total": max(
                            0, comp.get("year_1_cost", 0) - comp.get("vs_build_savings", 0)
                        ),
                    },
                    build_time_weeks=8,  # Default estimate
                    buy_integration_time_weeks=2,
                    risks=comp.get("risks", []) if include_risks else [],
                    rationale=comp.get("rationale", ""),
                    strategic_importance="supporting",
                    key_factors=[comp.get("decision", "")],
                )
                decisions.append(decision)

            analysis_result["decisions"] = decisions

        response = BuildVsBuyAnalysisResponse(
            session_id=session_id,
            decisions=analysis_result.get("decisions", []),
            overall_recommendation=analysis_result.get("overall_recommendation", "HYBRID"),
            total_build_cost=analysis_result.get("total_build_cost"),
            total_buy_cost=analysis_result.get("total_buy_cost"),
            generated_at=datetime.utcnow().isoformat() + "Z",
        )

        _audit_log(
            "get_build_vs_buy_analysis",
            "analysis_complete",
            {"session_id": session_id},
        )

        return response

    except Exception as e:
        logger.error(f"[FULL_MODE] Error getting build vs buy analysis: {e}")
        _audit_log(
            "get_build_vs_buy_analysis",
            "error",
            {"session_id": session_id, "error": str(e)},
            success=False,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get build vs buy analysis: {str(e)}",
        )


@research_router.get(
    "/full/session/{session_id}/analysis/followup-triggers",
    response_model=FollowupTriggerResponse,
)
@full_mode_guard
async def get_followup_triggers(
    session_id: str, priority_filter: Optional[str] = None, limit: int = 100
):
    """Get identified followup research triggers for a session.

    This endpoint is only accessible in FULL mode with safety gates.
    Returns gaps and uncertainties that require follow-up research.

    Args:
        session_id: The research session ID
        priority_filter: Optional filter for specific priority (critical, high, medium, low)
        limit: Maximum number of triggers to return (default: 100)

    Returns:
        FollowupTriggerResponse with identified research triggers
    """
    if not _bootstrap_available or not _orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Research components not available. Check server logs.",
        )

    # Validate session_id
    session_id = SQLSanitizer.validate_parameter(session_id)

    # Validate priority filter
    valid_priorities = {"critical", "high", "medium", "low"}
    if priority_filter and priority_filter.lower() not in valid_priorities:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority filter. Valid values: {', '.join(valid_priorities)}",
        )

    # Validate limit
    if limit < 1 or limit > 1000:
        limit = 100

    try:
        # Get bootstrap session
        session = _orchestrator.get_bootstrap_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Bootstrap session {session_id} not found",
            )

        if not session.is_complete():
            raise HTTPException(
                status_code=400,
                detail="Bootstrap session is not complete. Cannot run analysis.",
            )

        # Run trigger analysis
        trigger_result = _orchestrator.analyze_followup_triggers(session)

        # Process triggers
        triggers = []
        total_estimated_time = 0

        for trigger_data in trigger_result.get("triggers", []):
            # Apply priority filter if provided
            if priority_filter:
                if trigger_data.get("priority", "").lower() != priority_filter.lower():
                    continue

            trigger = FollowupTrigger(
                trigger_id=trigger_data.get("trigger_id", ""),
                trigger_type=trigger_data.get("type", "gap"),
                priority=trigger_data.get("priority", "medium"),
                reason=trigger_data.get("reason", ""),
                source_finding=trigger_data.get("source_finding", ""),
                research_plan=trigger_data.get("research_plan"),
                created_at=trigger_data.get("created_at", datetime.utcnow().isoformat() + "Z"),
                addressed=trigger_data.get("addressed", False),
                callback_results=trigger_data.get("callback_results", []),
            )
            triggers.append(trigger)

            # Add to estimated time
            if research_plan := trigger_data.get("research_plan"):
                total_estimated_time += research_plan.get("estimated_time_minutes", 15)

            # Respect limit
            if len(triggers) >= limit:
                break

        response = FollowupTriggerResponse(
            session_id=session_id,
            triggers=triggers,
            should_research=trigger_result.get("should_research", len(triggers) > 0),
            triggers_selected=len(triggers),
            total_estimated_time=total_estimated_time,
            generated_at=datetime.utcnow().isoformat() + "Z",
        )

        _audit_log(
            "get_followup_triggers",
            "analysis_complete",
            {"session_id": session_id, "trigger_count": len(triggers)},
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FULL_MODE] Error getting followup triggers: {e}")
        _audit_log(
            "get_followup_triggers",
            "error",
            {"session_id": session_id, "error": str(e)},
            success=False,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get followup triggers: {str(e)}",
        )


@research_router.get(
    "/full/session/{session_id}/analysis/research-state",
    response_model=ResearchStateResponse,
)
@full_mode_guard
async def get_research_state(session_id: str, include_details: bool = True):
    """Get research state and identified gaps for a session.

    This endpoint is only accessible in FULL mode with safety gates.
    Returns current research coverage, identified gaps, and research depth.

    Args:
        session_id: The research session ID
        include_details: Include detailed gap information (default: true)

    Returns:
        ResearchStateResponse with research state and gaps
    """
    if not _bootstrap_available or not _orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Research components not available. Check server logs.",
        )

    # Validate session_id
    session_id = SQLSanitizer.validate_parameter(session_id)

    try:
        # Get bootstrap session
        session = _orchestrator.get_bootstrap_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Bootstrap session {session_id} not found",
            )

        if not session.is_complete():
            raise HTTPException(
                status_code=400,
                detail="Bootstrap session is not complete. Cannot get research state.",
            )

        # Get research state
        state_summary = _orchestrator.get_research_state_summary(session)
        gaps = _orchestrator.get_research_gaps(session) if include_details else []

        # Process gaps
        gap_objects = []
        critical_count = 0

        for gap_data in gaps:
            gap = ResearchGap(
                gap_id=gap_data.get("gap_id", ""),
                gap_type=gap_data.get("gap_type", "coverage"),
                category=gap_data.get("category", "general"),
                description=gap_data.get("description", ""),
                priority=gap_data.get("priority", "medium"),
                suggested_queries=gap_data.get("suggested_queries", []),
                identified_at=gap_data.get("identified_at", datetime.utcnow().isoformat() + "Z"),
                addressed_at=gap_data.get("addressed_at"),
                status=gap_data.get("status", "open"),
            )
            gap_objects.append(gap)

            if gap.priority == "critical":
                critical_count += 1

        response = ResearchStateResponse(
            session_id=session_id,
            gaps=gap_objects,
            gap_count=len(gap_objects),
            critical_gaps=critical_count,
            coverage_metrics=state_summary.get("coverage_metrics", {}),
            completed_queries=state_summary.get("completed_queries", 0),
            discovered_sources=state_summary.get("discovered_sources", 0),
            research_depth=state_summary.get("research_depth", "MEDIUM"),
            generated_at=datetime.utcnow().isoformat() + "Z",
        )

        _audit_log(
            "get_research_state",
            "analysis_complete",
            {"session_id": session_id, "gap_count": len(gap_objects)},
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FULL_MODE] Error getting research state: {e}")
        _audit_log(
            "get_research_state",
            "error",
            {"session_id": session_id, "error": str(e)},
            success=False,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get research state: {str(e)}",
        )


@research_router.get(
    "/full/session/{session_id}/analysis",
    response_model=AnalysisResultsAggregation,
)
@full_mode_guard
async def get_all_analysis_results(
    session_id: str,
    include_cost_effectiveness: bool = True,
    include_build_vs_buy: bool = True,
    include_followup_triggers: bool = True,
    include_research_state: bool = True,
    trigger_limit: int = 50,
):
    """Get aggregated analysis results for a research session.

    This endpoint combines all analysis results (cost effectiveness, build vs buy,
    followup triggers, and research state) into a single response.

    This endpoint is only accessible in FULL mode with safety gates.

    Args:
        session_id: The research session ID
        include_cost_effectiveness: Include cost effectiveness analysis (default: true)
        include_build_vs_buy: Include build vs buy analysis (default: true)
        include_followup_triggers: Include followup triggers (default: true)
        include_research_state: Include research state (default: true)
        trigger_limit: Maximum number of triggers to include (default: 50)

    Returns:
        AnalysisResultsAggregation with all requested analysis results
    """
    if not _bootstrap_available or not _orchestrator:
        raise HTTPException(
            status_code=503,
            detail="Research components not available. Check server logs.",
        )

    # Validate session_id
    session_id = SQLSanitizer.validate_parameter(session_id)

    # Validate trigger_limit
    if trigger_limit < 1 or trigger_limit > 1000:
        trigger_limit = 50

    try:
        # Get bootstrap session
        session = _orchestrator.get_bootstrap_session(session_id)
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Bootstrap session {session_id} not found",
            )

        if not session.is_complete():
            raise HTTPException(
                status_code=400,
                detail="Bootstrap session is not complete. Cannot run analysis.",
            )

        # Collect all analysis results
        cost_effectiveness_result = None
        build_vs_buy_result = None
        followup_triggers_result = None
        research_state_result = None

        # Get cost effectiveness if requested
        if include_cost_effectiveness:
            try:
                analysis_result = _orchestrator.run_cost_effectiveness_analysis(session)
                executive_summary = CostEffectivenessSummary(
                    total_year_1_cost=analysis_result.get("executive_summary", {}).get(
                        "total_year_1_cost", 0
                    ),
                    total_year_3_cost=analysis_result.get("executive_summary", {}).get(
                        "total_year_3_cost", 0
                    ),
                    total_year_5_cost=analysis_result.get("executive_summary", {}).get(
                        "total_year_5_cost", 0
                    ),
                    primary_cost_drivers=analysis_result.get("executive_summary", {}).get(
                        "primary_cost_drivers", []
                    ),
                    key_recommendations=analysis_result.get("executive_summary", {}).get(
                        "key_recommendations", []
                    ),
                    cost_confidence=analysis_result.get("executive_summary", {}).get(
                        "cost_confidence", "medium"
                    ),
                )

                component_analysis = []
                for comp in analysis_result.get("component_analysis", []):
                    component_analysis.append(
                        ComponentCostDecision(
                            component=comp.get("component", ""),
                            decision=comp.get("decision", ""),
                            service=comp.get("service", ""),
                            year_1_cost=comp.get("year_1_cost", 0),
                            year_5_cost=comp.get("year_5_cost", 0),
                            vs_build_savings=comp.get("vs_build_savings", 0),
                            rationale=comp.get("rationale", ""),
                        )
                    )

                cost_effectiveness_result = CostEffectivenessResponse(
                    session_id=session_id,
                    executive_summary=executive_summary,
                    component_analysis=component_analysis,
                    ai_token_projection=analysis_result.get("ai_token_projection"),
                    infrastructure_projection=analysis_result.get("infrastructure_projection"),
                    development_costs=analysis_result.get("development_costs"),
                    total_cost_of_ownership=analysis_result.get("total_cost_of_ownership"),
                    cost_optimization_roadmap=analysis_result.get("cost_optimization_roadmap", []),
                    risk_adjusted_costs=analysis_result.get("risk_adjusted_costs"),
                    break_even_analysis=analysis_result.get("break_even_analysis"),
                    vendor_lock_in_assessment=analysis_result.get("vendor_lock_in_assessment", []),
                    generated_at=datetime.utcnow().isoformat() + "Z",
                )
            except Exception as e:
                logger.warning(f"Failed to get cost effectiveness analysis: {e}")

        # Get build vs buy if requested
        if include_build_vs_buy:
            try:
                cost_analysis = _orchestrator.run_cost_effectiveness_analysis(session)
                decisions = []

                for comp in cost_analysis.get("component_analysis", []):
                    decision = BuildVsBuyDecision(
                        component=comp.get("component", ""),
                        recommendation=comp.get("decision", "BUILD").upper(),
                        confidence=0.75,
                        build_cost={
                            "initial_cost": comp.get("year_1_cost", 0),
                            "monthly_recurring": 0,
                            "year_1_total": comp.get("year_1_cost", 0),
                        },
                        buy_cost={
                            "initial_cost": 0,
                            "monthly_recurring": 0,
                            "year_1_total": max(
                                0, comp.get("year_1_cost", 0) - comp.get("vs_build_savings", 0)
                            ),
                        },
                        build_time_weeks=8,
                        buy_integration_time_weeks=2,
                        risks=comp.get("risks", []),
                        rationale=comp.get("rationale", ""),
                        strategic_importance="supporting",
                        key_factors=[comp.get("decision", "")],
                    )
                    decisions.append(decision)

                build_vs_buy_result = BuildVsBuyAnalysisResponse(
                    session_id=session_id,
                    decisions=decisions,
                    overall_recommendation="HYBRID",
                    generated_at=datetime.utcnow().isoformat() + "Z",
                )
            except Exception as e:
                logger.warning(f"Failed to get build vs buy analysis: {e}")

        # Get followup triggers if requested
        if include_followup_triggers:
            try:
                trigger_result = _orchestrator.analyze_followup_triggers(session)
                triggers = []
                total_estimated_time = 0

                for trigger_data in trigger_result.get("triggers", [])[:trigger_limit]:
                    trigger = FollowupTrigger(
                        trigger_id=trigger_data.get("trigger_id", ""),
                        trigger_type=trigger_data.get("type", "gap"),
                        priority=trigger_data.get("priority", "medium"),
                        reason=trigger_data.get("reason", ""),
                        source_finding=trigger_data.get("source_finding", ""),
                        research_plan=trigger_data.get("research_plan"),
                        created_at=trigger_data.get(
                            "created_at", datetime.utcnow().isoformat() + "Z"
                        ),
                        addressed=trigger_data.get("addressed", False),
                        callback_results=trigger_data.get("callback_results", []),
                    )
                    triggers.append(trigger)

                    if research_plan := trigger_data.get("research_plan"):
                        total_estimated_time += research_plan.get("estimated_time_minutes", 15)

                followup_triggers_result = FollowupTriggerResponse(
                    session_id=session_id,
                    triggers=triggers,
                    should_research=trigger_result.get("should_research", len(triggers) > 0),
                    triggers_selected=len(triggers),
                    total_estimated_time=total_estimated_time,
                    generated_at=datetime.utcnow().isoformat() + "Z",
                )
            except Exception as e:
                logger.warning(f"Failed to get followup triggers: {e}")

        # Get research state if requested
        if include_research_state:
            try:
                state_summary = _orchestrator.get_research_state_summary(session)
                gaps = _orchestrator.get_research_gaps(session)

                gap_objects = []
                critical_count = 0

                for gap_data in gaps:
                    gap = ResearchGap(
                        gap_id=gap_data.get("gap_id", ""),
                        gap_type=gap_data.get("gap_type", "coverage"),
                        category=gap_data.get("category", "general"),
                        description=gap_data.get("description", ""),
                        priority=gap_data.get("priority", "medium"),
                        suggested_queries=gap_data.get("suggested_queries", []),
                        identified_at=gap_data.get(
                            "identified_at", datetime.utcnow().isoformat() + "Z"
                        ),
                        addressed_at=gap_data.get("addressed_at"),
                        status=gap_data.get("status", "open"),
                    )
                    gap_objects.append(gap)

                    if gap.priority == "critical":
                        critical_count += 1

                research_state_result = ResearchStateResponse(
                    session_id=session_id,
                    gaps=gap_objects,
                    gap_count=len(gap_objects),
                    critical_gaps=critical_count,
                    coverage_metrics=state_summary.get("coverage_metrics", {}),
                    completed_queries=state_summary.get("completed_queries", 0),
                    discovered_sources=state_summary.get("discovered_sources", 0),
                    research_depth=state_summary.get("research_depth", "MEDIUM"),
                    generated_at=datetime.utcnow().isoformat() + "Z",
                )
            except Exception as e:
                logger.warning(f"Failed to get research state: {e}")

        response = AnalysisResultsAggregation(
            session_id=session_id,
            cost_effectiveness=cost_effectiveness_result,
            build_vs_buy=build_vs_buy_result,
            followup_triggers=followup_triggers_result,
            research_state=research_state_result,
            generated_at=datetime.utcnow().isoformat() + "Z",
        )

        _audit_log(
            "get_all_analysis_results",
            "analysis_complete",
            {
                "session_id": session_id,
                "include_cost_effectiveness": include_cost_effectiveness,
                "include_build_vs_buy": include_build_vs_buy,
                "include_followup_triggers": include_followup_triggers,
                "include_research_state": include_research_state,
            },
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FULL_MODE] Error getting analysis results: {e}")
        _audit_log(
            "get_all_analysis_results",
            "error",
            {"session_id": session_id, "error": str(e)},
            success=False,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get analysis results: {str(e)}",
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
