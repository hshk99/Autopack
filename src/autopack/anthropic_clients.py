"""Anthropic Claude-based Builder and Auditor implementations

Per models.yaml configuration:
- Claude Opus 4.5 for high-risk auditing
- Claude Sonnet 4.5 for progressive strategy auditing
- Complementary to OpenAI models for dual auditing

This module provides Anthropic API integration for when
ModelRouter selects Claude models based on category/quota.
"""

import os
import json
import logging
import yaml
import copy
from pathlib import Path
from typing import Dict, List, Optional, Any

try:
    from anthropic import Anthropic
except ImportError:
    # Graceful degradation if anthropic package not installed
    Anthropic = None

from .llm_client import BuilderResult, AuditorResult
from .journal_reader import get_prevention_prompt_injection
from .llm_service import estimate_tokens
from .repair_helpers import JsonRepairHelper, save_repair_debug

logger = logging.getLogger(__name__)


# Per GPT_RESPONSE24 C1: Normalize complexity to handle variations
ALLOWED_COMPLEXITIES = {"low", "medium", "high", "maintenance"}


def normalize_complexity(value: str | None) -> str:
    """
    Normalize complexity value to canonical form.
    
    Per GPT_RESPONSE24 C1: Handle case variations, common suffixes, and aliases.
    Per GPT_RESPONSE25 C1: Log DATA_INTEGRITY for unknown values and fallback to "medium".
    
    Args:
        value: Raw complexity value from phase_spec
    
    Returns:
        Normalized complexity value (always one of ALLOWED_COMPLEXITIES)
    """
    if value is None:
        return "medium"  # Default
    
    v = value.strip().lower()
    
    # Strip common suffixes (per GPT1 and GPT2)
    for suffix in ("_complexity", "-complexity", "_level", "-level", "_mode", "-mode", "_task", "_tier"):
        if v.endswith(suffix):
            v = v[:-len(suffix)]
    
    # Map common aliases (per GPT1 and GPT2)
    alias_map = {
        "low": "low",
        "medium": "medium",
        "med": "medium",
        "high": "high",
        "maint": "maintenance",
        "maintain": "maintenance",
        "maintenance": "maintenance",
        "maintenance_mode": "maintenance",
    }
    
    normalized = alias_map.get(v, v)
    
    # Per GPT_RESPONSE25 C1: Guard for unknown values - log and fallback to "medium"
    if normalized not in ALLOWED_COMPLEXITIES:
        logger.warning(
            "[DATA_INTEGRITY] Unknown complexity value %r (normalized to %r); "
            "falling back to 'medium'. Consider adding to alias_map if valid.",
            value, normalized,
        )
        return "medium"
    
    return normalized


