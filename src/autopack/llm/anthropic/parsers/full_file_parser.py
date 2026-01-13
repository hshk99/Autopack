"""Full file format parser for Anthropic Builder responses.

Extracted from anthropic_clients.py lines 389-1432 as part of PR-CLIENT-2.
Handles parsing of full-file replacement JSON format with local diff generation.

Per GPT_RESPONSE10: LLM outputs complete file content, we generate diff.
Per GPT_RESPONSE11: Added guards for large files, churn, and symbol validation.
Per IMPLEMENTATION_PLAN2.md Phase 4: Added read-only enforcement and shrinkage/growth detection.
"""

import json
import logging
import difflib
import re
import subprocess
import tempfile
from typing import Optional, Dict, Any
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FullFileParseResult:
    """Result of full file parsing."""

    success: bool
    patch_content: str
    summary: str
    tokens_used: int
    prompt_tokens: int
    completion_tokens: int
    error: Optional[str] = None
    stop_reason: Optional[str] = None
    was_truncated: bool = False


class FullFileParser:
    """Parses full-file replacement format Builder responses.

    Full-file format provides complete file contents in JSON, and diff is generated locally.

    Responsibilities:
    1. Parse JSON with nested validation helpers
    2. Handle malformed JSON with repair attempts
    3. Validate pack YAML files
    4. Enforce read-only file constraints
    5. Detect suspicious shrinkage/growth
    6. Perform churn and symbol validation for small fixes
    7. Generate unified diffs locally using git
    """

    def __init__(self):
        """Initialize parser with helper methods."""
        pass

    def _escape_newlines_in_json_strings(self, raw: str) -> str:
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

    def _attempt_json_parse(self, candidate: Optional[str]) -> Optional[Dict[str, Any]]:
        """Attempt to parse JSON with newline repair fallback."""
        if not candidate:
            return None
        try:
            return json.loads(candidate.strip())
        except json.JSONDecodeError:
            repaired = self._escape_newlines_in_json_strings(candidate.strip())
            try:
                return json.loads(repaired)
            except json.JSONDecodeError:
                return None

    def _decode_placeholder_string(self, raw_segment: str) -> str:
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

    def _sanitize_full_file_output(self, raw_text: Optional[str]) -> tuple[str, Dict[str, str]]:
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

    def _balance_json_brackets(self, raw_text: str) -> str:
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

    def _restore_placeholder_content(
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
                file_entry["new_content"] = self._decode_placeholder_string(raw_segment)

    def _extract_code_fence(self, raw_text: str, fence: str) -> Optional[str]:
        """Extract content from markdown code fence."""
        start = raw_text.find(fence)
        if start == -1:
            return None
        start += len(fence)
        end = raw_text.find("```", start)
        if end == -1:
            return None
        return raw_text[start:end].strip()

    def _extract_first_json_object(self, raw_text: str) -> Optional[str]:
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

    def _validate_pack_fullfile(self, file_path: str, content: str) -> Optional[str]:
        """
        Lightweight preflight for pack YAMLs in full-file mode.
        Reject obviously incomplete/truncated outputs before diff generation so the Builder can retry.
        """
        if not (file_path.endswith((".yaml", ".yml")) and "backend/packs/" in file_path):
            return None

        stripped = content.lstrip()
        if not stripped:
            return f"pack_fullfile_empty: {file_path} returned empty content"

        # YAML allows comments (#) before document marker (---) or keys
        # The --- document marker is optional in YAML, so we don't enforce it
        lines = stripped.split("\n")

        # Check that required top-level keys appear in the first ~50 lines
        # This catches patches that only include partial content
        first_lines = "\n".join(lines[:50])
        required_top_level = ["name:", "description:", "version:", "country:", "domain:"]
        missing_top = [k for k in required_top_level if k not in first_lines]
        if missing_top:
            return (
                f"pack_fullfile_incomplete_header: {file_path} is missing top-level keys in header: {', '.join(missing_top)}. "
                f"First 200 chars: {stripped[:200]}... "
                "You must emit the COMPLETE YAML file with ALL top-level keys, not a patch."
            )

        # Check that required sections appear somewhere in the file
        required_sections = ["categories:", "official_sources:"]
        missing_sections = [s for s in required_sections if s not in content]
        if missing_sections:
            return (
                f"pack_fullfile_missing_sections: {file_path} missing required sections: {', '.join(missing_sections)}. "
                "You must emit the COMPLETE YAML file with all required sections."
            )

        return None

    def _classify_change_type(self, phase_spec: Optional[Dict]) -> str:
        """Classify whether a phase is a small fix or large refactor.

        Per GPT_RESPONSE11 Q4: Use phase metadata to classify.

        Args:
            phase_spec: Phase specification

        Returns:
            "small_fix" or "large_refactor"
        """
        if not phase_spec:
            return "small_fix"  # Default to conservative

        complexity = phase_spec.get("complexity", "medium")
        num_criteria = len(phase_spec.get("acceptance_criteria", []) or [])
        scope_cfg = phase_spec.get("scope") or {}
        scope_paths = scope_cfg.get("paths", []) if isinstance(scope_cfg, dict) else []
        scope_paths = [p for p in scope_paths if isinstance(p, str)]

        # Scope-driven overrides
        if any("package-lock" in p or "yarn.lock" in p for p in scope_paths):
            return "large_refactor"
        if any("package.json" in p for p in scope_paths):
            return "large_refactor"
        if any("/packs/" in p or p.endswith((".yaml", ".yml")) for p in scope_paths):
            return "large_refactor"

        # Explicit override
        if phase_spec.get("change_size") == "large_refactor":
            return "large_refactor"
        if phase_spec.get("allow_symbol_removal"):
            return "large_refactor"

        # Heuristic per GPT2
        if complexity == "low":
            return "small_fix"
        elif complexity == "medium" and num_criteria <= 3:
            return "small_fix"
        else:
            return "large_refactor"

    def _calculate_churn_percent(self, old_content: str, new_content: str) -> float:
        """Calculate the percentage of lines changed between old and new content.

        Per GPT_RESPONSE11 Q4: Compute churn from patch characteristics.

        Args:
            old_content: Original file content
            new_content: New file content

        Returns:
            Percentage of lines changed (0-100)
        """
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()

        if not old_lines:
            return 100.0  # All new content

        # Use SequenceMatcher to count changed lines
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)

        # Count lines that are different
        changed_lines = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "replace":
                changed_lines += max(i2 - i1, j2 - j1)
            elif tag == "delete":
                changed_lines += i2 - i1
            elif tag == "insert":
                changed_lines += j2 - j1

        churn_percent = 100.0 * changed_lines / max(len(old_lines), 1)
        return churn_percent

    def _check_missing_symbols(
        self, old_content: str, new_content: str, file_path: str
    ) -> Optional[str]:
        """Check if any required top-level symbols are missing after full-file replacement.

        Per GPT_RESPONSE11 Q5: Symbol validation for small fixes.

        Args:
            old_content: Original file content
            new_content: New file content
            file_path: Path to the file (for language detection)

        Returns:
            Comma-separated list of missing symbols, or None if all present
        """
        # Only validate Python files for now
        if not file_path.endswith(".py"):
            return None

        # Extract top-level function and class definitions
        def extract_symbols(content: str) -> set:
            symbols = set()
            # Match top-level def and class (not indented)
            for match in re.finditer(r"^(def|class)\s+(\w+)", content, re.MULTILINE):
                symbols.add(match.group(2))
            return symbols

        old_symbols = extract_symbols(old_content)
        new_symbols = extract_symbols(new_content)

        # Find missing symbols
        missing = old_symbols - new_symbols

        if missing:
            # Log warning for large refactors, error for small fixes
            logger.warning(f"[Builder] Symbols removed from {file_path}: {missing}")
            return ", ".join(sorted(missing))

        return None

    def _generate_unified_diff(self, file_path: str, old_content: str, new_content: str) -> str:
        """Generate a unified diff from old and new file content.

        Per GPT_RESPONSE10: Generate git-compatible diff locally, not by LLM.
        Per GPT_RESPONSE12 Q3: Fixed format for new/deleted files with /dev/null.

        Args:
            file_path: Path to the file
            old_content: Original file content (empty for new files)
            new_content: New file content (empty for deleted files)

        Returns:
            Unified diff string in git format
        """
        # Determine file mode: new, deleted, or modified
        is_new_file = not old_content and bool(new_content)
        is_deleted_file = bool(old_content) and not new_content

        # Safety: if we think this is a "new file" but it already exists on disk,
        # treat this as a modification instead of emitting `new file mode`.
        # This avoids governed-apply rejecting the patch as unsafe.
        if is_new_file:
            try:
                existing_path = Path(file_path)
                if existing_path.exists():
                    logger.warning(
                        f"[Builder] Diff generation: {file_path} exists but old_content empty; "
                        "treating as modify (not new file mode)"
                    )
                    old_content = existing_path.read_text(encoding="utf-8", errors="ignore")
                    is_new_file = False
                    is_deleted_file = False
            except Exception as e:
                logger.warning(
                    f"[Builder] Diff generation: could not read existing file {file_path} to avoid new-file mode: {e}"
                )

        # Construct git-format diff header (per GPT_RESPONSE12 Q3)
        # Order matters: diff --git, new/deleted file mode, index, ---, +++
        git_header = [f"diff --git a/{file_path} b/{file_path}"]

        if is_new_file:
            git_header.extend(
                [
                    "new file mode 100644",
                    "index 0000000..1111111",
                    "--- /dev/null",
                    f"+++ b/{file_path}",
                ]
            )
        elif is_deleted_file:
            git_header.extend(
                [
                    "deleted file mode 100644",
                    "index 1111111..0000000",
                    f"--- a/{file_path}",
                    "+++ /dev/null",
                ]
            )
        else:
            git_header.extend(
                [
                    "index 1111111..2222222 100644",
                    f"--- a/{file_path}",
                    f"+++ b/{file_path}",
                ]
            )

        # Generate reliable diff body via git --no-index to avoid malformed hunks
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_dir = Path(tmpdir)
            old_file = temp_dir / "old_file"
            new_file = temp_dir / "new_file"

            old_file.write_text(old_content, encoding="utf-8")
            new_file.write_text(new_content, encoding="utf-8")

            diff_cmd = [
                "git",
                "--no-pager",
                "diff",
                "--no-index",
                "--text",
                "--unified=3",
                "--",
                str(old_file),
                str(new_file),
            ]

            proc = subprocess.run(
                diff_cmd,
                capture_output=True,
                text=False,  # Decode manually to avoid locale-dependent errors
            )

            stderr_text = ""
            if proc.stderr:
                stderr_text = proc.stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode not in (0, 1):
                logger.error(f"[BuilderDiff] git diff failed: {stderr_text}")
                raise RuntimeError("git diff --no-index failed while generating builder patch")

            diff_stdout = proc.stdout.decode("utf-8", errors="replace")
            diff_output = diff_stdout.strip()
            if not diff_output:
                return ""

        diff_lines = diff_output.splitlines()

        # Drop git's own metadata lines (diff --git, index, ---/+++)
        body_lines = []
        started = False
        for line in diff_lines:
            if line.startswith("@@") or started:
                started = True
                body_lines.append(line)

        if not body_lines:
            return ""

        full_diff = git_header + body_lines

        return "\n".join(full_diff)

    def parse(
        self,
        content: str,
        file_context: Optional[Dict],
        response: Any,
        model: str,
        phase_spec: Optional[Dict] = None,
        config: Optional[Any] = None,
        stop_reason: Optional[str] = None,
        was_truncated: bool = False,
    ) -> FullFileParseResult:
        """Parse full-file replacement output and generate git diff locally.

        Extracted from anthropic_clients.py lines 389-1182.

        Args:
            content: Raw LLM output (should be JSON)
            file_context: Original file contents for diff generation
            response: API response object for token usage
            model: Model identifier
            phase_spec: Phase specification for churn classification
            config: BuilderOutputConfig for thresholds
            stop_reason: Stop reason from LLM
            was_truncated: Whether output was truncated

        Returns:
            FullFileParseResult with generated patch or error
        """
        from autopack.builder_config import BuilderOutputConfig
        from autopack.repair_helpers import JsonRepairHelper, save_repair_debug

        # Load config if not provided
        if config is None:
            config = BuilderOutputConfig()

        try:
            # Try to parse JSON directly, with newline repair fallback
            result_json: Optional[Dict[str, Any]] = None
            placeholder_map: Dict[str, str] = {}
            raw = content.strip()

            candidates: list[str] = [raw]

            # Format guard: if the raw output looks like a git diff, bail out early
            # and request regeneration instead of trying to parse/apply malformed diffs.
            if "diff --git" in raw and "{" not in raw:  # heuristic: no JSON object present
                error_msg = (
                    "Detected git diff output; expected JSON with 'files' array. "
                    "Regenerate a JSON full-file response (no diff, no markdown fences)."
                )
                logger.error(error_msg)
                return FullFileParseResult(
                    success=False,
                    patch_content="",
                    summary="",
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    error="full_file_parse_failed_diff_detected",
                )
            if "```json" in content:
                fenced = self._extract_code_fence(content, "```json")
                if fenced:
                    candidates.append(fenced)
            if "```" in content:
                fenced_generic = self._extract_code_fence(content, "```")
                if fenced_generic:
                    candidates.append(fenced_generic)
            extracted = self._extract_first_json_object(raw)
            if extracted:
                candidates.append(extracted)

            for candidate in candidates:
                sanitized_candidate, placeholders = self._sanitize_full_file_output(candidate)
                balanced_candidate = self._balance_json_brackets(sanitized_candidate)
                result_json = self._attempt_json_parse(balanced_candidate)
                if result_json:
                    placeholder_map = placeholders
                    break

            if not result_json:
                # Do NOT fall back to legacy git-diff; request regeneration instead
                logger.warning(
                    "[Builder] WARNING: Full-file JSON parse failed; requesting regeneration (no legacy diff fallback)"
                )
                debug_path = Path("builder_fullfile_failure_latest.json")
                try:
                    debug_path.write_text(content, encoding="utf-8")
                    logger.warning(f"[Builder] Wrote failing full-file output to {debug_path}")
                except Exception as write_exc:
                    logger.error(f"[Builder] Failed to write debug output: {write_exc}")
                # Attempt JSON repair before giving up (per ref2.md recommendations)
                logger.info("[Builder] Attempting JSON repair on malformed output...")
                json_repair = JsonRepairHelper()
                initial_error = "Failed to parse JSON with 'files' array"
                repaired_json, repair_method = json_repair.attempt_repair(content, initial_error)

                if repaired_json is not None:
                    logger.info(f"[Builder] JSON repair succeeded via {repair_method}")
                    # Save debug info for telemetry
                    save_repair_debug(
                        file_path="builder_output.json",
                        original="",
                        attempted=content,
                        repaired=json.dumps(repaired_json),
                        error=initial_error,
                        method=repair_method,
                    )
                    # Use the repaired JSON
                    result_json = repaired_json
                    placeholder_map = {}  # Placeholders already processed in raw content
                else:
                    # Save failed repair attempt for debugging
                    save_repair_debug(
                        file_path="builder_output.json",
                        original="",
                        attempted=content,
                        repaired=None,
                        error=initial_error,
                        method=repair_method,
                    )
                    error_msg = "LLM output invalid format - expected JSON with 'files' array (repair also failed)"
                    # Include truncation info so autonomous_executor can trigger structured_edit fallback
                    if was_truncated:
                        error_msg += " (stop_reason=max_tokens)"
                    logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                    return FullFileParseResult(
                        success=False,
                        patch_content="",
                        summary="",
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        error=(
                            "full_file_parse_failed"
                            if not was_truncated
                            else "full_file_parse_failed (stop_reason=max_tokens)"
                        ),
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )

            summary = result_json.get("summary", "Generated by Claude")
            if placeholder_map:
                self._restore_placeholder_content(result_json, placeholder_map)
            files = result_json.get("files", [])

            if not files:
                error_msg = "LLM returned empty files array"
                if was_truncated:
                    error_msg += " (stop_reason=max_tokens)"
                return FullFileParseResult(
                    success=False,
                    patch_content="",
                    summary=summary,
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    error=error_msg,
                    stop_reason=stop_reason,
                    was_truncated=was_truncated,
                )

            # Schema validation for file entries
            required_keys = {"path", "mode", "new_content"}
            for entry in files:
                if not isinstance(entry, dict) or not required_keys.issubset(entry.keys()):
                    error_msg = (
                        "LLM output invalid format - each file entry must include "
                        "`path`, `mode`, and `new_content`. Regenerate JSON."
                    )
                    if was_truncated:
                        error_msg += " (stop_reason=max_tokens)"
                    logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                    return FullFileParseResult(
                        success=False,
                        patch_content="",
                        summary=summary,
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        error=(
                            "full_file_schema_invalid"
                            if not was_truncated
                            else "full_file_schema_invalid (stop_reason=max_tokens)"
                        ),
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )

            # Determine change type for churn validation (per GPT_RESPONSE11 Q4)
            change_type = self._classify_change_type(phase_spec)

            # Generate unified diff for each file
            diff_parts = []
            attempted_file_paths = []  # BUILD-141 Part 8: Track files Builder attempted to modify
            existing_files = {}
            if file_context:
                existing_files = file_context.get("existing_files", file_context)
                # Safety check: ensure existing_files is a dict
                if not isinstance(existing_files, dict):
                    existing_files = {}

            for file_entry in files:
                file_path = file_entry.get("path", "")
                mode = file_entry.get("mode", "modify")
                new_content = file_entry.get("new_content", "")

                if not file_path:
                    continue

                # BUILD-141 Part 8: Track attempted file paths for no-op detection
                attempted_file_paths.append(file_path)

                # Get original content
                old_content = existing_files.get(file_path, "")
                old_line_count = old_content.count("\n") + 1 if old_content else 0
                new_line_count = new_content.count("\n") + 1 if new_content else 0

                # Pack YAML preflight validation (per ref2.md - pack quality improvements)
                pack_validation_error = self._validate_pack_fullfile(file_path, new_content)
                if pack_validation_error:
                    logger.error(f"[Builder] {pack_validation_error}")
                    return FullFileParseResult(
                        success=False,
                        patch_content="",
                        summary=summary,
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        error=pack_validation_error,
                    )

                # ============================================================================
                # NEW: Read-only file enforcement (per IMPLEMENTATION_PLAN2.md Phase 4.1)
                # This is the PARSER-LEVEL enforcement - LLM violated the contract
                # ============================================================================
                if mode == "modify" and old_line_count > config.max_lines_for_full_file:
                    error_msg = (
                        f"readonly_violation: {file_path} has {old_line_count} lines "
                        f"(limit: {config.max_lines_for_full_file}). This file was marked as READ-ONLY CONTEXT. "
                        f"The LLM should not have attempted to modify it."
                    )
                    logger.error(f"[Builder] {error_msg}")

                    # Record telemetry (if available in context)
                    # Note: We don't have run_id/phase_id here, so we log for manual review
                    logger.warning(
                        f"[TELEMETRY] readonly_violation: file={file_path}, lines={old_line_count}, model={model}"
                    )

                    return FullFileParseResult(
                        success=False,
                        patch_content="",
                        summary=summary,
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        error=error_msg,
                    )

                # ============================================================================
                # NEW: Shrinkage detection (per IMPLEMENTATION_PLAN2.md Phase 4.2)
                # Reject >60% shrinkage unless phase allows mass deletion
                # ============================================================================
                if mode == "modify" and old_content and new_content:
                    shrinkage_percent = ((old_line_count - new_line_count) / old_line_count) * 100

                    if shrinkage_percent > config.max_shrinkage_percent:
                        # Check if phase allows mass deletion
                        allow_mass_deletion = (
                            phase_spec.get("allow_mass_deletion", False) if phase_spec else False
                        )

                        if not allow_mass_deletion:
                            error_msg = (
                                f"suspicious_shrinkage: {file_path} shrank by {shrinkage_percent:.1f}% "
                                f"({old_line_count} → {new_line_count} lines). "
                                f"Limit: {config.max_shrinkage_percent}%. "
                                f"This may indicate truncation. Set allow_mass_deletion=true to override."
                            )
                            logger.error(f"[Builder] {error_msg}")
                            logger.warning(
                                f"[TELEMETRY] suspicious_shrinkage: file={file_path}, old={old_line_count}, new={new_line_count}, shrinkage={shrinkage_percent:.1f}%"
                            )

                            return FullFileParseResult(
                                success=False,
                                patch_content="",
                                summary=summary,
                                tokens_used=response.usage.input_tokens
                                + response.usage.output_tokens,
                                prompt_tokens=response.usage.input_tokens,
                                completion_tokens=response.usage.output_tokens,
                                error=error_msg,
                            )

                # ============================================================================
                # NEW: Growth detection (per IMPLEMENTATION_PLAN2.md Phase 4.2)
                # Reject >3x growth unless phase allows mass addition
                # ============================================================================
                if mode == "modify" and old_content and new_content and old_line_count > 0:
                    growth_multiplier = new_line_count / old_line_count

                    # Optional: skip growth guard for YAML packs where large expansions are expected
                    if getattr(
                        config, "disable_growth_guard_for_yaml", False
                    ) and file_path.endswith((".yaml", ".yml")):
                        logger.info(
                            f"[Builder] Skipping growth guard for YAML file {file_path} (growth {growth_multiplier:.1f}x)"
                        )
                    else:
                        if growth_multiplier > config.max_growth_multiplier:
                            # Check if phase allows mass addition
                            allow_mass_addition = (
                                phase_spec.get("allow_mass_addition", False)
                                if phase_spec
                                else False
                            )

                            if not allow_mass_addition:
                                error_msg = (
                                    f"suspicious_growth: {file_path} grew by {growth_multiplier:.1f}x "
                                    f"({old_line_count} → {new_line_count} lines). "
                                    f"Limit: {config.max_growth_multiplier}x. "
                                    f"This may indicate duplication. Set allow_mass_addition=true to override."
                                )
                                logger.error(f"[Builder] {error_msg}")
                                logger.warning(
                                    f"[TELEMETRY] suspicious_growth: file={file_path}, old={old_line_count}, "
                                    f"new={new_line_count}, growth={growth_multiplier:.1f}x"
                                )

                                return FullFileParseResult(
                                    success=False,
                                    patch_content="",
                                    summary=summary,
                                    tokens_used=response.usage.input_tokens
                                    + response.usage.output_tokens,
                                    prompt_tokens=response.usage.input_tokens,
                                    completion_tokens=response.usage.output_tokens,
                                    error=error_msg,
                                )

                # Q4: Churn detection for small fixes
                if mode == "modify" and change_type == "small_fix" and old_content:
                    # Optional: skip small-fix churn guard for YAML packs where high churn is expected
                    if file_path.endswith(("package-lock.json", "yarn.lock", "package.json")):
                        logger.info(
                            f"[Builder] Skipping small-fix churn guard for manifest/lockfile {file_path}"
                        )
                    elif getattr(
                        config, "disable_small_fix_churn_for_yaml", False
                    ) and file_path.endswith((".yaml", ".yml")):
                        logger.info(
                            f"[Builder] Skipping small-fix churn guard for YAML file {file_path}"
                        )
                    else:
                        churn_percent = self._calculate_churn_percent(old_content, new_content)
                        if churn_percent > config.max_churn_percent_for_small_fix:
                            error_msg = f"churn_limit_exceeded: {churn_percent:.1f}% (small_fix limit {config.max_churn_percent_for_small_fix}%) on {file_path}"
                            logger.error(f"[Builder] {error_msg}")
                            return FullFileParseResult(
                                success=False,
                                patch_content="",
                                summary=summary,
                                tokens_used=response.usage.input_tokens
                                + response.usage.output_tokens,
                                prompt_tokens=response.usage.input_tokens,
                                completion_tokens=response.usage.output_tokens,
                                error=error_msg,
                            )

                # Q5: Symbol validation for small fixes
                if mode == "modify" and change_type == "small_fix" and old_content:
                    missing_symbols = self._check_missing_symbols(
                        old_content, new_content, file_path
                    )
                    if missing_symbols:
                        error_msg = f"symbol_missing_after_full_file_replacement: lost {missing_symbols} in {file_path}"
                        logger.error(f"[Builder] {error_msg}")
                        return FullFileParseResult(
                            success=False,
                            patch_content="",
                            summary=summary,
                            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                            prompt_tokens=response.usage.input_tokens,
                            completion_tokens=response.usage.output_tokens,
                            error=error_msg,
                        )

                # Generate diff based on mode
                if mode == "delete":
                    # Generate delete diff
                    diff = self._generate_unified_diff(file_path, old_content, "")
                elif mode == "create":
                    # Generate create diff
                    diff = self._generate_unified_diff(file_path, "", new_content)
                else:  # modify
                    # Generate modify diff
                    diff = self._generate_unified_diff(file_path, old_content, new_content)

                if diff:
                    diff_parts.append(diff)

            if not diff_parts:
                # BUILD-141 Part 8: Treat "no diffs" as no-op success if deliverables already exist
                # This handles idempotent phases where Builder generates content matching existing files

                # Check if all attempted files exist on disk
                # If Builder tried to modify files that already match the generated content,
                # this is a successful no-op (idempotent phase)
                repo_root = Path.cwd()  # Workspace root where autonomous executor runs

                all_files_exist = False
                if attempted_file_paths:
                    existing_count = 0
                    for path in attempted_file_paths:
                        file_path_obj = repo_root / path
                        if file_path_obj.exists() and file_path_obj.is_file():
                            existing_count += 1

                    all_files_exist = existing_count == len(attempted_file_paths)

                if all_files_exist:
                    # Idempotent phase: Builder regenerated content matching existing files
                    # This is a success - treat as no-op
                    no_op_msg = (
                        f"Full-file produced no diffs; treating as no-op success "
                        f"(all {len(attempted_file_paths)} file(s) already exist and match generated content)"
                    )
                    logger.info(f"[Builder] {no_op_msg}")

                    return FullFileParseResult(
                        success=True,  # Success, not failure!
                        patch_content="",  # Empty patch is OK for no-op
                        summary=summary,
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        stop_reason=stop_reason,
                        was_truncated=was_truncated,
                    )
                else:
                    # Deliverables don't exist or couldn't be determined - this is a real failure
                    error_msg = "No valid file changes generated"
                    return FullFileParseResult(
                        success=False,
                        patch_content="",
                        summary=summary,
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        prompt_tokens=response.usage.input_tokens,
                        completion_tokens=response.usage.output_tokens,
                        error=error_msg,
                    )

            # Join diffs defensively. Some `git apply` versions are picky about
            # patch boundaries; ensure each diff starts on a fresh line and the
            # overall patch ends with a newline to avoid "patch fragment without header".
            patch_content = "\n\n".join(d.rstrip("\n") for d in diff_parts).rstrip("\n") + "\n"
            logger.info(
                f"[Builder] Generated {len(diff_parts)} file diffs locally from full-file content"
            )

            return FullFileParseResult(
                success=True,
                patch_content=patch_content,
                summary=summary,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                stop_reason=stop_reason,
                was_truncated=was_truncated,
            )

        except Exception as e:
            error_msg = f"Failed to parse full-file output: {str(e)}"
            logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
            return FullFileParseResult(
                success=False,
                patch_content="",
                summary="",
                tokens_used=(
                    response.usage.input_tokens + response.usage.output_tokens if response else 0
                ),
                prompt_tokens=response.usage.input_tokens if response else 0,
                completion_tokens=response.usage.output_tokens if response else 0,
                error=error_msg,
            )
