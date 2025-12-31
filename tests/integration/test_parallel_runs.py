"""Integration tests for parallel runs capability (P2.0-P2.4).

Tests the full parallel runs workflow including:
- WorkspaceManager (git worktree isolation)
- WorkspaceLease (concurrent access prevention)
- TestBaselineTracker (run-scoped artifacts)
- ExecutorLockManager (per-run locking)
- Supervisor orchestration
"""

import pytest
from pathlib import Path
import subprocess
import tempfile
import shutil
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autopack.workspace_manager import WorkspaceManager
from autopack.workspace_lease import WorkspaceLease
from autopack.test_baseline_tracker import TestBaselineTracker
from autopack.executor_lock import ExecutorLockManager


@pytest.fixture
def git_repo(tmp_path):
    """Create a test git repository."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Initialize git
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)

    # Create initial content
    (repo / "README.md").write_text("# Test Repo")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo, check=True, capture_output=True)

    yield repo

    # Cleanup
    if repo.exists():
        shutil.rmtree(repo, ignore_errors=True)


def test_workspace_isolation_for_parallel_runs(git_repo, tmp_path):
    """Test that multiple runs can execute in parallel without interfering."""
    worktree_base = tmp_path / "worktrees"

    # Create two isolated workspaces
    manager1 = WorkspaceManager("run-001", git_repo, worktree_base, cleanup_on_exit=False)
    manager2 = WorkspaceManager("run-002", git_repo, worktree_base, cleanup_on_exit=False)

    workspace1 = manager1.create_worktree()
    workspace2 = manager2.create_worktree()

    # Both workspaces exist
    assert workspace1.exists()
    assert workspace2.exists()
    assert workspace1 != workspace2

    # Modify files independently
    (workspace1 / "file1.txt").write_text("workspace1 content")
    (workspace2 / "file2.txt").write_text("workspace2 content")

    # Verify isolation
    assert (workspace1 / "file1.txt").exists()
    assert not (workspace1 / "file2.txt").exists()
    assert (workspace2 / "file2.txt").exists()
    assert not (workspace2 / "file1.txt").exists()

    # Cleanup
    manager1.remove_worktree()
    manager2.remove_worktree()


def test_per_run_locking_prevents_duplicate_execution(git_repo, tmp_path):
    """Test that ExecutorLockManager prevents duplicate run execution."""
    lock_dir = tmp_path / "locks"

    # Acquire lock for run-001
    lock1 = ExecutorLockManager("run-001", lock_dir=lock_dir)
    assert lock1.acquire() is True

    # Try to acquire same run (should fail)
    lock2 = ExecutorLockManager("run-001", lock_dir=lock_dir)
    assert lock2.acquire() is False

    # Different run should succeed
    lock3 = ExecutorLockManager("run-002", lock_dir=lock_dir)
    assert lock3.acquire() is True

    # Cleanup
    lock1.release()
    lock3.release()


def test_workspace_lease_prevents_concurrent_workspace_access(git_repo, tmp_path):
    """Test that WorkspaceLease prevents concurrent access to same workspace."""
    worktree_base = tmp_path / "worktrees"
    lease_dir = tmp_path / "leases"

    # Create workspace
    manager = WorkspaceManager("run-001", git_repo, worktree_base, cleanup_on_exit=False)
    workspace = manager.create_worktree()

    # Acquire lease
    lease1 = WorkspaceLease(workspace, lease_dir=lease_dir)
    assert lease1.acquire() is True

    # Second lease for same workspace should fail
    lease2 = WorkspaceLease(workspace, lease_dir=lease_dir)
    assert lease2.acquire() is False

    # After release, second can acquire
    lease1.release()
    assert lease2.acquire() is True

    # Cleanup
    lease2.release()
    manager.remove_worktree()


def test_test_baseline_tracker_run_scoped_artifacts(git_repo, tmp_path):
    """Test that TestBaselineTracker uses run-scoped paths."""
    import os

    # Without run_id (legacy mode - global paths)
    tracker_legacy = TestBaselineTracker(git_repo)
    # Normalize path separators for cross-platform compatibility
    cache_dir_str = str(tracker_legacy.cache_dir).replace(os.sep, "/")
    assert ".autonomous_runs/baselines" in cache_dir_str
    # Legacy mode should NOT have run_id in path (should end with /baselines, not /run-id/baselines)
    assert cache_dir_str.endswith("/.autonomous_runs/baselines")

    # With run_id (parallel-safe mode - run-scoped paths)
    tracker_scoped = TestBaselineTracker(git_repo, run_id="run-001")
    cache_dir_scoped_str = str(tracker_scoped.cache_dir).replace(os.sep, "/")
    assert ".autonomous_runs/run-001/baselines" in cache_dir_scoped_str

    # Different runs have different cache dirs
    tracker_scoped2 = TestBaselineTracker(git_repo, run_id="run-002")
    assert tracker_scoped.cache_dir != tracker_scoped2.cache_dir


def test_complete_parallel_run_workflow(git_repo, tmp_path):
    """Test complete workflow: workspace + lease + lock."""
    worktree_base = tmp_path / "worktrees"
    lease_dir = tmp_path / "leases"
    lock_dir = tmp_path / "locks"

    run_id = "integration-test-001"

    # Step 1: Create isolated workspace
    workspace_manager = WorkspaceManager(
        run_id=run_id,
        source_repo=git_repo,
        worktree_base=worktree_base,
        cleanup_on_exit=False
    )
    workspace = workspace_manager.create_worktree()

    # Step 2: Acquire workspace lease
    workspace_lease = WorkspaceLease(workspace, lease_dir=lease_dir)
    assert workspace_lease.acquire() is True

    # Step 3: Acquire run lock
    executor_lock = ExecutorLockManager(run_id, lock_dir=lock_dir)
    assert executor_lock.acquire() is True

    # Step 4: Simulate run execution
    (workspace / "output.txt").write_text("Run completed successfully")

    # Step 5: Release locks
    executor_lock.release()
    workspace_lease.release()

    # Step 6: Cleanup workspace
    workspace_manager.remove_worktree()

    # Verify cleanup
    assert not workspace.exists()
    assert not executor_lock.is_locked()
    assert not workspace_lease.is_locked()


def test_parallel_runs_dont_collide_on_artifacts(git_repo, tmp_path):
    """Test that parallel runs don't overwrite each other's artifacts."""
    # Create two trackers for different runs
    tracker1 = TestBaselineTracker(git_repo, run_id="run-001")
    tracker2 = TestBaselineTracker(git_repo, run_id="run-002")

    # Verify different cache directories
    assert tracker1.cache_dir != tracker2.cache_dir

    # Both can create caches without collision
    tracker1.cache_dir.mkdir(parents=True, exist_ok=True)
    tracker2.cache_dir.mkdir(parents=True, exist_ok=True)

    (tracker1.cache_dir / "test.txt").write_text("run-001")
    (tracker2.cache_dir / "test.txt").write_text("run-002")

    # Verify isolation
    assert (tracker1.cache_dir / "test.txt").read_text() == "run-001"
    assert (tracker2.cache_dir / "test.txt").read_text() == "run-002"
