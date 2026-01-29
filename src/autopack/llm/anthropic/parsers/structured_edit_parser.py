"""Structured edit format parser for Anthropic Builder responses.

Extracted from anthropic_clients.py lines 1513-1797 as part of PR-CLIENT-2.
Handles parsing of structured edit JSON format with explicit edit operations.

This is Stage 2 format per IMPLEMENTATION_PLAN3.md Phase 2.2.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class StructuredEditParseResult:
    """Result of structured edit parsing."""

    success: bool
    edit_plan: Optional[Any]  # EditPlan type
    summary: str
    operations_count: int
    tokens_used: int
    prompt_tokens: int
    completion_tokens: int
    error: Optional[str] = None
    stop_reason: Optional[str] = None
    was_truncated: bool = False


class StructuredEditParser:
    """Parses structured edit format Builder responses.

    Structured edit format uses JSON with explicit edit operations.

    Responsibilities:
    1. Extract JSON from response (with markdown fence handling)
    2. Validate edit structure schema
    3. Parse operations into EditPlan
    4. Handle JSON repair for malformed responses
    5. Auto-convert full-file format to structured_edit format
    """

    def parse(
        self,
        content: str,
        file_context: Optional[Dict],
        response: Any,
        model: str,
        phase_spec: Dict,
        config: Optional[Any] = None,
        stop_reason: Optional[str] = None,
        was_truncated: bool = False,
    ) -> StructuredEditParseResult:
        """Parse structured edit JSON output.

        Extracted from anthropic_clients.py lines 1513-1797.

        Args:
            content: Raw LLM output
            file_context: File context dict with existing_files
            response: LLM response object (for token counts)
            model: Model name used
            phase_spec: Phase specification dict
            config: BuilderOutputConfig (optional)
            stop_reason: Stop reason from LLM
            was_truncated: Whether output was truncated

        Returns:
            StructuredEditParseResult with parsed edit plan or error
        """
        from autopack.builder_config import BuilderOutputConfig
        from autopack.structured_edits import (EditOperation,
                                               EditOperationType, EditPlan)

        if config is None:
            config = BuilderOutputConfig()

        # Extract existing files from context for format conversion
        files = {}
        if file_context:
            files = file_context.get("existing_files", {})
            if not isinstance(files, dict):
                logger.warning(
                    f"[Builder] file_context.get('existing_files') returned non-dict: {type(files)}, using empty dict"
                )
                files = {}

        try:
            # Parse JSON
            result_json = None
            initial_parse_error = None
            try:
                result_json = json.loads(content.strip())
            except json.JSONDecodeError as e:
                initial_parse_error = str(e)
                # Try extracting from markdown code fence
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    if json_end > json_start:
                        json_str = content[json_start:json_end].strip()
                        try:
                            result_json = json.loads(json_str)
                            initial_parse_error = None  # Fence extraction succeeded
                        except json.JSONDecodeError as e2:
                            initial_parse_error = str(e2)

            if not result_json:
                # BUILD-039: Apply JSON repair to structured_edit mode (same as full-file mode)
                logger.info(
                    "[Builder] Attempting JSON repair on malformed structured_edit output..."
                )
                from autopack.repair_helpers import (JsonRepairHelper,
                                                     save_repair_debug)

                json_repair = JsonRepairHelper()
                error_msg = initial_parse_error or "Failed to parse JSON with 'operations' array"
                repaired_json, repair_method = json_repair.attempt_repair(content, error_msg)

                if repaired_json is not None:
                    logger.info(
                        f"[Builder] Structured edit JSON repair succeeded via {repair_method}"
                    )
                    save_repair_debug(
                        file_path="builder_structured_edit.json",
                        original="",
                        attempted=content,
                        repaired=json.dumps(repaired_json),
                        error=error_msg,
                        method=repair_method,
                    )
                    result_json = repaired_json
                else:
                    # JSON repair failed - return error
                    error_msg = "LLM output invalid format - expected JSON with 'operations' array"
                    if was_truncated:
                        error_msg += " (stop_reason=max_tokens)"
                    logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                    return StructuredEditParseResult(
                        success=False,
                        edit_plan=None,
                        summary="",
                        operations_count=0,
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        error=error_msg,
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )

            # Extract summary and operations
            summary = result_json.get("summary", "Structured edits")
            operations_json = result_json.get("operations", [])

            # BUILD-040: Auto-convert full-file format to structured_edit format
            # If LLM produced {"files": [...]} instead of {"operations": [...]}, convert it
            if not operations_json and "files" in result_json:
                logger.info(
                    "[Builder] Detected full-file format in structured_edit mode - auto-converting to operations"
                )
                files_json = result_json.get("files", [])
                operations_json = []

                for file_entry in files_json:
                    file_path = file_entry.get("path")
                    mode = file_entry.get("mode", "modify")
                    new_content = file_entry.get("new_content")

                    if not file_path:
                        continue

                    if mode == "create" and new_content:
                        # Convert "create" to prepend operation (which creates file if missing)
                        # Using prepend instead of insert to handle non-existent files
                        operations_json.append(
                            {"type": "prepend", "file_path": file_path, "content": new_content}
                        )
                        logger.info(
                            f"[Builder] Converted create file '{file_path}' to prepend operation"
                        )
                    elif mode == "delete":
                        # For delete, we need to know file line count
                        # Since we don't have it here, skip delete conversions
                        # DELETE mode is rare for restoration tasks anyway
                        logger.warning(
                            f"[Builder] Skipping delete mode conversion for '{file_path}' (not supported)"
                        )
                        continue
                    elif mode == "modify" and new_content:
                        # Convert "modify" to replace operation (whole file)
                        # Check if file exists in context to get line count
                        file_exists = file_path in files
                        if file_exists:
                            # Get actual line count from existing file
                            existing_content = files.get(file_path, "")
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
                                    f"[Builder] Converted modify file '{file_path}' to replace operation (lines 1-{line_count})"
                                )
                            else:
                                logger.warning(
                                    f"[Builder] Skipping modify for '{file_path}' (existing content not string)"
                                )
                        else:
                            # File doesn't exist, treat as create (use prepend)
                            operations_json.append(
                                {"type": "prepend", "file_path": file_path, "content": new_content}
                            )
                            logger.info(
                                f"[Builder] Converted modify non-existent file '{file_path}' to prepend operation (create)"
                            )

                if operations_json:
                    logger.info(
                        f"[Builder] Format conversion successful: {len(operations_json)} operations generated"
                    )
                else:
                    logger.warning("[Builder] Format conversion produced no operations")

            if not operations_json:
                # Treat empty structured edits as a safe no-op rather than a hard failure.
                info_msg = "Structured edit produced no operations; treating as no-op"
                logger.warning(f"[Builder] {info_msg}")
                return StructuredEditParseResult(
                    success=True,
                    edit_plan=None,
                    summary=summary,
                    operations_count=0,
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    error=None,
                )

            # Parse operations
            operations = []
            for i, op_json in enumerate(operations_json):
                try:
                    op = EditOperation(
                        type=EditOperationType(op_json.get("type")),
                        file_path=op_json.get("file_path"),
                        line=op_json.get("line"),
                        content=op_json.get("content"),
                        start_line=op_json.get("start_line"),
                        end_line=op_json.get("end_line"),
                        context_before=op_json.get("context_before"),
                        context_after=op_json.get("context_after"),
                    )

                    # Validate operation
                    is_valid, error = op.validate()
                    if not is_valid:
                        error_msg = f"Operation {i} invalid: {error}"
                        logger.error(f"[Builder] {error_msg}")
                        return StructuredEditParseResult(
                            success=False,
                            edit_plan=None,
                            summary=summary,
                            operations_count=0,
                            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                            prompt_tokens=response.usage.input_tokens,
                            completion_tokens=response.usage.output_tokens,
                            error=error_msg,
                        )

                    operations.append(op)

                except Exception as e:
                    error_msg = f"Failed to parse operation {i}: {str(e)}"
                    logger.error(f"[Builder] {error_msg}")
                    return StructuredEditParseResult(
                        success=False,
                        edit_plan=None,
                        summary=summary,
                        operations_count=0,
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        error=error_msg,
                    )

            # Create edit plan
            edit_plan = EditPlan(summary=summary, operations=operations)

            # Validate plan
            is_valid, error = edit_plan.validate()
            if not is_valid:
                error_msg = f"Invalid edit plan: {error}"
                logger.error(f"[Builder] {error_msg}")
                return StructuredEditParseResult(
                    success=False,
                    edit_plan=None,
                    summary=summary,
                    operations_count=len(operations),
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    error=error_msg,
                )

            # Store edit plan in result
            logger.info(
                f"[Builder] Generated structured edit plan with {len(operations)} operations"
            )

            return StructuredEditParseResult(
                success=True,
                edit_plan=edit_plan,
                summary=summary,
                operations_count=len(operations),
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                error=None,
                stop_reason=stop_reason,
                was_truncated=was_truncated,
            )

        except Exception as e:
            logger.error(f"[Builder] Error parsing structured edit output: {e}")
            return StructuredEditParseResult(
                success=False,
                edit_plan=None,
                summary="",
                operations_count=0,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                error=str(e),
            )
