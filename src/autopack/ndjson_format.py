"""
NDJSON Structured-Edit Format for BUILD-129 Phase 3.

Implements truncation-tolerant output format using Newline-Delimited JSON.

Per TOKEN_BUDGET_ANALYSIS_REVISED.md Layer 3:
"Current formats (monolithic diff, single JSON object) are catastrophically fragile
under truncation. A single truncation ruins 100% of output. NDJSON makes each line
a complete JSON object, so only the last incomplete line is lost."

GPT-5.2 Priority: HIGH - prevents catastrophic JSON parse failures under truncation.
"""
import json
import logging
import ast
import re
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class NDJSONOperation:
    """Single NDJSON operation."""

    op_type: str  # "create", "modify", "delete", "meta"
    file_path: Optional[str]  # None for meta operations
    content: Optional[str]  # Full content for create operations
    operations: Optional[List[Dict]]  # Sub-operations for modify operations
    metadata: Optional[Dict]  # Additional metadata (for meta type)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        result = {"type": self.op_type}

        if self.file_path:
            result["file_path"] = self.file_path
        if self.content is not None:
            result["content"] = self.content
        if self.operations:
            result["operations"] = self.operations
        if self.metadata:
            result.update(self.metadata)

        return result


@dataclass
class NDJSONParseResult:
    """Result of NDJSON parsing."""

    operations: List[NDJSONOperation]
    was_truncated: bool  # True if last line was incomplete JSON
    total_expected: Optional[int]  # From meta line, if present
    lines_parsed: int
    lines_failed: int


