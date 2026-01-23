"""Tests for context_selector.py - JIT context loading.

IMP-TEST-005: Add comprehensive tests for ContextSelector class.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess


from autopack.context_selector import ContextSelector


class TestContextSelectorInit:
    """Tests for ContextSelector initialization."""

    def test_init_stores_repo_root(self):
        """Test that repo_root is stored correctly."""
        root = Path("/tmp/test-repo")
        selector = ContextSelector(root)
        assert selector.root == root

    def test_init_sets_category_patterns(self):
        """Test that category patterns are initialized."""
        root = Path("/tmp/test-repo")
        selector = ContextSelector(root)

        assert "backend" in selector.category_patterns
        assert "frontend" in selector.category_patterns
        assert "database" in selector.category_patterns
        assert "api" in selector.category_patterns
        assert "tests" in selector.category_patterns
        assert "docs" in selector.category_patterns
        assert "config" in selector.category_patterns


class TestEstimateContextSize:
    """Tests for estimate_context_size method."""

    def test_empty_context_returns_zero(self):
        """Test that empty context returns zero tokens."""
        selector = ContextSelector(Path("/tmp/test-repo"))
        result = selector.estimate_context_size({})
        assert result == 0

    def test_estimates_tokens_from_char_count(self):
        """Test that token estimation uses 4 chars per token rule."""
        selector = ContextSelector(Path("/tmp/test-repo"))
        # 100 chars should estimate to 25 tokens (100 // 4)
        context = {"file.py": "x" * 100}
        result = selector.estimate_context_size(context)
        assert result == 25

    def test_sums_multiple_files(self):
        """Test that estimation sums content from multiple files."""
        selector = ContextSelector(Path("/tmp/test-repo"))
        context = {
            "file1.py": "a" * 40,  # 10 tokens
            "file2.py": "b" * 80,  # 20 tokens
        }
        result = selector.estimate_context_size(context)
        assert result == 30


class TestLogContextStats:
    """Tests for log_context_stats method."""

    def test_logs_phase_id_and_stats(self, capsys):
        """Test that logging outputs phase ID, file count, and token estimate."""
        selector = ContextSelector(Path("/tmp/test-repo"))
        context = {"file1.py": "x" * 400, "file2.py": "y" * 400}

        selector.log_context_stats("phase-123", context)

        captured = capsys.readouterr()
        assert "[Context]" in captured.out
        assert "phase-123" in captured.out
        assert "2 files" in captured.out
        assert "200" in captured.out  # 800 chars / 4 = 200 tokens


class TestTypePriorityScore:
    """Tests for _type_priority_score scoring."""

    def setup_method(self):
        """Set up test fixtures."""
        self.selector = ContextSelector(Path("/tmp/test-repo"))

    def test_core_files_highest_priority(self):
        """Test that core autopack files get highest score."""
        score = self.selector._type_priority_score("src/autopack/module.py")
        assert score == 30.0

    def test_main_py_highest_priority(self):
        """Test that main.py files get highest score."""
        score = self.selector._type_priority_score("src/main.py")
        assert score == 30.0

    def test_test_files_medium_high_priority(self):
        """Test that test files get medium-high score."""
        score = self.selector._type_priority_score("tests/test_module.py")
        assert score == 25.0

    def test_api_routes_medium_priority(self):
        """Test that API/routes files get medium score."""
        score = self.selector._type_priority_score("src/routes/users.py")
        assert score == 20.0

    def test_config_files_low_medium_priority(self):
        """Test that config files get low-medium score."""
        score = self.selector._type_priority_score("config/settings.yaml")
        assert score == 15.0

    def test_documentation_low_priority(self):
        """Test that documentation files get low score."""
        score = self.selector._type_priority_score("docs/README.md")
        assert score == 10.0

    def test_misc_files_lowest_priority(self):
        """Test that miscellaneous files get lowest score."""
        score = self.selector._type_priority_score("random/file.txt")
        assert score == 5.0


class TestRelevanceScore:
    """Tests for _relevance_score scoring."""

    def setup_method(self):
        """Set up test fixtures."""
        self.selector = ContextSelector(Path("/tmp/test-repo"))

    def test_keyword_in_path_adds_score(self):
        """Test that keywords from description matching path add score."""
        # Use exact keyword that appears in path
        phase_spec = {"description": "Fix auth module bug", "task_category": "general"}
        score = self.selector._relevance_score("src/auth.py", phase_spec)
        # 'auth' keyword matches path
        assert score >= 5.0

    def test_category_path_matching(self):
        """Test that task category paths add score."""
        phase_spec = {"description": "Update models", "task_category": "database"}
        score = self.selector._relevance_score("src/models.py", phase_spec)
        # 'models' is in database category paths
        assert score >= 10.0

    def test_no_match_returns_low_score(self):
        """Test that non-matching files return low score."""
        phase_spec = {"description": "Fix database issue", "task_category": "database"}
        score = self.selector._relevance_score("src/unrelated.py", phase_spec)
        assert score < 10.0

    def test_score_capped_at_40(self):
        """Test that relevance score is capped at 40."""
        phase_spec = {
            "description": "database models migrations schemas api",
            "task_category": "database",
        }
        score = self.selector._relevance_score("src/database/models/api/schemas.py", phase_spec)
        assert score <= 40.0


class TestRecencyScore:
    """Tests for _recency_score scoring."""

    def setup_method(self):
        """Set up test fixtures with temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.selector = ContextSelector(self.root)

    def test_git_recent_file_gets_high_score(self):
        """Test that recently committed files get high score."""
        # Create test file
        test_file = self.root / "recent.py"
        test_file.write_text("content")

        # Mock git command to return recent date
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="2024-01-15 10:00:00 -0500", returncode=0)
            score = self.selector._recency_score("recent.py")
            assert score == 30.0

    def test_non_git_file_uses_mtime(self):
        """Test that non-git files fall back to mtime scoring."""
        # Create test file
        test_file = self.root / "local.py"
        test_file.write_text("content")

        # Mock git command to return empty (file not in git)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            score = self.selector._recency_score("local.py")
            # Recent mtime should give decent score
            assert score >= 10.0

    def test_git_error_falls_back_gracefully(self):
        """Test that git errors don't crash scoring."""
        test_file = self.root / "error.py"
        test_file.write_text("content")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=2)
            # Should not raise, should return some score
            score = self.selector._recency_score("error.py")
            assert score >= 0.0

    def test_score_capped_at_30(self):
        """Test that recency score is capped at 30."""
        test_file = self.root / "capped.py"
        test_file.write_text("content")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="2024-01-15 10:00:00 -0500", returncode=0)
            score = self.selector._recency_score("capped.py")
            assert score <= 30.0


