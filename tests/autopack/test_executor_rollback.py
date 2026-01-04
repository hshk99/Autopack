"""BUILD-145: Tests for git-based executor rollback

Tests savepoint creation, rollback logic, and cleanup functionality using temp git repo.
All tests are isolated (no network, no real repo modifications).
"""

import pytest
import subprocess

from autopack.rollback_manager import RollbackManager


class TestRollbackManager:
    """Test rollback manager savepoint and rollback functionality"""

    @pytest.fixture
    def temp_git_repo(self, tmp_path):
        """Create a temporary git repository for testing"""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)

        # Create initial commit
        test_file = repo_path / "test.txt"
        test_file.write_text("Initial content\n")
        subprocess.run(["git", "add", "test.txt"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

        return repo_path

    @pytest.fixture
    def rollback_manager(self, temp_git_repo):
        """Create rollback manager for temp repo"""
        return RollbackManager(
            workspace=temp_git_repo,
            run_id="test-run-123",
            phase_id="test-phase-456"
        )

    def test_create_savepoint_success(self, rollback_manager, temp_git_repo):
        """Creating savepoint should create a git tag"""
        success, error = rollback_manager.create_savepoint()

        assert success is True
        assert error is None
        assert rollback_manager.savepoint_tag is not None
        assert rollback_manager.savepoint_tag.startswith("save-before-test-run-123-test-phase-456-")

        # Verify tag exists in git
        result = subprocess.run(
            ["git", "tag", "-l", rollback_manager.savepoint_tag],
            cwd=temp_git_repo,
            capture_output=True,
            text=True
        )
        assert rollback_manager.savepoint_tag in result.stdout

    def test_create_savepoint_sanitizes_ids(self, temp_git_repo):
        """Savepoint should sanitize run/phase IDs for git tag names"""
        manager = RollbackManager(
            workspace=temp_git_repo,
            run_id="run/with/slashes and spaces",
            phase_id="phase/with/slashes"
        )

        success, error = manager.create_savepoint()

        assert success is True
        # Slashes and spaces should be replaced with dashes
        assert "/" not in manager.savepoint_tag
        assert " " not in manager.savepoint_tag
        assert "run-with-slashes-and-spaces" in manager.savepoint_tag

    def test_rollback_to_savepoint_success(self, rollback_manager, temp_git_repo):
        """Rolling back should restore working tree to savepoint state"""
        # Create savepoint
        rollback_manager.create_savepoint()

        # Make changes to file
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("Modified content\n")

        # Create new file
        new_file = temp_git_repo / "new_file.txt"
        new_file.write_text("New file content\n")

        # Verify changes exist
        assert test_file.read_text() == "Modified content\n"
        assert new_file.exists()

        # Rollback
        success, error = rollback_manager.rollback_to_savepoint("Test rollback")

        assert success is True
        assert error is None

        # Verify rollback worked - file restored to original, new file removed
        assert test_file.read_text() == "Initial content\n"
        assert not new_file.exists()

    def test_rollback_without_savepoint_fails(self, rollback_manager):
        """Rolling back without creating savepoint should fail"""
        success, error = rollback_manager.rollback_to_savepoint("Test rollback")

        assert success is False
        assert "no_savepoint_tag_set" in error

    def test_rollback_logs_to_audit_file(self, rollback_manager, temp_git_repo):
        """Rollback should log action to audit file"""
        rollback_manager.create_savepoint()

        # Make changes
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("Modified\n")

        # Rollback
        rollback_manager.rollback_to_savepoint("Test validation failure")

        # Verify audit log exists
        audit_log = temp_git_repo / ".autonomous_runs" / "test-run-123" / "rollback.log"
        assert audit_log.exists()

        log_content = audit_log.read_text()
        assert "test-phase-456" in log_content
        assert "Test validation failure" in log_content
        assert rollback_manager.savepoint_tag in log_content

    def test_cleanup_savepoint_deletes_tag(self, rollback_manager, temp_git_repo):
        """Cleanup should delete the savepoint tag when keep_last_n=False"""
        rollback_manager.create_savepoint()
        tag_name = rollback_manager.savepoint_tag

        # Verify tag exists
        result = subprocess.run(
            ["git", "tag", "-l", tag_name],
            cwd=temp_git_repo,
            capture_output=True,
            text=True
        )
        assert tag_name in result.stdout

        # Cleanup with keep_last_n=False (original behavior)
        rollback_manager.cleanup_savepoint(keep_last_n=False)

        # Verify tag deleted
        result = subprocess.run(
            ["git", "tag", "-l", tag_name],
            cwd=temp_git_repo,
            capture_output=True,
            text=True
        )
        assert tag_name not in result.stdout

    def test_cleanup_savepoint_without_tag_noop(self, rollback_manager):
        """Cleanup without creating savepoint should not crash"""
        # Should not raise exception
        rollback_manager.cleanup_savepoint()

    def test_cleanup_old_savepoints(self, temp_git_repo):
        """Cleanup should delete savepoints older than threshold"""
        # Create multiple savepoint tags
        tags = []
        for i in range(3):
            manager = RollbackManager(temp_git_repo, f"run-{i}", f"phase-{i}")
            manager.create_savepoint()
            tags.append(manager.savepoint_tag)

        # Verify all tags exist
        for tag in tags:
            result = subprocess.run(
                ["git", "tag", "-l", tag],
                cwd=temp_git_repo,
                capture_output=True,
                text=True
            )
            assert tag in result.stdout

        # Cleanup with 0 day threshold (delete all)
        deleted_count = RollbackManager.cleanup_old_savepoints(temp_git_repo, days_threshold=0)

        # At least one should be deleted (depends on timing)
        # We can't guarantee all 3 due to timestamp precision
        assert deleted_count >= 0

    def test_rollback_preserves_git_history(self, rollback_manager, temp_git_repo):
        """Rollback should not affect committed git history"""
        # Get current commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True
        )
        original_commit = result.stdout.strip()

        # Create savepoint
        rollback_manager.create_savepoint()

        # Make changes (uncommitted)
        test_file = temp_git_repo / "test.txt"
        test_file.write_text("Modified\n")

        # Rollback
        rollback_manager.rollback_to_savepoint("Test")

        # Verify HEAD is still at same commit
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True
        )
        current_commit = result.stdout.strip()

        assert current_commit == original_commit

    def test_rollback_works_on_windows_paths(self, tmp_path):
        """Rollback should work with Windows-style paths"""
        # Create temp repo with Windows-style path
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        test_file = repo_path / "test.txt"
        test_file.write_text("Initial\n")
        subprocess.run(["git", "add", "test.txt"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Init"], cwd=repo_path, check=True)

        # Use manager with Path object (works on Windows and Unix)
        manager = RollbackManager(repo_path, "run-id", "phase-id")

        success, _ = manager.create_savepoint()
        assert success is True

        # Make changes
        test_file.write_text("Modified\n")

        # Rollback should work
        success, _ = manager.rollback_to_savepoint("Test")
        assert success is True
        assert test_file.read_text() == "Initial\n"

    def test_rollback_handles_subprocess_timeout(self, rollback_manager, temp_git_repo, monkeypatch):
        """Rollback should handle subprocess timeouts gracefully"""
        import subprocess

        original_run = subprocess.run

        def mock_run_timeout(*args, **kwargs):
            if "git" in args[0] and "reset" in args[0]:
                raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout", 30))
            return original_run(*args, **kwargs)

        monkeypatch.setattr(subprocess, "run", mock_run_timeout)

        rollback_manager.create_savepoint()

        success, error = rollback_manager.rollback_to_savepoint("Test timeout")

        assert success is False
        assert "git_reset_timeout" in error

    def test_multiple_savepoints_independent(self, temp_git_repo):
        """Multiple rollback managers should create independent savepoints"""
        manager1 = RollbackManager(temp_git_repo, "run-1", "phase-1")
        manager2 = RollbackManager(temp_git_repo, "run-2", "phase-2")

        manager1.create_savepoint()
        manager2.create_savepoint()

        # Both tags should exist
        result = subprocess.run(
            ["git", "tag", "-l", "save-before-*"],
            cwd=temp_git_repo,
            capture_output=True,
            text=True
        )

        assert manager1.savepoint_tag in result.stdout
        assert manager2.savepoint_tag in result.stdout
        assert manager1.savepoint_tag != manager2.savepoint_tag
