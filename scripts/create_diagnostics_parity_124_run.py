#!/usr/bin/env python3
"""Create diagnostics-parity-phases-124 run for proper implementation of phases 1, 2, 4

Phases 3 & 5 were completed in autopack-diagnostics-parity-v5.
Phases 1, 2, 4 were completed in autopack-followups-v1 but with minimal/stub implementations.
This run lets Autopack properly implement the remaining diagnostics parity phases.

Usage:
    PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/create_diagnostics_parity_124_run.py
"""

import sys
from pathlib import Path
import yaml
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Run, Phase, Tier, RunState, PhaseState, TierState


def load_followup_yaml(yaml_path: Path) -> dict:
    """Load follow-up YAML configuration"""
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def create_diagnostics_parity_124_run():
    """Create diagnostics-parity-phases-124 run for phases 1, 2, 4"""

    db = SessionLocal()
    run_id = "diagnostics-parity-phases-124"

    try:
        # Check if run already exists
        existing_run = db.query(Run).filter(Run.id == run_id).first()
        if existing_run:
            print(f"✅ Run already exists: {existing_run.id}")
            print(f"   State: {existing_run.state}")
            print(f"   Phases: {len(existing_run.phases)}")
            return existing_run.id

        # Phases to implement (1, 2, 4 - in order)
        followup_files = [
            "followup1-diagnostics-handoff-bundle.yaml",
            "followup2-diagnostics-cursor-prompt.yaml",
            "followup3-diagnostics-second-opinion.yaml",  # This is phase 4
        ]

        followup_dir = Path("requirements/research_followup")
        if not followup_dir.exists():
            print(f"❌ Follow-up requirements directory not found: {followup_dir}")
            return None

        # Load all follow-up configs
        followup_configs = []
        for filename in followup_files:
            yaml_path = followup_dir / filename
            if not yaml_path.exists():
                print(f"❌ Follow-up YAML not found: {yaml_path}")
                return None
            followup_configs.append(load_followup_yaml(yaml_path))

        print(f"📋 Creating run: {run_id}")
        print(f"   Phases: {len(followup_configs)}")
        for config in followup_configs:
            print(f"   - {config['phase_id']}: {config['description'].strip().split('.')[0]}...")

        # Create Run
        run = Run(
            id=run_id,
            state=RunState.PHASE_QUEUEING,
            safety_profile="normal",
            run_scope="multi_tier",
            token_cap=1_000_000,  # 1M tokens for 3 phases
            max_phases=6,  # 3 phases + buffer for replanning
            max_duration_minutes=720,  # 12 hours
            tokens_used=0,
            ci_runs_used=0,
            minor_issues_count=0,
            major_issues_count=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(run)

        # Create a single tier
        tier = Tier(
            tier_id="diagnostics-parity-124-tier",
            run_id=run_id,
            tier_index=0,
            name="Diagnostics Parity Phases 1, 2, 4 (Proper Implementation)",
            description="Handoff Bundle, Cursor Prompt Generator, Second Opinion Triage - full implementations",
            state=TierState.PENDING,
            tokens_used=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(tier)
        db.flush()  # Get the auto-generated id

        # Create phases
        for idx, config in enumerate(followup_configs):
            phase = Phase(
                phase_id=config["phase_id"],
                run_id=run_id,
                tier_id=tier.id,
                phase_index=idx,
                name=config["phase_id"],
                description=config["description"].strip(),
                state=PhaseState.QUEUED,
                task_category="IMPLEMENT_FEATURE",
                complexity="MEDIUM",
                builder_mode="BUILD",
                scope={
                    "chunk_number": config.get("chunk_number", f"diagnostics-parity-{idx + 1}"),
                    "deliverables": config.get("deliverables", {}),
                    "features": config.get("features", []),
                    "validation": config.get("validation", {}),
                    "goals": config.get("goals", []),
                },
                tokens_used=0,
                builder_attempts=0,
                auditor_attempts=0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(phase)
            print(f"   ✓ Phase {idx}: {phase.phase_id}")

        # Commit all changes
        db.commit()

        print("\n✅ Run created successfully!")
        print(f"   Run ID: {run.id}")
        print(f"   Tier ID: {tier.tier_id}")
        print(f"   Phases: {len(followup_configs)}")
        print("\n🚀 Ready to launch autonomous executor:")
        print(
            f'   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -m autopack.autonomous_executor --run-id {run_id} --api-url http://127.0.0.1:8001 --max-iterations 100'
        )

        return run.id

    except Exception as e:
        print(f"❌ Error creating run: {e}")
        import traceback

        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_diagnostics_parity_124_run()
