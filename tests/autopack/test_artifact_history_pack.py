"""BUILD-145 P2: Tests for extended artifact-first substitution

Tests history pack generation and SOT doc substitution.
"""

import pytest
from pathlib import Path
import json

from autopack.artifact_loader import ArtifactLoader, estimate_tokens
from autopack.file_layout import RunFileLayout
from autopack.config import settings


class TestHistoryPack:
    """Test history pack generation"""

    @pytest.fixture
    def temp_workspace(self, tmp_path):
        """Create temporary workspace with artifacts directory"""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return workspace

    @pytest.fixture
    def artifact_loader(self, temp_workspace):
        """Create artifact loader with test run ID"""
        return ArtifactLoader(temp_workspace, "test-run-123")

    @pytest.fixture
    def artifacts_dir(self, temp_workspace):
        """Create and return artifacts directory"""
        artifacts = temp_workspace / ".autonomous_runs" / "test-run-123"
        artifacts.mkdir(parents=True)
        return artifacts

    @pytest.fixture
    def file_layout(self, temp_workspace):
        """Create file layout for test run"""
        return RunFileLayout("test-run-123", base_dir=temp_workspace / ".autonomous_runs")

    def test_history_pack_disabled_by_default(self, artifact_loader):
        """History pack should be disabled by default"""
        # Ensure setting is disabled
        original = settings.artifact_history_pack_enabled
        settings.artifact_history_pack_enabled = False

        try:
            result = artifact_loader.build_history_pack()
            assert result is None
        finally:
            settings.artifact_history_pack_enabled = original

    def test_history_pack_no_artifacts(self, artifact_loader):
        """Should return None when no artifacts exist"""
        original = settings.artifact_history_pack_enabled
        settings.artifact_history_pack_enabled = True

        try:
            result = artifact_loader.build_history_pack()
            assert result is None
        finally:
            settings.artifact_history_pack_enabled = original

    def test_history_pack_with_run_summary(self, artifact_loader, artifacts_dir):
        """Should include run summary in history pack"""
        original = settings.artifact_history_pack_enabled
        settings.artifact_history_pack_enabled = True

        try:
            run_summary = artifacts_dir / "run_summary.md"
            run_summary.write_text("# Run Summary\n\nTest run summary content")

            result = artifact_loader.build_history_pack()
            assert result is not None
            assert "# Run Summary" in result
            assert "Test run summary content" in result
        finally:
            settings.artifact_history_pack_enabled = original

    def test_history_pack_with_tier_summaries(self, artifact_loader, artifacts_dir):
        """Should include recent tier summaries in history pack"""
        original_enabled = settings.artifact_history_pack_enabled
        original_max_tiers = settings.artifact_history_pack_max_tiers
        settings.artifact_history_pack_enabled = True
        settings.artifact_history_pack_max_tiers = 2

        try:
            tiers_dir = artifacts_dir / "tiers"
            tiers_dir.mkdir()

            tier1 = tiers_dir / "tier_01_backend.md"
            tier1.write_text("# Tier 1\n\nBackend tier content")

            tier2 = tiers_dir / "tier_02_frontend.md"
            tier2.write_text("# Tier 2\n\nFrontend tier content")

            tier3 = tiers_dir / "tier_03_database.md"
            tier3.write_text("# Tier 3\n\nDatabase tier content")

            result = artifact_loader.build_history_pack()
            assert result is not None
            # Should include only 2 most recent tiers (tier_03, tier_02)
            assert "Database tier content" in result
            assert "Frontend tier content" in result
            # Should not include tier_01 (exceeds max_tiers limit)
            assert "Backend tier content" not in result
        finally:
            settings.artifact_history_pack_enabled = original_enabled
            settings.artifact_history_pack_max_tiers = original_max_tiers

    def test_history_pack_with_phase_summaries(self, artifact_loader, artifacts_dir):
        """Should include recent phase summaries in history pack"""
        original_enabled = settings.artifact_history_pack_enabled
        original_max_phases = settings.artifact_history_pack_max_phases
        settings.artifact_history_pack_enabled = True
        settings.artifact_history_pack_max_phases = 3

        try:
            phases_dir = artifacts_dir / "phases"
            phases_dir.mkdir()

            for i in range(1, 6):
                phase = phases_dir / f"phase_{i:02d}_test.md"
                phase.write_text(f"# Phase {i}\n\nPhase {i} content")

            result = artifact_loader.build_history_pack()
            assert result is not None
            # Should include only 3 most recent phases (phase_05, phase_04, phase_03)
            assert "Phase 5 content" in result
            assert "Phase 4 content" in result
            assert "Phase 3 content" in result
            # Should not include phase_01, phase_02 (exceed max_phases limit)
            assert "Phase 1 content" not in result
            assert "Phase 2 content" not in result
        finally:
            settings.artifact_history_pack_enabled = original_enabled
            settings.artifact_history_pack_max_phases = original_max_phases

    def test_history_pack_sections_separated(self, artifact_loader, artifacts_dir):
        """History pack sections should be separated by dividers"""
        original = settings.artifact_history_pack_enabled
        settings.artifact_history_pack_enabled = True

        try:
            run_summary = artifacts_dir / "run_summary.md"
            run_summary.write_text("Run summary")

            tiers_dir = artifacts_dir / "tiers"
            tiers_dir.mkdir()
            tier1 = tiers_dir / "tier_01_test.md"
            tier1.write_text("Tier summary")

            result = artifact_loader.build_history_pack()
            assert result is not None
            # Sections should be separated by ---
            assert "---" in result
        finally:
            settings.artifact_history_pack_enabled = original

    def test_file_layout_history_pack_path(self, file_layout):
        """File layout should provide history pack path"""
        path = file_layout.get_history_pack_path()
        assert path.name == "history_pack.md"
        assert "test-run-123" in str(path)

    def test_file_layout_write_history_pack(self, file_layout, temp_workspace):
        """File layout should write history pack file"""
        file_layout.ensure_directories()
        content = "# History Pack\n\nTest content"
        file_layout.write_history_pack(content)

        path = file_layout.get_history_pack_path()
        assert path.exists()
        assert path.read_text() == content