class NDJSONParser:
    """
    Parser for NDJSON structured-edit format.

    Format Specification (from TOKEN_BUDGET_ANALYSIS_REVISED.md):
    - Each line is a complete JSON object
    - First line (optional): {"type": "meta", "summary": "...", "total_operations": N}
    - Subsequent lines: Operation objects (create, modify, delete)
    - Truncation tolerance: Only last incomplete line is lost

    Example:
        {"type": "meta", "summary": "Implement feature X", "total_operations": 5}
        {"type": "create", "file_path": "src/foo.py", "content": "def foo():\\n    pass"}
        {"type": "modify", "file_path": "src/bar.py", "operations": [...]}
        {"type": "create", "file_path": "tests/test_foo.py", "content": "..."}
    """

    def __init__(self):
        """Initialize parser."""
        pass

    def parse(self, output: str) -> NDJSONParseResult:
        """
        Parse NDJSON output.

        Args:
            output: Raw NDJSON output from LLM

        Returns:
            NDJSONParseResult with parsed operations and truncation status
        """
        lines = output.strip().split('\n')
        operations = []
        total_expected = None
        was_truncated = False
        lines_parsed = 0
        lines_failed = 0
        failed_examples: List[Tuple[int, str, str]] = []  # (line_num, snippet, error)

        logger.info(f"[NDJSON:Parse] Parsing {len(lines)} lines")

        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue  # Skip empty lines

            # Be tolerant of models that add prose/markdown around NDJSON.
            # Only attempt JSON parsing for lines that plausibly start a JSON value.
            if not (line.startswith("{") or line.startswith("[")):
                continue

            try:
                obj = json.loads(line)
                lines_parsed += 1

                # Handle meta line
                if obj.get("type") == "meta":
                    total_expected = obj.get("total_operations")
                    logger.info(
                        f"[NDJSON:Parse] Meta line: total_operations={total_expected}, "
                        f"summary={obj.get('summary', 'N/A')[:50]}"
                    )
                    continue

                # Parse operation
                op = self._parse_operation(obj, i + 1)
                if op:
                    operations.append(op)

            except json.JSONDecodeError as e:
                # Some models emit Python-literal dicts/lists (single quotes) instead of strict JSON.
                # Try to salvage via ast.literal_eval on a per-line basis.
                salvaged = False
                try:
                    candidate = line
                    # Common when models emit Python list elements: "{...}," at EOL
                    if candidate.endswith(","):
                        candidate = candidate[:-1]
                    lit = ast.literal_eval(candidate)
                    if isinstance(lit, (dict, list)):
                        obj = lit
                        salvaged = True
                except Exception:
                    salvaged = False

                # As a last resort, try to coerce "loose JSON" to valid JSON:
                # - unquoted keys: {type: 'meta'} -> {"type": "meta"}
                # - python literals: True/False/None -> true/false/null
                # - single quotes -> double quotes (best-effort)
                if not salvaged:
                    try:
                        candidate = line.strip()
                        if candidate.endswith(","):
                            candidate = candidate[:-1]
                        candidate = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', candidate)
                        # Replace Python literals with JSON literals
                        candidate = re.sub(r"\bTrue\b", "true", candidate)
                        candidate = re.sub(r"\bFalse\b", "false", candidate)
                        candidate = re.sub(r"\bNone\b", "null", candidate)
                        # If there are no double-quotes at all, assume single quotes are used for strings.
                        if '"' not in candidate and "'" in candidate:
                            candidate = candidate.replace("'", '"')
                        obj2 = json.loads(candidate)
                        obj = obj2
                        salvaged = True
                    except Exception:
                        salvaged = False

                if salvaged:
                    lines_parsed += 1
                    # Handle meta line
                    if isinstance(obj, dict) and obj.get("type") == "meta":
                        total_expected = obj.get("total_operations")
                        logger.info(
                            f"[NDJSON:Parse] Meta line: total_operations={total_expected}, "
                            f"summary={str(obj.get('summary', 'N/A'))[:50]}"
                        )
                        continue
                    if isinstance(obj, dict):
                        op = self._parse_operation(obj, i + 1)
                        if op:
                            operations.append(op)
                    continue

                lines_failed += 1
                if len(failed_examples) < 5:
                    failed_examples.append((i + 1, line[:160], str(e)))

                # Last line truncated?
                if i == len(lines) - 1:
                    was_truncated = True
                    logger.warning(
                        f"[NDJSON:Parse] Last line (#{i+1}) truncated mid-JSON: {e}. "
                        f"Successfully parsed {len(operations)} operations."
                    )
                else:
                    # Mid-output parse failure is unexpected, but can happen when models emit non-JSON objects.
                    # We keep a small sample and log it once at the end to avoid spamming logs.
                    pass

        logger.info(
            f"[NDJSON:Parse] Complete: {lines_parsed} lines parsed, {lines_failed} failed, "
            f"{len(operations)} operations extracted, truncated={was_truncated}"
        )
        if lines_failed and not operations and failed_examples:
            logger.error(
                "[NDJSON:Parse] No operations extracted; sample failed lines: "
                + " | ".join([f"#{ln}:{err}::{snip}" for (ln, snip, err) in failed_examples])
            )

        return NDJSONParseResult(
            operations=operations,
            was_truncated=was_truncated,
            total_expected=total_expected,
            lines_parsed=lines_parsed,
            lines_failed=lines_failed
        )

    def _parse_operation(self, obj: Dict, line_num: int) -> Optional[NDJSONOperation]:
        """Parse a single operation object."""
        op_type = obj.get("type")

        if not op_type:
            logger.warning(f"[NDJSON:Parse] Line #{line_num} missing 'type' field")
            return None

        if op_type == "create":
            return NDJSONOperation(
                op_type="create",
                file_path=obj.get("file_path"),
                content=obj.get("content"),
                operations=None,
                metadata=None
            )
        elif op_type == "modify":
            return NDJSONOperation(
                op_type="modify",
                file_path=obj.get("file_path"),
                content=None,
                operations=obj.get("operations", []),
                metadata=None
            )
        elif op_type == "delete":
            return NDJSONOperation(
                op_type="delete",
                file_path=obj.get("file_path"),
                content=None,
                operations=None,
                metadata=None
            )
        else:
            logger.warning(f"[NDJSON:Parse] Line #{line_num} has unknown type '{op_type}'")
            return None

    def format_for_prompt(self, deliverables: List[str], summary: str) -> str:
        """
        Generate NDJSON format instruction for Builder prompt.

        Args:
            deliverables: List of deliverables to generate
            summary: Summary of the changes

        Returns:
            Formatted prompt section requesting NDJSON output
        """
        return f"""
**OUTPUT FORMAT: NDJSON (Newline-Delimited JSON)**

Generate output in NDJSON format - one complete JSON object per line.

First line (meta):
{{"type": "meta", "summary": "{summary}", "total_operations": {len(deliverables)}}}

Subsequent lines (one operation per line):
{{"type": "create", "file_path": "path/to/file.py", "content": "full file content here"}}
{{"type": "modify", "file_path": "path/to/existing.py", "operations": [{{"type": "insert_after", "anchor": "import os", "content": "import sys"}}]}}

**CRITICAL RULES**:
1. Each line MUST be a complete, valid JSON object
2. NO line breaks within JSON objects (use \\n for newlines in content)
3. Each operation on its own line
4. Format: meta line first, then operation lines
5. Do NOT use a JSON array wrapper - each line is independent

Example (3 operations):
{{"type": "meta", "summary": "Add user service", "total_operations": 3}}
{{"type": "create", "file_path": "src/user_service.py", "content": "class UserService:\\n    def __init__(self):\\n        pass"}}
{{"type": "create", "file_path": "tests/test_user_service.py", "content": "import pytest\\nfrom src.user_service import UserService\\n\\ndef test_init():\\n    service = UserService()\\n    assert service is not None"}}
{{"type": "modify", "file_path": "src/main.py", "operations": [{{"type": "append", "content": "\\nfrom src.user_service import UserService"}}]}}
""".strip()


