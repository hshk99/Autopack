"""Seed 4 autonomous phases for BUILD-145 P1 completion"""
import json
from pathlib import Path
from autopack.database import SessionLocal
from autopack.models import Run, Tier, Phase, RunState, PhaseState

def seed_run_from_json(json_path: Path):
    """Seed a single run from JSON specification"""
    with open(json_path) as f:
        spec = json.load(f)

    session = SessionLocal()
    try:
        run_config = spec["run"]
        run_id = run_config["run_id"]

        # Check if run already exists
        existing = session.query(Run).filter(Run.id == run_id).first()
        if existing:
            print(f"Run {run_id} already exists, skipping")
            return False

        # Create run
        run = Run(
            id=run_id,
            safety_profile=run_config["safety_profile"],
            run_scope=run_config["run_scope"],
            state=RunState.QUEUED,
            token_cap=run_config.get("token_cap"),
            max_phases=run_config.get("max_phases"),
            max_duration_minutes=run_config.get("max_duration_minutes")
        )
        session.add(run)

        # Create tiers and build tier_id_map
        tier_id_map = {}  # Maps tier_id string (e.g., "T1") to Tier.id integer
        for tier_spec in spec["tiers"]:
            tier = Tier(
                tier_id=tier_spec["tier_id"],
                tier_index=tier_spec["tier_index"],
                run_id=run_id,
                name=tier_spec["name"],
                description=tier_spec.get("description", "")
            )
            session.add(tier)
            session.flush()  # Flush to get the auto-generated tier.id
            tier_id_map[tier_spec["tier_id"]] = tier.id

        # Create phases
        for phase_spec in spec["phases"]:
            # Map tier_id string to tier.id integer
            tier_id_int = tier_id_map.get(phase_spec["tier_id"])
            if tier_id_int is None:
                raise ValueError(f"Unknown tier_id: {phase_spec['tier_id']}")

            phase = Phase(
                phase_id=phase_spec["phase_id"],
                phase_index=phase_spec["phase_index"],
                tier_id=tier_id_int,  # Use integer tier.id, not string tier_id
                run_id=run_id,
                name=phase_spec["name"],
                description=phase_spec.get("description", ""),
                task_category=phase_spec.get("task_category"),
                complexity=phase_spec.get("complexity"),
                builder_mode=phase_spec.get("builder_mode", "default"),
                state=PhaseState.QUEUED,
                scope=phase_spec.get("scope")
            )
            session.add(phase)

        session.commit()
        print(f"✅ Seeded run {run_id}")
        return True

    except Exception as e:
        session.rollback()
        print(f"❌ Error seeding {json_path.name}: {e}")
        raise
    finally:
        session.close()

def main():
    """Seed all 4 phases"""
    base_dir = Path(__file__).parent.parent

    json_files = [
        base_dir / "phase_a_p11_observability.json",
        base_dir / "phase_b_p12_embedding_cache.json",
        base_dir / "phase_c_p13_expand_artifacts.json",
        base_dir / "phase_d_research_imports.json"
    ]

    seeded_count = 0
    for json_file in json_files:
        if json_file.exists():
            if seed_run_from_json(json_file):
                seeded_count += 1
        else:
            print(f"⚠️  File not found: {json_file}")

    print(f"\n✅ Seeded {seeded_count}/{len(json_files)} runs")

if __name__ == "__main__":
    main()
