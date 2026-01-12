"""Patch quality validation functions.

Extracted from governed_apply.py for PR-APPLY-3.

This module handles:
- Patch quality validation (truncation detection, malformed hunks)
- Content change validation (symbol preservation, structural similarity)
- File syntax validation (Python, JSON, YAML)
- Merge conflict marker detection
- Pack schema validation
"""

from __future__ import annotations

import ast
import hashlib
import logging
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# SYMBOL EXTRACTION AND VALIDATION (per GPT_RESPONSE18 Q5/Q6)
# =============================================================================


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


# =============================================================================
# PATCH QUALITY VALIDATION
# =============================================================================


def validate_patch_quality(patch_content: str) -> List[str]:
    """
    Validate patch quality to detect LLM truncation/abbreviation issues.

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    lines = patch_content.split("\n")

    # Check for ellipsis/truncation markers (CRITICAL: LLMs use these when hitting token limits)
    # Be careful NOT to flag legitimate code like logger.info("...") or f-strings
    truncation_patterns = [
        r"^\+\s*\.\.\.\s*$",  # Line that is ONLY "..."
        r"^\+\s*#\s*\.\.\.\s*$",  # Comment line that is only "# ..."
        r"^\+.*\.\.\.\s*more\s+code",  # "... more code" pattern
        r"^\+.*\.\.\.\s*rest\s+of",  # "... rest of" pattern
        r"^\+.*\.\.\.\s*continues",  # "... continues" pattern
        r"^\+.*\.\.\.\s*etc",  # "... etc" pattern
        r"^\+.*code\s+omitted\s*\.\.\.",  # "code omitted..." pattern
    ]

    for i, line in enumerate(lines, 1):
        # Skip comment lines, docstrings, and strings (... is ok there)
        stripped = line.strip()
        if stripped.startswith(("#", '"""', "'''")):
            continue
        # Skip lines with ... inside strings (legitimate code)
        if '("' in line or "('" in line or 'f"' in line or "f'" in line:
            continue

        for pattern in truncation_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                errors.append(f"Line {i} contains truncation/ellipsis '...': {line[:80]}")
                break

    # Check for malformed hunk headers (common LLM error)
    # Valid unified diff allows omitted counts when they are 1: @@ -1 +1 @@
    hunk_header_pattern = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")
    for i, line in enumerate(lines, 1):
        if line.startswith("@@"):
            match = hunk_header_pattern.match(line)
            if not match:
                errors.append(f"Line {i} has malformed hunk header: {line[:80]}")
            else:
                # Validate line counts make sense
                groups = match.groups()
                old_count = int(groups[1]) if groups[1] else 1
                new_count = int(groups[3]) if groups[3] else 1
                if old_count == 0 and new_count == 0:
                    errors.append(f"Line {i} has zero-length hunk (invalid): {line[:80]}")

    # Check for incomplete diff structure
    if "diff --git" in patch_content:
        has_index = "index " in patch_content
        has_minus = "---" in patch_content
        has_plus = "+++" in patch_content

        if not (has_index and has_minus and has_plus):
            errors.append("Incomplete diff structure (missing index/---/+++ lines)")

    # Check for truncated file content (common LLM issue - output cut off mid-file)
    truncation_errors = detect_truncated_content(patch_content)
    errors.extend(truncation_errors)

    return errors


