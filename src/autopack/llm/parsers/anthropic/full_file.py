"""Full-file JSON format parser with repair logic.

This parser handles JSON responses where the LLM outputs complete file content.
It includes sophisticated repair logic for handling:
- Bare newlines in JSON strings
- Placeholder content decoding
- Bracket balancing on truncation
- Malformed JSON recovery

Per GPT_RESPONSE10: LLM outputs complete file content, we generate diff.
"""

import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FullFileParseResult:
    """Result of parsing full-file JSON output."""

    success: bool
    """Whether parsing succeeded."""

    content: Optional[Dict[str, Any]]
    """Parsed JSON content (files array)."""

    error: Optional[str] = None
    """Error message if parsing failed."""

    repair_method: Optional[str] = None
    """Method used for JSON repair if applicable."""


class FullFileParser:
    """Parser for full-file JSON format with repair logic."""

    @staticmethod
    def _escape_newlines_in_json_strings(raw: str) -> str:
        """
        Make JSON more robust by escaping bare newlines inside string literals.

        Some models emit multi-line strings with literal newlines inside quotes,
        which is invalid JSON and causes 'Unterminated string' errors.
        This helper walks the text and replaces '\\n' with '\\\\n' only while
        inside a JSON string, preserving semantics but making the JSON valid.
        """
        out: list[str] = []
        in_string = False
        escape = False

        for ch in raw:
            if not in_string:
                if ch == '"':
                    in_string = True
                out.append(ch)
                continue

            # We are inside a string
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
    def _attempt_json_parse(candidate: Optional[str]) -> Optional[Dict[str, Any]]:
        """Attempt to parse JSON with newline repair fallback."""
        if not candidate:
            return None
        try:
            return json.loads(candidate.strip())
        except json.JSONDecodeError:
            repaired = FullFileParser._escape_newlines_in_json_strings(candidate.strip())
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                return None

    @staticmethod
    def _decode_placeholder_string(raw_segment: str) -> str:
        """Decode a pseudo-JSON string segment without trusting malformed escapes."""
        result_chars: list[str] = []
        idx = 0
        length = len(raw_segment)

        while idx < length:
            ch = raw_segment[idx]
            if ch == "\\" and idx + 1 < length:
                nxt = raw_segment[idx + 1]
                if nxt == "n":
                    result_chars.append("\n")
                    idx += 2
                    continue
                if nxt == "r":
                    result_chars.append("\r")
                    idx += 2
                    continue
                if nxt == "t":
                    result_chars.append("\t")
                    idx += 2
                    continue
                if nxt in ('"', "\\", "/"):
                    result_chars.append(nxt)
                    idx += 2
                    continue
                if nxt == "u" and idx + 5 < length:
                    hex_value = raw_segment[idx + 2 : idx + 6]
                    try:
                        result_chars.append(chr(int(hex_value, 16)))
                        idx += 6
                        continue
                    except ValueError:
                        # Fall back to literal output
                        result_chars.append("\\")
                        idx += 1
                        continue
                # Unknown escape - keep the backslash and reprocess next char normally
                result_chars.append("\\")
                idx += 1
                continue

            result_chars.append(ch)
            idx += 1

        return "".join(result_chars)

    @staticmethod
    def _sanitize_full_file_output(raw_text: Optional[str]) -> tuple[str, Dict[str, str]]:
        """
        Replace problematic new_content blobs with safe placeholders so json.loads succeeds.
        Returns sanitized text plus a mapping of placeholder -> raw segment.
        """
        if not raw_text or '"new_content":"' not in raw_text:
            return raw_text or "", {}

        placeholders: Dict[str, str] = {}
        output_chars: list[str] = []
        idx = 0
        placeholder_idx = 0
        target = raw_text

        sentinel = '"new_content":"'

        while idx < len(target):
            if target.startswith(sentinel, idx):
                output_chars.append(sentinel)
                idx += len(sentinel)
                segment_chars: list[str] = []

                while idx < len(target):
                    ch = target[idx]

                    # Preserve escaped sequences verbatim
                    if ch == "\\" and idx + 1 < len(target):
                        segment_chars.append(target[idx : idx + 2])
                        idx += 2
                        continue

                    if ch == '"':
                        probe = idx + 1
                        while probe < len(target) and target[probe] in " \t\r\n":
                            probe += 1
                        if probe < len(target) and target[probe] == "}":
                            probe2 = probe + 1
                            while probe2 < len(target) and target[probe2] in " \t\r\n":
                                probe2 += 1
                            if probe2 >= len(target) or target[probe2] in ",]}":
                                break

                    segment_chars.append(ch)
                    idx += 1

                content_raw = "".join(segment_chars)
                placeholder = f"__FULLFILE_CONTENT_{placeholder_idx}__"
                placeholder_idx += 1
                placeholders[placeholder] = content_raw
                output_chars.append(placeholder)
                output_chars.append('"')

                if idx < len(target) and target[idx] == '"':
                    idx += 1
                continue

            else:
                output_chars.append(target[idx])
                idx += 1

        return "".join(output_chars), placeholders

    @staticmethod
    def _balance_json_brackets(raw_text: str) -> str:
        """
        Ensure any unterminated braces/brackets are closed in LIFO order.
        Helps when the LLM truncates output before emitting final ]}.
        """
        stack: list[str] = []
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
    def _restore_placeholder_content(
        payload: Dict[str, Any], placeholder_map: Dict[str, str]
    ) -> None:
        """Restore placeholders in parsed JSON with original content."""
        files = payload.get("files")
        if not isinstance(files, list):
            return

        for file_entry in files:
            if not isinstance(file_entry, dict):
                continue
            content = file_entry.get("new_content")
            if isinstance(content, str) and content in placeholder_map:
                raw_segment = placeholder_map[content]
                file_entry["new_content"] = FullFileParser._decode_placeholder_string(raw_segment)

    @staticmethod
    def _extract_code_fence(raw_text: str, fence: str) -> Optional[str]:
        """Extract content from markdown code fence."""
        start = raw_text.find(fence)
        if start == -1:
            return None
        start += len(fence)
        end = raw_text.find("```", start)
        if end == -1:
            return None
        return raw_text[start:end].strip()

    @staticmethod
    def _extract_first_json_object(raw_text: str) -> Optional[str]:
        """Extract the first complete JSON object from text."""
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

    def parse(self, content: str) -> FullFileParseResult:
        """
        Parse full-file JSON output with repair logic.

        Args:
            content: Raw LLM output (should be JSON with 'files' array)

        Returns:
            FullFileParseResult with success/failure status and parsed content
        """
        try:
            result_json: Optional[Dict[str, Any]] = None
            placeholder_map: Dict[str, str] = {}
            raw = content.strip()
            repair_method: Optional[str] = None

            candidates: list[str] = [raw]

            # Format guard: if the raw output looks like a git diff, bail out early
            if "diff --git" in raw and "{" not in raw:
                return FullFileParseResult(
                    success=False,
                    content=None,
                    error="Detected git diff output; expected JSON with 'files' array. "
                    "Regenerate a JSON full-file response (no diff, no markdown fences).",
                )

            # Try extracting from markdown code fence
            if "```json" in content:
                fenced = self._extract_code_fence(content, "```json")
                if fenced:
                    candidates.insert(0, fenced)
                    repair_method = "markdown_fence_extraction"

            # Try each candidate
            for candidate in candidates:
                # Try direct parse
                result_json = self._attempt_json_parse(candidate)
                if result_json:
                    if not repair_method:
                        repair_method = "direct_parse"
                    break

                # Try with bracket balancing
                balanced = self._balance_json_brackets(candidate)
                result_json = self._attempt_json_parse(balanced)
                if result_json:
                    repair_method = "bracket_balancing"
                    break

                # Try sanitizing new_content fields
                sanitized_candidate, placeholder_map = self._sanitize_full_file_output(candidate)
                if sanitized_candidate != candidate:
                    balanced_candidate = self._balance_json_brackets(sanitized_candidate)
                    result_json = self._attempt_json_parse(balanced_candidate)
                    if result_json:
                        repair_method = "content_sanitization_and_balancing"
                        break

            if not result_json:
                # Try extracting first JSON object and balancing
                extracted = self._extract_first_json_object(raw)
                if extracted:
                    # Try direct parse of extracted object
                    result_json = self._attempt_json_parse(extracted)
                    if result_json:
                        repair_method = "object_extraction"
                    else:
                        # Try with sanitization and balancing
                        sanitized_candidate, placeholder_map = self._sanitize_full_file_output(
                            extracted
                        )
                        balanced_candidate = self._balance_json_brackets(sanitized_candidate)
                        result_json = self._attempt_json_parse(balanced_candidate)
                        if result_json:
                            repair_method = "object_extraction_and_balancing"

            if not result_json:
                return FullFileParseResult(
                    success=False,
                    content=None,
                    error="Failed to parse JSON after all repair attempts",
                )

            # Restore placeholder content
            if placeholder_map:
                self._restore_placeholder_content(result_json, placeholder_map)

            # Validate that we have a files array
            if "files" not in result_json:
                return FullFileParseResult(
                    success=False,
                    content=None,
                    error="JSON missing 'files' array",
                )

            if not isinstance(result_json.get("files"), list):
                return FullFileParseResult(
                    success=False,
                    content=None,
                    error="'files' field is not an array",
                )

            return FullFileParseResult(
                success=True,
                content=result_json,
                error=None,
                repair_method=repair_method,
            )

        except Exception as e:
            logger.error(f"[FullFileParser] Unexpected error: {e}")
            return FullFileParseResult(
                success=False,
                content=None,
                error=f"Unexpected error during parsing: {str(e)}",
            )
