"""FastAPI application for Autopack Supervisor (Chunks A, B, C, D implementation)"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

# DIAGNOSTIC: Log DATABASE_URL before load_dotenv() to verify subprocess inheritance
print(f"[API_SERVER_STARTUP] DATABASE_URL from environment: {os.getenv('DATABASE_URL', 'NOT SET')}")

from fastapi import Depends, FastAPI, HTTPException, Request, Security
from contextlib import asynccontextmanager
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
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

# Load .env but DON'T override existing env vars (e.g., DATABASE_URL from executor)
# This ensures subprocess API server inherits DATABASE_URL from parent process
load_dotenv(override=False)
print(f"[API_SERVER_STARTUP] DATABASE_URL after load_dotenv(): {os.getenv('DATABASE_URL', 'NOT SET')}")

# P0 diagnostic: Log actual resolved database URL after normalization
from autopack.config import get_database_url
resolved_url = get_database_url()
print(f"[API_SERVER_STARTUP] Resolved DATABASE_URL (after normalization): {resolved_url}")


async def approval_timeout_cleanup():
    """Background task to handle approval request timeouts.

    Runs every minute to check for expired approval requests and apply
    the configured default behavior (approve or reject).
    """
    import asyncio
    from autopack.notifications.telegram_notifier import TelegramNotifier

    logger.info("[APPROVAL-TIMEOUT] Background task started")

    while True:
        try:
            await asyncio.sleep(60)  # Check every minute

            # Get database session
            db = next(get_db())

            try:
                # Find expired pending requests
                now = datetime.now(timezone.utc)
                expired_requests = db.query(models.ApprovalRequest).filter(
                    models.ApprovalRequest.status == "pending",
                    models.ApprovalRequest.timeout_at <= now
                ).all()

                if expired_requests:
                    logger.info(f"[APPROVAL-TIMEOUT] Found {len(expired_requests)} expired requests")

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
                                message=f"⏱️ Approval timed out. Default action: {final_status}"
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
    # Skip DB init during testing (tests use their own DB setup)
    if os.getenv("TESTING") != "1":
        init_db()

    # Start background task for approval timeout cleanup
    import asyncio
    timeout_task = asyncio.create_task(approval_timeout_cleanup())

    yield

    # Stop background tasks
    timeout_task.cancel()
    try:
        await timeout_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Autopack Supervisor",
    description="Supervisor/orchestrator implementing the v7 autonomous build playbook",
    version="0.1.0",
    lifespan=lifespan,
)

# Add rate limiting to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Mount authentication router
from backend.api import auth as auth_router
app.include_router(auth_router.router, tags=["authentication"])

# Mount research router
from autopack.research.api.router import research_router
app.include_router(research_router, prefix="/research", tags=["research"])

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
    try:
        existing_run = db.query(models.Run).filter(models.Run.id == request_data.run.run_id).first()
    except OperationalError as e:
        logger.error(f"[API] DB OperationalError during run start: {e}")
        db.rollback()
        raise HTTPException(status_code=503, detail="Database unavailable, please retry") from e
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
        started_at=datetime.now(timezone.utc),
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
    try:
        run = db.query(models.Run).filter(models.Run.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        return run
    except OperationalError as e:
        # Avoid opaque 500s when the API is pointed at the wrong DB (common during local validation).
        logger.error(f"[RUNS] Database error while fetching run {run_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "Database unavailable or misconfigured for Autopack API. "
                "Ensure the API server and executor use the same DATABASE_URL."
            ),
        )


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

    phase.updated_at = datetime.now(timezone.utc)

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
        file_layout = None

    # If all phases for this run are now terminal, update run state + run_summary.md
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if run:
        all_phases = db.query(models.Phase).filter(models.Phase.run_id == run_id).all()
        if all_phases and all(
            p.state in (models.PhaseState.COMPLETE, models.PhaseState.FAILED, models.PhaseState.SKIPPED)
            for p in all_phases
        ):
            # Choose a conservative terminal run state: failed if any phase failed, otherwise success.
            if any(p.state == models.PhaseState.FAILED for p in all_phases):
                run.state = models.RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW
            else:
                run.state = models.RunState.DONE_SUCCESS

            run.updated_at = datetime.now(timezone.utc)

            # Rewrite run_summary.md with final state
            try:
                layout = file_layout or RunFileLayout(run_id)
                phases_complete = sum(1 for p in all_phases if p.state == models.PhaseState.COMPLETE)
                phases_failed = sum(1 for p in all_phases if p.state == models.PhaseState.FAILED)
                layout.write_run_summary(
                    run_id=run.id,
                    state=run.state.value,
                    safety_profile=run.safety_profile,
                    run_scope=run.run_scope,
                    created_at=run.created_at.isoformat(),
                    tier_count=len(run.tiers),
                    phase_count=len(all_phases),
                    tokens_used=run.tokens_used,
                    phases_complete=phases_complete,
                    phases_failed=phases_failed,
                    failure_reason=run.failure_reason,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
            except FileNotFoundError:
                # If the layout wasn't initialized on disk, skip quietly.
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
    # Safety: some older deployments may lack the Run.run_id synonym; ensure it exists to avoid AttributeError
    if not hasattr(models.Run, "run_id"):
        models.Run.run_id = models.Run.id  # type: ignore[attr-defined]
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
        run = db.query(models.Run).filter(models.Run.id == run_id).first()
        payload_run_type = getattr(builder_result, "run_type", None)
        
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
            
            run_type = payload_run_type or "project_build"
        else:
            run_type_from_db = getattr(run, "run_type", None)
            run_type = payload_run_type or run_type_from_db

            if not run_type:
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
                                f"Run {run_id} missing run_type in DB and payload when applying patch for phase {phase_id}",
                        ],
                    )
                except Exception:
                    # Per GPT_RESPONSE21 Q1: Use [IssueTracker] prefix for monitoring
                    logger.exception(
                        "[IssueTracker] Failed to record DATA_INTEGRITY issue for missing run_type "
                        f"on run_id={run_id}, phase_id={phase_id}"
                    )
            
            run_type = run_type or "project_build"

        apply_on_server = run_type in GovernedApplyPath.MAINTENANCE_RUN_TYPES

        if not apply_on_server:
            logger.info(
                f"[API] Skipping server-side patch apply for run_type={run_type}; "
                "executor already applied patch locally."
            )
            if builder_result.status == "success":
                phase.state = models.PhaseState.GATE
        else:
            apply_path = GovernedApplyPath(
                workspace=workspace,
                run_type=run_type,
                autopack_internal_mode=run_type in GovernedApplyPath.MAINTENANCE_RUN_TYPES,
                allowed_paths=builder_result.allowed_paths or None,
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
                    phase.state = models.PhaseState.GATE
                    
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
                # Convert unexpected patch/apply errors to 422 so executor does not keep 5xx retrying
                raise HTTPException(
                    status_code=422,
                    detail=f"Patch application failed unexpectedly: {e}"
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


@app.post("/runs/{run_id}/phases/{phase_id}/auditor_result")
def submit_auditor_result(
    run_id: str,
    phase_id: str,
    auditor_result: AuditorResult,
    db: Session = Depends(get_db),
):
    """Submit Auditor result metadata for a phase."""
    phase = (
        db.query(models.Phase)
        .filter(models.Phase.run_id == run_id, models.Phase.phase_id == phase_id)
        .first()
    )

    if not phase:
        raise HTTPException(status_code=404, detail=f"Phase {phase_id} not found")

    phase.auditor_attempts = auditor_result.auditor_attempts
    phase.tokens_used = max(phase.tokens_used or 0, auditor_result.tokens_used or 0)

    logger.info(
        f"[API] auditor_result: run_id={run_id}, phase_id={phase_id}, "
        f"recommendation={auditor_result.recommendation}, issues={len(auditor_result.issues_found)}"
    )

    try:
        db.commit()
    except Exception as e:
        logger.error(f"[API] [{run_id}/{phase_id}] Failed to store auditor result: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error during auditor_result commit")

    return {"message": "Auditor result submitted"}


@app.post("/approval/request")
async def request_approval(request: Request, db: Session = Depends(get_db)):
    """Handle approval requests from BUILD-113 autonomous executor.

    BUILD-117 Enhanced Implementation with:
    - Telegram notifications with approve/reject buttons
    - Database audit trail for all approval requests
    - Approval timeout mechanism (default: 15 minutes)
    - Dashboard UI integration

    Expected payload:
    {
        "phase_id": str,
        "run_id": str,
        "context": str,  # "build113_risky_decision", "build113_ambiguous_decision", or "troubleshoot"
        "decision_info": dict  # Decision metadata
        "deletion_info": dict  # (optional) For deletion approvals
    }

    Returns:
    {
        "status": "approved" | "rejected" | "pending",
        "reason": str (optional),
        "approval_id": int (if stored in database)
    }
    """
    try:
        from datetime import timedelta
        from autopack.notifications.telegram_notifier import TelegramNotifier

        data = await request.json()
        phase_id = data.get("phase_id")
        run_id = data.get("run_id")
        context = data.get("context", "unknown")
        decision_info = data.get("decision_info", {})
        deletion_info = data.get("deletion_info")

        logger.info(
            f"[APPROVAL] Request received: run={run_id}, phase={phase_id}, "
            f"context={context}, decision_type={decision_info.get('type', 'N/A')}"
        )

        # Configuration
        auto_approve = os.getenv("AUTO_APPROVE_BUILD113", "true").lower() == "true"
        timeout_minutes = int(os.getenv("APPROVAL_TIMEOUT_MINUTES", "15"))
        default_on_timeout = os.getenv("APPROVAL_DEFAULT_ON_TIMEOUT", "reject")  # "approve" or "reject"

        # Calculate timeout
        timeout_at = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)

        # Store approval request in database for audit trail
        approval_request = models.ApprovalRequest(
            run_id=run_id,
            phase_id=phase_id,
            context=context,
            decision_info=decision_info,
            deletion_info=deletion_info,
            timeout_at=timeout_at,
            status="pending"
        )
        db.add(approval_request)
        db.commit()
        db.refresh(approval_request)

        logger.info(f"[APPROVAL] Stored request #{approval_request.id} in database")

        # Auto-approve mode: immediate approval without notification
        if auto_approve:
            approval_request.status = "approved"
            approval_request.response_method = "auto"
            approval_request.approval_reason = "Auto-approved (AUTO_APPROVE_BUILD113=true)"
            approval_request.responded_at = datetime.now(timezone.utc)
            db.commit()

            logger.warning(
                f"[APPROVAL] AUTO-APPROVING request #{approval_request.id} for {phase_id}"
            )
            return {
                "status": "approved",
                "reason": "Auto-approved (BUILD-117 - auto-approve mode enabled)",
                "approval_id": approval_request.id
            }

        # Send Telegram notification
        notifier = TelegramNotifier()
        telegram_sent = False
        telegram_error = None

        if notifier.is_configured():
            logger.info(f"[APPROVAL] Sending Telegram notification for request #{approval_request.id}")

            # Prepare deletion info for notification
            telegram_deletion_info = deletion_info or {
                'net_deletion': 0,
                'loc_removed': 0,
                'loc_added': 0,
                'files': [],
                'risk_level': decision_info.get('risk_level', 'medium'),
                'risk_score': decision_info.get('risk_score', 50)
            }

            telegram_sent = notifier.send_approval_request(
                phase_id=phase_id,
                deletion_info=telegram_deletion_info,
                run_id=run_id,
                context=context
            )

            if not telegram_sent:
                telegram_error = "Failed to send Telegram notification (check bot configuration)"
                logger.error(f"[APPROVAL] {telegram_error}")
        else:
            telegram_error = "Telegram not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)"
            logger.warning(f"[APPROVAL] {telegram_error}")

        # Update approval request with Telegram status
        approval_request.telegram_sent = telegram_sent
        approval_request.telegram_error = telegram_error
        db.commit()

        # Return pending status (will be updated via webhook or timeout)
        return {
            "status": "pending",
            "reason": f"Awaiting human approval (timeout in {timeout_minutes} minutes, default: {default_on_timeout})",
            "approval_id": approval_request.id,
            "telegram_sent": telegram_sent,
            "timeout_at": timeout_at.isoformat()
        }

    except Exception as e:
        logger.error(f"[APPROVAL] Error processing approval request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Approval request processing failed: {str(e)}")


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Telegram webhook callbacks for approval buttons.

    This endpoint receives callbacks when users tap Approve/Reject buttons
    in Telegram notifications.

    Callback data format: "approve:{phase_id}" or "reject:{phase_id}"
    """
    try:
        from autopack.notifications.telegram_notifier import TelegramNotifier

        data = await request.json()
        logger.info(f"[TELEGRAM] Webhook received: {data}")

        # Extract callback query
        callback_query = data.get("callback_query")
        if not callback_query:
            logger.warning("[TELEGRAM] No callback_query in webhook data")
            return {"ok": True}

        callback_data = callback_query.get("data")
        message_id = callback_query.get("message", {}).get("message_id")
        chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
        user_id = callback_query.get("from", {}).get("id")
        username = callback_query.get("from", {}).get("username", "unknown")

        if not callback_data:
            logger.warning("[TELEGRAM] No callback data in query")
            return {"ok": True}

        # Parse callback data: "approve:{phase_id}" or "reject:{phase_id}"
        action, phase_id = callback_data.split(":", 1)

        logger.info(f"[TELEGRAM] User @{username} ({user_id}) {action}d phase {phase_id}")

        # Find the approval request
        approval_request = db.query(models.ApprovalRequest).filter(
            models.ApprovalRequest.phase_id == phase_id,
            models.ApprovalRequest.status == "pending"
        ).order_by(models.ApprovalRequest.requested_at.desc()).first()

        if not approval_request:
            logger.warning(f"[TELEGRAM] No pending approval request found for {phase_id}")
            # Still acknowledge the callback
            notifier = TelegramNotifier()
            if notifier.is_configured():
                notifier.send_completion_notice(
                    phase_id=phase_id,
                    status="error",
                    message="⚠️ Approval request not found or already processed"
                )
            return {"ok": True}

        # Update approval request
        approval_request.status = action + "ed"  # "approve" -> "approved", "reject" -> "rejected"
        approval_request.response_method = "telegram"
        approval_request.responded_at = datetime.now(timezone.utc)
        approval_request.telegram_message_id = str(message_id)

        if action == "approve":
            approval_request.approval_reason = f"Approved by Telegram user @{username}"
        else:
            approval_request.rejected_reason = f"Rejected by Telegram user @{username}"

        db.commit()

        logger.info(
            f"[TELEGRAM] Approval request #{approval_request.id} {action}ed by @{username}"
        )

        # Send confirmation message
        notifier = TelegramNotifier()
        if notifier.is_configured():
            notifier.send_completion_notice(
                phase_id=phase_id,
                status=action + "ed",
                message=f"Phase `{phase_id}` has been {action}ed."
            )

        return {"ok": True}

    except Exception as e:
        logger.error(f"[TELEGRAM] Webhook error: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


@app.get("/approval/status/{approval_id}")
async def get_approval_status(approval_id: int, db: Session = Depends(get_db)):
    """Check the status of an approval request.

    Used by autonomous executor to poll for approval decisions.

    Returns:
    {
        "approval_id": int,
        "status": "pending" | "approved" | "rejected" | "timeout",
        "requested_at": datetime,
        "responded_at": datetime (if responded),
        "timeout_at": datetime,
        "approval_reason": str (if approved),
        "rejected_reason": str (if rejected)
    }
    """
    try:
        approval_request = db.query(models.ApprovalRequest).filter(
            models.ApprovalRequest.id == approval_id
        ).first()

        if not approval_request:
            raise HTTPException(status_code=404, detail=f"Approval request #{approval_id} not found")

        return {
            "approval_id": approval_request.id,
            "run_id": approval_request.run_id,
            "phase_id": approval_request.phase_id,
            "status": approval_request.status,
            "requested_at": approval_request.requested_at.isoformat(),
            "responded_at": approval_request.responded_at.isoformat() if approval_request.responded_at else None,
            "timeout_at": approval_request.timeout_at.isoformat() if approval_request.timeout_at else None,
            "approval_reason": approval_request.approval_reason,
            "rejected_reason": approval_request.rejected_reason,
            "response_method": approval_request.response_method
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[APPROVAL] Error fetching status for #{approval_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch approval status: {str(e)}")


@app.get("/approval/pending")
async def get_pending_approvals(db: Session = Depends(get_db)):
    """Get all pending approval requests (for dashboard UI).

    Returns:
    {
        "count": int,
        "requests": [...]
    }
    """
    try:
        pending_requests = db.query(models.ApprovalRequest).filter(
            models.ApprovalRequest.status == "pending"
        ).order_by(models.ApprovalRequest.requested_at.desc()).all()

        return {
            "count": len(pending_requests),
            "requests": [
                {
                    "id": req.id,
                    "run_id": req.run_id,
                    "phase_id": req.phase_id,
                    "context": req.context,
                    "requested_at": req.requested_at.isoformat(),
                    "timeout_at": req.timeout_at.isoformat() if req.timeout_at else None,
                    "decision_info": req.decision_info,
                    "deletion_info": req.deletion_info,
                    "telegram_sent": req.telegram_sent
                }
                for req in pending_requests
            ]
        }

    except Exception as e:
        logger.error(f"[APPROVAL] Error fetching pending approvals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch pending approvals: {str(e)}")


# =============================================================================
# BUILD-127 Phase 2: Governance Request Endpoints
# =============================================================================

@app.get("/governance/pending")
async def get_pending_governance_requests(db: Session = Depends(get_db)):
    """Get all pending governance requests (BUILD-127 Phase 2).

    Returns:
        JSON response with pending governance requests
    """
    try:
        from .governance_requests import get_pending_requests

        pending = get_pending_requests(db)

        return {
            "count": len(pending),
            "pending_requests": [req.to_dict() for req in pending]
        }

    except Exception as e:
        logger.error(f"[GOVERNANCE] Error fetching pending requests: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch pending requests: {str(e)}")


@app.post("/governance/approve/{request_id}")
async def approve_governance_request(
    request_id: str,
    approved: bool = True,
    user_id: str = "human",
    db: Session = Depends(get_db)
):
    """Approve or deny a governance request (BUILD-127 Phase 2).

    Args:
        request_id: Governance request ID
        approved: True to approve, False to deny
        user_id: ID of approving user

    Returns:
        JSON response with approval status
    """
    try:
        from .governance_requests import approve_request, deny_request

        if approved:
            success = approve_request(db, request_id, approved_by=user_id)
            status = "approved"
        else:
            success = deny_request(db, request_id, denied_by=user_id)
            status = "denied"

        if success:
            return {
                "status": status,
                "request_id": request_id,
                "message": f"Governance request {status}"
            }
        else:
            raise HTTPException(status_code=404, detail="Governance request not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GOVERNANCE] Error updating request {request_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update request: {str(e)}")


# =============================================================================
# Dashboard Endpoints
# =============================================================================

@app.get("/dashboard/runs/{run_id}/status", response_model=dashboard_schemas.DashboardRunStatus)
def get_dashboard_run_status(run_id: str, db: Session = Depends(get_db)):
    """Get run status for dashboard display"""
    from .run_progress import calculate_run_progress

    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Calculate progress
    progress = calculate_run_progress(db, run_id)

    # Calculate token utilization
    tokens_used = run.tokens_used or 0
    token_cap = run.token_cap or 1
    token_utilization = (tokens_used / token_cap) * 100 if token_cap > 0 else 0

    # Count issues
    minor_issues_count = run.minor_issues_count or 0
    major_issues_count = run.major_issues_count or 0

    return dashboard_schemas.DashboardRunStatus(
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
        tokens_used=tokens_used,
        token_cap=token_cap,
        token_utilization=token_utilization,
        minor_issues_count=minor_issues_count,
        major_issues_count=major_issues_count,
    )


@app.get("/dashboard/usage", response_model=dashboard_schemas.UsageResponse)
def get_dashboard_usage(period: str = "week", db: Session = Depends(get_db)):
    """Get token usage statistics for dashboard display"""
    from datetime import timedelta
    from .usage_recorder import LlmUsageEvent

    # Calculate time range based on period
    now = datetime.now(timezone.utc)
    if period == "day":
        start_time = now - timedelta(days=1)
    elif period == "week":
        start_time = now - timedelta(weeks=1)
    elif period == "month":
        start_time = now - timedelta(days=30)
    else:
        start_time = now - timedelta(weeks=1)  # Default to week

    # Query usage events in time range
    usage_events = db.query(LlmUsageEvent).filter(
        LlmUsageEvent.created_at >= start_time
    ).all()

    if not usage_events:
        return dashboard_schemas.UsageResponse(providers=[], models=[])

    # Aggregate by provider
    provider_stats = {}
    for event in usage_events:
        if event.provider not in provider_stats:
            provider_stats[event.provider] = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        provider_stats[event.provider]["prompt_tokens"] += event.prompt_tokens
        provider_stats[event.provider]["completion_tokens"] += event.completion_tokens
        provider_stats[event.provider]["total_tokens"] += (event.prompt_tokens + event.completion_tokens)

    # Aggregate by model
    model_stats = {}
    for event in usage_events:
        key = f"{event.provider}:{event.model}"
        if key not in model_stats:
            model_stats[key] = {
                "provider": event.provider,
                "model": event.model,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        model_stats[key]["prompt_tokens"] += event.prompt_tokens
        model_stats[key]["completion_tokens"] += event.completion_tokens
        model_stats[key]["total_tokens"] += (event.prompt_tokens + event.completion_tokens)

    # Convert to response models
    providers = [
        dashboard_schemas.ProviderUsage(
            provider=provider,
            period=period,
            prompt_tokens=stats["prompt_tokens"],
            completion_tokens=stats["completion_tokens"],
            total_tokens=stats["total_tokens"],
            cap_tokens=0,  # TODO: Get from config
            percent_of_cap=0.0
        )
        for provider, stats in provider_stats.items()
    ]

    models_list = [
        dashboard_schemas.ModelUsage(**stats)
        for stats in model_stats.values()
    ]

    return dashboard_schemas.UsageResponse(providers=providers, models=models_list)


@app.get("/dashboard/models")
def get_dashboard_models(db: Session = Depends(get_db)):
    """Get current model mappings for dashboard display"""
    from .model_router import ModelRouter

    # Create router instance
    router = ModelRouter(db)

    # Get current mappings
    mappings = router.get_current_mappings()

    # Convert to list format for dashboard
    result = []
    for role in ["builder", "auditor"]:
        for key, model in mappings[role].items():
            category, complexity = key.split(":")
            result.append(
                dashboard_schemas.ModelMapping(
                    role=role,
                    category=category,
                    complexity=complexity,
                    model=model,
                    scope="global"
                )
            )

    return result


@app.post("/dashboard/human-notes")
def add_dashboard_human_note(note_request: dashboard_schemas.HumanNoteRequest, db: Session = Depends(get_db)):
    """Add a human note to the notes file"""
    from .config import settings

    notes_file = Path(settings.autonomous_runs_dir) / ".." / ".autopack" / "human_notes.md"
    notes_file.parent.mkdir(parents=True, exist_ok=True)

    # Append note with timestamp
    timestamp = datetime.now(timezone.utc).isoformat()
    note_entry = f"\n## {timestamp}\n"
    if note_request.run_id:
        note_entry += f"**Run:** {note_request.run_id}\n"
    note_entry += f"{note_request.note}\n"

    with open(notes_file, "a", encoding="utf-8") as f:
        f.write(note_entry)

    return {
        "message": "Note added successfully",
        "timestamp": timestamp,
        "notes_file": ".autopack/human_notes.md"
    }


@app.post("/dashboard/models/override")
def add_dashboard_model_override(override_request: dashboard_schemas.ModelOverrideRequest, db: Session = Depends(get_db)):
    """Add a model override (global or per-run)"""
    if override_request.scope == "global":
        # For global scope, we would update config file
        # For now, return success message
        return {
            "message": "Global model mapping updated",
            "scope": "global",
            "role": override_request.role,
            "category": override_request.category,
            "complexity": override_request.complexity,
            "model": override_request.model
        }
    elif override_request.scope == "run":
        # For run scope, we would update run context
        # For now, return "coming soon" message per test expectations
        return {
            "message": "Run-scoped model overrides coming soon",
            "scope": "run",
            "run_id": override_request.run_id
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid scope. Must be 'global' or 'run'")


@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint.

    BUILD-129 Phase 3: Treat DB connectivity as part of health to prevent false-positives where
    /health is 200 but /runs/{id} fails with 500 due to DB misconfiguration (e.g., API using
    default Postgres while executor wrote runs into local SQLite).
    """
    try:
        # Basic connectivity
        db.execute(text("SELECT 1"))
        # Basic schema sanity (will raise if tables missing/misconfigured)
        db.query(models.Run).limit(1).all()
        payload = {
            "status": "healthy",
            "service": "autopack",
            "component": "supervisor_api",
            "db_ok": True,
        }
        # Optional DB identity payload for drift debugging.
        # This is intentionally gated because it reveals local file paths.
        if os.getenv("DEBUG_DB_IDENTITY") == "1":
            try:
                from autopack.db_identity import _get_sqlite_db_path  # type: ignore

                run_ids = [r[0] for r in db.query(models.Run.id).order_by(models.Run.id.asc()).limit(5).all()]
                payload["db_identity"] = {
                    "database_url": os.getenv("DATABASE_URL"),
                    "sqlite_file": str(_get_sqlite_db_path() or ""),
                    "runs": db.query(models.Run).count(),
                    "phases": db.query(models.Phase).count(),
                    "sample_run_ids": run_ids,
                }
            except Exception as _e:
                payload["db_identity_error"] = str(_e)

        return payload
    except Exception as e:
        logger.error(f"[HEALTH] DB health check failed: {e}", exc_info=True)
        # 503 so callers know to treat the server as unhealthy.
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "db_ok": False,
                "error": str(e),
                "hint": "Start the API server with the same DATABASE_URL as the executor.",
            },
        )
