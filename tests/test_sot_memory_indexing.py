"""
Tests for SOT memory indexing and retrieval.

Ensures that:
1. SOT files are chunked correctly
2. Chunks are indexed into MemoryService
3. Retrieval works with strict caps
4. Features are opt-in via env flags
"""

import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopack.config import Settings
from autopack.memory.memory_service import MemoryService
from autopack.memory.sot_indexing import (
    chunk_sot_file,
    chunk_sot_json,
    chunk_text,
    extract_heading_from_chunk,
    extract_timestamp_from_chunk,
    stable_chunk_id,
    json_to_embedding_text,
)


class TestSOTChunking:
    """Test SOT file chunking logic."""

    def test_chunk_text_short_content(self):
        """Test chunking short content that fits in one chunk."""
        text = "This is short content."
        chunks = chunk_text(text, max_chars=100, overlap_chars=20)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_text_long_content(self):
        """Test chunking long content into multiple chunks."""
        # Create content that requires multiple chunks
        sentences = ["This is sentence number {}. ".format(i) for i in range(100)]
        text = "".join(sentences)

        chunks = chunk_text(text, max_chars=200, overlap_chars=50)

        assert len(chunks) > 1
        # Check overlap exists
        assert chunks[1][:20] in chunks[0]

    def test_chunk_text_sentence_boundary(self):
        """Test that chunking respects sentence boundaries."""
        text = "First sentence. " * 10 + "Second sentence. " * 10

        chunks = chunk_text(text, max_chars=100, overlap_chars=20)

        # Each chunk should end with a period (sentence boundary)
        for chunk in chunks[:-1]:  # Except possibly the last chunk
            # Check that we broke at a sentence
            assert chunk.rstrip().endswith('.')

    def test_extract_heading(self):
        """Test heading extraction from chunks."""
        chunk = """
### BUILD-146 | 2025-01-01 | Phase A Complete

This phase implements observability.
        """

        heading = extract_heading_from_chunk(chunk)
        assert heading == "BUILD-146 | 2025-01-01 | Phase A Complete"

    def test_extract_timestamp(self):
        """Test timestamp extraction from chunks."""
        chunk = """
### BUILD-146 | 2025-01-15 | Phase Complete

Content here.
        """

        timestamp = extract_timestamp_from_chunk(chunk)
        assert timestamp is not None
        assert timestamp.year == 2025
        assert timestamp.month == 1
        assert timestamp.day == 15

    def test_stable_chunk_id_determinism(self):
        """Test that chunk IDs are stable for same content."""
        chunk_content = "This is test content for chunk ID stability."

        id1 = stable_chunk_id("autopack", "BUILD_HISTORY.md", chunk_content, 0)
        id2 = stable_chunk_id("autopack", "BUILD_HISTORY.md", chunk_content, 0)

        assert id1 == id2
        assert id1.startswith("sot:autopack:BUILD_HISTORY.md:")

    def test_chunk_sot_file(self, tmp_path):
        """Test full SOT file chunking."""
        # Create a test SOT file
        sot_file = tmp_path / "BUILD_HISTORY.md"
        content = """
### BUILD-001 | 2025-01-01 | Initial Setup

This is the first build entry.

### BUILD-002 | 2025-01-05 | Add Features

This is the second build entry with more content.
        """
        sot_file.write_text(content, encoding="utf-8")

        chunks = chunk_sot_file(sot_file, "autopack", max_chars=150, overlap_chars=30)

        assert len(chunks) > 0
        # Each chunk should have required metadata
        for chunk in chunks:
            assert "id" in chunk
            assert "content" in chunk
            assert "metadata" in chunk
            assert chunk["metadata"]["type"] == "sot"
            assert chunk["metadata"]["sot_file"] == "BUILD_HISTORY.md"
            assert chunk["metadata"]["project_id"] == "autopack"


