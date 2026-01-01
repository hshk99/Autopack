"""Integration test for token_efficiency_metrics unique index (Postgres-only).

BUILD-146 P17.x: Validates DB-level enforcement of idempotency for terminal outcomes.

This test runs ONLY when a Postgres DSN is explicitly provided:
- DATABASE_URL starts with "postgresql://"
- or AUTOPACK_TEST_POSTGRES=1 env var is set

Otherwise: pytest.skip(...) (no noise in CI)

Test cases:
1. Assert index exists (query pg_indexes)
2. Assert duplicates are prevented (IntegrityError on duplicate insert)

Usage:
    # Skip by default (SQLite or no Postgres):
    pytest tests/integration/test_token_efficiency_idempotency_index_postgres.py

    # Run with Postgres:
    DATABASE_URL="postgresql://..." pytest tests/integration/test_token_efficiency_idempotency_index_postgres.py

    # Or via env flag:
    AUTOPACK_TEST_POSTGRES=1 DATABASE_URL="postgresql://..." pytest tests/integration/test_token_efficiency_idempotency_index_postgres.py
"""

import os
import pytest
from pathlib import Path
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autopack.database import Base
from autopack.usage_recorder import TokenEfficiencyMetrics


def should_run_postgres_tests() -> bool:
    """Determine if Postgres integration tests should run.

    Returns:
        True if either:
        - DATABASE_URL starts with "postgresql://"
        - AUTOPACK_TEST_POSTGRES=1 is set
    """
    db_url = os.getenv("DATABASE_URL", "")
    postgres_flag = os.getenv("AUTOPACK_TEST_POSTGRES", "0").lower() in ("1", "true", "yes")

    return db_url.startswith("postgresql://") or postgres_flag


