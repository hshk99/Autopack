"""Contract tests for heuristic context loading determinism.

Tests that file selection and ordering is deterministic and follows
priority rules (git status > mentioned > priority > source).

Part of PR-EXE-6 (god file refactoring Item 1.1).
"""

from unittest.mock import Mock, patch

from autopack.executor.context_loading_heuristic import (
    HeuristicContextLoader, get_default_priority_files)


class TestFilePriorityOrdering:
    """Tests for file priority ordering (git > mentioned > priority > source)."""

    def test_git_status_files_have_highest_priority(self, tmp_path):
        """Files from git status should be included first."""
        loader = HeuristicContextLoader(max_files=5)

        # Create test files
        (tmp_path / "git_modified.py").write_text("# git modified file")
        (tmp_path / "mentioned.py").write_text("# mentioned file")
        (tmp_path / "priority.py").write_text("# priority file")

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=["git_modified.py"],
            mentioned_files=["mentioned.py"],
            priority_files=["priority.py"],
            source_dirs=[],
        )

        # Git status files should be loaded first
        assert "git_modified.py" in result
        # Other files should also be loaded (not at max yet)
        assert "mentioned.py" in result
        assert "priority.py" in result

    def test_mentioned_files_included_after_git_status(self, tmp_path):
        """Files mentioned in description should be included after git files."""
        loader = HeuristicContextLoader(max_files=2)

        # Create test files
        (tmp_path / "git_modified.py").write_text("# git modified")
        (tmp_path / "mentioned.py").write_text("# mentioned")
        (tmp_path / "priority.py").write_text("# priority")

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=["git_modified.py"],
            mentioned_files=["mentioned.py"],
            priority_files=["priority.py"],
            source_dirs=[],
        )

        # With max_files=2, git and mentioned should be loaded
        assert "git_modified.py" in result
        assert "mentioned.py" in result
        # Priority should be skipped (max_files exceeded)
        assert "priority.py" not in result

    def test_priority_files_included_after_mentioned(self, tmp_path):
        """Priority files should be included after mentioned files."""
        loader = HeuristicContextLoader(max_files=3)

        # Create test files
        (tmp_path / "git.py").write_text("# git")
        (tmp_path / "mentioned.py").write_text("# mentioned")
        (tmp_path / "priority.py").write_text("# priority")
        (tmp_path / "source.py").write_text("# source")

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=["git.py"],
            mentioned_files=["mentioned.py"],
            priority_files=["priority.py"],
            source_dirs=[],
        )

        # With max_files=3, git, mentioned, and priority should be loaded
        assert "git.py" in result
        assert "mentioned.py" in result
        assert "priority.py" in result

    def test_source_files_loaded_last(self, tmp_path):
        """Source files should be loaded last after other priorities."""
        loader = HeuristicContextLoader(max_files=10)

        # Create test files
        (tmp_path / "git.py").write_text("# git")
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "source1.py").write_text("# source 1")
        (src_dir / "source2.py").write_text("# source 2")

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=["git.py"],
            mentioned_files=[],
            priority_files=[],
            source_dirs=["src"],
        )

        # All files should be loaded
        assert "git.py" in result
        assert "src/source1.py" in result or "src\\source1.py" in result
        assert "src/source2.py" in result or "src\\source2.py" in result


class TestMaxFilesCapEnforcement:
    """Tests for max_files cap enforcement."""

    def test_max_files_cap_enforced(self, tmp_path):
        """Should not exceed max_files limit."""
        loader = HeuristicContextLoader(max_files=2)

        # Create multiple test files
        (tmp_path / "file1.py").write_text("# file 1")
        (tmp_path / "file2.py").write_text("# file 2")
        (tmp_path / "file3.py").write_text("# file 3")
        (tmp_path / "file4.py").write_text("# file 4")

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=["file1.py", "file2.py", "file3.py", "file4.py"],
            mentioned_files=[],
            priority_files=[],
            source_dirs=[],
        )

        # Should only load 2 files
        assert len(result) == 2

    def test_max_files_zero_returns_empty(self, tmp_path):
        """Max files = 0 should return empty dict."""
        loader = HeuristicContextLoader(max_files=0)

        (tmp_path / "file.py").write_text("# file")

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=["file.py"],
            mentioned_files=[],
            priority_files=[],
            source_dirs=[],
        )

        assert result == {}

    def test_git_files_always_included_first_under_cap(self, tmp_path):
        """Git status files should be included first if under cap."""
        loader = HeuristicContextLoader(max_files=1)

        (tmp_path / "git.py").write_text("# git")
        (tmp_path / "mentioned.py").write_text("# mentioned")

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=["git.py"],
            mentioned_files=["mentioned.py"],
            priority_files=[],
            source_dirs=[],
        )

        # Only git file should be loaded (max_files=1)
        assert "git.py" in result
        assert "mentioned.py" not in result
        assert len(result) == 1


