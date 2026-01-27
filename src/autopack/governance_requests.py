"""
Governance Request Handler for BUILD-127 Phase 2.

Enables self-negotiation for protected path modifications:
- Detects protected path violations
- Creates governance requests in database
- Supports auto-approval for low-risk paths
- Enables human approval via API or Telegram
- Provides audit trail across runs

Per BUILD-127 Final Plan:
- Conservative auto-approval defaults (tests/docs only)
- Database persistence for queryability and audit
- Structured error messages via JSON encoding
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# GOVERNANCE REQUEST MODEL
# =============================================================================


@dataclass
class GovernanceRequest:
    """Governance request for protected path modification."""

    request_id: str
    run_id: str
    phase_id: str
    requested_paths: List[str]
    justification: str
    risk_level: str  # "low", "medium", "high", "critical"
    auto_approved: bool
    approved: Optional[bool]  # None = pending, True = approved, False = denied
    approved_by: Optional[str]
    created_at: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "phase_id": self.phase_id,
            "requested_paths": self.requested_paths,
            "justification": self.justification,
            "risk_level": self.risk_level,
            "auto_approved": self.auto_approved,
            "approved": self.approved,
            "approved_by": self.approved_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_db_row(cls, row: Any) -> "GovernanceRequest":
        """Create from database row."""
        return cls(
            request_id=row.request_id,
            run_id=row.run_id,
            phase_id=row.phase_id,
            requested_paths=json.loads(row.requested_paths),
            justification=row.justification or "",
            risk_level=row.risk_level or "medium",
            auto_approved=bool(row.auto_approved),
            approved=row.approved if row.approved is not None else None,
            approved_by=row.approved_by,
            created_at=row.created_at,
        )


# =============================================================================
# AUTO-APPROVAL POLICY (CONSERVATIVE)
# =============================================================================

# Paths that should NEVER be auto-approved (require human review)
NEVER_AUTO_APPROVE = [
    "src/autopack/models.py",
    "alembic/versions/*",
    "src/autopack/main.py",
    "src/autopack/governed_apply.py",
    "src/autopack/autonomous_executor.py",
    "src/autopack/quality_gate.py",
    ".git/*",
    ".env*",
    "config/*",
    ".autonomous_runs/*",
]


def can_auto_approve(
    path: str,
    risk_level: str,
    diff_stats: Optional[Dict[str, int]] = None,
    run_type: str = "project_build",
) -> bool:
    """
    Conservative auto-approval check.

    Auto-approval is only granted for:
    - Low-risk test files (tests/test_*.py)
    - Documentation files (docs/*.md)
    - Small changes (<100 lines) to non-critical files

    All other cases require human approval.

    Args:
        path: File path to check
        risk_level: Risk level from risk scorer ("low", "medium", "high", "critical")
        diff_stats: Optional dict with "lines_changed" count
        run_type: Run type (affects auto-approval policy)

    Returns:
        True if auto-approval is allowed, False otherwise
    """
    # Hard blocks: Never auto-approve certain paths
    for pattern in NEVER_AUTO_APPROVE:
        if fnmatch(path, pattern):
            logger.info(f"[Governance:AutoApproval] BLOCKED (hard block): {path}")
            return False

    # Risk-based blocking
    if risk_level in ["high", "critical"]:
        logger.info(f"[Governance:AutoApproval] BLOCKED (risk={risk_level}): {path}")
        return False

    # Size-based blocking
    if diff_stats and diff_stats.get("lines_changed", 0) > 100:
        logger.info(
            f"[Governance:AutoApproval] BLOCKED (large change "
            f"{diff_stats['lines_changed']} lines): {path}"
        )
        return False

    # Allow: Test files (conservative - only test_*.py pattern)
    if fnmatch(path, "tests/test_*.py"):
        logger.info(f"[Governance:AutoApproval] ALLOWED (test file): {path}")
        return True

    # Allow: Documentation files
    if fnmatch(path, "docs/*.md"):
        logger.info(f"[Governance:AutoApproval] ALLOWED (documentation): {path}")
        return True

    # Default: Require human approval for everything else
    logger.info(f"[Governance:AutoApproval] BLOCKED (default deny): {path}")
    return False


def assess_risk_level(path: str, risk_scorer: Optional[Any] = None) -> str:
    """
    Assess risk level for a path modification.

    Args:
        path: File path to assess
        risk_scorer: Optional RiskScorer instance

    Returns:
        Risk level string: "low", "medium", "high", or "critical"
    """
    # If risk_scorer available, use it
    if risk_scorer:
        try:
            risk_result = risk_scorer.assess_file_risk(path)
            return risk_result.get("risk_level", "medium")
        except Exception as e:
            logger.warning(f"[Governance:Risk] Failed to assess risk for {path}: {e}")

    # Fallback: Pattern-based risk assessment
    # Critical: Core governance and database files
    critical_patterns = [
        "src/autopack/models.py",
        "src/autopack/governed_apply.py",
        "src/autopack/autonomous_executor.py",
        "alembic/versions/*",
    ]
    for pattern in critical_patterns:
        if fnmatch(path, pattern):
            return "critical"

    # High: Other core autopack files
    if fnmatch(path, "src/autopack/*.py"):
        return "high"

    # Low: Test and documentation files
    if fnmatch(path, "tests/*.py") or fnmatch(path, "docs/*.md"):
        return "low"

    # Default: Medium risk
    return "medium"


# =============================================================================
# GOVERNANCE REQUEST OPERATIONS
# =============================================================================


def create_governance_request(
    db_session: Session,
    run_id: str,
    phase_id: str,
    violated_paths: List[str],
    justification: str,
    risk_scorer: Optional[Any] = None,
    diff_stats: Optional[Dict[str, int]] = None,
) -> GovernanceRequest:
    """
    Create a governance request in the database.

    Args:
        db_session: SQLAlchemy session
        run_id: Run ID
        phase_id: Phase ID
        violated_paths: List of protected paths that need approval
        justification: Builder's justification for the changes
        risk_scorer: Optional RiskScorer instance
        diff_stats: Optional diff statistics

    Returns:
        GovernanceRequest instance
    """
    from .models import GovernanceRequest as GovernanceRequestDB

    request_id = str(uuid.uuid4())[:8]

    # Assess overall risk (max of individual path risks)
    path_risks = [assess_risk_level(path, risk_scorer) for path in violated_paths]
    risk_levels_ordered = ["low", "medium", "high", "critical"]
    overall_risk = max(path_risks, key=lambda r: risk_levels_ordered.index(r))

    # Check auto-approval eligibility for ALL paths
    auto_approved = all(
        can_auto_approve(path, assess_risk_level(path, risk_scorer), diff_stats)
        for path in violated_paths
    )

    # Create database record
    db_request = GovernanceRequestDB(
        request_id=request_id,
        run_id=run_id,
        phase_id=phase_id,
        requested_paths=json.dumps(violated_paths),
        justification=justification or "No justification provided",
        risk_level=overall_risk,
        auto_approved=auto_approved,
        approved=True if auto_approved else None,  # Auto-approved → immediately approved
        approved_by="auto" if auto_approved else None,
        created_at=datetime.now(timezone.utc),
    )

    db_session.add(db_request)
    db_session.commit()

    logger.info(
        f"[Governance] Created request {request_id}: "
        f"{len(violated_paths)} paths, risk={overall_risk}, auto_approved={auto_approved}"
    )

    return GovernanceRequest.from_db_row(db_request)


def approve_request(db_session: Session, request_id: str, approved_by: str = "human") -> bool:
    """
    Approve a governance request.

    Args:
        db_session: SQLAlchemy session
        request_id: Request ID to approve
        approved_by: Who approved the request

    Returns:
        True if request was found and approved, False otherwise
    """
    from .models import GovernanceRequest as GovernanceRequestDB

    request = (
        db_session.query(GovernanceRequestDB)
        .filter(GovernanceRequestDB.request_id == request_id)
        .first()
    )

    if not request:
        logger.warning(f"[Governance] Request {request_id} not found")
        return False

    request.approved = True
    request.approved_by = approved_by
    db_session.commit()

    logger.info(f"[Governance] Request {request_id} APPROVED by {approved_by}")
    return True


def deny_request(db_session: Session, request_id: str, denied_by: str = "human") -> bool:
    """
    Deny a governance request.

    Args:
        db_session: SQLAlchemy session
        request_id: Request ID to deny
        denied_by: Who denied the request

    Returns:
        True if request was found and denied, False otherwise
    """
    from .models import GovernanceRequest as GovernanceRequestDB

    request = (
        db_session.query(GovernanceRequestDB)
        .filter(GovernanceRequestDB.request_id == request_id)
        .first()
    )

    if not request:
        logger.warning(f"[Governance] Request {request_id} not found")
        return False

    request.approved = False
    request.approved_by = denied_by
    db_session.commit()

    logger.info(f"[Governance] Request {request_id} DENIED by {denied_by}")
    return True


def get_pending_requests(
    db_session: Session, run_id: Optional[str] = None
) -> List[GovernanceRequest]:
    """
    Get all pending governance requests.

    Args:
        db_session: SQLAlchemy session
        run_id: Optional run_id filter

    Returns:
        List of pending GovernanceRequest instances
    """
    from .models import GovernanceRequest as GovernanceRequestDB

    query = db_session.query(GovernanceRequestDB).filter(GovernanceRequestDB.approved.is_(None))

    if run_id:
        query = query.filter(GovernanceRequestDB.run_id == run_id)

    rows = query.order_by(GovernanceRequestDB.created_at.desc()).all()

    return [GovernanceRequest.from_db_row(row) for row in rows]


# =============================================================================
# STRUCTURED ERROR GENERATION
# =============================================================================


def create_protected_path_error(violated_paths: List[str], justification: str = "") -> str:
    """
    Create structured error message for protected path violation.

    Per BUILD-127 Final Plan: Return JSON-encoded error that can be parsed
    by autonomous_executor.py to trigger governance flow.

    Args:
        violated_paths: List of protected paths
        justification: Builder's justification (extracted from patch)

    Returns:
        JSON-encoded error message string
    """
    error_data = {
        "error_type": "protected_path_violation",
        "violated_paths": violated_paths,
        "justification": justification,
        "requires_approval": True,
    }

    return json.dumps(error_data)
