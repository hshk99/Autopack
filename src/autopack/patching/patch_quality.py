"""Patch quality validation for Autopack.

Extracted from governed_apply.py as part of Item 1.1 god file refactoring (PR-APPLY-3).

This module provides patch quality validation to detect LLM truncation and abbreviation
issues that can cause patch application failures.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class QualityIssue:
    """Represents a patch quality issue."""

    severity: str  # "warning" or "error"
    message: str
    line_number: Optional[int] = None


@dataclass
class QualityValidationResult:
    """Result of patch quality validation."""

    valid: bool
    issues: List[QualityIssue] = field(default_factory=list)
    score: float = 1.0  # 0.0-1.0, quality score


def validate_patch_quality(
    patch_content: str, strict_mode: bool = False
) -> QualityValidationResult:
    """Validate patch quality against heuristics.

    Detects common LLM issues:
    - Truncation markers (ellipsis, "... more code", etc.)
    - Malformed hunk headers
    - Incomplete diff structure
    - Truncated file content (unclosed quotes, incomplete YAML)

    Args:
        patch_content: Unified diff patch content
        strict_mode: If True, apply stricter validation rules

    Returns:
        QualityValidationResult with issues found
    """
    if not patch_content or not patch_content.strip():
        return QualityValidationResult(
            valid=False,
            issues=[QualityIssue(severity="error", message="Empty patch content")],
            score=0.0,
        )

    issues: List[QualityIssue] = []
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
                issues.append(
                    QualityIssue(
                        severity="error",
                        message=f"Contains truncation/ellipsis '...': {line[:80]}",
                        line_number=i,
                    )
                )
                break

    # Check for malformed hunk headers (common LLM error)
    # Valid unified diff allows omitted counts when they are 1: @@ -1 +1 @@
    hunk_header_pattern = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")
    for i, line in enumerate(lines, 1):
        if line.startswith("@@"):
            match = hunk_header_pattern.match(line)
            if not match:
                issues.append(
                    QualityIssue(
                        severity="error",
                        message=f"Malformed hunk header: {line[:80]}",
                        line_number=i,
                    )
                )
            else:
                # Validate line counts make sense
                groups = match.groups()
                _old_start = int(groups[0])
                old_count = int(groups[1]) if groups[1] else 1
                _new_start = int(groups[2])
                new_count = int(groups[3]) if groups[3] else 1

                if old_count == 0 and new_count == 0:
                    issues.append(
                        QualityIssue(
                            severity="error",
                            message=f"Zero-length hunk (invalid): {line[:80]}",
                            line_number=i,
                        )
                    )

    # Check for incomplete diff structure
    if "diff --git" in patch_content:
        has_index = "index " in patch_content
        has_minus = "---" in patch_content
        has_plus = "+++" in patch_content

        if not (has_index and has_minus and has_plus):
            issues.append(
                QualityIssue(
                    severity="error",
                    message="Incomplete diff structure (missing index/---/+++ lines)",
                )
            )

    # Check for truncated file content (common LLM issue - output cut off mid-file)
    truncation_issues = _detect_truncated_content(patch_content)
    issues.extend(truncation_issues)

    # In strict mode, apply additional checks
    if strict_mode:
        # Check for large hunks that might indicate over-modification
        for i, line in enumerate(lines, 1):
            if line.startswith("@@"):
                match = hunk_header_pattern.match(line)
                if match:
                    groups = match.groups()
                    new_count = int(groups[3]) if groups[3] else 1
                    # Flag hunks with >100 lines as potentially problematic in strict mode
                    if new_count > 100:
                        issues.append(
                            QualityIssue(
                                severity="warning",
                                message=f"Large hunk ({new_count} lines) - review carefully",
                                line_number=i,
                            )
                        )

    # Calculate quality score
    score = 1.0
    error_count = len([issue for issue in issues if issue.severity == "error"])
    warning_count = len([issue for issue in issues if issue.severity == "warning"])

    if error_count > 0:
        score = 0.0
    elif warning_count > 0:
        score = max(0.5, 1.0 - (warning_count * 0.1))

    valid = error_count == 0

    return QualityValidationResult(valid=valid, issues=issues, score=score)


def _detect_truncated_content(patch_content: str) -> List[QualityIssue]:
    """Detect truncated file content in patches - catches LLM output that was cut off.

    Common patterns:
    - File ends with unclosed quote (started " or ' but never closed)
    - YAML file ends mid-list without proper structure
    - File ends with "No newline at end of file" after incomplete content

    Args:
        patch_content: Patch content to analyze

    Returns:
        List of quality issues related to truncation
    """
    issues: List[QualityIssue] = []
    lines = patch_content.split("\n")

    # Track files being patched and their new content (only meaningful for NEW files)
    current_file = None
    new_file_lines: List[str] = []
    in_new_file = False

    for i, line in enumerate(lines):
        if line.startswith("diff --git"):
            # Check previous file for truncation before moving to next
            if current_file and new_file_lines:
                file_issues = _check_file_truncation(current_file, new_file_lines)
                issues.extend(file_issues)

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
                issues.append(
                    QualityIssue(
                        severity="warning",
                        message=f"File '{current_file}' appears truncated (only {len(new_file_lines)} lines before 'No newline')",
                    )
                )

    # Check last file
    if current_file and new_file_lines:
        file_issues = _check_file_truncation(current_file, new_file_lines)
        issues.extend(file_issues)

    return issues


def _check_file_truncation(file_path: str, content_lines: List[str]) -> List[QualityIssue]:
    """Check a single file's content for truncation indicators.

    Args:
        file_path: File path being checked
        content_lines: Lines of file content (without + prefix)

    Returns:
        List of quality issues found
    """
    issues: List[QualityIssue] = []

    # Pattern: line ending with unclosed quote (started " but not closed)
    if content_lines:
        last_line = content_lines[-1].rstrip()
        # Check if last line has unclosed double quote
        if last_line.count('"') % 2 == 1:
            issues.append(
                QualityIssue(
                    severity="error",
                    message=f"File '{file_path}' ends with unclosed quote: '{last_line[-50:]}'",
                )
            )
        # Check if last line has unclosed single quote (but not apostrophes)
        if "'" in last_line and last_line.count("'") % 2 == 1:
            # Filter out common apostrophe usage
            if not re.search(r"\w'\w", last_line):  # e.g., "don't", "it's"
                issues.append(
                    QualityIssue(
                        severity="warning",
                        message=f"File '{file_path}' may end with unclosed quote: '{last_line[-50:]}'",
                    )
                )

    # For YAML files, check for incomplete structure
    if file_path.endswith((".yaml", ".yml")):
        yaml_issues = _check_yaml_truncation(file_path, content_lines)
        issues.extend(yaml_issues)

    return issues


def _check_yaml_truncation(file_path: str, content_lines: List[str]) -> List[QualityIssue]:
    """Check YAML content for truncation indicators.

    Args:
        file_path: File path being checked
        content_lines: Lines of YAML content

    Returns:
        List of quality issues found
    """
    issues: List[QualityIssue] = []

    if not content_lines:
        return issues

    # Check if file ends abruptly mid-list item
    last_line = content_lines[-1].rstrip()
    if last_line.strip().startswith("-") and last_line.strip() == "-":
        issues.append(
            QualityIssue(
                severity="error", message=f"YAML file '{file_path}' ends with empty list marker"
            )
        )

    # Check for incomplete list item (just "- " with nothing after)
    if re.match(r"^\s*-\s*$", last_line):
        issues.append(
            QualityIssue(
                severity="error",
                message=f"YAML file '{file_path}' ends with incomplete list item",
            )
        )

    # Check for unclosed multi-line string indicator
    for i in range(max(0, len(content_lines) - 5), len(content_lines)):
        line = content_lines[i]
        if line.rstrip().endswith("|") or line.rstrip().endswith(">"):
            # Multi-line string started but file ends soon after
            remaining = len(content_lines) - i - 1
            if remaining <= 1:  # Changed from < 2 to <= 1 to catch cases with only 1 or 0 lines after
                issues.append(
                    QualityIssue(
                        severity="error",
                        message=f"YAML file '{file_path}' ends shortly after multi-line string indicator",
                    )
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
            issues.append(
                QualityIssue(
                    severity="error",
                    message=f"YAML file '{file_path}' has incomplete structure: {str(e)[:100]}",
                )
            )

    return issues
