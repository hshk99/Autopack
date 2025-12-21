#!/usr/bin/env python3
"""Create research-system-v1 run with Chunk 0 phase

This script creates the initial database entries for the Research System
implementation, starting with Chunk 0 (Tracer Bullet).

Usage:
    PYTHONPATH=src python scripts/create_research_run.py
"""

import sys
from pathlib import Path
import yaml
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Run, Phase, Tier, RunState, PhaseState, TierState


def load_chunk_yaml(chunk_path: Path) -> dict:
    """Load chunk YAML configuration"""
    with open(chunk_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def create_research_run():
    """Create research-system-v1 run with Chunk 0"""

    db = SessionLocal()

    try:
        # Check if run already exists
        existing_run = db.query(Run).filter(Run.id == "research-system-v1").first()
        if existing_run:
            print(f"✅ Run already exists: {existing_run.id}")
            print(f"   State: {existing_run.state}")
            print(f"   Phases: {len(existing_run.phases)}")
            return existing_run.id

        # Load Chunk 0 configuration
        chunk0_path = Path(".autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk0-tracer-bullet.yaml")
        if not chunk0_path.exists():
            print(f"❌ Chunk 0 YAML not found: {chunk0_path}")
            return None

        chunk0_config = load_chunk_yaml(chunk0_path)

        print(f"📋 Creating run: research-system-v1")
        print(f"   Phase: {chunk0_config['phase_id']}")
        print(f"   Description: {chunk0_config['description'].strip()[:100]}...")

        # Create Run
        run = Run(
            id="research-system-v1",
            state=RunState.PHASE_QUEUEING,
            safety_profile="normal",
            run_scope="multi_tier",
            token_cap=5_000_000,
            max_phases=50,  # Research system has 8 chunks, estimate ~6 phases per chunk
            max_duration_minutes=2880,  # 2 days per chunk * 8 chunks = ~16 days
            tokens_used=0,
            ci_runs_used=0,
            minor_issues_count=0,
            major_issues_count=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(run)

        # Create Tier 0 (Chunk 0) - id is auto-increment, tier_id is string identifier
        tier0 = Tier(
            tier_id=f"chunk-{chunk0_config['chunk_number']}",
            run_id="research-system-v1",
            tier_index=chunk0_config['chunk_number'],
            name=f"Chunk {chunk0_config['chunk_number']}: Tracer Bullet",
            description=chunk0_config['description'].strip(),
            state=TierState.PENDING,
            tokens_used=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(tier0)
        db.flush()  # Get the auto-generated id

        # Create Phase for Chunk 0 - id is auto-increment, tier_id is FK to tier.id (integer)
        phase = Phase(
            phase_id=chunk0_config['phase_id'],
            run_id="research-system-v1",
            tier_id=tier0.id,  # Use the auto-generated tier.id (integer)
            phase_index=0,
            name=chunk0_config['phase_id'],
            description=chunk0_config['description'].strip(),
            state=PhaseState.QUEUED,
            task_category="IMPLEMENT_FEATURE",
            complexity="HIGH",  # Research system is complex
            builder_mode="BUILD",
            scope={
                "chunk_number": chunk0_config['chunk_number'],
                "deliverables": chunk0_config['deliverables'],
                "features": chunk0_config['features'],
                "validation": chunk0_config['validation'],
            },
            tokens_used=0,
            builder_attempts=0,
            auditor_attempts=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        db.add(phase)

        # Commit all changes
        db.commit()

        print(f"\n✅ Run created successfully!")
        print(f"   Run ID: {run.id}")
        print(f"   Tier ID: {tier0.tier_id}")
        print(f"   Phase ID: {phase.phase_id}")
        print(f"   State: {phase.state}")
        print(f"\n🚀 Ready to launch autonomous executor:")
        print(f"   PYTHONPATH=src python -m autopack.autonomous_executor --run-id research-system-v1")

        return run.id

    except Exception as e:
        print(f"❌ Error creating run: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_research_run()
