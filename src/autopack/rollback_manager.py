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
- Safe clean mode: protects .env, *.db, .autonomous_runs/ from deletion

Cleanup strategy:
- Savepoint tags are kept for 7 days by default
- Per-run retention: keeps last N savepoints for audit (default: 3)
- Can be cleaned up via: git tag -d save-before-*
- Or run cleanup method to delete tags older than threshold
"""

import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

# Protected file patterns - never deleted by git clean during rollback
# These files are important for development and should not be removed
PROTECTED_PATTERNS = {
    ".env",  # Environment configuration
    ".env.local",  # Local environment overrides
    "*.db",  # SQLite databases
    "autopack.db",  # Main database file
    ".autonomous_runs/",  # Run artifacts (should be gitignored)
    "*.log",  # Log files
    ".vscode/",  # VSCode settings
    ".idea/",  # IntelliJ settings
}


class RollbackManager:
    """Manages git-based savepoints and rollback for autonomous executor."""

    def __init__(
        self, workspace: Path, run_id: str, phase_id: str, max_savepoints_per_run: int = 3
    ):
        """
        Initialize rollback manager.

        Args:
            workspace: Path to git repository root
            run_id: Current run ID
            phase_id: Current phase ID
            max_savepoints_per_run: Maximum savepoints to keep per run (default: 3)
        """
        self.workspace = Path(workspace)
        self.run_id = run_id
        self.phase_id = phase_id
        self.savepoint_tag: Optional[str] = None
        self.max_savepoints_per_run = max_savepoints_per_run

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
                timeout=10,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                logger.error(
                    f"[Rollback] Failed to create savepoint tag {self.savepoint_tag}: {error_msg}"
                )
                return False, f"git_tag_failed: {error_msg}"

            logger.info(f"[Rollback] Created savepoint: {self.savepoint_tag}")
            return True, None

        except subprocess.TimeoutExpired:
            logger.error(f"[Rollback] Timeout creating savepoint tag {self.savepoint_tag}")
            return False, "git_tag_timeout"
        except Exception as e:
            logger.error(f"[Rollback] Exception creating savepoint: {e}")
            return False, f"git_tag_exception: {str(e)}"

    def _check_protected_untracked_files(self) -> Tuple[bool, List[str]]:
        """
        Check for protected untracked files that would be deleted by git clean.

        Returns:
            Tuple of (has_protected_files: bool, protected_files: List[str])
        """
        try:
            # Get list of untracked files that would be deleted by git clean
            result = subprocess.run(
                ["git", "clean", "-fdn"],  # Dry run mode
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.warning(
                    f"[Rollback] Failed to check untracked files: {result.stderr.strip()}"
                )
                return False, []

            # Parse output - format is "Would remove <path>"
            untracked_files = []
            for line in result.stdout.split("\n"):
                if line.startswith("Would remove "):
                    file_path = line.replace("Would remove ", "").strip()
                    untracked_files.append(file_path)

            # Check if any untracked files match protected patterns
            protected_files = []
            for file_path in untracked_files:
                # Normalize path separators for matching
                normalized_path = file_path.replace("\\", "/")

                for pattern in PROTECTED_PATTERNS:
                    matched = False

                    # Simple pattern matching - expand if needed
                    if pattern.endswith("/"):
                        # Directory pattern - match if path starts with or contains directory
                        if (
                            normalized_path.startswith(pattern)
                            or ("/" + pattern) in normalized_path
                        ):
                            matched = True
                    elif "*" in pattern:
                        # Glob pattern (simple implementation for *.ext patterns)
                        suffix = pattern.replace("*", "")
                        if normalized_path.endswith(suffix):
                            matched = True
                    else:
                        # Exact match - check full path or basename
                        basename = normalized_path.split("/")[-1]
                        if (
                            normalized_path == pattern
                            or basename == pattern
                            or normalized_path.endswith("/" + pattern)
                        ):
                            matched = True

                    if matched:
                        protected_files.append(file_path)
                        break

            return len(protected_files) > 0, protected_files

        except Exception as e:
            logger.warning(f"[Rollback] Exception checking protected files: {e}")
            return False, []

    def rollback_to_savepoint(
        self, reason: str, safe_clean: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Rollback working tree to savepoint tag.

        Args:
            reason: Reason for rollback (for logging)
            safe_clean: If True, check for protected files before cleaning (default: True)

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        if not self.savepoint_tag:
            logger.error("[Rollback] No savepoint tag set - cannot rollback")
            return False, "no_savepoint_tag_set"

        try:
            logger.warning(f"[Rollback] Rolling back to savepoint {self.savepoint_tag}")
            logger.warning(f"[Rollback] Reason: {reason}")

            # Check for protected untracked files before cleaning
            has_protected = False
            protected_files = []
            if safe_clean:
                has_protected, protected_files = self._check_protected_untracked_files()
                if has_protected:
                    logger.warning(
                        "[Rollback] Protected untracked files detected - skipping git clean"
                    )
                    logger.warning(f"[Rollback] Protected files: {', '.join(protected_files)}")
                    logger.info(
                        "[Rollback] These files will NOT be deleted: .env, *.db, .autonomous_runs/, etc."
                    )
                    # Continue with reset, but skip clean

            # Reset working tree to savepoint tag (hard reset discards all changes)
            result = subprocess.run(
                ["git", "reset", "--hard", self.savepoint_tag],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                logger.error(
                    f"[Rollback] Failed to reset to savepoint {self.savepoint_tag}: {error_msg}"
                )
                return False, f"git_reset_failed: {error_msg}"

            # Clean untracked files (git reset --hard doesn't remove new files)
            # Skip if safe_clean is enabled and protected files detected
            skip_clean = safe_clean and has_protected
            if not skip_clean:
                clean_result = subprocess.run(
                    ["git", "clean", "-fd"],
                    cwd=self.workspace,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if clean_result.returncode != 0:
                    error_msg = clean_result.stderr.strip()
                    logger.warning(f"[Rollback] Failed to clean untracked files: {error_msg}")
                    # Non-fatal - reset succeeded, just couldn't clean untracked files
                else:
                    logger.debug("[Rollback] Cleaned untracked files")
            else:
                logger.info("[Rollback] Skipped git clean due to protected files")

            logger.info(f"[Rollback] Successfully rolled back to savepoint {self.savepoint_tag}")
            logger.info("[Rollback] Working tree restored to pre-patch state")

            # Log rollback action for audit trail
            self._log_rollback_action(reason)

            return True, None

        except subprocess.TimeoutExpired:
            logger.error(f"[Rollback] Timeout rolling back to savepoint {self.savepoint_tag}")
            return False, "git_reset_timeout"
        except Exception as e:
            logger.error(f"[Rollback] Exception during rollback: {e}")
            return False, f"git_reset_exception: {str(e)}"

    def cleanup_savepoint(self, keep_last_n: bool = True) -> None:
        """
        Delete the savepoint tag after successful patch apply.

        This prevents tag explosion in the repository. If keep_last_n is True,
        keeps the most recent N savepoints per run for audit purposes.

        Args:
            keep_last_n: If True, keep last N savepoints per run (default: True)
        """
        if not self.savepoint_tag:
            return

        try:
            # If keep_last_n is enabled, check if we should retain this savepoint
            if keep_last_n:
                # Get all savepoint tags for this run
                run_tags = self._get_run_savepoint_tags()

                # Sort by timestamp (newest first)
                run_tags_sorted = sorted(run_tags, reverse=True)

                # If we have more than max_savepoints_per_run, delete oldest ones
                if len(run_tags_sorted) > self.max_savepoints_per_run:
                    tags_to_delete = run_tags_sorted[self.max_savepoints_per_run :]
                    for old_tag in tags_to_delete:
                        self._delete_tag(old_tag)
                    logger.info(
                        f"[Rollback] Kept last {self.max_savepoints_per_run} savepoints, deleted {len(tags_to_delete)} old ones"
                    )

                # Keep the current savepoint (don't delete it)
                logger.debug(f"[Rollback] Keeping savepoint tag for audit: {self.savepoint_tag}")
            else:
                # Original behavior - delete the savepoint tag immediately
                self._delete_tag(self.savepoint_tag)

        except Exception as e:
            logger.warning(f"[Rollback] Exception cleaning up savepoint: {e}")

    def _get_run_savepoint_tags(self) -> List[str]:
        """
        Get all savepoint tags for the current run.

        Returns:
            List of savepoint tag names for this run
        """
        try:
            # Sanitize run_id for tag pattern matching
            safe_run_id = self.run_id.replace("/", "-").replace(" ", "-")
            pattern = f"save-before-{safe_run_id}-*"

            result = subprocess.run(
                ["git", "tag", "-l", pattern],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.warning(
                    f"[Rollback] Failed to list run savepoint tags: {result.stderr.strip()}"
                )
                return []

            tags = [tag.strip() for tag in result.stdout.split("\n") if tag.strip()]
            return tags

        except Exception as e:
            logger.warning(f"[Rollback] Exception getting run savepoint tags: {e}")
            return []

    def _delete_tag(self, tag_name: str) -> bool:
        """
        Delete a git tag.

        Args:
            tag_name: Name of the tag to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "tag", "-d", tag_name],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                logger.debug(f"[Rollback] Deleted savepoint tag: {tag_name}")
                return True
            else:
                logger.warning(
                    f"[Rollback] Failed to delete savepoint tag {tag_name}: {result.stderr.strip()}"
                )
                return False

        except Exception as e:
            logger.warning(f"[Rollback] Exception deleting tag {tag_name}: {e}")
            return False

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
                timeout=10,
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
                    timeout=5,
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
                            timeout=5,
                        )

                        if delete_result.returncode == 0:
                            deleted_count += 1
                            logger.debug(f"[Rollback] Deleted old savepoint tag: {tag}")

                except ValueError:
                    continue

            if deleted_count > 0:
                logger.info(
                    f"[Rollback] Cleaned up {deleted_count} old savepoint tags (>{days_threshold} days)"
                )

            return deleted_count

        except Exception as e:
            logger.warning(f"[Rollback] Exception during savepoint cleanup: {e}")
            return 0
