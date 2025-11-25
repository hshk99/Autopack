"""Run progress tracking for dashboard"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from . import models


@dataclass
class RunProgress:
    """Progress tracking for a run"""

    run_id: str
    total_tiers: int
    total_phases: int
    completed_tiers: int
    completed_phases: int
    current_tier_index: Optional[int]
    current_phase_index: Optional[int]
    current_tier_name: Optional[str] = None
    current_phase_name: Optional[str] = None

    @property
    def percent_complete(self) -> float:
        """Calculate completion percentage based on phases"""
        if self.total_phases == 0:
            return 0.0
        return (self.completed_phases / self.total_phases) * 100

    @property
    def tiers_percent_complete(self) -> float:
        """Calculate completion percentage based on tiers"""
        if self.total_tiers == 0:
            return 0.0
        return (self.completed_tiers / self.total_tiers) * 100


def calculate_run_progress(db: Session, run_id: str) -> RunProgress:
    """
    Calculate current progress for a run.

    Args:
        db: Database session
        run_id: Run identifier

    Returns:
        RunProgress dataclass with current state
    """
    # Get run with all tiers and phases
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    # Count totals
    total_tiers = len(run.tiers)
    total_phases = len(run.phases)

    # Count completed
    completed_tiers = sum(
        1 for tier in run.tiers if tier.state in [models.TierState.COMPLETE, models.TierState.SKIPPED]
    )

    completed_phases = sum(
        1
        for phase in run.phases
        if phase.state
        in [
            models.PhaseState.COMPLETE,
            models.PhaseState.SKIPPED,
        ]
    )

    # Find current tier and phase (first non-completed)
    current_tier = None
    current_phase = None

    for tier in sorted(run.tiers, key=lambda t: t.tier_index):
        if tier.state not in [models.TierState.COMPLETE, models.TierState.SKIPPED]:
            current_tier = tier
            break

    for phase in sorted(run.phases, key=lambda p: p.phase_index):
        if phase.state not in [models.PhaseState.COMPLETE, models.PhaseState.SKIPPED]:
            current_phase = phase
            break

    return RunProgress(
        run_id=run_id,
        total_tiers=total_tiers,
        total_phases=total_phases,
        completed_tiers=completed_tiers,
        completed_phases=completed_phases,
        current_tier_index=current_tier.tier_index if current_tier else None,
        current_phase_index=current_phase.phase_index if current_phase else None,
        current_tier_name=current_tier.name if current_tier else None,
        current_phase_name=current_phase.name if current_phase else None,
    )
