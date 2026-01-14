"""Create research-build113-test run in database for BUILD-113 testing."""

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
    with open(phase_file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_build113_run():
    """Create BUILD-113 test run with 6 phases."""

    run_id = "research-build113-test"
    phases_dir = Path(".autonomous_runs/research-build113-test/phases")

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
            token_cap=1000000,
            tokens_used=0,
        )
        db.add(run)
        db.flush()

        print(f"✓ Created run: {run_id}")

        # Create tier
        tier = Tier(
            tier_id=f"{run_id}-tier",
            run_id=run_id,
            tier_index=0,
            name="BUILD-113 Test Tier",
            description="Research System Integration - Testing autonomous fixes",
            state=TierState.PENDING,
            tokens_used=0,
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
            description = phase_data.get("description", "")
            goals = phase_data.get("goals", [])
            deliverables = phase_data.get("deliverables", [])
            acceptance_criteria = phase_data.get("acceptance_criteria", [])
            allowed_paths = phase_data.get("allowed_paths", [])
            protected_paths = phase_data.get("protected_paths", [])
            complexity = phase_data.get("complexity", "medium")
            category = phase_data.get("category", "feature")

            # Build scope dict
            scope = {
                "deliverables": deliverables if isinstance(deliverables, list) else [deliverables],
                "goals": goals if isinstance(goals, list) else [goals],
                "acceptance_criteria": (
                    acceptance_criteria
                    if isinstance(acceptance_criteria, list)
                    else [acceptance_criteria]
                ),
                "allowed_paths": (
                    allowed_paths if isinstance(allowed_paths, list) else [allowed_paths]
                ),
                "protected_paths": (
                    protected_paths if isinstance(protected_paths, list) else [protected_paths]
                ),
            }

            # Add features if present
            if "features" in phase_data:
                scope["features"] = phase_data["features"]

            # Create phase
            phase = Phase(
                phase_id=phase_id,
                run_id=run_id,
                tier_id=tier.id,  # Fixed: Use tier.id (Integer PK) not tier.tier_id (String)
                phase_index=idx,
                name=phase_id,
                description=description,
                state=PhaseState.QUEUED,
                task_category="IMPLEMENT_FEATURE",
                complexity=complexity.upper(),
                builder_mode="BUILD",
                scope=scope,
                tokens_used=0,
                builder_attempts=0,
                auditor_attempts=0,
            )
            db.add(phase)

            print(f"  ✓ Created phase {idx + 1}: {phase_id}")
            print(f"    Complexity: {complexity}")
            print(f"    Category: {category}")
            print(f"    Deliverables: {len(deliverables) if isinstance(deliverables, list) else 1}")

        # Commit all changes
        db.commit()

        print(f"\n{'=' * 80}")
        print(f"SUCCESS: Created run '{run_id}' with {len(phase_files)} phases")
        print(f"{'=' * 80}")
        print("\nRun details:")
        print(f"  - Run ID: {run_id}")
        print("  - State: IN_PROGRESS")
        print(f"  - Tier: {tier.tier_id}")
        print(f"  - Phases: {len(phase_files)}")
        print("\nNext step:")
        print("  Launch autonomous executor with:")
        print("  bash launch_research_build113_test.sh")
        print()

        return True

    except Exception as e:
        print(f"\nERROR: Failed to create run: {e}")
        import traceback

        traceback.print_exc()
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = create_build113_run()
    sys.exit(0 if success else 1)
