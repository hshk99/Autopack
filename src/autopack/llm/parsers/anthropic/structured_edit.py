"""Structured edit format parser.

This parser handles JSON responses containing structured edit operations
(insert, replace, delete, prepend, append) with line numbers and context.

Per IMPLEMENTATION_PLAN3.md Phase 2.2: LLM outputs structured edit instructions
that are applied to files rather than generating complete file content.
"""

import json
import logging
from typing import Dict, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class StructuredEditParseResult:
    """Result of parsing structured edit output."""

    success: bool
    """Whether parsing succeeded."""

    operations: Optional[list]
    """Parsed edit operations (list of dicts)."""

    summary: Optional[str] = None
    """Summary description of edits."""

    error: Optional[str] = None
    """Error message if parsing failed."""

    repair_method: Optional[str] = None
    """Method used for JSON repair if applicable."""

    converted_from_full_file: bool = False
    """Whether content was auto-converted from full-file format."""


class StructuredEditParser:
    """Parser for structured edit JSON format."""

    @staticmethod
    def _extract_from_fence(content: str) -> Optional[str]:
        """Extract JSON from markdown code fence."""
        if "```json" not in content:
            return None

        json_start = content.find("```json") + 7
        json_end = content.find("```", json_start)
        if json_end > json_start:
            return content[json_start:json_end].strip()
        return None

    @staticmethod
    def _convert_full_file_to_operations(
        files_json: list, existing_files: Dict[str, str]
    ) -> tuple[list, bool]:
        """
        Convert full-file format to structured edit operations.

        Per BUILD-040: Auto-convert if LLM produced {"files": [...]} instead
        of {"operations": [...]}.

        Args:
            files_json: List of file entries with mode and new_content
            existing_files: Map of file_path -> existing content (for line counts)

        Returns:
            Tuple of (operations list, whether any files were skipped)
        """
        operations_json = []
        any_skipped = False

        for file_entry in files_json:
            file_path = file_entry.get("path")
            mode = file_entry.get("mode", "modify")
            new_content = file_entry.get("new_content")

            if not file_path:
                continue

            if mode == "create" and new_content:
                # Convert "create" to prepend operation (which creates file if missing)
                operations_json.append(
                    {"type": "prepend", "file_path": file_path, "content": new_content}
                )
                logger.info(
                    f"[StructuredEditParser] Converted create file '{file_path}' to prepend operation"
                )

            elif mode == "delete":
                # DELETE mode is rare and requires file line count
                logger.warning(
                    f"[StructuredEditParser] Skipping delete mode conversion for '{file_path}' (not supported)"
                )
                any_skipped = True
                continue

            elif mode == "modify" and new_content:
                # Convert "modify" to replace operation (whole file)
                file_exists = file_path in existing_files
                if file_exists:
                    # Get actual line count from existing file
                    existing_content = existing_files.get(file_path, "")
                    if isinstance(existing_content, str):
                        line_count = existing_content.count("\n") + 1
                        operations_json.append(
                            {
                                "type": "replace",
                                "file_path": file_path,
                                "start_line": 1,
                                "end_line": line_count,
                                "content": new_content,
                            }
                        )
                        logger.info(
                            f"[StructuredEditParser] Converted modify file '{file_path}' to replace operation (lines 1-{line_count})"
                        )
                    else:
                        logger.warning(
                            f"[StructuredEditParser] Skipping modify for '{file_path}' (existing content not string)"
                        )
                        any_skipped = True
                else:
                    # File doesn't exist, treat as create (use prepend)
                    operations_json.append(
                        {"type": "prepend", "file_path": file_path, "content": new_content}
                    )
                    logger.info(
                        f"[StructuredEditParser] Converted modify non-existent file '{file_path}' to prepend operation (create)"
                    )

        return operations_json, any_skipped

    def parse(
        self, content: str, existing_files: Optional[Dict[str, str]] = None
    ) -> StructuredEditParseResult:
        """
        Parse structured edit JSON output.

        Args:
            content: Raw LLM output (should be JSON with 'operations' array)
            existing_files: Optional map of file_path -> content for format conversion

        Returns:
            StructuredEditParseResult with success/failure status and operations
        """
        existing_files = existing_files or {}

        try:
            # Parse JSON
            result_json = None
            initial_parse_error = None
            repair_method = None

            try:
                result_json = json.loads(content.strip())
                repair_method = "direct_parse"
            except json.JSONDecodeError as e:
                initial_parse_error = str(e)
                # Try extracting from markdown code fence
                fenced = self._extract_from_fence(content)
                if fenced:
                    try:
                        result_json = json.loads(fenced)
                        repair_method = "markdown_fence_extraction"
                        initial_parse_error = None
                    except json.JSONDecodeError as e2:
                        initial_parse_error = str(e2)

            if not result_json:
                # Try JSON repair (uses external JsonRepairHelper if available)
                try:
                    from autopack.repair_helpers import JsonRepairHelper

                    json_repair = JsonRepairHelper()
                    error_msg = (
                        initial_parse_error or "Failed to parse JSON with 'operations' array"
                    )
                    repaired_json, repair_method_name = json_repair.attempt_repair(
                        content, error_msg
                    )

                    if repaired_json is not None:
                        logger.info(
                            f"[StructuredEditParser] JSON repair succeeded via {repair_method_name}"
                        )
                        result_json = repaired_json
                        repair_method = f"json_repair_{repair_method_name}"
                except ImportError:
                    pass  # JsonRepairHelper not available

            if not result_json:
                return StructuredEditParseResult(
                    success=False,
                    operations=None,
                    error="Failed to parse JSON with 'operations' array",
                )

            # Extract summary and operations
            summary = result_json.get("summary", "Structured edits")
            operations_json = result_json.get("operations", [])
            converted_from_full_file = False

            # BUILD-040: Auto-convert full-file format to structured_edit format
            if not operations_json and "files" in result_json:
                logger.info(
                    "[StructuredEditParser] Detected full-file format - auto-converting to operations"
                )
                files_json = result_json.get("files", [])
                operations_json, any_skipped = self._convert_full_file_to_operations(
                    files_json, existing_files
                )
                converted_from_full_file = True

                if operations_json:
                    logger.info(
                        f"[StructuredEditParser] Format conversion successful: {len(operations_json)} operations generated"
                    )
                else:
                    logger.warning(
                        "[StructuredEditParser] Format conversion produced no operations"
                    )

            # Empty operations is treated as a no-op, not a failure
            if not operations_json:
                logger.warning(
                    "[StructuredEditParser] Structured edit produced no operations (treating as no-op)"
                )
                return StructuredEditParseResult(
                    success=True,
                    operations=[],
                    summary=summary,
                    repair_method=repair_method,
                    converted_from_full_file=converted_from_full_file,
                )

            # Basic validation of operations structure
            if not isinstance(operations_json, list):
                return StructuredEditParseResult(
                    success=False,
                    operations=None,
                    error="'operations' field is not an array",
                )

            # Return parsed operations (detailed validation happens in EditOperation class)
            return StructuredEditParseResult(
                success=True,
                operations=operations_json,
                summary=summary,
                repair_method=repair_method,
                converted_from_full_file=converted_from_full_file,
            )

        except Exception as e:
            logger.error(f"[StructuredEditParser] Unexpected error: {e}")
            return StructuredEditParseResult(
                success=False,
                operations=None,
                error=f"Unexpected error during parsing: {str(e)}",
            )
