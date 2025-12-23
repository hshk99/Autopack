"""Create build112-completion run in database for BUILD-112 Phase 3, 4, 5 completion."""
import sys
import yaml
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Run, Phase, Tier, RunState, PhaseState, TierState

def load_phase_yaml(phase_file: Path) -> dict:
    """Load phase YAML file."""
    with open(phase_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def create_build112_completion_run():
    """Create BUILD-112 completion run with 4 phases."""

    run_id = "build112-completion"
    phases_dir = Path(".autonomous_runs/build112-completion/phases")

    print(f"Creating run: {run_id}")
    print(f"Phases directory: {phases_dir}")

    # Load all phase files
    phase_files = sorted(phases_dir.glob("phase-*.yaml"))
    if not phase_files:
        print(f"ERROR: No phase files found in {phases_dir}")
        return False

    print(f"Found {len(phase_files)} phase files")

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
            created_at=datetime.now(),
            updated_at=datetime.now(),
            safety_profile="normal",
            run_scope="multi_tier",
            token_cap=1500000,
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
            name="BUILD-112 Completion Tier",
            description="Diagnostics Parity with Cursor - Complete Phases 3, 4, 5",
            state=TierState.PENDING,
            tokens_used=0
        )
        db.add(tier)
        db.flush()

        print(f"✓ Created tier: {tier.tier_id}")

        # Create phases
        for idx, phase_file in enumerate(phase_files):
            print(f"\nProcessing: {phase_file.name}")

            phase_data = load_phase_yaml(phase_file)

            # Extract phase info
            phase_id = phase_data.get("phase_id")
            display_name = phase_data.get("display_name", phase_id)
            goal = phase_data.get("goal", "")
            constraints = phase_data.get("constraints", {})
            deliverables = phase_data.get("deliverables", [])
            phase_type = phase_data.get("phase_type", "implementation")
            tier_num = phase_data.get("tier", 1)
            priority = phase_data.get("priority", idx + 1)

            # Build scope dict
            scope = {
                "goal": goal,
                "deliverables": deliverables if isinstance(deliverables, list) else [deliverables],
                "allowed_paths": constraints.get("allowed_paths", []),
                "protected_paths": constraints.get("protected_paths", []),
            }

            # Create phase
            phase = Phase(
                phase_id=phase_id,
                run_id=run_id,
                tier_id=tier.id,  # Use tier.id (integer FK) not tier.tier_id (string)
                phase_index=idx,
                name=display_name,
                description=goal[:500] if goal else None,  # Truncate for description
                state=PhaseState.QUEUED,
                task_category=phase_data.get("task_category", "implementation"),
                complexity=phase_data.get("complexity", "medium"),
                builder_mode=phase_data.get("builder_mode", "BUILD"),
                scope=scope,
                retry_attempt=0,
                revision_epoch=0,
                escalation_level=0,
                tokens_used=0
            )
            db.add(phase)

            print(f"  ✓ Created phase: {phase_id} (index={idx}, tier={tier.tier_id})")

        # Commit all changes
        db.commit()
        print(f"\n✓ Successfully created run '{run_id}' with {len(phase_files)} phases")
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
    success = create_build112_completion_run()
    sys.exit(0 if success else 1)
