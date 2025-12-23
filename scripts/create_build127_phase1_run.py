"""Create build127-phase1 run in database for BUILD-127 Phase 1: Self-Healing Governance."""
import sys
import yaml
from pathlib import Path
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Run, Phase, Tier, RunState, PhaseState, TierState

def load_phase_yaml(phase_file: Path) -> dict:
    """Load phase YAML file."""
    with open(phase_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def create_build127_phase1_run():
    """Create BUILD-127 Phase 1 run."""

    run_id = "build127-phase1-self-healing-governance"
    phases_dir = Path(".autonomous_runs/build127-phase1/phases")

    print(f"Creating run: {run_id}")
    print(f"Phases directory: {phases_dir}")

    # Load phase file
    phase_file = phases_dir / "phase-1-self-healing-governance.yaml"
    if not phase_file.exists():
        print(f"ERROR: Phase file not found: {phase_file}")
        return False

    print(f"Found phase file: {phase_file.name}")

    # Create database session
    db = SessionLocal()

    try:
        # Check if run already exists
        existing_run = db.query(Run).filter(Run.id == run_id).first()
        if existing_run:
            print(f"Run {run_id} already exists - deleting and recreating")
            db.delete(existing_run)
            db.commit()

        # Create run
        run = Run(
            id=run_id,
            state=RunState.PHASE_EXECUTION,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            safety_profile="normal",
            run_scope="single_phase",
            token_cap=500000,  # 500K tokens for single complex phase
            tokens_used=0
        )
        db.add(run)
        db.flush()

        print(f"✓ Created run: {run_id}")

        # Create tier
        tier = Tier(
            tier_id=f"{run_id}-tier",
            run_id=run_id,
            tier_index=0,
            name="BUILD-127 Phase 1: Self-Healing Governance",
            description="Authoritative completion gates and governance negotiation",
            state=TierState.PENDING,
            tokens_used=0
        )
        db.add(tier)
        db.flush()

        print(f"✓ Created tier: {tier.tier_id}")

        # Load phase data
        phase_data = load_phase_yaml(phase_file)

        # Extract phase info
        phase_id = phase_data.get("phase_id")
        display_name = phase_data.get("display_name", phase_id)
        goal = phase_data.get("goal", "")
        constraints = phase_data.get("constraints", {})
        deliverables = phase_data.get("deliverables", [])
        phase_type = phase_data.get("phase_type", "implementation")
        tier_num = phase_data.get("tier", 1)
        priority = phase_data.get("priority", 1)

        # Build scope dict
        scope = {
            "goal": goal,
            "deliverables": deliverables if isinstance(deliverables, list) else [deliverables],
            "allowed_paths": constraints.get("allowed_paths", []),
            "protected_paths": constraints.get("protected_paths", []),
            "dependencies": phase_data.get("dependencies", {}),
            "implementation_order": phase_data.get("implementation_order", []),
            "risk_mitigation": phase_data.get("risk_mitigation", []),
            "architectural_principles": phase_data.get("architectural_principles", []),
        }

        # Create phase
        phase = Phase(
            phase_id=phase_id,
            run_id=run_id,
            tier_id=tier.id,  # Use tier.id (integer FK) not tier.tier_id (string)
            phase_index=0,
            name=display_name,
            description=goal[:500] if goal else None,  # Truncate for description
            state=PhaseState.QUEUED,
            task_category=phase_data.get("task_category", "implementation"),
            complexity=phase_data.get("complexity", "high"),
            builder_mode=phase_data.get("builder_mode", "BUILD"),
            scope=scope,
            retry_attempt=0,
            revision_epoch=0,
            escalation_level=0,
            tokens_used=0
        )
        db.add(phase)

        print(f"  ✓ Created phase: {phase_id} (complexity={phase.complexity}, tier={tier.tier_id})")

        # Commit all changes
        db.commit()
        print(f"\n✓ Successfully created run '{run_id}' with 1 phase")
        print(f"\n🚀 Ready to execute: PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"sqlite:///autopack.db\" python -m autopack.autonomous_executor --run-id {run_id}")
        return True

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        db.close()

if __name__ == "__main__":
    success = create_build127_phase1_run()
    sys.exit(0 if success else 1)
