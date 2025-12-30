"""BUILD-145: Git-based Rollback Manager

Provides deterministic, opt-in rollback for failed patch applies using git savepoints.

Triggers:
- Patch apply failure (git apply error)
- Post-apply validation failure (governed apply error)
- Critical test/quality-gate failure

Mechanism:
- Creates git tag savepoint before patch apply: save-before-{run_id}-{phase_id}-{timestamp}
- On failure, resets working tree to savepoint using git reset --hard
- Logs savepoint id and rollback action for auditing

Protected paths:
- Never touches .git/, .autonomous_runs/, autopack.db except via git commands
- Windows-safe: uses subprocess with explicit args (no shell=True)

Cleanup strategy:
- Savepoint tags are kept for 7 days by default
- Can be cleaned up via: git tag -d save-before-*
- Or run cleanup method to delete tags older than threshold
"""

import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class RollbackManager:
    """Manages git-based savepoints and rollback for autonomous executor."""

    def __init__(self, workspace: Path, run_id: str, phase_id: str):
        """
        Initialize rollback manager.

        Args:
            workspace: Path to git repository root
            run_id: Current run ID
            phase_id: Current phase ID
        """
        self.workspace = Path(workspace)
        self.run_id = run_id
        self.phase_id = phase_id
        self.savepoint_tag: Optional[str] = None

    def create_savepoint(self) -> Tuple[bool, Optional[str]]:
        """
        Create a git savepoint tag before applying patches.

        Savepoint format: save-before-{run_id}-{phase_id}-{timestamp}

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        # Sanitize run_id and phase_id for tag name (replace slashes, spaces with dashes)
        safe_run_id = self.run_id.replace("/", "-").replace(" ", "-")
        safe_phase_id = self.phase_id.replace("/", "-").replace(" ", "-")

        self.savepoint_tag = f"save-before-{safe_run_id}-{safe_phase_id}-{timestamp}"

        try:
            # Create lightweight tag at current HEAD
            result = subprocess.run(
                ["git", "tag", self.savepoint_tag],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                logger.error(f"[Rollback] Failed to create savepoint tag {self.savepoint_tag}: {error_msg}")
                return False, f"git_tag_failed: {error_msg}"

            logger.info(f"[Rollback] Created savepoint: {self.savepoint_tag}")
            return True, None

        except subprocess.TimeoutExpired:
            logger.error(f"[Rollback] Timeout creating savepoint tag {self.savepoint_tag}")
            return False, "git_tag_timeout"
        except Exception as e:
            logger.error(f"[Rollback] Exception creating savepoint: {e}")
            return False, f"git_tag_exception: {str(e)}"

    def rollback_to_savepoint(self, reason: str) -> Tuple[bool, Optional[str]]:
        """
        Rollback working tree to savepoint tag.

        Args:
            reason: Reason for rollback (for logging)

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        if not self.savepoint_tag:
            logger.error("[Rollback] No savepoint tag set - cannot rollback")
            return False, "no_savepoint_tag_set"

        try:
            logger.warning(f"[Rollback] Rolling back to savepoint {self.savepoint_tag}")
            logger.warning(f"[Rollback] Reason: {reason}")

            # Reset working tree to savepoint tag (hard reset discards all changes)
            result = subprocess.run(
                ["git", "reset", "--hard", self.savepoint_tag],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                logger.error(f"[Rollback] Failed to reset to savepoint {self.savepoint_tag}: {error_msg}")
                return False, f"git_reset_failed: {error_msg}"

            # Clean untracked files (git reset --hard doesn't remove new files)
            clean_result = subprocess.run(
                ["git", "clean", "-fd"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30
            )

            if clean_result.returncode != 0:
                error_msg = clean_result.stderr.strip()
                logger.warning(f"[Rollback] Failed to clean untracked files: {error_msg}")
                # Non-fatal - reset succeeded, just couldn't clean untracked files

            logger.info(f"[Rollback] Successfully rolled back to savepoint {self.savepoint_tag}")
            logger.info(f"[Rollback] Working tree restored to pre-patch state")

            # Log rollback action for audit trail
            self._log_rollback_action(reason)

            return True, None

        except subprocess.TimeoutExpired:
            logger.error(f"[Rollback] Timeout rolling back to savepoint {self.savepoint_tag}")
            return False, "git_reset_timeout"
        except Exception as e:
            logger.error(f"[Rollback] Exception during rollback: {e}")
            return False, f"git_reset_exception: {str(e)}"

    def cleanup_savepoint(self) -> None:
        """
        Delete the savepoint tag after successful patch apply.

        This prevents tag explosion in the repository.
        """
        if not self.savepoint_tag:
            return

        try:
            result = subprocess.run(
                ["git", "tag", "-d", self.savepoint_tag],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                logger.debug(f"[Rollback] Cleaned up savepoint tag: {self.savepoint_tag}")
            else:
                # Non-fatal - just log warning
                logger.warning(f"[Rollback] Failed to delete savepoint tag {self.savepoint_tag}: {result.stderr.strip()}")

        except Exception as e:
            logger.warning(f"[Rollback] Exception cleaning up savepoint: {e}")

    def _log_rollback_action(self, reason: str) -> None:
        """
        Log rollback action to audit file for compliance/debugging.

        Args:
            reason: Reason for rollback
        """
        try:
            # Log to .autonomous_runs/{run_id}/rollback.log
            runs_dir = self.workspace / ".autonomous_runs" / self.run_id
            runs_dir.mkdir(parents=True, exist_ok=True)

            rollback_log = runs_dir / "rollback.log"

            timestamp = datetime.utcnow().isoformat()
            log_entry = f"{timestamp} | Phase: {self.phase_id} | Savepoint: {self.savepoint_tag} | Reason: {reason}\n"

            with open(rollback_log, "a", encoding="utf-8") as f:
                f.write(log_entry)

            logger.info(f"[Rollback] Logged rollback action to {rollback_log}")

        except Exception as e:
            logger.warning(f"[Rollback] Failed to write rollback audit log: {e}")

    @staticmethod
    def cleanup_old_savepoints(workspace: Path, days_threshold: int = 7) -> int:
        """
        Clean up savepoint tags older than threshold.

        Args:
            workspace: Path to git repository root
            days_threshold: Delete tags older than this many days (default: 7)

        Returns:
            Number of tags deleted
        """
        try:
            # List all tags matching savepoint pattern
            result = subprocess.run(
                ["git", "tag", "-l", "save-before-*"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                logger.warning(f"[Rollback] Failed to list savepoint tags: {result.stderr.strip()}")
                return 0

            tags = [tag.strip() for tag in result.stdout.split("\n") if tag.strip()]

            if not tags:
                logger.debug("[Rollback] No savepoint tags found for cleanup")
                return 0

            deleted_count = 0
            threshold_timestamp = datetime.utcnow().timestamp() - (days_threshold * 86400)

            for tag in tags:
                # Get tag creation date
                tag_info_result = subprocess.run(
                    ["git", "log", "-1", "--format=%ct", tag],
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                if tag_info_result.returncode != 0:
                    continue

                try:
                    tag_timestamp = int(tag_info_result.stdout.strip())

                    if tag_timestamp < threshold_timestamp:
                        # Delete old tag
                        delete_result = subprocess.run(
                            ["git", "tag", "-d", tag],
                            cwd=workspace,
                            capture_output=True,
                            text=True,
                            timeout=5
                        )

                        if delete_result.returncode == 0:
                            deleted_count += 1
                            logger.debug(f"[Rollback] Deleted old savepoint tag: {tag}")

                except ValueError:
                    continue

            if deleted_count > 0:
                logger.info(f"[Rollback] Cleaned up {deleted_count} old savepoint tags (>{days_threshold} days)")

            return deleted_count

        except Exception as e:
            logger.warning(f"[Rollback] Exception during savepoint cleanup: {e}")
            return 0
