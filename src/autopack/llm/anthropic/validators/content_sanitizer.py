"""Content sanitization for Anthropic Builder responses.

Extracted from full_file_parser.py lines 58-273 as part of PR-CLIENT-3.
Handles placeholder replacement and JSON escape sequence processing.
"""

import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ContentSanitizer:
    """Sanitizes and validates JSON content from Builder responses.

    Responsibilities:
    1. Escape bare newlines in JSON strings
    2. Replace problematic new_content blobs with placeholders
    3. Decode placeholder strings with proper escape handling
    4. Restore placeholder content after parsing
    5. Balance JSON brackets for truncated output
    """

    def escape_newlines_in_json_strings(self, raw: str) -> str:
        """
        Make JSON more robust by escaping bare newlines inside string literals.

        Some models emit multi-line strings with literal newlines inside quotes,
        which is invalid JSON and causes 'Unterminated string' errors.
        This helper walks the text and replaces '\n' with '\\n' only while
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

    def attempt_json_parse(self, candidate: Optional[str]) -> Optional[Dict[str, Any]]:
        """Attempt to parse JSON with newline repair fallback."""
        if not candidate:
            return None
        try:
            return json.loads(candidate.strip())
        except json.JSONDecodeError:
            repaired = self.escape_newlines_in_json_strings(candidate.strip())
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                return None

    def decode_placeholder_string(self, raw_segment: str) -> str:
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

    def sanitize_full_file_output(self, raw_text: Optional[str]) -> tuple[str, Dict[str, str]]:
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

                output_chars.append(target[idx])
                idx += 1

            else:
                output_chars.append(target[idx])
                idx += 1

        return "".join(output_chars), placeholders

    def balance_json_brackets(self, raw_text: str) -> str:
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

    def restore_placeholder_content(
        self, payload: Dict[str, Any], placeholder_map: Dict[str, str]
    ) -> None:
        """Restore placeholder content in file entries."""
        files = payload.get("files")
        if not isinstance(files, list):
            return

        for file_entry in files:
            if not isinstance(file_entry, dict):
                continue
            content = file_entry.get("new_content")
            if isinstance(content, str) and content in placeholder_map:
                raw_segment = placeholder_map[content]
                file_entry["new_content"] = self.decode_placeholder_string(raw_segment)

    def extract_code_fence(self, raw_text: str, fence: str) -> Optional[str]:
        """Extract content from markdown code fence."""
        start = raw_text.find(fence)
        if start == -1:
            return None
        start += len(fence)
        end = raw_text.find("```", start)
        if end == -1:
            return None
        return raw_text[start:end].strip()

    def extract_first_json_object(self, raw_text: str) -> Optional[str]:
        """Extract first JSON object from text."""
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
