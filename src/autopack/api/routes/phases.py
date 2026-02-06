"""Phases router for phase status and result endpoints.

Extracted from main.py as part of PR-API-3h.

Endpoints:
- GET /phases - List phases with pagination
- POST /runs/{run_id}/phases/{phase_id}/update_status - Update phase status
- POST /runs/{run_id}/phases/{phase_id}/record_issue - Record an issue for a phase
- POST /runs/{run_id}/phases/{phase_id}/builder_result - Submit Builder result
- POST /runs/{run_id}/phases/{phase_id}/auditor_result - Submit Auditor result
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from autopack import models, schemas
from autopack.api.db_query_validator import DBQueryValidator
from autopack.api.deps import verify_api_key
from autopack.builder_schemas import AuditorResult, BuilderResult
from autopack.config import settings
from autopack.database import get_db
from autopack.file_layout import RunFileLayout
from autopack.governed_apply import GovernedApplyPath, PatchApplyError
from autopack.issue_tracker import IssueTracker

logger = logging.getLogger(__name__)

router = APIRouter(tags=["phases"])


@router.get("/phases", response_model=schemas.PaginatedResponse)
async def list_phases(
    run_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    """
    List phases with pagination.

    Args:
        run_id: Optional filter by run ID
        page: Page number (1-indexed, default 1)
        page_size: Number of items per page (default 50, max 100)

    Returns:
        Paginated response with items and metadata
    """
    # IMP-SEC-002: Validate user-controlled parameters before database query
    try:
        run_id = DBQueryValidator.validate_run_id(run_id)
    except ValueError as e:
        logger.warning(f"Invalid run_id in list_phases: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid run_id: {str(e)}")

    # Validate pagination params
    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    query = db.query(models.Phase)
    if run_id:
        query = query.filter_by(run_id=run_id)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    phase_items = query.offset(offset).limit(page_size).all()

    # Convert Phase objects to PhaseResponse for serialization
    items = [schemas.PhaseResponse.model_validate(phase) for phase in phase_items]

    return schemas.PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(offset + page_size) < total,
    )


@router.post(
    "/runs/{run_id}/phases/{phase_id}/update_status",
    summary="Update phase status",
    description="Update the status and metadata of a specific phase including state, builder attempts, tokens used, and issue counts. Also updates run state if all phases reach terminal state.",
    dependencies=[Depends(verify_api_key)],
    responses={
        200: {"description": "Phase status updated successfully"},
        400: {"description": "Invalid phase state"},
        404: {"description": "Phase or run not found"},
        500: {"description": "Internal server error"},
    },
)
def update_phase_status(
    run_id: str,
    phase_id: str,
    update: schemas.PhaseStatusUpdate,
    db: Session = Depends(get_db),
):
    """Update phase status."""
    # IMP-SEC-002: Validate user-controlled parameters before database query
    try:
        run_id = DBQueryValidator.validate_run_id(run_id)
        phase_id = DBQueryValidator.validate_phase_id(phase_id)
    except ValueError as e:
        logger.warning(f"Invalid parameters in update_phase_status: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid parameter: {str(e)}")

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
            p.state
            in (models.PhaseState.COMPLETE, models.PhaseState.FAILED, models.PhaseState.SKIPPED)
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
                phases_complete = sum(
                    1 for p in all_phases if p.state == models.PhaseState.COMPLETE
                )
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


@router.post(
    "/runs/{run_id}/phases/{phase_id}/record_issue",
    summary="Record an issue for a phase",
    description="Record an issue detected during phase execution. Updates phase, tier, and run issue counts. Issues are categorized by severity and source.",
    dependencies=[Depends(verify_api_key)],
    responses={
        200: {"description": "Issue recorded successfully"},
        404: {"description": "Phase, run, or tier not found"},
        500: {"description": "Internal server error"},
    },
)
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
    # IMP-SEC-002: Validate user-controlled parameters before database query
    try:
        run_id = DBQueryValidator.validate_run_id(run_id)
        phase_id = DBQueryValidator.validate_phase_id(phase_id)
        issue_key = DBQueryValidator.validate_string_parameter(issue_key, "issue_key")
        severity = DBQueryValidator.validate_string_parameter(severity, "severity")
        source = DBQueryValidator.validate_string_parameter(source, "source")
        category = DBQueryValidator.validate_string_parameter(category, "category")
        if task_category:
            task_category = DBQueryValidator.validate_string_parameter(task_category, "task_category")
        if complexity:
            complexity = DBQueryValidator.validate_string_parameter(complexity, "complexity")
        if evidence_refs:
            evidence_refs = DBQueryValidator.validate_list_of_strings(evidence_refs, "evidence_refs")
    except ValueError as e:
        logger.warning(f"Invalid parameters in record_phase_issue: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid parameter: {str(e)}")

    phase = (
        db.query(models.Phase)
        .options(joinedload(models.Phase.tier))
        .filter(models.Phase.run_id == run_id, models.Phase.phase_id == phase_id)
        .first()
    )

    if not phase:
        raise HTTPException(status_code=404, detail=f"Phase {phase_id} not found in run {run_id}")

    tier = phase.tier
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


@router.post(
    "/runs/{run_id}/phases/{phase_id}/builder_result",
    summary="Submit Builder result for a phase",
    description="Submit the results of Builder execution for a phase including patch content, issues, and token usage. Applies patches to workspace via governed apply path and updates phase state.",
    dependencies=[Depends(verify_api_key)],
    responses={
        200: {"description": "Builder result submitted successfully"},
        400: {"description": "Invalid run or phase ID mismatch"},
        404: {"description": "Phase not found"},
        422: {"description": "Patch application failed"},
        500: {"description": "Internal server error"},
    },
)
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
        .options(joinedload(models.Phase.tier))
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
        tier = phase.tier  # Eager-loaded via joinedload

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
        logger.info(
            f"[API] builder_result: run_id={run_id}, phase_id={phase_id}, patch_size={patch_size}"
        )

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
                tier = phase.tier  # Eager-loaded via joinedload

                issue_key = "run_missing_for_phase"  # Per GPT1: descriptive key for de-duplication
                tracker.record_issue(
                    phase_index=phase.phase_index,
                    phase_id=phase_id,
                    tier_id=tier.tier_id if tier else "unknown",
                    issue_key=issue_key,
                    severity="major",  # Per GPT2: matches existing severity levels
                    source="api_server",  # Per GPT2: more specific than "system"
                    category="data_integrity",  # New category
                    task_category=getattr(phase, "task_category", None),
                    complexity=getattr(phase, "complexity", None),
                    evidence_refs=[
                        "phases.py: submit_builder_result",
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
                    tier = phase.tier  # Eager-loaded via joinedload

                    issue_key = "run_type_missing_for_run"  # Per GPT1/GPT2: descriptive key
                    tracker.record_issue(
                        phase_index=phase.phase_index,
                        phase_id=phase_id,
                        tier_id=tier.tier_id if tier else "unknown",
                        issue_key=issue_key,
                        severity="major",
                        source="api_server",
                        category="data_integrity",
                        task_category=getattr(phase, "task_category", None),
                        complexity=getattr(phase, "complexity", None),
                        evidence_refs=[
                            "phases.py: submit_builder_result",
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
            # IMP-SAFETY-008: Extract scope_paths from phase for Layer 2 validation
            scope_config = phase.scope if hasattr(phase, "scope") and phase.scope else {}
            scope_paths = scope_config.get("paths", []) if isinstance(scope_config, dict) else []

            apply_path = GovernedApplyPath(
                workspace=workspace,
                run_type=run_type,
                autopack_internal_mode=run_type in GovernedApplyPath.MAINTENANCE_RUN_TYPES,
                allowed_paths=builder_result.allowed_paths or None,
                scope_paths=scope_paths,
            )

            # Patch application with exception handling per GPT_RESPONSE16 Q2
            try:
                patch_success, error_msg = apply_path.apply_patch(
                    builder_result.patch_content or "",
                    full_file_mode=True,  # Per GPT_RESPONSE15: all patches are full-file mode now
                )

                if not patch_success:
                    logger.error(
                        f"[API] [{run_id}/{phase_id}] Patch application failed: {error_msg}"
                    )
                    phase.state = models.PhaseState.FAILED
                    raise HTTPException(
                        status_code=422,  # Per GPT_RESPONSE16: validation errors should be 422
                        detail=f"Failed to apply patch: {error_msg or 'unknown error'}",
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
                    status_code=422, detail="Patch application failed - check logs for details"
                )
            except Exception as e:
                logger.error(
                    f"[API] [{run_id}/{phase_id}] Unexpected error applying patch: {e}",
                    exc_info=True,
                )
                phase.state = models.PhaseState.FAILED
                # Convert unexpected patch/apply errors to 422 so executor does not keep 5xx retrying
                raise HTTPException(
                    status_code=422, detail=f"Patch application failed unexpectedly: {e}"
                )

    # DB commit with exception handling per GPT_RESPONSE16 Q2
    try:
        db.commit()
        db.refresh(phase)
    except Exception as e:
        logger.error(f"[API] [{run_id}/{phase_id}] Database commit failed: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error during commit")

    return {
        "message": "Builder result submitted successfully",
        "phase_id": phase_id,
        "run_id": run_id,
        "phase_state": phase.state.value if hasattr(phase.state, "value") else str(phase.state),
    }


@router.post(
    "/runs/{run_id}/phases/{phase_id}/auditor_result",
    summary="Submit Auditor result for a phase",
    description="Submit the results of Auditor execution for a phase including recommendation and issues found. Records auditor attempts and token usage for the phase.",
    dependencies=[Depends(verify_api_key)],
    responses={
        200: {"description": "Auditor result submitted successfully"},
        400: {"description": "Run or phase ID mismatch"},
        404: {"description": "Phase not found"},
        500: {"description": "Database error"},
    },
)
def submit_auditor_result(
    run_id: str,
    phase_id: str,
    auditor_result: AuditorResult,
    db: Session = Depends(get_db),
):
    """Submit Auditor result for a phase."""
    if auditor_result.run_id != run_id or auditor_result.phase_id != phase_id:
        raise HTTPException(
            status_code=400,
            detail="Path parameters (run_id, phase_id) must match AuditorResult payload",
        )

    phase = (
        db.query(models.Phase)
        .filter(models.Phase.run_id == run_id, models.Phase.phase_id == phase_id)
        .first()
    )
    if not phase:
        raise HTTPException(status_code=404, detail=f"Phase {phase_id} not found")

    # Record auditor attempt count + tokens (best-effort)
    phase.auditor_attempts = max(
        int(phase.auditor_attempts or 0), int(auditor_result.auditor_attempts or 0)
    )
    phase.tokens_used = max(int(phase.tokens_used or 0), int(auditor_result.tokens_used or 0))

    logger.info(
        f"[API] auditor_result: run_id={run_id}, phase_id={phase_id}, "
        f"recommendation={auditor_result.recommendation}, issues={len(auditor_result.issues_found)}"
    )

    try:
        db.commit()
    except Exception as e:
        logger.error(
            f"[API] [{run_id}/{phase_id}] Failed to store auditor result: {e}", exc_info=True
        )
        db.rollback()
        raise HTTPException(status_code=500, detail="Database error during auditor_result commit")

    return {"message": "Auditor result submitted"}
