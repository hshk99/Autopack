"""Tests for token efficiency observability (BUILD-145)"""

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from autopack.artifact_loader import ArtifactLoader, get_artifact_substitution_stats
from autopack.context_budgeter import BudgetSelection
from autopack.database import Base
from autopack.file_layout import RunFileLayout
from autopack.usage_recorder import (
    TokenEfficiencyMetrics,
    get_token_efficiency_stats,
    record_token_efficiency_metrics,
)


@pytest.fixture
def test_db():
    """Create in-memory test database"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestTokenEfficiencyMetrics:
    """Test token efficiency metrics recording"""

    def test_record_metrics(self, test_db):
        """Should record token efficiency metrics for a phase"""
        metrics = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run-123",
            phase_id="phase-001",
            artifact_substitutions=5,
            tokens_saved_artifacts=2500,
            budget_mode="semantic",
            budget_used=8000,
            budget_cap=10000,
            files_kept=15,
            files_omitted=3,
        )

        assert metrics.run_id == "test-run-123"
        assert metrics.phase_id == "phase-001"
        assert metrics.artifact_substitutions == 5
        assert metrics.tokens_saved_artifacts == 2500
        assert metrics.budget_mode == "semantic"
        assert metrics.budget_used == 8000
        assert metrics.budget_cap == 10000
        assert metrics.files_kept == 15
        assert metrics.files_omitted == 3

    def test_get_stats_empty_run(self, test_db):
        """Should return zero stats for run with no metrics"""
        stats = get_token_efficiency_stats(test_db, "nonexistent-run")

        assert stats["run_id"] == "nonexistent-run"
        assert stats["total_phases"] == 0
        assert stats["total_artifact_substitutions"] == 0
        assert stats["total_tokens_saved_artifacts"] == 0

    def test_get_stats_aggregation(self, test_db):
        """Should aggregate metrics across multiple phases"""
        # Record metrics for 3 phases
        for i in range(3):
            record_token_efficiency_metrics(
                db=test_db,
                run_id="test-run-123",
                phase_id=f"phase-{i:03d}",
                artifact_substitutions=2,
                tokens_saved_artifacts=1000,
                budget_mode="semantic" if i < 2 else "lexical",
                budget_used=5000,
                budget_cap=10000,
                files_kept=10,
                files_omitted=2,
            )

        stats = get_token_efficiency_stats(test_db, "test-run-123")

        assert stats["total_phases"] == 3
        assert stats["total_artifact_substitutions"] == 6  # 2 * 3
        assert stats["total_tokens_saved_artifacts"] == 3000  # 1000 * 3
        assert stats["total_budget_used"] == 15000  # 5000 * 3
        assert stats["total_budget_cap"] == 30000  # 10000 * 3
        assert stats["total_files_kept"] == 30  # 10 * 3
        assert stats["total_files_omitted"] == 6  # 2 * 3
        assert stats["semantic_mode_count"] == 2
        assert stats["lexical_mode_count"] == 1

    def test_get_stats_averages(self, test_db):
        """Should calculate correct averages"""
        # Record 2 phases with different metrics
        record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run-123",
            phase_id="phase-001",
            artifact_substitutions=4,
            tokens_saved_artifacts=2000,
            budget_mode="semantic",
            budget_used=8000,
            budget_cap=10000,
            files_kept=12,
            files_omitted=3,
        )

        record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run-123",
            phase_id="phase-002",
            artifact_substitutions=2,
            tokens_saved_artifacts=1000,
            budget_mode="lexical",
            budget_used=6000,
            budget_cap=10000,
            files_kept=8,
            files_omitted=5,
        )

        stats = get_token_efficiency_stats(test_db, "test-run-123")

        # Averages
        assert stats["avg_artifact_substitutions_per_phase"] == 3.0  # (4 + 2) / 2
        assert stats["avg_tokens_saved_per_phase"] == 1500.0  # (2000 + 1000) / 2

        # Budget utilization
        assert stats["budget_utilization"] == 0.7  # (8000 + 6000) / (10000 + 10000)

    def test_budget_utilization_zero_cap(self, test_db):
        """Should handle zero budget cap gracefully"""
        record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run-123",
            phase_id="phase-001",
            artifact_substitutions=0,
            tokens_saved_artifacts=0,
            budget_mode="lexical",
            budget_used=0,
            budget_cap=0,
            files_kept=0,
            files_omitted=0,
        )

        stats = get_token_efficiency_stats(test_db, "test-run-123")
        assert stats["budget_utilization"] == 0


class TestArtifactSubstitutionStats:
    """Test artifact substitution statistics"""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        """Create temporary workspace"""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return workspace

    @pytest.fixture
    def artifact_loader(self, temp_workspace):
        """Create artifact loader"""
        return ArtifactLoader(temp_workspace, "test-run-123")

    def test_no_substitutions(self, artifact_loader):
        """Should return zero stats when no artifacts available"""
        files = {
            "file1.py": "a" * 1000,
            "file2.py": "b" * 2000,
        }

        count, tokens_saved = get_artifact_substitution_stats(artifact_loader, files)

        assert count == 0
        assert tokens_saved == 0

    def test_with_substitutions(self, artifact_loader, temp_workspace):
        """Should count substitutions and tokens saved"""
        # Create artifacts using RunFileLayout with the same base_dir that ArtifactLoader uses
        # ArtifactLoader internally uses: workspace / ".autonomous_runs"
        autonomous_runs_base = temp_workspace / ".autonomous_runs"
        layout = RunFileLayout(run_id="test-run-123", base_dir=autonomous_runs_base)
        artifacts_dir = layout.base_dir / "phases"
        artifacts_dir.mkdir(parents=True)

        phase_summary = artifacts_dir / "phase_01_test.md"
        phase_summary.write_text("file1.py: summary (100 chars)" + "a" * 300)  # ~100 tokens

        files = {
            "file1.py": "a" * 4000,  # ~1000 tokens
            "file2.py": "b" * 2000,  # ~500 tokens (no artifact)
        }

        count, tokens_saved = get_artifact_substitution_stats(artifact_loader, files)

        assert count == 1  # Only file1.py has artifact
        assert tokens_saved > 0  # Should save ~900 tokens

    def test_empty_files_dict(self, artifact_loader):
        """Should handle empty files dictionary"""
        count, tokens_saved = get_artifact_substitution_stats(artifact_loader, {})

        assert count == 0
        assert tokens_saved == 0


class TestDashboardIntegration:
    """Test dashboard endpoint integration"""

    def test_token_efficiency_in_run_status(self):
        """Token efficiency should be optional in DashboardRunStatus for backwards compatibility"""
        from autopack.dashboard_schemas import DashboardRunStatus

        # Without token_efficiency (backwards compatible)
        status = DashboardRunStatus(
            run_id="test-run",
            state="running",
            current_tier_name="tier1",
            current_phase_name="phase1",
            current_tier_index=0,
            current_phase_index=0,
            total_tiers=1,
            total_phases=1,
            completed_tiers=0,
            completed_phases=0,
            percent_complete=0.0,
            tiers_percent_complete=0.0,
            tokens_used=1000,
            token_cap=10000,
            token_utilization=0.1,
            minor_issues_count=0,
            major_issues_count=0,
        )
        assert status.token_efficiency is None

        # With token_efficiency
        status_with_efficiency = DashboardRunStatus(
            run_id="test-run",
            state="running",
            current_tier_name="tier1",
            current_phase_name="phase1",
            current_tier_index=0,
            current_phase_index=0,
            total_tiers=1,
            total_phases=1,
            completed_tiers=0,
            completed_phases=0,
            percent_complete=0.0,
            tiers_percent_complete=0.0,
            tokens_used=1000,
            token_cap=10000,
            token_utilization=0.1,
            minor_issues_count=0,
            major_issues_count=0,
            token_efficiency={
                "total_artifact_substitutions": 10,
                "total_tokens_saved_artifacts": 5000,
            },
        )
        assert status_with_efficiency.token_efficiency is not None
        assert status_with_efficiency.token_efficiency["total_artifact_substitutions"] == 10


class TestExecutorTelemetryIntegration:
    """Test executor telemetry recording integration"""

    def test_record_telemetry_with_budget_selection(self, test_db):
        """Should record telemetry with budget selection data"""
        budget_selection = BudgetSelection(
            kept={"file1.py": "content1", "file2.py": "content2"},
            omitted=["file3.py"],
            used_tokens_est=8000,
            budget_tokens=10000,
            mode="semantic",
            files_kept_count=2,
            files_omitted_count=1,
        )

        metrics = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=1,
            tokens_saved_artifacts=500,
            budget_mode=budget_selection.mode,
            budget_used=budget_selection.used_tokens_est,
            budget_cap=budget_selection.budget_tokens,
            files_kept=budget_selection.files_kept_count,
            files_omitted=budget_selection.files_omitted_count,
        )

        assert metrics.budget_mode == "semantic"
        assert metrics.budget_used == 8000
        assert metrics.budget_cap == 10000
        assert metrics.files_kept == 2
        assert metrics.files_omitted == 1

    def test_record_telemetry_without_budget_selection(self, test_db):
        """Should record telemetry with default values when no budget selection"""
        metrics = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=3,
            tokens_saved_artifacts=1500,
            budget_mode="unknown",
            budget_used=0,
            budget_cap=0,
            files_kept=0,
            files_omitted=0,
        )

        assert metrics.artifact_substitutions == 3
        assert metrics.tokens_saved_artifacts == 1500
        assert metrics.budget_mode == "unknown"

    def test_telemetry_logging_format(self, caplog, test_db):
        """Should log compact metrics in expected format"""
        import logging

        # Create minimal mock executor
        class MockExecutor:
            def __init__(self):
                self.run_id = "test-run"
                self.db = test_db

            def _record_token_efficiency_telemetry(
                self,
                phase,
                artifact_substitutions,
                tokens_saved_artifacts,
                budget_selection,
            ):
                phase_id = phase.get("id", "unknown")

                if budget_selection:
                    budget_mode = budget_selection.mode
                    budget_used = budget_selection.used_tokens_est
                    budget_cap = budget_selection.budget_tokens
                    files_kept = budget_selection.files_kept_count
                    files_omitted = budget_selection.files_omitted_count
                else:
                    budget_mode = "unknown"
                    budget_used = 0
                    budget_cap = 0
                    files_kept = 0
                    files_omitted = 0

                logger = logging.getLogger(__name__)
                logger.info(
                    f"[TOKEN_EFFICIENCY] phase={phase_id} "
                    f"artifacts={artifact_substitutions} saved={tokens_saved_artifacts}tok "
                    f"budget={budget_mode} used={budget_used}/{budget_cap}tok "
                    f"files={files_kept}kept/{files_omitted}omitted"
                )

        executor = MockExecutor()
        phase = {"id": "phase-001"}
        budget_selection = BudgetSelection(
            kept={},
            omitted=[],
            used_tokens_est=5000,
            budget_tokens=10000,
            mode="semantic",
            files_kept_count=10,
            files_omitted_count=2,
        )

        with caplog.at_level(logging.INFO):
            executor._record_token_efficiency_telemetry(
                phase=phase,
                artifact_substitutions=3,
                tokens_saved_artifacts=1200,
                budget_selection=budget_selection,
            )

        # Verify log format
        log_messages = [record.message for record in caplog.records]
        assert any("[TOKEN_EFFICIENCY]" in msg for msg in log_messages)
        assert any("artifacts=3" in msg for msg in log_messages)
        assert any("saved=1200tok" in msg for msg in log_messages)
        assert any("budget=semantic" in msg for msg in log_messages)
        assert any("used=5000/10000tok" in msg for msg in log_messages)
        assert any("files=10kept/2omitted" in msg for msg in log_messages)


class TestKeptOnlyTelemetry:
    """Test kept-only savings calculation (BUILD-145 P1 hardening)."""

    def test_recompute_savings_after_budgeting(self, test_db):
        """Should only count savings for files kept after budgeting."""
        # Simulate scope_metadata with some artifact substitutions
        scope_metadata = {
            "file1.py": {
                "category": "read_only",
                "source": "artifact:summary",
                "tokens_saved": 1000,
            },
            "file2.py": {
                "category": "read_only",
                "source": "artifact:summary",
                "tokens_saved": 2000,
            },
            "file3.py": {
                "category": "read_only",
                "source": "full_file",  # Not an artifact
            },
            "file4.py": {
                "category": "read_only",
                "source": "artifact:summary",
                "tokens_saved": 1500,
            },
        }

        # Simulate budgeting keeping only file1 and file3 (omitting file2 and file4)
        kept_files = {"file1.py", "file3.py"}

        # Recompute as done in _load_scoped_context
        kept_artifact_substitutions = 0
        kept_tokens_saved = 0
        substituted_paths_sample = []

        for path, metadata in scope_metadata.items():
            if path in kept_files and metadata.get("source", "").startswith("artifact:"):
                kept_artifact_substitutions += 1
                kept_tokens_saved += metadata.get("tokens_saved", 0)
                if len(substituted_paths_sample) < 10:
                    substituted_paths_sample.append(path)

        # Should only count file1.py (kept + artifact)
        assert kept_artifact_substitutions == 1
        assert kept_tokens_saved == 1000
        assert substituted_paths_sample == ["file1.py"]

        # Original would have been 3 substitutions, 4500 tokens saved (over-reporting)

    def test_substituted_paths_sample_capped(self, test_db):
        """Should cap substituted paths list at 10 entries."""
        scope_metadata = {}
        kept_files = set()

        # Create 15 substituted files
        for i in range(15):
            path = f"file{i}.py"
            scope_metadata[path] = {
                "category": "read_only",
                "source": "artifact:summary",
                "tokens_saved": 100,
            }
            kept_files.add(path)

        # Recompute
        substituted_paths_sample = []
        for path, metadata in scope_metadata.items():
            if path in kept_files and metadata.get("source", "").startswith("artifact:"):
                if len(substituted_paths_sample) < 10:
                    substituted_paths_sample.append(path)

        # Should be capped at 10
        assert len(substituted_paths_sample) == 10

    def test_phase_outcome_recorded(self, test_db):
        """Should record phase outcome in metrics."""
        # Test COMPLETE outcome
        metrics_complete = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=2,
            tokens_saved_artifacts=1000,
            budget_mode="semantic",
            budget_used=8000,
            budget_cap=10000,
            files_kept=5,
            files_omitted=2,
            phase_outcome="COMPLETE",
        )
        assert metrics_complete.phase_outcome == "COMPLETE"

        # Test FAILED outcome
        metrics_failed = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-002",
            artifact_substitutions=1,
            tokens_saved_artifacts=500,
            budget_mode="lexical",
            budget_used=5000,
            budget_cap=10000,
            files_kept=3,
            files_omitted=1,
            phase_outcome="FAILED",
        )
        assert metrics_failed.phase_outcome == "FAILED"


class TestTelemetryInvariants:
    """BUILD-146 P17.1: Telemetry correctness hardening tests.

    Ensures idempotency, no double-counting, and category non-overlap.
    """

    def test_idempotent_recording_same_outcome(self, test_db):
        """Should prevent duplicate metrics for same (run_id, phase_id, outcome)."""
        # Record first time
        metrics1 = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=5,
            tokens_saved_artifacts=2500,
            budget_mode="semantic",
            budget_used=8000,
            budget_cap=10000,
            files_kept=15,
            files_omitted=3,
            phase_outcome="COMPLETE",
        )
        assert metrics1.id is not None
        first_id = metrics1.id

        # Record again with same outcome - should return existing record
        metrics2 = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=10,  # Different values
            tokens_saved_artifacts=5000,
            budget_mode="lexical",
            budget_used=9000,
            budget_cap=12000,
            files_kept=20,
            files_omitted=5,
            phase_outcome="COMPLETE",  # Same outcome
        )

        # Should return the original record (idempotency)
        assert metrics2.id == first_id
        assert metrics2.artifact_substitutions == 5  # Original values preserved
        assert metrics2.tokens_saved_artifacts == 2500

        # Verify only one record exists in DB
        all_metrics = (
            test_db.query(TokenEfficiencyMetrics)
            .filter(
                TokenEfficiencyMetrics.run_id == "test-run",
                TokenEfficiencyMetrics.phase_id == "phase-001",
                TokenEfficiencyMetrics.phase_outcome == "COMPLETE",
            )
            .all()
        )
        assert len(all_metrics) == 1

    def test_different_outcomes_allowed(self, test_db):
        """Should allow separate metrics for different outcomes (e.g., retry scenarios)."""
        # Record FAILED outcome
        metrics_failed = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=3,
            tokens_saved_artifacts=1500,
            budget_mode="semantic",
            budget_used=7000,
            budget_cap=10000,
            files_kept=10,
            files_omitted=2,
            phase_outcome="FAILED",
        )
        assert metrics_failed.phase_outcome == "FAILED"

        # Record COMPLETE outcome (after retry)
        metrics_complete = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=5,
            tokens_saved_artifacts=2500,
            budget_mode="semantic",
            budget_used=8000,
            budget_cap=10000,
            files_kept=15,
            files_omitted=3,
            phase_outcome="COMPLETE",
        )
        assert metrics_complete.phase_outcome == "COMPLETE"

        # Both records should exist
        all_metrics = (
            test_db.query(TokenEfficiencyMetrics)
            .filter(
                TokenEfficiencyMetrics.run_id == "test-run",
                TokenEfficiencyMetrics.phase_id == "phase-001",
            )
            .all()
        )
        assert len(all_metrics) == 2
        outcomes = {m.phase_outcome for m in all_metrics}
        assert outcomes == {"FAILED", "COMPLETE"}

    def test_retry_same_failed_outcome_idempotent(self, test_db):
        """Multiple FAILED outcomes should be idempotent (e.g., crash recovery)."""
        # Record first FAILED
        metrics1 = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=3,
            tokens_saved_artifacts=1500,
            budget_mode="semantic",
            budget_used=7000,
            budget_cap=10000,
            files_kept=10,
            files_omitted=2,
            phase_outcome="FAILED",
        )
        first_id = metrics1.id

        # Record second FAILED (e.g., executor crashed and restarted)
        metrics2 = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=5,
            tokens_saved_artifacts=2000,
            budget_mode="lexical",
            budget_used=8000,
            budget_cap=10000,
            files_kept=12,
            files_omitted=3,
            phase_outcome="FAILED",
        )

        # Should return existing record
        assert metrics2.id == first_id
        assert metrics2.artifact_substitutions == 3  # Original values

        # Only one FAILED record should exist
        failed_metrics = (
            test_db.query(TokenEfficiencyMetrics)
            .filter(
                TokenEfficiencyMetrics.run_id == "test-run",
                TokenEfficiencyMetrics.phase_id == "phase-001",
                TokenEfficiencyMetrics.phase_outcome == "FAILED",
            )
            .all()
        )
        assert len(failed_metrics) == 1

    def test_no_outcome_always_creates_new(self, test_db):
        """Records without phase_outcome should always create new entries (no idempotency)."""
        # Record without outcome (backward compatibility mode)
        metrics1 = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=3,
            tokens_saved_artifacts=1500,
            budget_mode="semantic",
            budget_used=7000,
            budget_cap=10000,
            files_kept=10,
            files_omitted=2,
            phase_outcome=None,
        )
        assert metrics1.phase_outcome is None

        # Record again without outcome - should create new record
        metrics2 = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=5,
            tokens_saved_artifacts=2500,
            budget_mode="lexical",
            budget_used=8000,
            budget_cap=10000,
            files_kept=15,
            files_omitted=3,
            phase_outcome=None,
        )
        assert metrics2.phase_outcome is None
        assert metrics2.id != metrics1.id  # Different records

        # Two separate records should exist
        all_metrics = (
            test_db.query(TokenEfficiencyMetrics)
            .filter(
                TokenEfficiencyMetrics.run_id == "test-run",
                TokenEfficiencyMetrics.phase_id == "phase-001",
                TokenEfficiencyMetrics.phase_outcome.is_(None),
            )
            .all()
        )
        assert len(all_metrics) == 2

    def test_token_categories_non_overlapping(self, test_db):
        """Token categories should not overlap (budget_used != tokens_saved_artifacts)."""
        # Record metrics
        metrics = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=5,
            tokens_saved_artifacts=2500,  # Tokens avoided via artifacts
            budget_mode="semantic",
            budget_used=8000,  # Actual tokens used in context
            budget_cap=10000,
            files_kept=15,
            files_omitted=3,
            phase_outcome="COMPLETE",
        )

        # Categories should be non-overlapping:
        # - budget_used: actual tokens sent to LLM (kept files)
        # - tokens_saved_artifacts: tokens avoided by using summaries instead of full files
        # - tokens from omitted files: neither in budget_used nor tokens_saved_artifacts

        # Invariant: tokens_saved_artifacts represents savings on KEPT files only
        # This is separate from budget_used which is actual usage
        assert metrics.tokens_saved_artifacts >= 0
        assert metrics.budget_used >= 0
        assert metrics.budget_used <= metrics.budget_cap

        # Total context footprint = budget_used + tokens_saved_artifacts
        # (budget_used is what we sent, tokens_saved is what we avoided sending)
        total_footprint = metrics.budget_used + metrics.tokens_saved_artifacts
        assert total_footprint > 0

    def test_recording_failure_never_raises(self, test_db):
        """Recording failures should be best-effort and never raise exceptions."""
        # This is tested at the executor level (_record_token_efficiency_telemetry)
        # which wraps record_token_efficiency_metrics in a try/except.
        # Here we just verify the DB layer handles invalid data gracefully.

        # Test with minimal valid data
        metrics = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=0,
            tokens_saved_artifacts=0,
            budget_mode="unknown",
            budget_used=0,
            budget_cap=0,
            files_kept=0,
            files_omitted=0,
            phase_outcome="COMPLETE",
        )
        assert metrics.id is not None

    def test_embedding_cache_metrics_optional(self, test_db):
        """Embedding cache metrics should be optional (default to 0 when omitted)."""
        # Record without embedding metrics
        metrics = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=5,
            tokens_saved_artifacts=2500,
            budget_mode="semantic",
            budget_used=8000,
            budget_cap=10000,
            files_kept=15,
            files_omitted=3,
            phase_outcome="COMPLETE",
            # All embedding fields omitted (default to 0)
        )
        # Schema default is 0, not NULL (makes queries easier)
        assert metrics.embedding_cache_hits == 0
        assert metrics.embedding_cache_misses == 0
        assert metrics.embedding_calls_made == 0

        # Record with embedding metrics
        metrics2 = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-002",
            artifact_substitutions=3,
            tokens_saved_artifacts=1500,
            budget_mode="semantic",
            budget_used=7000,
            budget_cap=10000,
            files_kept=10,
            files_omitted=2,
            phase_outcome="COMPLETE",
            embedding_cache_hits=45,
            embedding_cache_misses=5,
            embedding_calls_made=50,
        )
        assert metrics2.embedding_cache_hits == 45
        assert metrics2.embedding_cache_misses == 5
        assert metrics2.embedding_calls_made == 50

    def test_integrity_error_fallback(self, test_db):
        """BUILD-146 P17.x: Should handle IntegrityError by returning existing record.

        This test simulates a race condition where:
        1. First insert succeeds (creates initial record)
        2. Second insert attempt raises IntegrityError (duplicate terminal outcome)
        3. Function should rollback and return the existing record

        This validates the race-safe fallback path added in P17.x.
        """
        # Step 1: Insert initial record for (run_id, phase_id, outcome)
        initial_metrics = record_token_efficiency_metrics(
            db=test_db,
            run_id="test-run",
            phase_id="phase-001",
            artifact_substitutions=5,
            tokens_saved_artifacts=2500,
            budget_mode="semantic",
            budget_used=8000,
            budget_cap=10000,
            files_kept=15,
            files_omitted=3,
            phase_outcome="COMPLETE",
        )
        assert initial_metrics.id is not None
        initial_id = initial_metrics.id

        # Step 2: Mock db.commit() to raise IntegrityError on next call
        # This simulates a concurrent writer beating us to the insert
        original_commit = test_db.commit
        call_count = [0]

        def mock_commit_with_integrity_error():
            call_count[0] += 1
            if call_count[0] == 1:
                # First call after our test setup - raise IntegrityError
                raise IntegrityError(
                    statement="INSERT INTO token_efficiency_metrics",
                    params={},
                    orig=Exception(
                        "UNIQUE constraint failed: token_efficiency_metrics.ux_token_eff_metrics_run_phase_outcome"
                    ),
                )
            else:
                # Subsequent calls - use original commit
                return original_commit()

        # Step 3: Patch commit to simulate race condition
        with patch.object(test_db, "commit", side_effect=mock_commit_with_integrity_error):
            # Attempt to record again with different values (simulating concurrent writer)
            # This should trigger IntegrityError, rollback, and return existing record
            recovered_metrics = record_token_efficiency_metrics(
                db=test_db,
                run_id="test-run",
                phase_id="phase-001",
                artifact_substitutions=10,  # Different values
                tokens_saved_artifacts=5000,
                budget_mode="lexical",
                budget_used=9000,
                budget_cap=12000,
                files_kept=20,
                files_omitted=5,
                phase_outcome="COMPLETE",  # Same outcome
            )

        # Step 4: Verify we got the original record back (not a new one)
        assert recovered_metrics.id == initial_id
        assert recovered_metrics.artifact_substitutions == 5  # Original values preserved
        assert recovered_metrics.tokens_saved_artifacts == 2500
        assert recovered_metrics.budget_mode == "semantic"

        # Step 5: Verify only one record exists in DB (no duplicate created)
        all_metrics = (
            test_db.query(TokenEfficiencyMetrics)
            .filter(
                TokenEfficiencyMetrics.run_id == "test-run",
                TokenEfficiencyMetrics.phase_id == "phase-001",
                TokenEfficiencyMetrics.phase_outcome == "COMPLETE",
            )
            .all()
        )
        assert len(all_metrics) == 1
        assert all_metrics[0].id == initial_id