class TestDeterministicBehavior:
    """Tests for deterministic behavior."""

    def test_ordering_is_deterministic(self, tmp_path):
        """Same inputs should produce same order every time."""
        loader = HeuristicContextLoader(max_files=10)

        # Create test files
        (tmp_path / "git.py").write_text("# git")
        (tmp_path / "mentioned.py").write_text("# mentioned")
        (tmp_path / "priority.py").write_text("# priority")

        # Run multiple times with same inputs
        results = []
        for _ in range(3):
            result = loader.load_context_files(
                workspace=tmp_path,
                git_status_files=["git.py"],
                mentioned_files=["mentioned.py"],
                priority_files=["priority.py"],
                source_dirs=[],
            )
            results.append(list(result.keys()))

        # All runs should produce same file list in same order
        assert results[0] == results[1] == results[2]

    def test_deduplication_keeps_highest_priority_source(self, tmp_path):
        """If file appears in multiple sources, it should only be loaded once."""
        loader = HeuristicContextLoader(max_files=10)

        # Create test file
        (tmp_path / "duplicate.py").write_text("# duplicate file")

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=["duplicate.py"],
            mentioned_files=["duplicate.py"],
            priority_files=["duplicate.py"],
            source_dirs=[],
        )

        # Should only appear once in result
        assert "duplicate.py" in result
        assert len(result) == 1


class TestFilePathExtraction:
    """Tests for file path extraction from descriptions."""

    def test_extract_single_file_from_description(self):
        """Should extract single file path from description."""
        loader = HeuristicContextLoader()

        description = "Update src/main.py to fix the bug"
        files = loader.extract_mentioned_files(description)

        assert "src/main.py" in files

    def test_extract_multiple_files_from_description(self):
        """Should extract multiple file paths from description."""
        loader = HeuristicContextLoader()

        description = "Modify config/settings.json and lib/utils.py"
        files = loader.extract_mentioned_files(description)

        assert "config/settings.json" in files
        assert "lib/utils.py" in files

    def test_extract_files_with_various_extensions(self):
        """Should extract files with different extensions."""
        loader = HeuristicContextLoader()

        description = "Update file.py, config.yaml, data.json, script.js, doc.md, types.ts"
        files = loader.extract_mentioned_files(description)

        assert "file.py" in files
        assert "config.yaml" in files
        assert "data.json" in files
        assert "script.js" in files
        assert "doc.md" in files
        assert "types.ts" in files

    def test_extract_from_acceptance_criteria(self):
        """Should extract files from acceptance criteria."""
        loader = HeuristicContextLoader()

        description = "Fix the bug"
        criteria = ["Tests in test_utils.py should pass", "Update README.md"]
        files = loader.extract_mentioned_files(description, criteria)

        assert "test_utils.py" in files
        assert "README.md" in files


class TestEmptyInputs:
    """Tests for empty input handling."""

    def test_empty_inputs_returns_empty_dict(self, tmp_path):
        """Should handle empty inputs gracefully."""
        loader = HeuristicContextLoader()

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=[],
            mentioned_files=[],
            priority_files=[],
            source_dirs=[],
        )

        assert result == {}

    def test_nonexistent_files_skipped(self, tmp_path):
        """Should skip files that don't exist."""
        loader = HeuristicContextLoader()

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=["nonexistent.py"],
            mentioned_files=["missing.py"],
            priority_files=["absent.py"],
            source_dirs=[],
        )

        assert result == {}


class TestTokenBudgetEnforcement:
    """Tests for token budget enforcement."""

    def test_token_budget_stops_loading(self, tmp_path):
        """Should stop loading files when token budget exceeded."""
        # Set very small token budget
        loader = HeuristicContextLoader(max_files=100, target_tokens=100)

        # Create large files
        (tmp_path / "large1.py").write_text("x" * 1000)
        (tmp_path / "large2.py").write_text("x" * 1000)
        (tmp_path / "large3.py").write_text("x" * 1000)

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=["large1.py", "large2.py", "large3.py"],
            mentioned_files=[],
            priority_files=[],
            source_dirs=[],
        )

        # Should load first file, but not all three (budget exceeded)
        assert len(result) < 3


