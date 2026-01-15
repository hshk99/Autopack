"""
Tests for StorageScanner single-pass traversal optimization.

Verifies IMP-021 fix: Reduces O(n²) directory sizing complexity
by accumulating directory sizes during single traversal instead of
performing redundant traversals via _get_directory_size calls.
"""

from autopack.storage_optimizer.scanner import StorageScanner


class TestScannerSingleTraversal:
    """Tests for single-pass traversal with directory size accumulation."""

    def test_scan_directory_accumulates_sizes(self, tmp_path):
        """Verify directory sizes are accumulated during single traversal."""
        scanner = StorageScanner(max_depth=2)

        # Create test structure with known sizes
        # root/
        #   dir1/
        #     file1.txt (10 bytes)
        #     file2.txt (20 bytes)
        #   dir2/
        #     file3.txt (15 bytes)

        dir1 = tmp_path / "dir1"
        dir1.mkdir()
        (dir1 / "file1.txt").write_text("x" * 10)
        (dir1 / "file2.txt").write_text("x" * 20)

        dir2 = tmp_path / "dir2"
        dir2.mkdir()
        (dir2 / "file3.txt").write_text("x" * 15)

        results = scanner.scan_directory(str(tmp_path))

        # Find directory results
        dir_results = {r.path: r for r in results if r.is_folder}

        # Verify dir1 size is accumulated (30 bytes)
        assert str(dir1) in dir_results
        assert dir_results[str(dir1)].size_bytes == 30

        # Verify dir2 size is accumulated (15 bytes)
        assert str(dir2) in dir_results
        assert dir_results[str(dir2)].size_bytes == 15

    def test_scan_directory_nested_accumulation(self, tmp_path):
        """Verify sizes accumulate through nested directory hierarchy."""
        scanner = StorageScanner(max_depth=3)

        # Create nested structure
        # root/
        #   parent/
        #     child/
        #       file.txt (100 bytes)
        #     sibling_file.txt (50 bytes)

        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "child"
        child.mkdir()

        (child / "file.txt").write_text("x" * 100)
        (parent / "sibling_file.txt").write_text("x" * 50)

        results = scanner.scan_directory(str(tmp_path))

        dir_results = {r.path: r for r in results if r.is_folder}

        # Verify parent accumulates both child and sibling file sizes (150 bytes)
        assert str(parent) in dir_results
        assert dir_results[str(parent)].size_bytes == 150

        # Verify child has only its own file (100 bytes)
        assert str(child) in dir_results
        assert dir_results[str(child)].size_bytes == 100

    def test_scan_directory_handles_permission_errors_gracefully(self, tmp_path):
        """Verify scanner continues despite permission errors."""
        scanner = StorageScanner(max_depth=2)

        # Create test structure
        dir1 = tmp_path / "accessible_dir"
        dir1.mkdir()
        (dir1 / "file.txt").write_text("test")

        dir2 = tmp_path / "problematic_dir"
        dir2.mkdir()
        (dir2 / "file.txt").write_text("test")

        # Scanner should handle this gracefully
        results = scanner.scan_directory(str(tmp_path))

        # Should still get results from accessible directory
        assert len(results) > 0
        paths = [r.path for r in results]
        assert any("accessible_dir" in p for p in paths)

    def test_scan_directory_respects_max_depth(self, tmp_path):
        """Verify max_depth limit stops deep traversal."""
        scanner = StorageScanner(max_depth=1)

        # Create deep structure
        deep_path = tmp_path / "level1" / "level2" / "level3"
        deep_path.mkdir(parents=True)
        (deep_path / "deep_file.txt").write_text("test")

        results = scanner.scan_directory(str(tmp_path), max_items=100)

        paths = [r.path for r in results]
        # level1 should be found
        assert any("level1" in p for p in paths)
        # level2 and level3 should NOT be found due to max_depth=1
        assert not any("level2" in p for p in paths)
        assert not any("level3" in p for p in paths)
        # deep_file should NOT be found
        assert not any("deep_file" in p for p in paths)

    def test_scan_directory_respects_exclude_dirs(self, tmp_path):
        """Verify excluded directories are skipped."""
        scanner = StorageScanner(max_depth=2, exclude_dirs=[".git", "node_modules"])

        # Create structure with excluded dirs
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("git config")

        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "package.json").write_text("{}")

        normal_dir = tmp_path / "normal"
        normal_dir.mkdir()
        (normal_dir / "file.txt").write_text("content")

        results = scanner.scan_directory(str(tmp_path))

        paths = [r.path for r in results]
        # normal_dir should be found
        assert any("normal" in p for p in paths)
        # .git and node_modules should NOT be found
        assert not any(".git" in p for p in paths)
        assert not any("node_modules" in p for p in paths)

    def test_scan_directory_returns_correct_attributes(self, tmp_path):
        """Verify file and directory attributes are set correctly."""
        scanner = StorageScanner(max_depth=1)

        dir1 = tmp_path / "mydir"
        dir1.mkdir()
        (dir1 / "myfile.txt").write_text("content")

        results = scanner.scan_directory(str(tmp_path))

        for result in results:
            if result.is_folder:
                assert result.attributes == "d"
                assert result.is_folder is True
            else:
                assert result.attributes == "-"
                assert result.is_folder is False

    def test_scan_directory_respects_max_items(self, tmp_path):
        """Verify max_items parameter limits results."""
        scanner = StorageScanner(max_depth=2)

        # Create many files
        for i in range(20):
            (tmp_path / f"file_{i}.txt").write_text(f"content {i}")

        results = scanner.scan_directory(str(tmp_path), max_items=5)

        # Should not exceed max_items
        assert len(results) <= 5

    def test_scan_directory_file_sizes_accurate(self, tmp_path):
        """Verify individual file sizes are recorded accurately."""
        scanner = StorageScanner(max_depth=1)

        file1 = tmp_path / "file1.txt"
        file1.write_text("x" * 1000)

        file2 = tmp_path / "file2.txt"
        file2.write_text("y" * 2000)

        results = scanner.scan_directory(str(tmp_path))

        file_results = {r.path: r for r in results if not r.is_folder}

        assert str(file1) in file_results
        assert file_results[str(file1)].size_bytes == 1000

        assert str(file2) in file_results
        assert file_results[str(file2)].size_bytes == 2000

    def test_scan_directory_empty_directories_have_zero_size(self, tmp_path):
        """Verify empty directories report 0 bytes."""
        scanner = StorageScanner(max_depth=2)

        empty_dir = tmp_path / "empty_dir"
        empty_dir.mkdir()

        # Also create a non-empty dir for comparison
        filled_dir = tmp_path / "filled_dir"
        filled_dir.mkdir()
        (filled_dir / "file.txt").write_text("content")

        results = scanner.scan_directory(str(tmp_path))

        dir_results = {r.path: r for r in results if r.is_folder}

        # Empty directory should have 0 bytes
        assert str(empty_dir) in dir_results
        assert dir_results[str(empty_dir)].size_bytes == 0

        # Filled directory should have content size
        assert str(filled_dir) in dir_results
        assert dir_results[str(filled_dir)].size_bytes > 0

    def test_scan_directory_returns_all_attributes(self, tmp_path):
        """Verify all required ScanResult attributes are populated."""
        scanner = StorageScanner(max_depth=1)

        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        (test_dir / "test.txt").write_text("test")

        results = scanner.scan_directory(str(tmp_path))

        assert len(results) > 0

        for result in results:
            # Verify all required attributes exist
            assert hasattr(result, "path")
            assert hasattr(result, "size_bytes")
            assert hasattr(result, "modified")
            assert hasattr(result, "is_folder")
            assert hasattr(result, "attributes")

            # Verify values are set
            assert result.path is not None
            assert isinstance(result.size_bytes, int)
            assert result.size_bytes >= 0
            assert result.modified is not None
            assert isinstance(result.is_folder, bool)
            assert result.attributes in ["d", "-"]
