"""Governed apply path for patches (Chunk D)

Per §3 of v7 playbook:
- All code changes go to integration branch only
- Never write to main/protected branches
- Track all patches with metadata

Updated per v7 architect recommendation:
- Uses GitAdapter abstraction layer
- Enables future migration to external git service
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import settings
from .git_adapter import get_git_adapter, GitAdapter


class GovernedApplyPath:
    """Manages the governed apply path for patches"""

    def __init__(self, run_id: str, repo_path: Optional[str] = None):
        self.run_id = run_id
        self.integration_branch = f"autonomous/{run_id}"
        self.repo_path = repo_path or settings.repo_path
        self.git_adapter: GitAdapter = get_git_adapter(self.repo_path)

    def ensure_integration_branch(self, base_branch: str = "main") -> bool:
        """
        Ensure integration branch exists for this run.

        Per §3: integration branches are created per run,
        main is never touched by autonomous agents.

        Now uses GitAdapter abstraction.
        """
        try:
            self.git_adapter.ensure_integration_branch(self.repo_path, self.run_id)
            return True
        except Exception as e:
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

        Now uses GitAdapter abstraction.
        """
        try:
            # Use GitAdapter to apply patch
            success, commit_sha = self.git_adapter.apply_patch(
                repo_path=self.repo_path,
                run_id=self.run_id,
                phase_id=phase_id,
                patch_content=patch_content
            )

            return success, commit_sha or ""

        except Exception as e:
            print(f"Error applying patch: {e}")
            return False, ""

    def get_integration_branch_status(self) -> dict:
        """
        Get status of integration branch.

        Now uses GitAdapter abstraction.
        """
        try:
            return self.git_adapter.get_integration_status(self.repo_path, self.run_id)
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