class AnthropicBuilderClient:
    """Builder implementation using Anthropic Claude API

    Currently used for:
    - Test generation (claude-sonnet-4-5 per models.yaml)
    - Escalation scenarios when OpenAI quota exhausted
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Anthropic client

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        """
        if Anthropic is None:
            raise ImportError(
                "anthropic package not installed. "
                "Install with: pip install anthropic"
            )

        self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    def execute_phase(
        self,
        phase_spec: Dict,
        file_context: Optional[Dict] = None,
        max_tokens: Optional[int] = None,
        model: str = "claude-sonnet-4-5",
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
        use_full_file_mode: bool = True,
        config = None  # NEW: BuilderOutputConfig for consistency
    ) -> BuilderResult:
        """Execute a phase using Claude

        Args:
            phase_spec: Phase specification
            file_context: Repository file context
            max_tokens: Token budget
            model: Claude model (claude-opus-4-5, claude-sonnet-4-5, etc.)
            project_rules: Persistent learned rules
            run_hints: Within-run hints
            use_full_file_mode: If True, use new full-file replacement format (GPT_RESPONSE10).
                               If False, use legacy git diff format (deprecated).
            config: BuilderOutputConfig instance (per IMPLEMENTATION_PLAN2.md)

        Returns:
            BuilderResult with patch and metadata
        """
        # Defensive: ensure phase_spec is always a dict
        if phase_spec is None:
            phase_spec = {}
        scope_cfg = phase_spec.get("scope") or {}
        scope_paths = scope_cfg.get("paths", []) if isinstance(scope_cfg, dict) else []
        scope_paths = [p for p in scope_paths if isinstance(p, str)]

        # Heuristic: lockfile / manifest phases need larger outputs and should be treated as large refactors
        lockfile_phase = any("package-lock" in p or "yarn.lock" in p for p in scope_paths)
        manifest_phase = any("package.json" in p for p in scope_paths)
        pack_phase = any("/packs/" in p or p.endswith((".yaml", ".yml")) for p in scope_paths)

        # Apply safe defaults based on scope
        if pack_phase:
            phase_spec.setdefault("allow_mass_addition", True)
        if lockfile_phase or manifest_phase:
            phase_spec.setdefault("change_size", "large_refactor")

        # Increase token budget when emitting larger artifacts (lockfiles, docker configs, packs)
        task_category = phase_spec.get("task_category", "")
        if max_tokens is None:
            max_tokens = 4096
        if lockfile_phase or manifest_phase:
            max_tokens = max(max_tokens, 12000)
        if task_category in ("deployment", "frontend"):
            max_tokens = max(max_tokens, 16384)
            # Deployment/frontends often touch multiple files; treat as large refactor
            phase_spec.setdefault("change_size", "large_refactor")
        if task_category == "backend" and len(scope_paths) >= 3:
            # Backend multi-file phases (e.g., API + services + tests) need larger budget
            max_tokens = max(max_tokens, 12000)

        # Adaptive: if small scope and all files are small, treat as large_refactor and allow mass addition
        if file_context:
            files = file_context.get("existing_files", {})
            if isinstance(files, dict):
                scoped_files = []
                for fp, fc in files.items():
                    if not isinstance(fp, str):
                        continue
                    if any(fp.startswith(sp) for sp in scope_paths):
                        if isinstance(fc, str):
                            scoped_files.append(fc)
                max_lines = max((c.count("\n") + 1 for c in scoped_files), default=0)
                if len(scope_paths) <= 6 and max_lines <= 500:
                    phase_spec.setdefault("change_size", "large_refactor")
                    phase_spec.setdefault("allow_mass_addition", True)

        # Adaptive mode selection: keep full-file mode for small scopes; avoid only for large multi-file scopes
        use_full_file_mode_flag = use_full_file_mode
        multi_file_scope = len(scope_paths) >= 3
        if task_category in ("deployment", "frontend"):
            multi_file_scope = True
        if multi_file_scope and use_full_file_mode_flag and len(scope_paths) > 6:
            logger.info(
                "[Builder] Disabling full-file mode due to large multi-file scope (paths=%d, category=%s)",
                len(scope_paths), task_category
            )
            use_full_file_mode_flag = False
        try:
            # Check if we need structured edit mode before building prompt
            # Structured edit should ONLY be used if files being MODIFIED exceed the limit
            # NOT if any file in context exceeds the limit
            use_structured_edit = False
            if file_context and config:
                files = file_context.get("existing_files", {})
                # Safety check: ensure files is a dict
                if not isinstance(files, dict):
                    logger.warning(f"[Builder] file_context.get('existing_files') returned non-dict: {type(files)}, using empty dict")
                    files = {}

                # Get explicit scope paths from phase_spec (guard None/empty)
                scope_config = phase_spec.get("scope") or {}
                scope_paths = scope_config.get("paths", []) if isinstance(scope_config, dict) else []
                # Safety check: ensure scope_paths is a list of strings
                if not isinstance(scope_paths, list):
                    logger.warning(f"[Builder] scope_paths is not a list: {type(scope_paths)}, using empty list")
                    scope_paths = []
                # Filter out non-string items
                scope_paths = [sp for sp in scope_paths if isinstance(sp, str)]

                # If no explicit scope, try to infer from file context
                # Only check files that will actually be modified
                if not scope_paths:
                    # If no scope defined, assume all files ≤ max_lines_for_full_file are modifiable
                    # and files > max_lines_for_full_file are read-only context
                    # Structured edit mode should NOT be triggered unless explicitly scoped
                    logger.debug("[Builder] No scope_paths defined; assuming small files are modifiable, large files are read-only")
                    use_structured_edit = False
                else:
                    # Check only files in scope
                    for file_path, content in files.items():
                        # Safety check: ensure file_path is a string
                        if not isinstance(file_path, str):
                            logger.warning(f"[Builder] Skipping non-string file_path: {file_path} (type: {type(file_path)})")
                            continue

                        # Only check if file is in scope
                        if any(file_path.startswith(sp) for sp in scope_paths):
                            if isinstance(content, str):
                                line_count = content.count('\n') + 1
                                if line_count > config.max_lines_hard_limit:
                                    logger.info(f"[Builder] File {file_path} ({line_count} lines) exceeds hard limit; enabling structured edit mode")
                                    use_structured_edit = True
                                    break
            
            # Build system prompt (with mode selection per GPT_RESPONSE10)
            system_prompt = self._build_system_prompt(
                use_full_file_mode=use_full_file_mode_flag,
                use_structured_edit=use_structured_edit
            )

            # Build user prompt (includes full file content for full-file mode or line numbers for structured edit)
            user_prompt = self._build_user_prompt(
                phase_spec, file_context, project_rules, run_hints,
                use_full_file_mode=use_full_file_mode_flag,
                config=config  # NEW: Pass config for read-only markers and structured edit detection
            )

            # Per GPT_RESPONSE23 Q2: Add sanity checks for max_tokens
            # Note: None is expected when ModelRouter decides - use default based on phase config
            builder_mode = phase_spec.get("builder_mode", "")
            change_size = phase_spec.get("change_size", "")

            # Increase max_tokens for full_file mode with large files or large_refactor changes
            # This prevents truncation of YAML pack files and other large file replacements
            if max_tokens is None:
                if builder_mode == "full_file" or change_size == "large_refactor":
                    # Large refactors need more output budget (16K tokens)
                    max_tokens = 16384
                    logger.debug(
                        "[TOKEN_EST] Using increased max_tokens=%d for builder_mode=%s change_size=%s",
                        max_tokens, builder_mode, change_size
                    )
                else:
                    max_tokens = 4096
            elif max_tokens <= 0:
                logger.warning(
                    "[TOKEN_EST] max_tokens invalid (%s); falling back to default 4096",
                    max_tokens
                )
                max_tokens = 4096
            
            # Per GPT_RESPONSE21 Q2: Estimate tokens on final prompt text (as sent to provider)
            # Build full prompt text for estimation (system + user)
            full_prompt_text = system_prompt + "\n" + user_prompt
            estimated_prompt_tokens = estimate_tokens(full_prompt_text)
            call_max_tokens = max_tokens or 64000  # Keep existing default as final fallback
            estimated_completion_tokens = int(call_max_tokens * 0.7)  # Conservative estimate (70% of max)
            estimated_total_tokens = estimated_prompt_tokens + estimated_completion_tokens
            
            # Per GPT_RESPONSE22 Q1: Breakdown at DEBUG, INFO/WARNING for cap events
            phase_id = phase_spec.get("phase_id") or "unknown"
            run_id = phase_spec.get("run_id") or "unknown"
            
            # Always log breakdown at DEBUG for telemetry
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(
                    "[TOKEN_EST] run_id=%s phase_id=%s total=%d prompt=%d completion=%d max_tokens=%d",
                    run_id, phase_id, estimated_total_tokens, estimated_prompt_tokens,
                    estimated_completion_tokens, call_max_tokens,
                )
            
            # Per GPT_RESPONSE24 C1: Normalize complexity to handle variations
            # Per GPT_RESPONSE24 Q2 (GPT2): Use "medium" as fallback, no default tier in Phase 1
            # Per GPT_RESPONSE22 C1: Check soft cap with buffer bands (no safety margin on estimate)
            raw_complexity = phase_spec.get("complexity")
            complexity = normalize_complexity(raw_complexity)
            soft_cap = None
            try:
                # Load token_soft_caps from config
                config_path = Path(__file__).parent.parent.parent / "config" / "models.yaml"
                if config_path.exists():
                    with open(config_path) as f:
                        models_config = yaml.safe_load(f)
                        token_caps_config = models_config.get("token_soft_caps", {})
                        if token_caps_config.get("enabled", False):
                            per_phase_caps = token_caps_config.get("per_phase_soft_caps", {})
                            soft_cap = per_phase_caps.get(complexity)
                            
                            # Per GPT_RESPONSE24 Q2 (GPT2): Fallback to "medium" if complexity not found
                            if soft_cap is None:
                                if "medium" in per_phase_caps:
                                    logger.debug(
                                        "[TOKEN_SOFT_CAP] Unknown complexity %r (normalized %r) for run_id=%s phase_id=%s; "
                                        "falling back to 'medium' tier (%s tokens)",
                                        raw_complexity, complexity, run_id, phase_id, per_phase_caps["medium"],
                                    )
                                    soft_cap = per_phase_caps["medium"]
                                else:
                                    # Config is inconsistent; skip soft cap advisory
                                    logger.warning(
                                        "[TOKEN_SOFT_CAP] No soft cap for %r and no 'medium' tier in config; "
                                        "skipping soft cap check for this phase",
                                        raw_complexity,
                                    )
                                    soft_cap = None
            except Exception:
                # If config loading fails, skip soft cap check (non-fatal)
                pass
            
            # Log INFO/WARNING when soft cap is exceeded or approached
            if soft_cap:
                if estimated_total_tokens >= soft_cap:
                    # Clearly over soft cap
                    logger.warning(
                        "[TOKEN_SOFT_CAP] run_id=%s phase_id=%s est_total=%d soft_cap=%d "
                        "(prompt=%d completion=%d complexity=%s)",
                        run_id, phase_id, estimated_total_tokens, soft_cap,
                        estimated_prompt_tokens, estimated_completion_tokens, complexity,
                    )
                elif estimated_total_tokens >= int(soft_cap * 0.9):  # ≥90% of cap
                    # Approaching soft cap
                    logger.info(
                        "[TOKEN_SOFT_CAP] run_id=%s phase_id=%s est_total=%d soft_cap=%d (approaching, complexity=%s)",
                        run_id, phase_id, estimated_total_tokens, soft_cap, complexity,
                    )

            # Call Anthropic API with streaming for long operations
            # Use Claude's max output capacity (64K) to avoid truncation of large patches
            # Enable streaming to avoid 10-minute timeout for complex generations
            with self.client.messages.stream(
                model=model,
                max_tokens=min(max_tokens or 64000, 64000),
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.2
            ) as stream:
                # Collect streaming response
                content = ""
                for text in stream.text_stream:
                    content += text

                # Get final message for token usage
                response = stream.get_final_message()

            # Track truncation (stop_reason from Anthropic API)
            stop_reason = getattr(response, 'stop_reason', None)
            was_truncated = (stop_reason == 'max_tokens')
            if was_truncated:
                logger.warning(f"[Builder] Output was truncated (stop_reason=max_tokens)")

            format_error_codes = {
                "full_file_parse_failed_diff_detected",
                "full_file_schema_invalid",
                "full_file_parse_failed",
            }

            def _parse_once(text: str):
                if use_structured_edit:
                    return self._parse_structured_edit_output(
                        text, file_context, response, model, phase_spec, config=config,
                        stop_reason=stop_reason, was_truncated=was_truncated
                    )
                elif use_full_file_mode_flag:
                    return self._parse_full_file_output(
                        text, file_context, response, model, phase_spec, config=config,
                        stop_reason=stop_reason, was_truncated=was_truncated
                    )
                else:
                    return self._parse_legacy_diff_output(
                        text, response, model, stop_reason=stop_reason, was_truncated=was_truncated
                    )

            result = _parse_once(content)

            # Adaptive churn relaxation: if only churn_limit_exceeded and small scope, retry once with relaxed threshold
            if (
                result is not None
                and not result.success
                and isinstance(result.error, str)
                and "churn_limit_exceeded" in result.error
                and file_context
            ):
                files = file_context.get("existing_files", {})
                scope_cfg = phase_spec.get("scope") or {}
                scope_paths = scope_cfg.get("paths", []) if isinstance(scope_cfg, dict) else []
                scope_paths = [p for p in scope_paths if isinstance(p, str)]
                # Small-scope heuristic: only when ≤6 scoped paths and all files ≤ hard limit
                small_scope = len(scope_paths) <= 6
                if small_scope and isinstance(files, dict):
                    all_small = True
                    for fp, fc in files.items():
                        if isinstance(fp, str) and any(fp.startswith(sp) for sp in scope_paths):
                            if isinstance(fc, str):
                                line_count = fc.count("\n") + 1
                                if line_count > config.max_lines_hard_limit:
                                    all_small = False
                                    break
                    if all_small:
                        # Relax churn threshold for this parse retry
                        relaxed_config = copy.deepcopy(config)
                        relaxed_config.max_churn_percent_for_small_fix = max(
                            config.max_churn_percent_for_small_fix, 60
                        )
                        logger.warning(
                            "[Builder] Relaxing small-fix churn guard to %s%% for this phase/run (single retry)",
                            relaxed_config.max_churn_percent_for_small_fix,
                        )
                        # Add prompt nudge for minimal change
                        correction_content = content + (
                            "\n\n# CHURN CORRECTION\n"
                            "Minimize changes; only add the necessary import/path fix. Keep churn under 60%."
                        )
                        try:
                            return self._parse_full_file_output(
                                correction_content,
                                file_context,
                                response,
                                model,
                                phase_spec,
                                config=relaxed_config,
                                stop_reason=stop_reason,
                                was_truncated=was_truncated,
                            )
                        except Exception:
                            # Fall through to original result if retry parse fails
                            pass

            return result

        except Exception as e:
            # Log full traceback for debugging (critical to diagnose silent failures)
            import traceback
            error_traceback = traceback.format_exc()
            error_msg = str(e)
            logger.error("[Builder] Unhandled exception during execute_phase: %s\nTraceback:\n%s", error_msg, error_traceback)
            
            # Check if this is the Path/list error we're tracking
            if "unsupported operand type(s) for /" in error_msg and "list" in error_msg:
                logger.error(f"[Builder] Path/list TypeError detected:\n{error_msg}\nTraceback:\n{error_traceback}")
            
            # Return error result
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[f"Builder error: {error_msg}"],
                tokens_used=0,
                model_used=model,
                error=error_msg
            )

    def _extract_diff_from_text(self, text: str) -> str:
        """Extract git diff content from text that may contain explanations.

        Args:
            text: Raw text that may contain diff content

        Returns:
            Extracted diff content or empty string
        """
        import re

        lines = text.split('\n')
        diff_lines = []
        in_diff = False

        for line in lines:
            # Start of diff
            if line.startswith('diff --git'):
                in_diff = True
                diff_lines.append(line)
            # Continuation of diff
            elif in_diff:
                # Clean up malformed hunk headers (remove trailing context)
                if line.startswith('@@'):
                    # Extract the valid hunk header part only
                    match = re.match(r'^(@@\s+-\d+,\d+\s+\+\d+,\d+\s+@@)', line)
                    if match:
                        # Use only the valid hunk header, discard anything after
                        clean_line = match.group(1)
                        diff_lines.append(clean_line)
                    else:
                        # Malformed hunk header, skip it
                        logger.warning(f"Skipping malformed hunk header: {line[:80]}")
                        continue
                # Check if still in diff (various diff markers)
                elif (line.startswith(('index ', '---', '+++', '+', '-', ' ')) or
                    line.startswith('new file mode') or
                    line.startswith('deleted file mode') or
                    line.startswith('similarity index') or
                    line.startswith('rename from') or
                    line.startswith('rename to') or
                    line == ''):
                    diff_lines.append(line)
                # Next diff section
                elif line.startswith('diff --git'):
                    diff_lines.append(line)
                # End of diff (explanatory text or other content)
                else:
                    # Stop if we hit markdown fence or explanatory text
                    if line.startswith('```') or line.startswith('#'):
                        break

        return '\n'.join(diff_lines) if diff_lines else ""

    def _parse_full_file_output(
        self,
        content: str,
        file_context: Optional[Dict],
        response,
        model: str,
        phase_spec: Optional[Dict] = None,
        config = None,  # NEW: BuilderOutputConfig for thresholds
        stop_reason: Optional[str] = None,  # NEW: Anthropic stop_reason
        was_truncated: bool = False  # NEW: Truncation flag
    ) -> 'BuilderResult':
        """Parse full-file replacement output and generate git diff locally.
        
        Per GPT_RESPONSE10: LLM outputs complete file content, we generate diff.
        Per GPT_RESPONSE11: Added guards for large files, churn, and symbol validation.
        Per IMPLEMENTATION_PLAN2.md Phase 4: Added read-only enforcement and shrinkage/growth detection.
        
        Args:
            content: Raw LLM output (should be JSON)
            file_context: Original file contents for diff generation
            response: API response object for token usage
            model: Model identifier
            phase_spec: Phase specification for churn classification
            config: BuilderOutputConfig for thresholds (per IMPLEMENTATION_PLAN2.md)
            
        Returns:
            BuilderResult with generated patch
        """
        # Load config if not provided
        if config is None:
            from autopack.builder_config import BuilderOutputConfig
            config = BuilderOutputConfig()
        import subprocess
        import tempfile
        import tempfile
        import subprocess
        import tempfile
        import re

        def _escape_newlines_in_json_strings(raw: str) -> str:
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

        def _attempt_json_parse(candidate: Optional[str]) -> Optional[Dict[str, Any]]:
            if not candidate:
                return None
            try:
                return json.loads(candidate.strip())
            except json.JSONDecodeError:
                repaired = _escape_newlines_in_json_strings(candidate.strip())
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    return None

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
                        hex_value = raw_segment[idx + 2:idx + 6]
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
                            segment_chars.append(target[idx:idx + 2])
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

        def _restore_placeholder_content(payload: Dict[str, Any], placeholder_map: Dict[str, str]) -> None:
            files = payload.get("files")
            if not isinstance(files, list):
                return

            for file_entry in files:
                if not isinstance(file_entry, dict):
                    continue
                content = file_entry.get("new_content")
                if isinstance(content, str) and content in placeholder_map:
                    raw_segment = placeholder_map[content]
                    file_entry["new_content"] = _decode_placeholder_string(raw_segment)

        def _extract_code_fence(raw_text: str, fence: str) -> Optional[str]:
            start = raw_text.find(fence)
            if start == -1:
                return None
            start += len(fence)
            end = raw_text.find("```", start)
            if end == -1:
                return None
            return raw_text[start:end].strip()

        def _extract_first_json_object(raw_text: str) -> Optional[str]:
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
                        return raw_text[start:idx + 1]
            return None

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
                return BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=[error_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    model_used=model,
                    error="full_file_parse_failed_diff_detected"
                )
            if "```json" in content:
                fenced = _extract_code_fence(content, "```json")
                if fenced:
                    candidates.append(fenced)
            if "```" in content:
                fenced_generic = _extract_code_fence(content, "```")
                if fenced_generic:
                    candidates.append(fenced_generic)
            extracted = _extract_first_json_object(raw)
            if extracted:
                candidates.append(extracted)

            for candidate in candidates:
                sanitized_candidate, placeholders = _sanitize_full_file_output(candidate)
                balanced_candidate = _balance_json_brackets(sanitized_candidate)
                result_json = _attempt_json_parse(balanced_candidate)
                if result_json:
                    placeholder_map = placeholders
                    break

            if not result_json:
                # Do NOT fall back to legacy git-diff; request regeneration instead
                logger.warning("[Builder] WARNING: Full-file JSON parse failed; requesting regeneration (no legacy diff fallback)")
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
                        method=repair_method
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
                        method=repair_method
                    )
                    error_msg = "LLM output invalid format - expected JSON with 'files' array (repair also failed)"
                    logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[
                            error_msg,
                            "Regenerate a valid JSON full-file response; diff fallback is disabled."
                        ],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        model_used=model,
                        error="full_file_parse_failed"
                    )
            
            summary = result_json.get("summary", "Generated by Claude")
            if placeholder_map:
                _restore_placeholder_content(result_json, placeholder_map)
            files = result_json.get("files", [])
            
            if not files:
                error_msg = "LLM returned empty files array"
                return BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=[error_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    model_used=model,
                    error=error_msg
                )
            
            # Schema validation for file entries
            required_keys = {"path", "mode", "new_content"}
            for entry in files:
                if not isinstance(entry, dict) or not required_keys.issubset(entry.keys()):
                    error_msg = (
                        "LLM output invalid format - each file entry must include "
                        "`path`, `mode`, and `new_content`. Regenerate JSON."
                    )
                    logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        model_used=model,
                        error="full_file_schema_invalid"
                    )
            
            # Determine change type for churn validation (per GPT_RESPONSE11 Q4)
            change_type = self._classify_change_type(phase_spec)
            
            # Generate unified diff for each file
            diff_parts = []
            existing_files = {}
            if file_context:
                existing_files = file_context.get("existing_files", file_context)
                # Safety check: ensure existing_files is a dict
                if not isinstance(existing_files, dict):
                    existing_files = {}

            def _validate_pack_fullfile(file_path: str, content: str) -> Optional[str]:
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

            for file_entry in files:
                file_path = file_entry.get("path", "")
                mode = file_entry.get("mode", "modify")
                new_content = file_entry.get("new_content", "")
                
                if not file_path:
                    continue
                
                # Get original content
                old_content = existing_files.get(file_path, "")
                old_line_count = old_content.count('\n') + 1 if old_content else 0
                new_line_count = new_content.count('\n') + 1 if new_content else 0

                # Pack YAML preflight validation (per ref2.md - pack quality improvements)
                pack_validation_error = _validate_pack_fullfile(file_path, new_content)
                if pack_validation_error:
                    logger.error(f"[Builder] {pack_validation_error}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[pack_validation_error],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        model_used=model,
                        error=pack_validation_error
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
                    logger.warning(f"[TELEMETRY] readonly_violation: file={file_path}, lines={old_line_count}, model={model}")
                    
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        model_used=model,
                        error=error_msg
                    )
                
                # ============================================================================
                # NEW: Shrinkage detection (per IMPLEMENTATION_PLAN2.md Phase 4.2)
                # Reject >60% shrinkage unless phase allows mass deletion
                # ============================================================================
                if mode == "modify" and old_content and new_content:
                    shrinkage_percent = ((old_line_count - new_line_count) / old_line_count) * 100
                    
                    if shrinkage_percent > config.max_shrinkage_percent:
                        # Check if phase allows mass deletion
                        allow_mass_deletion = phase_spec.get("allow_mass_deletion", False) if phase_spec else False
                        
                        if not allow_mass_deletion:
                            error_msg = (
                                f"suspicious_shrinkage: {file_path} shrank by {shrinkage_percent:.1f}% "
                                f"({old_line_count} → {new_line_count} lines). "
                                f"Limit: {config.max_shrinkage_percent}%. "
                                f"This may indicate truncation. Set allow_mass_deletion=true to override."
                            )
                            logger.error(f"[Builder] {error_msg}")
                            logger.warning(f"[TELEMETRY] suspicious_shrinkage: file={file_path}, old={old_line_count}, new={new_line_count}, shrinkage={shrinkage_percent:.1f}%")
                            
                            return BuilderResult(
                                success=False,
                                patch_content="",
                                builder_messages=[error_msg],
                                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                                model_used=model,
                                error=error_msg
                            )
                
                # ============================================================================
                # NEW: Growth detection (per IMPLEMENTATION_PLAN2.md Phase 4.2)
                # Reject >3x growth unless phase allows mass addition
                # ============================================================================
                if mode == "modify" and old_content and new_content and old_line_count > 0:
                    growth_multiplier = new_line_count / old_line_count

                    # Optional: skip growth guard for YAML packs where large expansions are expected
                    if getattr(config, "disable_growth_guard_for_yaml", False) and file_path.endswith((".yaml", ".yml")):
                        logger.info(f"[Builder] Skipping growth guard for YAML file {file_path} (growth {growth_multiplier:.1f}x)")
                    else:
                        if growth_multiplier > config.max_growth_multiplier:
                            # Check if phase allows mass addition
                            allow_mass_addition = phase_spec.get("allow_mass_addition", False) if phase_spec else False

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

                                return BuilderResult(
                                    success=False,
                                    patch_content="",
                                    builder_messages=[error_msg],
                                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                                    model_used=model,
                                    error=error_msg,
                                )
                
                # Q4: Churn detection for small fixes
                if mode == "modify" and change_type == "small_fix" and old_content:
                    # Optional: skip small-fix churn guard for YAML packs where high churn is expected
                    if file_path.endswith(("package-lock.json", "yarn.lock", "package.json")):
                        logger.info(f"[Builder] Skipping small-fix churn guard for manifest/lockfile {file_path}")
                    elif getattr(config, "disable_small_fix_churn_for_yaml", False) and file_path.endswith((".yaml", ".yml")):
                        logger.info(f"[Builder] Skipping small-fix churn guard for YAML file {file_path}")
                    else:
                        churn_percent = self._calculate_churn_percent(old_content, new_content)
                        if churn_percent > config.max_churn_percent_for_small_fix:
                            error_msg = f"churn_limit_exceeded: {churn_percent:.1f}% (small_fix limit {config.max_churn_percent_for_small_fix}%) on {file_path}"
                            logger.error(f"[Builder] {error_msg}")
                            return BuilderResult(
                                success=False,
                                patch_content="",
                                builder_messages=[error_msg],
                                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                                model_used=model,
                                error=error_msg
                            )
                
                # Q5: Symbol validation for small fixes
                if mode == "modify" and change_type == "small_fix" and old_content:
                    missing_symbols = self._check_missing_symbols(old_content, new_content, file_path)
                    if missing_symbols:
                        error_msg = f"symbol_missing_after_full_file_replacement: lost {missing_symbols} in {file_path}"
                        logger.error(f"[Builder] {error_msg}")
                        return BuilderResult(
                            success=False,
                            patch_content="",
                            builder_messages=[error_msg],
                            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                            model_used=model,
                            error=error_msg
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
                error_msg = "No valid file changes generated"
                return BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=[error_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    model_used=model,
                    error=error_msg
                )
            
            patch_content = "\n".join(diff_parts)
            logger.info(f"[Builder] Generated {len(diff_parts)} file diffs locally from full-file content")

            return BuilderResult(
                success=True,
                patch_content=patch_content,
                builder_messages=[summary],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                model_used=model,
                stop_reason=stop_reason,
                was_truncated=was_truncated
            )
            
        except Exception as e:
            error_msg = f"Failed to parse full-file output: {str(e)}"
            logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[error_msg],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens if response else 0,
                model_used=model,
                error=error_msg
            )

    def _generate_unified_diff(
        self,
        file_path: str,
        old_content: str,
        new_content: str
    ) -> str:
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
        import subprocess
        import tempfile
        
        # Determine file mode: new, deleted, or modified
        is_new_file = not old_content and bool(new_content)
        is_deleted_file = bool(old_content) and not new_content
        
        # Construct git-format diff header (per GPT_RESPONSE12 Q3)
        # Order matters: diff --git, new/deleted file mode, index, ---, +++
        git_header = [f"diff --git a/{file_path} b/{file_path}"]
        
        if is_new_file:
            git_header.extend([
                "new file mode 100644",
                "index 0000000..1111111",
                "--- /dev/null",
                f"+++ b/{file_path}",
            ])
        elif is_deleted_file:
            git_header.extend([
                "deleted file mode 100644",
                "index 1111111..0000000",
                f"--- a/{file_path}",
                "+++ /dev/null",
            ])
        else:
            git_header.extend([
                "index 1111111..2222222 100644",
                f"--- a/{file_path}",
                f"+++ b/{file_path}",
            ])

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
            if line.startswith('@@') or started:
                started = True
                body_lines.append(line)

        if not body_lines:
            return ""

        full_diff = git_header + body_lines

        return "\n".join(full_diff)

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
        import difflib
        
        old_lines = old_content.splitlines()
        new_lines = new_content.splitlines()
        
        if not old_lines:
            return 100.0  # All new content
        
        # Use SequenceMatcher to count changed lines
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
        
        # Count lines that are different
        changed_lines = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                changed_lines += max(i2 - i1, j2 - j1)
            elif tag == 'delete':
                changed_lines += i2 - i1
            elif tag == 'insert':
                changed_lines += j2 - j1
        
        churn_percent = 100.0 * changed_lines / max(len(old_lines), 1)
        return churn_percent

    def _check_missing_symbols(
        self,
        old_content: str,
        new_content: str,
        file_path: str
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
        import re
        
        # Only validate Python files for now
        if not file_path.endswith('.py'):
            return None
        
        # Extract top-level function and class definitions
        def extract_symbols(content: str) -> set:
            symbols = set()
            # Match top-level def and class (not indented)
            for match in re.finditer(r'^(def|class)\s+(\w+)', content, re.MULTILINE):
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

    def _parse_legacy_diff_output(
        self,
        content: str,
        response,
        model: str,
        stop_reason=None,
        was_truncated: bool = False,
    ) -> 'BuilderResult':
        """Parse legacy git diff output from LLM.
        
        This is the deprecated mode where LLM generates raw git diffs.
        Kept for backward compatibility.
        
        Args:
            content: Raw LLM output
            response: API response object for token usage
            model: Model identifier
            
        Returns:
            BuilderResult with extracted patch
        """
        patch_content = ""
        summary = "Generated by Claude"

        try:
            # Try to parse as direct JSON first
            result_json = json.loads(content)
            patch_content = result_json.get("patch_content", "")
            summary = result_json.get("summary", "Generated by Claude")
        except json.JSONDecodeError:
            # Check if wrapped in markdown code fence
            if "```json" in content:
                # Extract JSON from markdown code block
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                if json_end > json_start:
                    json_str = content[json_start:json_end].strip()
                    try:
                        result_json = json.loads(json_str)
                        patch_content = result_json.get("patch_content", "")
                        summary = result_json.get("summary", "Generated by Claude")
                    except json.JSONDecodeError:
                        pass

            # If still no patch, try to extract raw diff content
            if not patch_content:
                patch_content = self._extract_diff_from_text(content)
                if not patch_content:
                    # Format validation failed - return error
                    error_msg = "LLM output invalid format - no git diff markers found. Output must start with 'diff --git'"
                    logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        model_used=model,
                        error=error_msg
                    )

        return BuilderResult(
            success=True,
            patch_content=patch_content,
            builder_messages=[summary],
            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
            model_used=model
        )

    def _parse_structured_edit_output(
        self,
        content: str,
        file_context: Optional[Dict],
        response,
        model: str,
        phase_spec: Dict,
        config = None,
        stop_reason=None,
        was_truncated: bool = False,
    ) -> 'BuilderResult':
        """Parse LLM's structured edit JSON output (Stage 2)
        
        Per IMPLEMENTATION_PLAN3.md Phase 2.2
        """
        import json
        from autopack.structured_edits import EditPlan, EditOperation, EditOperationType
        from autopack.builder_config import BuilderOutputConfig
        
        if config is None:
            config = BuilderOutputConfig()
        
        try:
            # Parse JSON
            result_json = None
            try:
                result_json = json.loads(content.strip())
            except json.JSONDecodeError:
                # Try extracting from markdown code fence
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    if json_end > json_start:
                        json_str = content[json_start:json_end].strip()
                        result_json = json.loads(json_str)
            
            if not result_json:
                error_msg = "LLM output invalid format - expected JSON with 'operations' array"
                logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                return BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=[error_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    model_used=model,
                    error=error_msg
                )
            
            # Extract summary and operations
            summary = result_json.get("summary", "Structured edits")
            operations_json = result_json.get("operations", [])
            
            if not operations_json:
                # Treat empty structured edits as a safe no-op rather than a hard failure.
                info_msg = "Structured edit produced no operations; treating as no-op"
                logger.warning(f"[Builder] {info_msg}")
                return BuilderResult(
                    success=True,
                    patch_content="",
                    builder_messages=[info_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    model_used=model,
                    error=None
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
                        context_after=op_json.get("context_after")
                    )
                    
                    # Validate operation
                    is_valid, error = op.validate()
                    if not is_valid:
                        error_msg = f"Operation {i} invalid: {error}"
                        logger.error(f"[Builder] {error_msg}")
                        return BuilderResult(
                            success=False,
                            patch_content="",
                            builder_messages=[error_msg],
                            tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                            model_used=model,
                            error=error_msg
                        )
                    
                    operations.append(op)
                
                except Exception as e:
                    error_msg = f"Failed to parse operation {i}: {str(e)}"
                    logger.error(f"[Builder] {error_msg}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        model_used=model,
                        error=error_msg
                    )
            
            # Create edit plan
            edit_plan = EditPlan(summary=summary, operations=operations)
            
            # Validate plan
            is_valid, error = edit_plan.validate()
            if not is_valid:
                error_msg = f"Invalid edit plan: {error}"
                logger.error(f"[Builder] {error_msg}")
                return BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=[error_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    model_used=model,
                    error=error_msg
                )
            
            # Store edit plan in BuilderResult
            logger.info(f"[Builder] Generated structured edit plan with {len(operations)} operations")
            
            return BuilderResult(
                success=True,
                patch_content="",  # No patch content for structured edits
                builder_messages=[f"Generated {len(operations)} edit operations"],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                model_used=model,
                edit_plan=edit_plan  # NEW: Store edit plan
            )
        
        except Exception as e:
            logger.error(f"[Builder] Error parsing structured edit output: {e}")
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[str(e)],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                model_used=model,
                error=str(e)
            )

    def _build_system_prompt(self, use_full_file_mode: bool = True, use_structured_edit: bool = False) -> str:
        """Build system prompt for Claude Builder
        
        Args:
            use_full_file_mode: If True, use new full-file replacement format (GPT_RESPONSE10).
                               If False, use legacy git diff format (deprecated).
            use_structured_edit: If True, use structured edit mode for large files (Stage 2).
        """
        if use_structured_edit:
            # NEW: Structured edit mode for large files (Stage 2) - per IMPLEMENTATION_PLAN3.md Phase 2.1
            base_prompt = """You are a code modification assistant. Generate targeted edit operations for large files.

Your task is to output a structured JSON edit plan with specific operations.

Output format:
{
  "summary": "Brief description of changes",
  "operations": [
    {
      "type": "insert",
      "file_path": "src/example.py",
      "line": 100,
      "content": "new code here\\n"
    },
    {
      "type": "replace",
      "file_path": "src/example.py",
      "start_line": 50,
      "end_line": 55,
      "content": "updated code here\\n"
    },
    {
      "type": "delete",
      "file_path": "src/example.py",
      "start_line": 200,
      "end_line": 210
    }
  ]
}

Operation Types:
1. "insert" - Insert new lines at a specific position
   Required: type, file_path, line, content
   
2. "replace" - Replace a range of lines
   Required: type, file_path, start_line, end_line, content
   Optional: context_before, context_after (for validation)
   
3. "delete" - Delete a range of lines
   Required: type, file_path, start_line, end_line
   
4. "append" - Append lines to end of file
   Required: type, file_path, content
   
5. "prepend" - Prepend lines to start of file
   Required: type, file_path, content

CRITICAL RULES:
- Line numbers are 1-indexed (first line is line 1)
- Ranges are inclusive (start_line to end_line, both included)
- Content should include newlines (\\n) where appropriate
- Do NOT output full file contents
- Do NOT use ellipses (...) or placeholders
- Make targeted, minimal changes
- Include context_before and context_after for validation when replacing critical sections

Example - Add a new function:
{
  "summary": "Add telemetry recording function",
  "operations": [
    {
      "type": "insert",
      "file_path": "src/autopack/autonomous_executor.py",
      "line": 500,
      "content": "    def record_telemetry(self, event):\\n        self.telemetry.record_event(event)\\n"
    }
  ]
}

Do NOT:
- Output complete file contents
- Use placeholders or ellipses
- Make unnecessary changes
- Modify lines outside the specified ranges"""
        elif use_full_file_mode:
            # Per GPT_RESPONSE10: Full-file replacement mode (Option A)
            # LLM outputs complete file content, executor generates diff locally
            base_prompt = """You are an expert software engineer working on an autonomous build system.

Your task is to generate code changes based on phase specifications.

OUTPUT FORMAT - CRITICAL:
You MUST output a valid JSON object with this exact structure:
{
  "summary": "Brief description of changes made",
  "files": [
    {
      "path": "full/path/to/file.py",
      "mode": "modify" or "create" or "delete",
      "new_content": "Complete file content here..."
    }
  ]
}

RULES:
1. Output ONLY the JSON object - no markdown fences, no explanations before/after
2. For "modify" mode: provide the COMPLETE new file content (not a diff, not a snippet)
3. For "create" mode: provide the COMPLETE new file content
4. For "delete" mode: set new_content to null
5. Use COMPLETE file paths from repository root (e.g., src/autopack/health_checks.py)
6. Preserve all existing code that should not change - do NOT accidentally delete functions
7. Maintain consistent formatting with the existing codebase
8. Include all imports, docstrings, and type hints

IMPORTANT:
- You are generating COMPLETE file content, not patches or diffs
- The system will compute the diff automatically from your output
- Do NOT include line numbers, @@ markers, or +/- prefixes
- Do NOT truncate or abbreviate - output the FULL file"""
        else:
            # Diff mode for medium files (501-1000 lines) - per IMPLEMENTATION_PLAN2.md Phase 3.1
            base_prompt = """You are a code modification assistant. Generate ONLY a git-compatible unified diff patch.

Output format:
- Start with `diff --git a/path/to/file.py b/path/to/file.py`
- Include `index`, `---`, and `+++` headers
- Use `@@ -OLD_START,OLD_COUNT +NEW_START,NEW_COUNT @@` hunk headers
- Use `-` for removed lines, `+` for added lines, and a leading space for context lines
- Include at least 3 lines of context around each change
- Use COMPLETE repository-relative paths (e.g., `src/autopack/error_recovery.py`)

Do NOT:
- Output JSON
- Output full file contents outside hunks
- Wrap the diff in markdown fences (```)
- Add explanations before or after the diff
- Modify files that are not shown in the context
- Include any text that is not part of the unified diff format

CRITICAL REQUIREMENTS:
1. Output ONLY a raw git diff format patch
2. Do NOT wrap it in JSON, markdown code blocks, or any other format
3. Do NOT add explanatory text before or after the patch
4. Start directly with: diff --git a/path/to/file.py b/path/to/file.py

GIT DIFF FORMAT RULES:
- Each file change MUST start with: diff --git a/PATH b/PATH
- Followed by: index HASH..HASH
- Then: --- a/PATH and +++ b/PATH
- Then: @@ -LINE,COUNT +LINE,COUNT @@ CONTEXT
- Then the actual changes with +/- prefixes
- Use COMPLETE file paths from repository root (e.g., src/backend/api/health.py)
- Do NOT use relative or partial paths (e.g., backend/api/health.py is WRONG)

Requirements:
- Generate clean, production-quality code
- Follow best practices (type hints, docstrings, tests)
- Apply learned rules from project history
- Output ONLY the raw git diff format patch (no JSON, no markdown fences, no explanations)"""

        # Inject prevention rules from debug journal
        try:
            prevention_rules = get_prevention_prompt_injection()
            if prevention_rules:
                base_prompt += "\n\n" + prevention_rules
        except Exception:
            # Gracefully continue if prevention rules can't be loaded
            pass

        return base_prompt

    def _build_user_prompt(
        self,
        phase_spec: Dict,
        file_context: Optional[Dict],
        project_rules: Optional[List],
        run_hints: Optional[List],
        use_full_file_mode: bool = True,
        config = None  # NEW: BuilderOutputConfig for thresholds
    ) -> str:
        """Build user prompt with phase details
        
        Args:
            phase_spec: Phase specification
            file_context: Repository file context
            project_rules: Persistent learned rules
            run_hints: Within-run hints
            use_full_file_mode: If True, include FULL file content for accurate editing
            config: BuilderOutputConfig instance (per IMPLEMENTATION_PLAN2.md)
        """
        # Load config if not provided
        if config is None:
            from autopack.builder_config import BuilderOutputConfig
            config = BuilderOutputConfig()
        prompt_parts = [
            "# Phase Specification",
            f"Description: {phase_spec.get('description', '')}",
            f"Category: {phase_spec.get('task_category', 'general')}",
            f"Complexity: {phase_spec.get('complexity', 'medium')}",
        ]

        # Detect country pack phases (pack YAMLs in scope) to inject a schema contract
        scope_config = phase_spec.get("scope") or {}
        scope_paths = scope_config.get("paths") or []
        readonly_entries = scope_config.get("read_only_context") or []

        scope_paths_for_detection = scope_paths or []
        is_pack_phase = any(
            isinstance(p, str) and "backend/packs/" in p and p.endswith((".yaml", ".yml"))
            for p in scope_paths_for_detection
        )
        if is_pack_phase:
            prompt_parts.append("\n# PACK SCHEMA CONTRACT (country packs)")
            prompt_parts.append(
                "You are generating complete country pack YAML files. You MUST output full, well-formed YAML with these keys:"
            )
            prompt_parts.append(
                "- Required top-level keys: name, description, version, country, domain, categories, checklists, official_sources"
            )
            prompt_parts.append(
                "- categories: non-empty list; each category has name, description, examples (list, non-empty). No duplicate category names."
            )
            prompt_parts.append(
                "- checklists: non-empty list; each checklist has name, required_documents (non-empty list)."
            )
            prompt_parts.append("- official_sources: non-empty list of URLs or source strings.")
            prompt_parts.append(
                "- Do NOT emit header-only or stub content (e.g., just version or a 4-line file). If unsure, leave content unchanged rather than emitting partial YAML."
            )
            prompt_parts.append(
                "- Use only the allowed files in scope. Do NOT introduce new files outside scope."
            )
            prompt_parts.append(
                "- If you cannot satisfy the schema confidently, return the previous content unchanged."
            )

            # Grounding hint: encourage use of curated research snippets if present in read-only context
            prompt_parts.append(
                "\nGrounding: Prefer facts from the provided research/reference files in read-only context (e.g., research_report_tax_immigration_legal_packs.md, research briefs). Do not invent thresholds or categories; align with those sources."
            )

        if phase_spec.get("acceptance_criteria"):
            prompt_parts.append("\nAcceptance Criteria:")
            for criteria in phase_spec["acceptance_criteria"]:
                prompt_parts.append(f"- {criteria}")
        else:
            # Universal output contract (goal/criteria prompting; refuse partials)
            prompt_parts.append("\nAcceptance Criteria (universal):")
            prompt_parts.append("- Emit COMPLETE, well-formed output for every file you touch; no stubs or truncated content.")
            prompt_parts.append("- For YAML/JSON/TOML, include required top-level keys/sections; do not omit document starts when applicable.")
            prompt_parts.append("- Do not emit patches that reference files outside the allowed scope.")
            prompt_parts.append("- If unsure or lacking context, leave the file unchanged rather than emitting partial output.")

        # Explicit format contract (applies to all modes)
        prompt_parts.append("\n# Output Format (strict)")
        prompt_parts.append("- Output JSON ONLY with a top-level `files` array.")
        prompt_parts.append("- Each entry MUST include: path, mode (replace|create|modify), new_content.")
        prompt_parts.append("- Do NOT output git diff, markdown fences, or prose.")
        prompt_parts.append("- No code fences, no surrounding text. Return only JSON.")

        # Inject scope constraints if provided
        if scope_paths:
            prompt_parts.append("\n## File Modification Constraints")
            prompt_parts.append("CRITICAL: You may ONLY modify these files:\n")
            for allowed in scope_paths:
                prompt_parts.append(f"- {allowed}")
            prompt_parts.append(
                "\nIf you touch any other file your patch will be rejected immediately."
            )

            if readonly_entries:
                prompt_parts.append("\nRead-only context (reference only, do NOT modify):")
                for entry in readonly_entries:
                    prompt_parts.append(f"- {entry}")

            prompt_parts.append(
                "\nDo not add new files or edit files outside this list. "
                "All other paths are strictly forbidden."
            )

        if project_rules:
            prompt_parts.append("\n# Learned Rules (must follow):")
            for rule in project_rules[:10]:  # Top 10 rules
                # Support both dict-based rules and LearnedRule dataclasses
                if isinstance(rule, dict):
                    text = rule.get("rule_text") or rule.get("constraint") or ""
                else:
                    text = getattr(rule, "constraint", str(rule))
                if text:
                    prompt_parts.append(f"- {text}")

        if run_hints:
            prompt_parts.append("\n# Hints from earlier phases:")
            for hint in run_hints[:5]:  # Recent hints
                # Support both dict-based hints and RunRuleHint dataclasses
                if isinstance(hint, dict):
                    text = hint.get("hint_text", "")
                else:
                    text = getattr(hint, "hint_text", str(hint))
                if text:
                    prompt_parts.append(f"- {text}")

        if file_context:
            # Extract existing_files dict (autonomous_executor returns {"existing_files": {path: content}})
            files = file_context.get("existing_files", file_context)
            scope_metadata = file_context.get("scope_metadata", {})
            missing_scope_files = file_context.get("missing_scope_files", [])

            # Safety check: ensure files is a dict, not a list or other type
            if not isinstance(files, dict):
                logger.warning(f"[Builder] file_context.get('existing_files') returned non-dict type: {type(files)}, using empty dict")
                files = {}

            # Check if we need structured edit mode (files >1000 lines IN SCOPE)
            # NOTE: This should match the logic in execute_phase() above
            use_structured_edit_mode = False
            if config:
                # Get explicit scope paths from phase_spec
                scope_config = phase_spec.get("scope") or {}
                scope_paths = scope_config.get("paths", []) if isinstance(scope_config, dict) else []
                if not isinstance(scope_paths, list):
                    scope_paths = []
                scope_paths = [sp for sp in scope_paths if isinstance(sp, str)]

                # Only check files in scope (or skip if no scope defined)
                if scope_paths:
                    for file_path, content in files.items():
                        if isinstance(content, str) and isinstance(file_path, str):
                            # Only check if file is in scope
                            if any(file_path.startswith(sp) for sp in scope_paths):
                                line_count = content.count('\n') + 1
                                if line_count > config.max_lines_hard_limit:
                                    use_structured_edit_mode = True
                                    break

            if missing_scope_files:
                prompt_parts.append("\n# Missing Scoped Files")
                prompt_parts.append("The following scoped files are within scope but do not exist yet. You may create them:")
                for missing_path in missing_scope_files:
                    prompt_parts.append(f"- {missing_path}")

            if use_structured_edit_mode:
                # NEW: Structured edit mode - show files with line numbers (per IMPLEMENTATION_PLAN3.md Phase 5)
                prompt_parts.append("\n# Files in Context (for structured edits):")
                prompt_parts.append("Use line numbers to specify where to make changes.")
                prompt_parts.append("Line numbers are 1-indexed (first line is line 1).\n")
                
                for file_path, content in files.items():
                    if not isinstance(content, str):
                        continue
                    
                    line_count = content.count('\n') + 1
                    prompt_parts.append(f"\n## {file_path} ({line_count} lines)")
                    
                    # Show file with line numbers
                    lines = content.split('\n')
                    
                    # For very large files, show first 100, middle section, last 100
                    if line_count > 300:
                        # First 100 lines
                        for i, line in enumerate(lines[:100], 1):
                            prompt_parts.append(f"{i:4d} | {line}")
                        
                        prompt_parts.append(f"\n... [{line_count - 200} lines omitted] ...\n")
                        
                        # Last 100 lines
                        for i, line in enumerate(lines[-100:], line_count - 99):
                            prompt_parts.append(f"{i:4d} | {line}")
                    else:
                        # Show all lines with numbers
                        for i, line in enumerate(lines, 1):
                            prompt_parts.append(f"{i:4d} | {line}")
            
            elif use_full_file_mode:
                # NEW: Separate files into modifiable vs read-only using scope metadata
                modifiable_files: List[Tuple[str, str, int, Dict[str, Any]]] = []
                readonly_files: List[Tuple[str, str, int, Dict[str, Any]]] = []
                fallback_readonly: List[Tuple[str, str, int]] = []

                for file_path, content in files.items():
                    if not isinstance(content, str):
                        continue
                    meta = scope_metadata.get(file_path)
                    line_count = content.count('\n') + 1

                    if meta:
                        category = meta.get("category")
                        if category == "modifiable":
                            modifiable_files.append((file_path, content, line_count, meta))
                        elif category == "read_only":
                            readonly_files.append((file_path, content, line_count, meta))
                        else:
                            fallback_readonly.append((file_path, content, line_count))
                    else:
                        fallback_readonly.append((file_path, content, line_count))
                
                # Add explicit contract (per GPT_RESPONSE14 Q1)
                if modifiable_files or readonly_files:
                    prompt_parts.append("\n# File Modification Rules")
                    prompt_parts.append("You are only allowed to modify files that are fully shown below.")
                    prompt_parts.append("Any file marked as READ-ONLY CONTEXT must NOT appear in the `files` list in your JSON output.")
                    prompt_parts.append("For each file you modify, return the COMPLETE new file content in `new_content`.")
                    prompt_parts.append("Do NOT use ellipses (...) or omit any code that should remain.")
                
                # Show modifiable files with full content (Bucket A: ≤500 lines)
                if modifiable_files:
                    prompt_parts.append("\n# Files You May Modify (COMPLETE CONTENT):")
                    for file_path, content, line_count, meta in modifiable_files:
                        missing_note = " — file does not exist yet, create it." if meta.get("missing") else ""
                        prompt_parts.append(f"\n## {file_path} ({line_count} lines){missing_note}")
                        if meta.get("missing"):
                            prompt_parts.append("This file is currently missing. Provide the complete new content below.")
                        prompt_parts.append(f"```\n{content}\n```")
                
                # Show read-only files with truncated content (Bucket B+C: >500 lines)
                readonly_combined = readonly_files + [(path, content, line_count, {}) for path, content, line_count in fallback_readonly]
                if readonly_combined:
                    prompt_parts.append("\n# Read-Only Context Files (DO NOT MODIFY):")
                    for file_path, content, line_count, meta in readonly_combined:
                        prompt_parts.append(f"\n## {file_path} (READ-ONLY CONTEXT — DO NOT MODIFY)")
                        prompt_parts.append(f"This file has {line_count} lines (too large for full-file replacement).")
                        prompt_parts.append("You may read this snippet as context, but you must NOT include it in your JSON output.")
                        
                        # Show first 200 + last 50 lines for context
                        lines = content.split('\n')
                        first_part = '\n'.join(lines[:200])
                        last_part = '\n'.join(lines[-50:])
                        prompt_parts.append(f"```\n{first_part}\n\n... [{line_count - 250} lines omitted] ...\n\n{last_part}\n```")
            else:
                # Legacy diff mode: show truncated content
                prompt_parts.append("\n# Repository Context:")
                for file_path, content in list(files.items())[:5]:
                    prompt_parts.append(f"\n## {file_path}")
                    # Show first 500 chars without literal "..." to avoid teaching model bad habits
                    if isinstance(content, str):
                        prompt_parts.append(f"```\n{content[:500]}\n```")
                    else:
                        prompt_parts.append(f"```\n{str(content)[:500]}\n```")

        return "\n".join(prompt_parts)