class TestGitStatusExtraction:
    """Tests for git status file extraction."""

    @patch("subprocess.run")
    def test_extract_git_status_files(self, mock_run, tmp_path):
        """Should extract modified files from git status."""
        # Git status --porcelain format matches real output
        # " M filename" = modified in working tree
        # "A  filename" = added to index
        # "?? filename" = untracked
        mock_run.return_value = Mock(
            returncode=0,
            stdout=" M file1.py\nA  file2.py\n?? file3.py\n",
        )

        loader = HeuristicContextLoader()
        files = loader.extract_git_status_files(tmp_path)

        # All files should be extracted
        assert len(files) == 3
        assert "file1.py" in files
        assert "file2.py" in files
        assert "file3.py" in files

    @patch("subprocess.run")
    def test_extract_git_status_with_renames(self, mock_run, tmp_path):
        """Should handle renamed files in git status."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="R  old.py -> new.py\n",
        )

        loader = HeuristicContextLoader()
        files = loader.extract_git_status_files(tmp_path)

        # Should extract the new filename
        assert "new.py" in files
        assert "old.py" not in files

    @patch("subprocess.run")
    def test_git_status_failure_returns_empty(self, mock_run, tmp_path):
        """Should return empty list if git status fails."""
        mock_run.return_value = Mock(returncode=1, stdout="")

        loader = HeuristicContextLoader()
        files = loader.extract_git_status_files(tmp_path)

        assert files == []


class TestDefaultPriorityFiles:
    """Tests for default priority files configuration."""

    def test_default_priority_files_list(self):
        """Should return expected default priority files."""
        files = get_default_priority_files()

        assert "package.json" in files
        assert "setup.py" in files
        assert "requirements.txt" in files
        assert "pyproject.toml" in files
        assert "README.md" in files
        assert ".gitignore" in files


class TestInvalidInputHandling:
    """Tests for handling invalid inputs."""

    def test_non_string_path_skipped(self, tmp_path):
        """Should skip non-string paths gracefully."""
        loader = HeuristicContextLoader()

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=[None, 123, "valid.py"],  # type: ignore
            mentioned_files=[],
            priority_files=[],
            source_dirs=[],
        )

        # Should only attempt to load valid string path
        # (which doesn't exist, so result is empty)
        assert result == {}

    def test_empty_string_path_skipped(self, tmp_path):
        """Should skip empty string paths."""
        loader = HeuristicContextLoader()

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=["", "  ", "valid.py"],
            mentioned_files=[],
            priority_files=[],
            source_dirs=[],
        )

        assert result == {}

    def test_path_outside_workspace_skipped(self, tmp_path):
        """Should skip files outside workspace."""
        loader = HeuristicContextLoader()

        # Create file outside workspace
        outside = tmp_path.parent / "outside.py"
        outside.write_text("# outside")

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=[str(outside)],
            mentioned_files=[],
            priority_files=[],
            source_dirs=[],
        )

        # File outside workspace should not be loaded
        assert result == {}


class TestMaxCharsPerFile:
    """Tests for max characters per file truncation."""

    def test_large_file_truncated(self, tmp_path):
        """Should truncate files exceeding max_chars_per_file."""
        loader = HeuristicContextLoader(max_chars_per_file=100)

        # Create large file
        large_content = "x" * 1000
        (tmp_path / "large.py").write_text(large_content)

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=["large.py"],
            mentioned_files=[],
            priority_files=[],
            source_dirs=[],
        )

        # Content should be truncated
        assert "large.py" in result
        assert len(result["large.py"]) == 100


class TestSourceDirectoryScan:
    """Tests for source directory scanning."""

    def test_scan_multiple_source_dirs(self, tmp_path):
        """Should scan multiple source directories."""
        loader = HeuristicContextLoader(max_files=10)

        # Create multiple source directories
        src_dir = tmp_path / "src"
        backend_dir = tmp_path / "backend"
        src_dir.mkdir()
        backend_dir.mkdir()

        (src_dir / "file1.py").write_text("# src file")
        (backend_dir / "file2.py").write_text("# backend file")

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=[],
            mentioned_files=[],
            priority_files=[],
            source_dirs=["src", "backend"],
        )

        # Should find files in both directories
        assert len(result) == 2

    def test_nonexistent_source_dir_skipped(self, tmp_path):
        """Should skip source directories that don't exist."""
        loader = HeuristicContextLoader()

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=[],
            mentioned_files=[],
            priority_files=[],
            source_dirs=["nonexistent"],
        )

        assert result == {}

    def test_pycache_files_skipped(self, tmp_path):
        """Should skip __pycache__ files."""
        loader = HeuristicContextLoader()

        src_dir = tmp_path / "src"
        pycache_dir = src_dir / "__pycache__"
        src_dir.mkdir()
        pycache_dir.mkdir()

        (src_dir / "good.py").write_text("# good")
        (pycache_dir / "bad.pyc").write_text("# bad")

        result = loader.load_context_files(
            workspace=tmp_path,
            git_status_files=[],
            mentioned_files=[],
            priority_files=[],
            source_dirs=["src"],
        )

        # Should only load good.py, not .pyc file
        assert "src/good.py" in result or "src\\good.py" in result
        assert "__pycache__" not in str(result.keys())
