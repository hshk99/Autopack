"""NDJSON format parser with truncation tolerance.

This parser handles NDJSON (Newline-Delimited JSON) responses where each line
is a complete JSON object. This format provides truncation tolerance - if the
output is truncated, only the last incomplete line is lost, not the entire output.

Per BUILD-129 Phase 3 and TOKEN_BUDGET_ANALYSIS_REVISED.md Layer 3:
"Current formats (monolithic diff, single JSON object) are catastrophically fragile
under truncation. A single truncation ruins 100% of output. NDJSON makes each line
a complete JSON object, so only the last incomplete line is lost."
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

# Import the existing NDJSON infrastructure
from ....ndjson_format import NDJSONParser
from ....ndjson_format import NDJSONParseResult as CoreNDJSONParseResult

logger = logging.getLogger(__name__)


@dataclass
class NDJSONResponseParseResult:
    """Result of parsing NDJSON response."""

    success: bool
    """Whether parsing succeeded and produced operations."""

    operations: list
    """List of parsed NDJSON operations."""

    was_truncated: bool = False
    """Whether the last line was incomplete (truncation detected)."""

    lines_parsed: int = 0
    """Number of lines successfully parsed."""

    lines_failed: int = 0
    """Number of lines that failed to parse."""

    total_expected: Optional[int] = None
    """Expected total operations from meta line (if present)."""

    error: Optional[str] = None
    """Error message if parsing failed completely."""

    fallback_format: Optional[str] = None
    """Format detected if not NDJSON (e.g., 'structured_edit', 'legacy_diff')."""


class NDJSONResponseParser:
    """Parser for NDJSON response format with truncation tolerance."""

    def __init__(self):
        """Initialize parser with core NDJSON parser."""
        self.core_parser = NDJSONParser()

    @staticmethod
    def _sanitize_markdown_fences(content: str) -> str:
        """Remove markdown code fences that break NDJSON line parsing."""
        lines = []
        for ln in content.splitlines():
            s = ln.strip()
            if s.startswith("```"):
                continue
            lines.append(ln)
        return "\n".join(lines).strip()

    @staticmethod
    def _detect_format(sanitized: str) -> Optional[str]:
        """
        Detect if content is in a different format than NDJSON.

        Returns:
            Format name if detected ('structured_edit', 'legacy_diff', 'json_array'),
            or None if appears to be NDJSON.
        """
        # Check for structured edit JSON (pretty-printed object with operations array)
        if (
            sanitized.startswith("{")
            and '"operations"' in sanitized
            and "diff --git" not in sanitized
        ):
            try:
                obj = json.loads(sanitized)
                if isinstance(obj, dict) and isinstance(obj.get("operations"), list):
                    return "structured_edit"
            except Exception:
                pass

        # Check for legacy diff format
        if "diff --git" in sanitized or sanitized.startswith("*** Begin Patch"):
            return "legacy_diff"

        # Check for JSON array format (not NDJSON)
        # But allow array if it seems like operations
        if sanitized.startswith("["):
            try:
                obj = json.loads(sanitized)
                if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
                    # Check if these look like NDJSON operations
                    has_type = any(
                        x.get("type") in ("create", "modify", "delete", "meta") for x in obj
                    )
                    if not has_type:
                        return "json_array"
                    # Otherwise, treat as convertible to NDJSON (handled later)
            except Exception:
                pass

        # Single-line NDJSON with one operation is valid NDJSON, not a different format
        # Don't flag as "single_json_op" - let it be parsed as NDJSON

        return None

    @staticmethod
    def _try_scan_decode_json(sanitized: str) -> Optional[Dict[str, Any]]:
        """
        Try to recover any decodable JSON from payload by scanning.

        This is truncation-tolerant and ignores leading fragments.
        Used as a last resort to salvage structured edit JSON from truncated NDJSON output.
        """
        try:
            import ast
            from json import JSONDecoder

            decoder = JSONDecoder()
            idx = 0
            text = sanitized

            while True:
                # Find next plausible JSON start
                m1 = text.find("{", idx)
                m2 = text.find("[", idx)
                starts = [p for p in (m1, m2) if p != -1]
                if not starts:
                    return None
                start = min(starts)
                try:
                    obj, end = decoder.raw_decode(text[start:])
                    return obj
                except Exception:
                    # Try Python literal_eval as fallback
                    try:
                        obj = ast.literal_eval(text[start:])
                        return obj
                    except Exception:
                        idx = start + 1

        except Exception:
            return None

    def parse(self, content: str) -> NDJSONResponseParseResult:
        """
        Parse NDJSON response with truncation tolerance and format detection.

        Args:
            content: Raw LLM output (expected to be NDJSON format)

        Returns:
            NDJSONResponseParseResult with operations or format detection info
        """
        try:
            # Pre-sanitize: strip markdown fences
            sanitized = self._sanitize_markdown_fences(content or "")

            # Detect if content is in a different format
            detected_format = self._detect_format(sanitized)
            if detected_format:
                logger.warning(
                    f"[NDJSONResponseParser] Detected {detected_format} format instead of NDJSON"
                )
                return NDJSONResponseParseResult(
                    success=False,
                    operations=[],
                    fallback_format=detected_format,
                    error=f"Content is in {detected_format} format, not NDJSON",
                )

            # Parse NDJSON
            core_result: CoreNDJSONParseResult = self.core_parser.parse(sanitized)

            # Check if we got operations
            if not core_result.operations:
                # Try format detection again with more aggressive scanning
                detected_format = self._detect_format(sanitized)
                if detected_format:
                    return NDJSONResponseParseResult(
                        success=False,
                        operations=[],
                        fallback_format=detected_format,
                        error=f"No NDJSON operations found; content is {detected_format} format",
                    )

                # Try scanning for structured edit JSON
                obj = self._try_scan_decode_json(sanitized)
                if isinstance(obj, dict) and isinstance(obj.get("operations"), list):
                    logger.warning(
                        "[NDJSONResponseParser] Decoded structured-edit plan via scanning"
                    )
                    return NDJSONResponseParseResult(
                        success=False,
                        operations=[],
                        fallback_format="structured_edit",
                        error="Decoded structured-edit plan instead of NDJSON",
                    )

                # Try JSON array conversion
                if sanitized.startswith("["):
                    try:
                        obj = json.loads(sanitized)
                        if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
                            # Convert JSON array to NDJSON
                            converted = "\n".join(json.dumps(x, ensure_ascii=False) for x in obj)
                            core_result = self.core_parser.parse(converted)
                            if core_result.operations:
                                logger.info(
                                    f"[NDJSONResponseParser] Converted JSON array to {len(core_result.operations)} NDJSON operations"
                                )
                    except Exception:
                        pass

                # Still no operations?
                if not core_result.operations:
                    return NDJSONResponseParseResult(
                        success=False,
                        operations=[],
                        was_truncated=core_result.was_truncated,
                        lines_parsed=core_result.lines_parsed,
                        lines_failed=core_result.lines_failed,
                        error="NDJSON parsing produced no valid operations",
                    )

            # Success - return parsed operations
            return NDJSONResponseParseResult(
                success=True,
                operations=core_result.operations,
                was_truncated=core_result.was_truncated,
                lines_parsed=core_result.lines_parsed,
                lines_failed=core_result.lines_failed,
                total_expected=core_result.total_expected,
            )

        except Exception as e:
            logger.error(f"[NDJSONResponseParser] Unexpected error: {e}")
            return NDJSONResponseParseResult(
                success=False,
                operations=[],
                error=f"Unexpected error during parsing: {str(e)}",
            )