class NDJSONApplier:
    """
    Applier for NDJSON operations.

    Applies operations incrementally - if truncation occurs, all complete
    operations are still applied successfully.
    """

    def __init__(self, workspace: Path):
        """Initialize applier with workspace root."""
        self.workspace = workspace

    def apply(self, operations: List[NDJSONOperation]) -> Dict:
        """
        Apply NDJSON operations incrementally.

        Args:
            operations: List of parsed operations

        Returns:
            Dict with applied/failed counts and details
        """
        applied = []
        failed = []

        logger.info(f"[NDJSON:Apply] Applying {len(operations)} operations")

        for i, op in enumerate(operations):
            try:
                if op.op_type == "create":
                    self._apply_create(op)
                    applied.append(op.file_path)
                    logger.debug(f"[NDJSON:Apply] Created {op.file_path}")

                elif op.op_type == "modify":
                    self._apply_modify(op)
                    applied.append(op.file_path)
                    logger.debug(f"[NDJSON:Apply] Modified {op.file_path}")

                elif op.op_type == "delete":
                    self._apply_delete(op)
                    applied.append(op.file_path)
                    logger.debug(f"[NDJSON:Apply] Deleted {op.file_path}")

            except Exception as e:
                failed.append({
                    "operation_index": i,
                    "file_path": op.file_path,
                    "error": str(e)
                })
                logger.error(
                    f"[NDJSON:Apply] Failed to apply operation #{i} ({op.op_type} {op.file_path}): {e}"
                )

        logger.info(
            f"[NDJSON:Apply] Complete: {len(applied)} applied, {len(failed)} failed"
        )

        return {
            "applied": applied,
            "failed": failed,
            "total_operations": len(operations)
        }

    def _apply_create(self, op: NDJSONOperation):
        """Apply create operation."""
        if not op.file_path:
            raise ValueError("Create operation missing file_path")
        if op.content is None:
            raise ValueError("Create operation missing content")

        file_path = self.workspace / op.file_path

        # Create parent directories
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        file_path.write_text(op.content, encoding='utf-8')

    def _apply_modify(self, op: NDJSONOperation):
        """Apply modify operation."""
        if not op.file_path:
            raise ValueError("Modify operation missing file_path")
        if not op.operations:
            raise ValueError("Modify operation missing operations list")

        file_path = self.workspace / op.file_path

        if not file_path.exists():
            raise FileNotFoundError(f"Cannot modify non-existent file: {op.file_path}")

        # Read current content
        content = file_path.read_text(encoding='utf-8')

        # Apply sub-operations
        for sub_op in op.operations:
            content = self._apply_sub_operation(content, sub_op, op.file_path)

        # Write modified content
        file_path.write_text(content, encoding='utf-8')

    def _apply_sub_operation(self, content: str, sub_op: Dict, file_path: str) -> str:
        """Apply a single sub-operation to content."""
        sub_type = sub_op.get("type")

        if sub_type == "append":
            # Append to end of file
            return content + sub_op.get("content", "")

        elif sub_type == "insert_after":
            # Insert after anchor line
            anchor = sub_op.get("anchor")
            new_content = sub_op.get("content")

            if anchor not in content:
                logger.warning(
                    f"[NDJSON:Apply] Anchor '{anchor[:50]}' not found in {file_path}, appending instead"
                )
                return content + "\n" + new_content

            # Find anchor and insert after it
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if anchor in line:
                    lines.insert(i + 1, new_content)
                    break

            return '\n'.join(lines)

        elif sub_type == "replace":
            # Replace old_text with new_text
            old_text = sub_op.get("old_text", "")
            new_text = sub_op.get("new_text", "")

            if old_text not in content:
                raise ValueError(f"Replace anchor '{old_text[:50]}' not found in {file_path}")

            return content.replace(old_text, new_text, 1)  # Replace first occurrence

        elif sub_type == "replace_all":
            # Replace ALL occurrences of old_text with new_text
            old_text = sub_op.get("old_text", "")
            new_text = sub_op.get("new_text", "")

            if not old_text:
                raise ValueError(f"replace_all requires non-empty old_text in {file_path}")
            if old_text not in content:
                raise ValueError(f"replace_all anchor '{old_text[:50]}' not found in {file_path}")

            return content.replace(old_text, new_text)

        else:
            logger.warning(f"[NDJSON:Apply] Unknown sub-operation type: {sub_type}")
            return content

    def _apply_delete(self, op: NDJSONOperation):
        """Apply delete operation."""
        if not op.file_path:
            raise ValueError("Delete operation missing file_path")

        file_path = self.workspace / op.file_path

        if file_path.exists():
            file_path.unlink()
        else:
            logger.warning(f"[NDJSON:Apply] Cannot delete non-existent file: {op.file_path}")


def detect_ndjson_format(output: str) -> bool:
    """
    Detect if output is in NDJSON format.

    Args:
        output: Raw LLM output

    Returns:
        True if NDJSON format detected
    """
    # Check for newline-delimited JSON pattern
    if '\n{' not in output:
        return False

    # Check for NDJSON-specific markers
    if '"type":' in output and ('"file_path":' in output or '"meta"' in output):
        # Additional check: first non-empty line should be valid JSON
        for line in output.strip().split('\n'):
            line = line.strip()
            if line:
                try:
                    obj = json.loads(line)
                    # Valid JSON line with type field → likely NDJSON
                    if "type" in obj:
                        return True
                except json.JSONDecodeError:
                    pass
                break

    return False
