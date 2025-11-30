"""FastAPI application for Autopack Supervisor (Chunks A, B, C, D implementation)"""

import os
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from . import dashboard_schemas, models, schemas
from .builder_schemas import AuditorRequest, AuditorResult, BuilderResult
from .database import get_db, init_db
from .file_layout import RunFileLayout
from .governed_apply import GovernedApplyPath
from .issue_tracker import IssueTracker
from .strategy_engine import StrategyEngine

# Security: API Key authentication
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(api_key: str = Security(API_KEY_HEADER)):
    """Verify API key for protected endpoints"""
    expected_key = os.getenv("AUTOPACK_API_KEY")

    # Skip auth in testing mode
    if os.getenv("TESTING") == "1":
        return "test-key"

    # Skip auth if no key configured (for initial setup)
    if not expected_key:
        return None

    if not api_key or api_key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing API key. Set X-API-Key header."
        )
    return api_key

# Rate limiting
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Autopack Supervisor",
    description="Supervisor/orchestrator implementing the v7 autonomous build playbook",
    version="0.1.0",
)

# Add rate limiting to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Global exception handler for debugging
import logging
from fastapi.responses import JSONResponse
from fastapi import status

logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    import traceback
    tb = traceback.format_exc()
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": str(exc),
            "type": type(exc).__name__,
            "traceback": tb if os.getenv("DEBUG") == "1" else None
        },
    )


@app.on_event("startup")
def startup_event():
    """Initialize database on startup (skipped during testing)"""
    import os

    # Skip DB init during testing (tests use their own DB setup)
    if os.getenv("TESTING") != "1":
        init_db()


@app.get("/")
def read_root():
    """Root endpoint"""
    return {
        "service": "Autopack Supervisor",
        "version": "0.1.0",
        "description": "v7 autonomous build playbook orchestrator",
    }


