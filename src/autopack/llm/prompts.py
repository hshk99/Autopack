"""Prompt building utilities for LLM interactions.

Provides:
- System prompt construction for various output formats
- User prompt building with phase specs, file context, and rules
- Context-aware prompt optimization for token efficiency

This module extracts prompt building logic from anthropic_clients.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PromptConfig:
    """Configuration for prompt building.

    Attributes:
        use_full_file_mode: Whether to include full file content
        use_structured_edit: Whether to use structured edit JSON format
        use_ndjson_format: Whether to use NDJSON for truncation tolerance
        max_lines_hard_limit: Line count threshold for structured edit mode
        context_budget_tokens: Maximum tokens for file context
    """

    use_full_file_mode: bool = True
    use_structured_edit: bool = False
    use_ndjson_format: bool = False
    max_lines_hard_limit: int = 1000
    context_budget_tokens: int = 120000


@dataclass
class PromptParts:
    """Components of a built prompt.

    Attributes:
        system: System prompt content
        user: User prompt content
        estimated_tokens: Estimated token count (if calculated)
    """

    system: str
    user: str
    estimated_tokens: Optional[int] = None


class PromptBuilder:
    """Builder for LLM prompts with various output formats.

    Supports:
    - Full-file replacement mode (JSON with complete file content)
    - Structured edit mode (JSON with line-based operations)
    - NDJSON format (truncation-tolerant newline-delimited JSON)
    - Legacy diff mode (git diff format)

    Example:
        builder = PromptBuilder()
        parts = builder.build(
            phase_spec={"description": "Add tests", "complexity": "medium"},
            file_context={"existing_files": {"src/main.py": "..."}},
            config=PromptConfig(use_full_file_mode=True),
        )
        print(parts.system)
        print(parts.user)
    """

    def build(
        self,
        phase_spec: Dict[str, Any],
        file_context: Optional[Dict[str, Any]] = None,
        project_rules: Optional[List[Any]] = None,
        run_hints: Optional[List[Any]] = None,
        config: Optional[PromptConfig] = None,
        retrieved_context: Optional[str] = None,
    ) -> PromptParts:
        """Build complete system and user prompts.

        Args:
            phase_spec: Phase specification with description, category, etc.
            file_context: Repository file context
            project_rules: Learned rules to include
            run_hints: Within-run hints from earlier phases
            config: Prompt configuration options
            retrieved_context: Retrieved context from vector memory

        Returns:
            PromptParts with system and user prompts
        """
        if config is None:
            config = PromptConfig()

        system = self.build_system_prompt(
            use_full_file_mode=config.use_full_file_mode,
            use_structured_edit=config.use_structured_edit,
            use_ndjson_format=config.use_ndjson_format,
            phase_spec=phase_spec,
        )

        user = self.build_user_prompt(
            phase_spec=phase_spec,
            file_context=file_context,
            project_rules=project_rules,
            run_hints=run_hints,
            use_full_file_mode=config.use_full_file_mode,
            max_lines_hard_limit=config.max_lines_hard_limit,
            retrieved_context=retrieved_context,
            context_budget_tokens=config.context_budget_tokens,
        )

        return PromptParts(system=system, user=user)

    def build_system_prompt(
        self,
        use_full_file_mode: bool = True,
        use_structured_edit: bool = False,
        use_ndjson_format: bool = False,
        phase_spec: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build system prompt based on output format.

        Args:
            use_full_file_mode: Use full-file replacement JSON format
            use_structured_edit: Use structured edit JSON format
            use_ndjson_format: Use NDJSON format for truncation tolerance
            phase_spec: Phase specification for context-aware optimization

        Returns:
            System prompt string
        """
        # Check for minimal prompt optimization
        if phase_spec:
            complexity = phase_spec.get("complexity", "medium")
            task_category = phase_spec.get("task_category", "")

            # Simple file creation phases don't need complex instructions
            if complexity == "low" and task_category in ("feature", "bugfix"):
                return self._build_minimal_system_prompt(
                    use_structured_edit, use_ndjson_format, phase_spec
                )

        if use_ndjson_format:
            return self._build_ndjson_system_prompt(phase_spec)
        elif use_structured_edit:
            return self._build_structured_edit_system_prompt(phase_spec)
        elif use_full_file_mode:
            return self._build_full_file_system_prompt(phase_spec)
        else:
            return self._build_diff_system_prompt(phase_spec)

    def build_user_prompt(
        self,
        phase_spec: Dict[str, Any],
        file_context: Optional[Dict[str, Any]] = None,
        project_rules: Optional[List[Any]] = None,
        run_hints: Optional[List[Any]] = None,
        use_full_file_mode: bool = True,
        max_lines_hard_limit: int = 1000,
        retrieved_context: Optional[str] = None,
        context_budget_tokens: Optional[int] = None,
    ) -> str:
        """Build user prompt with phase details and context.

        Args:
            phase_spec: Phase specification
            file_context: Repository file context
            project_rules: Learned rules to follow
            run_hints: Hints from earlier phases
            use_full_file_mode: Include full file content
            max_lines_hard_limit: Threshold for structured edit mode
            retrieved_context: Retrieved context from vector memory
            context_budget_tokens: Token budget for file context

        Returns:
            User prompt string
        """
        prompt_parts = self._build_phase_header(phase_spec)
        prompt_parts.extend(self._build_acceptance_criteria(phase_spec))
        prompt_parts.extend(self._build_output_format_contract())
        prompt_parts.extend(self._build_scope_constraints(phase_spec))
        prompt_parts.extend(self._build_deliverables_contract(phase_spec))
        prompt_parts.extend(self._build_rules_section(project_rules, run_hints))
        prompt_parts.extend(self._build_retrieved_context(retrieved_context))
        prompt_parts.extend(
            self._build_file_context(
                file_context,
                phase_spec,
                use_full_file_mode,
                max_lines_hard_limit,
                context_budget_tokens,
            )
        )

        return "\n".join(prompt_parts)

    def _build_phase_header(self, phase_spec: Dict[str, Any]) -> List[str]:
        """Build phase specification header."""
        return [
            "# Phase Specification",
            f"Description: {phase_spec.get('description', '')}",
            f"Category: {phase_spec.get('task_category', 'general')}",
            f"Complexity: {phase_spec.get('complexity', 'medium')}",
        ]

    def _build_acceptance_criteria(self, phase_spec: Dict[str, Any]) -> List[str]:
        """Build acceptance criteria section."""
        parts = []
        if phase_spec.get("acceptance_criteria"):
            parts.append("\nAcceptance Criteria:")
            for criteria in phase_spec["acceptance_criteria"]:
                parts.append(f"- {criteria}")
        else:
            # Universal output contract
            parts.append("\nAcceptance Criteria (universal):")
            parts.append(
                "- Emit COMPLETE, well-formed output for every file you touch; "
                "no stubs or truncated content."
            )
            parts.append(
                "- For YAML/JSON/TOML, include required top-level keys/sections; "
                "do not omit document starts when applicable."
            )
            parts.append("- Do not emit patches that reference files outside the allowed scope.")
            parts.append(
                "- If unsure or lacking context, leave the file unchanged rather than "
                "emitting partial output."
            )
        return parts

    def _build_output_format_contract(self) -> List[str]:
        """Build output format contract section."""
        return [
            "\n# Output Format (strict)",
            "- Output JSON ONLY with a top-level `files` array.",
            "- Each entry MUST include: path, mode (replace|create|modify), new_content.",
            "- Do NOT output git diff, markdown fences, or prose.",
            "- No code fences, no surrounding text. Return only JSON.",
        ]

    def _build_scope_constraints(self, phase_spec: Dict[str, Any]) -> List[str]:
        """Build scope constraints section."""
        parts = []
        scope_config = phase_spec.get("scope") or {}
        scope_paths = scope_config.get("paths", []) if isinstance(scope_config, dict) else []
        readonly_entries = scope_config.get("read_only_context", []) if isinstance(scope_config, dict) else []

        if scope_paths:
            parts.append("\n## File Modification Constraints")
            parts.append("CRITICAL: You may ONLY modify these files:\n")
            for allowed in scope_paths:
                if allowed.endswith("/"):
                    parts.append(
                        f"- {allowed} (directory prefix - creating/modifying files "
                        "under this path is ALLOWED)"
                    )
                else:
                    parts.append(f"- {allowed}")
            parts.append("\nIf you touch any other file your patch will be rejected immediately.")

            if readonly_entries:
                parts.append("\nRead-only context (reference only, do NOT modify):")
                for entry in readonly_entries:
                    parts.append(f"- {entry}")

            parts.append(
                "\nDo not add new files or edit files outside this list. "
                "All other paths are strictly forbidden."
            )

        return parts

    def _build_deliverables_contract(self, phase_spec: Dict[str, Any]) -> List[str]:
        """Build deliverables contract section."""
        parts = []
        deliverables_list = phase_spec.get("deliverables")
        if not deliverables_list:
            scope_cfg = phase_spec.get("scope") or {}
            if isinstance(scope_cfg, dict):
                deliverables_list = scope_cfg.get("deliverables")

        if deliverables_list and isinstance(deliverables_list, list):
            parts.append("\n## REQUIRED DELIVERABLES")
            parts.append("Your output MUST include at least these files:\n")
            for deliverable in deliverables_list:
                parts.append(f"- {deliverable}")
            parts.append(
                "\nCRITICAL: The 'files' array in your JSON output MUST contain at least one file "
                "and MUST cover all deliverables listed above. Empty files array is NOT allowed."
            )

        return parts

    def _build_rules_section(
        self,
        project_rules: Optional[List[Any]],
        run_hints: Optional[List[Any]],
    ) -> List[str]:
        """Build learned rules and hints section."""
        parts = []

        if project_rules:
            parts.append("\n# Learned Rules (must follow):")
            for rule in project_rules[:10]:  # Top 10 rules
                if isinstance(rule, dict):
                    text = rule.get("rule_text") or rule.get("constraint") or ""
                else:
                    text = getattr(rule, "constraint", str(rule))
                if text:
                    parts.append(f"- {text}")

        if run_hints:
            parts.append("\n# Hints from earlier phases:")
            for hint in run_hints[:5]:  # Recent hints
                if isinstance(hint, dict):
                    text = hint.get("hint_text", "")
                else:
                    text = getattr(hint, "hint_text", str(hint))
                if text:
                    parts.append(f"- {text}")

        return parts

    def _build_retrieved_context(self, retrieved_context: Optional[str]) -> List[str]:
        """Build retrieved context section."""
        if not retrieved_context:
            return []
        return [
            "\n# Retrieved Context (from previous runs/phases):",
            retrieved_context,
        ]

    def _build_file_context(
        self,
        file_context: Optional[Dict[str, Any]],
        phase_spec: Dict[str, Any],
        use_full_file_mode: bool,
        max_lines_hard_limit: int,
        context_budget_tokens: Optional[int],
    ) -> List[str]:
        """Build file context section with appropriate formatting."""
        if not file_context:
            return []

        parts = []
        files = file_context.get("existing_files", file_context)
        scope_metadata = file_context.get("scope_metadata", {})
        missing_scope_files = file_context.get("missing_scope_files", [])

        if not isinstance(files, dict):
            logger.warning(
                f"[PromptBuilder] file_context.get('existing_files') returned non-dict type: "
                f"{type(files)}, using empty dict"
            )
            return []

        # Handle missing scope files
        if missing_scope_files:
            parts.append("\n# Missing Scoped Files")
            parts.append(
                "The following scoped files are within scope but do not exist yet. "
                "You may create them:"
            )
            for missing_path in missing_scope_files:
                parts.append(f"- {missing_path}")

        # Determine if structured edit mode is needed
        use_structured_edit_mode = self._should_use_structured_edit(
            files, phase_spec, max_lines_hard_limit
        )

        if use_structured_edit_mode:
            parts.extend(self._format_files_for_structured_edit(files))
        elif use_full_file_mode:
            parts.extend(self._format_files_for_full_file(files, scope_metadata))
        else:
            parts.extend(self._format_files_for_diff(files))

        return parts

    def _should_use_structured_edit(
        self,
        files: Dict[str, str],
        phase_spec: Dict[str, Any],
        max_lines_hard_limit: int,
    ) -> bool:
        """Determine if structured edit mode should be used."""
        scope_config = phase_spec.get("scope") or {}
        scope_paths = scope_config.get("paths", []) if isinstance(scope_config, dict) else []
        if not isinstance(scope_paths, list):
            scope_paths = []
        scope_paths = [sp for sp in scope_paths if isinstance(sp, str)]

        if not scope_paths:
            return False

        for file_path, content in files.items():
            if isinstance(content, str) and isinstance(file_path, str):
                if any(file_path.startswith(sp) for sp in scope_paths):
                    line_count = content.count("\n") + 1
                    if line_count > max_lines_hard_limit:
                        return True
        return False

    def _format_files_for_structured_edit(self, files: Dict[str, str]) -> List[str]:
        """Format files with line numbers for structured edit mode."""
        parts = [
            "\n# Files in Context (for structured edits):",
            "Use line numbers to specify where to make changes.",
            "Line numbers are 1-indexed (first line is line 1).\n",
        ]

        for file_path, content in files.items():
            if not isinstance(content, str):
                continue

            lines = content.split("\n")
            line_count = len(lines)
            parts.append(f"\n## {file_path} ({line_count} lines)")

            # For very large files, show first 100, middle section, last 100
            if line_count > 300:
                for i, line in enumerate(lines[:100], 1):
                    parts.append(f"{i:4d} | {line}")
                parts.append(f"\n... [{line_count - 200} lines omitted] ...\n")
                for i, line in enumerate(lines[-100:], line_count - 99):
                    parts.append(f"{i:4d} | {line}")
            else:
                for i, line in enumerate(lines, 1):
                    parts.append(f"{i:4d} | {line}")

        return parts

    def _format_files_for_full_file(
        self,
        files: Dict[str, str],
        scope_metadata: Dict[str, Any],
    ) -> List[str]:
        """Format files for full-file replacement mode."""
        parts = []
        modifiable_files: List[Tuple[str, str, int, Dict[str, Any]]] = []
        readonly_files: List[Tuple[str, str, int, Dict[str, Any]]] = []
        fallback_readonly: List[Tuple[str, str, int]] = []

        for file_path, content in files.items():
            if not isinstance(content, str):
                continue
            meta = scope_metadata.get(file_path)
            line_count = content.count("\n") + 1

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

        # Add explicit contract
        if modifiable_files or readonly_files:
            parts.append("\n# File Modification Rules")
            parts.append("You are only allowed to modify files that are fully shown below.")
            parts.append(
                "Any file marked as READ-ONLY CONTEXT must NOT appear in the `files` list "
                "in your JSON output."
            )
            parts.append(
                "For each file you modify, return the COMPLETE new file content in `new_content`."
            )
            parts.append("Do NOT use ellipses (...) or omit any code that should remain.")

        # Show modifiable files with full content
        if modifiable_files:
            parts.append("\n# Files You May Modify (COMPLETE CONTENT):")
            for file_path, content, line_count, meta in modifiable_files:
                missing_note = (
                    " - file does not exist yet, create it." if meta.get("missing") else ""
                )
                parts.append(f"\n## {file_path} ({line_count} lines){missing_note}")
                if meta.get("missing"):
                    parts.append(
                        "This file is currently missing. Provide the complete new content below."
                    )
                parts.append(f"```\n{content}\n```")

        # Show read-only files with truncated content
        readonly_combined = readonly_files + [
            (path, content, line_count, {})
            for path, content, line_count in fallback_readonly
        ]
        if readonly_combined:
            parts.append("\n# Read-Only Context Files (DO NOT MODIFY):")
            for file_path, content, line_count, meta in readonly_combined:
                parts.append(f"\n## {file_path} (READ-ONLY CONTEXT - DO NOT MODIFY)")
                parts.append(
                    f"This file has {line_count} lines (too large for full-file replacement)."
                )
                parts.append(
                    "You may read this snippet as context, but you must NOT include it "
                    "in your JSON output."
                )

                # Show first 200 + last 50 lines for context
                lines = content.split("\n")
                first_part = "\n".join(lines[:200])
                last_part = "\n".join(lines[-50:])
                parts.append(
                    f"```\n{first_part}\n\n... [{line_count - 250} lines omitted] ...\n\n"
                    f"{last_part}\n```"
                )

        return parts

    def _format_files_for_diff(self, files: Dict[str, str]) -> List[str]:
        """Format files for legacy diff mode."""
        parts = ["\n# Repository Context:"]
        for file_path, content in list(files.items())[:5]:
            parts.append(f"\n## {file_path}")
            if isinstance(content, str):
                parts.append(f"```\n{content[:500]}\n```")
            else:
                parts.append(f"```\n{str(content)[:500]}\n```")
        return parts

    def _build_ndjson_system_prompt(self, phase_spec: Optional[Dict[str, Any]]) -> str:
        """Build system prompt for NDJSON format."""
        deliverables = []
        if phase_spec:
            deliverables = phase_spec.get("deliverables")
            if not deliverables:
                scope_cfg = phase_spec.get("scope") or {}
                if isinstance(scope_cfg, dict):
                    deliverables = scope_cfg.get("deliverables")
        deliverables = deliverables or []

        base_prompt = """You are an expert software engineer working on an autonomous build system.

**OUTPUT FORMAT: NDJSON (Newline-Delimited JSON) - TRUNCATION-TOLERANT**

Generate output in NDJSON format - one complete JSON object per line.
This format is truncation-tolerant: if output is cut off mid-generation, all complete lines are still valid.

**CRITICAL REQUIREMENTS**:
1. Each line MUST be a complete, valid JSON object
2. NO line breaks within JSON objects (use \\n for newlines in content strings)
3. First line: meta object with summary and total_operations
4. Subsequent lines: one operation per line

**OPERATION TYPES**:
- create: Full file content for new files
- modify: Structured edit operations for existing files
- delete: Remove files

**TRUNCATION TOLERANCE**:
This format ensures that if generation is truncated, all complete operation lines are preserved and usable.
Only the last incomplete line is lost."""

        return base_prompt

    def _build_structured_edit_system_prompt(
        self, phase_spec: Optional[Dict[str, Any]]
    ) -> str:
        """Build system prompt for structured edit mode."""
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

