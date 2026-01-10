"""
Continuation-Based Recovery for BUILD-129 Phase 2.

Handles truncation by continuing from last completed marker instead of regenerating everything.
Per TOKEN_BUDGET_ANALYSIS_REVISED.md: "Continuation is cheaper and faster than regeneration."

GPT-5.2 Priority: HIGHEST - recovers 95% of truncation failures.
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class ContinuationContext:
    """Context for continuation recovery."""

    completed_files: List[str]  # Files successfully completed before truncation
    last_partial_file: Optional[str]  # File that was partially written
    remaining_deliverables: List[str]  # Deliverables not yet started
    partial_output: str  # The truncated output
    tokens_used: int  # Tokens used in truncated attempt
    format_type: str  # "diff" or "full_file" or "ndjson"


class ContinuationRecovery:
    """
    Handles truncation recovery via continuation.

    Per GPT-5.2 Layer 2: When truncation occurs at 95% completion,
    the best retry is "continue from last marker", not "regenerate everything."

    Example:
        Attempt 1: Generate 12 files → truncates at file #11 (95% done)
        Continuation: "Continue from file #11" → completes files #11-12 (SUCCESS)

    Without continuation:
        Attempt 2: Regenerate all 12 files from scratch → truncates at file #10 (FAIL)
    """

    def __init__(self):
        """Initialize continuation recovery."""
        pass

    def detect_truncation_context(
        self,
        raw_output: str,
        deliverables: List[str],
        stop_reason: Optional[str] = None,
        tokens_used: int = 0,
    ) -> Optional[ContinuationContext]:
        """
        Detect if output was truncated and extract continuation context.

        Args:
            raw_output: The raw LLM output (potentially truncated)
            deliverables: List of expected deliverables
            stop_reason: Stop reason from API (e.g., "max_tokens", "stop_sequence")
            tokens_used: Tokens used in this attempt

        Returns:
            ContinuationContext if truncation detected, None otherwise
        """
        # Check if truncation occurred
        if stop_reason != "max_tokens":
            logger.debug(
                "[ContinuationRecovery] No truncation detected (stop_reason=%s)", stop_reason
            )
            return None

        logger.info("[ContinuationRecovery] Truncation detected (stop_reason=max_tokens)")

        # Detect format type
        format_type = self._detect_format(raw_output)
        logger.info(f"[ContinuationRecovery] Detected format: {format_type}")

        # Parse based on format
        if format_type == "diff":
            return self._parse_diff_truncation(raw_output, deliverables, tokens_used)
        elif format_type == "full_file":
            return self._parse_full_file_truncation(raw_output, deliverables, tokens_used)
        elif format_type == "ndjson":
            return self._parse_ndjson_truncation(raw_output, deliverables, tokens_used)
        else:
            logger.warning(f"[ContinuationRecovery] Unknown format type: {format_type}")
            return None

    def _detect_format(self, output: str) -> str:
        """Detect output format from content."""
        if "diff --git" in output:
            return "diff"
        # Check for NDJSON (newline-delimited JSON) - has newlines between objects
        elif "\n{" in output and '"op"' in output:
            return "ndjson"
        elif output.strip().startswith('{"meta":') or (
            output.strip().startswith('{"op":') and "\n{" in output
        ):
            return "ndjson"
        # Full-file JSON (single array or object)
        elif output.strip().startswith("[") and ("file_path" in output or "path" in output):
            return "full_file"
        elif output.strip().startswith("{") and ("file_path" in output or "path" in output):
            return "full_file"
        else:
            return "unknown"

    def _parse_diff_truncation(
        self, output: str, deliverables: List[str], tokens_used: int
    ) -> ContinuationContext:
        """
        Parse truncated diff format output.

        Finds last complete "diff --git" block to determine what was successfully completed.
        """
        # Find all complete diff blocks
        re.findall(r"diff --git a/(.*?) b/\1.*?(?=diff --git|$)", output, re.DOTALL)

        # Extract completed file paths
        completed_files = []
        for match in re.finditer(r"diff --git a/(.*?) b/\1", output):
            filepath = match.group(1)
            completed_files.append(filepath)

        # Find last partial file (incomplete diff block)
        last_partial = None
        if completed_files:
            # Check if last diff block is complete
            last_file = completed_files[-1]
            # Look for the diff block ending patterns
            last_block_pattern = f"diff --git a/{re.escape(last_file)} b/{re.escape(last_file)}.*"
            last_block_match = re.search(last_block_pattern, output, re.DOTALL)

            if last_block_match:
                last_block = last_block_match.group(0)
                # Check if ends mid-block (truncated)
                if not last_block.rstrip().endswith(("+", "-", " ", "@")):
                    # Block seems incomplete, mark as partial
                    last_partial = last_file
                    completed_files = completed_files[:-1]  # Remove from completed

        # Determine remaining deliverables
        completed_set = set(completed_files)
        remaining = [d for d in deliverables if not any(comp in d for comp in completed_set)]

        logger.info(
            f"[ContinuationRecovery:Diff] Completed {len(completed_files)} files, "
            f"partial={last_partial}, remaining={len(remaining)}"
        )

        return ContinuationContext(
            completed_files=completed_files,
            last_partial_file=last_partial,
            remaining_deliverables=remaining,
            partial_output=output,
            tokens_used=tokens_used,
            format_type="diff",
        )

    def _parse_full_file_truncation(
        self, output: str, deliverables: List[str], tokens_used: int
    ) -> ContinuationContext:
        """
        Parse truncated full-file format output.

        Looks for complete JSON objects with file_path/path keys.
        Uses incremental parsing to handle truncation gracefully (P1.5).
        """
        completed_files = []
        last_partial_file = None

        try:
            import json

            stripped = output.strip()

            # Try to parse as JSON array using incremental approach
            if stripped.startswith("["):
                completed_files, last_partial_file = self._incremental_parse_json_array(stripped)
            # Handle single object case
            elif stripped.startswith("{"):
                try:
                    obj = json.loads(stripped)
                    path = obj.get("file_path") or obj.get("path")
                    if path:
                        completed_files.append(path)
                except json.JSONDecodeError:
                    # Try to extract path from partial object
                    last_partial_file = self._extract_path_from_partial_object(stripped)

        except Exception as e:
            logger.warning(f"[ContinuationRecovery:FullFile] JSON parsing failed: {e}")

        # Determine remaining
        completed_set = set(completed_files) if completed_files else set()
        remaining = [d for d in deliverables if not any(comp in d for comp in completed_set)]

        logger.info(
            f"[ContinuationRecovery:FullFile] Completed {len(completed_files)} files, "
            f"partial={last_partial_file}, remaining={len(remaining)}"
        )

        return ContinuationContext(
            completed_files=completed_files,
            last_partial_file=last_partial_file,
            remaining_deliverables=remaining,
            partial_output=output,
            tokens_used=tokens_used,
            format_type="full_file",
        )

    def _parse_ndjson_truncation(
        self, output: str, deliverables: List[str], tokens_used: int
    ) -> ContinuationContext:
        """
        Parse truncated NDJSON format output.

        NDJSON is newline-delimited JSON, so we can easily find complete operations.
        """
        completed_files = []

        # Parse line by line
        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue

            try:
                import json

                obj = json.loads(line)
                # Extract file path from operation
                if "path" in obj:
                    completed_files.append(obj["path"])
                elif "file_path" in obj:
                    completed_files.append(obj["file_path"])
            except json.JSONDecodeError:
                # Last line might be truncated mid-JSON
                logger.debug("[ContinuationRecovery:NDJSON] Skipping incomplete line")
                break

        # Determine remaining
        completed_set = set(completed_files)
        remaining = [d for d in deliverables if not any(comp in d for comp in completed_set)]

        logger.info(
            f"[ContinuationRecovery:NDJSON] Completed {len(completed_files)} operations, "
            f"remaining={len(remaining)}"
        )

        return ContinuationContext(
            completed_files=completed_files,
            last_partial_file=None,  # NDJSON makes partial detection easy
            remaining_deliverables=remaining,
            partial_output=output,
            tokens_used=tokens_used,
            format_type="ndjson",
        )

    def build_continuation_prompt(self, context: ContinuationContext, original_prompt: str) -> str:
        """
        Build continuation prompt from truncation context.

        Args:
            context: Truncation context
            original_prompt: The original prompt that was truncated

        Returns:
            Modified prompt for continuation
        """
        completed_count = len(context.completed_files)
        remaining_count = len(context.remaining_deliverables)

        logger.info(
            f"[ContinuationRecovery] Building continuation prompt: "
            f"{completed_count} completed, {remaining_count} remaining"
        )

        # Build continuation instruction
        if context.format_type == "diff":
            format_instruction = "Continue generating git diff format patches."
        elif context.format_type == "full_file":
            format_instruction = "Continue generating full-file JSON operations."
        elif context.format_type == "ndjson":
            format_instruction = "Continue generating NDJSON operations (one JSON object per line)."
        else:
            format_instruction = "Continue generating the output."

        # List what's been completed
        if context.completed_files:
            completed_list = "\n".join(f"  - {f}" for f in context.completed_files[:5])
            if len(context.completed_files) > 5:
                completed_list += f"\n  - ... and {len(context.completed_files) - 5} more"
            completed_section = f"\n\nAlready completed:\n{completed_list}"
        else:
            completed_section = ""

        # List what remains
        if context.remaining_deliverables:
            remaining_list = "\n".join(f"  - {d}" for d in context.remaining_deliverables[:10])
            if len(context.remaining_deliverables) > 10:
                remaining_list += f"\n  - ... and {len(context.remaining_deliverables) - 10} more"
            remaining_section = f"\n\nRemaining to complete:\n{remaining_list}"
        else:
            remaining_section = (
                "\n\n(All deliverables appear to be completed - please finish any partial work)"
            )

        # Build continuation prompt
        continuation_prompt = f"""