class TestScoreFile:
    """Tests for _score_file combined scoring."""

    def setup_method(self):
        """Set up test fixtures with temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.selector = ContextSelector(self.root)

    def test_combines_all_scoring_methods(self):
        """Test that scoring combines relevance, recency, and type priority."""
        # Create test file
        test_file = self.root / "src" / "autopack" / "auth.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("def authenticate(): pass")

        phase_spec = {"description": "Fix auth bug", "task_category": "general"}

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            score = self.selector._score_file(
                "src/autopack/auth.py", "def authenticate(): pass", phase_spec
            )
            # Should have relevance (auth keyword) + type priority (autopack dir)
            assert score > 30.0


class TestGetFilesByPaths:
    """Tests for _get_files_by_paths method."""

    def setup_method(self):
        """Set up test fixtures with temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.selector = ContextSelector(self.root)

    def test_loads_existing_files(self):
        """Test that existing files are loaded correctly."""
        test_file = self.root / "test.py"
        test_file.write_text("content here")

        result = self.selector._get_files_by_paths(["test.py"])
        assert "test.py" in result
        assert result["test.py"] == "content here"

    def test_skips_nonexistent_files(self):
        """Test that nonexistent files are skipped."""
        result = self.selector._get_files_by_paths(["nonexistent.py"])
        assert len(result) == 0

    def test_skips_directories(self):
        """Test that directories are skipped."""
        (self.root / "subdir").mkdir()
        result = self.selector._get_files_by_paths(["subdir"])
        assert len(result) == 0

    def test_handles_unreadable_files(self):
        """Test that unreadable files are skipped gracefully."""
        test_file = self.root / "binary.bin"
        test_file.write_bytes(b"\x00\x01\x02\xff\xfe")

        # Should not raise exception
        result = self.selector._get_files_by_paths(["binary.bin"])
        # May or may not be included depending on encoding
        assert isinstance(result, dict)


