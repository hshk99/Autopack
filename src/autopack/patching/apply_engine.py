"""Patch application engine for Autopack.

Extracted from governed_apply.py as part of Item 1.1 god file refactoring (PR-APPLY-4).

This module contains the core patch application engine that executes git apply
and fallback strategies for applying patches to the filesystem.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ApplyResult:
    """Result of patch application attempt."""

    success: bool
    method: str  # "git_apply", "git_apply_lenient", "git_apply_3way", "manual", "failed"
    message: str
    files_modified: List[str]
    error_output: Optional[str] = None


def execute_git_apply(
    patch_content: str,
    workspace: Path,
    check_only: bool = False,
    reverse: bool = False,
) -> ApplyResult:
    """Execute git apply for patch application.

    Tries multiple strategies in order:
    1. Strict mode (default git apply)
    2. Lenient mode (--ignore-whitespace -C1)
    3. 3-way merge mode (-3)

    Args:
        patch_content: Unified diff patch
        workspace: Working directory
        check_only: If True, only check if patch applies (--check)
        reverse: If True, reverse the patch (--reverse)

    Returns:
        ApplyResult with success status and details
    """
    # Write patch to temporary file
    patch_file = workspace / "temp_patch.diff"
    try:
        with open(patch_file, "w", encoding="utf-8") as f:
            f.write(patch_content)

        # Also save a debug copy
        debug_patch_file = workspace / "last_patch_debug.diff"
        with open(debug_patch_file, "w", encoding="utf-8") as f:
            f.write(patch_content)

        # Build base command
        base_cmd = ["git", "apply"]
        if check_only:
            base_cmd.append("--check")
        if reverse:
            base_cmd.append("--reverse")

        # Strategy 1: Strict mode
        logger.info("Checking if patch can be applied (dry run - strict mode)...")
        check_cmd = base_cmd + ["temp_patch.diff"]
        check_result = subprocess.run(
            check_cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
        )

        if check_result.returncode == 0:
            if check_only:
                return ApplyResult(
                    success=True,
                    method="git_apply_check",
                    message="Patch can be applied (strict mode)",
                    files_modified=[],
                )

            # Apply in strict mode
            logger.info("Applying patch to filesystem (strict mode)...")
            apply_result = subprocess.run(
                ["git", "apply", "temp_patch.diff"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )

            if apply_result.returncode == 0:
                files_changed = _extract_files_from_patch(patch_content)
                logger.info(
                    f"Patch applied successfully (strict) - {len(files_changed)} files modified"
                )
                return ApplyResult(
                    success=True,
                    method="git_apply",
                    message=f"Patch applied successfully ({len(files_changed)} files)",
                    files_modified=files_changed,
                )
            else:
                error_msg = apply_result.stderr.strip()
                logger.error(f"Strict mode apply failed: {error_msg}")
                return ApplyResult(
                    success=False,
                    method="git_apply",
                    message=error_msg,
                    files_modified=[],
                    error_output=error_msg,
                )

        # Strategy 2: Lenient mode
        error_msg = check_result.stderr.strip()
        logger.warning(f"Strict patch check failed: {error_msg}")
        logger.info("Retrying with lenient mode (--ignore-whitespace -C1)...")

        lenient_check_cmd = [
            "git",
            "apply",
            "--check",
            "--ignore-whitespace",
            "-C1",
            "temp_patch.diff",
        ]
        lenient_check = subprocess.run(
            lenient_check_cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
        )

        if lenient_check.returncode == 0:
            if check_only:
                return ApplyResult(
                    success=True,
                    method="git_apply_lenient_check",
                    message="Patch can be applied (lenient mode)",
                    files_modified=[],
                )

            logger.info("Lenient mode check passed, applying patch...")
            apply_result = subprocess.run(
                ["git", "apply", "--ignore-whitespace", "-C1", "temp_patch.diff"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )

            if apply_result.returncode == 0:
                files_changed = _extract_files_from_patch(patch_content)
                logger.info(
                    f"Patch applied successfully (lenient) - {len(files_changed)} files modified"
                )
                return ApplyResult(
                    success=True,
                    method="git_apply_lenient",
                    message=f"Patch applied successfully in lenient mode ({len(files_changed)} files)",
                    files_modified=files_changed,
                )
            else:
                error_msg = apply_result.stderr.strip()
                logger.error(f"Lenient mode apply failed: {error_msg}")
                return ApplyResult(
                    success=False,
                    method="git_apply_lenient",
                    message=error_msg,
                    files_modified=[],
                    error_output=error_msg,
                )

        # Strategy 3: 3-way merge mode
        logger.warning(f"Lenient mode also failed: {lenient_check.stderr.strip()}")
        logger.info("Retrying with 3-way merge mode (-3)...")

        three_way_check_cmd = ["git", "apply", "--check", "-3", "temp_patch.diff"]
        three_way_check = subprocess.run(
            three_way_check_cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
        )

        if three_way_check.returncode == 0:
            if check_only:
                return ApplyResult(
                    success=True,
                    method="git_apply_3way_check",
                    message="Patch can be applied (3-way merge)",
                    files_modified=[],
                )

            logger.info("3-way merge mode check passed, applying patch...")
            apply_result = subprocess.run(
                ["git", "apply", "-3", "temp_patch.diff"],
                cwd=workspace,
                capture_output=True,
                text=True,
            )

            if apply_result.returncode == 0:
                files_changed = _extract_files_from_patch(patch_content)
                logger.info(
                    f"Patch applied successfully (3-way) - {len(files_changed)} files modified"
                )
                return ApplyResult(
                    success=True,
                    method="git_apply_3way",
                    message=f"Patch applied successfully in 3-way merge mode ({len(files_changed)} files)",
                    files_modified=files_changed,
                )
            else:
                error_msg = apply_result.stderr.strip()
                logger.error(f"3-way merge apply failed: {error_msg}")
                return ApplyResult(
                    success=False,
                    method="git_apply_3way",
                    message=error_msg,
                    files_modified=[],
                    error_output=error_msg,
                )

        # All strategies failed
        final_error = three_way_check.stderr.strip()
        logger.error(f"All git apply modes failed. Final error: {final_error}")
        return ApplyResult(
            success=False,
            method="failed",
            message=f"All git apply modes failed: {final_error}",
            files_modified=[],
            error_output=final_error,
        )

    finally:
        # Clean up temp file
        if patch_file.exists():
            patch_file.unlink()


def execute_manual_apply(
    patch_content: str,
    workspace: Path,
    target_files: Optional[List[str]] = None,
) -> ApplyResult:
    """Fallback manual patch application (direct file write for new files only).

    This extracts new file content from patches and writes them directly.
    ONLY works for new files (where --- /dev/null) - partial patches for
    existing files cannot be safely applied this way.

    Args:
        patch_content: Unified diff patch for single or multiple files
        workspace: Working directory
        target_files: Optional list of specific files to apply (default: all new files)

    Returns:
        ApplyResult with success status
    """
    # First, classify which files are new vs existing
    new_files, existing_files = _classify_patch_files(patch_content)

    if existing_files:
        logger.error(
            "[Manual Apply] Patch modifies existing files. Cannot safely apply partial patches."
        )
        return ApplyResult(
            success=False,
            method="manual",
            message="Cannot manually apply patches to existing files (only new files supported)",
            files_modified=[],
            error_output="existing_files_detected",
        )

    if not new_files:
        logger.error("[Manual Apply] No new files detected for direct write.")
        return ApplyResult(
            success=False,
            method="manual",
            message="No new files found in patch",
            files_modified=[],
            error_output="no_new_files",
        )

    # Filter by target_files if specified
    if target_files:
        new_files = new_files & set(target_files)

    if not new_files:
        return ApplyResult(
            success=False,
            method="manual",
            message="No matching new files to apply",
            files_modified=[],
            error_output="no_matching_files",
        )

    logger.info(f"[Manual Apply] Attempting direct write for {len(new_files)} new files")

    files_written = []
    lines = patch_content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # Look for new file diffs
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= 4:
                file_path = parts[3][2:]  # Remove 'b/' prefix

                # Check if this file should be processed
                if file_path not in new_files:
                    i += 1
                    continue

                # Check if this is a new file (has '--- /dev/null' or 'new file mode')
                is_new_file = False
                hunk_start = -1
                j = i + 1
                while j < len(lines) and not lines[j].startswith("diff --git"):
                    if lines[j].startswith("new file mode") or lines[j] == "--- /dev/null":
                        is_new_file = True
                    if lines[j].startswith("@@"):
                        hunk_start = j
                        break
                    j += 1

                # Only process new files
                if is_new_file and hunk_start >= 0:
                    content_lines = []

                    # Handle malformed hunk header where content is on same line
                    hunk_line = lines[hunk_start]
                    hunk_header_end = hunk_line.rfind("@@")
                    if hunk_header_end > 2:
                        after_header = hunk_line[hunk_header_end + 2 :].lstrip()
                        if after_header:
                            content_lines.append(after_header)

                    k = hunk_start + 1
                    while k < len(lines) and not lines[k].startswith("diff --git"):
                        line_k = lines[k]
                        # Skip additional hunk headers
                        if line_k.startswith("@@"):
                            # Handle inline content after @@
                            hunk_end = line_k.rfind("@@")
                            if hunk_end > 2:
                                after_hunk = line_k[hunk_end + 2 :].lstrip()
                                if after_hunk:
                                    content_lines.append(after_hunk)
                            k += 1
                            continue
                        # Extract added lines (for new files, everything after + is content)
                        if line_k.startswith("+") and not line_k.startswith("+++"):
                            content_lines.append(line_k[1:])
                        k += 1

                    if content_lines:
                        full_path = workspace / file_path
                        try:
                            full_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(full_path, "w", encoding="utf-8") as f:
                                f.write("\n".join(content_lines))
                                if not content_lines[-1] == "":
                                    f.write("\n")
                            files_written.append(file_path)
                            logger.info(f"[Manual Apply] Directly wrote file: {file_path}")
                        except Exception as e:
                            logger.error(f"[Manual Apply] Failed to write {file_path}: {e}")
                            return ApplyResult(
                                success=False,
                                method="manual",
                                message=f"Failed to write file {file_path}: {e}",
                                files_modified=files_written,
                                error_output=str(e),
                            )

        i += 1

    if len(files_written) == len(new_files):
        logger.info(f"[Manual Apply] Successfully wrote {len(files_written)} files")
        return ApplyResult(
            success=True,
            method="manual",
            message=f"Manually applied {len(files_written)} new files",
            files_modified=files_written,
        )
    else:
        logger.error(
            f"[Manual Apply] Incomplete: expected {len(new_files)} files, wrote {len(files_written)}"
        )
        return ApplyResult(
            success=False,
            method="manual",
            message=f"Incomplete manual apply: expected {len(new_files)}, wrote {len(files_written)}",
            files_modified=files_written,
            error_output="incomplete_write",
        )


def recover_from_failed_apply(
    workspace: Path,
    backup_files: List[str],
) -> bool:
    """Recover from failed patch application by restoring backups.

    Note: This function is currently a placeholder for future enhancement.
    The actual backup/restore logic is still in GovernedApplyPath for now.

    Args:
        workspace: Working directory
        backup_files: List of backup file paths to restore

    Returns:
        True if recovery successful
    """
    logger.warning(
        "[Recovery] recover_from_failed_apply called but backup/restore logic still in GovernedApplyPath"
    )
    return False


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _extract_files_from_patch(patch_content: str) -> List[str]:
    """Extract list of files modified from patch content.

    Args:
        patch_content: Git diff/patch content

    Returns:
        List of file paths that were modified
    """
    files = []
    for line in patch_content.split("\n"):
        # Look for diff --git a/path b/path lines
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= 4:
                # Extract file path from 'a/path/to/file'
                file_path = parts[2][2:]  # Remove 'a/' prefix
                files.append(file_path)
        # Also look for +++ b/path lines as backup
        elif line.startswith("+++") and not line.startswith("+++ /dev/null"):
            file_path = line[6:].strip()  # Remove '+++ b/'
            if file_path and file_path not in files:
                files.append(file_path)

    return files


def _classify_patch_files(patch_content: str) -> Tuple[Set[str], Set[str]]:
    """Identify which files in a patch are new vs. existing.

    Returns:
        Tuple of (new_files, existing_files) as relative paths
    """
    new_files: Set[str] = set()
    existing_files: Set[str] = set()
    current_file = None

    lines = patch_content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("diff --git"):
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[3][2:]  # b/path -> path
            continue

        if current_file is None:
            continue

        if line.startswith("new file mode") or line.startswith("--- /dev/null"):
            new_files.add(current_file)
        elif line.startswith("deleted file mode") or line.startswith("+++ /dev/null"):
            existing_files.add(current_file)
        elif line.startswith("--- a/") and "/dev/null" not in line:
            existing_files.add(current_file)

    return new_files, existing_files
