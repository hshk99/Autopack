"""Contract tests for context heuristics module.

These tests verify the context_heuristics module behavior contract for PR-EXE-6.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
import subprocess

from autopack.executor.context_heuristics import (
    ContextLoadResult,
    FileLoader,
    get_recently_modified_files,
    extract_mentioned_files,
    load_priority_config_files,
    load_source_directories,
    load_repository_context_heuristic,
    load_targeted_context_for_patterns,
    load_template_context,
    load_frontend_context,
    load_docker_context,
    normalize_rel_path,
    is_file_in_scope,
    REPO_ROOT_BUCKETS,
    ALLOWED_SCOPE_EXTENSIONS,
    SCOPE_DENYLIST_DIRS,
)


class TestContextLoadResult:
    """Contract tests for ContextLoadResult dataclass."""

    def test_default_values(self):
        """Contract: Result has sensible defaults."""
        result = ContextLoadResult(existing_files={})

        assert result.files_loaded == 0
        assert result.modified_files_loaded == 0
        assert result.tokens_estimated == 0
        assert result.token_budget == 20000

    def test_with_files(self):
        """Contract: Result captures file counts."""
        result = ContextLoadResult(
            existing_files={"file1.py": "content", "file2.py": "content"},
            files_loaded=2,
            tokens_estimated=100,
        )

        assert result.files_loaded == 2
        assert len(result.existing_files) == 2


class TestFileLoader:
    """Contract tests for FileLoader class."""

    def test_estimate_tokens(self, tmp_path):
        """Contract: Token estimation uses ~4 chars per token."""
        loader = FileLoader(workspace=tmp_path)

        assert loader.estimate_tokens("1234567890") == 2  # 10 chars / 4 = 2
        assert loader.estimate_tokens("12345678") == 2  # 8 chars / 4 = 2
        assert loader.estimate_tokens("") == 0

    def test_load_file_success(self, tmp_path):
        """Contract: Loads file and tracks it."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        loader = FileLoader(workspace=tmp_path)
        result = loader.load_file(test_file)

        assert result is True
        assert "test.py" in loader.existing_files
        assert "test.py" in loader.loaded_paths

    def test_load_file_skips_duplicates(self, tmp_path):
        """Contract: Skips already loaded files."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        loader = FileLoader(workspace=tmp_path)
        loader.load_file(test_file)
        result = loader.load_file(test_file)

        assert result is False
        assert len(loader.existing_files) == 1

    def test_load_file_respects_max_files(self, tmp_path):
        """Contract: Respects max files limit."""
        loader = FileLoader(workspace=tmp_path, max_files=2)

        for i in range(3):
            f = tmp_path / f"file{i}.py"
            f.write_text(f"content {i}")

        loader.load_file(tmp_path / "file0.py")
        loader.load_file(tmp_path / "file1.py")
        result = loader.load_file(tmp_path / "file2.py")

        assert result is False
        assert len(loader.existing_files) == 2

    def test_load_file_respects_token_budget(self, tmp_path):
        """Contract: Stops loading when token budget exceeded."""
        loader = FileLoader(workspace=tmp_path, target_tokens=10)

        # Create file with ~50 tokens worth of content
        large_file = tmp_path / "large.py"
        large_file.write_text("x" * 200)  # 200 chars = ~50 tokens

        result = loader.load_file(large_file)

        assert result is False
        assert len(loader.existing_files) == 0

    def test_load_file_skips_pycache(self, tmp_path):
        """Contract: Skips __pycache__ directories."""
        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        cached_file = pycache / "module.cpython-312.pyc"
        cached_file.write_text("bytecode")

        loader = FileLoader(workspace=tmp_path)
        result = loader.load_file(cached_file)

        assert result is False

    def test_load_file_skips_nonexistent(self, tmp_path):
        """Contract: Skips non-existent files."""
        loader = FileLoader(workspace=tmp_path)
        result = loader.load_file(tmp_path / "nonexistent.py")

        assert result is False

    def test_get_result(self, tmp_path):
        """Contract: get_result returns proper ContextLoadResult."""
        test_file = tmp_path / "test.py"
        test_file.write_text("content")

        loader = FileLoader(workspace=tmp_path)
        loader.load_file(test_file)
        result = loader.get_result()

        assert result.files_loaded == 1
        assert "test.py" in result.existing_files


class TestGetRecentlyModifiedFiles:
    """Contract tests for get_recently_modified_files function."""

    def test_parses_git_status(self, tmp_path):
        """Contract: Parses git status output correctly."""
        with patch("autopack.executor.context_heuristics.subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            # Git status format: XY filename (2 chars status + space + filename)
            mock_result.stdout = " M file1.py\nA  file2.py\n?? newfile.py"
            mock_run.return_value = mock_result

            files = get_recently_modified_files(tmp_path)

            assert "file1.py" in files
            assert "file2.py" in files
            assert "newfile.py" in files

    def test_handles_rename_format(self, tmp_path):
        """Contract: Handles git rename format (old -> new)."""
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = "R  old.py -> new.py"
            mock_run.return_value = mock_result

            files = get_recently_modified_files(tmp_path)

            assert "new.py" in files
            assert "old.py" not in files

    def test_handles_empty_status(self, tmp_path):
        """Contract: Returns empty list for clean repo."""
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_run.return_value = mock_result

            files = get_recently_modified_files(tmp_path)

            assert files == []

    def test_handles_timeout(self, tmp_path):
        """Contract: Returns empty list on timeout."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 10)

            files = get_recently_modified_files(tmp_path)

            assert files == []

    def test_handles_git_error(self, tmp_path):
        """Contract: Returns empty list on git error."""
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 128
            mock_result.stdout = ""
            mock_run.return_value = mock_result

            files = get_recently_modified_files(tmp_path)

            assert files == []


