"""
Create telemetry-collection-v6 targeted sampling run.

BUILD-141 Part 9: Targeted v6 sampling to close weak groups from v5.
- docs/low (need ~7-10 more, currently n=3)
- docs/medium (need ~5, currently n=0)
- tests/medium (need ~5, currently n=3)

Critical guardrails:
- Explicit output caps for docs phases (≤150-250 lines)
- Minimal context loading (5-10 files max)
- Low initial budgets for docs (4K-8K output tokens)
- Multi-deliverable phases (2-3 files) to diversify deliverable count

Total: 20 phases
- Docs: 12 phases (10 docs/low, 2 docs/medium)
- Tests/medium: 6 phases
- Implementation/medium: 2 phases (with 2-3 deliverables)

Usage (from repo root):
    PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///./telemetry_seed_v6.db" \
        python scripts/create_telemetry_v6_targeted_run.py
"""

import os
import sys
from pathlib import Path

# Require DATABASE_URL to prevent silent fallback to Postgres
if not os.environ.get("DATABASE_URL"):
    print("[telemetry_v6_seed] ERROR: DATABASE_URL must be set explicitly.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Example usage (PowerShell, from repo root):", file=sys.stderr)
    print("  $env:DATABASE_URL='sqlite:///./telemetry_seed_v6.db'", file=sys.stderr)
    print("  python scripts/create_telemetry_v6_targeted_run.py", file=sys.stderr)
    print("", file=sys.stderr)
    print("Example usage (bash):", file=sys.stderr)
    print("  DATABASE_URL='sqlite:///telemetry_seed_v6.db' python scripts/create_telemetry_v6_targeted_run.py", file=sys.stderr)
    sys.exit(1)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal, init_db
from autopack.models import Run, RunState, Phase, PhaseState, Tier, TierState
from datetime import datetime, timezone
import json