class TestSOTMemoryIndexing:
    """Test MemoryService SOT indexing."""

    @pytest.fixture
    def memory_service(self):
        """Create an in-memory MemoryService instance."""
        with patch.dict(os.environ, {"AUTOPACK_ENABLE_MEMORY": "true"}):
            service = MemoryService(enabled=True, use_qdrant=False)
            return service

    @pytest.fixture
    def workspace_with_sot(self, tmp_path):
        """Create a workspace with SOT files."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create BUILD_HISTORY.md
        (docs_dir / "BUILD_HISTORY.md").write_text("""
### BUILD-146 | 2025-01-01 | Phase A Complete

Implemented comprehensive observability features including:
- Token tracking
- Error recovery
- Telemetry collection
        """, encoding="utf-8")

        # Create DEBUG_LOG.md
        (docs_dir / "DEBUG_LOG.md").write_text("""
## DBG-078 | 2025-01-10 | Test Timeout Fix

**Issue**: Tests were timing out intermittently.

**Solution**: Added async/await handling for long-running operations.
        """, encoding="utf-8")

        return tmp_path

    def test_index_sot_docs_disabled_by_default(self, memory_service, workspace_with_sot):
        """Test that SOT indexing is disabled by default."""
        result = memory_service.index_sot_docs("autopack", workspace_with_sot)

        assert result["skipped"] is True
        assert result["reason"] == "sot_indexing_disabled"

    def test_index_sot_docs_enabled(self, workspace_with_sot):
        """Test SOT indexing when enabled."""
        with patch.dict(os.environ, {
            "AUTOPACK_ENABLE_MEMORY": "true",
            "AUTOPACK_ENABLE_SOT_MEMORY_INDEXING": "true",
        }):
            # Reload settings module to pick up environment changes
            import sys
            import importlib
            if "autopack.config" in sys.modules:
                importlib.reload(sys.modules["autopack.config"])
            from autopack.config import settings
            assert settings.autopack_enable_sot_memory_indexing is True

            service = MemoryService(enabled=True, use_qdrant=False)
            result = service.index_sot_docs("autopack", workspace_with_sot)

            assert result["skipped"] is False
            assert result["indexed"] > 0

    def test_search_sot(self, workspace_with_sot):
        """Test SOT search functionality."""
        with patch.dict(os.environ, {
            "AUTOPACK_ENABLE_MEMORY": "true",
            "AUTOPACK_ENABLE_SOT_MEMORY_INDEXING": "true",
        }):
            # Reload settings module to pick up environment changes
            import sys
            import importlib
            if "autopack.config" in sys.modules:
                importlib.reload(sys.modules["autopack.config"])

            service = MemoryService(enabled=True, use_qdrant=False)

            # Index SOT docs
            service.index_sot_docs("autopack", workspace_with_sot)

            # Search for observability-related content
            results = service.search_sot("observability features", "autopack", limit=5)

            # Should find chunks from BUILD_HISTORY
            assert len(results) > 0

    def test_retrieve_context_with_sot_disabled(self, memory_service):
        """Test that SOT retrieval requires explicit opt-in."""
        # SOT retrieval disabled by default
        results = memory_service.retrieve_context(
            query="test query",
            project_id="autopack",
            include_sot=True,
        )

        # Should not return SOT results when disabled
        assert "sot" in results
        assert len(results["sot"]) == 0

    def test_retrieve_context_with_sot_enabled(self, workspace_with_sot):
        """Test SOT retrieval when enabled."""
        with patch.dict(os.environ, {
            "AUTOPACK_ENABLE_MEMORY": "true",
            "AUTOPACK_ENABLE_SOT_MEMORY_INDEXING": "true",
            "AUTOPACK_SOT_RETRIEVAL_ENABLED": "true",
        }):
            # Reload settings module to pick up environment changes
            import sys
            import importlib
            if "autopack.config" in sys.modules:
                importlib.reload(sys.modules["autopack.config"])

            service = MemoryService(enabled=True, use_qdrant=False)

            # Index SOT docs
            service.index_sot_docs("autopack", workspace_with_sot)

            # Retrieve with SOT enabled
            results = service.retrieve_context(
                query="observability",
                project_id="autopack",
                include_sot=True,
            )

            assert "sot" in results
            assert len(results["sot"]) > 0

    def test_format_retrieved_context_includes_sot(self, workspace_with_sot):
        """Test that formatted context includes SOT chunks."""
        with patch.dict(os.environ, {
            "AUTOPACK_ENABLE_MEMORY": "true",
            "AUTOPACK_ENABLE_SOT_MEMORY_INDEXING": "true",
            "AUTOPACK_SOT_RETRIEVAL_ENABLED": "true",
        }):
            # Reload settings module to pick up environment changes
            import sys
            import importlib
            if "autopack.config" in sys.modules:
                importlib.reload(sys.modules["autopack.config"])

            service = MemoryService(enabled=True, use_qdrant=False)

            # Index and retrieve
            service.index_sot_docs("autopack", workspace_with_sot)
            results = service.retrieve_context(
                query="observability",
                project_id="autopack",
                include_sot=True,
            )

            # Format results
            formatted = service.format_retrieved_context(results, max_chars=10000)

            # Should include SOT section
            assert "## Relevant Documentation (SOT)" in formatted

    def test_sot_retrieval_respects_max_chars(self, workspace_with_sot):
        """Test that SOT retrieval respects max_chars limits."""
        with patch.dict(os.environ, {
            "AUTOPACK_ENABLE_MEMORY": "true",
            "AUTOPACK_ENABLE_SOT_MEMORY_INDEXING": "true",
            "AUTOPACK_SOT_RETRIEVAL_ENABLED": "true",
            "AUTOPACK_SOT_RETRIEVAL_MAX_CHARS": "100",  # Very small limit
        }):
            service = MemoryService(enabled=True, use_qdrant=False)

            # Index and retrieve
            service.index_sot_docs("autopack", workspace_with_sot)
            results = service.retrieve_context(
                query="observability",
                project_id="autopack",
                include_sot=True,
            )

            # Format with limit
            formatted = service.format_retrieved_context(results, max_chars=10000)

            # SOT section should exist but be limited
            if "## Relevant Documentation (SOT)" in formatted:
                sot_section = formatted.split("## Relevant Documentation (SOT)")[1]
                # Should be truncated due to max_chars limit
                assert len(sot_section) < 500  # Much less than full content


class TestSOTIdempotency:
    """Test that re-indexing SOT docs is idempotent."""

    def test_reindex_produces_same_ids(self, tmp_path):
        """Test that re-indexing produces same chunk IDs."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        sot_file = docs_dir / "BUILD_HISTORY.md"
        sot_file.write_text("""
### BUILD-001 | 2025-01-01 | Test Build

Test content.
        """, encoding="utf-8")

        # Index twice
        chunks1 = chunk_sot_file(sot_file, "autopack", max_chars=500, overlap_chars=50)
        chunks2 = chunk_sot_file(sot_file, "autopack", max_chars=500, overlap_chars=50)

        # Should produce same IDs
        assert len(chunks1) == len(chunks2)
        for c1, c2 in zip(chunks1, chunks2):
            assert c1["id"] == c2["id"]


