"""Tests for token efficiency observability (BUILD-145)"""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from autopack.usage_recorder import (
    record_token_efficiency_metrics,
    get_token_efficiency_stats,
    TokenEfficiencyMetrics,
)
from autopack.artifact_loader import ArtifactLoader, get_artifact_substitution_stats
from autopack.context_budgeter import BudgetSelection
from autopack.database import Base, get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


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
        # Create artifacts
        artifacts_dir = temp_workspace / ".autonomous_runs" / "test-run-123" / "phases"
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