CONTINUATION REQUEST - Previous attempt was truncated at {completed_count}/{completed_count + remaining_count} files.

{format_instruction}

IMPORTANT: Only generate the remaining files listed below. Do NOT regenerate already-completed files.
{completed_section}
{remaining_section}

Continue from where the previous attempt was truncated. Generate ONLY the remaining deliverables.
"""

        # Prepend continuation instruction to original prompt
        # Remove any previous continuation markers
        base_prompt = re.sub(
            r"CONTINUATION REQUEST.*?Continue from where.*?$",
            "",
            original_prompt,
            flags=re.DOTALL | re.MULTILINE,
        ).strip()

        return continuation_prompt + "\n\n" + base_prompt

    def merge_outputs(self, partial_output: str, continuation_output: str, format_type: str) -> str:
        """
        Merge partial output and continuation output.

        Args:
            partial_output: The truncated output from first attempt
            continuation_output: The continuation output
            format_type: Format type ("diff", "full_file", "ndjson")

        Returns:
            Merged complete output
        """
        if format_type == "diff":
            return self._merge_diff_outputs(partial_output, continuation_output)
        elif format_type == "full_file":
            return self._merge_full_file_outputs(partial_output, continuation_output)
        elif format_type == "ndjson":
            return self._merge_ndjson_outputs(partial_output, continuation_output)
        else:
            logger.warning(f"[ContinuationRecovery] Unknown format for merge: {format_type}")
            return partial_output + "\n\n" + continuation_output

    def _merge_diff_outputs(self, partial: str, continuation: str) -> str:
        """Merge diff format outputs."""
        # Find last complete diff block in partial
        # Remove any incomplete trailing diff header
        partial_clean = partial.rstrip()

        # Check if partial ends with an incomplete diff header
        # Pattern: ends with "diff --git a/..." but no actual content after it
        last_diff_match = None
        for match in re.finditer(r"(diff --git a/.*? b/.*?)$", partial_clean, re.MULTILINE):
            last_diff_match = match

        if last_diff_match:
            # Check if there's content after this diff header
            after_header = partial_clean[last_diff_match.end() :]
            # If very little content after header (< 50 chars), it's probably incomplete
            if len(after_header.strip()) < 50:
                # Remove incomplete diff header
                partial_clean = partial_clean[: last_diff_match.start()].rstrip()
                logger.debug("[ContinuationRecovery] Removed incomplete diff header from partial")

        # Merge
        merged = partial_clean + "\n" + continuation.lstrip()
        return merged

    def _merge_full_file_outputs(self, partial: str, continuation: str) -> str:
        """Merge full-file JSON outputs."""
        # Try to parse both as JSON arrays and merge
        try:
            import json

            # Parse partial (may be incomplete array)
            partial_ops = []
            if partial.strip().startswith("["):
                last_complete = partial.rfind("},")
                if last_complete != -1:
                    partial_array = partial[: last_complete + 1] + "]"
                    partial_ops = json.loads(partial_array)

            # Parse continuation
            continuation_ops = []
            if continuation.strip().startswith("["):
                continuation_ops = json.loads(continuation)

            # Merge
            merged_ops = partial_ops + continuation_ops
            return json.dumps(merged_ops, indent=2)

        except Exception as e:
            logger.warning(
                f"[ContinuationRecovery] JSON merge failed: {e}, using simple concatenation"
            )
            return partial + "\n" + continuation

    def _merge_ndjson_outputs(self, partial: str, continuation: str) -> str:
        """Merge NDJSON outputs."""
        # NDJSON is simple: just concatenate lines
        # Remove any incomplete last line from partial
        partial_lines = partial.strip().split("\n")

        # Check if last line is complete JSON
        if partial_lines:
            try:
                import json

                json.loads(partial_lines[-1])
                # Last line is complete
                complete_partial = "\n".join(partial_lines)
            except json.JSONDecodeError:
                # Last line incomplete, remove it
                complete_partial = "\n".join(partial_lines[:-1])
        else:
            complete_partial = ""

        # Merge
        merged = complete_partial + "\n" + continuation.strip()
        return merged

    # =========================================================================
    # P1.5: Robust incremental JSON parsing helpers
    # =========================================================================

    def _incremental_parse_json_array(self, json_str: str) -> Tuple[List[str], Optional[str]]:
        """
        Incrementally parse a JSON array, extracting complete objects.

        Uses bracket/brace counting to find complete objects without requiring
        the entire array to be valid JSON. This handles truncation gracefully.

        Args:
            json_str: Potentially truncated JSON array string

        Returns:
            Tuple of (completed_file_paths, last_partial_file_path)
        """
        import json

        completed_files: List[str] = []
        last_partial_file: Optional[str] = None

        # Skip the opening bracket
        if not json_str.startswith("["):
            return completed_files, last_partial_file

        pos = 1  # Start after '['
        length = len(json_str)

        while pos < length:
            # Skip whitespace and commas
            while pos < length and json_str[pos] in " \t\n\r,":
                pos += 1

            if pos >= length:
                break

            # Check for array end
            if json_str[pos] == "]":
                break

            # Find start of object
            if json_str[pos] != "{":
                pos += 1
                continue

            # Find the end of this object using bracket counting
            obj_start = pos
            obj_end = self._find_object_end(json_str, pos)

            if obj_end == -1:
                # Object is incomplete (truncated)
                # Try to extract path from partial object
                partial_obj = json_str[obj_start:]
                last_partial_file = self._extract_path_from_partial_object(partial_obj)
                break

            # Extract and parse the complete object
            obj_str = json_str[obj_start : obj_end + 1]
            try:
                obj = json.loads(obj_str)
                path = obj.get("file_path") or obj.get("path")
                if path:
                    completed_files.append(path)
            except json.JSONDecodeError:
                # Shouldn't happen if bracket counting is correct, but be safe
                logger.debug(f"[ContinuationRecovery] Failed to parse object: {obj_str[:50]}...")

            pos = obj_end + 1

        return completed_files, last_partial_file

    def _find_object_end(self, json_str: str, start: int) -> int:
        """
        Find the position of the closing brace for an object.

        Uses bracket/brace counting to handle nested structures and strings.

        Args:
            json_str: The JSON string
            start: Position of the opening brace '{'

        Returns:
            Position of matching closing brace '}', or -1 if not found (truncated)
        """
        depth = 0
        in_string = False
        escape_next = False
        pos = start
        length = len(json_str)

        while pos < length:
            char = json_str[pos]

            if escape_next:
                escape_next = False
                pos += 1
                continue

            if char == "\\":
                escape_next = True
                pos += 1
                continue

            if char == '"':
                in_string = not in_string
                pos += 1
                continue

            if in_string:
                pos += 1
                continue

            # Not in string, count braces
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return pos

            pos += 1

        # Reached end without finding closing brace
        return -1

    def _extract_path_from_partial_object(self, partial_obj: str) -> Optional[str]:
        """
        Extract file_path or path from a partial/truncated JSON object.

        Uses regex to find the path even if the object is incomplete.

        Args:
            partial_obj: Potentially truncated JSON object string

        Returns:
            The extracted path, or None if not found
        """
        # Try to find "file_path": "..." or "path": "..."
        # Handle escaped quotes in values

        # Pattern for file_path
        match = re.search(r'"file_path"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', partial_obj)
        if match:
            # Unescape the path
            return match.group(1).encode().decode("unicode_escape")

        # Pattern for path
        match = re.search(r'"path"\s*:\s*"([^"\\]*(?:\\.[^"\\]*)*)"', partial_obj)
        if match:
            return match.group(1).encode().decode("unicode_escape")

        return None