def create_telemetry_v6_run():
    """Create telemetry-collection-v6 targeted sampling run."""

    # Initialize database
    print("Initializing database...")
    init_db()

    session = SessionLocal()

    try:
        # Create run
        run = Run(
            id="telemetry-collection-v6",
            state=RunState.PHASE_EXECUTION,
            created_at=datetime.now(timezone.utc),
            goal_anchor=json.dumps({
                "goal": (
                    "Targeted telemetry sampling to stabilize weak groups from v5. "
                    "Focus: docs/low (n=3→13), docs/medium (n=0→5), tests/medium (n=3→8). "
                    "All docs phases have explicit output caps (≤150-250 lines) and minimal context. "
                    "Multi-deliverable phases to diversify deliverable count distribution."
                ),
                "purpose": "telemetry_v6_targeted_sampling",
                "target_groups": ["docs/low", "docs/medium", "tests/medium"],
                "v5_gaps": {
                    "docs/low": "n=3, unstable (CV=0.95), need 10 more",
                    "docs/medium": "n=0, need 5",
                    "tests/medium": "n=3, unstable (CV=0.71), need 5"
                },
                "guardrails": [
                    "Explicit output caps for docs (≤150-250 lines)",
                    "Minimal context loading (5-10 files max)",
                    "Low initial budgets for docs (4K-8K)",
                    "Multi-deliverable phases (2-3 files)"
                ],
                "total_phases": 20,
                "expected_clean_samples": 18
            })
        )
        session.add(run)
        session.flush()

        print(f"Created run: {run.id}")
        print()

        # Create a single tier for all phases
        tier = Tier(
            tier_id="telemetry-v6-T1",
            run_id=run.id,
            tier_index=1,
            name="telemetry-v6-tier1",
            description="Single tier for all v6 telemetry sampling phases",
            state=TierState.IN_PROGRESS,
            created_at=datetime.now(timezone.utc),
        )
        session.add(tier)
        session.flush()

        # Define phases
        phases = []

        # === DOCS/LOW PHASES (10) ===
        # Short, capped outputs, minimal context
        docs_low_phases = [
            {
                "phase_id": "telemetry-v6-d1-quickstart",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["docs/QUICKSTART.md"],
                "goal": (
                    "Create concise QUICKSTART.md (≤150 lines). "
                    "Cover: installation (5 lines), basic usage (1 snippet), first run. "
                    "Keep it brief. Minimal context (3-5 files)."
                ),
            },
            {
                "phase_id": "telemetry-v6-d2-contributing",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["docs/CONTRIBUTING.md"],
                "goal": (
                    "Create CONTRIBUTING.md (≤200 lines). "
                    "Sections: dev setup, testing, PR process. "
                    "Max 8 sections total. Minimal context (5 files)."
                ),
            },
            {
                "phase_id": "telemetry-v6-d3-architecture-overview",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["docs/ARCHITECTURE.md"],
                "goal": (
                    "Create high-level ARCHITECTURE.md (≤180 lines). "
                    "Cover: key components, data flow, no detailed API docs. "
                    "Use bullet-style. Context: 5-8 key files only."
                ),
            },
            {
                "phase_id": "telemetry-v6-d4-config-guide",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["docs/CONFIG_GUIDE.md"],
                "goal": (
                    "Create CONFIG_GUIDE.md (≤150 lines). "
                    "Cover: environment variables, .env file, common configs. "
                    "3-5 code snippets total. Context: config files + 2-3 source files."
                ),
            },
            {
                "phase_id": "telemetry-v6-d5-telemetry-guide",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["docs/TELEMETRY_GUIDE.md"],
                "goal": (
                    "Create TELEMETRY_GUIDE.md (≤200 lines). "
                    "Cover: enabling telemetry, collection workflow, analysis. "
                    "5-7 sections max. Context: telemetry-related files only (6-8 files)."
                ),
            },
            {
                "phase_id": "telemetry-v6-d6-error-handling",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["docs/ERROR_HANDLING.md"],
                "goal": (
                    "Create ERROR_HANDLING.md (≤150 lines). "
                    "Cover: common errors, recovery strategies, debugging tips. "
                    "Bullet-style, 3-5 scenarios. Context: error_*.py files (4-6 files)."
                ),
            },
            {
                "phase_id": "telemetry-v6-d7-deployment",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["docs/DEPLOYMENT.md"],
                "goal": (
                    "Create DEPLOYMENT.md (≤180 lines). "
                    "Cover: Docker setup, env vars, health checks. "
                    "No comprehensive ops guide. Context: Docker files + 3-4 config files."
                ),
            },
            {
                "phase_id": "telemetry-v6-d8-testing-guide",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["docs/TESTING_GUIDE.md"],
                "goal": (
                    "Create TESTING_GUIDE.md (≤150 lines). "
                    "Cover: running tests, writing tests, test structure. "
                    "3 snippets total. Context: test files + pytest.ini (5-7 files)."
                ),
            },
            {
                "phase_id": "telemetry-v6-d9-api-basics",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["docs/API_BASICS.md"],
                "goal": (
                    "Create API_BASICS.md (≤200 lines). "
                    "Cover: API routes overview, auth, common responses. "
                    "High-level only, no exhaustive reference. Context: router files (6-8 files)."
                ),
            },
            {
                "phase_id": "telemetry-v6-d10-troubleshooting",
                "category": "docs",
                "complexity": "low",
                "deliverables": ["docs/TROUBLESHOOTING.md"],
                "goal": (
                    "Create TROUBLESHOOTING.md (≤180 lines). "
                    "Cover: 10-15 common issues with fixes. "
                    "Bullet-style Q&A. Context: error logs + health_checks.py (4-5 files)."
                ),
            },
        ]

        # === DOCS/MEDIUM PHASES (2) ===
        docs_medium_phases = [
            {
                "phase_id": "telemetry-v6-d11-phase-lifecycle",
                "category": "docs",
                "complexity": "medium",
                "deliverables": ["docs/PHASE_LIFECYCLE.md"],
                "goal": (
                    "Create PHASE_LIFECYCLE.md (≤250 lines). "
                    "Cover: phase states, transitions, finalization, error recovery. "
                    "Include sequence diagram (text). Max 10 sections. "
                    "Context: phase_*.py files (8-12 files)."
                ),
            },
            {
                "phase_id": "telemetry-v6-d12-governance",
                "category": "docs",
                "complexity": "medium",
                "deliverables": ["docs/GOVERNANCE.md"],
                "goal": (
                    "Create GOVERNANCE.md (≤250 lines). "
                    "Cover: approval workflow, governance tiers, auto-approval rules. "
                    "5-8 sections. Context: governance_*.py files (8-10 files)."
                ),
            },
        ]

        # === TESTS/MEDIUM PHASES (6) ===
        tests_medium_phases = [
            {
                "phase_id": "telemetry-v6-t1-context-budgeter",
                "category": "testing",
                "complexity": "medium",
                "deliverables": ["tests/autopack/test_context_budgeter_extended.py"],
                "goal": (
                    "Create extended tests for context_budgeter.py. "
                    "Test: budget allocation, priority handling, context splitting. "
                    "Write 12-15 test cases. Context: context_budgeter.py + related files."
                ),
            },
            {
                "phase_id": "telemetry-v6-t2-token-estimator",
                "category": "testing",
                "complexity": "medium",
                "deliverables": ["tests/autopack/test_token_estimator_calibration.py"],
                "goal": (
                    "Create calibration-specific tests for token_estimator.py. "
                    "Test: PHASE_OVERHEAD changes, damped updates, confidence scoring. "
                    "Write 10-12 test cases. Context: token_estimator.py."
                ),
            },
            {
                "phase_id": "telemetry-v6-t3-error-recovery",
                "category": "testing",
                "complexity": "medium",
                "deliverables": ["tests/autopack/test_error_recovery_extended.py"],
                "goal": (
                    "Create extended tests for error_recovery.py. "
                    "Test: retry strategies, circuit breaker, backoff. "
                    "Write 12-15 test cases. Context: error_recovery.py + related files."
                ),
            },
            {
                "phase_id": "telemetry-v6-t4-governance",
                "category": "testing",
                "complexity": "medium",
                "deliverables": ["tests/autopack/test_governance_requests_extended.py"],
                "goal": (
                    "Create extended tests for governance_requests.py. "
                    "Test: approval flow, tier escalation, auto-approval. "
                    "Write 10-12 test cases. Context: governance_requests.py + related files."
                ),
            },
            {
                "phase_id": "telemetry-v6-t5-memory-service",
                "category": "testing",
                "complexity": "medium",
                "deliverables": ["tests/autopack/memory/test_memory_service_extended.py"],
                "goal": (
                    "Create extended tests for memory_service.py. "
                    "Test: embedding storage, retrieval, similarity search. "
                    "Write 12-15 test cases. Context: memory_service.py + qdrant_store.py."
                ),
            },
            {
                "phase_id": "telemetry-v6-t6-diagnostics",
                "category": "testing",
                "complexity": "medium",
                "deliverables": ["tests/autopack/diagnostics/test_deep_retrieval_extended.py"],
                "goal": (
                    "Create extended tests for deep_retrieval.py. "
                    "Test: retrieval triggers, evidence collection, ranking. "
                    "Write 10-12 test cases. Context: deep_retrieval.py + related files."
                ),
            },
        ]

        # === IMPLEMENTATION/MEDIUM PHASES (2) ===
        # Multi-deliverable to diversify deliverable count
        impl_medium_phases = [
            {
                "phase_id": "telemetry-v6-i1-telemetry-utils",
                "category": "implementation",
                "complexity": "medium",
                "deliverables": [
                    "src/autopack/telemetry_utils.py",
                    "tests/autopack/test_telemetry_utils.py",
                    "docs/telemetry_utils_api.md"
                ],
                "goal": (
                    "Create telemetry utility module with helpers for: "
                    "sample filtering, SMAPE calculation, ratio statistics. "
                    "Include tests and brief API doc. "
                    "3 deliverables total (not 1)."
                ),
            },
            {
                "phase_id": "telemetry-v6-i2-calibration-reporter",
                "category": "implementation",
                "complexity": "medium",
                "deliverables": [
                    "src/autopack/calibration_reporter.py",
                    "tests/autopack/test_calibration_reporter.py"
                ],
                "goal": (
                    "Create calibration report generator with: "
                    "coefficient diff tracking, confidence scoring, markdown output. "
                    "Include tests. "
                    "2 deliverables total."
                ),
            },
        ]

        # Combine all phases
        all_phases = (
            docs_low_phases +
            docs_medium_phases +
            tests_medium_phases +
            impl_medium_phases
        )

        # Create phase records
        for idx, phase_spec in enumerate(all_phases, 1):
            phase = Phase(
                run_id=run.id,
                tier_id=tier.id,
                phase_id=phase_spec["phase_id"],
                phase_index=idx,
                name=phase_spec["phase_id"],
                description=phase_spec["goal"],
                state=PhaseState.QUEUED,
                task_category=phase_spec["category"],
                complexity=phase_spec["complexity"],
                scope=json.dumps({
                    "deliverables": phase_spec["deliverables"],
                }),
                created_at=datetime.now(timezone.utc),
            )
            session.add(phase)
            phases.append(phase)

            print(f"  [{idx:02d}] {phase.phase_id} ({phase_spec['category']}/{phase_spec['complexity']})")

        session.commit()

        print()
        print("=" * 70)
        print("TELEMETRY-COLLECTION-V6 CREATED")
        print("=" * 70)
        print(f"Run ID: {run.run_id}")
        print(f"Total phases: {len(phases)}")
        print()
        print("Breakdown:")
        print("  docs/low: 10 phases")
        print("  docs/medium: 2 phases")
        print("  tests/medium: 6 phases")
        print("  implementation/medium: 2 phases (multi-deliverable)")
        print()
        print("Guardrails:")
        print("  ✓ All docs phases have explicit output caps (≤150-250 lines)")
        print("  ✓ Minimal context loading (3-12 files max)")
        print("  ✓ Multi-deliverable phases to diversify deliverable count")
        print()
        print("Next steps:")
        print("  1. Drain queued phases (batch_drain_controller only works for FAILED phases):")
        print("     PowerShell:")
        print("       $env:PYTHONUTF8='1'; $env:PYTHONPATH='src'; $env:TELEMETRY_DB_ENABLED='1'")
        print("       $env:AUTOPACK_SKIP_CI='1'; $env:DATABASE_URL='sqlite:///./telemetry_seed_v6.db'")
        print("       python scripts/drain_queued_phases.py --run-id telemetry-collection-v6 `")
        print("         --batch-size 20 --max-batches 1 --no-dual-auditor --run-type autopack_maintenance")
        print("")
        print("     Bash:")
        print("       PYTHONUTF8=1 PYTHONPATH=src TELEMETRY_DB_ENABLED=1 AUTOPACK_SKIP_CI=1 \\")
        print("         DATABASE_URL='sqlite:///./telemetry_seed_v6.db' \\")
        print("         python scripts/drain_queued_phases.py --run-id telemetry-collection-v6 \\")
        print("           --batch-size 20 --max-batches 1 --no-dual-auditor --run-type autopack_maintenance")
        print()
        print("  2. After completion:")
        print("     - Re-run calibration analysis")
        print("     - Verify docs/low, docs/medium, tests/medium now have ≥5 samples")
        print("     - Generate updated coefficient recommendations")
        print("=" * 70)

    except Exception as e:
        session.rollback()
        print(f"Error: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    create_telemetry_v6_run()
