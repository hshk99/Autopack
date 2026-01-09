"""
Database cleanup for BUILD-130, BUILD-132, and BUILD-129 test runs.

Based on FAILED_PHASES_ASSESSMENT.md:
- BUILD-132: Work completed manually on 2025-12-23, update failure_reason to document completion
- BUILD-130: Work completed manually on 2025-12-23/24, update failure_reason to document completion
- BUILD-129 test runs: Update failure_reason to document test/validation purpose

Following "other cursor" advice: Don't change states to hide operational failures.
Use failure_reason field to document manual completion while preserving failure metrics.

Note: Phase and Run models don't have 'notes' field. Using failure_reason instead.
"""
from autopack.database import SessionLocal
from autopack.models import Run

def main():
    session = SessionLocal()

    try:
        # BUILD-132: Coverage Delta Integration (manually completed Dec 23)
        print("\n=== BUILD-132: Coverage Delta Integration ===")
        build132_run = session.query(Run).filter(
            Run.id == 'build132-coverage-delta-integration'
        ).first()

        if build132_run:
            print(f"Run {build132_run.id}: {build132_run.state} (updating failure_reason)")
            build132_run.failure_reason = (
                "[MANUAL COMPLETION] All phases failed in autonomous execution, but work completed manually on 2025-12-23. "
                "Deliverables: pytest.ini with coverage, coverage_tracker.py, autonomous_executor.py Quality Gate integration. "
                "See BUILD_LOG.md and BUILD-132_IMPLEMENTATION_STATUS.md for details. "
                "State preserved as FAILED to maintain accurate failure metrics."
            )

        # BUILD-130: Schema Validation Prevention (manually completed Dec 23-24)
        print("\n=== BUILD-130: Schema Validation Prevention ===")
        build130_run = session.query(Run).filter(
            Run.id == 'build130-schema-validation-prevention'
        ).first()

        if build130_run:
            print(f"Run {build130_run.id}: {build130_run.state} (updating failure_reason)")
            build130_run.failure_reason = (
                "[MANUAL COMPLETION] Phases queued but never executed - deliverables created manually on 2025-12-23/24. "
                "Deliverables exist: circuit_breaker.py (9398 bytes), circuit_breaker_registry.py, schema_validator.py (8949 bytes), "
                "break_glass_repair.py (6275 bytes), tests, examples, docs. "
                "See FAILED_PHASES_ASSESSMENT.md. Protected paths prevented autonomous execution."
            )

        # BUILD-129: Document test/validation runs (keep for reproducibility)
        print("\n=== BUILD-129: Test/Validation Runs ===")
        test_run_ids = [
            'build129-p2-validation',
            'build129-p3-week1-telemetry',
            'telemetry-test-single'
        ]

        for run_id in test_run_ids:
            run = session.query(Run).filter(Run.id == run_id).first()
            if run:
                print(f"Run {run_id}: {run.state} (updating failure_reason)")
                run.failure_reason = (
                    "[TEST/VALIDATION RUN] Created for BUILD-129 Phase 3 telemetry collection validation. "
                    "Purpose: Collect diverse telemetry samples to validate overhead model. "
                    "Outcome: Operational blockers (protected paths, telemetry persistence to stderr vs database). "
                    "Preserved as reproducible telemetry baseline - DO NOT DELETE. "
                    "See BUILD-129_PHASE3_EXECUTION_SUMMARY.md."
                )

        session.commit()

        print("\n" + "=" * 80)
        print("✅ Database cleanup complete")
        print("\nSummary:")
        if build132_run:
            print(f"  BUILD-132: Run failure_reason updated (state: {build132_run.state})")
        if build130_run:
            print(f"  BUILD-130: Run failure_reason updated (state: {build130_run.state})")
        print(f"  BUILD-129: {len(test_run_ids)} test runs documented")

    except Exception as e:
        session.rollback()
        print(f"\n❌ Error during cleanup: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    main()
