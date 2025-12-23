"""
Continuation-Based Recovery for BUILD-129 Phase 2.

Handles truncation by continuing from last completed marker instead of regenerating everything.
Per TOKEN_BUDGET_ANALYSIS_REVISED.md: "Continuation is cheaper and faster than regeneration."

GPT-5.2 Priority: HIGHEST - recovers 95% of truncation failures.
"""
from dataclasses import dataclass
from typing import Optional, List, Tuple
from pathlib import Path
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
        tokens_used: int = 0
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
            logger.debug("[ContinuationRecovery] No truncation detected (stop_reason=%s)", stop_reason)
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
        elif '\n{' in output and '"op"' in output:
            return "ndjson"
        elif output.strip().startswith('{"meta":') or (output.strip().startswith('{"op":') and '\n{' in output):
            return "ndjson"
        # Full-file JSON (single array or object)
        elif output.strip().startswith("[") and ("file_path" in output or "path" in output):
            return "full_file"
        elif output.strip().startswith("{") and ("file_path" in output or "path" in output):
            return "full_file"
        else:
            return "unknown"

    def _parse_diff_truncation(
        self,
        output: str,
        deliverables: List[str],
        tokens_used: int
    ) -> ContinuationContext:
        """
        Parse truncated diff format output.

        Finds last complete "diff --git" block to determine what was successfully completed.
        """
        # Find all complete diff blocks
        diff_blocks = re.findall(
            r'diff --git a/(.*?) b/\1.*?(?=diff --git|$)',
            output,
            re.DOTALL
        )

        # Extract completed file paths
        completed_files = []
        for match in re.finditer(r'diff --git a/(.*?) b/\1', output):
            filepath = match.group(1)
            completed_files.append(filepath)

        # Find last partial file (incomplete diff block)
        last_partial = None
        if completed_files:
            # Check if last diff block is complete
            last_file = completed_files[-1]
            # Look for the diff block ending patterns
            last_block_pattern = f'diff --git a/{re.escape(last_file)} b/{re.escape(last_file)}.*'
            last_block_match = re.search(last_block_pattern, output, re.DOTALL)

            if last_block_match:
                last_block = last_block_match.group(0)
                # Check if ends mid-block (truncated)
                if not last_block.rstrip().endswith(('+', '-', ' ', '@')):
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
            format_type="diff"
        )

    def _parse_full_file_truncation(
        self,
        output: str,
        deliverables: List[str],
        tokens_used: int
    ) -> ContinuationContext:
        """
        Parse truncated full-file format output.

        Looks for complete JSON objects with file_path/path keys.
        """
        # Try to find all complete file operations
        # Pattern: {"file_path": "...", ...} or {"path": "...", ...}
        completed_files = []

        # Simple heuristic: count closing braces to find complete objects
        # This is fragile but works for basic cases
        # TODO: Use proper JSON parsing with error recovery

        try:
            import json
            # Try to parse as JSON array
            if output.strip().startswith('['):
                # Attempt to find complete objects before truncation
                # Find last complete object
                last_complete_idx = output.rfind('},')
                if last_complete_idx != -1:
                    # Try parsing up to last complete object
                    partial_array = output[:last_complete_idx + 1] + ']'
                    try:
                        parsed = json.loads(partial_array)
                        completed_files = [
                            op.get('file_path') or op.get('path')
                            for op in parsed
                            if isinstance(op, dict) and (op.get('file_path') or op.get('path'))
                        ]
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            logger.warning(f"[ContinuationRecovery:FullFile] JSON parsing failed: {e}")

        # Determine remaining
        completed_set = set(completed_files) if completed_files else set()
        remaining = [d for d in deliverables if not any(comp in d for comp in completed_set)]

        logger.info(
            f"[ContinuationRecovery:FullFile] Completed {len(completed_files)} files, "
            f"remaining={len(remaining)}"
        )

        return ContinuationContext(
            completed_files=completed_files,
            last_partial_file=None,  # Hard to detect in JSON format
            remaining_deliverables=remaining,
            partial_output=output,
            tokens_used=tokens_used,
            format_type="full_file"
        )

    def _parse_ndjson_truncation(
        self,
        output: str,
        deliverables: List[str],
        tokens_used: int
    ) -> ContinuationContext:
        """
        Parse truncated NDJSON format output.

        NDJSON is newline-delimited JSON, so we can easily find complete operations.
        """
        completed_files = []

        # Parse line by line
        for line in output.strip().split('\n'):
            line = line.strip()
            if not line:
                continue

            try:
                import json
                obj = json.loads(line)
                # Extract file path from operation
                if 'path' in obj:
                    completed_files.append(obj['path'])
                elif 'file_path' in obj:
                    completed_files.append(obj['file_path'])
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
            format_type="ndjson"
        )

    def build_continuation_prompt(
        self,
        context: ContinuationContext,
        original_prompt: str
    ) -> str:
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
            remaining_section = "\n\n(All deliverables appear to be completed - please finish any partial work)"

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
            r'CONTINUATION REQUEST.*?Continue from where.*?$',
            '',
            original_prompt,
            flags=re.DOTALL | re.MULTILINE
        ).strip()

        return continuation_prompt + "\n\n" + base_prompt

    def merge_outputs(
        self,
        partial_output: str,
        continuation_output: str,
        format_type: str
    ) -> str:
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
        for match in re.finditer(r'(diff --git a/.*? b/.*?)$', partial_clean, re.MULTILINE):
            last_diff_match = match

        if last_diff_match:
            # Check if there's content after this diff header
            after_header = partial_clean[last_diff_match.end():]
            # If very little content after header (< 50 chars), it's probably incomplete
            if len(after_header.strip()) < 50:
                # Remove incomplete diff header
                partial_clean = partial_clean[:last_diff_match.start()].rstrip()
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
            if partial.strip().startswith('['):
                last_complete = partial.rfind('},')
                if last_complete != -1:
                    partial_array = partial[:last_complete + 1] + ']'
                    partial_ops = json.loads(partial_array)

            # Parse continuation
            continuation_ops = []
            if continuation.strip().startswith('['):
                continuation_ops = json.loads(continuation)

            # Merge
            merged_ops = partial_ops + continuation_ops
            return json.dumps(merged_ops, indent=2)

        except Exception as e:
            logger.warning(f"[ContinuationRecovery] JSON merge failed: {e}, using simple concatenation")
            return partial + "\n" + continuation

    def _merge_ndjson_outputs(self, partial: str, continuation: str) -> str:
        """Merge NDJSON outputs."""
        # NDJSON is simple: just concatenate lines
        # Remove any incomplete last line from partial
        partial_lines = partial.strip().split('\n')

        # Check if last line is complete JSON
        if partial_lines:
            try:
                import json
                json.loads(partial_lines[-1])
                # Last line is complete
                complete_partial = '\n'.join(partial_lines)
            except json.JSONDecodeError:
                # Last line incomplete, remove it
                complete_partial = '\n'.join(partial_lines[:-1])
        else:
            complete_partial = ""

        # Merge
        merged = complete_partial + "\n" + continuation.strip()
        return merged