class TestSOTDocSubstitution:
    """Test SOT doc substitution"""

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

    def test_sot_doc_substitution_disabled_by_default(self, artifact_loader):
        """SOT doc substitution should be disabled by default"""
        original = settings.artifact_substitute_sot_docs
        settings.artifact_substitute_sot_docs = False

        try:
            assert not artifact_loader.should_substitute_sot_doc("docs/BUILD_HISTORY.md")
        finally:
            settings.artifact_substitute_sot_docs = original

    def test_should_substitute_build_history(self, artifact_loader):
        """Should identify BUILD_HISTORY as SOT doc"""
        original = settings.artifact_substitute_sot_docs
        settings.artifact_substitute_sot_docs = True

        try:
            assert artifact_loader.should_substitute_sot_doc("docs/BUILD_HISTORY.md")
            assert artifact_loader.should_substitute_sot_doc(".autonomous_runs/BUILD_HISTORY.md")
        finally:
            settings.artifact_substitute_sot_docs = original

    def test_should_substitute_build_log(self, artifact_loader):
        """Should identify BUILD_LOG as SOT doc"""
        original = settings.artifact_substitute_sot_docs
        settings.artifact_substitute_sot_docs = True

        try:
            assert artifact_loader.should_substitute_sot_doc("docs/BUILD_LOG.md")
            assert artifact_loader.should_substitute_sot_doc(".autonomous_runs/BUILD_LOG.md")
        finally:
            settings.artifact_substitute_sot_docs = original

    def test_should_not_substitute_regular_files(self, artifact_loader):
        """Should not substitute regular files"""
        original = settings.artifact_substitute_sot_docs
        settings.artifact_substitute_sot_docs = True

        try:
            assert not artifact_loader.should_substitute_sot_doc("src/auth.py")
            assert not artifact_loader.should_substitute_sot_doc("docs/README.md")
        finally:
            settings.artifact_substitute_sot_docs = original

    def test_get_sot_doc_summary_with_history_pack(self, artifact_loader, temp_workspace):
        """Should return history pack as SOT doc summary"""
        original_sot = settings.artifact_substitute_sot_docs
        original_history = settings.artifact_history_pack_enabled
        settings.artifact_substitute_sot_docs = True
        settings.artifact_history_pack_enabled = True

        try:
            # Create artifacts
            artifacts_dir = temp_workspace / ".autonomous_runs" / "test-run-123"
            artifacts_dir.mkdir(parents=True)
            run_summary = artifacts_dir / "run_summary.md"
            run_summary.write_text("Test run summary")

            summary = artifact_loader.get_sot_doc_summary("docs/BUILD_HISTORY.md")
            assert summary is not None
            assert "Summary of docs/BUILD_HISTORY.md" in summary
            assert "Test run summary" in summary
        finally:
            settings.artifact_substitute_sot_docs = original_sot
            settings.artifact_history_pack_enabled = original_history

    def test_get_sot_doc_summary_returns_none_when_disabled(self, artifact_loader):
        """Should return None when SOT substitution disabled"""
        original = settings.artifact_substitute_sot_docs
        settings.artifact_substitute_sot_docs = False

        try:
            summary = artifact_loader.get_sot_doc_summary("docs/BUILD_HISTORY.md")
            assert summary is None
        finally:
            settings.artifact_substitute_sot_docs = original

    def test_get_sot_doc_summary_returns_none_for_regular_files(self, artifact_loader):
        """Should return None for non-SOT files"""
        original = settings.artifact_substitute_sot_docs
        settings.artifact_substitute_sot_docs = True

        try:
            summary = artifact_loader.get_sot_doc_summary("src/auth.py")
            assert summary is None
        finally:
            settings.artifact_substitute_sot_docs = original


