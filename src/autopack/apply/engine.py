"""Core patch application engine.

Extracted from governed_apply.py for PR-APPLY-4.

This module handles:
- Git apply execution with fallback strategies
- Direct file write fallback for new files
- Patch context validation
- YAML repair integration
- NDJSON synthetic patch handling
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .policy import (
    extract_justification_from_patch,
    get_effective_allowed_paths,
    get_effective_protected_paths,
    is_path_protected,
    validate_patch_paths,
)
from .quality import (
    backup_files,
    restore_file,
    validate_applied_files,
    validate_content_changes,
    validate_patch_quality,
)
from .sanitize import (
    classify_patch_files,
    extract_files_from_patch,
    normalize_patch,
    repair_hunk_headers,
    sanitize_patch,
)

logger = logging.getLogger(__name__)


class PatchApplyError(Exception):
    """Raised when patch application fails."""

    pass


def validate_patch_context(patch_content: str, workspace: Path) -> List[str]:
    """
    BUILD-045: Validate that patch hunk context lines match actual file content.

    This detects goal drift where LLM generates patches for the wrong file state,
    preventing git apply failures due to context mismatches.

    Args:
        patch_content: Patch content to validate
        workspace: Path to workspace root

    Returns:
        List of validation error messages (empty if context matches)
    """
    import re

    errors = []

    # Parse patch to extract file paths and hunks
    current_file = None
    current_hunks: List[Dict] = []

    lines = patch_content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]

        # Extract file path from diff header
        if line.startswith("diff --git"):
            # Save previous file's hunks for validation
            if current_file and current_hunks:
                file_errors = _validate_file_hunks(workspace, current_file, current_hunks)
                errors.extend(file_errors)

            # Extract new file path (e.g., "diff --git a/src/file.py b/src/file.py")
            parts = line.split()
            if len(parts) >= 4:
                # Remove a/ or b/ prefix
                current_file = parts[3].lstrip("b/")
                current_hunks = []

        # Parse hunk header (e.g., "@@ -10,5 +12,6 @@")
        elif line.startswith("@@"):
            match = re.match(r"^@@\s+-(\d+),(\d+)\s+\+(\d+),(\d+)\s+@@", line)
            if match:
                old_start = int(match.group(1))

                # Extract context lines from this hunk
                hunk_lines = []
                j = i + 1
                while (
                    j < len(lines)
                    and not lines[j].startswith("@@")
                    and not lines[j].startswith("diff --git")
                ):
                    hunk_lines.append(lines[j])
                    j += 1

                # Extract context lines (lines without + or - prefix, or lines with - prefix)
                context_lines = []
                for hunk_line in hunk_lines:
                    if hunk_line.startswith(" ") or hunk_line.startswith("-"):
                        # Remove the prefix to get actual line content
                        context_lines.append(hunk_line[1:] if hunk_line else "")

                if context_lines:
                    current_hunks.append(
                        {
                            "start_line": old_start,
                            "context": context_lines[:5],  # First 5 context lines for validation
                        }
                    )

        i += 1

    # Validate last file's hunks
    if current_file and current_hunks:
        file_errors = _validate_file_hunks(workspace, current_file, current_hunks)
        errors.extend(file_errors)

    return errors


def _validate_file_hunks(workspace: Path, file_path: str, hunks: List[Dict]) -> List[str]:
    """
    Validate that hunk context lines match actual file content.

    Args:
        workspace: Path to workspace root
        file_path: Relative path to file
        hunks: List of hunk dictionaries with start_line and context

    Returns:
        List of validation error messages
    """
    errors = []

    # Check if file exists
    full_path = workspace / file_path
    if not full_path.exists():
        # File doesn't exist yet - this is a new file, skip validation
        return errors

    try:
        # Read actual file content
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            actual_lines = f.readlines()

        # Validate each hunk
        for hunk in hunks:
            start_line = hunk["start_line"]
            context = hunk["context"]

            # Check if start_line is within file bounds
            if start_line < 1 or start_line > len(actual_lines):
                errors.append(
                    f"{file_path}: Hunk starts at line {start_line} but file only has {len(actual_lines)} lines"
                )
                continue

            # Check if context lines match (allowing for minor whitespace differences)
            for i, context_line in enumerate(context[:3]):  # Check first 3 context lines
                actual_line_num = start_line + i - 1  # 0-indexed
                if actual_line_num < 0 or actual_line_num >= len(actual_lines):
                    continue

                actual_line = actual_lines[actual_line_num].rstrip("\n")
                context_line_normalized = context_line.rstrip()
                actual_line_normalized = actual_line.rstrip()

                # Compare normalized lines (ignore trailing whitespace)
                if context_line_normalized != actual_line_normalized:
                    # Allow minor differences (e.g., tabs vs spaces) for first line
                    if i == 0 and context_line_normalized.strip() == actual_line_normalized.strip():
                        continue

                    errors.append(
                        f"{file_path}:{start_line + i}: Context mismatch - "
                        f"expected '{context_line_normalized}' but found '{actual_line_normalized}'"
                    )
                    break  # Don't flood with errors for same hunk

    except Exception as e:
        # Don't fail validation if we can't read the file - let git apply handle it
        logger.debug(f"[BUILD-045] Could not validate {file_path}: {e}")

    return errors


def check_existing_files_for_new_patches(patch_content: str, workspace: Path) -> None:
    """
    Check that patches marked as 'new file' don't overwrite existing files.

    When a patch marks a file as 'new file mode' but the file already exists,
    fail fast and require the patch to be emitted as a modification instead.

    Args:
        patch_content: Patch content to check
        workspace: Path to workspace root

    Raises:
        PatchApplyError: If patch tries to create file that already exists
    """
    from .policy import PROTECTED_PATHS, is_path_protected

    lines = patch_content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.startswith("diff --git"):
            # Extract file path: diff --git a/path b/path
            parts = line.split()
            if len(parts) >= 4:
                file_path = parts[3][2:]  # Remove 'b/' prefix
                full_path = workspace / file_path

                # Check if next lines indicate new file mode
                if i + 1 < len(lines) and lines[i + 1].startswith("new file mode"):
                    if full_path.exists():
                        # File exists but patch wants to create it - treat as an error
                        if is_path_protected(file_path, PROTECTED_PATHS, []):
                            raise PatchApplyError(
                                f"Unsafe patch: attempts to create protected file as new when it already exists: {file_path}. "
                                f"Refuse to delete/replace protected files."
                            )
                        raise PatchApplyError(
                            f"Unsafe patch: attempts to create existing file as new: {file_path}. "
                            f"Emit this change as a modification instead of 'new file mode'."
                        )

        i += 1


def apply_patch_directly(patch_content: str, workspace: Path) -> Tuple[bool, List[str]]:
    """
    Apply patch by directly writing files - fallback when git apply fails.

    This extracts new file content from patches and writes them directly.
    ONLY works for new files (where --- /dev/null) - partial patches for
    existing files cannot be safely applied this way.

    Args:
        patch_content: Patch content
        workspace: Path to workspace root

    Returns:
        Tuple of (success, list of files written)
    """
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

                # Check if this is a new file (has '--- /dev/null')
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

                # Only process new files - for existing files, we can't safely
                # apply partial patches without the original file content
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
                                if content_lines[-1] != "":
                                    f.write("\n")
                            files_written.append(file_path)
                            logger.info(f"Directly wrote file: {file_path}")
                        except Exception as e:
                            logger.error(f"Failed to write {file_path}: {e}")
                elif not is_new_file:
                    logger.warning(
                        f"Skipping {file_path} - cannot apply partial patch to existing file via direct write"
                    )

        i += 1

    return len(files_written) > 0, files_written


def restore_corrupted_files(
    workspace: Path,
    corrupted_files: List[str],
    backups: Dict[str, Tuple[str, str]],
    protected_paths: List[str],
) -> Tuple[int, int]:
    """
    Attempt to restore corrupted files from backup.

    Args:
        workspace: Path to workspace root
        corrupted_files: List of corrupted file paths
        backups: Dict of backups from backup_files()
        protected_paths: List of protected path prefixes

    Returns:
        Tuple of (restored_count, failed_count)
    """
    restored = 0
    failed = 0

    for rel_path in corrupted_files:
        if rel_path in backups:
            if restore_file(workspace, rel_path, backups[rel_path]):
                restored += 1
            else:
                failed += 1
        else:
            # No backup available - file was new, just delete it
            full_path = workspace / rel_path
            try:
                if is_path_protected(rel_path, protected_paths, []):
                    logger.error(
                        "[Integrity] Refusing to delete protected file %s even though it appears 'new' "
                        "(no backup available). Treating as failure.",
                        rel_path,
                    )
                    failed += 1
                    continue
                full_path.unlink()
                logger.info(f"[Integrity] Removed corrupted new file: {rel_path}")
                restored += 1
            except Exception as e:
                logger.error(f"[Integrity] Failed to remove {rel_path}: {e}")
                failed += 1

    return restored, failed


def run_git_apply(
    workspace: Path,
    patch_file: Path,
    mode: str = "strict",
) -> Tuple[bool, str]:
    """
    Run git apply with specified mode.

    Args:
        workspace: Path to workspace root
        patch_file: Path to patch file
        mode: One of "strict", "lenient", "three_way"

    Returns:
        Tuple of (success, error_message)
    """
    if mode == "strict":
        cmd = ["git", "apply", patch_file.name]
    elif mode == "lenient":
        cmd = ["git", "apply", "--ignore-whitespace", "-C1", patch_file.name]
    elif mode == "three_way":
        cmd = ["git", "apply", "-3", patch_file.name]
    else:
        return False, f"Unknown mode: {mode}"

    result = subprocess.run(
        cmd,
        cwd=workspace,
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        return True, ""
    else:
        return False, result.stderr.strip()


def check_git_apply(
    workspace: Path,
    patch_file: Path,
    mode: str = "strict",
) -> Tuple[bool, str]:
    """
    Run git apply --check with specified mode.

    Args:
        workspace: Path to workspace root
        patch_file: Path to patch file
        mode: One of "strict", "lenient", "three_way"

    Returns:
        Tuple of (success, error_message)
    """
    if mode == "strict":
        cmd = ["git", "apply", "--check", patch_file.name]
    elif mode == "lenient":
        cmd = ["git", "apply", "--check", "--ignore-whitespace", "-C1", patch_file.name]
    elif mode == "three_way":
        cmd = ["git", "apply", "--check", "-3", patch_file.name]
    else:
        return False, f"Unknown mode: {mode}"

    result = subprocess.run(
        cmd,
        cwd=workspace,
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        return True, ""
    else:
        return False, result.stderr.strip()


def is_ndjson_synthetic_patch(patch_content: str) -> bool:
    """
    Check if patch is a synthetic NDJSON patch header.

    BUILD-129: When the Builder uses NDJSON, operations are applied directly to disk
    inside the LLM client. The executor still threads a synthetic diff-like header
    through the pipeline for deliverables validation.

    Args:
        patch_content: Patch content to check

    Returns:
        True if this is a synthetic NDJSON patch
    """
    stripped = patch_content.lstrip()
    return stripped.startswith("# NDJSON Operations Applied")


def apply_patch(
    patch_content: str,
    workspace: Path,
    *,
    full_file_mode: bool = False,
    scope_paths: Optional[List[str]] = None,
    autopack_internal_mode: bool = False,
    additional_protected: Optional[List[str]] = None,
    additional_allowed: Optional[List[str]] = None,
    rollback_manager: Optional[object] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Apply a patch to the filesystem.

    Args:
        patch_content: The patch content to apply (git diff format)
        workspace: Path to workspace root
        full_file_mode: If True, allows direct write fallback for complete file contents.
                       If False (diff mode), skips direct write fallback and fails fast.
        scope_paths: Optional list of allowed file paths (scope enforcement)
        autopack_internal_mode: If True, unlocks src/autopack/ for maintenance
        additional_protected: Additional paths to protect
        additional_allowed: Additional paths to allow
        rollback_manager: Optional rollback manager for savepoint support

    Returns:
        Tuple of (success: bool, error_message: Optional[str])
        - (True, None) if patch applied successfully
        - (False, error_message) if patch failed with error details
    """
    if not patch_content or not patch_content.strip():
        logger.warning("Empty patch content provided")
        return True, None  # Empty patch is technically successful

    # Get effective path lists
    protected_paths = get_effective_protected_paths(additional_protected, autopack_internal_mode)
    allowed_paths = get_effective_allowed_paths(additional_allowed)

    # Handle NDJSON synthetic patches
    if is_ndjson_synthetic_patch(patch_content):
        try:
            files_to_modify = extract_files_from_patch(patch_content)
            is_valid, violations = validate_patch_paths(
                files_to_modify, protected_paths, allowed_paths, scope_paths
            )
            if not is_valid:
                protected_path_violations = [
                    v.replace("Protected path: ", "")
                    for v in violations
                    if v.startswith("Protected path:")
                ]
                if protected_path_violations:
                    from autopack.governance_requests import create_protected_path_error

                    error_msg = create_protected_path_error(
                        violated_paths=protected_path_violations,
                        justification=extract_justification_from_patch(patch_content),
                    )
                    logger.warning(
                        f"[Governance] Protected path violation: {len(protected_path_violations)} paths"
                    )
                    return False, error_msg
                error_msg = f"Patch rejected - violations: {', '.join(violations)}"
                logger.error(f"[Isolation] {error_msg}")
                return False, error_msg
            logger.info(
                "[NDJSON] Detected synthetic NDJSON patch header; skipping git apply (already applied)"
            )
            return True, None
        except Exception as e:
            return False, f"ndjson_synthetic_patch_validation_failed: {e}"

    # Track savepoint creation status for rollback
    savepoint_created = False

    try:
        # Sanitize patch to fix common LLM output issues
        patch_content = sanitize_patch(patch_content)
        # Check for existing files that conflict with new file patches
        check_existing_files_for_new_patches(patch_content, workspace)
        # Repair incorrect line numbers and counts in hunk headers
        patch_content = repair_hunk_headers(patch_content, workspace)
        # Normalize line endings
        patch_content = normalize_patch(patch_content)

        # Backup files before modification
        files_to_modify = extract_files_from_patch(patch_content)

        # Check for protected path violations BEFORE applying
        is_valid, violations = validate_patch_paths(
            files_to_modify, protected_paths, allowed_paths, scope_paths
        )
        if not is_valid:
            protected_path_violations = [
                v.replace("Protected path: ", "")
                for v in violations
                if v.startswith("Protected path:")
            ]

            if protected_path_violations:
                from autopack.governance_requests import create_protected_path_error

                error_msg = create_protected_path_error(
                    violated_paths=protected_path_violations,
                    justification=extract_justification_from_patch(patch_content),
                )
                logger.warning(
                    f"[Governance] Protected path violation: {len(protected_path_violations)} paths"
                )
                return False, error_msg
            else:
                error_msg = f"Patch rejected - violations: {', '.join(violations)}"
                logger.error(f"[Isolation] {error_msg}")
                return False, error_msg

        backups = backup_files(workspace, files_to_modify)
        logger.debug(f"[Integrity] Backed up {len(backups)} existing files before patch")

        # Create git savepoint before applying patch (if rollback enabled)
        if rollback_manager:
            success, error = rollback_manager.create_savepoint()
            if success:
                savepoint_created = True
            else:
                logger.warning(
                    f"[Rollback] Failed to create savepoint: {error} - proceeding without rollback"
                )

        # Validate patch for common LLM truncation issues
        validation_errors = validate_patch_quality(patch_content)
        if validation_errors:
            # Check if any errors are YAML-related - attempt repair
            yaml_errors = [e for e in validation_errors if "YAML" in e or "yaml" in e]
            if yaml_errors and full_file_mode:
                logger.info(
                    f"[YamlRepair] Detected {len(yaml_errors)} YAML validation errors, attempting repair..."
                )
                # Note: YAML repair integration would go here
                # For now, we proceed with validation errors

            if validation_errors:
                error_details = "\n".join(f"  - {err}" for err in validation_errors)
                error_msg = f"Patch validation failed - LLM generated incomplete/truncated patch:\n{error_details}"
                logger.error(error_msg)
                logger.error(f"Patch content:\n{patch_content[:500]}...")
                raise PatchApplyError(error_msg)

        # Write patch to a temporary file
        patch_file = workspace / "temp_patch.diff"
        logger.info(f"Writing patch to {patch_file}")

        with open(patch_file, "w", encoding="utf-8") as f:
            f.write(patch_content)

        # Also save a debug copy
        debug_patch_file = workspace / "last_patch_debug.diff"
        with open(debug_patch_file, "w", encoding="utf-8") as f:
            f.write(patch_content)

        # Validate patch context matches actual file state before applying
        context_errors = validate_patch_context(patch_content, workspace)
        if context_errors:
            error_details = "\n".join(f"  - {err}" for err in context_errors)
            logger.error(f"[BUILD-045] Patch context validation failed:\n{error_details}")
            logger.warning(
                "[BUILD-045] This typically indicates goal drift - LLM generated patch for wrong file state"
            )
            logger.info(
                "[BUILD-045] Proceeding with git apply - 3-way merge may resolve context differences"
            )

        # Try different git apply modes
        use_mode = "strict"

        # First, try strict apply (dry run)
        logger.info("Checking if patch can be applied (dry run)...")
        success, error_msg = check_git_apply(workspace, patch_file, "strict")

        if not success:
            logger.warning(f"Strict patch check failed: {error_msg}")

            # Try lenient mode
            logger.info("Retrying with lenient mode (--ignore-whitespace -C1)...")
            success, error_msg = check_git_apply(workspace, patch_file, "lenient")
            if success:
                use_mode = "lenient"
                logger.info("Lenient mode check passed")
            else:
                # Try 3-way merge
                logger.warning(f"Lenient mode also failed: {error_msg}")
                logger.info("Retrying with 3-way merge mode (-3)...")
                success, error_msg = check_git_apply(workspace, patch_file, "three_way")
                if success:
                    use_mode = "three_way"
                    logger.info("3-way merge mode check passed")
                else:
                    # All git apply modes failed
                    if not full_file_mode:
                        logger.error(
                            "All git apply modes failed for diff-mode patch. Direct write fallback skipped."
                        )
                        if patch_file.exists():
                            patch_file.unlink()
                        return (
                            False,
                            "diff_mode_patch_failed: All git apply modes failed and direct write is not available for diff patches",
                        )

                    new_files, existing_files = classify_patch_files(patch_content)
                    if existing_files:
                        logger.error(
                            "[Integrity] Patch modifies existing files. Skipping direct-write fallback."
                        )
                        if patch_file.exists():
                            patch_file.unlink()
                        return False, "git_apply_failed_existing_files_no_fallback"

                    if not new_files:
                        logger.error(
                            "[Integrity] Git apply failed and no new files detected for fallback."
                        )
                        if patch_file.exists():
                            patch_file.unlink()
                        return False, "git_apply_failed_no_new_files_for_fallback"

                    # Try direct file write as last resort
                    logger.warning(
                        "All git apply modes failed, attempting direct file write fallback..."
                    )
                    direct_success, files_written = apply_patch_directly(patch_content, workspace)
                    if direct_success and len(files_written) == len(new_files):
                        logger.info(f"Direct file write succeeded - {len(files_written)} files")

                        # Validate files after direct write
                        all_valid, corrupted = validate_applied_files(workspace, files_written)
                        if not all_valid:
                            logger.error(
                                f"[Integrity] Direct write corrupted {len(corrupted)} files"
                            )
                            restored, failed = restore_corrupted_files(
                                workspace, corrupted, backups, protected_paths
                            )
                            if patch_file.exists():
                                patch_file.unlink()
                            return (
                                False,
                                f"Direct file write corrupted {len(corrupted)} files (restored {restored})",
                            )

                        # Validate content changes
                        content_valid, problem_files = validate_content_changes(
                            workspace, files_written, backups
                        )
                        if not content_valid:
                            logger.warning(
                                f"[Validation] Content validation issues in {len(problem_files)} files."
                            )

                        if patch_file.exists():
                            patch_file.unlink()
                        return True, None
                    else:
                        logger.error("Direct file write failed or incomplete")
                        if patch_file.exists():
                            patch_file.unlink()
                        return False, error_msg

        # Apply patch using git
        logger.info(f"Applying patch to filesystem (mode: {use_mode})...")
        success, error_msg = run_git_apply(workspace, patch_file, use_mode)

        # Clean up temp file
        if patch_file.exists():
            patch_file.unlink()

        if not success:
            logger.error(f"Failed to apply patch: {error_msg}")

            # Rollback to savepoint on apply failure
            if savepoint_created and rollback_manager:
                rollback_success, rollback_error = rollback_manager.rollback_to_savepoint(
                    f"Git apply failed: {error_msg}"
                )
                if rollback_success:
                    logger.info("[Rollback] Successfully rolled back to pre-patch state")
                else:
                    logger.error(f"[Rollback] Rollback failed: {rollback_error}")

            return False, error_msg

        # Extract files that were modified
        files_changed = extract_files_from_patch(patch_content)
        logger.info(f"Patch applied successfully - {len(files_changed)} files modified")
        for file_path in files_changed:
            logger.info(f"  - {file_path}")

        # Validate files after git apply
        all_valid, corrupted = validate_applied_files(workspace, files_changed)
        if not all_valid:
            logger.error(f"[Integrity] Git apply corrupted {len(corrupted)} files - restoring")

            # Rollback to savepoint on validation failure
            if savepoint_created and rollback_manager:
                rollback_success, rollback_error = rollback_manager.rollback_to_savepoint(
                    f"Post-apply validation failed: {len(corrupted)} corrupted files"
                )
                if rollback_success:
                    logger.info("[Rollback] Successfully rolled back to pre-patch state")
                    return (
                        False,
                        f"Patch corrupted {len(corrupted)} files - rolled back to savepoint",
                    )
                else:
                    logger.error(f"[Rollback] Rollback failed: {rollback_error}")

            # Fallback to file-level restore if rollback not enabled or failed
            restored, failed = restore_corrupted_files(
                workspace, corrupted, backups, protected_paths
            )
            return (
                False,
                f"Patch corrupted {len(corrupted)} files (restored {restored}, failed {failed})",
            )

        # Validate content changes (symbol preservation, structural similarity)
        content_valid, problem_files = validate_content_changes(workspace, files_changed, backups)
        if not content_valid:
            logger.warning(
                f"[Validation] Content validation issues in {len(problem_files)} files. "
                "Patch applied but may have unintended changes."
            )

        # Cleanup savepoint on successful apply
        if savepoint_created and rollback_manager:
            rollback_manager.cleanup_savepoint()

        return True, None

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Exception during patch application: {error_msg}")

        # Rollback to savepoint on exception
        if savepoint_created and rollback_manager:
            rollback_success, rollback_error = rollback_manager.rollback_to_savepoint(
                f"Exception during patch apply: {error_msg}"
            )
            if rollback_success:
                logger.info(
                    "[Rollback] Successfully rolled back to pre-patch state after exception"
                )
            else:
                logger.error(f"[Rollback] Rollback failed: {rollback_error}")

        # Clean up temp file if it exists
        patch_file = workspace / "temp_patch.diff"
        if patch_file.exists():
            patch_file.unlink()
        return False, error_msg