class TestExtractMentionedFiles:
    """Contract tests for extract_mentioned_files function."""

    def test_extracts_python_files(self):
        """Contract: Extracts Python file paths."""
        text = "Modify src/autopack/executor.py to add feature"

        files = extract_mentioned_files(text)

        assert "src/autopack/executor.py" in files

    def test_extracts_multiple_extensions(self):
        """Contract: Extracts various file types."""
        text = "Update config/models.yaml and package.json and README.md"

        files = extract_mentioned_files(text)

        assert "config/models.yaml" in files
        assert "package.json" in files
        assert "README.md" in files

    def test_limits_to_10_files(self):
        """Contract: Limits results to 10 files."""
        text = " ".join([f"file{i}.py" for i in range(20)])

        files = extract_mentioned_files(text)

        assert len(files) == 10

    def test_handles_empty_text(self):
        """Contract: Returns empty list for empty text."""
        files = extract_mentioned_files("")

        assert files == []


class TestLoadPriorityConfigFiles:
    """Contract tests for load_priority_config_files function."""

    def test_loads_existing_config_files(self, tmp_path):
        """Contract: Loads existing priority config files."""
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "README.md").write_text("# Test")

        loader = FileLoader(workspace=tmp_path)
        count = load_priority_config_files(loader)

        assert count == 2
        assert "package.json" in loader.existing_files
        assert "README.md" in loader.existing_files

    def test_skips_missing_files(self, tmp_path):
        """Contract: Skips files that don't exist."""
        loader = FileLoader(workspace=tmp_path)
        count = load_priority_config_files(loader)

        assert count == 0


class TestLoadSourceDirectories:
    """Contract tests for load_source_directories function."""

    def test_loads_from_src_directory(self, tmp_path):
        """Contract: Loads Python files from src/."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("code")

        loader = FileLoader(workspace=tmp_path)
        count = load_source_directories(loader)

        assert count == 1
        assert "src/module.py" in loader.existing_files

    def test_loads_from_custom_directories(self, tmp_path):
        """Contract: Loads from custom directory list."""
        app_dir = tmp_path / "myapp"
        app_dir.mkdir()
        (app_dir / "main.py").write_text("code")

        loader = FileLoader(workspace=tmp_path)
        count = load_source_directories(loader, source_dirs=["myapp"])

        assert count == 1
        assert "myapp/main.py" in loader.existing_files

    def test_skips_nonexistent_directories(self, tmp_path):
        """Contract: Skips directories that don't exist."""
        loader = FileLoader(workspace=tmp_path)
        count = load_source_directories(loader)

        assert count == 0


class TestLoadRepositoryContextHeuristic:
    """Contract tests for load_repository_context_heuristic function."""

    def test_loads_with_priorities(self, tmp_path):
        """Contract: Loads files with correct priority order."""
        # Create source directory
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("code")
        (tmp_path / "package.json").write_text('{}')

        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_run.return_value = mock_result

            phase = {"description": "Test phase", "acceptance_criteria": []}
            result = load_repository_context_heuristic(tmp_path, phase)

            assert result.files_loaded > 0
            assert "package.json" in result.existing_files

    def test_respects_token_budget(self, tmp_path):
        """Contract: Respects token budget limit."""
        # Create many files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        for i in range(50):
            (src_dir / f"module{i}.py").write_text("x" * 1000)

        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_run.return_value = mock_result

            phase = {"description": "Test", "acceptance_criteria": []}
            result = load_repository_context_heuristic(
                tmp_path, phase, target_tokens=1000
            )

            assert result.tokens_estimated <= 1000


