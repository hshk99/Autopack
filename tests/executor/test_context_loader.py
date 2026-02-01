"""Tests for ExecutorContextLoader.

IMP-MAINT-006: Tests for context loading utilities extracted from autonomous_executor.py.
"""

from pathlib import Path
from unittest.mock import MagicMock

from autopack.executor.context_loader import (ExecutorContextLoader,
                                              derive_allowed_paths_from_scope,
                                              determine_workspace_root,
                                              resolve_scope_target)


class TestExecutorContextLoader:
    """Tests for ExecutorContextLoader class."""

    def test_init(self):
        """Test initialization with default values."""
        loader = ExecutorContextLoader(
            workspace=Path("/test/workspace"),
            run_type="project_build",
        )
        assert loader.workspace == Path("/test/workspace")
        assert loader.run_type == "project_build"

    def test_determine_workspace_root_autopack_maintenance(self):
        """Test that autopack_maintenance returns workspace root."""
        loader = ExecutorContextLoader(
            workspace=Path("/test/autopack"),
            run_type="autopack_maintenance",
        )
        scope_config = {"paths": ["src/some/path"]}
        result = loader.determine_workspace_root(scope_config)
        assert result == Path("/test/autopack")

    def test_determine_workspace_root_autopack_upgrade(self):
        """Test that autopack_upgrade returns workspace root."""
        loader = ExecutorContextLoader(
            workspace=Path("/test/autopack"),
            run_type="autopack_upgrade",
        )
        scope_config = {"paths": ["src/some/path"]}
        result = loader.determine_workspace_root(scope_config)
        assert result == Path("/test/autopack")

    def test_determine_workspace_root_self_repair(self):
        """Test that self_repair returns workspace root."""
        loader = ExecutorContextLoader(
            workspace=Path("/test/autopack"),
            run_type="self_repair",
        )
        scope_config = {"paths": ["src/some/path"]}
        result = loader.determine_workspace_root(scope_config)
        assert result == Path("/test/autopack")

    def test_determine_workspace_root_autonomous_runs_prefix(self, tmp_path):
        """Test workspace root from .autonomous_runs prefix."""
        loader = ExecutorContextLoader(
            workspace=tmp_path,
            run_type="project_build",
        )
        scope_config = {"paths": [".autonomous_runs/myproject/src/file.py"]}
        result = loader.determine_workspace_root(scope_config)
        assert result == tmp_path / ".autonomous_runs" / "myproject"

    def test_determine_workspace_root_repo_bucket(self, tmp_path):
        """Test workspace root from repo bucket (src, docs, etc.)."""
        loader = ExecutorContextLoader(
            workspace=tmp_path,
            run_type="project_build",
        )
        # Test each known bucket
        for bucket in ["src", "docs", "tests", "config", "scripts"]:
            scope_config = {"paths": [f"{bucket}/some/file.py"]}
            result = loader.determine_workspace_root(scope_config)
            assert result == tmp_path.resolve()

    def test_determine_workspace_root_project_directory(self, tmp_path):
        """Test workspace root from project directory that exists."""
        # Create a project directory
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()

        loader = ExecutorContextLoader(
            workspace=tmp_path,
            run_type="project_build",
        )
        scope_config = {"paths": ["myproject/src/file.py"]}
        result = loader.determine_workspace_root(scope_config)
        assert result == project_dir.resolve()

    def test_determine_workspace_root_fallback(self, tmp_path):
        """Test fallback to default workspace when no paths match."""
        loader = ExecutorContextLoader(
            workspace=tmp_path,
            run_type="project_build",
        )
        scope_config = {"paths": []}
        result = loader.determine_workspace_root(scope_config)
        assert result == tmp_path

    def test_resolve_scope_target_absolute_path(self, tmp_path):
        """Test resolving absolute path."""
        loader = ExecutorContextLoader(workspace=tmp_path, run_type="project_build")

        # Create a file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        result = loader.resolve_scope_target(str(test_file), tmp_path, must_exist=True)
        assert result is not None
        abs_path, rel_key = result
        assert abs_path == test_file.resolve()
        assert rel_key == "test.txt"

    def test_resolve_scope_target_relative_path(self, tmp_path):
        """Test resolving relative path."""
        loader = ExecutorContextLoader(workspace=tmp_path, run_type="project_build")

        # Create a file
        test_file = tmp_path / "src" / "test.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("test")

        result = loader.resolve_scope_target("src/test.py", tmp_path, must_exist=True)
        assert result is not None
        abs_path, rel_key = result
        assert abs_path == test_file.resolve()
        assert "src/test.py" in rel_key or "src\\test.py" in rel_key

    def test_resolve_scope_target_must_exist_false(self, tmp_path):
        """Test resolving path that doesn't exist when must_exist=False."""
        loader = ExecutorContextLoader(workspace=tmp_path, run_type="project_build")

        result = loader.resolve_scope_target("nonexistent.py", tmp_path, must_exist=False)
        assert result is not None
        abs_path, rel_key = result
        assert "nonexistent.py" in rel_key

    def test_resolve_scope_target_must_exist_true_not_found(self, tmp_path):
        """Test resolving path that doesn't exist when must_exist=True."""
        loader = ExecutorContextLoader(workspace=tmp_path, run_type="project_build")

        result = loader.resolve_scope_target("nonexistent.py", tmp_path, must_exist=True)
        assert result is None

    def test_derive_allowed_paths_from_scope_empty(self):
        """Test deriving allowed paths from empty scope."""
        loader = ExecutorContextLoader(
            workspace=Path("/test/workspace"),
            run_type="project_build",
        )
        result = loader.derive_allowed_paths_from_scope(None)
        assert result == []

        result = loader.derive_allowed_paths_from_scope({})
        assert result == []

        result = loader.derive_allowed_paths_from_scope({"paths": []})
        assert result == []

    def test_load_targeted_context_for_templates(self, tmp_path):
        """Test loading targeted context for template phases."""
        loader = ExecutorContextLoader(workspace=tmp_path, run_type="project_build")

        # Create some template files
        templates_dir = tmp_path / "templates"
        templates_dir.mkdir()
        (templates_dir / "test.yaml").write_text("key: value")

        result = loader.load_targeted_context_for_templates(tmp_path)

        assert "existing_files" in result
        # Should have loaded the yaml file
        assert any("test.yaml" in key for key in result["existing_files"])

    def test_load_targeted_context_for_frontend(self, tmp_path):
        """Test loading targeted context for frontend phases."""
        loader = ExecutorContextLoader(workspace=tmp_path, run_type="project_build")

        # Create some frontend files
        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        (frontend_dir / "App.tsx").write_text("const App = () => <div/>;")
        (tmp_path / "package.json").write_text('{"name": "test"}')

        result = loader.load_targeted_context_for_frontend(tmp_path)

        assert "existing_files" in result
        # Should have loaded frontend files
        assert any("App.tsx" in key for key in result["existing_files"])
        assert any("package.json" in key for key in result["existing_files"])

    def test_load_targeted_context_for_docker(self, tmp_path):
        """Test loading targeted context for docker phases."""
        loader = ExecutorContextLoader(workspace=tmp_path, run_type="project_build")

        # Create some docker files
        (tmp_path / "Dockerfile").write_text("FROM python:3.11")
        (tmp_path / "docker-compose.yml").write_text("version: '3'")
        (tmp_path / "requirements.txt").write_text("flask==2.0.0")

        result = loader.load_targeted_context_for_docker(tmp_path)

        assert "existing_files" in result
        # Should have loaded docker files
        assert any("Dockerfile" in key for key in result["existing_files"])
        assert any("docker-compose.yml" in key for key in result["existing_files"])
        assert any("requirements.txt" in key for key in result["existing_files"])


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_determine_workspace_root_wrapper(self, tmp_path):
        """Test the convenience wrapper function."""
        mock_executor = MagicMock()
        mock_executor.workspace = str(tmp_path)
        mock_executor.run_type = "autopack_maintenance"

        scope_config = {"paths": ["src/file.py"]}
        result = determine_workspace_root(mock_executor, scope_config)
        assert result == tmp_path

    def test_resolve_scope_target_wrapper(self, tmp_path):
        """Test the convenience wrapper function."""
        mock_executor = MagicMock()
        mock_executor.workspace = str(tmp_path)
        mock_executor.run_type = "project_build"

        # Create a file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        result = resolve_scope_target(mock_executor, "test.txt", tmp_path, must_exist=True)
        assert result is not None

    def test_derive_allowed_paths_from_scope_wrapper(self, tmp_path):
        """Test the convenience wrapper function."""
        mock_executor = MagicMock()
        mock_executor.workspace = str(tmp_path)
        mock_executor.run_type = "autopack_maintenance"

        result = derive_allowed_paths_from_scope(mock_executor, None)
        assert result == []