class TestExtendedContexts:
    """Test extended context artifact substitution"""

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

    @pytest.fixture
    def artifacts_dir(self, temp_workspace):
        """Create and return artifacts directory"""
        artifacts = temp_workspace / ".autonomous_runs" / "test-run-123"
        artifacts.mkdir(parents=True)
        return artifacts

    def test_extended_contexts_disabled_by_default(self, artifact_loader):
        """Extended contexts should be disabled by default"""
        original = settings.artifact_extended_contexts_enabled
        settings.artifact_extended_contexts_enabled = False

        try:
            content = "Phase 1 description with lots of text"
            result, tokens_saved, source = artifact_loader.load_with_extended_contexts(
                content, "phase_description"
            )
            assert result == content
            assert tokens_saved == 0
            assert source == "original"
        finally:
            settings.artifact_extended_contexts_enabled = original

    def test_extended_contexts_only_safe_types(self, artifact_loader):
        """Should only apply to safe context types"""
        original = settings.artifact_extended_contexts_enabled
        settings.artifact_extended_contexts_enabled = True

        try:
            content = "Some content"
            # Unsafe context type should not be substituted
            result, tokens_saved, source = artifact_loader.load_with_extended_contexts(
                content, "unsafe_context"
            )
            assert result == content
            assert tokens_saved == 0
            assert source == "original"
        finally:
            settings.artifact_extended_contexts_enabled = original

    def test_historical_context_uses_history_pack(self, artifact_loader, artifacts_dir):
        """Historical context should use history pack"""
        original_extended = settings.artifact_extended_contexts_enabled
        original_history = settings.artifact_history_pack_enabled
        settings.artifact_extended_contexts_enabled = True
        settings.artifact_history_pack_enabled = True

        try:
            # Create artifacts
            run_summary = artifacts_dir / "run_summary.md"
            run_summary.write_text("Test run summary")

            content = "Long historical context " * 100
            result, tokens_saved, source = artifact_loader.load_with_extended_contexts(
                content, "historical"
            )
            
            assert "Test run summary" in result
            assert tokens_saved > 0
            assert source == "artifact:history_pack"
        finally:
            settings.artifact_extended_contexts_enabled = original_extended
            settings.artifact_history_pack_enabled = original_history

    def test_phase_description_substitution(self, artifact_loader, artifacts_dir):
        """Phase descriptions should be substituted with artifacts"""
        original = settings.artifact_extended_contexts_enabled
        settings.artifact_extended_contexts_enabled = True

        try:
            # Create phase artifact
            phases_dir = artifacts_dir / "phases"
            phases_dir.mkdir()
            phase1 = phases_dir / "phase_01_test.md"
            phase1.write_text("# Phase 1\n\nDetailed phase 1 summary with implementation details")

            content = "Long description of phase 1 with lots of text " * 50
            result, tokens_saved, source = artifact_loader.load_with_extended_contexts(
                content, "phase_description"
            )
            
            assert "Phase 1" in result
            assert tokens_saved > 0
            assert source == "artifact:phase_description"
        finally:
            settings.artifact_extended_contexts_enabled = original

    def test_tier_summary_substitution(self, artifact_loader, artifacts_dir):
        """Tier summaries should be substituted with artifacts"""
        original = settings.artifact_extended_contexts_enabled
        settings.artifact_extended_contexts_enabled = True

        try:
            # Create tier artifact
            tiers_dir = artifacts_dir / "tiers"
            tiers_dir.mkdir()
            tier1 = tiers_dir / "tier_01_backend.md"
            tier1.write_text("# Tier 1\n\nBackend tier summary with details")

            content = "Long description of tier 1 with lots of text " * 50
            result, tokens_saved, source = artifact_loader.load_with_extended_contexts(
                content, "tier_summary"
            )
            
            assert "Tier 1" in result
            assert tokens_saved > 0
            assert source == "artifact:tier_summary"
        finally:
            settings.artifact_extended_contexts_enabled = original

    def test_no_substitution_when_no_artifacts(self, artifact_loader):
        """Should not substitute when no artifacts available"""
        original = settings.artifact_extended_contexts_enabled
        settings.artifact_extended_contexts_enabled = True

        try:
            content = "Description of phase 1"
            result, tokens_saved, source = artifact_loader.load_with_extended_contexts(
                content, "phase_description"
            )
            assert result == content
            assert tokens_saved == 0
            assert source == "original"
        finally:
            settings.artifact_extended_contexts_enabled = original

    def test_multiple_phase_references(self, artifact_loader, artifacts_dir):
        """Should handle multiple phase references"""
        original = settings.artifact_extended_contexts_enabled
        settings.artifact_extended_contexts_enabled = True

        try:
            # Create multiple phase artifacts
            phases_dir = artifacts_dir / "phases"
            phases_dir.mkdir()
            for i in range(1, 4):
                phase = phases_dir / f"phase_{i:02d}_test.md"
                phase.write_text(f"# Phase {i}\n\nPhase {i} summary")

            content = "References to phase 1, phase 2, and phase 3 " * 20
            result, tokens_saved, source = artifact_loader.load_with_extended_contexts(
                content, "phase_description"
            )
            
            assert "Phase 1" in result
            assert "Phase 2" in result
            assert "Phase 3" in result
            assert tokens_saved > 0
        finally:
            settings.artifact_extended_contexts_enabled = original
