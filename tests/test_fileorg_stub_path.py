"""Unit test for fileorg deliverables stub path fix.

BUILD-146: Ensure stubs for missing files land in correct workspace root,
not duplicated paths like fileorganizer/fileorganizer/package-lock.json.
"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from autopack.autonomous_executor import AutonomousExecutor


@pytest.fixture
def mock_executor(tmp_path):
    """Create a mock AutonomousExecutor with temporary workspace."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create mock dependencies
    mock_builder_client = Mock()
    mock_auditor_client = Mock()
    mock_db = Mock()
    mock_memory = Mock()
    mock_quality_gate = Mock()

    executor = AutonomousExecutor(
        builder_client=mock_builder_client,
        auditor_client=mock_auditor_client,
        db=mock_db,
        memory_service=mock_memory,
        quality_gate=mock_quality_gate,
        workspace=str(workspace),
        run_id="test-run"
    )

    return executor, workspace


def test_load_scoped_context_missing_file_stub_path(mock_executor):
    """Test that missing files get proper relative paths without duplication."""
    executor, workspace = mock_executor

    # Create a fileorganizer subdirectory as workspace_root
    fileorg_dir = workspace / "fileorganizer"
    fileorg_dir.mkdir()

    # Simulate a phase with scope pointing to fileorganizer workspace
    phase = {"phase_id": "test-phase"}
    scope_config = {
        "workspace_root": "fileorganizer",
        "paths": ["package-lock.json"]  # Missing file
    }

    # Call _load_scoped_context
    result = executor._load_scoped_context(phase, scope_config)

    # Verify missing files list contains correct relative path
    missing_files = result.get("missing_scope_files", [])
    assert len(missing_files) > 0

    # The key should be "fileorganizer/package-lock.json", NOT "fileorganizer/fileorganizer/package-lock.json"
    for missing in missing_files:
        assert "fileorganizer/fileorganizer" not in missing, \
            f"Duplicate path detected: {missing}"
        assert missing.startswith("fileorganizer/") or missing == "package-lock.json", \
            f"Unexpected path format: {missing}"


def test_load_scoped_context_stub_creation_path(mock_executor, tmp_path):
    """Test that stub creation uses correct base_workspace path."""
    executor, workspace = mock_executor

    # Create a fileorganizer subdirectory
    fileorg_dir = workspace / "fileorganizer"
    fileorg_dir.mkdir()

    phase = {"phase_id": "test-phase"}
    scope_config = {
        "workspace_root": "fileorganizer",
        "paths": ["package-lock.json"]
    }

    # Call _load_scoped_context (this should create stub for package-lock.json)
    result = executor._load_scoped_context(phase, scope_config)

    # Verify the stub was created at the correct location
    expected_stub_path = workspace / "fileorganizer" / "package-lock.json"
    wrong_stub_path = workspace / "fileorganizer" / "fileorganizer" / "package-lock.json"

    # The stub should exist at the correct path
    if expected_stub_path.exists():
        assert expected_stub_path.exists(), "Stub should be created at correct path"
        assert not wrong_stub_path.exists(), "Stub should NOT be created at duplicate path"

    # Verify existing_files has correct key
    existing_files = result.get("existing_files", {})
    for key in existing_files.keys():
        assert "fileorganizer/fileorganizer" not in key, \
            f"Duplicate path in existing_files: {key}"


def test_resolve_scope_target_relative_path(mock_executor):
    """Test _resolve_scope_target with relative paths in subdirectory workspace."""
    executor, workspace = mock_executor

    # Create fileorganizer subdirectory
    fileorg_dir = workspace / "fileorganizer"
    fileorg_dir.mkdir()

    # Create a test file
    test_file = fileorg_dir / "test.json"
    test_file.write_text("{}", encoding="utf-8")

    # Resolve using fileorganizer as workspace_root
    workspace_root = fileorg_dir
    result = executor._resolve_scope_target("test.json", workspace_root, must_exist=True)

    assert result is not None, "Should resolve existing file"
    abs_path, rel_key = result

    # rel_key should be "fileorganizer/test.json", not "fileorganizer/fileorganizer/test.json"
    assert rel_key == "fileorganizer/test.json", f"Unexpected rel_key: {rel_key}"
    assert "fileorganizer/fileorganizer" not in rel_key, f"Duplicate path in rel_key: {rel_key}"
