"""Tests for WorkspaceManager (P2.0 parallel runs)."""

import pytest
import shutil
import subprocess

from autopack.workspace_manager import WorkspaceManager


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary git repository for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repository
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True, capture_output=True)

    # Create initial commit
    test_file = repo_path / "test.txt"
    test_file.write_text("initial content")
    subprocess.run(["git", "add", "test.txt"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True, capture_output=True)

    yield repo_path

    # Cleanup
    if repo_path.exists():
        shutil.rmtree(repo_path, ignore_errors=True)


def test_workspace_manager_create_worktree(temp_repo, tmp_path):
    """Test creating an isolated worktree."""
    run_id = "test-run-001"
    worktree_base = tmp_path / "worktrees"

    manager = WorkspaceManager(
        run_id=run_id,
        source_repo=temp_repo,
        worktree_base=worktree_base,
        cleanup_on_exit=False
    )

    # Create worktree
    workspace = manager.create_worktree()

    assert workspace.exists()
    assert workspace.is_dir()
    assert (workspace / "test.txt").exists()
    assert (workspace / ".git").exists()

    # Verify it's a separate worktree
    result = subprocess.run(
        ["git", "worktree", "list"],
        cwd=temp_repo,
        capture_output=True,
        text=True
    )
    # Normalize paths for comparison (git uses forward slashes on Windows)
    workspace_normalized = str(workspace).replace("\\", "/")
    assert workspace_normalized in result.stdout

    # Cleanup
    manager.remove_worktree()


def test_workspace_manager_isolation(temp_repo, tmp_path):
    """Test that worktrees are isolated from each other."""
    worktree_base = tmp_path / "worktrees"

    # Create two worktrees
    manager1 = WorkspaceManager("run-001", temp_repo, worktree_base, cleanup_on_exit=False)
    manager2 = WorkspaceManager("run-002", temp_repo, worktree_base, cleanup_on_exit=False)

    workspace1 = manager1.create_worktree()
    workspace2 = manager2.create_worktree()

    # Modify file in workspace1
    test_file1 = workspace1 / "test.txt"
    test_file1.write_text("modified in workspace1")

    # Verify workspace2 is unaffected
    test_file2 = workspace2 / "test.txt"
    assert test_file2.read_text() == "initial content"

    # Cleanup
    manager1.remove_worktree()
    manager2.remove_worktree()


def test_workspace_manager_context_manager(temp_repo, tmp_path):
    """Test WorkspaceManager as context manager."""
    run_id = "test-run-context"
    worktree_base = tmp_path / "worktrees"

    manager = WorkspaceManager(
        run_id=run_id,
        source_repo=temp_repo,
        worktree_base=worktree_base,
        cleanup_on_exit=True
    )

    workspace_path = None

    with manager as workspace:
        workspace_path = workspace
        assert workspace.exists()
        assert (workspace / "test.txt").exists()

    # Verify cleanup happened
    assert not workspace_path.exists()


def test_workspace_manager_cleanup_all(temp_repo, tmp_path):
    """Test cleanup of all managed worktrees."""
    worktree_base = tmp_path / "worktrees"

    # Create multiple worktrees
    for i in range(3):
        manager = WorkspaceManager(
            f"run-{i:03d}",
            temp_repo,
            worktree_base,
            cleanup_on_exit=False
        )
        manager.create_worktree()

    # Verify all created
    assert len(list(worktree_base.iterdir())) == 3

    # Cleanup all
    count = WorkspaceManager.cleanup_all_worktrees(temp_repo, worktree_base)

    assert count == 3
    # Directory might still exist but should be empty
    if worktree_base.exists():
        assert len(list(worktree_base.iterdir())) == 0


def test_workspace_manager_list_worktrees(temp_repo, tmp_path):
    """Test listing existing worktrees."""
    worktree_base = tmp_path / "worktrees"

    # Create worktrees
    manager1 = WorkspaceManager("run-001", temp_repo, worktree_base, cleanup_on_exit=False)
    manager2 = WorkspaceManager("run-002", temp_repo, worktree_base, cleanup_on_exit=False)

    workspace1 = manager1.create_worktree()
    workspace2 = manager2.create_worktree()

    # List worktrees
    worktrees = WorkspaceManager.list_worktrees(temp_repo)

    # Should include main repo + 2 worktrees
    assert len(worktrees) >= 3

    # Verify our worktrees are in the list
    # Normalize paths for comparison (git uses forward slashes, Path uses backslashes on Windows)
    paths = [wt.get("path") for wt in worktrees]
    workspace1_normalized = str(workspace1).replace("\\", "/")
    workspace2_normalized = str(workspace2).replace("\\", "/")
    assert workspace1_normalized in paths
    assert workspace2_normalized in paths

    # Cleanup
    manager1.remove_worktree()
    manager2.remove_worktree()


def test_workspace_manager_handles_special_chars_in_run_id(temp_repo, tmp_path):
    """Test that special characters in run_id are sanitized."""
    worktree_base = tmp_path / "worktrees"

    # Run ID with special characters
    run_id = "test/run\\with spaces"

    manager = WorkspaceManager(
        run_id=run_id,
        source_repo=temp_repo,
        worktree_base=worktree_base,
        cleanup_on_exit=False
    )

    workspace = manager.create_worktree()

    # Should create valid filesystem path
    assert workspace.exists()
    # Verify sanitization happened (no slashes/backslashes in path component)
    assert "/" not in workspace.name
    assert "\\" not in workspace.name

    # Cleanup
    manager.remove_worktree()