class TestLoadTargetedContextForPatterns:
    """Contract tests for load_targeted_context_for_patterns function."""

    def test_loads_matching_patterns(self, tmp_path):
        """Contract: Loads files matching glob patterns."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "module.py").write_text("code")
        (src_dir / "other.txt").write_text("text")

        files = load_targeted_context_for_patterns(tmp_path, ["src/*.py"])

        assert "src/module.py" in files
        assert "src/other.txt" not in files

    def test_excludes_specified_directories(self, tmp_path):
        """Contract: Excludes specified directories."""
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        (node_modules / "dep.js").write_text("code")

        files = load_targeted_context_for_patterns(
            tmp_path, ["**/*.js"], exclude_dirs={"node_modules"}
        )

        assert len(files) == 0


class TestLoadTemplateContext:
    """Contract tests for load_template_context function."""

    def test_loads_template_files(self, tmp_path):
        """Contract: Loads template-related files."""
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        (templates_dir / "base.yaml").write_text("template: base")

        files = load_template_context(tmp_path)

        assert "templates/base.yaml" in files


class TestLoadFrontendContext:
    """Contract tests for load_frontend_context function."""

    def test_loads_frontend_files(self, tmp_path):
        """Contract: Loads frontend-related files."""
        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        (frontend_dir / "App.tsx").write_text("export default App")

        files = load_frontend_context(tmp_path)

        assert "frontend/App.tsx" in files


class TestLoadDockerContext:
    """Contract tests for load_docker_context function."""

    def test_loads_docker_files(self, tmp_path):
        """Contract: Loads docker-related files."""
        (tmp_path / "Dockerfile").write_text("FROM python:3.12")
        (tmp_path / "docker-compose.yml").write_text("version: '3'")

        files = load_docker_context(tmp_path)

        assert "Dockerfile" in files
        assert "docker-compose.yml" in files


class TestNormalizeRelPath:
    """Contract tests for normalize_rel_path function."""

    def test_replaces_backslashes(self):
        """Contract: Replaces backslashes with forward slashes."""
        assert normalize_rel_path("src\\autopack\\file.py") == "src/autopack/file.py"

    def test_removes_leading_dot_slash(self):
        """Contract: Removes leading ./ from path."""
        assert normalize_rel_path("./src/file.py") == "src/file.py"
        assert normalize_rel_path("././src/file.py") == "src/file.py"

    def test_handles_empty_string(self):
        """Contract: Returns empty string for empty input."""
        assert normalize_rel_path("") == ""


class TestIsFileInScope:
    """Contract tests for is_file_in_scope function."""

    def test_exact_match(self):
        """Contract: Returns True for exact scope match."""
        scope_set = {"src/file.py", "config/settings.yaml"}

        assert is_file_in_scope("src/file.py", scope_set, []) is True
        assert is_file_in_scope("other.py", scope_set, []) is False

    def test_prefix_match(self):
        """Contract: Returns True for directory prefix match."""
        scope_set = set()
        prefixes = ["src/", "config/"]

        assert is_file_in_scope("src/module/file.py", scope_set, prefixes) is True
        assert is_file_in_scope("tests/test.py", scope_set, prefixes) is False


class TestConstants:
    """Contract tests for module constants."""

    def test_repo_root_buckets(self):
        """Contract: Contains expected repo root directories."""
        assert "src" in REPO_ROOT_BUCKETS
        assert "docs" in REPO_ROOT_BUCKETS
        assert "tests" in REPO_ROOT_BUCKETS
        assert "config" in REPO_ROOT_BUCKETS

    def test_allowed_scope_extensions(self):
        """Contract: Contains expected file extensions."""
        assert ".py" in ALLOWED_SCOPE_EXTENSIONS
        assert ".ts" in ALLOWED_SCOPE_EXTENSIONS
        assert ".yaml" in ALLOWED_SCOPE_EXTENSIONS
        assert ".json" in ALLOWED_SCOPE_EXTENSIONS

    def test_scope_denylist_dirs(self):
        """Contract: Contains expected denylist directories."""
        assert "node_modules" in SCOPE_DENYLIST_DIRS
        assert "__pycache__" in SCOPE_DENYLIST_DIRS
        assert "venv" in SCOPE_DENYLIST_DIRS