def detect_truncated_content(patch_content: str) -> List[str]:
    """
    Detect truncated file content in patches - catches LLM output that was cut off.

    Common patterns:
    - File ends with unclosed quote (started " or ' but never closed)
    - YAML file ends mid-list without proper structure
    - File ends with "No newline at end of file" after incomplete content

    Returns:
        List of truncation error messages
    """
    errors = []
    lines = patch_content.split("\n")

    # Track files being patched and their new content (only meaningful for NEW files)
    current_file = None
    new_file_lines: List[str] = []
    in_new_file = False

    for i, line in enumerate(lines):
        if line.startswith("diff --git"):
            # Check previous file for truncation before moving to next
            if current_file and new_file_lines:
                file_errors = check_file_truncation(current_file, new_file_lines)
                errors.extend(file_errors)

            # Extract new file path
            match = re.search(r"diff --git a/.+ b/(.+)", line)
            if match:
                current_file = match.group(1)
            new_file_lines = []
            in_new_file = False

        elif line.startswith("--- /dev/null"):
            in_new_file = True

        elif in_new_file and line.startswith("+") and not line.startswith("+++"):
            # Collect added lines ONLY for new files.
            # For modified files, diff hunks do not represent full file content, so truncation
            # heuristics (like "file ends with unclosed quote") would create false positives.
            new_file_lines.append(line[1:])  # Remove + prefix

        elif line.startswith("\\ No newline at end of file"):
            # This marker after minimal content is suspicious. For JSON/package files we tolerate short bodies.
            if len(new_file_lines) < 5 and not (current_file or "").endswith("package.json"):
                errors.append(
                    f"File '{current_file}' appears truncated (only {len(new_file_lines)} lines before 'No newline')"
                )

    # Check last file
    if current_file and new_file_lines:
        file_errors = check_file_truncation(current_file, new_file_lines)
        errors.extend(file_errors)

    return errors


def check_file_truncation(file_path: str, content_lines: List[str]) -> List[str]:
    """Check a single file's content for truncation indicators."""
    errors = []

    # Check for unclosed quotes at end of file
    if content_lines:
        last_line = content_lines[-1].rstrip()
        # Check if last line has unclosed double quote
        if last_line.count('"') % 2 == 1:
            errors.append(f"File '{file_path}' ends with unclosed quote: '{last_line[-50:]}'")
        # Check if last line has unclosed single quote (but not apostrophes)
        if "'" in last_line and last_line.count("'") % 2 == 1:
            # Filter out common apostrophe usage
            if not re.search(r"\w'\w", last_line):  # e.g., "don't", "it's"
                errors.append(
                    f"File '{file_path}' may end with unclosed quote: '{last_line[-50:]}'"
                )

    # For YAML files, check for incomplete structure
    if file_path.endswith((".yaml", ".yml")):
        yaml_errors = check_yaml_truncation(file_path, content_lines)
        errors.extend(yaml_errors)

    return errors


def check_yaml_truncation(file_path: str, content_lines: List[str]) -> List[str]:
    """Check YAML content for truncation indicators."""
    errors = []

    if not content_lines:
        return errors

    # Check if file ends abruptly mid-list item
    last_line = content_lines[-1].rstrip()
    if last_line.strip().startswith("-") and last_line.strip() == "-":
        errors.append(f"YAML file '{file_path}' ends with empty list marker")

    # Check for incomplete list item (just "- " with nothing after)
    if re.match(r"^\s*-\s*$", last_line):
        errors.append(f"YAML file '{file_path}' ends with incomplete list item")

    # Check for unclosed multi-line string indicator
    for i, line in enumerate(content_lines[-5:], len(content_lines) - 4):
        if line.rstrip().endswith("|") or line.rstrip().endswith(">"):
            # Multi-line string started but file ends soon after
            remaining = len(content_lines) - i - 1
            if remaining < 2:
                errors.append(
                    f"YAML file '{file_path}' ends shortly after multi-line string indicator"
                )

    # Try to parse as YAML to catch structural issues
    try:
        import yaml

        content = "\n".join(content_lines)
        # Lenient handling: if YAML starts with comments and no document marker, prepend '---'
        stripped = content.lstrip()
        if stripped.startswith("#") and not stripped.startswith("---"):
            content = "---\n" + content
        yaml.safe_load(content)
    except yaml.YAMLError as e:
        # Only report if it looks like truncation (not just any YAML error)
        error_str = str(e).lower()
        if "end of stream" in error_str or "expected" in error_str:
            errors.append(f"YAML file '{file_path}' has incomplete structure: {str(e)[:100]}")
    except ImportError:
        pass  # yaml not available

    return errors


