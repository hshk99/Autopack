"""Governed apply path for patches (Chunk D)

Per §3 of v7 playbook:
- All code changes go to integration branch only
- Never write to main/protected branches
- Track all patches with metadata
"""

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import settings


class GovernedApplyPath:
    """Manages the governed apply path for patches"""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.integration_branch = f"autonomous/{run_id}"

    def ensure_integration_branch(self, base_branch: str = "main") -> bool:
        """
        Ensure integration branch exists for this run.

        Per §3: integration branches are created per run,
        main is never touched by autonomous agents.
        """
        try:
            # Check if branch exists
            result = subprocess.run(
                ["git", "rev-parse", "--verify", self.integration_branch],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                # Branch exists, check it out
                subprocess.run(
                    ["git", "checkout", self.integration_branch],
                    check=True,
                    capture_output=True,
                )
                return True
            else:
                # Create new branch from base
                subprocess.run(
                    ["git", "checkout", "-b", self.integration_branch, base_branch],
                    check=True,
                    capture_output=True,
                )
                return True

        except subprocess.CalledProcessError as e:
            print(f"Error managing integration branch: {e}")
            return False

    def apply_patch(
        self,
        patch_content: str,
        phase_id: str,
        commit_message: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Apply a patch to the integration branch.

        Returns: (success: bool, commit_sha: str)
        """
        # Ensure we're on integration branch
        if not self.ensure_integration_branch():
            return False, ""

        # Write patch to temp file
        patch_path = Path(settings.autonomous_runs_dir) / self.run_id / f"patch_{phase_id}.diff"
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(patch_content)

        try:
            # Apply patch
            subprocess.run(
                ["git", "apply", str(patch_path)],
                check=True,
                capture_output=True,
            )

            # Stage changes
            subprocess.run(
                ["git", "add", "-A"],
                check=True,
                capture_output=True,
            )

            # Commit
            if not commit_message:
                commit_message = f"[Autonomous] Phase {phase_id} - {self.run_id}"

            subprocess.run(
                ["git", "commit", "-m", commit_message],
                check=True,
                capture_output=True,
            )

            # Get commit SHA
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            commit_sha = result.stdout.strip()

            return True, commit_sha

        except subprocess.CalledProcessError as e:
            print(f"Error applying patch: {e}")
            return False, ""

    def get_integration_branch_status(self) -> dict:
        """Get status of integration branch"""
        try:
            # Get commit count ahead of main
            result = subprocess.run(
                ["git", "rev-list", "--count", f"main..{self.integration_branch}"],
                capture_output=True,
                text=True,
            )
            commits_ahead = int(result.stdout.strip()) if result.returncode == 0 else 0

            # Get current commit
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
            )
            current_commit = result.stdout.strip() if result.returncode == 0 else ""

            return {
                "branch": self.integration_branch,
                "commits_ahead_of_main": commits_ahead,
                "current_commit": current_commit,
            }
        except Exception as e:
            return {"error": str(e)}

    def create_snapshot_tag(self, phase_id: str, tier_id: str) -> Optional[str]:
        """
        Create a snapshot tag after successful phase completion.

        Per §3: snapshots are created after green CI and acceptable tier policy.
        """
        tag_name = f"autonomous/{self.run_id}/tier-{tier_id}/phase-{phase_id}"

        try:
            subprocess.run(
                ["git", "tag", "-a", tag_name, "-m", f"Snapshot after phase {phase_id}"],
                check=True,
                capture_output=True,
            )
            return tag_name
        except subprocess.CalledProcessError:
            return None
