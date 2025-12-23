"""Create build112-completion run using raw SQL (BUILD-115 compatible)."""
import sys
import yaml
import sqlite3
from pathlib import Path
from datetime import datetime

def load_phase_yaml(phase_file: Path) -> dict:
    """Load phase YAML file."""
    with open(phase_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def create_build112_completion_run():
    """Create BUILD-112 completion run with 4 phases using raw SQL."""

    run_id = "build112-completion"
    phases_dir = Path(".autonomous_runs/build112-completion/phases")
    db_path = "autopack.db"

    print(f"Creating run: {run_id}")
    print(f"Phases directory: {phases_dir}")
    print(f"Database: {db_path}")

    # Load all phase files
    phase_files = sorted(phases_dir.glob("phase-*.yaml"))
    if not phase_files:
        print(f"ERROR: No phase files found in {phases_dir}")
        return False

    print(f"Found {len(phase_files)} phase files")

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if run already exists
        cursor.execute("SELECT id FROM runs WHERE id = ?", (run_id,))
        existing = cursor.fetchone()
        if existing:
            print(f"Run {run_id} already exists - deleting phases and tiers")
            cursor.execute("DELETE FROM phases WHERE run_id = ?", (run_id,))
            cursor.execute("DELETE FROM tiers WHERE run_id = ?", (run_id,))
            cursor.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            conn.commit()

        # Create run
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO runs (
                id, state, created_at, updated_at, safety_profile, run_scope,
                token_cap, max_phases, max_duration_minutes, tokens_used, ci_runs_used,
                minor_issues_count, major_issues_count, promotion_eligible_to_main
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_id, "PHASE_EXECUTION", now, now, "normal", "multi_tier",
              1500000, 100, 480, 0, 0, 0, 0, "false"))

        print(f"✓ Created run: {run_id}")

        # Create tier
        tier_id = f"{run_id}-tier"
        cursor.execute("""
            INSERT INTO tiers (
                tier_id, run_id, tier_index, name, description, state,
                max_major_issues_tolerated, tokens_used, ci_runs_used,
                minor_issues_count, major_issues_count, cleanliness,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (tier_id, run_id, 0, "BUILD-112 Completion Tier",
              "Diagnostics Parity with Cursor - Complete Phases 3, 4, 5", "PENDING",
              3, 0, 0, 0, 0, "spotless", now, now))

        print(f"✓ Created tier: {tier_id}")

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
            priority = phase_data.get("priority", idx + 1)

            # Build scope JSON string
            import json
            scope = {
                "goal": goal,
                "deliverables": deliverables if isinstance(deliverables, list) else [deliverables],
                "allowed_paths": constraints.get("allowed_paths", []),
                "protected_paths": constraints.get("protected_paths", []),
            }
            scope_json = json.dumps(scope)

            # Create phase
            cursor.execute("""
                INSERT INTO phases (
                    id, run_id, tier_id, phase_index, name, description, state, phase_type,
                    scope, priority, retry_attempt, revision_epoch, escalation_level, tokens_used
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                phase_id, run_id, tier_id, idx, display_name, goal[:500],
                "QUEUED", phase_type, scope_json, priority, 0, 0, 0, 0
            ))

            print(f"  ✓ Created phase: {phase_id} (priority={priority})")

        # Commit all changes
        conn.commit()
        print(f"\n✓ Successfully created run '{run_id}' with {len(phase_files)} phases")
        return True

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        conn.close()

if __name__ == "__main__":
    success = create_build112_completion_run()
    sys.exit(0 if success else 1)