# =============================================================================
# FILE SYNTAX VALIDATION
# =============================================================================


def validate_python_syntax(file_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Validate Python file syntax by attempting to compile it.

    Args:
        file_path: Path to Python file

    Returns:
        Tuple of (is_valid, error_message)
    """
    if file_path.suffix != ".py":
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


def validate_json_syntax(file_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Validate JSON file syntax.

    Args:
        file_path: Path to JSON file

    Returns:
        Tuple of (is_valid, error_message)
    """
    if file_path.suffix != ".json":
        return True, None

    try:
        import json

        with open(file_path, "r", encoding="utf-8") as f:
            json.load(f)
        return True, None
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON: {e}"
    except Exception as e:
        return False, str(e)


def validate_yaml_syntax(file_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Validate YAML file syntax.

    Args:
        file_path: Path to YAML file

    Returns:
        Tuple of (is_valid, error_message)
    """
    if file_path.suffix not in [".yaml", ".yml"]:
        return True, None

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
    except yaml.YAMLError as e:
        return False, f"Invalid YAML: {e}"
    except ImportError:
        return True, None  # yaml not available, skip validation
    except Exception as e:
        return False, str(e)


def validate_applied_files(workspace: Path, files_modified: List[str]) -> Tuple[bool, List[str]]:
    """
    Verify files are syntactically valid after patch application.

    This is a critical self-troubleshoot check that detects corruption
    immediately after any file modification.

    Args:
        workspace: Path to workspace root
        files_modified: List of relative file paths that were modified

    Returns:
        Tuple of (all_valid, list_of_corrupted_files)
    """
    corrupted_files = []

    for rel_path in files_modified:
        full_path = workspace / rel_path

        if not full_path.exists():
            logger.warning(f"[Validation] File does not exist after patch: {rel_path}")
            continue

        # Check for merge conflict markers (critical - prevents API crashes)
        has_conflicts, conflict_error = check_merge_conflict_markers(full_path)
        if has_conflicts:
            logger.error(f"[Validation] MERGE CONFLICTS: {rel_path} - {conflict_error}")
            corrupted_files.append(rel_path)
            continue  # Skip other validations - file is definitely corrupted

        # Validate Python files
        if full_path.suffix == ".py":
            is_valid, error = validate_python_syntax(full_path)
            if not is_valid:
                logger.error(f"[Validation] CORRUPTED: {rel_path} - {error}")
                corrupted_files.append(rel_path)
            else:
                logger.debug(f"[Validation] OK: {rel_path}")

        # Validate JSON files
        elif full_path.suffix == ".json":
            is_valid, error = validate_json_syntax(full_path)
            if not is_valid:
                logger.error(f"[Validation] CORRUPTED: {rel_path} - {error}")
                corrupted_files.append(rel_path)
            else:
                logger.debug(f"[Validation] OK: {rel_path}")

        # Validate YAML files
        elif full_path.suffix in [".yaml", ".yml"]:
            is_valid, error = validate_yaml_syntax(full_path)
            if not is_valid:
                logger.error(f"[Validation] CORRUPTED: {rel_path} - {error}")
                corrupted_files.append(rel_path)
            else:
                logger.debug(f"[Validation] OK: {rel_path}")

    if corrupted_files:
        logger.error(f"[Validation] {len(corrupted_files)} files corrupted after patch application")
        return False, corrupted_files

    logger.info(f"[Validation] All {len(files_modified)} modified files validated successfully")
    return True, []


# =============================================================================
# CONTENT CHANGE VALIDATION
# =============================================================================


def validate_content_changes(
    workspace: Path,
    files_modified: List[str],
    backups: Dict[str, Tuple[str, str]],
    validation_config: Optional[Dict] = None,
) -> Tuple[bool, List[str]]:
    """
    Validate content changes using symbol preservation and structural similarity.

    Per GPT_RESPONSE18 Q5/Q6: Post-apply validation that checks:
    - Python files: symbol preservation (≤30% loss allowed)
    - Large files (≥300 lines): structural similarity (≥60% required)

    Args:
        workspace: Path to workspace root
        files_modified: List of relative file paths that were modified
        backups: Dict mapping file path to (hash, content) tuple
        validation_config: Optional config dict with thresholds

    Returns:
        Tuple of (all_valid, list of files with issues)
    """
    # Load validation config from models.yaml or use defaults
    if validation_config is None:
        try:
            import yaml

            config_path = Path(__file__).parent.parent.parent.parent / "config" / "models.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    models_config = yaml.safe_load(f)
                    validation_config = models_config.get("validation", {})
            else:
                validation_config = {}
        except Exception as e:
            logger.debug(f"[Validation] Could not load validation config: {e}")
            validation_config = {}

    # Get thresholds from config
    symbol_config = validation_config.get("symbol_preservation", {})
    symbol_enabled = symbol_config.get("enabled", True)
    max_lost_ratio = symbol_config.get("max_lost_ratio", 0.3)

    similarity_config = validation_config.get("structural_similarity", {})
    similarity_enabled = similarity_config.get("enabled", True)
    min_ratio = similarity_config.get("min_ratio", 0.6)
    min_lines_for_check = similarity_config.get("min_lines_for_check", 300)

    problem_files = []

    for rel_path in files_modified:
        full_path = workspace / rel_path

        # Skip if file doesn't exist (was deleted) or no backup
        if not full_path.exists() or rel_path not in backups:
            continue

        # Get old content from backup
        _, old_content = backups[rel_path]

        # Read new content
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                new_content = f.read()
        except Exception as e:
            logger.warning(f"[Validation] Failed to read {rel_path}: {e}")
            continue

        old_line_count = old_content.count("\n") + 1

        # Check 1: Symbol preservation for Python files
        if symbol_enabled and full_path.suffix == ".py":
            is_valid, error = check_symbol_preservation(old_content, new_content, max_lost_ratio)
            if not is_valid:
                logger.warning(f"[Validation] SYMBOL_LOSS: {rel_path} - {error}")
                problem_files.append(rel_path)
                continue  # Skip further checks for this file

        # Check 2: Structural similarity for large files
        if similarity_enabled and old_line_count >= min_lines_for_check:
            is_valid, error = check_structural_similarity(old_content, new_content, min_ratio)
            if not is_valid:
                logger.warning(f"[Validation] SIMILARITY_LOW: {rel_path} - {error}")
                problem_files.append(rel_path)
                continue

    if problem_files:
        logger.warning(
            f"[Validation] {len(problem_files)} files have content validation issues: "
            f"{', '.join(problem_files[:5])}"
            + (f" (+{len(problem_files) - 5} more)" if len(problem_files) > 5 else "")
        )
        return False, problem_files

    return True, []


# =============================================================================
# FILE BACKUP AND INTEGRITY
# =============================================================================


def compute_file_hash(file_path: Path) -> Optional[str]:
    """Compute SHA256 hash of a file for integrity checking."""
    try:
        if file_path.exists():
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        logger.warning(f"Failed to compute hash for {file_path}: {e}")
    return None


def backup_files(workspace: Path, file_paths: List[str]) -> Dict[str, Tuple[str, str]]:
    """
    Create in-memory backups of files before modification.

    Args:
        workspace: Path to workspace root
        file_paths: List of relative file paths to backup

    Returns:
        Dict mapping file path to (hash, content) tuple
    """
    backups: Dict[str, Tuple[str, str]] = {}
    for rel_path in file_paths:
        full_path = workspace / rel_path
        if full_path.exists():
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                file_hash = hashlib.sha256(content.encode()).hexdigest()
                backups[rel_path] = (file_hash, content)
                logger.debug(f"Backed up {rel_path} (hash: {file_hash[:12]}...)")
            except Exception as e:
                logger.warning(f"Failed to backup {rel_path}: {e}")
    return backups


def restore_file(workspace: Path, rel_path: str, backup: Tuple[str, str]) -> bool:
    """
    Restore a file from backup.

    Args:
        workspace: Path to workspace root
        rel_path: Relative file path
        backup: Tuple of (hash, content)

    Returns:
        True if restoration succeeded
    """
    _, content = backup
    full_path = workspace / rel_path
    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"[Integrity] Restored {rel_path} from backup")
        return True
    except Exception as e:
        logger.error(f"[Integrity] Failed to restore {rel_path}: {e}")
        return False


# =============================================================================
# PACK SCHEMA VALIDATION
# =============================================================================


def validate_pack_schema(file_path: str, content: str) -> List[str]:
    """
    Validate a country pack YAML against a minimal schema:
    - Required top-level keys: name, description, version, country, domain, categories, checklists, official_sources
    - categories: non-empty list, no duplicate names, each with name/description/examples
    - checklists: non-empty list, each with name/required_documents
    - official_sources: non-empty list
    """
    try:
        import yaml
    except ImportError:
        return []

    required_keys = [
        "name",
        "description",
        "version",
        "country",
        "domain",
        "categories",
        "checklists",
        "official_sources",
    ]
    errors: List[str] = []

    try:
        content_to_load = content
        stripped = content.lstrip()
        # Always provide a document start for validation to avoid PyYAML expecting one.
        if not stripped.startswith("---"):
            content_to_load = "---\n" + content
        data = yaml.safe_load(content_to_load)
    except Exception as e:
        errors.append(f"Pack schema: YAML parse failed for {file_path}: {e}")
        return errors

    if not isinstance(data, dict):
        errors.append(f"Pack schema: Expected mapping at top level for {file_path}")
        return errors

    for key in required_keys:
        if key not in data or data.get(key) in ("", None):
            errors.append(f"Pack schema: Missing required key '{key}' in {file_path}")

    categories = data.get("categories", [])
    if not isinstance(categories, list) or not categories:
        errors.append(f"Pack schema: 'categories' must be a non-empty list in {file_path}")
    else:
        seen: Set[str] = set()
        for cat in categories:
            if not isinstance(cat, dict):
                errors.append(f"Pack schema: category entry is not a mapping in {file_path}")
                continue
            name = cat.get("name")
            if not name or not isinstance(name, str):
                errors.append(f"Pack schema: category missing 'name' in {file_path}")
            elif name in seen:
                errors.append(f"Pack schema: duplicate category name '{name}' in {file_path}")
            else:
                seen.add(name)
            if not cat.get("description"):
                errors.append(
                    f"Pack schema: category '{name or '?'}' missing description in {file_path}"
                )
            examples = cat.get("examples", [])
            if not isinstance(examples, list) or not examples:
                errors.append(
                    f"Pack schema: category '{name or '?'}' missing examples list in {file_path}"
                )

    checklists = data.get("checklists", [])
    if not isinstance(checklists, list) or not checklists:
        errors.append(f"Pack schema: 'checklists' must be a non-empty list in {file_path}")
    else:
        for cl in checklists:
            if not isinstance(cl, dict):
                errors.append(f"Pack schema: checklist entry is not a mapping in {file_path}")
                continue
            if not cl.get("name"):
                errors.append(f"Pack schema: checklist missing 'name' in {file_path}")
            reqs = cl.get("required_documents", [])
            if not isinstance(reqs, list) or not reqs:
                errors.append(
                    f"Pack schema: checklist '{cl.get('name','?')}' missing required_documents list in {file_path}"
                )

    sources = data.get("official_sources", [])
    if not isinstance(sources, list) or not sources:
        errors.append(f"Pack schema: 'official_sources' must be a non-empty list in {file_path}")

    return errors
