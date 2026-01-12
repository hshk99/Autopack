"""Response parsing utilities for LLM outputs.

Provides:
- JSON parsing with repair/recovery for malformed output
- Full-file replacement output parsing
- NDJSON parsing for truncation-tolerant format
- Structured edit parsing for line-based operations
- Legacy diff extraction

This module extracts parsing logic from anthropic_clients.py.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ParseResult:
    """Result of parsing LLM output.

    Attributes:
        success: Whether parsing succeeded
        data: Parsed data structure (if successful)
        error: Error message (if failed)
        format_type: Detected format type
        was_repaired: Whether JSON repair was applied
    """

    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    format_type: Optional[str] = None
    was_repaired: bool = False


class JSONRepair:
    """Utilities for repairing malformed JSON from LLM output."""

    @staticmethod
    def escape_newlines_in_strings(raw: str) -> str:
        """Escape bare newlines inside JSON string literals.

        Some models emit multi-line strings with literal newlines inside quotes,
        which is invalid JSON. This helper replaces '\\n' with '\\\\n' only
        inside JSON strings.

        Args:
            raw: Raw JSON text

        Returns:
            JSON text with newlines escaped in strings
        """
        out: List[str] = []
        in_string = False
        escape = False

        for ch in raw:
            if not in_string:
                if ch == '"':
                    in_string = True
                out.append(ch)
                continue

            if escape:
                out.append(ch)
                escape = False
                continue

            if ch == "\\":
                out.append(ch)
                escape = True
            elif ch == '"':
                out.append(ch)
                in_string = False
            elif ch == "\n":
                out.append("\\n")
            else:
                out.append(ch)

        return "".join(out)

    @staticmethod
    def balance_brackets(raw_text: str) -> str:
        """Close any unterminated braces/brackets in LIFO order.

        Helps when the LLM truncates output before emitting final ]}.

        Args:
            raw_text: Raw JSON text

        Returns:
            JSON text with balanced brackets
        """
        stack: List[str] = []
        in_string = False
        escape = False

        for ch in raw_text:
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in ("}", "]"):
                if stack and stack[-1] == ch:
                    stack.pop()

        if not stack:
            return raw_text

        # Append missing closers in reverse order (LIFO)
        closing = "".join(reversed(stack))
        return raw_text + closing

    @staticmethod
    def extract_code_fence(raw_text: str, fence: str = "```json") -> Optional[str]:
        """Extract content from a markdown code fence.

        Args:
            raw_text: Text containing code fence
            fence: Fence marker to look for

        Returns:
            Content inside fence, or None if not found
        """
        start = raw_text.find(fence)
        if start == -1:
            return None
        start += len(fence)
        end = raw_text.find("```", start)
        if end == -1:
            return None
        return raw_text[start:end].strip()

    @staticmethod
    def extract_first_json_object(raw_text: str) -> Optional[str]:
        """Extract the first complete JSON object from text.

        Args:
            raw_text: Text potentially containing JSON

        Returns:
            First complete JSON object, or None
        """
        start = raw_text.find("{")
        if start == -1:
            return None
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(raw_text)):
            ch = raw_text[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return raw_text[start : idx + 1]
        return None


class DiffExtractor:
    """Utilities for extracting git diff content from text."""

    @staticmethod
    def extract_diff_from_text(text: str) -> str:
        """Extract git diff content from text that may contain explanations.

        Args:
            text: Raw text that may contain diff content

        Returns:
            Extracted diff content or empty string
        """
        lines = text.split("\n")
        diff_lines = []
        in_diff = False

        for line in lines:
            # Start of diff
            if line.startswith("diff --git"):
                in_diff = True
                diff_lines.append(line)
            # Continuation of diff
            elif in_diff:
                # Clean up malformed hunk headers
                if line.startswith("@@"):
                    match = re.match(r"^(@@\s+-\d+,\d+\s+\+\d+,\d+\s+@@)", line)
                    if match:
                        diff_lines.append(match.group(1))
                    else:
                        logger.warning(f"Skipping malformed hunk header: {line[:80]}")
                        continue
                # Check if still in diff
                elif (
                    line.startswith(("index ", "---", "+++", "+", "-", " "))
                    or line.startswith("new file mode")
                    or line.startswith("deleted file mode")
                    or line.startswith("similarity index")
                    or line.startswith("rename from")
                    or line.startswith("rename to")
                    or line == ""
                ):
                    diff_lines.append(line)
                # Next diff section
                elif line.startswith("diff --git"):
                    diff_lines.append(line)
                # End of diff
                else:
                    if line.startswith("```") or line.startswith("#"):
                        break

        return "\n".join(diff_lines) if diff_lines else ""


class ResponseParser:
    """Parser for various LLM response formats.

    Supports:
    - Full-file replacement JSON
    - Structured edit JSON
    - NDJSON (truncation-tolerant)
    - Legacy git diff

    Example:
        parser = ResponseParser()
        result = parser.parse_json(raw_output)
        if result.success:
            files = result.data.get("files", [])
    """

    def __init__(self):
        """Initialize the response parser."""
        self._json_repair = JSONRepair()
        self._diff_extractor = DiffExtractor()

    def parse_json(self, content: str) -> ParseResult:
        """Parse JSON content with repair capabilities.

        Tries multiple strategies:
        1. Direct JSON parse
        2. Extract from ```json fence
        3. Extract from ``` fence
        4. Extract first JSON object
        5. Apply newline escaping and bracket balancing

        Args:
            content: Raw LLM output

        Returns:
            ParseResult with parsed data or error
        """
        raw = content.strip()

        # Check for git diff format (wrong format)
        if "diff --git" in raw and "{" not in raw:
            return ParseResult(
                success=False,
                error="Detected git diff output; expected JSON with 'files' array",
                format_type="diff",
            )

        candidates = [raw]

        # Try code fence extraction
        if "```json" in content:
            fenced = self._json_repair.extract_code_fence(content, "```json")
            if fenced:
                candidates.append(fenced)

        if "```" in content:
            fenced_generic = self._json_repair.extract_code_fence(content, "```")
            if fenced_generic:
                candidates.append(fenced_generic)

        # Try first JSON object extraction
        extracted = self._json_repair.extract_first_json_object(raw)
        if extracted:
            candidates.append(extracted)

        # Try each candidate
        for candidate in candidates:
            result = self._try_parse_json(candidate)
            if result.success:
                return result

        return ParseResult(
            success=False,
            error="Failed to parse JSON from any extraction strategy",
            format_type="unknown",
        )

    def _try_parse_json(self, candidate: str) -> ParseResult:
        """Try to parse a JSON candidate with repair fallback.

        Args:
            candidate: JSON candidate text

        Returns:
            ParseResult with parsed data or error
        """
        # Direct parse
        try:
            data = json.loads(candidate)
            return ParseResult(
                success=True,
                data=data,
                format_type="json",
                was_repaired=False,
            )
        except json.JSONDecodeError:
            pass

        # Try with newline escaping
        repaired = self._json_repair.escape_newlines_in_strings(candidate)
        try:
            data = json.loads(repaired)
            return ParseResult(
                success=True,
                data=data,
                format_type="json",
                was_repaired=True,
            )
        except json.JSONDecodeError:
            pass

        # Try with bracket balancing
        balanced = self._json_repair.balance_brackets(repaired)
        try:
            data = json.loads(balanced)
            return ParseResult(
                success=True,
                data=data,
                format_type="json",
                was_repaired=True,
            )
        except json.JSONDecodeError as e:
            return ParseResult(
                success=False,
                error=str(e),
                format_type="json",
            )

    def parse_full_file_output(self, content: str) -> ParseResult:
        """Parse full-file replacement output.

        Expected format:
        {
            "summary": "description",
            "files": [
                {"path": "...", "mode": "modify|create|delete", "new_content": "..."}
            ]
        }

        Args:
            content: Raw LLM output

        Returns:
            ParseResult with files data
        """
        result = self.parse_json(content)
        if not result.success:
            return result

        data = result.data
        if not isinstance(data, dict):
            return ParseResult(
                success=False,
                error="Expected JSON object",
                format_type="full_file",
            )

        if "files" not in data:
            return ParseResult(
                success=False,
                error="Missing 'files' array in output",
                format_type="full_file",
            )

        if not isinstance(data["files"], list):
            return ParseResult(
                success=False,
                error="'files' must be an array",
                format_type="full_file",
            )

        return ParseResult(
            success=True,
            data=data,
            format_type="full_file",
            was_repaired=result.was_repaired,
        )

    def parse_structured_edit_output(self, content: str) -> ParseResult:
        """Parse structured edit output.

        Expected format:
        {
            "summary": "description",
            "operations": [
                {"type": "insert|replace|delete", ...}
            ]
        }

        Args:
            content: Raw LLM output

        Returns:
            ParseResult with operations data
        """
        result = self.parse_json(content)
        if not result.success:
            return result

        data = result.data
        if not isinstance(data, dict):
            return ParseResult(
                success=False,
                error="Expected JSON object",
                format_type="structured_edit",
            )

        if "operations" not in data:
            return ParseResult(
                success=False,
                error="Missing 'operations' array in output",
                format_type="structured_edit",
            )

        if not isinstance(data["operations"], list):
            return ParseResult(
                success=False,
                error="'operations' must be an array",
                format_type="structured_edit",
            )

        return ParseResult(
            success=True,
            data=data,
            format_type="structured_edit",
            was_repaired=result.was_repaired,
        )

    def parse_diff_output(self, content: str) -> ParseResult:
        """Parse legacy git diff output.

        Args:
            content: Raw LLM output

        Returns:
            ParseResult with extracted diff
        """
        # Try JSON first (some models wrap diff in JSON)
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "patch_content" in data:
                return ParseResult(
                    success=True,
                    data={"patch_content": data["patch_content"]},
                    format_type="diff",
                )
        except json.JSONDecodeError:
            pass

        # Extract from markdown fence
        if "```json" in content:
            fenced = self._json_repair.extract_code_fence(content, "```json")
            if fenced:
                try:
                    data = json.loads(fenced)
                    if isinstance(data, dict) and "patch_content" in data:
                        return ParseResult(
                            success=True,
                            data={"patch_content": data["patch_content"]},
                            format_type="diff",
                        )
                except json.JSONDecodeError:
                    pass

        # Extract raw diff
        diff_content = self._diff_extractor.extract_diff_from_text(content)
        if diff_content:
            return ParseResult(
                success=True,
                data={"patch_content": diff_content},
                format_type="diff",
            )

        return ParseResult(
            success=False,
            error="No git diff markers found. Output must start with 'diff --git'",
            format_type="diff",
        )

    def detect_format(self, content: str) -> str:
        """Detect the format of LLM output.

        Args:
            content: Raw LLM output

        Returns:
            Detected format: 'full_file', 'structured_edit', 'ndjson', 'diff', or 'unknown'
        """
        raw = content.strip()

        # Check for NDJSON (multiple JSON objects on separate lines)
        lines = [line.strip() for line in raw.split("\n") if line.strip()]
        if len(lines) >= 2:
            ndjson_lines = sum(1 for line in lines[:5] if line.startswith("{"))
            if ndjson_lines >= 2:
                return "ndjson"

        # Check for diff format
        if "diff --git" in raw:
            return "diff"

        # Try parsing as JSON
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                if "files" in data:
                    return "full_file"
                if "operations" in data:
                    return "structured_edit"
        except json.JSONDecodeError:
            # Try fence extraction
            if "```json" in content:
                fenced = self._json_repair.extract_code_fence(content, "```json")
                if fenced:
                    try:
                        data = json.loads(fenced)
                        if isinstance(data, dict):
                            if "files" in data:
                                return "full_file"
                            if "operations" in data:
                                return "structured_edit"
                    except json.JSONDecodeError:
                        pass

        return "unknown"


@dataclass
class NDJSONOperation:
    """A single NDJSON operation.

    Attributes:
        op_type: Operation type (create, modify, delete, meta)
        file_path: Target file path
        content: File content (for create/modify)
        operations: Edit operations (for modify with structured edits)
        raw_line: Original JSON line
    """

    op_type: str
    file_path: Optional[str] = None
    content: Optional[str] = None
    operations: Optional[List[Dict[str, Any]]] = None
    raw_line: str = ""


@dataclass
class NDJSONParseResult:
    """Result of NDJSON parsing.

    Attributes:
        success: Whether parsing succeeded
        operations: List of parsed operations
        lines_parsed: Number of lines successfully parsed
        lines_failed: Number of lines that failed parsing
        was_truncated: Whether output appears truncated
        total_expected: Expected total operations (from meta line)
        meta: Metadata from meta line
    """

    success: bool
    operations: List[NDJSONOperation] = field(default_factory=list)
    lines_parsed: int = 0
    lines_failed: int = 0
    was_truncated: bool = False
    total_expected: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None


class NDJSONParser:
    """Parser for NDJSON (Newline-Delimited JSON) format.

    NDJSON is truncation-tolerant: each line is a complete JSON object,
    so if truncation occurs, all complete lines are still usable.

    Example:
        parser = NDJSONParser()
        result = parser.parse(raw_output)
        for op in result.operations:
            print(f"{op.op_type}: {op.file_path}")
    """

    def parse(self, content: str) -> NDJSONParseResult:
        """Parse NDJSON content.

        Args:
            content: Raw NDJSON content (one JSON object per line)

        Returns:
            NDJSONParseResult with parsed operations
        """
        operations: List[NDJSONOperation] = []
        lines_parsed = 0
        lines_failed = 0
        meta: Optional[Dict[str, Any]] = None
        total_expected: Optional[int] = None

        # Strip markdown fences
        lines = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("```"):
                continue
            if stripped:
                lines.append(stripped)

        for line in lines:
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    lines_failed += 1
                    continue

                op_type = obj.get("type", "")

                if op_type == "meta":
                    meta = obj
                    total_expected = obj.get("total_operations")
                    lines_parsed += 1
                    continue

                op = NDJSONOperation(
                    op_type=op_type,
                    file_path=obj.get("file_path"),
                    content=obj.get("content"),
                    operations=obj.get("operations"),
                    raw_line=line,
                )
                operations.append(op)
                lines_parsed += 1

            except json.JSONDecodeError:
                lines_failed += 1

        # Detect truncation
        was_truncated = False
        if total_expected is not None and len(operations) < total_expected:
            was_truncated = True
        elif lines_failed > 0 and lines_failed == 1 and len(lines) > 1:
            # Last line might be truncated
            was_truncated = True

        return NDJSONParseResult(
            success=len(operations) > 0,
            operations=operations,
            lines_parsed=lines_parsed,
            lines_failed=lines_failed,
            was_truncated=was_truncated,
            total_expected=total_expected,
            meta=meta,
        )

    def format_for_prompt(
        self,
        deliverables: List[str],
        summary: str,
    ) -> str:
        """Generate NDJSON format instructions for prompt.

        Args:
            deliverables: List of deliverable file paths
            summary: Task summary

        Returns:
            Format instruction text
        """
        example = []
        example.append('{"type":"meta","summary":"' + summary + '","total_operations":2}')
        if deliverables:
            example.append(
                '{"type":"create","file_path":"'
                + deliverables[0]
                + '","content":"# File content\\n"}'
            )

        return "\n".join(
            [
                "**Example NDJSON output:**",
                "```",
            ]
            + example
            + [
                "```",
                "",
                "Each line must be a complete, valid JSON object.",
            ]
        )