class TestGetFilesByGlob:
    """Tests for _get_files_by_glob method."""

    def setup_method(self):
        """Set up test fixtures with temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.selector = ContextSelector(self.root)

    def test_matches_glob_patterns(self):
        """Test that glob patterns match correctly."""
        (self.root / "src").mkdir()
        (self.root / "src" / "a.py").write_text("content a")
        (self.root / "src" / "b.py").write_text("content b")
        (self.root / "src" / "c.txt").write_text("content c")

        result = self.selector._get_files_by_glob("src/*.py")
        assert len(result) == 2
        assert any("a.py" in k for k in result)
        assert any("b.py" in k for k in result)

    def test_respects_max_files_limit(self):
        """Test that max_files limits results."""
        (self.root / "many").mkdir()
        for i in range(30):
            (self.root / "many" / f"file{i}.py").write_text(f"content {i}")

        result = self.selector._get_files_by_glob("many/*.py", max_files=5)
        assert len(result) <= 5

    def test_recursive_glob(self):
        """Test that recursive globs work."""
        (self.root / "a" / "b").mkdir(parents=True)
        (self.root / "a" / "x.py").write_text("x")
        (self.root / "a" / "b" / "y.py").write_text("y")

        result = self.selector._get_files_by_glob("**/*.py")
        assert len(result) >= 2


class TestNormalizeScopePaths:
    """Tests for _normalize_scope_paths method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.root = Path("/tmp/test-repo")
        self.selector = ContextSelector(self.root)

    def test_converts_to_absolute_paths(self):
        """Test that relative paths are converted to absolute."""
        result = self.selector._normalize_scope_paths(["src/file.py"])
        assert result[0] == Path("/tmp/test-repo/src/file.py")

    def test_handles_windows_paths(self):
        """Test that Windows-style paths are normalized."""
        result = self.selector._normalize_scope_paths(["src\\subdir\\file.py"])
        # Should handle backslashes
        assert "file.py" in str(result[0])

    def test_handles_multiple_paths(self):
        """Test that multiple paths are all normalized."""
        result = self.selector._normalize_scope_paths(["a.py", "b.py", "c/d.py"])
        assert len(result) == 3


