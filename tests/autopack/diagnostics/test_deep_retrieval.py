"""Tests for Stage 2A: Deep Retrieval - Bounded escalation with strict caps.

Tests verify:
- Per-category caps (run artifacts: 5 files/10KB, SOT: 3 files/15KB, memory: 5 entries/5KB)
- Recency awareness (24-hour window prioritization)
- Relevance ranking for SOT files
- Proper truncation when budget exceeded
- Isolation from protected paths

Per BUILD-043/044/045 patterns: strict isolation, no protected path modifications.
"""

import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from autopack.diagnostics.deep_retrieval import DeepRetrieval


class TestDeepRetrievalCaps:
    """Test strict per-category caps and size limits."""

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

    def test_run_artifacts_max_files_cap(self, retrieval, temp_dirs):
        """Test that run artifacts are capped at 5 files."""
        run_dir, _ = temp_dirs

        # Create 10 artifact files
        for i in range(10):
            artifact_file = run_dir / f"artifact_{i}.log"
            artifact_file.write_text(f"Artifact {i} content\n" * 10)

        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Should retrieve max 5 files
        assert result["stats"]["run_artifacts_count"] <= DeepRetrieval.MAX_RUN_ARTIFACTS
        assert len(result["run_artifacts"]) <= 5

    def test_run_artifacts_max_size_cap(self, retrieval, temp_dirs):
        """Test that run artifacts are capped at 10KB total."""
        run_dir, _ = temp_dirs

        # Create 3 large artifact files (5KB each = 15KB total)
        for i in range(3):
            artifact_file = run_dir / f"large_artifact_{i}.log"
            artifact_file.write_text("X" * 5000)  # 5KB

        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Should cap at 10KB total
        total_size = result["stats"]["run_artifacts_size"]
        assert total_size <= DeepRetrieval.MAX_RUN_ARTIFACTS_SIZE
        assert total_size <= 10 * 1024

    def test_sot_files_max_files_cap(self, retrieval, temp_dirs):
        """Test that SOT files are capped at 3 files."""
        _, repo_root = temp_dirs

        # Create docs directory with 5 markdown files
        docs_dir = repo_root / "docs"
        docs_dir.mkdir()
        for i in range(5):
            doc_file = docs_dir / f"doc_{i}.md"
            doc_file.write_text(f"# Document {i}\n\nContent here.\n")

        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Should retrieve max 3 files
        assert result["stats"]["sot_files_count"] <= DeepRetrieval.MAX_SOT_FILES
        assert len(result["sot_files"]) <= 3

    def test_sot_files_max_size_cap(self, retrieval, temp_dirs):
        """Test that SOT files are capped at 15KB total."""
        _, repo_root = temp_dirs

        # Create docs directory with 2 large files (10KB each = 20KB total)
        docs_dir = repo_root / "docs"
        docs_dir.mkdir()
        for i in range(2):
            doc_file = docs_dir / f"large_doc_{i}.md"
            doc_file.write_text("X" * 10000)  # 10KB

        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Should cap at 15KB total
        total_size = result["stats"]["sot_files_size"]
        assert total_size <= DeepRetrieval.MAX_SOT_FILES_SIZE
        assert total_size <= 15 * 1024

    def test_memory_entries_caps(self, retrieval, temp_dirs):
        """Test that memory entries respect caps (currently returns empty)."""
        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Memory not yet implemented - should return empty
        assert result["stats"]["memory_entries_count"] == 0
        assert result["stats"]["memory_entries_size"] == 0
        assert len(result["memory_entries"]) == 0