@app.post("/runs/start", response_model=schemas.RunResponse, status_code=201, dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")  # Max 10 runs per minute per IP
def start_run(request_data: schemas.RunStartRequest, request: Request, db: Session = Depends(get_db)):
    """
    Start a new autonomous build run with tiers and phases.

    Per §3 of v7 playbook:
    1. Create run record
    2. Create tier records
    3. Create phase records
    4. Initialize file layout under .autonomous_runs/{run_id}/
    """
    # Check if run already exists
    existing_run = db.query(models.Run).filter(models.Run.id == request_data.run.run_id).first()
    if existing_run:
        raise HTTPException(status_code=400, detail=f"Run {request_data.run.run_id} already exists")

    # Create run
    run = models.Run(
        id=request_data.run.run_id,
        state=models.RunState.RUN_CREATED,
        safety_profile=request_data.run.safety_profile,
        run_scope=request_data.run.run_scope,
        token_cap=request_data.run.token_cap or 5_000_000,
        max_phases=request_data.run.max_phases or 25,
        max_duration_minutes=request_data.run.max_duration_minutes or 120,
        max_minor_issues_total=None,  # Will be computed based on phase count
        started_at=datetime.utcnow(),
    )

    # Compute max_minor_issues_total (phases_in_run * 3 per §9.1)
    if request_data.phases:
        run.max_minor_issues_total = len(request_data.phases) * 3

    db.add(run)
    db.flush()

    # Create tiers
    tier_map = {}  # tier_id -> Tier model
    for tier_create in request_data.tiers:
        tier = models.Tier(
            tier_id=tier_create.tier_id,
            run_id=run.id,
            tier_index=tier_create.tier_index,
            name=tier_create.name,
            description=tier_create.description,
            state=models.TierState.PENDING,
        )
        db.add(tier)
        db.flush()
        tier_map[tier_create.tier_id] = tier

    # Create phases
    for phase_create in request_data.phases:
        if phase_create.tier_id not in tier_map:
            raise HTTPException(
                status_code=400,
                detail=f"Phase {phase_create.phase_id} references unknown tier {phase_create.tier_id}",
            )

        phase = models.Phase(
            phase_id=phase_create.phase_id,
            run_id=run.id,
            tier_id=tier_map[phase_create.tier_id].id,
            phase_index=phase_create.phase_index,
            name=phase_create.name,
            description=phase_create.description,
            task_category=phase_create.task_category,
            complexity=phase_create.complexity,
            builder_mode=phase_create.builder_mode,
            state=models.PhaseState.QUEUED,
        )
        db.add(phase)

    db.commit()
    db.refresh(run)

    # Compile strategy for this run (Chunk C integration)
    strategy_engine = StrategyEngine(project_id="Autopack")
    strategy = strategy_engine.compile_strategy(
        run_id=run.id,
        phases=[
            {
                "phase_id": p.phase_id,
                "task_category": p.task_category,
                "complexity": p.complexity,
            }
            for p in run.phases
        ],
        tiers=[{"tier_id": t.tier_id} for t in run.tiers],
        safety_profile_override=run.safety_profile,
    )

    # Initialize file layout
    file_layout = RunFileLayout(run.id)
    file_layout.ensure_directories()
    file_layout.write_run_summary(
        run_id=run.id,
        state=run.state.value,
        safety_profile=run.safety_profile,
        run_scope=run.run_scope,
        created_at=run.created_at.isoformat(),
        tier_count=len(request_data.tiers),
        phase_count=len(request_data.phases),
    )

    # Write tier summaries
    for tier in run.tiers:
        phase_count = len([p for p in run.phases if p.tier_id == tier.id])
        file_layout.write_tier_summary(
            tier_index=tier.tier_index,
            tier_id=tier.tier_id,
            tier_name=tier.name,
            state=tier.state.value,
            phase_count=phase_count,
        )

    # Write phase summaries
    for phase in run.phases:
        file_layout.write_phase_summary(
            phase_index=phase.phase_index,
            phase_id=phase.phase_id,
            phase_name=phase.name,
            state=phase.state.value,
            task_category=phase.task_category,
            complexity=phase.complexity,
        )

    # Eagerly load relationships to avoid DetachedInstanceError during response serialization
    run_with_relationships = (
        db.query(models.Run)
        .filter(models.Run.id == run.id)
        .options(
            joinedload(models.Run.tiers).joinedload(models.Tier.phases),
            joinedload(models.Run.phases)
        )
        .first()
    )

    return run_with_relationships


@app.get("/runs/{run_id}", response_model=schemas.RunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    """
    Get run details including all tiers and phases.

    Per §3 of v7 playbook, this provides inspection of run state.
    """
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return run


@app.post("/runs/{run_id}/phases/{phase_id}/update_status")
def update_phase_status(
    run_id: str,
    phase_id: str,
    update: schemas.PhaseStatusUpdate,
    db: Session = Depends(get_db),
):
    """
    Update phase status.

    Per §3 of v7 playbook, this is used to advance phases through the state machine.
    In Chunk A, this is a basic update endpoint. Full state machine logic will be
    added in later chunks.
    """
    # Find the phase
    phase = (
        db.query(models.Phase)
        .filter(models.Phase.run_id == run_id, models.Phase.phase_id == phase_id)
        .first()
    )

    if not phase:
        raise HTTPException(status_code=404, detail=f"Phase {phase_id} not found in run {run_id}")

    # Update state
    try:
        phase.state = models.PhaseState(update.state)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid phase state: {update.state}")

    # Update optional fields
    if update.builder_attempts is not None:
        phase.builder_attempts = update.builder_attempts
    if update.tokens_used is not None:
        phase.tokens_used = update.tokens_used
    if update.minor_issues_count is not None:
        phase.minor_issues_count = update.minor_issues_count
    if update.major_issues_count is not None:
        phase.major_issues_count = update.major_issues_count

    # Phase 2: Quality gate fields
    if update.quality_level is not None:
        phase.quality_level = update.quality_level
    if update.quality_blocked is not None:
        phase.quality_blocked = update.quality_blocked

    phase.updated_at = datetime.utcnow()

    # Update phase summary file (optional - don't fail if file doesn't exist)
    try:
        file_layout = RunFileLayout(run_id)
        file_layout.write_phase_summary(
            phase_index=phase.phase_index,
            phase_id=phase.phase_id,
            phase_name=phase.name,
            state=phase.state.value,
            task_category=phase.task_category,
            complexity=phase.complexity,
        )
    except FileNotFoundError:
        # Phase summary file doesn't exist yet - this is OK for escalation/force-fail scenarios
        pass

    db.commit()
    db.refresh(phase)

    return {"message": f"Phase {phase_id} updated to state {phase.state.value}", "phase": phase}


@app.post("/runs/{run_id}/phases/{phase_id}/record_issue")
def record_phase_issue(
    run_id: str,
    phase_id: str,
    issue_key: str,
    severity: str,
    source: str,
    category: str,
    task_category: Optional[str] = None,
    complexity: Optional[str] = None,
    evidence_refs: Optional[List[str]] = None,
    db: Session = Depends(get_db),
):
    """
    Record an issue for a phase (Chunk B implementation).

    Per §5 of v7 playbook, this records the issue at three levels:
    1. Phase-level issue file
    2. Run-level issue index (de-duplication)
    3. Project-level issue backlog (aging)
    """
    # Find the phase to get tier_id and phase_index
    phase = (
        db.query(models.Phase)
        .filter(models.Phase.run_id == run_id, models.Phase.phase_id == phase_id)
        .first()
    )

    if not phase:
        raise HTTPException(status_code=404, detail=f"Phase {phase_id} not found in run {run_id}")

    # Get tier
    tier = db.query(models.Tier).filter(models.Tier.id == phase.tier_id).first()
    if not tier:
        raise HTTPException(status_code=404, detail=f"Tier not found for phase {phase_id}")

    # Record issue at all levels
    tracker = IssueTracker(run_id=run_id)
    phase_file, run_index, project_backlog = tracker.record_issue(
        phase_index=phase.phase_index,
        phase_id=phase_id,
        tier_id=tier.tier_id,
        issue_key=issue_key,
        severity=severity,
        source=source,
        category=category,
        task_category=task_category,
        complexity=complexity,
        evidence_refs=evidence_refs,
    )

    # Update phase DB record
    phase.minor_issues_count = phase_file.minor_issue_count
    phase.major_issues_count = phase_file.major_issue_count
    phase.issue_state = phase_file.issue_state

    # Update tier counts (aggregate from all phases)
    tier_phases = db.query(models.Phase).filter(models.Phase.tier_id == tier.id).all()
    tier.minor_issues_count = sum(p.minor_issues_count for p in tier_phases)
    tier.major_issues_count = sum(p.major_issues_count for p in tier_phases)

    # Update run counts (aggregate from all phases)
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    all_phases = db.query(models.Phase).filter(models.Phase.run_id == run_id).all()
    run.minor_issues_count = sum(p.minor_issues_count for p in all_phases)
    run.major_issues_count = sum(p.major_issues_count for p in all_phases)

    db.commit()

    return {
        "message": f"Issue {issue_key} recorded",
        "phase_file": phase_file.model_dump(),
        "run_index_entry": run_index.issues_by_key.get(issue_key),
        "project_backlog_entry": project_backlog.issues_by_key.get(issue_key),
    }


@app.get("/runs/{run_id}/issues/index")
def get_run_issue_index(run_id: str):
    """Get run-level issue index (Chunk B)"""
    tracker = IssueTracker(run_id=run_id)
    index = tracker.load_run_issue_index()
    return index.model_dump()


@app.get("/project/issues/backlog")
def get_project_backlog():
    """Get project-level issue backlog (Chunk B)"""
    tracker = IssueTracker(run_id="dummy")  # run_id not used for backlog loading
    backlog = tracker.load_project_backlog()
    return backlog.model_dump()


@app.post("/runs/{run_id}/phases/{phase_id}/builder_result")
def submit_builder_result(
    run_id: str,
    phase_id: str,
    builder_result: BuilderResult,
    db: Session = Depends(get_db),
):
    """
    Submit Builder result for a phase (Chunk D implementation).

    Per §2.2 of v7 playbook:
    - Builder submits diffs, probe outputs, and issue suggestions
    - Patches go through governed apply path
    - Phase status and issues are updated
    """
    # Find phase
    phase = (
        db.query(models.Phase)
        .filter(models.Phase.run_id == run_id, models.Phase.phase_id == phase_id)
        .first()
    )

    if not phase:
        raise HTTPException(status_code=404, detail=f"Phase {phase_id} not found")

    # Update phase with builder details
    phase.builder_attempts = builder_result.builder_attempts
    phase.tokens_used = builder_result.tokens_used

    # Record suggested issues
    if builder_result.suggested_issues:
        tracker = IssueTracker(run_id=run_id)
        tier = db.query(models.Tier).filter(models.Tier.id == phase.tier_id).first()

        for suggested in builder_result.suggested_issues:
            tracker.record_issue(
                phase_index=phase.phase_index,
                phase_id=phase_id,
                tier_id=tier.tier_id if tier else "unknown",
                issue_key=suggested.issue_key,
                severity=suggested.severity,
                source=suggested.source,
                category=suggested.category,
                task_category=phase.task_category,
                complexity=phase.complexity,
                evidence_refs=suggested.evidence_refs,
            )

    # Apply patch if provided and auto_apply is enabled
    commit_sha = None
    if builder_result.patch_content:
        # Phase 2.1-2.2: Validate patch before application
        from .patch_validator import validate_patch, format_validation_errors

        is_valid, validation_errors = validate_patch(builder_result.patch_content)
        if not is_valid:
            error_detail = format_validation_errors(validation_errors)
            logger.warning(f"Patch validation failed for phase {phase_id}: {error_detail}")
            raise HTTPException(
                status_code=422,  # Unprocessable Entity - validation failure
                detail=error_detail
            )

        # Get strategy to check auto_apply
        strategy_engine = StrategyEngine(project_id="Autopack")
        # For now, always apply (full strategy integration in next step)
        # Use workspace from environment or default to current directory
        import os
        from pathlib import Path
        workspace = Path(os.getenv("REPO_PATH", "."))
        apply_path = GovernedApplyPath(workspace=workspace)
        try:
            success, error_msg = apply_path.apply_patch(
                patch_content=builder_result.patch_content
            )
        except Exception as e:
            logger.error(f"Patch application failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to apply patch: {str(e)}")

        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to apply patch: {error_msg}")

    # Update phase state based on result
    if builder_result.status == "success":
        phase.state = models.PhaseState.COMPLETE
    elif builder_result.status == "needs_review":
        phase.state = models.PhaseState.GATE  # Requires Auditor
    else:
        phase.state = models.PhaseState.FAILED

    try:
        db.commit()
    except Exception as e:
        logger.error(f"Database commit failed: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error during commit: {str(e)}")

    return {
        "message": f"Builder result processed for phase {phase_id}",
        "commit_sha": commit_sha,
        "phase_state": phase.state.value,
    }


@app.post("/runs/{run_id}/phases/{phase_id}/auditor_request")
def request_auditor_review(
    run_id: str,
    phase_id: str,
    request: AuditorRequest,
    db: Session = Depends(get_db),
):
    """
    Request Auditor review for a phase (Chunk D implementation).

    Per §2.3 of v7 playbook:
    - Auditor is invoked when major issues appear, failure loops detected,
      or high-risk phases fail
    """
    phase = (
        db.query(models.Phase)
        .filter(models.Phase.run_id == run_id, models.Phase.phase_id == phase_id)
        .first()
    )

    if not phase:
        raise HTTPException(status_code=404, detail=f"Phase {phase_id} not found")

    # Mark phase as awaiting Auditor
    phase.state = models.PhaseState.GATE

    db.commit()

    return {
        "message": f"Auditor review requested for phase {phase_id}",
        "review_focus": request.review_focus,
        "auditor_profile": request.auditor_profile,
    }


@app.post("/runs/{run_id}/phases/{phase_id}/auditor_result")
def submit_auditor_result(
    run_id: str,
    phase_id: str,
    auditor_result: AuditorResult,
    db: Session = Depends(get_db),
):
    """
    Submit Auditor result for a phase (Chunk D implementation).

    Per §2.3 of v7 playbook:
    - Auditor reviews diffs, logs, and context
    - Suggests minimal patches
    - Patches go through same governed apply path as Builder
    """
    phase = (
        db.query(models.Phase)
        .filter(models.Phase.run_id == run_id, models.Phase.phase_id == phase_id)
        .first()
    )

    if not phase:
        raise HTTPException(status_code=404, detail=f"Phase {phase_id} not found")

    # Update phase with auditor details
    phase.auditor_attempts = auditor_result.auditor_attempts
    phase.tokens_used += auditor_result.tokens_used

    # Record issues found by Auditor
    if auditor_result.issues_found:
        tracker = IssueTracker(run_id=run_id)
        tier = db.query(models.Tier).filter(models.Tier.id == phase.tier_id).first()

        for issue in auditor_result.issues_found:
            tracker.record_issue(
                phase_index=phase.phase_index,
                phase_id=phase_id,
                tier_id=tier.tier_id if tier else "unknown",
                issue_key=issue.issue_key,
                severity=issue.severity,
                source="auditor",
                category=issue.category,
                task_category=phase.task_category,
                complexity=phase.complexity,
                evidence_refs=issue.evidence_refs,
            )

    # Apply suggested patches
    commit_shas = []
    if auditor_result.suggested_patches:
        import os
        from pathlib import Path
        workspace = Path(os.getenv("REPO_PATH", "."))
        apply_path = GovernedApplyPath(workspace=workspace)

        for patch in auditor_result.suggested_patches:
            success, error_msg = apply_path.apply_patch(
                patch_content=patch.patch_content
            )
            if success:
                commit_shas.append(f"patch-applied")  # Simplified - no git integration yet

    # Update phase state based on recommendation
    if auditor_result.recommendation == "approve":
        phase.state = models.PhaseState.COMPLETE
    elif auditor_result.recommendation == "revise":
        phase.state = models.PhaseState.EXECUTING  # Back to Builder
    else:  # escalate
        phase.state = models.PhaseState.FAILED

    db.commit()

    return {
        "message": f"Auditor result processed for phase {phase_id}",
        "recommendation": auditor_result.recommendation,
        "patches_applied": len(commit_shas),
        "commit_shas": commit_shas,
        "phase_state": phase.state.value,
    }


@app.get("/runs/{run_id}/integration_status")
def get_integration_status(run_id: str):
    """Get status of integration branch for this run (Chunk D)"""
    apply_path = GovernedApplyPath(run_id=run_id)
    return apply_path.get_integration_branch_status()


@app.get("/metrics/runs")
def get_run_metrics(status: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Get metrics for all runs (Chunk F implementation).

    Per §11.3 of v7 playbook: operational view of runs with filtering by status.
    """
    query = db.query(models.Run)

    if status:
        try:
            query = query.filter(models.Run.state == models.RunState(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid run state: {status}")

    runs = query.all()

    metrics = []
    for run in runs:
        metrics.append(
            {
                "run_id": run.id,
                "state": run.state.value,
                "safety_profile": run.safety_profile,
                "tokens_used": run.tokens_used,
                "token_cap": run.token_cap,
                "token_utilization": run.tokens_used / run.token_cap if run.token_cap > 0 else 0,
                "minor_issues_count": run.minor_issues_count,
                "major_issues_count": run.major_issues_count,
                "max_minor_issues_total": run.max_minor_issues_total,
                "phase_count": len(run.phases),
                "tier_count": len(run.tiers),
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            }
        )

    return {"total_runs": len(metrics), "runs": metrics}


@app.get("/metrics/tiers/{run_id}")
def get_tier_metrics(run_id: str, db: Session = Depends(get_db)):
    """
    Get tier-level metrics for a run (Chunk F implementation).

    Per §11.3 of v7 playbook: tier status and issue counts.
    """
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    tier_metrics = []
    for tier in run.tiers:
        # Count phases by state
        phase_states = {}
        for phase in [p for p in run.phases if p.tier_id == tier.id]:
            state = phase.state.value
            phase_states[state] = phase_states.get(state, 0) + 1

        tier_metrics.append(
            {
                "tier_id": tier.tier_id,
                "tier_index": tier.tier_index,
                "name": tier.name,
                "state": tier.state.value,
                "minor_issues_count": tier.minor_issues_count,
                "major_issues_count": tier.major_issues_count,
                "phase_count": len([p for p in run.phases if p.tier_id == tier.id]),
                "phase_states": phase_states,
                "tokens_used": sum(p.tokens_used for p in run.phases if p.tier_id == tier.id),
            }
        )

    return {"run_id": run_id, "tier_count": len(tier_metrics), "tiers": tier_metrics}


@app.get("/reports/issue_backlog_summary")
def get_issue_backlog_summary():
    """
    Get summary of project-level issue backlog (Chunk F implementation).

    Per §11.3 of v7 playbook: top recurring issues, aging issues, needs_cleanup status.
    """
    tracker = IssueTracker(run_id="dummy")
    backlog = tracker.load_project_backlog()

    # Sort by age (descending)
    issues_sorted = sorted(
        backlog.issues_by_key.items(), key=lambda x: x[1].age_in_runs, reverse=True
    )

    top_aging = []
    needs_cleanup = []
    open_issues = []

    for issue_key, entry in issues_sorted:
        issue_data = {
            "issue_key": issue_key,
            "base_severity": entry.base_severity,
            "age_in_runs": entry.age_in_runs,
            "age_in_tiers": entry.age_in_tiers,
            "status": entry.status,
            "seen_in_tiers": entry.seen_in_tiers,
            "first_seen_run_id": entry.first_seen_run_id,
            "last_seen_run_id": entry.last_seen_run_id,
        }

        if entry.status == "needs_cleanup":
            needs_cleanup.append(issue_data)
        elif entry.status == "open":
            open_issues.append(issue_data)

    return {
        "total_issues": len(backlog.issues_by_key),
        "open_count": len(open_issues),
        "needs_cleanup_count": len(needs_cleanup),
        "top_aging_issues": issues_sorted[:10],  # Top 10 by age
        "needs_cleanup": needs_cleanup,
    }


@app.get("/reports/budget_analysis")
def get_budget_analysis(db: Session = Depends(get_db)):
    """
    Get analysis of runs that failed due to budget exhaustion (Chunk F implementation).

    Per §11.3 of v7 playbook: identify runs that hit token/phase/duration limits.
    """
    all_runs = db.query(models.Run).all()

    budget_failures = []
    for run in all_runs:
        if run.state in [
            models.RunState.DONE_FAILED_BUDGET_EXHAUSTED,
            models.RunState.DONE_FAILED_PHASE_LIMIT_EXCEEDED,
            models.RunState.DONE_FAILED_TOKEN_CAP_EXCEEDED,
        ]:
            budget_failures.append(
                {
                    "run_id": run.id,
                    "state": run.state.value,
                    "tokens_used": run.tokens_used,
                    "token_cap": run.token_cap,
                    "token_utilization": run.tokens_used / run.token_cap if run.token_cap > 0 else 0,
                    "phase_count": len(run.phases),
                    "max_phases": run.max_phases,
                    "minor_issues_count": run.minor_issues_count,
                    "max_minor_issues_total": run.max_minor_issues_total,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                }
            )

    # Summary statistics
    total_failed = len(budget_failures)
    avg_token_utilization = (
        sum(f["token_utilization"] for f in budget_failures) / total_failed if total_failed > 0 else 0
    )

    return {
        "total_budget_failures": total_failed,
        "average_token_utilization": avg_token_utilization,
        "failures": budget_failures,
    }


@app.get("/reports/run_summary/{run_id}")
def get_run_summary(run_id: str, db: Session = Depends(get_db)):
    """
    Get comprehensive summary for a run (Chunk F implementation).

    Per §11.3 of v7 playbook: combines run state, tier metrics, phase details,
    issue tracking, and budget utilization.
    """
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Tier summaries
    tier_summaries = []
    for tier in run.tiers:
        tier_phases = [p for p in run.phases if p.tier_id == tier.id]
        tier_summaries.append(
            {
                "tier_id": tier.tier_id,
                "name": tier.name,
                "state": tier.state.value,
                "phase_count": len(tier_phases),
                "minor_issues": tier.minor_issues_count,
                "major_issues": tier.major_issues_count,
                "tokens_used": sum(p.tokens_used for p in tier_phases),
            }
        )

    # Phase summaries
    phase_summaries = []
    for phase in run.phases:
        phase_summaries.append(
            {
                "phase_id": phase.phase_id,
                "phase_index": phase.phase_index,
                "name": phase.name,
                "state": phase.state.value,
                "task_category": phase.task_category,
                "complexity": phase.complexity,
                "builder_attempts": phase.builder_attempts,
                "auditor_attempts": phase.auditor_attempts,
                "tokens_used": phase.tokens_used,
                "minor_issues": phase.minor_issues_count,
                "major_issues": phase.major_issues_count,
            }
        )

    # Issue index
    tracker = IssueTracker(run_id=run_id)
    issue_index = tracker.load_run_issue_index()

    return {
        "run_id": run.id,
        "state": run.state.value,
        "safety_profile": run.safety_profile,
        "run_scope": run.run_scope,
        "budgets": {
            "tokens_used": run.tokens_used,
            "token_cap": run.token_cap,
            "token_utilization": run.tokens_used / run.token_cap if run.token_cap > 0 else 0,
            "phase_count": len(run.phases),
            "max_phases": run.max_phases,
        },
        "issues": {
            "minor_count": run.minor_issues_count,
            "major_count": run.major_issues_count,
            "max_minor_total": run.max_minor_issues_total,
            "distinct_issues": len(issue_index.issues_by_key),
        },
        "tiers": tier_summaries,
        "phases": phase_summaries,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


# ===================================================================
# DASHBOARD API ENDPOINTS (Phase 1 - Run Progress + Usage Tracking)
# ===================================================================


@app.get("/dashboard/runs/{run_id}/status")
def get_dashboard_run_status(run_id: str, db: Session = Depends(get_db)):
    """
    Get run status for dashboard display.

    Returns high-level status including:
    - Progress (percent_complete)
    - Current tier/phase indices and names
    - Budget utilization
    - Issue counts
    """
    from .dashboard_schemas import DashboardRunStatus
    from .run_progress import calculate_run_progress
    from .usage_service import UsageService

    # Get run from database
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Calculate progress
    progress = calculate_run_progress(db, run_id)

    # Calculate token utilization
    token_utilization = run.tokens_used / run.token_cap if run.token_cap > 0 else 0.0

    # Get current phase quality info (Phase 2: Quality gate)
    quality_level = None
    quality_blocked = False
    quality_warnings = []

    if progress.current_phase_index is not None:
        current_phase = (
            db.query(models.Phase)
            .filter(
                models.Phase.run_id == run_id,
                models.Phase.phase_index == progress.current_phase_index,
            )
            .first()
        )
        if current_phase:
            quality_level = current_phase.quality_level
            quality_blocked = current_phase.quality_blocked
            # If blocked or needs review, add warnings
            if quality_blocked:
                quality_warnings.append(
                    f"Phase {current_phase.phase_id} is blocked by quality gate"
                )
            elif quality_level == "needs_review":
                quality_warnings.append(
                    f"Phase {current_phase.phase_id} needs human review"
                )

    return DashboardRunStatus(
        run_id=run.id,
        state=run.state.value,
        current_tier_name=progress.current_tier_name,
        current_phase_name=progress.current_phase_name,
        current_tier_index=progress.current_tier_index,
        current_phase_index=progress.current_phase_index,
        total_tiers=progress.total_tiers,
        total_phases=progress.total_phases,
        completed_tiers=progress.completed_tiers,
        completed_phases=progress.completed_phases,
        percent_complete=progress.percent_complete,
        tiers_percent_complete=progress.tiers_percent_complete,
        tokens_used=run.tokens_used,
        token_cap=run.token_cap,
        token_utilization=token_utilization,
        minor_issues_count=run.minor_issues_count,
        major_issues_count=run.major_issues_count,
        quality_level=quality_level,
        quality_blocked=quality_blocked,
        quality_warnings=quality_warnings,
    )


@app.get("/dashboard/usage")
def get_dashboard_usage(
    period: str = "week",  # day, week, month
    db: Session = Depends(get_db),
):
    """
    Get token usage aggregated by provider and model.

    Args:
        period: Time window for usage (day/week/month)

    Returns:
        Usage summary with provider and model breakdowns
    """
    import yaml
    from pathlib import Path

    from .dashboard_schemas import ModelUsage, ProviderUsage, UsageResponse
    from .usage_service import UsageService

    # Load provider caps from config
    config_path = Path("config/models.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    provider_quotas = config.get("provider_quotas", {})

    # Get usage data
    usage_service = UsageService(db)
    provider_usage = usage_service.get_provider_usage_summary(period)
    model_usage = usage_service.get_model_usage_summary(period)

    # Build provider usage list with cap calculations
    providers = []
    for provider, usage in provider_usage.items():
        # Get cap for this provider
        quota_config = provider_quotas.get(provider, {})

        if period == "day":
            cap_tokens = quota_config.get("daily_token_cap", 0)
        elif period == "week":
            cap_tokens = quota_config.get("weekly_token_cap", 0)
        else:  # month
            cap_tokens = quota_config.get("weekly_token_cap", 0) * 4  # Estimate

        # Calculate percentage
        percent_of_cap = (
            (usage["total_tokens"] / cap_tokens * 100) if cap_tokens > 0 else 0.0
        )

        providers.append(
            ProviderUsage(
                provider=provider,
                period=period,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                total_tokens=usage["total_tokens"],
                cap_tokens=cap_tokens,
                percent_of_cap=round(percent_of_cap, 2),
            )
        )

    # Build model usage list
    models = [
        ModelUsage(
            provider=m["provider"],
            model=m["model"],
            prompt_tokens=m["prompt_tokens"],
            completion_tokens=m["completion_tokens"],
            total_tokens=m["total_tokens"],
        )
        for m in model_usage
    ]

    return UsageResponse(providers=providers, models=models)


@app.post("/dashboard/human-notes")
def add_human_note(request: dashboard_schemas.HumanNoteRequest):
    """
    Add a human note for Autopack to read.

    Writes to .autopack/human_notes.md with timestamp.
    """
    from datetime import datetime
    from pathlib import Path

    notes_dir = Path(".autopack")
    notes_dir.mkdir(exist_ok=True)

    notes_file = notes_dir / "human_notes.md"

    timestamp = datetime.utcnow().isoformat()
    run_context = f" (Run: {request.run_id})" if request.run_id else ""

    note_entry = f"\n## {timestamp}{run_context}\n\n{request.note}\n\n---\n"

    # Append to file
    with open(notes_file, "a") as f:
        f.write(note_entry)

    return {
        "message": "Note added successfully",
        "timestamp": timestamp,
        "notes_file": str(notes_file),
    }


# ===================================================================
# DASHBOARD API ENDPOINTS (Phase 2 - Model Router + Controls)
# ===================================================================


@app.get("/dashboard/models")
def get_model_mappings(db: Session = Depends(get_db)):
    """
    Get current model mappings for all roles, categories, and complexity levels.

    Returns:
        Dict with current model assignments
    """
    from .dashboard_schemas import ModelMapping
    from .model_router import ModelRouter

    router = ModelRouter(db)
    mappings = router.get_current_mappings()

    # Convert to list of ModelMapping objects for response
    result = []
    for role, role_mappings in mappings.items():
        for key, model in role_mappings.items():
            category, complexity = key.split(":")
            result.append(
                ModelMapping(
                    role=role,
                    category=category,
                    complexity=complexity,
                    model=model,
                    scope="global",  # Default scope
                )
            )

    return result


@app.post("/dashboard/models/override")
def override_model_mapping(
    request: "dashboard_schemas.ModelOverrideRequest",
    db: Session = Depends(get_db),
):
    """
    Override model mapping for a specific role/category/complexity.

    Scope determines if change is global (affects new runs) or
    run-specific (affects only future phases in that run).

    Args:
        request: Model override request with role, category, complexity, model, scope

    Returns:
        Success message with details
    """
    import yaml
    from pathlib import Path

    from .dashboard_schemas import ModelOverrideRequest

    if request.scope == "run" and not request.run_id:
        raise HTTPException(status_code=400, detail="run_id required for scope=run")

    if request.scope == "global":
        # Update models.yaml config file
        config_path = Path("config/models.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Update category_models or complexity_models
        if request.category != "general":
            # Category-specific override
            if "category_models" not in config:
                config["category_models"] = {}
            if request.category not in config["category_models"]:
                config["category_models"][request.category] = {}

            override_key = f"{request.role}_model_override"
            config["category_models"][request.category][override_key] = request.model
        else:
            # Complexity-based default
            if "complexity_models" not in config:
                config["complexity_models"] = {}
            if request.complexity not in config["complexity_models"]:
                config["complexity_models"][request.complexity] = {}

            config["complexity_models"][request.complexity][request.role] = request.model

        # Write back to file
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return {
            "message": "Global model mapping updated",
            "role": request.role,
            "category": request.category,
            "complexity": request.complexity,
            "model": request.model,
            "scope": "global",
            "note": "Will affect new runs only. Existing runs unchanged.",
        }

    else:  # scope == "run"
        # Update run context model_overrides
        run = db.query(models.Run).filter(models.Run.id == request.run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {request.run_id} not found")

        # For now, we don't have a run context field in the database
        # This would need to be added to the Run model to fully support per-run overrides
        # For MVP, we'll just return a message indicating the feature needs DB schema update

        return {
            "message": "Per-run model overrides require database schema update",
            "role": request.role,
            "category": request.category,
            "complexity": request.complexity,
            "model": request.model,
            "scope": "run",
            "note": "Feature coming soon - requires run_context JSON field in Run model",
            "todo": "Add run_context JSONB column to runs table",
        }


# Mount dashboard frontend (static files)
# This serves the built React app from the dist/ folder
import os
from pathlib import Path

dashboard_path = Path(__file__).parent / "dashboard" / "frontend" / "dist"
if dashboard_path.exists():
    app.mount("/dashboard", StaticFiles(directory=str(dashboard_path), html=True), name="dashboard")