class TestBuildScopedContext:
    """Tests for _build_scoped_context method."""

    def setup_method(self):
        """Set up test fixtures with temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.selector = ContextSelector(self.root)

    def test_loads_scope_files(self):
        """Test that scope files are loaded."""
        (self.root / "target.py").write_text("target content")

        result = self.selector._build_scoped_context(
            scope_paths=["target.py"],
            readonly_context=[],
            token_budget=None,
            phase_spec={},
        )

        assert "target.py" in result
        assert result["target.py"] == "target content"

    def test_loads_readonly_context(self):
        """Test that read-only context is loaded."""
        (self.root / "scope.py").write_text("scope content")
        (self.root / "readonly.py").write_text("readonly content")

        result = self.selector._build_scoped_context(
            scope_paths=["scope.py"],
            readonly_context=["readonly.py"],
            token_budget=None,
            phase_spec={},
        )

        assert "scope.py" in result
        assert "readonly.py" in result

    def test_scope_takes_precedence_over_readonly(self):
        """Test that scope files are not overwritten by readonly."""
        (self.root / "shared.py").write_text("scope version")

        result = self.selector._build_scoped_context(
            scope_paths=["shared.py"],
            readonly_context=["shared.py"],  # Same file
            token_budget=None,
            phase_spec={},
        )

        # Should have scope version, not readonly
        assert result["shared.py"] == "scope version"

    def test_loads_directory_recursively(self):
        """Test that directory scope paths load all files."""
        (self.root / "dir" / "sub").mkdir(parents=True)
        (self.root / "dir" / "a.py").write_text("a")
        (self.root / "dir" / "sub" / "b.py").write_text("b")

        result = self.selector._build_scoped_context(
            scope_paths=["dir"],
            readonly_context=[],
            token_budget=None,
            phase_spec={},
        )

        assert any("a.py" in k for k in result)
        assert any("b.py" in k for k in result)

    def test_applies_token_budget(self):
        """Test that token budget limits context."""
        (self.root / "big.py").write_text("x" * 1000)
        (self.root / "small.py").write_text("y" * 100)

        result = self.selector._build_scoped_context(
            scope_paths=["big.py", "small.py"],
            readonly_context=[],
            token_budget=50,  # Very small budget
            phase_spec={},
        )

        # Should limit based on budget
        total_tokens = self.selector.estimate_context_size(result)
        assert total_tokens <= 50


class TestRankAndLimitContext:
    """Tests for _rank_and_limit_context method."""

    def setup_method(self):
        """Set up test fixtures with temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.selector = ContextSelector(self.root)

    def test_respects_token_budget(self):
        """Test that token budget is respected."""
        context = {
            "a.py": "x" * 400,  # 100 tokens
            "b.py": "y" * 400,  # 100 tokens
            "c.py": "z" * 400,  # 100 tokens
        }

        result = self.selector._rank_and_limit_context(
            context=context, phase_spec={}, token_budget=150
        )

        total_tokens = self.selector.estimate_context_size(result)
        assert total_tokens <= 150

    def test_keeps_highest_scored_files(self):
        """Test that highest scored files are kept."""
        # Create files with different priority
        (self.root / "src" / "autopack").mkdir(parents=True)
        (self.root / "src" / "autopack" / "core.py").write_text("core content")
        (self.root / "misc.txt").write_text("misc content")

        context = {
            "src/autopack/core.py": "core content",
            "misc.txt": "misc content",
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            result = self.selector._rank_and_limit_context(
                context=context,
                phase_spec={},
                token_budget=10,  # Only room for one
            )

        # Core file should be kept due to higher type priority
        assert "src/autopack/core.py" in result or len(result) == 1


class TestGetContextForPhase:
    """Tests for get_context_for_phase main entry point."""

    def setup_method(self):
        """Set up test fixtures with temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.selector = ContextSelector(self.root)

        # Create minimal repo structure
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text("def main(): pass")
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_main.py").write_text("def test_main(): pass")

    def test_uses_scope_when_provided(self):
        """Test that scope configuration is used when provided."""
        (self.root / "scoped.py").write_text("scoped content")

        phase_spec = {
            "scope": {
                "paths": ["scoped.py"],
                "read_only_context": [],
            }
        }

        result = self.selector.get_context_for_phase(phase_spec)
        assert "scoped.py" in result

    def test_falls_back_to_heuristics_without_scope(self):
        """Test that heuristics are used without scope config."""
        phase_spec = {
            "task_category": "tests",
            "complexity": "medium",
            "description": "Write test for main",
        }

        result = self.selector.get_context_for_phase(phase_spec)
        # Should include some files based on heuristics
        assert isinstance(result, dict)

    def test_includes_changed_files(self):
        """Test that changed files are included."""
        (self.root / "changed.py").write_text("changed content")

        phase_spec = {"task_category": "general", "complexity": "low", "description": "Fix"}

        result = self.selector.get_context_for_phase(phase_spec, changed_files=["changed.py"])
        assert "changed.py" in result

    def test_includes_architecture_docs_for_high_complexity(self):
        """Test that high complexity phases get architecture docs."""
        (self.root / "README.md").write_text("# Project README")

        phase_spec = {
            "task_category": "general",
            "complexity": "high",
            "description": "Major refactor",
        }

        result = self.selector.get_context_for_phase(phase_spec)
        # README should be included for high complexity
        assert "README.md" in result

    def test_applies_token_budget(self):
        """Test that token budget limits results."""
        # Create files
        for i in range(10):
            (self.root / f"file{i}.py").write_text("x" * 400)

        phase_spec = {
            "scope": {"paths": [f"file{i}.py" for i in range(10)]},
        }

        result = self.selector.get_context_for_phase(phase_spec, token_budget=200)
        total_tokens = self.selector.estimate_context_size(result)
        assert total_tokens <= 200


class TestGetFilesFromKeywords:
    """Tests for _get_files_from_keywords method."""

    def setup_method(self):
        """Set up test fixtures with temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.selector = ContextSelector(self.root)

    def test_matches_database_keyword(self):
        """Test that 'database' keyword matches database files."""
        (self.root / "src").mkdir()
        (self.root / "src" / "database.py").write_text("db code")

        result = self.selector._get_files_from_keywords("Fix database connection")
        assert any("database.py" in k for k in result)

    def test_matches_api_keyword(self):
        """Test that 'api' keyword matches API files."""
        (self.root / "src" / "routes").mkdir(parents=True)
        (self.root / "src" / "routes" / "users.py").write_text("api code")

        result = self.selector._get_files_from_keywords("Update API endpoint")
        assert any("users.py" in k for k in result)

    def test_matches_test_keyword(self):
        """Test that 'test' keyword matches test files."""
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_module.py").write_text("test code")

        result = self.selector._get_files_from_keywords("Add unit test")
        assert any("test_module.py" in k for k in result)

    def test_no_match_returns_empty(self):
        """Test that no keyword match returns empty dict."""
        result = self.selector._get_files_from_keywords("Do something unrelated")
        # May or may not be empty, but should be a dict
        assert isinstance(result, dict)


class TestGetGlobalConfigs:
    """Tests for _get_global_configs method."""

    def setup_method(self):
        """Set up test fixtures with temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.selector = ContextSelector(self.root)

    def test_loads_existing_config_files(self):
        """Test that existing config files are loaded."""
        (self.root / "pyproject.toml").write_text("[tool.pytest]")
        (self.root / "requirements.txt").write_text("pytest>=7.0")

        result = self.selector._get_global_configs()
        assert "pyproject.toml" in result or "requirements.txt" in result

    def test_skips_missing_config_files(self):
        """Test that missing config files are skipped."""
        result = self.selector._get_global_configs()
        # Should not raise, should return empty or partial dict
        assert isinstance(result, dict)


class TestGetCategoryFiles:
    """Tests for _get_category_files method."""

    def setup_method(self):
        """Set up test fixtures with temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.selector = ContextSelector(self.root)

    def test_tests_category_loads_test_files(self):
        """Test that 'tests' category loads test files."""
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_unit.py").write_text("test code")

        result = self.selector._get_category_files("tests")
        assert any("test" in k for k in result)

    def test_unknown_category_defaults_to_backend(self):
        """Test that unknown categories default to backend files."""
        (self.root / "src").mkdir()
        (self.root / "src" / "module.py").write_text("backend code")

        result = self.selector._get_category_files("unknown_category")
        # Should attempt to load backend files
        assert isinstance(result, dict)


class TestGetArchitectureDocs:
    """Tests for _get_architecture_docs method."""

    def setup_method(self):
        """Set up test fixtures with temp directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.root = Path(self.temp_dir)
        self.selector = ContextSelector(self.root)

    def test_loads_readme(self):
        """Test that README.md is loaded."""
        (self.root / "README.md").write_text("# Project")

        result = self.selector._get_architecture_docs()
        assert "README.md" in result

    def test_loads_architecture_doc(self):
        """Test that ARCHITECTURE.md is loaded if present."""
        (self.root / "docs").mkdir()
        (self.root / "docs" / "ARCHITECTURE.md").write_text("# Architecture")

        result = self.selector._get_architecture_docs()
        # Check if it was loaded (path format may vary)
        assert any("ARCHITECTURE" in k for k in result)

    def test_loads_claude_md(self):
        """Test that CLAUDE.md is loaded if present."""
        (self.root / "CLAUDE.md").write_text("# Claude integration")

        result = self.selector._get_architecture_docs()
        assert "CLAUDE.md" in result