class TestSOTJSONChunking:
    """Test JSON SOT file chunking with field-selective embedding."""

    def test_json_to_embedding_text_project_index(self):
        """Test PROJECT_INDEX.json field extraction."""
        obj = {
            "project_name": "Test Project",
            "description": "A test project for validation",
            "setup": {
                "commands": ["npm install", "npm run build"],
                "dependencies": ["react", "typescript"]
            },
            "structure": {
                "entrypoints": ["src/index.ts", "src/main.ts"]
            },
            "api": {
                "summary": "REST API with GraphQL"
            }
        }

        items = json_to_embedding_text(obj, "PROJECT_INDEX.json")

        assert len(items) > 0
        # Check that we extracted high-signal fields
        key_paths = [item[0] for item in items]
        assert "project_name" in key_paths
        assert "description" in key_paths
        assert "setup.commands" in key_paths
        assert "api.summary" in key_paths

    def test_json_to_embedding_text_learned_rules(self):
        """Test LEARNED_RULES.json field extraction."""
        obj = {
            "rules": [
                {
                    "id": "R001",
                    "title": "Always validate input",
                    "rule": "Validate all user input before processing",
                    "when": "Processing user data",
                    "because": "Prevents injection attacks",
                    "examples": ["SQL injection", "XSS attacks"]
                }
            ]
        }

        items = json_to_embedding_text(obj, "LEARNED_RULES.json")

        assert len(items) > 0
        # Should extract rule with ID
        assert items[0][0] == "rules.R001"
        # Should contain rule text
        assert "R001" in items[0][1]
        assert "validate input" in items[0][1].lower()

    def test_chunk_sot_json_project_index(self, tmp_path):
        """Test chunking PROJECT_INDEX.json file."""
        json_file = tmp_path / "PROJECT_INDEX.json"
        import json
        content = {
            "project_name": "Autopack",
            "description": "Autonomous development framework",
            "setup": {
                "commands": ["pip install -e ."],
                "dependencies": ["sqlalchemy", "pydantic"]
            }
        }
        json_file.write_text(json.dumps(content), encoding="utf-8")

        chunks = chunk_sot_json(json_file, "autopack", max_chars=500, overlap_chars=50)

        assert len(chunks) > 0
        # Each chunk should have required metadata
        for chunk in chunks:
            assert "id" in chunk
            assert "content" in chunk
            assert "metadata" in chunk
            assert chunk["metadata"]["type"] == "sot"
            assert chunk["metadata"]["sot_file"] == "PROJECT_INDEX.json"
            assert "json_key_path" in chunk["metadata"]

    def test_chunk_sot_json_windows_line_endings(self, tmp_path):
        """Test that Windows line endings don't affect chunk IDs."""
        import json
        json_file = tmp_path / "test.json"

        content = {"project_name": "Test"}

        # Write with Unix line endings
        json_file.write_text(json.dumps(content, indent=2), encoding="utf-8")
        chunks1 = chunk_sot_json(json_file, "autopack")

        # Write with Windows line endings
        json_text = json.dumps(content, indent=2).replace("\n", "\r\n")
        json_file.write_text(json_text, encoding="utf-8")
        chunks2 = chunk_sot_json(json_file, "autopack")

        # IDs should be same despite different line endings
        assert len(chunks1) == len(chunks2)
        for c1, c2 in zip(chunks1, chunks2):
            assert c1["id"] == c2["id"]


