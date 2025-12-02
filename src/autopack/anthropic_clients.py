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
from pathlib import Path
from typing import Dict, List, Optional

try:
    from anthropic import Anthropic
except ImportError:
    # Graceful degradation if anthropic package not installed
    Anthropic = None

from .llm_client import BuilderResult, AuditorResult
from .journal_reader import get_prevention_prompt_injection

logger = logging.getLogger(__name__)


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
        try:
            # Check if we need structured edit mode before building prompt
            use_structured_edit = False
            if file_context and config:
                files = file_context.get("existing_files", {})
                for file_path, content in files.items():
                    if isinstance(content, str):
                        line_count = content.count('\n') + 1
                        if line_count > config.max_lines_hard_limit:
                            scope_paths = phase_spec.get("scope", {}).get("paths", [])
                            if not scope_paths or any(file_path.startswith(sp) for sp in scope_paths):
                                use_structured_edit = True
                                break
            
            # Build system prompt (with mode selection per GPT_RESPONSE10)
            system_prompt = self._build_system_prompt(
                use_full_file_mode=use_full_file_mode,
                use_structured_edit=use_structured_edit
            )

            # Build user prompt (includes full file content for full-file mode)
            user_prompt = self._build_user_prompt(
                phase_spec, file_context, project_rules, run_hints,
                use_full_file_mode=use_full_file_mode,
                config=config  # NEW: Pass config for read-only markers
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

            # Parse output based on mode (use_structured_edit was already determined above)
            if use_structured_edit:
                # NEW: Structured edit mode for large files (Stage 2)
                return self._parse_structured_edit_output(
                    content, file_context, response, model, phase_spec, config=config
                )
            elif use_full_file_mode:
                # New full-file replacement mode (GPT_RESPONSE10/11)
                return self._parse_full_file_output(
                    content, file_context, response, model, phase_spec, config=config
                )
            else:
                # Legacy git diff mode (deprecated)
                return self._parse_legacy_diff_output(
                    content, response, model
            )

        except Exception as e:
            # Return error result
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[f"Builder error: {str(e)}"],
                tokens_used=0,
                model_used=model,
                error=str(e)
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
        config = None  # NEW: BuilderOutputConfig for thresholds
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
        import difflib
        import re
        
        try:
            # Try to parse JSON directly
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
                elif "```" in content:
                    # Try plain code fence
                    json_start = content.find("```") + 3
                    json_end = content.find("```", json_start)
                    if json_end > json_start:
                        json_str = content[json_start:json_end].strip()
                        result_json = json.loads(json_str)
            
            if not result_json:
                # Fallback: try legacy diff extraction (per GPT_RESPONSE11 Q3)
                logger.warning("[Builder] WARNING: Falling back to legacy git-diff mode (JSON full-file parse failed)")
                patch_content = self._extract_diff_from_text(content)
                if patch_content:
                    return BuilderResult(
                        success=True,
                        patch_content=patch_content,
                        builder_messages=["Fallback to legacy diff extraction"],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        model_used=model
                    )
                else:
                    error_msg = "LLM output invalid format - expected JSON with 'files' array"
                    logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                    return BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[error_msg],
                        tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                        model_used=model,
                        error=error_msg
                    )
            
            summary = result_json.get("summary", "Generated by Claude")
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
            
            # Determine change type for churn validation (per GPT_RESPONSE11 Q4)
            change_type = self._classify_change_type(phase_spec)
            
            # Generate unified diff for each file
            diff_parts = []
            existing_files = {}
            if file_context:
                existing_files = file_context.get("existing_files", file_context)
            
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
                            logger.warning(f"[TELEMETRY] suspicious_growth: file={file_path}, old={old_line_count}, new={new_line_count}, growth={growth_multiplier:.1f}x")
                            
                            return BuilderResult(
                                success=False,
                                patch_content="",
                                builder_messages=[error_msg],
                                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                                model_used=model,
                                error=error_msg
                            )
                
                # Q4: Churn detection for small fixes
                if mode == "modify" and change_type == "small_fix" and old_content:
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
                model_used=model
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
        import difflib
        
        # Determine file mode: new, deleted, or modified
        is_new_file = not old_content and new_content
        is_deleted_file = old_content and not new_content
        
        # Split into lines, preserving line endings
        old_lines = old_content.splitlines(keepends=True) if old_content else []
        new_lines = new_content.splitlines(keepends=True) if new_content else []
        
        # Ensure files end with newline for clean diffs
        if old_lines and not old_lines[-1].endswith('\n'):
            old_lines[-1] += '\n'
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines[-1] += '\n'
        
        # Construct git-format diff header (per GPT_RESPONSE12 Q3)
        # Order matters: diff --git, new/deleted file mode, index, ---, +++
        git_header = [f"diff --git a/{file_path} b/{file_path}"]
        
        if is_new_file:
            # New file format: mode before index, /dev/null for old path
            git_header.extend([
                "new file mode 100644",
                "index 0000000..1111111",
                "--- /dev/null",
                f"+++ b/{file_path}",
            ])
            # Generate diff from empty to new content
            diff_lines = list(difflib.unified_diff(
                [],
                new_lines,
                fromfile="/dev/null",
                tofile=f"b/{file_path}",
                lineterm=""
            ))
        elif is_deleted_file:
            # Deleted file format: mode before index, /dev/null for new path
            git_header.extend([
                "deleted file mode 100644",
                "index 1111111..0000000",
                f"--- a/{file_path}",
                "+++ /dev/null",
            ])
            # Generate diff from old content to empty
            diff_lines = list(difflib.unified_diff(
                old_lines,
                [],
                fromfile=f"a/{file_path}",
                tofile="/dev/null",
                lineterm=""
            ))
        else:
            # Modified file format: standard a/b paths
            git_header.extend([
                "index 1111111..2222222 100644",
                f"--- a/{file_path}",
                f"+++ b/{file_path}",
            ])
            # Generate diff between old and new
            diff_lines = list(difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
                lineterm=""
            ))
        
        if not diff_lines and not is_new_file and not is_deleted_file:
            return ""  # No changes for modified file
        
        # Skip the first two lines of unified_diff output (---/+++ lines)
        # since we already have them in git_header
        if len(diff_lines) >= 2 and diff_lines[0].startswith('---') and diff_lines[1].startswith('+++'):
            diff_lines = diff_lines[2:]
        
        # Combine header with diff content
        full_diff = git_header + diff_lines
        
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
        model: str
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
        config = None
    ) -> 'BuilderResult':
        """Parse LLM's structured edit JSON output (Stage 2)
        
        Per IMPLEMENTATION_PLAN3.md Phase 2.2
        """
        import json
        from src.autopack.structured_edits import EditPlan, EditOperation, EditOperationType
        from src.autopack.builder_config import BuilderOutputConfig
        
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
                error_msg = "LLM returned empty operations array"
                return BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=[error_msg],
                    tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                    model_used=model,
                    error=error_msg
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

        if phase_spec.get("acceptance_criteria"):
            prompt_parts.append("\nAcceptance Criteria:")
            for criteria in phase_spec["acceptance_criteria"]:
                prompt_parts.append(f"- {criteria}")

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

            if use_full_file_mode:
                # NEW: Separate files into modifiable vs read-only (per IMPLEMENTATION_PLAN2.md Phase 3.2)
                modifiable_files = []
                readonly_files = []
                
                for file_path, content in files.items():
                    if not isinstance(content, str):
                        continue
                    line_count = content.count('\n') + 1
                    
                    if line_count <= config.max_lines_for_full_file:
                        modifiable_files.append((file_path, content, line_count))
                    else:
                        readonly_files.append((file_path, content, line_count))
                
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
                    for file_path, content, line_count in modifiable_files:
                        prompt_parts.append(f"\n## {file_path} ({line_count} lines)")
                        prompt_parts.append(f"```\n{content}\n```")
                
                # Show read-only files with truncated content (Bucket B+C: >500 lines)
                if readonly_files:
                    prompt_parts.append("\n# Read-Only Context Files (DO NOT MODIFY):")
                    for file_path, content, line_count in readonly_files:
                        prompt_parts.append(f"\n## {file_path} (READ-ONLY CONTEXT — DO NOT MODIFY)")
                        prompt_parts.append(f"This file has {line_count} lines (too large for full-file replacement).")
                        prompt_parts.append("You may read this snippet as context, but you must NOT include it in your JSON output.")
                        
                        # Show first 200 + last 50 lines for context
                        lines = content.split('\n')
                        first_part = '\n'.join(lines[:200])
                        last_part = '\n'.join(lines[-50:])
                        prompt_parts.append(f"```\n{first_part}\n\n... [{line_count - 250} lines omitted] ...\n\n{last_part}\n```")
            else:
                # Legacy mode: show truncated content
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