@pytest.fixture(scope="module")
def postgres_engine():
    """Create Postgres engine for integration tests.

    Skips if Postgres is not available.
    """
    if not should_run_postgres_tests():
        pytest.skip("Postgres integration test skipped (set DATABASE_URL=postgresql://... or AUTOPACK_TEST_POSTGRES=1 to run)")

    db_url = os.getenv("DATABASE_URL")
    if not db_url or not db_url.startswith("postgresql://"):
        pytest.skip("DATABASE_URL must start with 'postgresql://' for Postgres integration tests")

    engine = create_engine(db_url)

    # Ensure schema exists
    Base.metadata.create_all(engine)

    yield engine

    # Cleanup: drop test data
    # Note: We don't drop tables to avoid breaking other concurrent tests
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        # Clean up test data
        db.query(TokenEfficiencyMetrics).filter(
            TokenEfficiencyMetrics.run_id.like("test-postgres-idempotency-%")
        ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


@pytest.fixture
def postgres_session(postgres_engine):
    """Create a Postgres session for each test."""
    SessionLocal = sessionmaker(bind=postgres_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestPostgresIdempotencyIndex:
    """Integration tests for Postgres unique index enforcement."""

    def test_index_exists_in_postgres(self, postgres_engine):
        """Assert that the idempotency index exists in Postgres.

        Query pg_indexes to verify:
        - Index name: ux_token_eff_metrics_run_phase_outcome
        - Columns: run_id, phase_id, phase_outcome
        - Uniqueness: UNIQUE index
        """
        inspector = inspect(postgres_engine)
        indexes = inspector.get_indexes("token_efficiency_metrics")

        index_names = [idx["name"] for idx in indexes]
        assert "ux_token_eff_metrics_run_phase_outcome" in index_names, (
            "Missing idempotency index 'ux_token_eff_metrics_run_phase_outcome'. "
            "Run migration: python scripts/migrations/add_token_efficiency_idempotency_index_build146_p17x.py upgrade"
        )

        # Find the specific index
        idempotency_index = next(
            idx for idx in indexes
            if idx["name"] == "ux_token_eff_metrics_run_phase_outcome"
        )

        # Verify it's a unique index
        assert idempotency_index["unique"] is True, "Index should be UNIQUE"

        # Verify columns (order matters for partial unique index)
        expected_columns = ["run_id", "phase_id", "phase_outcome"]
        assert idempotency_index["column_names"] == expected_columns, (
            f"Index columns should be {expected_columns}, got {idempotency_index['column_names']}"
        )

    def test_duplicate_terminal_outcome_prevented(self, postgres_session):
        """Assert that duplicates are prevented by the unique index.

        Test scenario:
        1. Insert a row with phase_outcome='COMPLETE'
        2. Attempt to insert the same (run_id, phase_id, phase_outcome) again
        3. Expect IntegrityError (UNIQUE constraint violation)
        4. Confirm only one row exists
        """
        run_id = "test-postgres-idempotency-001"
        phase_id = "phase-001"
        phase_outcome = "COMPLETE"

        # Clean up any existing test data
        postgres_session.query(TokenEfficiencyMetrics).filter_by(
            run_id=run_id,
            phase_id=phase_id,
        ).delete(synchronize_session=False)
        postgres_session.commit()

        # Step 1: Insert initial row
        initial_row = TokenEfficiencyMetrics(
            run_id=run_id,
            phase_id=phase_id,
            artifact_substitutions=5,
            tokens_saved_artifacts=1000,
            budget_mode="semantic",
            budget_used=8000,
            budget_cap=10000,
            files_kept=10,
            files_omitted=2,
            phase_outcome=phase_outcome,
        )
        postgres_session.add(initial_row)
        postgres_session.commit()

        # Verify initial row exists
        count = postgres_session.query(TokenEfficiencyMetrics).filter_by(
            run_id=run_id,
            phase_id=phase_id,
            phase_outcome=phase_outcome,
        ).count()
        assert count == 1, "Initial insert should succeed"

        # Step 2: Attempt duplicate insert (should fail)
        duplicate_row = TokenEfficiencyMetrics(
            run_id=run_id,
            phase_id=phase_id,
            artifact_substitutions=10,  # Different values
            tokens_saved_artifacts=2000,
            budget_mode="lexical",
            budget_used=9000,
            budget_cap=12000,
            files_kept=15,
            files_omitted=3,
            phase_outcome=phase_outcome,  # Same terminal outcome
        )
        postgres_session.add(duplicate_row)

        # Step 3: Expect IntegrityError
        with pytest.raises(IntegrityError) as exc_info:
            postgres_session.commit()

        # Verify error message mentions the index
        error_msg = str(exc_info.value).lower()
        assert "ux_token_eff_metrics_run_phase_outcome" in error_msg or "unique" in error_msg, (
            f"IntegrityError should mention unique constraint or index, got: {exc_info.value}"
        )

        # Rollback the failed transaction
        postgres_session.rollback()

        # Step 4: Confirm only one row exists (duplicate was rejected)
        final_count = postgres_session.query(TokenEfficiencyMetrics).filter_by(
            run_id=run_id,
            phase_id=phase_id,
            phase_outcome=phase_outcome,
        ).count()
        assert final_count == 1, "Duplicate insert should be rejected by DB"

        # Verify original values are preserved (not overwritten)
        existing_row = postgres_session.query(TokenEfficiencyMetrics).filter_by(
            run_id=run_id,
            phase_id=phase_id,
            phase_outcome=phase_outcome,
        ).one()
        assert existing_row.artifact_substitutions == 5, "Original values should be preserved"
        assert existing_row.tokens_saved_artifacts == 1000

    def test_null_outcome_allows_duplicates(self, postgres_session):
        """Assert that NULL phase_outcome is not enforced by the index.

        The partial unique index has predicate: WHERE phase_outcome IS NOT NULL
        This means NULL outcomes are allowed to have duplicates (legacy behavior).

        Test scenario:
        1. Insert row with phase_outcome=NULL
        2. Insert another row with same (run_id, phase_id) but phase_outcome=NULL
        3. Both should succeed (NULL is not enforced)
        """
        run_id = "test-postgres-idempotency-null-001"
        phase_id = "phase-null-001"

        # Clean up any existing test data
        postgres_session.query(TokenEfficiencyMetrics).filter_by(
            run_id=run_id,
            phase_id=phase_id,
        ).delete(synchronize_session=False)
        postgres_session.commit()

        # Insert first row with NULL outcome
        row1 = TokenEfficiencyMetrics(
            run_id=run_id,
            phase_id=phase_id,
            artifact_substitutions=1,
            tokens_saved_artifacts=100,
            budget_mode="semantic",
            budget_used=5000,
            budget_cap=10000,
            files_kept=5,
            files_omitted=1,
            phase_outcome=None,  # NULL outcome
        )
        postgres_session.add(row1)
        postgres_session.commit()

        # Insert second row with same run_id, phase_id, NULL outcome
        row2 = TokenEfficiencyMetrics(
            run_id=run_id,
            phase_id=phase_id,
            artifact_substitutions=2,
            tokens_saved_artifacts=200,
            budget_mode="lexical",
            budget_used=6000,
            budget_cap=10000,
            files_kept=6,
            files_omitted=2,
            phase_outcome=None,  # NULL outcome (same as row1)
        )
        postgres_session.add(row2)
        postgres_session.commit()  # Should succeed (NULL not enforced)

        # Verify both rows exist
        count = postgres_session.query(TokenEfficiencyMetrics).filter_by(
            run_id=run_id,
            phase_id=phase_id,
            phase_outcome=None,
        ).count()
        assert count == 2, "NULL outcomes should allow duplicates (partial index predicate)"

    def test_different_outcomes_allowed(self, postgres_session):
        """Assert that different terminal outcomes are allowed for same (run_id, phase_id).

        Edge case: If a phase is retried and completes with a different outcome,
        multiple rows should be allowed (e.g., FAILED then COMPLETE on retry).

        Note: This is a theoretical edge case - in practice, phase_outcome should be
        terminal (COMPLETE, FAILED, BLOCKED, etc.) and immutable. But the DB schema
        allows it.

        Test scenario:
        1. Insert row with phase_outcome='FAILED'
        2. Insert row with same (run_id, phase_id) but phase_outcome='COMPLETE'
        3. Both should succeed (different outcomes)
        """
        run_id = "test-postgres-idempotency-different-outcomes-001"
        phase_id = "phase-retry-001"

        # Clean up any existing test data
        postgres_session.query(TokenEfficiencyMetrics).filter_by(
            run_id=run_id,
            phase_id=phase_id,
        ).delete(synchronize_session=False)
        postgres_session.commit()

        # Insert first row with FAILED outcome
        row_failed = TokenEfficiencyMetrics(
            run_id=run_id,
            phase_id=phase_id,
            artifact_substitutions=1,
            tokens_saved_artifacts=100,
            budget_mode="semantic",
            budget_used=5000,
            budget_cap=10000,
            files_kept=5,
            files_omitted=1,
            phase_outcome="FAILED",
        )
        postgres_session.add(row_failed)
        postgres_session.commit()

        # Insert second row with COMPLETE outcome (different outcome)
        row_complete = TokenEfficiencyMetrics(
            run_id=run_id,
            phase_id=phase_id,
            artifact_substitutions=2,
            tokens_saved_artifacts=200,
            budget_mode="lexical",
            budget_used=6000,
            budget_cap=10000,
            files_kept=6,
            files_omitted=2,
            phase_outcome="COMPLETE",  # Different outcome
        )
        postgres_session.add(row_complete)
        postgres_session.commit()  # Should succeed (different outcomes)

        # Verify both rows exist
        count = postgres_session.query(TokenEfficiencyMetrics).filter_by(
            run_id=run_id,
            phase_id=phase_id,
        ).count()
        assert count == 2, "Different outcomes should be allowed"

        # Verify we have one FAILED and one COMPLETE
        failed_count = postgres_session.query(TokenEfficiencyMetrics).filter_by(
            run_id=run_id,
            phase_id=phase_id,
            phase_outcome="FAILED",
        ).count()
        complete_count = postgres_session.query(TokenEfficiencyMetrics).filter_by(
            run_id=run_id,
            phase_id=phase_id,
            phase_outcome="COMPLETE",
        ).count()
        assert failed_count == 1
        assert complete_count == 1