class TestSOTChunkingBoundaries:
    """Test improved chunking boundary detection."""

    def test_chunk_text_paragraph_boundary(self):
        """Test that chunking prefers paragraph breaks."""
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."

        chunks = chunk_text(text, max_chars=50, overlap_chars=10)

        # Should break at paragraph boundaries when possible
        assert len(chunks) > 1

    def test_chunk_text_markdown_heading_boundary(self):
        """Test that chunking breaks at markdown headings."""
        text = """Some text here.

# Heading 1

Content under heading 1.

## Heading 2

More content here."""

        chunks = chunk_text(text, max_chars=80, overlap_chars=15)

        # Should break near headings
        assert len(chunks) > 1

    def test_chunk_text_question_exclamation_boundaries(self):
        """Test that chunking handles ? and ! boundaries."""
        text = "Question one? Question two! Statement three. " * 10

        chunks = chunk_text(text, max_chars=100, overlap_chars=20)

        assert len(chunks) > 1


class TestSOTMultiProject:
    """Test multi-project docs directory resolution."""

    def test_index_sot_docs_with_explicit_docs_dir(self, tmp_path):
        """Test indexing with explicit docs_dir parameter."""
        # Create a sub-project docs dir
        sub_docs = tmp_path / ".autonomous_runs" / "my-project" / "docs"
        sub_docs.mkdir(parents=True)

        (sub_docs / "BUILD_HISTORY.md").write_text("""
### BUILD-001 | Sub-project build
Content here.
        """, encoding="utf-8")

        with patch.dict(os.environ, {
            "AUTOPACK_ENABLE_MEMORY": "true",
            "AUTOPACK_ENABLE_SOT_MEMORY_INDEXING": "true",
        }):
            # Reload settings module to pick up environment changes
            import sys
            import importlib
            if "autopack.config" in sys.modules:
                importlib.reload(sys.modules["autopack.config"])

            service = MemoryService(enabled=True, use_qdrant=False)

            # Index with explicit docs_dir
            result = service.index_sot_docs(
                "my-project",
                tmp_path,
                docs_dir=sub_docs
            )

            assert result["skipped"] is False
            assert result["indexed"] > 0

    def test_index_sot_docs_fallback_to_default(self, tmp_path):
        """Test that docs_dir defaults to workspace_root/docs."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        (docs_dir / "BUILD_HISTORY.md").write_text("""