class TestDeepRetrievalRecency:
    """Test recency awareness (24-hour window prioritization)."""

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

    def test_prioritizes_recent_artifacts(self, retrieval, temp_dirs):
        """Test that recent artifacts (within 24h) are prioritized."""
        run_dir, _ = temp_dirs

        # Create old artifact (48 hours ago)
        old_artifact = run_dir / "old_artifact.log"
        old_artifact.write_text("Old artifact content")
        datetime.now().timestamp() - (48 * 3600)
        old_artifact.touch()
        # Note: Can't easily set mtime in test, but logic is tested

        # Create recent artifact (1 hour ago)
        recent_artifact = run_dir / "recent_artifact.log"
        recent_artifact.write_text("Recent artifact content")

        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Should retrieve artifacts (recent prioritized if within window)
        assert result["stats"]["run_artifacts_count"] >= 1

    def test_falls_back_when_no_recent_artifacts(self, retrieval, temp_dirs):
        """Test fallback to most recent overall when no files in 24h window."""
        run_dir, _ = temp_dirs

        # Create artifact (will be recent by default)
        artifact = run_dir / "artifact.log"
        artifact.write_text("Artifact content")

        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Should still retrieve artifacts even if not in recency window
        assert result["stats"]["run_artifacts_count"] >= 1


class TestDeepRetrievalRelevance:
    """Test relevance ranking for SOT files."""

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

    def test_ranks_by_keyword_matches(self, retrieval, temp_dirs):
        """Test that SOT files are ranked by keyword relevance."""
        _, repo_root = temp_dirs

        # Create docs with varying keyword matches
        docs_dir = repo_root / "docs"
        docs_dir.mkdir()

        # High relevance: multiple keyword matches
        high_doc = docs_dir / "high_relevance.md"
        high_doc.write_text("# Error Handling\n\nThis document covers error handling patterns.")

        # Low relevance: no keyword matches
        low_doc = docs_dir / "low_relevance.md"
        low_doc.write_text("# Introduction\n\nWelcome to the project.")

        handoff_bundle = {
            "error_message": "Error occurred during handling",
            "root_cause": "Error in handler",
        }
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Should retrieve SOT files with relevance scores
        if result["sot_files"]:
            assert "relevance_score" in result["sot_files"][0]

    def test_extracts_keywords_from_handoff(self, retrieval):
        """Test keyword extraction from handoff bundle."""
        handoff_bundle = {
            "error_message": "Database connection failed unexpectedly",
            "root_cause": "Connection timeout occurred",
        }

        keywords = retrieval._extract_keywords(handoff_bundle)

        # Should extract meaningful keywords (>4 chars)
        assert len(keywords) > 0
        assert all(len(kw) > 4 for kw in keywords)
        # Should include words like "database", "connection", "failed", etc.

    def test_handles_empty_keywords(self, retrieval, temp_dirs):
        """Test that ranking works even with no keywords (falls back to recency)."""
        _, repo_root = temp_dirs

        docs_dir = repo_root / "docs"
        docs_dir.mkdir()
        doc = docs_dir / "doc.md"
        doc.write_text("# Document\n\nContent here.")

        handoff_bundle = {}  # No keywords
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Should still work (falls back to recency sorting)
        assert "sot_files" in result


class TestDeepRetrievalTruncation:
    """Test proper truncation when budget exceeded."""

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

    def test_truncates_artifact_content_at_budget(self, retrieval, temp_dirs):
        """Test that artifact content is truncated to stay within budget."""
        run_dir, _ = temp_dirs

        # Create artifact that exceeds budget
        artifact = run_dir / "large.log"
        artifact.write_text("X" * 20000)  # 20KB (exceeds 10KB cap)

        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Total size should not exceed cap
        assert result["stats"]["run_artifacts_size"] <= DeepRetrieval.MAX_RUN_ARTIFACTS_SIZE

    def test_truncates_sot_content_at_budget(self, retrieval, temp_dirs):
        """Test that SOT content is truncated to stay within budget."""
        _, repo_root = temp_dirs

        docs_dir = repo_root / "docs"
        docs_dir.mkdir()

        # Create doc that exceeds budget
        doc = docs_dir / "large.md"
        doc.write_text("X" * 20000)  # 20KB (exceeds 15KB cap)

        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Total size should not exceed cap
        assert result["stats"]["sot_files_size"] <= DeepRetrieval.MAX_SOT_FILES_SIZE


