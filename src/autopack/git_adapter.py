"""
Git Adapter Abstraction Layer

Per v7 architect recommendation: Abstraction layer for git operations
to enable future migration from local git CLI to external git service.

This enables governed apply path while keeping implementation flexible.
"""

from typing import Protocol, Dict, Optional
import subprocess
from pathlib import Path


class GitAdapter(Protocol):
    """
    Protocol defining git operations interface.

    Implementations:
    - LocalGitCliAdapter: Uses subprocess to call git CLI (current)
    - ExternalGitServiceAdapter: Future cloud-native implementation
    """

    def ensure_integration_branch(self, repo_path: str, run_id: str) -> str:
        """
        Ensure integration branch exists for the run.

        Args:
            repo_path: Path to git repository
            run_id: Run identifier

        Returns:
            Branch name (autonomous/{run_id})
        """
        ...

    def apply_patch(
        self, repo_path: str, run_id: str, phase_id: str, patch_content: str
    ) -> tuple[bool, Optional[str]]:
        """
        Apply patch to integration branch.

        Args:
            repo_path: Path to git repository
            run_id: Run identifier
            phase_id: Phase identifier for commit tagging
            patch_content: Git diff patch

        Returns:
            (success, commit_sha)
        """
        ...

    def get_integration_status(self, repo_path: str, run_id: str) -> Dict:
        """
        Get status of integration branch.

        Args:
            repo_path: Path to git repository
            run_id: Run identifier

        Returns:
            Status dict with branch info, commits, etc.
        """
        ...


class LocalGitCliAdapter:
    """
    Local git CLI implementation using subprocess.

    Per v7 architect recommendation:
    - Uses git CLI in mounted working tree with .git
    - Suitable for single-user, local Docker deployments
    - Foundation for future ExternalGitServiceAdapter
    """

    def __init__(self, default_repo_path: Optional[str] = None):
        """
        Initialize adapter.

        Args:
            default_repo_path: Default repository path (can be overridden per call)
        """
        self.default_repo_path = default_repo_path or "/workspace"

    def _run_git(
        self, args: list[str], cwd: str, check: bool = True, capture_output: bool = True
    ) -> subprocess.CompletedProcess:
        """
        Run git command.

        Args:
            args: Git command arguments (e.g., ['status', '--porcelain'])
            cwd: Working directory
            check: Raise exception on error
            capture_output: Capture stdout/stderr

        Returns:
            CompletedProcess result
        """
        cmd = ["git"] + args
        return subprocess.run(cmd, cwd=cwd, check=check, capture_output=capture_output, text=True)

    def ensure_integration_branch(self, repo_path: str, run_id: str) -> str:
        """
        Ensure integration branch exists.

        Creates branch `autonomous/{run_id}` if it doesn't exist.
        Switches to it if it does.
        """
        branch_name = f"autonomous/{run_id}"

        # Check if branch exists
        result = self._run_git(["rev-parse", "--verify", branch_name], cwd=repo_path, check=False)

        if result.returncode == 0:
            # Branch exists, switch to it
            self._run_git(["switch", branch_name], cwd=repo_path)
        else:
            # Create new branch
            self._run_git(["switch", "-c", branch_name], cwd=repo_path)

        return branch_name

    def apply_patch(
        self, repo_path: str, run_id: str, phase_id: str, patch_content: str
    ) -> tuple[bool, Optional[str]]:
        """
        Apply patch to integration branch.

        Per v7 playbook (§8):
        - Apply to autonomous/{run_id} branch only
        - Tag commit with phase_id
        - Never write to main
        """
        try:
            # Ensure we're on the right branch
            self.ensure_integration_branch(repo_path, run_id)

            # Write patch to temp file
            patch_file = Path(repo_path) / ".autopack_patch.tmp"
            patch_file.write_text(patch_content)

            try:
                # Apply patch
                self._run_git(["apply", "--verbose", str(patch_file)], cwd=repo_path)

                # Stage changes
                self._run_git(["add", "-A"], cwd=repo_path)

                # Commit with phase tag
                commit_msg = f"[Autopack] Phase {phase_id} for run {run_id}\n\nAutonomous build phase completion."
                self._run_git(["commit", "-m", commit_msg], cwd=repo_path)

                # Get commit SHA
                result = self._run_git(["rev-parse", "HEAD"], cwd=repo_path)
                commit_sha = result.stdout.strip()

                # Tag commit
                tag_name = f"{run_id}_{phase_id}"
                self._run_git(
                    ["tag", "-f", tag_name], cwd=repo_path, check=False  # Don't fail if tag exists
                )

                return (True, commit_sha)

            finally:
                # Clean up temp file
                if patch_file.exists():
                    patch_file.unlink()

        except subprocess.CalledProcessError as e:
            print(f"Git operation failed: {e}")
            print(f"stdout: {e.stdout}")
            print(f"stderr: {e.stderr}")
            return (False, None)

    def get_integration_status(self, repo_path: str, run_id: str) -> Dict:
        """
        Get integration branch status.

        Returns branch info, commit count, etc.
        """
        branch_name = f"autonomous/{run_id}"

        try:
            # Check if branch exists
            result = self._run_git(
                ["rev-parse", "--verify", branch_name], cwd=repo_path, check=False
            )

            if result.returncode != 0:
                return {
                    "branch": branch_name,
                    "exists": False,
                    "message": "Integration branch not yet created",
                }

            # Get commit count
            result = self._run_git(["rev-list", "--count", branch_name], cwd=repo_path)
            commit_count = int(result.stdout.strip())

            # Get latest commit
            result = self._run_git(["log", "-1", "--format=%H %s", branch_name], cwd=repo_path)
            latest_commit = result.stdout.strip()

            # Get branch status (ahead/behind)
            result = self._run_git(
                ["rev-list", "--left-right", "--count", f"main...{branch_name}"],
                cwd=repo_path,
                check=False,
            )

            if result.returncode == 0:
                behind, ahead = result.stdout.strip().split()
                behind_count = int(behind)
                ahead_count = int(ahead)
            else:
                behind_count = 0
                ahead_count = commit_count

            return {
                "branch": branch_name,
                "exists": True,
                "commit_count": commit_count,
                "latest_commit": latest_commit,
                "ahead_of_main": ahead_count,
                "behind_main": behind_count,
            }

        except subprocess.CalledProcessError as e:
            return {"branch": branch_name, "exists": False, "error": str(e)}


# Factory function to get adapter instance
def get_git_adapter(repo_path: Optional[str] = None) -> GitAdapter:
    """
    Get git adapter instance.

    Currently returns LocalGitCliAdapter.
    Future: Can return ExternalGitServiceAdapter based on config.

    Args:
        repo_path: Repository path (optional)

    Returns:
        GitAdapter instance
    """
    return LocalGitCliAdapter(default_repo_path=repo_path)
