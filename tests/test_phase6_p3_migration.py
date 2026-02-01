"""
BUILD-146 P3: CI tests for Phase 6 migration and endpoint

Tests:
1. Migration idempotence (can run upgrade twice safely)
2. Phase6 stats endpoint works on fresh DB
3. Median estimation function returns valid results
4. Coverage tracking fields are populated correctly
"""

import os
# Import migration functions
import sys
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "migrations"))
from add_phase6_metrics_build146 import check_table_exists
from add_phase6_metrics_build146 import upgrade as base_upgrade
from add_phase6_p3_fields import check_column_exists
from add_phase6_p3_fields import upgrade as p3_upgrade


def test_migration_idempotence():
    """Test that running migration twice doesn't fail"""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db_url = f"sqlite:///{db_path}"
        engine = create_engine(db_url)

        # Run base migration
        base_upgrade(engine)
        assert check_table_exists(engine, "phase6_metrics")

        # Run base migration again (should be idempotent)
        base_upgrade(engine)
        assert check_table_exists(engine, "phase6_metrics")

        # Run P3 migration
        p3_upgrade(engine)
        assert check_column_exists(engine, "phase6_metrics", "doctor_tokens_avoided_estimate")
        assert check_column_exists(engine, "phase6_metrics", "estimate_coverage_n")
        assert check_column_exists(engine, "phase6_metrics", "estimate_source")

        # Run P3 migration again (should be idempotent)
        p3_upgrade(engine)
        assert check_column_exists(engine, "phase6_metrics", "doctor_tokens_avoided_estimate")

        # Dispose engine to release file handle (Windows compatibility)
        engine.dispose()

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_phase6_stats_endpoint_fresh_db():
    """Test that phase6-stats endpoint works on fresh DB"""
    from autopack.database import Base
    from autopack.models import Run
    from autopack.usage_recorder import get_phase6_metrics_summary

    # Use in-memory DB for test
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(test_engine)

    # Apply migrations
    base_upgrade(test_engine)
    p3_upgrade(test_engine)

    from sqlalchemy.orm import sessionmaker

    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    try:
        # Create a test run
        run = Run(id="test-run-p3")
        db.add(run)
        db.commit()

        # Get metrics (should return empty but not error)
        metrics = get_phase6_metrics_summary(db, "test-run-p3")

        assert metrics is not None
        assert metrics["total_phases"] == 0
        assert metrics["total_doctor_tokens_avoided_estimate"] == 0
        assert metrics["estimate_coverage_stats"] == {}

    finally:
        db.close()


def test_median_estimation_function():
    """Test that estimate_doctor_tokens_avoided returns valid results"""
    from autopack.database import Base
    from autopack.models import Run
    from autopack.usage_recorder import (UsageEventData,
                                         estimate_doctor_tokens_avoided,
                                         record_usage)

    # Use in-memory DB for test
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(test_engine)

    from sqlalchemy.orm import sessionmaker

    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    try:
        # Create a test run
        run = Run(id="test-run-estimation")
        db.add(run)
        db.commit()

        # Test 1: No baseline data (should return fallback)
        estimate, coverage_n, source = estimate_doctor_tokens_avoided(db, "test-run-estimation")
        assert estimate > 0  # Should be fallback (10k-15k range)
        assert coverage_n == 0
        assert source == "fallback"

        # Test 2: Add some Doctor call samples (run-local)
        for tokens in [8000, 10000, 12000, 15000, 20000]:
            record_usage(
                db,
                UsageEventData(
                    provider="anthropic",
                    model="claude-3-5-haiku-20241022",
                    run_id="test-run-estimation",
                    phase_id="test-phase",
                    role="doctor",
                    total_tokens=tokens,
                    prompt_tokens=tokens // 2,
                    completion_tokens=tokens // 2,
                    is_doctor_call=True,
                    doctor_model="cheap",
                    doctor_action="retry_with_fix",
                ),
            )

        # Now should use run-local median
        estimate, coverage_n, source = estimate_doctor_tokens_avoided(db, "test-run-estimation")
        assert estimate == 12000  # Median of [8000, 10000, 12000, 15000, 20000]
        assert coverage_n == 5
        assert source == "run_local"

        # Test 3: Different run should fall back to global
        estimate, coverage_n, source = estimate_doctor_tokens_avoided(db, "different-run")
        assert estimate == 12000  # Should use global baseline (same samples)
        assert coverage_n == 5
        assert source == "global"

    finally:
        db.close()


def test_coverage_fields_populated():
    """Test that coverage fields are populated when recording metrics"""
    from autopack.database import Base
    from autopack.models import Run
    from autopack.usage_recorder import Phase6Metrics, record_phase6_metrics

    # Use in-memory DB for test
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(test_engine)

    # Apply migrations
    base_upgrade(test_engine)
    p3_upgrade(test_engine)

    from sqlalchemy.orm import sessionmaker

    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    try:
        # Create a test run
        run = Run(id="test-run-coverage")
        db.add(run)
        db.commit()

        # Record metrics with coverage info
        metrics = record_phase6_metrics(
            db=db,
            run_id="test-run-coverage",
            phase_id="test-phase-1",
            doctor_call_skipped=True,
            doctor_tokens_avoided_estimate=12000,
            estimate_coverage_n=5,
            estimate_source="run_local",
        )

        assert metrics.doctor_tokens_avoided_estimate == 12000
        assert metrics.estimate_coverage_n == 5
        assert metrics.estimate_source == "run_local"

        # Verify it's in DB
        saved = (
            db.query(Phase6Metrics)
            .filter(
                Phase6Metrics.run_id == "test-run-coverage",
                Phase6Metrics.phase_id == "test-phase-1",
            )
            .first()
        )

        assert saved is not None
        assert saved.doctor_tokens_avoided_estimate == 12000
        assert saved.estimate_coverage_n == 5
        assert saved.estimate_source == "run_local"

    finally:
        db.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
