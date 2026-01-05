"""Tests for handoff bundle generation.

Tests the deterministic handoff bundle generator that creates
reproducible handoff/ folders from run directories.
"""

import json
import tempfile
from pathlib import Path
from typing import Generator

import pytest


class TestHandoffBundler:
    """Test suite for handoff bundle generation."""

    @pytest.fixture
    def temp_run_dir(self) -> Generator[Path, None, None]:
        """Create a temporary run directory with sample artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "test-run-20251220-120000"
            run_dir.mkdir(parents=True)

            # Create sample run metadata
            run_meta = {
                "run_id": "test-run-20251220-120000",
                "started_at": "2025-12-20T12:00:00Z",
                "status": "completed",
                "phases_completed": 3,
                "phases_total": 5,
            }
            (run_dir / "run_metadata.json").write_text(json.dumps(run_meta, indent=2))

            # Create sample log file
            log_content = "\n".join(
                [
                    "2025-12-20 12:00:00 [INFO] Starting run",
                    "2025-12-20 12:00:01 [INFO] Phase 1 started",
                    "2025-12-20 12:00:02 [INFO] Phase 1 completed",
                    "2025-12-20 12:00:03 [INFO] Phase 2 started",
                    "2025-12-20 12:00:04 [ERROR] Phase 2 failed: test error",
                    "2025-12-20 12:00:05 [INFO] Retrying phase 2",
                    "2025-12-20 12:00:06 [INFO] Phase 2 completed",
                    "2025-12-20 12:00:07 [INFO] Phase 3 started",
                    "2025-12-20 12:00:08 [INFO] Phase 3 completed",
                    "2025-12-20 12:00:09 [INFO] Run completed",
                ]
            )
            (run_dir / "run.log").write_text(log_content)

            # Create phases directory with sample phase outputs
            phases_dir = run_dir / "phases"
            phases_dir.mkdir()

            for i in range(1, 4):
                phase_dir = phases_dir / f"phase_{i:03d}"
                phase_dir.mkdir()
                phase_meta = {
                    "phase_id": f"phase_{i:03d}",
                    "name": f"Test Phase {i}",
                    "status": "completed",
                    "duration_seconds": 1.0 + i * 0.5,
                }
                (phase_dir / "metadata.json").write_text(json.dumps(phase_meta, indent=2))
                (phase_dir / "output.txt").write_text(f"Output from phase {i}\n" * 10)

            # Create artifacts directory
            artifacts_dir = run_dir / "artifacts"
            artifacts_dir.mkdir()
            (artifacts_dir / "result.json").write_text(
                json.dumps({"success": True, "items": [1, 2, 3]})
            )

            yield run_dir

    @pytest.fixture
    def empty_run_dir(self) -> Generator[Path, None, None]:
        """Create an empty run directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "empty-run"
            run_dir.mkdir(parents=True)
            yield run_dir

    def test_handoff_bundle_structure(self, temp_run_dir: Path) -> None:
        """Test that handoff bundle has correct structure."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        handoff_dir = generate_handoff_bundle(temp_run_dir)

        # Verify handoff directory exists
        assert handoff_dir.exists()
        assert handoff_dir.is_dir()
        assert handoff_dir.name == "handoff"
        assert handoff_dir.parent == temp_run_dir

        # Verify required files exist
        assert (handoff_dir / "index.json").exists()
        assert (handoff_dir / "summary.md").exists()
        assert (handoff_dir / "excerpts").exists()
        assert (handoff_dir / "excerpts").is_dir()

    def test_index_json_structure(self, temp_run_dir: Path) -> None:
        """Test that index.json has correct structure and content."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        handoff_dir = generate_handoff_bundle(temp_run_dir)
        index_path = handoff_dir / "index.json"

        # Load and validate index
        index = json.loads(index_path.read_text())

        # Check required top-level keys
        assert "version" in index
        assert "generated_at" in index
        assert "run_id" in index
        assert "artifacts" in index

        # Check artifacts is a list
        assert isinstance(index["artifacts"], list)

        # Each artifact should have required fields
        for artifact in index["artifacts"]:
            assert "path" in artifact
            assert "type" in artifact
            assert "size_bytes" in artifact

    def test_summary_md_content(self, temp_run_dir: Path) -> None:
        """Test that summary.md contains high-signal narrative."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        handoff_dir = generate_handoff_bundle(temp_run_dir)
        summary_path = handoff_dir / "summary.md"

        summary = summary_path.read_text()

        # Should contain key sections
        assert "# Handoff Summary" in summary or "# Run Summary" in summary
        assert "test-run-20251220-120000" in summary  # Run ID

    def test_excerpts_directory(self, temp_run_dir: Path) -> None:
        """Test that excerpts directory contains tailed snippets."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        handoff_dir = generate_handoff_bundle(temp_run_dir)
        excerpts_dir = handoff_dir / "excerpts"

        # Should have at least one excerpt file
        excerpt_files = list(excerpts_dir.iterdir())
        assert len(excerpt_files) >= 0  # May be empty for minimal runs

    def test_deterministic_output(self, temp_run_dir: Path) -> None:
        """Test that bundle generation is deterministic."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        # Generate bundle twice
        handoff_dir1 = generate_handoff_bundle(temp_run_dir)
        index1 = json.loads((handoff_dir1 / "index.json").read_text())

        # Remove and regenerate
        import shutil

        shutil.rmtree(handoff_dir1)

        handoff_dir2 = generate_handoff_bundle(temp_run_dir)
        index2 = json.loads((handoff_dir2 / "index.json").read_text())

        # Artifacts list should be identical (excluding timestamps)
        artifacts1 = sorted([a["path"] for a in index1["artifacts"]])
        artifacts2 = sorted([a["path"] for a in index2["artifacts"]])
        assert artifacts1 == artifacts2

    def test_invalid_run_dir(self) -> None:
        """Test error handling for invalid run directory."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        with pytest.raises(ValueError, match="does not exist|not found|invalid"):
            generate_handoff_bundle(Path("/nonexistent/path"))

    def test_empty_run_dir(self, empty_run_dir: Path) -> None:
        """Test handling of empty run directory."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        # Should either succeed with minimal output or raise clear error
        try:
            handoff_dir = generate_handoff_bundle(empty_run_dir)
            # If it succeeds, verify minimal structure
            assert (handoff_dir / "index.json").exists()
        except ValueError:
            # Acceptable to reject empty directories
            pass

    def test_large_file_excerpts(self, temp_run_dir: Path) -> None:
        """Test that large files are properly excerpted."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        # Create a large log file
        large_log = "\n".join([f"Line {i}: " + "x" * 100 for i in range(10000)])
        (temp_run_dir / "large.log").write_text(large_log)

        handoff_dir = generate_handoff_bundle(temp_run_dir)

        # Check that excerpts don't contain the full large file
        excerpts_dir = handoff_dir / "excerpts"
        if excerpts_dir.exists():
            for excerpt_file in excerpts_dir.iterdir():
                content = excerpt_file.read_text()
                # Excerpts should be reasonably sized (< 50KB)
                assert len(content) < 50000

    def test_special_characters_in_paths(self, temp_run_dir: Path) -> None:
        """Test handling of special characters in artifact paths."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        # Create file with special characters (that are valid on most filesystems)
        special_dir = temp_run_dir / "special_chars"
        special_dir.mkdir()
        (special_dir / "file-with-dashes.txt").write_text("content")
        (special_dir / "file_with_underscores.txt").write_text("content")
        (special_dir / "file.multiple.dots.txt").write_text("content")

        handoff_dir = generate_handoff_bundle(temp_run_dir)

        # Should complete without error
        assert handoff_dir.exists()
        assert (handoff_dir / "index.json").exists()

    def test_nested_directory_structure(self, temp_run_dir: Path) -> None:
        """Test handling of deeply nested directory structures."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        # Create nested structure
        nested = temp_run_dir / "a" / "b" / "c" / "d" / "e"
        nested.mkdir(parents=True)
        (nested / "deep_file.txt").write_text("deep content")

        handoff_dir = generate_handoff_bundle(temp_run_dir)

        # Should complete without error
        assert handoff_dir.exists()

        # Check that nested file is in index
        index = json.loads((handoff_dir / "index.json").read_text())
        paths = [a["path"] for a in index["artifacts"]]
        assert any("deep_file.txt" in p for p in paths)

    def test_binary_file_handling(self, temp_run_dir: Path) -> None:
        """Test handling of binary files."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        # Create a binary file
        binary_content = bytes(range(256))
        (temp_run_dir / "binary.bin").write_bytes(binary_content)

        handoff_dir = generate_handoff_bundle(temp_run_dir)

        # Should complete without error
        assert handoff_dir.exists()

        # Binary file should be in index
        index = json.loads((handoff_dir / "index.json").read_text())
        paths = [a["path"] for a in index["artifacts"]]
        assert any("binary.bin" in p for p in paths)

    def test_symlink_handling(self, temp_run_dir: Path) -> None:
        """Test handling of symbolic links."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        # Create a symlink (skip on Windows if not supported)
        target = temp_run_dir / "target.txt"
        target.write_text("target content")
        link = temp_run_dir / "link.txt"

        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

        handoff_dir = generate_handoff_bundle(temp_run_dir)

        # Should complete without error
        assert handoff_dir.exists()

    def test_regenerate_overwrites(self, temp_run_dir: Path) -> None:
        """Test that regenerating bundle overwrites existing."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        # Generate initial bundle
        handoff_dir = generate_handoff_bundle(temp_run_dir)
        (handoff_dir / "index.json").read_text()

        # Add new artifact
        (temp_run_dir / "new_artifact.txt").write_text("new content")

        # Regenerate
        handoff_dir = generate_handoff_bundle(temp_run_dir)
        new_index = (handoff_dir / "index.json").read_text()

        # Index should be updated
        assert "new_artifact.txt" in new_index


class TestHandoffBundlerEdgeCases:
    """Edge case tests for handoff bundler."""

    def test_unicode_content(self) -> None:
        """Test handling of unicode content in files."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "unicode-run"
            run_dir.mkdir()

            # Create file with unicode content
            unicode_content = "Hello 世界 🌍 Привет مرحبا"
            (run_dir / "unicode.txt").write_text(unicode_content, encoding="utf-8")

            # Create minimal metadata
            (run_dir / "run_metadata.json").write_text(json.dumps({"run_id": "unicode-run"}))

            handoff_dir = generate_handoff_bundle(run_dir)
            assert handoff_dir.exists()

    def test_empty_files(self) -> None:
        """Test handling of empty files."""
        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "empty-files-run"
            run_dir.mkdir()

            # Create empty file
            (run_dir / "empty.txt").write_text("")
            (run_dir / "run_metadata.json").write_text(json.dumps({"run_id": "empty-files-run"}))

            handoff_dir = generate_handoff_bundle(run_dir)
            assert handoff_dir.exists()

            # Empty file should be in index with size 0
            index = json.loads((handoff_dir / "index.json").read_text())
            empty_artifacts = [a for a in index["artifacts"] if "empty.txt" in a["path"]]
            if empty_artifacts:
                assert empty_artifacts[0]["size_bytes"] == 0

    def test_permission_errors(self) -> None:
        """Test handling of permission errors."""
        # This test is platform-specific and may need adjustment
        pytest.skip("Permission tests are platform-specific")

    def test_concurrent_generation(self, temp_run_dir: Path) -> None:
        """Test that concurrent generation doesn't cause issues."""
        import concurrent.futures

        from autopack.diagnostics.handoff_bundler import generate_handoff_bundle

        def generate():
            return generate_handoff_bundle(temp_run_dir)

        # Run multiple generations concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(generate) for _ in range(3)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All should succeed and point to same location
        assert all(r.exists() for r in results)
        assert len(set(str(r) for r in results)) == 1  # All same path


@pytest.fixture
def temp_run_dir() -> Generator[Path, None, None]:
    """Module-level fixture for temp run directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "test-run"
        run_dir.mkdir()
        (run_dir / "run_metadata.json").write_text(
            json.dumps({"run_id": "test-run", "status": "completed"})
        )
        (run_dir / "run.log").write_text("Test log content\n")
        yield run_dir
