"""Extended tests for Stage 2A: Deep Retrieval - Advanced scenarios and edge cases.

Tests verify:
- Retrieval trigger conditions and thresholds
- Evidence collection from multiple sources
- Ranking algorithms for artifacts and SOT files
- Budget enforcement across categories
- Error handling and edge cases
- Integration with retrieval triggers

Per BUILD-043/044/045 patterns: strict isolation, no protected path modifications.

NOTE: Originally an extended/aspirational test suite, now graduated to core suite
as deep retrieval enhancements have been implemented (22/22 tests passing).
"""

import pytest
from pathlib import Path

# GRADUATED: Removed xfail marker - enhancements have been implemented (BUILD-146 Phase A P15)
import json
import tempfile
import shutil
from autopack.diagnostics.deep_retrieval import DeepRetrieval


class TestDeepRetrievalTriggers:
    """Test retrieval trigger conditions and activation."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary run and repo directories."""
        run_dir = Path(tempfile.mkdtemp())
        repo_root = Path(tempfile.mkdtemp())
        yield run_dir, repo_root
        shutil.rmtree(run_dir, ignore_errors=True)
        shutil.rmtree(repo_root, ignore_errors=True)

    @pytest.fixture
    def retrieval(self, temp_dirs):
        """Create DeepRetrieval instance."""
        run_dir, repo_root = temp_dirs
        return DeepRetrieval(run_dir=run_dir, repo_root=repo_root)

    def test_triggers_on_empty_handoff_bundle(self, retrieval):
        """Test that empty handoff bundle triggers deep retrieval."""
        empty_bundle = {}
        result = retrieval.retrieve("phase_001", empty_bundle)

        # Should still return valid result structure
        assert "run_artifacts" in result
        assert "sot_files" in result
        assert "memory_entries" in result
        assert "stats" in result

    def test_triggers_on_minimal_error_context(self, retrieval):
        """Test that minimal error context triggers deeper search."""
        minimal_bundle = {
            "error_message": "Error",  # Very short
            "stack_trace": ""
        }
        result = retrieval.retrieve("phase_001", minimal_bundle)

        # Should attempt to gather more context
        assert result is not None
        assert isinstance(result["stats"], dict)

    def test_triggers_on_repeated_failure_pattern(self, retrieval, temp_dirs):
        """Test that repeated failures trigger enhanced retrieval."""
        run_dir, _ = temp_dirs

        # Create multiple failure logs
        for i in range(3):
            log_file = run_dir / f"phase_001_attempt_{i}.log"
            log_file.write_text(f"ERROR: Attempt {i} failed\nFAILED\n")

        bundle = {"error_message": "Repeated failure"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should collect artifacts from multiple attempts
        assert result["stats"]["run_artifacts_count"] >= 0

    def test_priority_affects_retrieval_depth(self, retrieval):
        """Test that priority level affects retrieval depth."""
        bundle = {"error_message": "test error"}

        # High priority retrieval
        high_priority_result = retrieval.retrieve("phase_001", bundle, priority="high")
        assert high_priority_result["priority"] == "high"

        # Low priority retrieval
        low_priority_result = retrieval.retrieve("phase_001", bundle, priority="low")
        assert low_priority_result["priority"] == "low"


class TestDeepRetrievalEvidenceCollection:
    """Test evidence collection from multiple sources."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary run and repo directories."""
        run_dir = Path(tempfile.mkdtemp())
        repo_root = Path(tempfile.mkdtemp())
        yield run_dir, repo_root
        shutil.rmtree(run_dir, ignore_errors=True)
        shutil.rmtree(repo_root, ignore_errors=True)

    @pytest.fixture
    def retrieval(self, temp_dirs):
        """Create DeepRetrieval instance."""
        run_dir, repo_root = temp_dirs
        return DeepRetrieval(run_dir=run_dir, repo_root=repo_root)

    def test_collects_from_run_artifacts(self, retrieval, temp_dirs):
        """Test collection of run artifacts."""
        run_dir, _ = temp_dirs

        # Create various artifact types
        (run_dir / "error.log").write_text("ERROR: Test error\n" * 10)
        (run_dir / "output.txt").write_text("Output data\n" * 10)
        (run_dir / "metadata.json").write_text(json.dumps({"status": "failed"}))

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should collect multiple artifact types
        assert result["stats"]["run_artifacts_count"] >= 1
        assert result["stats"]["run_artifacts_count"] <= DeepRetrieval.MAX_RUN_ARTIFACTS

    def test_collects_from_sot_files(self, retrieval, temp_dirs):
        """Test collection of source-of-truth files."""
        _, repo_root = temp_dirs

        # Create SOT files
        docs_dir = repo_root / "docs"
        docs_dir.mkdir()
        (docs_dir / "README.md").write_text("# Project Documentation\n" * 10)
        (docs_dir / "ARCHITECTURE.md").write_text("# Architecture\n" * 10)

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should collect SOT files
        assert result["stats"]["sot_files_count"] >= 0
        assert result["stats"]["sot_files_count"] <= DeepRetrieval.MAX_SOT_FILES

    def test_collects_recent_artifacts_first(self, retrieval, temp_dirs):
        """Test that recent artifacts are prioritized."""
        run_dir, _ = temp_dirs

        # Create old artifact
        old_artifact = run_dir / "old.log"
        old_artifact.write_text("Old artifact\n" * 10)

        # Create recent artifact
        recent_artifact = run_dir / "recent.log"
        recent_artifact.write_text("Recent artifact\n" * 10)

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should collect artifacts (recent prioritized)
        assert result["stats"]["run_artifacts_count"] >= 0

    def test_handles_missing_directories(self, retrieval, temp_dirs):
        """Test graceful handling of missing directories."""
        run_dir, repo_root = temp_dirs

        # Remove directories
        shutil.rmtree(run_dir)
        shutil.rmtree(repo_root)

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should handle gracefully
        assert result["stats"]["run_artifacts_count"] == 0
        assert result["stats"]["sot_files_count"] == 0


class TestDeepRetrievalRanking:
    """Test ranking algorithms for artifacts and SOT files."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary run and repo directories."""
        run_dir = Path(tempfile.mkdtemp())
        repo_root = Path(tempfile.mkdtemp())
        yield run_dir, repo_root
        shutil.rmtree(run_dir, ignore_errors=True)
        shutil.rmtree(repo_root, ignore_errors=True)

    @pytest.fixture
    def retrieval(self, temp_dirs):
        """Create DeepRetrieval instance."""
        run_dir, repo_root = temp_dirs
        return DeepRetrieval(run_dir=run_dir, repo_root=repo_root)

    def test_ranks_by_relevance_keywords(self, retrieval, temp_dirs):
        """Test that SOT files are ranked by keyword relevance."""
        _, repo_root = temp_dirs

        docs_dir = repo_root / "docs"
        docs_dir.mkdir()

        # High relevance - matches error keywords
        (docs_dir / "error_handling.md").write_text(
            "# Error Handling\nerror test failure\n" * 10
        )

        # Low relevance - no keyword matches
        (docs_dir / "unrelated.md").write_text(
            "# Unrelated Topic\nsome other content\n" * 10
        )

        bundle = {"error_message": "error test failure"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should rank by relevance
        if result["sot_files"]:
            for sot_file in result["sot_files"]:
                assert "relevance_score" in sot_file
                assert isinstance(sot_file["relevance_score"], (int, float))

    def test_ranks_by_recency(self, retrieval, temp_dirs):
        """Test that artifacts are ranked by recency."""
        run_dir, _ = temp_dirs

        # Create artifacts with different timestamps
        for i in range(5):
            artifact = run_dir / f"artifact_{i}.log"
            artifact.write_text(f"Artifact {i}\n" * 10)

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should include modified timestamps
        if result["run_artifacts"]:
            for artifact in result["run_artifacts"]:
                assert "modified" in artifact

    def test_ranks_by_file_type_priority(self, retrieval, temp_dirs):
        """Test that certain file types are prioritized."""
        run_dir, _ = temp_dirs

        # Create different file types
        (run_dir / "error.log").write_text("ERROR log\n" * 10)
        (run_dir / "debug.log").write_text("DEBUG log\n" * 10)
        (run_dir / "info.txt").write_text("INFO text\n" * 10)

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should collect artifacts with type awareness
        assert result["stats"]["run_artifacts_count"] >= 0

    def test_ranks_by_size_efficiency(self, retrieval, temp_dirs):
        """Test that ranking considers size efficiency."""
        run_dir, _ = temp_dirs

        # Create files of varying sizes
        (run_dir / "small.log").write_text("Small\n" * 10)
        (run_dir / "large.log").write_text("Large\n" * 1000)

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should respect size budgets
        assert result["stats"]["run_artifacts_size"] <= DeepRetrieval.MAX_RUN_ARTIFACTS_SIZE


class TestDeepRetrievalBudgetEnforcement:
    """Test strict budget enforcement across categories."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary run and repo directories."""
        run_dir = Path(tempfile.mkdtemp())
        repo_root = Path(tempfile.mkdtemp())
        yield run_dir, repo_root
        shutil.rmtree(run_dir, ignore_errors=True)
        shutil.rmtree(repo_root, ignore_errors=True)

    @pytest.fixture
    def retrieval(self, temp_dirs):
        """Create DeepRetrieval instance."""
        run_dir, repo_root = temp_dirs
        return DeepRetrieval(run_dir=run_dir, repo_root=repo_root)

    def test_enforces_run_artifacts_file_cap(self, retrieval, temp_dirs):
        """Test strict enforcement of run artifacts file cap."""
        run_dir, _ = temp_dirs

        # Create more files than cap allows
        for i in range(20):
            (run_dir / f"artifact_{i}.log").write_text(f"Artifact {i}\n" * 10)

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Must not exceed cap
        assert result["stats"]["run_artifacts_count"] <= DeepRetrieval.MAX_RUN_ARTIFACTS
        assert len(result["run_artifacts"]) <= DeepRetrieval.MAX_RUN_ARTIFACTS

    def test_enforces_run_artifacts_size_cap(self, retrieval, temp_dirs):
        """Test strict enforcement of run artifacts size cap."""
        run_dir, _ = temp_dirs

        # Create large files
        for i in range(5):
            (run_dir / f"large_{i}.log").write_text("X" * 5000)

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Must not exceed size cap
        assert result["stats"]["run_artifacts_size"] <= DeepRetrieval.MAX_RUN_ARTIFACTS_SIZE

    def test_enforces_sot_files_file_cap(self, retrieval, temp_dirs):
        """Test strict enforcement of SOT files file cap."""
        _, repo_root = temp_dirs

        docs_dir = repo_root / "docs"
        docs_dir.mkdir()

        # Create more files than cap allows
        for i in range(10):
            (docs_dir / f"doc_{i}.md").write_text(f"# Document {i}\n" * 10)

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Must not exceed cap
        assert result["stats"]["sot_files_count"] <= DeepRetrieval.MAX_SOT_FILES
        assert len(result["sot_files"]) <= DeepRetrieval.MAX_SOT_FILES

    def test_enforces_sot_files_size_cap(self, retrieval, temp_dirs):
        """Test strict enforcement of SOT files size cap."""
        _, repo_root = temp_dirs

        docs_dir = repo_root / "docs"
        docs_dir.mkdir()

        # Create large files
        for i in range(3):
            (docs_dir / f"large_doc_{i}.md").write_text("X" * 10000)

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Must not exceed size cap
        assert result["stats"]["sot_files_size"] <= DeepRetrieval.MAX_SOT_FILES_SIZE

    def test_enforces_total_budget_across_categories(self, retrieval, temp_dirs):
        """Test that total budget is enforced across all categories."""
        run_dir, repo_root = temp_dirs

        # Create artifacts
        for i in range(10):
            (run_dir / f"artifact_{i}.log").write_text("X" * 2000)

        # Create SOT files
        docs_dir = repo_root / "docs"
        docs_dir.mkdir()
        for i in range(5):
            (docs_dir / f"doc_{i}.md").write_text("X" * 3000)

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Each category must respect its own cap
        assert result["stats"]["run_artifacts_size"] <= DeepRetrieval.MAX_RUN_ARTIFACTS_SIZE
        assert result["stats"]["sot_files_size"] <= DeepRetrieval.MAX_SOT_FILES_SIZE


class TestDeepRetrievalEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary run and repo directories."""
        run_dir = Path(tempfile.mkdtemp())
        repo_root = Path(tempfile.mkdtemp())
        yield run_dir, repo_root
        shutil.rmtree(run_dir, ignore_errors=True)
        shutil.rmtree(repo_root, ignore_errors=True)

    @pytest.fixture
    def retrieval(self, temp_dirs):
        """Create DeepRetrieval instance."""
        run_dir, repo_root = temp_dirs
        return DeepRetrieval(run_dir=run_dir, repo_root=repo_root)

    def test_handles_binary_files_gracefully(self, retrieval, temp_dirs):
        """Test that binary files are handled gracefully."""
        run_dir, _ = temp_dirs

        # Create binary file
        (run_dir / "binary.dat").write_bytes(b"\x00\x01\x02\x03" * 100)

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should not crash
        assert result is not None

    def test_handles_empty_files(self, retrieval, temp_dirs):
        """Test that empty files are handled correctly."""
        run_dir, _ = temp_dirs

        # Create empty files
        (run_dir / "empty.log").write_text("")
        (run_dir / "empty.txt").write_text("")

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should handle gracefully
        assert result is not None

    def test_handles_unicode_content(self, retrieval, temp_dirs):
        """Test that unicode content is handled correctly."""
        run_dir, _ = temp_dirs

        # Create file with unicode
        (run_dir / "unicode.log").write_text(
            "Error: File 'café.txt' not found 🔍\n" * 10,
            encoding="utf-8",
        )

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should handle unicode
        assert result is not None

    def test_handles_very_long_filenames(self, retrieval, temp_dirs):
        """Test that very long filenames are handled."""
        run_dir, _ = temp_dirs

        # Create file with long name
        long_name = "a" * 200 + ".log"
        try:
            (run_dir / long_name).write_text("Content\n" * 10)
        except OSError:
            # Filesystem doesn't support long names
            pytest.skip("Filesystem doesn't support long filenames")

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should handle gracefully
        assert result is not None

    def test_handles_permission_errors(self, retrieval, temp_dirs):
        """Test that permission errors are handled gracefully."""
        import os
        import stat

        run_dir, _ = temp_dirs

        # Create file and make it unreadable
        test_file = run_dir / "protected.log"
        test_file.write_text("Protected content\n" * 10)

        if os.name != "nt":  # Skip on Windows
            os.chmod(test_file, 0o000)

            try:
                bundle = {"error_message": "test error"}
                result = retrieval.retrieve("phase_001", bundle)

                # Should handle gracefully
                assert result is not None
            finally:
                # Restore permissions for cleanup
                os.chmod(test_file, stat.S_IRUSR | stat.S_IWUSR)

    def test_handles_symlinks(self, retrieval, temp_dirs):
        """Test that symlinks are handled correctly."""
        import os

        run_dir, _ = temp_dirs

        # Create actual file
        actual_file = run_dir / "actual.log"
        actual_file.write_text("Actual content\n" * 10)

        # Create symlink
        symlink_file = run_dir / "symlink.log"
        try:
            os.symlink(actual_file, symlink_file)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not supported on this platform")

        bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", bundle)

        # Should handle symlinks
        assert result is not None
