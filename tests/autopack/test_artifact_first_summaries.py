"""BUILD-145 P1: Tests for artifact-first context loading

Tests that artifact loader prefers run artifacts over full file content
for token-efficient read-only context loading.
"""

import pytest
from pathlib import Path
import json

from autopack.artifact_loader import ArtifactLoader, estimate_tokens


class TestArtifactLoader:
    """Test artifact-first context loading"""

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

    def test_estimate_tokens(self):
        """Token estimation should use 4 chars per token ratio"""
        content = "a" * 400  # 400 chars
        assert estimate_tokens(content) == 100  # 100 tokens

        content = "test"  # 4 chars
        assert estimate_tokens(content) == 1  # 1 token

    def test_no_artifacts_returns_none(self, artifact_loader):
        """Should return None when no artifacts directory exists"""
        result = artifact_loader.find_artifact_for_path("src/test.py")
        assert result is None

    def test_phase_summary_found(self, artifact_loader, artifacts_dir):
        """Should find phase summary mentioning file"""
        phases_dir = artifacts_dir / "phases"
        phases_dir.mkdir()

        phase_summary = phases_dir / "phase_01_test-phase.md"
        phase_summary.write_text(
            "# Phase Summary\n\n"
            "Modified src/auth.py: Added JWT validation\n"
            "Modified src/middleware.py: Added auth middleware"
        )

        result = artifact_loader.find_artifact_for_path("src/auth.py")
        assert result is not None
        content, artifact_type = result
        assert artifact_type == "phase_summary"
        assert "src/auth.py" in content
        assert "JWT validation" in content

    def test_phase_summary_file_basename_match(self, artifact_loader, artifacts_dir):
        """Should match on file basename if full path not found"""
        phases_dir = artifacts_dir / "phases"
        phases_dir.mkdir()

        phase_summary = phases_dir / "phase_01_test.md"
        phase_summary.write_text("# Phase Summary\n\nModified auth.py to add validation")

        result = artifact_loader.find_artifact_for_path("src/auth.py")
        assert result is not None
        content, artifact_type = result
        assert artifact_type == "phase_summary"
        assert "auth.py" in content

    def test_tier_summary_found(self, artifact_loader, artifacts_dir):
        """Should find tier summary mentioning file"""
        tiers_dir = artifacts_dir / "tiers"
        tiers_dir.mkdir()

        tier_summary = tiers_dir / "tier_01_backend.md"
        tier_summary.write_text(
            "# Tier Summary\n\n"
            "Backend tier completed authentication refactor.\n"
            "Files modified: src/auth.py, src/middleware.py"
        )

        # No phase summary exists, should fall back to tier
        result = artifact_loader.find_artifact_for_path("src/auth.py")
        assert result is not None
        content, artifact_type = result
        assert artifact_type == "tier_summary"
        assert "auth" in content.lower()

    def test_diagnostics_json_found(self, artifact_loader, artifacts_dir):
        """Should find diagnostics JSON mentioning file"""
        diagnostics_dir = artifacts_dir / "diagnostics"
        diagnostics_dir.mkdir()

        diagnostic_data = {
            "status": "completed",
            "files_analyzed": ["src/auth.py", "src/middleware.py"],
            "findings": [{"file": "src/auth.py", "issue": "Missing input validation"}],
        }

        diag_json = diagnostics_dir / "diagnostic_summary.json"
        diag_json.write_text(json.dumps(diagnostic_data, indent=2))

        result = artifact_loader.find_artifact_for_path("src/auth.py")
        assert result is not None
        content, artifact_type = result
        assert artifact_type == "diagnostics"
        assert "src/auth.py" in content
        assert "Diagnostics Summary" in content

    def test_handoff_bundle_found(self, artifact_loader, artifacts_dir):
        """Should find handoff bundle mentioning file"""
        diagnostics_dir = artifacts_dir / "diagnostics"
        diagnostics_dir.mkdir()

        handoff = diagnostics_dir / "handoff_phase_01.md"
        handoff.write_text(
            "# Handoff Bundle\n\n"
            "## Context\n"
            "Phase completed authentication refactor in src/auth.py.\n\n"
            "## Next Steps\n"
            "Review JWT implementation."
        )

        result = artifact_loader.find_artifact_for_path("src/auth.py")
        assert result is not None
        content, artifact_type = result
        assert artifact_type == "diagnostics"
        assert "src/auth.py" in content
        assert "Handoff Bundle" in content

    def test_run_summary_found_last(self, artifact_loader, artifacts_dir):
        """Run summary should be last resort"""
        run_summary = artifacts_dir / "run_summary.md"
        run_summary.write_text(
            "# Run Summary\n\n"
            "Run completed successfully.\n"
            "Modified files: src/auth.py, src/middleware.py"
        )

        result = artifact_loader.find_artifact_for_path("src/auth.py")
        assert result is not None
        content, artifact_type = result
        assert artifact_type == "run_summary"

    def test_most_recent_phase_summary_preferred(self, artifact_loader, artifacts_dir):
        """Should prefer most recent phase summary"""
        phases_dir = artifacts_dir / "phases"
        phases_dir.mkdir()

        # Older phase
        old_phase = phases_dir / "phase_01_old.md"
        old_phase.write_text("Old phase modified auth.py")

        # Newer phase
        new_phase = phases_dir / "phase_05_new.md"
        new_phase.write_text("Recent phase updated auth.py with JWT")

        result = artifact_loader.find_artifact_for_path("auth.py")
        assert result is not None
        content, artifact_type = result
        # Should find the newer one first (phase_05 > phase_01 in sorted order)
        assert "Recent phase" in content

    def test_load_with_artifacts_prefer_true(self, artifact_loader, artifacts_dir):
        """Should use artifact when prefer_artifacts=True and artifact is smaller"""
        phases_dir = artifacts_dir / "phases"
        phases_dir.mkdir()

        phase_summary = phases_dir / "phase_01_test.md"
        phase_summary.write_text("Short summary: auth.py modified")

        full_content = "a" * 10000  # Large file (10000 chars = ~2500 tokens)

        content, tokens_saved, source_type = artifact_loader.load_with_artifacts(
            "auth.py", full_content, prefer_artifacts=True
        )

        assert source_type.startswith("artifact:")
        assert tokens_saved > 0
        assert "Short summary" in content
        assert len(content) < len(full_content)

    def test_load_with_artifacts_prefer_false(self, artifact_loader, artifacts_dir):
        """Should use full content when prefer_artifacts=False"""
        phases_dir = artifacts_dir / "phases"
        phases_dir.mkdir()

        phase_summary = phases_dir / "phase_01_test.md"
        phase_summary.write_text("Short summary: auth.py modified")

        full_content = "Full file content"

        content, tokens_saved, source_type = artifact_loader.load_with_artifacts(
            "auth.py", full_content, prefer_artifacts=False
        )

        assert source_type == "full_file"
        assert tokens_saved == 0
        assert content == full_content

    def test_load_with_artifacts_no_artifact_found(self, artifact_loader):
        """Should use full content when no artifact found"""
        full_content = "Full file content"

        content, tokens_saved, source_type = artifact_loader.load_with_artifacts(
            "src/unknown.py", full_content, prefer_artifacts=True
        )

        assert source_type == "full_file"
        assert tokens_saved == 0
        assert content == full_content

    def test_load_with_artifacts_artifact_larger_than_full(self, artifact_loader, artifacts_dir):
        """Should use full content when artifact is larger"""
        phases_dir = artifacts_dir / "phases"
        phases_dir.mkdir()

        # Create large artifact
        large_artifact = "a" * 10000
        phase_summary = phases_dir / "phase_01_test.md"
        phase_summary.write_text(f"auth.py: {large_artifact}")

        small_full_content = "Small file"

        content, tokens_saved, source_type = artifact_loader.load_with_artifacts(
            "auth.py", small_full_content, prefer_artifacts=True
        )

        # Should use full content since it's smaller
        assert source_type == "full_file"
        assert tokens_saved == 0
        assert content == small_full_content

    def test_token_savings_calculation(self, artifact_loader, artifacts_dir):
        """Should correctly calculate token savings"""
        phases_dir = artifacts_dir / "phases"
        phases_dir.mkdir()

        artifact_content = "a" * 400  # 100 tokens
        phase_summary = phases_dir / "phase_01_test.md"
        phase_summary.write_text(f"auth.py: {artifact_content}")

        full_content = "a" * 4000  # 1000 tokens

        content, tokens_saved, source_type = artifact_loader.load_with_artifacts(
            "auth.py", full_content, prefer_artifacts=True
        )

        # Should save ~900 tokens (1000 - 100)
        assert tokens_saved >= 800  # Allow some margin
        assert tokens_saved <= 1000

    def test_multiple_phase_summaries_returns_first_match(self, artifact_loader, artifacts_dir):
        """Should return first (most recent) matching phase summary"""
        phases_dir = artifacts_dir / "phases"
        phases_dir.mkdir()

        phase1 = phases_dir / "phase_01_first.md"
        phase1.write_text("First phase: auth.py")

        phase2 = phases_dir / "phase_02_second.md"
        phase2.write_text("Second phase: auth.py")

        result = artifact_loader.find_artifact_for_path("auth.py")
        assert result is not None
        content, artifact_type = result

        # _find_phase_summaries_mentioning returns list, first one is used
        # Sorted in reverse order, so phase_02 comes before phase_01
        assert "Second phase" in content

    def test_artifact_priority_phase_over_tier(self, artifact_loader, artifacts_dir):
        """Phase summary should take priority over tier summary"""
        phases_dir = artifacts_dir / "phases"
        phases_dir.mkdir()

        tiers_dir = artifacts_dir / "tiers"
        tiers_dir.mkdir()

        phase_summary = phases_dir / "phase_01_test.md"
        phase_summary.write_text("Phase: auth.py modified")

        tier_summary = tiers_dir / "tier_01_test.md"
        tier_summary.write_text("Tier: auth.py refactored")

        result = artifact_loader.find_artifact_for_path("auth.py")
        assert result is not None
        content, artifact_type = result
        assert artifact_type == "phase_summary"
        assert "Phase:" in content

    def test_artifact_priority_tier_over_diagnostics(self, artifact_loader, artifacts_dir):
        """Tier summary should take priority over diagnostics"""
        tiers_dir = artifacts_dir / "tiers"
        tiers_dir.mkdir()

        diagnostics_dir = artifacts_dir / "diagnostics"
        diagnostics_dir.mkdir()

        tier_summary = tiers_dir / "tier_01_test.md"
        tier_summary.write_text("Tier: auth.py refactored")

        diag_json = diagnostics_dir / "diagnostic_summary.json"
        diag_json.write_text(json.dumps({"files": ["auth.py"]}))

        result = artifact_loader.find_artifact_for_path("auth.py")
        assert result is not None
        content, artifact_type = result
        assert artifact_type == "tier_summary"

    def test_no_run_id_no_artifact_loader(self):
        """Should handle missing run_id gracefully"""
        workspace = Path("/tmp/test")
        loader = ArtifactLoader(workspace, "")

        # Should still work, just won't find artifacts
        result = loader.find_artifact_for_path("test.py")
        # artifacts_dir won't exist with empty run_id
        assert result is None

    def test_artifact_loader_handles_read_errors(self, artifact_loader, artifacts_dir):
        """Should handle file read errors gracefully"""
        phases_dir = artifacts_dir / "phases"
        phases_dir.mkdir()

        # Create a directory instead of a file (will cause read error)
        bad_phase = phases_dir / "phase_01_bad.md"
        bad_phase.mkdir()

        # Should not crash, just return None
        result = artifact_loader.find_artifact_for_path("auth.py")
        assert result is None
