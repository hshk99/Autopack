"""FastAPI application for Autopack Supervisor (Chunks A, B, C, D implementation)"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from . import dashboard_schemas, models, schemas
from .builder_schemas import AuditorRequest, AuditorResult, BuilderResult
from .config import settings
from .database import get_db, init_db
from .file_layout import RunFileLayout
from .governed_apply import GovernedApplyPath, PatchApplyError
from .issue_tracker import IssueTracker
from .strategy_engine import StrategyEngine
from .usage_recorder import get_doctor_stats

logger = logging.getLogger(__name__)

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

load_dotenv()  # Load environment variables from .env on startup

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

    # Use error reporter to capture detailed context
    from .error_reporter import report_error

    # Extract run_id and phase_id from request path if available
    path_parts = request.url.path.split('/')
    run_id = None
    phase_id = None

    try:
        if 'runs' in path_parts:
            run_idx = path_parts.index('runs')
            if len(path_parts) > run_idx + 1:
                run_id = path_parts[run_idx + 1]
        if 'phases' in path_parts:
            phase_idx = path_parts.index('phases')
            if len(path_parts) > phase_idx + 1:
                phase_id = path_parts[phase_idx + 1]
    except (ValueError, IndexError):
        pass

    # Report error with full context
    report_error(
        error=exc,
        run_id=run_id,
        phase_id=phase_id,
        component="api",
        operation=f"{request.method} {request.url.path}",
        context_data={
            "method": request.method,
            "url": str(request.url),
            "headers": dict(request.headers),
            "query_params": dict(request.query_params),
        }
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": str(exc),
            "type": type(exc).__name__,
            "traceback": tb if os.getenv("DEBUG") == "1" else None,
            "error_report": f"Error report saved to .autonomous_runs/{run_id or 'errors'}/errors/" if run_id else "Error report saved"
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
    """Start a new autonomous build run with tiers and phases."""
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
        max_minor_issues_total=None,
        started_at=datetime.utcnow(),
    )

    # Compute max_minor_issues_total
    if request_data.phases:
        run.max_minor_issues_total = len(request_data.phases) * 3

    db.add(run)
    db.flush()

    # Create tiers
    tier_map = {}
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
            scope=phase_create.scope,
            state=models.PhaseState.QUEUED,
        )
        db.add(phase)

    db.commit()
    db.refresh(run)

    # Compile strategy
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

    # Eagerly load relationships
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
    """Get run details including all tiers and phases."""
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
    """Update phase status."""
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

    # Quality gate fields
    if update.quality_level is not None:
        phase.quality_level = update.quality_level
    if update.quality_blocked is not None:
        phase.quality_blocked = update.quality_blocked

    phase.updated_at = datetime.utcnow()

    # Update phase summary file
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
    """Record an issue for a phase."""
    phase = (
        db.query(models.Phase)
        .filter(models.Phase.run_id == run_id, models.Phase.phase_id == phase_id)
        .first()
    )

    if not phase:
        raise HTTPException(status_code=404, detail=f"Phase {phase_id} not found in run {run_id}")

    tier = db.query(models.Tier).filter(models.Tier.id == phase.tier_id).first()
    if not tier:
        raise HTTPException(status_code=404, detail=f"Tier not found for phase {phase_id}")

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

    # Update tier counts
    tier_phases = db.query(models.Phase).filter(models.Phase.tier_id == tier.id).all()
    tier.minor_issues_count = sum(p.minor_issues_count for p in tier_phases)
    tier.major_issues_count = sum(p.major_issues_count for p in tier_phases)

    # Update run counts
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
    """Get run-level issue index."""
    tracker = IssueTracker(run_id=run_id)
    index = tracker.load_run_issue_index()
    return index.model_dump()


@app.get("/project/issues/backlog")
def get_project_backlog():
    """Get project-level issue backlog."""
    tracker = IssueTracker(run_id="dummy")
    backlog = tracker.load_project_backlog()
    return backlog.model_dump()


@app.get("/runs/{run_id}/errors")
def get_run_errors(run_id: str):
    """Get all error reports for a run."""
    from .error_reporter import get_error_reporter
    reporter = get_error_reporter()
    errors = reporter.get_run_errors(run_id)
    return {"run_id": run_id, "error_count": len(errors), "errors": errors}


@app.get("/runs/{run_id}/errors/summary")
def get_run_error_summary(run_id: str):
    """Get error summary for a run."""
    from .error_reporter import get_error_reporter
    reporter = get_error_reporter()
    summary = reporter.generate_run_error_summary(run_id)
    return {"run_id": run_id, "summary": summary}


@app.post("/runs/{run_id}/phases/{phase_id}/builder_result")
def submit_builder_result(
    run_id: str,
    phase_id: str,
    builder_result: BuilderResult,
    db: Session = Depends(get_db),
):
    """Submit Builder result for a phase."""
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

        for issue in builder_result.suggested_issues:
            tracker.record_issue(
                phase_index=phase.phase_index,
                phase_id=phase_id,
                tier_id=tier.tier_id if tier else "unknown",
                issue_key=issue.issue_key,
                severity=issue.severity,
                source=issue.source,
                category=issue.category,
                evidence_refs=issue.evidence_refs,
            )

    # Apply patch via governed apply path
    if builder_result.patch_content:
        patch_size = len(builder_result.patch_content)
        logger.info(f"[API] builder_result: run_id={run_id}, phase_id={phase_id}, patch_size={patch_size}")
        
        # Get workspace and run_type per GPT_RESPONSE18 Q2/C1 (hybrid approach)
        workspace = Path(settings.repo_path)
        run = db.query(models.Run).filter(models.Run.run_id == run_id).first()
        
        if not run:
            # Data integrity warning, but safe default behavior per GPT_RESPONSE19 Q1/C1
            logger.error(
                f"[API] Run {run_id} not found when applying patch; "
                "defaulting run_type='project_build' (autopack_internal_mode disabled). "
                "This indicates a data integrity issue - Run should exist if Phase exists."
            )
            
            # Record DATA_INTEGRITY issue via IssueTracker per GPT_RESPONSE19 Q1/C1
            try:
                tracker = IssueTracker(run_id=run_id)
                tier = db.query(models.Tier).filter(models.Tier.id == phase.tier_id).first()
                
                issue_key = "run_missing_for_phase"  # Per GPT1: descriptive key for de-duplication
                tracker.record_issue(
                    phase_index=phase.phase_index,
                    phase_id=phase_id,
                    tier_id=tier.tier_id if tier else "unknown",
                    issue_key=issue_key,
                    severity="major",  # Per GPT2: matches existing severity levels
                    source="api_server",  # Per GPT2: more specific than "system"
                    category="data_integrity",  # New category
                    task_category=getattr(phase, 'task_category', None),
                    complexity=getattr(phase, 'complexity', None),
                    evidence_refs=[
                        "main.py: submit_builder_result",
                        f"Run {run_id} missing when applying patch for phase {phase_id}",
                    ],
                )
            except Exception:
                # Don't break the API if IssueTracker fails per GPT_RESPONSE19 C1
                # Per GPT_RESPONSE21 Q1: Use [IssueTracker] prefix for monitoring
                logger.exception(
                    "[IssueTracker] Failed to record DATA_INTEGRITY issue "
                    f"for run_id={run_id}, phase_id={phase_id}"
                )
            
            run_type = "project_build"
        else:
            run_type = run.run_type or "project_build"
            if run.run_type is None:
                logger.error(
                    f"[API] Run {run_id} has no run_type; defaulting run_type='project_build'"
                )
                
                # Record DATA_INTEGRITY issue per GPT_RESPONSE20 Q2
                try:
                    tracker = IssueTracker(run_id=run_id)
                    tier = db.query(models.Tier).filter(models.Tier.id == phase.tier_id).first()
                    
                    issue_key = "run_type_missing_for_run"  # Per GPT1/GPT2: descriptive key
                    tracker.record_issue(
                        phase_index=phase.phase_index,
                        phase_id=phase_id,
                        tier_id=tier.tier_id if tier else "unknown",
                        issue_key=issue_key,
                        severity="major",
                        source="api_server",
                        category="data_integrity",
                        task_category=getattr(phase, 'task_category', None),
                        complexity=getattr(phase, 'complexity', None),
                        evidence_refs=[
                            "main.py: submit_builder_result",
                            f"Run {run_id} has run_type=None when applying patch for phase {phase_id}",
                        ],
                    )
                except Exception:
                    # Per GPT_RESPONSE21 Q1: Use [IssueTracker] prefix for monitoring
                    logger.exception(
                        "[IssueTracker] Failed to record DATA_INTEGRITY issue for missing run_type "
                        f"on run_id={run_id}, phase_id={phase_id}"
                    )
        
        apply_path = GovernedApplyPath(
            workspace=workspace,
            run_type=run_type,
            autopack_internal_mode=run_type in GovernedApplyPath.MAINTENANCE_RUN_TYPES,
        )
        
        # Patch application with exception handling per GPT_RESPONSE16 Q2
        try:
            patch_success, error_msg = apply_path.apply_patch(
                builder_result.patch_content or "",
                full_file_mode=True,  # Per GPT_RESPONSE15: all patches are full-file mode now
            )
            
            if not patch_success:
                logger.error(f"[API] [{run_id}/{phase_id}] Patch application failed: {error_msg}")
                phase.state = models.PhaseState.FAILED
                raise HTTPException(
                    status_code=422,  # Per GPT_RESPONSE16: validation errors should be 422
                    detail=f"Failed to apply patch: {error_msg or 'unknown error'}"
                )
            else:
                phase.state = models.PhaseState.BUILDER_COMPLETE
                
        except PatchApplyError as e:
            # Per GPT_RESPONSE17 C2: Don't log full traceback for expected PatchApplyError
            logger.warning(
                f"[API] [{run_id}/{phase_id}] Patch application failed: {e}"
                # No exc_info=True - expected validation errors don't need full traceback
            )
            phase.state = models.PhaseState.FAILED
            raise HTTPException(
                status_code=422,
                detail=f"Patch application failed: {str(e)}"
            )
        except Exception as e:
            logger.error(f"[API] [{run_id}/{phase_id}] Unexpected error applying patch: {e}", exc_info=True)
            phase.state = models.PhaseState.FAILED
            raise HTTPException(
                status_code=500,
                detail="Unexpected error applying patch"
            )

    # DB commit with exception handling per GPT_RESPONSE16 Q2
    try:
        db.commit()
        db.refresh(phase)
    except Exception as e:
        logger.error(f"[API] [{run_id}/{phase_id}] Database commit failed: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Database error during commit"
        )

    return {"message": "Builder result submitted", "phase": phase}


@app.get("/api/doctor-stats/{run_id}", response_model=dashboard_schemas.DoctorStatsResponse)
def get_doctor_stats_endpoint(run_id: str, db: Session = Depends(get_db)):
    """Get Doctor usage statistics for a run.
    
    Returns:
        - Total Doctor calls this run
        - Cheap vs strong model ratio
        - Action distribution (pie chart data)
        - Escalation frequency
    """
    stats = get_doctor_stats(db, run_id)
    
    if not stats:
        # Return empty stats if no Doctor calls yet
        return dashboard_schemas.DoctorStatsResponse(
            run_id=run_id,
            doctor_calls_total=0,
            doctor_cheap_calls=0,
            doctor_strong_calls=0,
            doctor_escalations=0,
            doctor_actions={},
            cheap_vs_strong_ratio=0.0,
            escalation_frequency=0.0
        )
    
    return dashboard_schemas.DoctorStatsResponse(**stats)


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
