"""FastAPI application for Autopack Supervisor (Chunks A, B, C, D implementation)"""

from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from . import models, schemas
from .builder_schemas import AuditorRequest, AuditorResult, BuilderResult
from .database import get_db, init_db
from .file_layout import RunFileLayout
from .governed_apply import GovernedApplyPath
from .issue_tracker import IssueTracker
from .strategy_engine import StrategyEngine

app = FastAPI(
    title="Autopack Supervisor",
    description="Supervisor/orchestrator implementing the v7 autonomous build playbook",
    version="0.1.0",
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


@app.post("/runs/start", response_model=schemas.RunResponse, status_code=201)
def start_run(request: schemas.RunStartRequest, db: Session = Depends(get_db)):
    """
    Start a new autonomous build run with tiers and phases.

    Per §3 of v7 playbook:
    1. Create run record
    2. Create tier records
    3. Create phase records
    4. Initialize file layout under .autonomous_runs/{run_id}/
    """
    # Check if run already exists
    existing_run = db.query(models.Run).filter(models.Run.id == request.run.run_id).first()
    if existing_run:
        raise HTTPException(status_code=400, detail=f"Run {request.run.run_id} already exists")

    # Create run
    run = models.Run(
        id=request.run.run_id,
        state=models.RunState.RUN_CREATED,
        safety_profile=request.run.safety_profile,
        run_scope=request.run.run_scope,
        token_cap=request.run.token_cap or 5_000_000,
        max_phases=request.run.max_phases or 25,
        max_duration_minutes=request.run.max_duration_minutes or 120,
        max_minor_issues_total=None,  # Will be computed based on phase count
        started_at=datetime.utcnow(),
    )

    # Compute max_minor_issues_total (phases_in_run * 3 per §9.1)
    if request.phases:
        run.max_minor_issues_total = len(request.phases) * 3

    db.add(run)
    db.flush()

    # Create tiers
    tier_map = {}  # tier_id -> Tier model
    for tier_create in request.tiers:
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
    for phase_create in request.phases:
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
        tier_count=len(request.tiers),
        phase_count=len(request.phases),
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

    return run


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

    phase.updated_at = datetime.utcnow()

    # Update phase summary file
    file_layout = RunFileLayout(run_id)
    file_layout.write_phase_summary(
        phase_index=phase.phase_index,
        phase_id=phase.phase_id,
        phase_name=phase.name,
        state=phase.state.value,
        task_category=phase.task_category,
        complexity=phase.complexity,
    )

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
        # Get strategy to check auto_apply
        strategy_engine = StrategyEngine(project_id="Autopack")
        # For now, always apply (full strategy integration in next step)
        apply_path = GovernedApplyPath(run_id=run_id)
        success, commit_sha = apply_path.apply_patch(
            patch_content=builder_result.patch_content,
            phase_id=phase_id,
            commit_message=f"[Builder] {phase_id}: {builder_result.notes}",
        )

        if not success:
            raise HTTPException(status_code=500, detail="Failed to apply patch")

    # Update phase state based on result
    if builder_result.status == "success":
        phase.state = models.PhaseState.COMPLETE
    elif builder_result.status == "needs_review":
        phase.state = models.PhaseState.GATE  # Requires Auditor
    else:
        phase.state = models.PhaseState.FAILED

    db.commit()

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
        apply_path = GovernedApplyPath(run_id=run_id)

        for patch in auditor_result.suggested_patches:
            success, commit_sha = apply_path.apply_patch(
                patch_content=patch.patch_content,
                phase_id=phase_id,
                commit_message=f"[Auditor] {phase_id}: {patch.description}",
            )
            if success:
                commit_shas.append(commit_sha)

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
