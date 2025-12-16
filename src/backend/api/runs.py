"""
Minimal Runs API for autonomous executor.

Provides the 3 critical endpoints needed for autonomous executor to function:
1. GET /runs/{run_id} - fetch run with phases
2. PUT /runs/{run_id}/phases/{phase_id} - update phase status
3. POST /runs/{run_id}/phases/{phase_id}/builder_result - submit builder results

This is a bootstrap implementation. Once functional, Autopack will autonomously
build the full REST API with all CRUD operations.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from autopack.database import get_db
from autopack.models import Run, Phase, PhaseState

router = APIRouter(prefix="/runs", tags=["runs"])


# Pydantic schemas
class PhaseUpdateRequest(BaseModel):
    """Request to update phase status."""
    state: str
    metadata: Optional[dict] = None


class BuilderResultRequest(BaseModel):
    """Request to submit builder results."""
    success: bool
    output: Optional[str] = None
    files_modified: Optional[list] = None
    metadata: Optional[dict] = None


# Endpoint 1: GET /runs/{run_id} - Fetch run with phases
@router.get("/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)):
    """
    Fetch run details with phases and tiers.

    This is the primary endpoint autonomous executor uses to:
    - Get run configuration
    - Check current state
    - Fetch phases to execute
    """
    run = db.query(Run).options(
        joinedload(Run.phases),
        joinedload(Run.tiers)
    ).filter(Run.id == run_id).first()

    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Convert to dict (simple serialization)
    return {
        "id": run.id,
        "run_id": run.id,  # Backwards compatibility
        "state": run.state.value if run.state else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "safety_profile": run.safety_profile,
        "run_scope": run.run_scope,
        "token_cap": run.token_cap,
        "tokens_used": run.tokens_used,
        "phases": [
            {
                "id": phase.id,
                "phase_id": phase.phase_id,
                "run_id": phase.run_id,
                "tier_id": phase.tier_id,
                "phase_index": phase.phase_index,
                "name": phase.name,
                "description": phase.description,
                "state": phase.state.value if phase.state else None,
                "task_category": phase.task_category,
                "complexity": phase.complexity,
                "builder_mode": phase.builder_mode,
                "scope": phase.scope,
                "tokens_used": phase.tokens_used,
                "builder_attempts": phase.builder_attempts,
                "auditor_attempts": phase.auditor_attempts,
            }
            for phase in run.phases
        ],
        "tiers": [
            {
                "id": tier.id,
                "tier_id": tier.tier_id,
                "run_id": tier.run_id,
                "tier_index": tier.tier_index,
                "name": tier.name,
                "description": tier.description,
                "state": tier.state.value if tier.state else None,
                "tokens_used": tier.tokens_used,
            }
            for tier in run.tiers
        ]
    }


# Endpoint 2: PUT /runs/{run_id}/phases/{phase_id} - Update phase status
@router.put("/{run_id}/phases/{phase_id}")
def update_phase_status(
    run_id: str,
    phase_id: str,
    request: PhaseUpdateRequest,
    db: Session = Depends(get_db)
):
    """
    Update phase state and metadata.

    Autonomous executor uses this to:
    - Mark phase as EXECUTING when starting
    - Mark phase as COMPLETE when done
    - Mark phase as FAILED on errors
    """
    phase = db.query(Phase).filter(
        Phase.run_id == run_id,
        Phase.phase_id == phase_id
    ).first()

    if not phase:
        raise HTTPException(
            status_code=404,
            detail=f"Phase not found: {phase_id} in run {run_id}"
        )

    # Update state
    try:
        phase.state = PhaseState(request.state)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid phase state: {request.state}"
        )

    # Update metadata if provided
    if request.metadata:
        if phase.scope is None:
            phase.scope = {}
        phase.scope.update(request.metadata)

    db.commit()
    db.refresh(phase)

    return {
        "id": phase.id,
        "phase_id": phase.phase_id,
        "state": phase.state.value,
        "message": "Phase status updated successfully"
    }


# Endpoint 3: POST /runs/{run_id}/phases/{phase_id}/builder_result - Submit builder results
@router.post("/{run_id}/phases/{phase_id}/builder_result")
def submit_builder_result(
    run_id: str,
    phase_id: str,
    request: BuilderResultRequest,
    db: Session = Depends(get_db)
):
    """
    Submit builder execution results.

    Autonomous executor uses this to:
    - Report successful phase completion
    - Report failures with error details
    - Track files modified
    - Update attempt counts
    """
    phase = db.query(Phase).filter(
        Phase.run_id == run_id,
        Phase.phase_id == phase_id
    ).first()

    if not phase:
        raise HTTPException(
            status_code=404,
            detail=f"Phase not found: {phase_id} in run {run_id}"
        )

    # Update phase based on result
    phase.builder_attempts += 1

    if request.success:
        phase.state = PhaseState.COMPLETE
    else:
        phase.state = PhaseState.FAILED

    # Store result metadata
    if phase.scope is None:
        phase.scope = {}

    phase.scope["last_builder_result"] = {
        "success": request.success,
        "output": request.output,
        "files_modified": request.files_modified,
        "metadata": request.metadata,
        "attempt": phase.builder_attempts
    }

    db.commit()
    db.refresh(phase)

    return {
        "id": phase.id,
        "phase_id": phase.phase_id,
        "state": phase.state.value,
        "builder_attempts": phase.builder_attempts,
        "message": "Builder result recorded successfully"
    }


# Bonus: POST /runs/{run_id}/phases/{phase_id}/auditor_result (executor also needs this)
@router.post("/{run_id}/phases/{phase_id}/auditor_result")
def submit_auditor_result(
    run_id: str,
    phase_id: str,
    request: BuilderResultRequest,  # Same schema works for auditor
    db: Session = Depends(get_db)
):
    """
    Submit auditor execution results.

    Autonomous executor uses this after CI/quality checks.
    """
    phase = db.query(Phase).filter(
        Phase.run_id == run_id,
        Phase.phase_id == phase_id
    ).first()

    if not phase:
        raise HTTPException(
            status_code=404,
            detail=f"Phase not found: {phase_id} in run {run_id}"
        )

    # Update phase based on audit result
    phase.auditor_attempts += 1

    # Store audit result
    if phase.scope is None:
        phase.scope = {}

    phase.scope["last_auditor_result"] = {
        "success": request.success,
        "output": request.output,
        "metadata": request.metadata,
        "attempt": phase.auditor_attempts
    }

    db.commit()
    db.refresh(phase)

    return {
        "id": phase.id,
        "phase_id": phase.phase_id,
        "auditor_attempts": phase.auditor_attempts,
        "message": "Auditor result recorded successfully"
    }
