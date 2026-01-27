"""Patch validation logic extracted from governed_apply.py.

This module contains validation functions for patch content, file integrity,
and content changes. It reduces complexity in governed_apply.py by separating
validation concerns.
"""

import ast
import hashlib
import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional, Set, Tuple

logger = logging.getLogger(__name__)


def extract_python_symbols(source: str) -> Set[str]:
    """
    Extract top-level symbols from Python source using AST.

    Per GPT_RESPONSE18 Q5: Extract function and class definitions,
    plus uppercase module-level constants.

    Args:
        source: Python source code

    Returns:
        Set of symbol names (functions, classes, CONSTANTS)
    """
    try:
        tree = ast.parse(source)
        names: Set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        names.add(target.id)
        return names
    except SyntaxError:
        return set()


def validate_patch_syntax(patch: str) -> bool:
    """
    Validate basic patch syntax.

    Args:
        patch: Patch content to validate

    Returns:
        True if patch syntax is valid, False otherwise
    """
    if not patch or not patch.strip():
        return False

    # Check for required patch headers
    has_diff_header = any(line.startswith("diff --git") for line in patch.split("\n"))
    return has_diff_header


def validate_file_exists(file_path: str, workspace: Path) -> bool:
    """
    Validate file exists and is accessible.

    Args:
        file_path: Relative file path to check
        workspace: Workspace root path

    Returns:
        True if file exists and is readable, False otherwise
    """
    try:
        full_path = workspace / file_path
        if not full_path.exists():
            return False
        # Try to read to ensure it's accessible
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            f.read(1)
        return True
    except Exception as e:
        logger.debug(f"File accessibility check failed for {file_path}: {e}")
        return False


def validate_no_conflicts(
    patch: str, current_content: str, file_path: str
) -> Tuple[bool, Optional[str]]:
    """
    Validate patch has no conflicts with current content.

    Checks for merge conflict markers in the file that would indicate
    failed application.

    Args:
        patch: Patch content
        current_content: Current file content
        file_path: Path to file being validated

    Returns:
        Tuple of (is_valid, error_message)
    """
    conflict_markers = ["<<<<<<<", ">>>>>>>"]
    try:
        for line_num, line in enumerate(current_content.split("\n"), 1):
            for marker in conflict_markers:
                if marker in line:
                    error = f"{file_path}:{line_num}: merge conflict marker '{marker}' found"
                    return False, error
        return True, None
    except Exception as e:
        logger.warning(f"Conflict validation failed for {file_path}: {e}")
        return False, str(e)


def check_symbol_preservation(
    old_content: str, new_content: str, max_lost_ratio: float
) -> Tuple[bool, str]:
    """
    Check if too many symbols were lost in the patch.

    Per GPT_RESPONSE18 Q5: Reject if >30% of symbols are lost (configurable).

    Args:
        old_content: Original file content
        new_content: New file content after patch
        max_lost_ratio: Maximum ratio of symbols that can be lost (e.g., 0.3)

    Returns:
        Tuple of (is_valid, error_message)
    """
    old_symbols = extract_python_symbols(old_content)
    new_symbols = extract_python_symbols(new_content)
    lost = old_symbols - new_symbols

    if old_symbols:
        lost_ratio = len(lost) / len(old_symbols)
        if lost_ratio > max_lost_ratio:
            lost_names = ", ".join(sorted(lost)[:10])
            if len(lost) > 10:
                lost_names += f"... (+{len(lost) - 10} more)"
            return False, (
                f"symbol_preservation_violation: Lost {len(lost)}/{len(old_symbols)} symbols "
                f"({lost_ratio:.1%} > {max_lost_ratio:.0%} threshold). "
                f"Lost: [{lost_names}]"
            )

    return True, ""


def check_structural_similarity(
    old_content: str, new_content: str, min_ratio: float
) -> Tuple[bool, str]:
    """
    Check if file was drastically rewritten unexpectedly.

    Per GPT_RESPONSE18 Q6: Reject if structural similarity is <60% (configurable)
    for files >=300 lines.

    Args:
        old_content: Original file content
        new_content: New file content after patch
        min_ratio: Minimum similarity ratio required (e.g., 0.6)

    Returns:
        Tuple of (is_valid, error_message)
    """
    ratio = SequenceMatcher(None, old_content, new_content).ratio()
    if ratio < min_ratio:
        return False, (
            f"structural_similarity_violation: Similarity {ratio:.2f} below threshold {min_ratio}. "
            f"File appears to have been drastically rewritten."
        )

    return True, ""


def compute_file_hash(file_path: Path) -> Optional[str]:
    """Compute SHA256 hash of a file for integrity checking."""
    try:
        if file_path.exists():
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        logger.warning(f"Failed to compute hash for {file_path}: {e}")
    return None


def validate_python_syntax(file_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Validate Python file syntax by attempting to compile it.

    Args:
        file_path: Path to Python file

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not file_path.suffix == ".py":
        return True, None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
        compile(source, str(file_path), "exec")
        return True, None
    except SyntaxError as e:
        error_msg = f"Line {e.lineno}: {e.msg}"
        return False, error_msg
    except Exception as e:
        return False, str(e)


def check_merge_conflict_markers(file_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Check if a file contains git merge conflict markers.

    These markers can be left behind by 3-way merge (-3) fallback when patches
    don't apply cleanly. They cause syntax errors and must be detected early.

    Note: We only check for '<<<<<<<' and '>>>>>>>' as these are unique to
    merge conflicts. '=======' alone is commonly used as a section divider
    in code comments (e.g., # =========) and would cause false positives.

    Args:
        file_path: Path to file to check

    Returns:
        Tuple of (has_conflicts, error_message)
    """
    # Only check for unique conflict markers, not '=======' which is used in comments
    conflict_markers = ["<<<<<<<", ">>>>>>>"]
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line_num, line in enumerate(f, 1):
                for marker in conflict_markers:
                    if marker in line:
                        return True, f"Line {line_num}: merge conflict marker '{marker}' found"
        return False, None
    except Exception as e:
        logger.warning(f"Failed to check merge conflicts in {file_path}: {e}")
        return False, None


def validate_json_file(file_path: Path) -> Tuple[bool, Optional[str]]:
    """Validate JSON file syntax."""
    try:
        import json

        with open(file_path, "r", encoding="utf-8") as f:
            json.load(f)
        return True, None
    except Exception as e:
        return False, f"Invalid JSON: {e}"


def validate_yaml_file(file_path: Path) -> Tuple[bool, Optional[str]]:
    """Validate YAML file syntax."""
    try:
        import yaml

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Allow leading comments without explicit document start by prepending '---'
        stripped = content.lstrip()
        if stripped.startswith("#") and not stripped.startswith("---"):
            content = "---\n" + content
        yaml.safe_load(content)
        return True, None
    except Exception as e:
        return False, f"Invalid YAML: {e}"