### BUILD-001 | Default location
Content.
        """, encoding="utf-8")

        with patch.dict(os.environ, {
            "AUTOPACK_ENABLE_MEMORY": "true",
            "AUTOPACK_ENABLE_SOT_MEMORY_INDEXING": "true",
        }):
            # Reload settings module to pick up environment changes
            import sys
            import importlib
            if "autopack.config" in sys.modules:
                importlib.reload(sys.modules["autopack.config"])

            service = MemoryService(enabled=True, use_qdrant=False)

            # Index without explicit docs_dir
            result = service.index_sot_docs("autopack", tmp_path)

            assert result["skipped"] is False
            assert result["indexed"] > 0


class TestSOTSkipExisting:
    """Test that re-indexing skips existing chunks."""

    def test_reindex_skips_existing_chunks(self, tmp_path):
        """Test that second indexing skips unchanged chunks."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        (docs_dir / "BUILD_HISTORY.md").write_text("""
### BUILD-001 | Test Build
Test content for skip test.
        """, encoding="utf-8")

        with patch.dict(os.environ, {
            "AUTOPACK_ENABLE_MEMORY": "true",
            "AUTOPACK_ENABLE_SOT_MEMORY_INDEXING": "true",
        }):
            service = MemoryService(enabled=True, use_qdrant=False)

            # First index
            result1 = service.index_sot_docs("autopack", tmp_path)
            indexed_first = result1["indexed"]

            # Second index (should skip existing)
            result2 = service.index_sot_docs("autopack", tmp_path)
            indexed_second = result2["indexed"]

            # Second run should index 0 new chunks (all already exist)
            assert indexed_second == 0


class TestSOT6FileSupport:
    """Test that all 6 SOT files are indexed."""

    def test_all_6_sot_files_indexed(self, tmp_path):
        """Test that markdown and JSON SOT files are all indexed."""
        import json
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create all 6 SOT files
        (docs_dir / "BUILD_HISTORY.md").write_text("# Build History\nContent.", encoding="utf-8")
        (docs_dir / "DEBUG_LOG.md").write_text("# Debug Log\nContent.", encoding="utf-8")
        (docs_dir / "ARCHITECTURE_DECISIONS.md").write_text("# Architecture\nContent.", encoding="utf-8")
        (docs_dir / "FUTURE_PLAN.md").write_text("# Future Plan\nContent.", encoding="utf-8")

        (docs_dir / "PROJECT_INDEX.json").write_text(
            json.dumps({"project_name": "Test"}), encoding="utf-8"
        )
        (docs_dir / "LEARNED_RULES.json").write_text(
            json.dumps({"rules": [{"id": "R1", "title": "Test Rule", "rule": "Test"}]}), encoding="utf-8"
        )

        with patch.dict(os.environ, {
            "AUTOPACK_ENABLE_MEMORY": "true",
            "AUTOPACK_ENABLE_SOT_MEMORY_INDEXING": "true",
        }):
            # Reload settings module to pick up environment changes
            import sys
            import importlib
            if "autopack.config" in sys.modules:
                importlib.reload(sys.modules["autopack.config"])

            service = MemoryService(enabled=True, use_qdrant=False)
            result = service.index_sot_docs("autopack", tmp_path)

            # Should index chunks from all 6 files
            assert result["skipped"] is False
            assert result["indexed"] >= 6  # At least one chunk per file


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
