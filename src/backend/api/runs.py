"""
Minimal Runs API for autonomous executor.

Provides the 5 critical endpoints needed for autonomous executor to function:
1. GET /runs/{run_id} - fetch run with phases
2. PUT /runs/{run_id}/phases/{phase_id} - update phase status
3. POST /runs/{run_id}/phases/{phase_id}/builder_result - submit builder results
4. POST /runs/{run_id}/execute - trigger run execution (BUILD-146 P11 API fix)
5. GET /runs/{run_id}/status - poll run status (BUILD-146 P11 API fix)

This is a bootstrap implementation. Once functional, Autopack will autonomously
build the full REST API with all CRUD operations.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from autopack.database import get_db
from autopack.models import Run, Phase, PhaseState, RunState
from backend.api.api_key_auth import verify_api_key_or_bearer

logger = logging.getLogger(__name__)

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


# BUILD-146 P11 Ops: Missing endpoints for run_parallel.py API mode compatibility

@router.post("/{run_id}/execute")
async def execute_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    auth: str = Depends(verify_api_key_or_bearer)
):
    """
    Trigger asynchronous run execution.

    This endpoint is called by scripts/run_parallel.py in API mode.
    It spawns autonomous_executor.py as a background subprocess to execute the run.

    Args:
        run_id: Run ID to execute
        background_tasks: FastAPI background tasks
        db: Database session

    Returns:
        JSON response with execution status

    Raises:
        HTTPException 404: Run not found
        HTTPException 400: Run already executing or completed
    """
    # Verify run exists
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Check if run is already executing or completed
    if run.state in [RunState.PHASE_EXECUTION, RunState.DONE_SUCCESS, RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW]:
        raise HTTPException(
            status_code=400,
            detail=f"Run {run_id} is already in state {run.state.value}, cannot execute"
        )

    # Update run state to PHASE_EXECUTION
    run.state = RunState.PHASE_EXECUTION
    db.commit()

    logger.info(f"[EXECUTE] Starting execution for run {run_id}")

    # Spawn autonomous_executor.py as background subprocess
    def execute_in_background():
        """Execute autonomous_executor.py as subprocess."""
        try:
            # Find autonomous_executor.py
            project_root = Path(__file__).parent.parent.parent.parent
            executor_script = project_root / "src" / "autopack" / "autonomous_executor.py"

            if not executor_script.exists():
                logger.error(f"[EXECUTE] Executor script not found: {executor_script}")
                # Mark run as failed
                with Session(db.bind) as session:
                    run_obj = session.query(Run).filter(Run.id == run_id).first()
                    if run_obj:
                        run_obj.state = RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW
                        run_obj.failure_reason = "Executor script not found"
                        session.commit()
                return

            # Build command
            python_exe = sys.executable
            cmd = [python_exe, str(executor_script), "--run-id", run_id]

            # Set environment variables
            env = os.environ.copy()
            env["PYTHONPATH"] = str(project_root / "src")
            env["PYTHONUTF8"] = "1"

            # Execute
            logger.info(f"[EXECUTE] Running: {' '.join(cmd)}")
            import subprocess
            result = subprocess.run(
                cmd,
                cwd=project_root,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )

            # Update run state based on result
            with Session(db.bind) as session:
                run_obj = session.query(Run).filter(Run.id == run_id).first()
                if run_obj:
                    if result.returncode == 0:
                        run_obj.state = RunState.DONE_SUCCESS
                        logger.info(f"[EXECUTE] Run {run_id} completed successfully")
                    else:
                        run_obj.state = RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW
                        run_obj.failure_reason = f"Executor failed with exit code {result.returncode}"
                        logger.error(f"[EXECUTE] Run {run_id} failed: {result.stderr[:500]}")
                    session.commit()

        except subprocess.TimeoutExpired:
            logger.error(f"[EXECUTE] Run {run_id} timeout after 1 hour")
            with Session(db.bind) as session:
                run_obj = session.query(Run).filter(Run.id == run_id).first()
                if run_obj:
                    run_obj.state = RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW
                    run_obj.failure_reason = "Execution timeout (1 hour)"
                    session.commit()
        except Exception as e:
            logger.error(f"[EXECUTE] Run {run_id} error: {e}", exc_info=True)
            with Session(db.bind) as session:
                run_obj = session.query(Run).filter(Run.id == run_id).first()
                if run_obj:
                    run_obj.state = RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW
                    run_obj.failure_reason = f"Execution error: {str(e)}"
                    session.commit()

    background_tasks.add_task(execute_in_background)

    return {
        "run_id": run_id,
        "status": "started",
        "message": f"Run {run_id} execution started in background",
        "state": RunState.PHASE_EXECUTION.value
    }


@router.get("/{run_id}/status")
def get_run_status(
    run_id: str,
    db: Session = Depends(get_db),
    auth: str = Depends(verify_api_key_or_bearer)
):
    """
    Get run execution status.

    This endpoint is polled by scripts/run_parallel.py in API mode.
    Returns current run state for monitoring execution progress.

    Args:
        run_id: Run ID
        db: Database session

    Returns:
        JSON response with run state and progress info

    Raises:
        HTTPException 404: Run not found
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    # Count phase states
    phases = db.query(Phase).filter(Phase.run_id == run_id).all()
    total_phases = len(phases)
    completed_phases = sum(1 for p in phases if p.state == PhaseState.COMPLETE)
    failed_phases = sum(1 for p in phases if p.state == PhaseState.FAILED)
    executing_phases = sum(1 for p in phases if p.state == PhaseState.EXECUTING)

    return {
        "run_id": run.id,
        "state": run.state.value if run.state else "UNKNOWN",
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "tokens_used": run.tokens_used or 0,
        "token_cap": run.token_cap or 0,
        "total_phases": total_phases,
        "completed_phases": completed_phases,
        "failed_phases": failed_phases,
        "executing_phases": executing_phases,
        "percent_complete": (completed_phases / total_phases * 100) if total_phases > 0 else 0,
        "failure_reason": run.failure_reason
    }