Do NOT:
- Output complete file contents
- Use placeholders or ellipses
- Make unnecessary changes
- Modify lines outside the specified ranges"""

        # Add protected path isolation guidance
        if phase_spec:
            base_prompt += self._build_protected_paths_guidance(phase_spec)

        return base_prompt

    def _build_full_file_system_prompt(self, phase_spec: Optional[Dict[str, Any]]) -> str:
        """Build system prompt for full-file replacement mode."""
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

        # Add protected path isolation guidance
        if phase_spec:
            base_prompt += self._build_protected_paths_guidance(phase_spec)

        return base_prompt

    def _build_diff_system_prompt(self, phase_spec: Optional[Dict[str, Any]]) -> str:
        """Build system prompt for legacy diff mode."""
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
- Use COMPLETE file paths from repository root (e.g., src/autopack/main.py)
- Do NOT use relative or partial paths (e.g., autopack/main.py is WRONG)

Requirements:
- Generate clean, production-quality code
- Follow best practices (type hints, docstrings, tests)
- Apply learned rules from project history
- Output ONLY the raw git diff format patch (no JSON, no markdown fences, no explanations)"""

        # Add protected path isolation guidance
        if phase_spec:
            base_prompt += self._build_protected_paths_guidance(phase_spec)

        return base_prompt

    def _build_minimal_system_prompt(
        self,
        use_structured_edit: bool = False,
        use_ndjson_format: bool = False,
        phase_spec: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Build minimal system prompt for simple phases (token optimization)."""
        if use_structured_edit:
            base_prompt = """You are a code modification assistant. Generate structured JSON edit operations.

Output format:
{
  "summary": "Brief description",
  "operations": [
    {
      "type": "insert|replace|delete|append|prepend",
      "file_path": "path/to/file",
      "line": 100,  // for insert
      "start_line": 50, "end_line": 55,  // for replace/delete
      "content": "code here\\n"  // for insert/replace/append/prepend
    }
  ]
}

Rules:
- Line numbers are 1-indexed
- Use targeted, minimal changes
- Do NOT output full file contents
- Include \\n in content where needed
"""
        else:
            base_prompt = """You are a code modification assistant. Generate git diff format patches.

Rules:
- Use standard git diff format
- Start with 'diff --git a/path b/path'
- Include proper @@ hunk headers
- Use +/- for added/removed lines
- Context lines have no prefix
- Be precise and complete

Example:
diff --git a/src/example.py b/src/example.py
index abc123..def456 100644
--- a/src/example.py
+++ b/src/example.py
@@ -10,3 +10,4 @@ def example():
     print("existing")
+    print("new line")
"""

        # Add protected path isolation guidance
        if phase_spec:
            base_prompt += self._build_protected_paths_guidance(phase_spec, minimal=True)

        return base_prompt

    def _build_protected_paths_guidance(
        self,
        phase_spec: Dict[str, Any],
        minimal: bool = False,
    ) -> str:
        """Build protected path isolation guidance."""
        protected_paths = phase_spec.get("protected_paths", [])
        if not protected_paths:
            return ""

        if minimal:
            guidance = "\n\nCRITICAL: The following paths are PROTECTED - DO NOT modify them:\n"
            for path in protected_paths:
                guidance += f"  - {path}\n"
            guidance += "\nInstead: Use their APIs via imports, create new files elsewhere.\n"
        else:
            guidance = """

CRITICAL ISOLATION RULES:
The following paths are PROTECTED and MUST NOT be modified under any circumstances:
"""
            for path in protected_paths:
                guidance += f"  - {path}\n"

            guidance += """
If your task requires functionality from these protected modules:
1. USE their existing APIs via imports (import statements)
2. CREATE NEW files in different directories outside protected paths
3. EXTEND functionality by creating wrapper/adapter modules
4. DO NOT modify, extend, or touch any protected files directly

VIOLATION CONSEQUENCES:
Any attempt to modify protected paths will cause immediate patch rejection.
Your changes will be lost and the phase will fail.

ALLOWED APPROACH:
- Import from protected modules: from src.autopack.embeddings import EmbeddingModel
- Create new files: src/my_feature/search.py
- Use APIs: embedding_model = EmbeddingModel(); results = embedding_model.search(query)

FORBIDDEN APPROACH:
- Modify protected files: src/autopack/embeddings/model.py
- Extend protected classes in-place
- Add methods to protected modules
"""

        return guidance