class AnthropicAuditorClient:
    """Auditor implementation using Anthropic Claude API

    Used for:
    - Primary auditing in progressive strategies (claude-sonnet-4-5)
    - High-risk auditing in best_first strategies (claude-opus-4-5)
    - Dual auditing partner with OpenAI
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Anthropic client

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        """
        if Anthropic is None:
            raise ImportError(
                "anthropic package not installed. "
                "Install with: pip install anthropic"
            )

        self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))

    def review_patch(
        self,
        patch_content: str,
        phase_spec: Dict,
        file_context: Optional[Dict] = None,
        max_tokens: Optional[int] = None,
        model: str = "claude-sonnet-4-5",
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None
    ) -> AuditorResult:
        """Review patch using Claude

        Args:
            patch_content: Git diff format patch
            phase_spec: Phase specification
            file_context: Repository context
            max_tokens: Token budget
            model: Claude model
            project_rules: Learned rules
            run_hints: Within-run hints from earlier phases

        Returns:
            AuditorResult with issues found
        """
        try:
            # Build system prompt
            system_prompt = self._build_system_prompt()

            # Build user prompt
            user_prompt = self._build_user_prompt(
                patch_content, phase_spec, file_context, project_rules, run_hints
            )

            # Call Anthropic API
            # Use higher token limit to avoid truncation on complex reviews
            # Actual usage is typically ~500 tokens for JSON response
            response = self.client.messages.create(
                model=model,
                max_tokens=min(max_tokens or 8192, 8192),
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.1  # Low temperature for consistent auditing
            )

            # Extract content
            content = response.content[0].text

            # Parse JSON response
            try:
                result_json = json.loads(content)
            except json.JSONDecodeError:
                # Fallback: treat as text review
                result_json = {
                    "approved": False,
                    "issues": [{"severity": "major", "description": content}],
                    "summary": "Review completed"
                }

            return AuditorResult(
                approved=result_json.get("approved", False),
                issues_found=result_json.get("issues", []),
                auditor_messages=[result_json.get("summary", "")],
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                model_used=model
            )

        except Exception as e:
            # Return error result
            return AuditorResult(
                approved=False,
                issues_found=[{
                    "severity": "critical",
                    "category": "auditor_error",
                    "description": f"Auditor error: {str(e)}"
                }],
                auditor_messages=[f"Auditor failed: {str(e)}"],
                tokens_used=0,
                model_used=model,
                error=str(e)
            )

    def _build_system_prompt(self) -> str:
        """Build system prompt for Claude Auditor"""
        base_prompt = """You are an expert code reviewer for an autonomous build system.

Your task is to review code patches for:
- Security vulnerabilities (OWASP Top 10)
- Type safety issues
- Edge cases and error handling
- Performance problems
- Best practice violations

Output Format (JSON):
{
  "approved": true/false,
  "issues": [
    {
      "severity": "minor|major|critical",
      "category": "security|types|logic|performance|style",
      "description": "Detailed issue description",
      "file_path": "path/to/file.py",
      "line_number": 42
    }
  ],
  "summary": "Brief review summary"
}

Approval Criteria:
- REJECT if any critical or major issues
- APPROVE if only minor issues or no issues"""

        # Inject prevention rules from debug journal
        try:
            prevention_rules = get_prevention_prompt_injection()
            if prevention_rules:
                base_prompt += "\n\n" + prevention_rules
        except Exception:
            # Gracefully continue if prevention rules can't be loaded
            pass

        return base_prompt

    def _build_user_prompt(
        self,
        patch_content: str,
        phase_spec: Dict,
        file_context: Optional[Dict],
        project_rules: Optional[List],
        run_hints: Optional[List] = None
    ) -> str:
        """Build user prompt with patch to review"""
        prompt_parts = [
            "# Patch to Review",
            f"```diff\n{patch_content}\n```",
            f"\n# Phase Context",
            f"Category: {phase_spec.get('task_category', 'general')}",
            f"Description: {phase_spec.get('description', '')}",
        ]

        if project_rules:
            prompt_parts.append("\n# Project Rules (check compliance):")
            for rule in project_rules[:10]:
                prompt_parts.append(f"- {rule.get('rule_text', '')}")

        if run_hints:
            prompt_parts.append("\n# Recent Run Hints:")
            for hint in run_hints[:5]:
                prompt_parts.append(f"- {hint}")

        prompt_parts.append("\nProvide your review as a JSON response.")

        return "\n".join(prompt_parts)
