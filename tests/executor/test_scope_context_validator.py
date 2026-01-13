"""Contract tests for ScopeContextValidator (PR-EXE-13).

Validates that the scope context validator correctly validates file context
against scope configuration, handling directory scopes, path normalization,
and read-only context.
"""

from unittest.mock import Mock
import pytest

from autopack.executor.scope_context_validator import ScopeContextValidator


class TestScopeContextValidator:
    """Test suite for ScopeContextValidator contract."""

    @pytest.fixture
    def mock_executor(self, tmp_path):
        """Create a mock executor with workspace."""
        executor = Mock()
        executor.workspace = tmp_path

        # Mock _determine_workspace_root to return tmp_path
        executor._determine_workspace_root = Mock(return_value=tmp_path)

        # Mock _resolve_scope_target to simulate path resolution
        def resolve_scope_target(path_str, workspace_root, must_exist=False):
            # Normalize path
            normalized = path_str.replace("\\", "/")
            abs_path = workspace_root / normalized
            return (abs_path, normalized)

        executor._resolve_scope_target = Mock(side_effect=resolve_scope_target)

        return executor

    @pytest.fixture
    def validator(self, mock_executor):
        """Create validator instance."""
        return ScopeContextValidator(mock_executor)

    def test_validation_passes_with_matching_files(self, validator, mock_executor, tmp_path):
        """Test validation passes when loaded files match scope."""
        phase = {"phase_id": "test-phase"}
        file_context = {
            "existing_files": {
                "src/main.py": "content",
                "src/utils.py": "content",
            }
        }
        scope_config = {
            "paths": ["src/main.py", "src/utils.py"]
        }

        # Should not raise
        validator.validate(phase, file_context, scope_config)

    def test_validation_fails_with_files_outside_scope(self, validator, mock_executor, tmp_path, caplog):
        """Test validation fails when files are outside scope."""
        phase = {"phase_id": "test-phase"}
        file_context = {
            "existing_files": {
                "src/main.py": "content",
                "tests/test_main.py": "content",  # Outside scope
            }
        }
        scope_config = {
            "paths": ["src/main.py"]
        }

        with pytest.raises(RuntimeError, match="Scope validation failed"):
            validator.validate(phase, file_context, scope_config)

    def test_readonly_context_allows_outside_files(self, validator, mock_executor, tmp_path):
        """Test read-only context allows files outside main scope."""
        phase = {"phase_id": "test-phase"}
        file_context = {
            "existing_files": {
                "src/main.py": "content",
                "tests/test_main.py": "content",  # Outside scope but in read_only
            }
        }
        scope_config = {
            "paths": ["src/main.py"],
            "read_only_context": ["tests/test_main.py"]
        }

        # Should not raise
        validator.validate(phase, file_context, scope_config)

    def test_directory_scope_includes_children(self, validator, mock_executor, tmp_path):
        """Test directory scope includes all child files."""
        phase = {"phase_id": "test-phase"}
        file_context = {
            "existing_files": {
                "src/main.py": "content",
                "src/utils.py": "content",
                "src/models/user.py": "content",
            }
        }
        scope_config = {
            "paths": ["src/"]  # Directory scope
        }

        # Mock _resolve_scope_target to return directory
        def resolve_with_dir(path_str, workspace_root, must_exist=False):
            normalized = path_str.replace("\\", "/")
            abs_path = workspace_root / normalized.rstrip("/")
            # Create directory for testing
            abs_path.mkdir(parents=True, exist_ok=True)
            return (abs_path, normalized)

        mock_executor._resolve_scope_target = Mock(side_effect=resolve_with_dir)

        # Should not raise - all files under src/
        validator.validate(phase, file_context, scope_config)

    def test_path_normalization_windows_style(self, validator, mock_executor, tmp_path):
        """Test path normalization handles Windows-style paths."""
        phase = {"phase_id": "test-phase"}
        file_context = {
            "existing_files": {
                "src/main.py": "content",
            }
        }
        scope_config = {
            "paths": ["src\\main.py"]  # Windows-style path
        }

        # Should normalize and pass
        validator.validate(phase, file_context, scope_config)

    def test_readonly_context_dict_format(self, validator, mock_executor, tmp_path):
        """Test read-only context supports dict format (BUILD-145)."""
        phase = {"phase_id": "test-phase"}
        file_context = {
            "existing_files": {
                "src/main.py": "content",
                "README.md": "content",
            }
        }
        scope_config = {
            "paths": ["src/main.py"],
            "read_only_context": [
                {"path": "README.md"}  # Dict format
            ]
        }

        # Should not raise
        validator.validate(phase, file_context, scope_config)

    def test_readonly_context_directory_prefix(self, validator, mock_executor, tmp_path):
        """Test read-only context with directory prefix."""
        phase = {"phase_id": "test-phase"}
        file_context = {
            "existing_files": {
                "src/main.py": "content",
                "docs/README.md": "content",
                "docs/api.md": "content",
            }
        }
        scope_config = {
            "paths": ["src/main.py"],
            "read_only_context": ["docs/"]  # Directory prefix
        }

        # Mock _resolve_scope_target to handle directory resolution
        def resolve_with_suffix(path_str, workspace_root, must_exist=False):
            normalized = path_str.replace("\\", "/")
            abs_path = workspace_root / normalized.rstrip("/")
            return (abs_path, normalized)

        mock_executor._resolve_scope_target = Mock(side_effect=resolve_with_suffix)

        # Should not raise - docs/ prefix allows all docs files
        validator.validate(phase, file_context, scope_config)

    def test_empty_file_context_passes(self, validator, mock_executor, tmp_path):
        """Test validation passes with empty file context."""
        phase = {"phase_id": "test-phase"}
        file_context = {
            "existing_files": {}
        }
        scope_config = {
            "paths": ["src/main.py"]
        }

        # Should not raise - no files to validate
        validator.validate(phase, file_context, scope_config)
