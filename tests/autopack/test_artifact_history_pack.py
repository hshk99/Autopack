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


class TestP17SafetyAndFallback:
    """BUILD-146 P17.2: Safety rules and fallback behavior tests.

    Ensures substitution only happens when enabled, caps are strictly enforced,
    and missing artifacts gracefully fallback to original content.
    """

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

    def test_no_substitution_when_all_disabled(self, artifact_loader, artifacts_dir):
        """Should not substitute anything when all flags are disabled."""
        # Save original settings
        original_sot = settings.artifact_substitute_sot_docs
        original_extended = settings.artifact_extended_contexts_enabled
        original_history = settings.artifact_history_pack_enabled

        # Disable all substitution features
        settings.artifact_substitute_sot_docs = False
        settings.artifact_extended_contexts_enabled = False
        settings.artifact_history_pack_enabled = False

        try:
            # Create artifacts that would normally be used
            run_summary = artifacts_dir / "run_summary.md"
            run_summary.write_text("Test run summary")

            # Verify no SOT substitution
            sot_result = artifact_loader.get_sot_doc_summary("docs/BUILD_HISTORY.md")
            assert sot_result is None

            # Verify no extended contexts substitution
            content = "Phase 1 description"
            extended_result, tokens_saved, source = artifact_loader.load_with_extended_contexts(
                content, "phase_description"
            )
            assert extended_result == content
            assert tokens_saved == 0
            assert source == "original"

            # Verify no history pack
            history_result = artifact_loader.build_history_pack()
            assert history_result is None

        finally:
            settings.artifact_substitute_sot_docs = original_sot
            settings.artifact_extended_contexts_enabled = original_extended
            settings.artifact_history_pack_enabled = original_history

    def test_only_sot_docs_are_substituted(self, artifact_loader, artifacts_dir):
        """Should only substitute allowed SOT docs, not arbitrary files."""
        original_sot = settings.artifact_substitute_sot_docs
        original_history = settings.artifact_history_pack_enabled
        settings.artifact_substitute_sot_docs = True
        settings.artifact_history_pack_enabled = True

        try:
            # Create artifacts
            run_summary = artifacts_dir / "run_summary.md"
            run_summary.write_text("Test run summary")

            # Allowed SOT docs should be substituted
            assert artifact_loader.should_substitute_sot_doc("docs/BUILD_HISTORY.md")
            assert artifact_loader.should_substitute_sot_doc("docs/BUILD_LOG.md")
            assert artifact_loader.should_substitute_sot_doc(".autonomous_runs/BUILD_HISTORY.md")

            # Non-SOT files should NOT be substituted
            assert not artifact_loader.should_substitute_sot_doc("src/main.py")
            assert not artifact_loader.should_substitute_sot_doc("README.md")
            assert not artifact_loader.should_substitute_sot_doc("docs/api.md")
            assert not artifact_loader.should_substitute_sot_doc(".autonomous_runs/phase_01.md")

        finally:
            settings.artifact_substitute_sot_docs = original_sot
            settings.artifact_history_pack_enabled = original_history

    def test_fallback_when_history_pack_missing(self, artifact_loader):
        """Should gracefully return None when history pack artifacts are missing."""
        original = settings.artifact_history_pack_enabled
        settings.artifact_history_pack_enabled = True

        try:
            # No artifacts exist - should return None
            result = artifact_loader.build_history_pack()
            assert result is None

        finally:
            settings.artifact_history_pack_enabled = original

    def test_fallback_to_original_when_no_artifacts(self, artifact_loader):
        """Should fallback to original content when no artifacts available."""
        original = settings.artifact_extended_contexts_enabled
        settings.artifact_extended_contexts_enabled = True

        try:
            # No artifacts exist
            content = "Long phase description " * 50
            result, tokens_saved, source = artifact_loader.load_with_extended_contexts(
                content, "phase_description"
            )

            # Should return original content unchanged
            assert result == content
            assert tokens_saved == 0
            assert source == "original"

        finally:
            settings.artifact_extended_contexts_enabled = original

    def test_max_tiers_cap_strictly_enforced(self, artifact_loader, artifacts_dir):
        """Should strictly enforce max_tiers cap, not exceed it."""
        original_enabled = settings.artifact_history_pack_enabled
        original_max_tiers = settings.artifact_history_pack_max_tiers
        settings.artifact_history_pack_enabled = True
        settings.artifact_history_pack_max_tiers = 3

        try:
            # Create 5 tier summaries
            tiers_dir = artifacts_dir / "tiers"
            tiers_dir.mkdir()
            for i in range(1, 6):
                tier = tiers_dir / f"tier_{i:02d}_test.md"
                tier.write_text(f"# Tier {i}\n\nTier {i} content")

            result = artifact_loader.build_history_pack()
            assert result is not None

            # Should include exactly 3 most recent tiers (tier_05, tier_04, tier_03)
            assert "Tier 5 content" in result
            assert "Tier 4 content" in result
            assert "Tier 3 content" in result

            # Should NOT include tier_01, tier_02 (exceed cap)
            assert "Tier 1 content" not in result
            assert "Tier 2 content" not in result

        finally:
            settings.artifact_history_pack_enabled = original_enabled
            settings.artifact_history_pack_max_tiers = original_max_tiers

    def test_max_phases_cap_strictly_enforced(self, artifact_loader, artifacts_dir):
        """Should strictly enforce max_phases cap, not exceed it."""
        original_enabled = settings.artifact_history_pack_enabled
        original_max_phases = settings.artifact_history_pack_max_phases
        settings.artifact_history_pack_enabled = True
        settings.artifact_history_pack_max_phases = 2

        try:
            # Create 5 phase summaries
            phases_dir = artifacts_dir / "phases"
            phases_dir.mkdir()
            for i in range(1, 6):
                phase = phases_dir / f"phase_{i:02d}_test.md"
                phase.write_text(f"# Phase {i}\n\nPhase {i} content")

            result = artifact_loader.build_history_pack()
            assert result is not None

            # Should include exactly 2 most recent phases (phase_05, phase_04)
            assert "Phase 5 content" in result
            assert "Phase 4 content" in result

            # Should NOT include phase_01, phase_02, phase_03 (exceed cap)
            assert "Phase 1 content" not in result
            assert "Phase 2 content" not in result
            assert "Phase 3 content" not in result

        finally:
            settings.artifact_history_pack_enabled = original_enabled
            settings.artifact_history_pack_max_phases = original_max_phases

    def test_zero_cap_excludes_all(self, artifact_loader, artifacts_dir):
        """Cap of 0 should exclude all items of that type."""
        original_enabled = settings.artifact_history_pack_enabled
        original_max_tiers = settings.artifact_history_pack_max_tiers
        settings.artifact_history_pack_enabled = True
        settings.artifact_history_pack_max_tiers = 0  # Exclude all tiers

        try:
            # Create tiers and phases
            tiers_dir = artifacts_dir / "tiers"
            tiers_dir.mkdir()
            tier1 = tiers_dir / "tier_01_test.md"
            tier1.write_text("# Tier 1\n\nTier content")

            phases_dir = artifacts_dir / "phases"
            phases_dir.mkdir()
            phase1 = phases_dir / "phase_01_test.md"
            phase1.write_text("# Phase 1\n\nPhase content")

            result = artifact_loader.build_history_pack()

            # Should include phases but NO tiers
            if result:  # May be None if only tiers exist
                assert "Phase content" in result
                assert "Tier content" not in result

        finally:
            settings.artifact_history_pack_enabled = original_enabled
            settings.artifact_history_pack_max_tiers = original_max_tiers

    def test_no_silent_substitutions_in_regular_files(self, artifact_loader, artifacts_dir):
        """Should never silently substitute regular code files."""
        original = settings.artifact_substitute_sot_docs
        settings.artifact_substitute_sot_docs = True

        try:
            # Create history pack
            run_summary = artifacts_dir / "run_summary.md"
            run_summary.write_text("Test run summary")

            # Regular files should NOT be substituted
            regular_files = [
                "src/main.py",
                "tests/test_foo.py",
                "README.md",
                "package.json",
                "config.yaml",
            ]

            for file_path in regular_files:
                assert not artifact_loader.should_substitute_sot_doc(file_path)
                summary = artifact_loader.get_sot_doc_summary(file_path)
                assert summary is None

        finally:
            settings.artifact_substitute_sot_docs = original

    def test_caps_use_recency_ordering(self, artifact_loader, artifacts_dir):
        """Caps should keep most recent items (reverse lexical order)."""
        original_enabled = settings.artifact_history_pack_enabled
        original_max_phases = settings.artifact_history_pack_max_phases
        settings.artifact_history_pack_enabled = True
        settings.artifact_history_pack_max_phases = 2

        try:
            # Create phases with timestamps in filenames
            phases_dir = artifacts_dir / "phases"
            phases_dir.mkdir()

            # Create in non-sequential order to test sorting
            phase3 = phases_dir / "phase_03_latest.md"
            phase3.write_text("# Phase 3 (latest)")

            phase1 = phases_dir / "phase_01_oldest.md"
            phase1.write_text("# Phase 1 (oldest)")

            phase2 = phases_dir / "phase_02_middle.md"
            phase2.write_text("# Phase 2 (middle)")

            result = artifact_loader.build_history_pack()
            assert result is not None

            # Should include 2 most recent: phase_03 and phase_02
            assert "Phase 3 (latest)" in result
            assert "Phase 2 (middle)" in result

            # Should NOT include oldest phase_01
            assert "Phase 1 (oldest)" not in result

        finally:
            settings.artifact_history_pack_enabled = original_enabled
            settings.artifact_history_pack_max_phases = original_max_phases