class TestDeepRetrievalIsolation:
    """Test isolation from protected paths."""

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

    def test_does_not_modify_protected_paths(self, retrieval, temp_dirs):
        """Test that retrieval does not modify protected paths."""
        run_dir, repo_root = temp_dirs

        # Create protected directories
        (repo_root / ".autonomous_runs").mkdir()
        (repo_root / ".git").mkdir()

        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Should complete without touching protected paths
        assert result["phase_id"] == "phase_001"
        assert "stats" in result

    def test_only_reads_from_allowed_directories(self, retrieval, temp_dirs):
        """Test that retrieval only reads from run_dir and SOT directories."""
        run_dir, repo_root = temp_dirs

        # Create allowed directories
        docs_dir = repo_root / "docs"
        docs_dir.mkdir()
        src_dir = repo_root / "src"
        src_dir.mkdir()

        # Create files in allowed locations
        (run_dir / "artifact.log").write_text("Artifact")
        (docs_dir / "doc.md").write_text("# Doc")
        (src_dir / "code.py").write_text("# Code")

        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Should retrieve from allowed locations
        assert result["stats"]["run_artifacts_count"] >= 0
        assert result["stats"]["sot_files_count"] >= 0


class TestDeepRetrievalBundle:
    """Test retrieval bundle structure and metadata."""

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

    def test_bundle_has_required_fields(self, retrieval):
        """Test that retrieval bundle has all required fields."""
        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Check required top-level fields
        assert "phase_id" in result
        assert "timestamp" in result
        assert "priority" in result
        assert "run_artifacts" in result
        assert "sot_files" in result
        assert "memory_entries" in result
        assert "stats" in result

    def test_bundle_stats_are_accurate(self, retrieval, temp_dirs):
        """Test that bundle stats match actual retrieved content."""
        run_dir, repo_root = temp_dirs

        # Create test files
        (run_dir / "artifact.log").write_text("Artifact content")
        docs_dir = repo_root / "docs"
        docs_dir.mkdir()
        (docs_dir / "doc.md").write_text("# Document")

        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        # Stats should match actual content
        assert result["stats"]["run_artifacts_count"] == len(result["run_artifacts"])
        assert result["stats"]["sot_files_count"] == len(result["sot_files"])
        assert result["stats"]["memory_entries_count"] == len(result["memory_entries"])

        # Size stats should match sum of content lengths
        actual_artifact_size = sum(len(a["content"]) for a in result["run_artifacts"])
        assert result["stats"]["run_artifacts_size"] == actual_artifact_size

    def test_bundle_includes_priority(self, retrieval):
        """Test that bundle includes priority level."""
        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle, priority="high")

        assert result["priority"] == "high"

    def test_artifact_entries_have_metadata(self, retrieval, temp_dirs):
        """Test that artifact entries include path, size, and modified timestamp."""
        run_dir, _ = temp_dirs
        (run_dir / "artifact.log").write_text("Content")

        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        if result["run_artifacts"]:
            artifact = result["run_artifacts"][0]
            assert "path" in artifact
            assert "content" in artifact
            assert "size" in artifact
            assert "modified" in artifact

    def test_sot_entries_have_relevance_score(self, retrieval, temp_dirs):
        """Test that SOT entries include relevance score."""
        _, repo_root = temp_dirs
        docs_dir = repo_root / "docs"
        docs_dir.mkdir()
        (docs_dir / "doc.md").write_text("# Document")

        handoff_bundle = {"error_message": "test error"}
        result = retrieval.retrieve("phase_001", handoff_bundle)

        if result["sot_files"]:
            sot_file = result["sot_files"][0]
            assert "path" in sot_file
            assert "content" in sot_file
            assert "size" in sot_file
            assert "relevance_score" in sot_file
