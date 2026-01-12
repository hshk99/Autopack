"""
Anthropic Builder Prompt Construction Logic

This module contains prompt construction functions extracted from anthropic_clients.py
to separate transport/parsing concerns from prompt building logic.

Each prompt mode includes required "output contract" markers that are verified by tests:
- full-file mode: Requires ```json marker and complete file content
- ndjson mode: Requires NDJSON format instructions with one JSON object per line
- structured-edit mode: Requires JSON with operations array and line number guidance
- legacy-diff mode: Requires git diff format with proper headers and hunks

Deliverables manifest preview limit: When a manifest is present, it shows up to 60 entries
to keep the prompt compact while ensuring path correctness.
"""

import os
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


def build_system_prompt(
    use_full_file_mode: bool = True,
    use_structured_edit: bool = False,
    use_ndjson_format: bool = False,
    phase_spec: Optional[Dict] = None,
) -> str:
    """Build system prompt for Claude Builder

    Args:
        use_full_file_mode: If True, use new full-file replacement format (GPT_RESPONSE10).
                           If False, use legacy git diff format (deprecated).
        use_structured_edit: If True, use structured edit mode for large files (Stage 2).
        use_ndjson_format: If True, use NDJSON format for truncation tolerance (BUILD-129 Phase 3).
        phase_spec: Phase specification for context-aware prompt optimization (BUILD-043).
    """
    # BUILD-043: Use minimal prompt for simple phases to save tokens
    if phase_spec:
        complexity = phase_spec.get("complexity", "medium")
        task_category = phase_spec.get("task_category", "")

        # Simple file creation phases don't need complex instructions
        if complexity == "low" and task_category in ("feature", "bugfix"):
            return build_minimal_system_prompt(
                use_structured_edit, use_ndjson_format, phase_spec
            )

    if use_ndjson_format:
        # BUILD-129 Phase 3: NDJSON format for truncation tolerance
        from autopack.ndjson_format import NDJSONParser

        parser = NDJSONParser()
        deliverables = []
        if phase_spec:
            deliverables = phase_spec.get("deliverables")
            if not deliverables:
                scope_cfg = phase_spec.get("scope") or {}
                if isinstance(scope_cfg, dict):
                    deliverables = scope_cfg.get("deliverables")
        deliverables = deliverables or []
        summary = (
            phase_spec.get("description", "Implement changes")
            if phase_spec
            else "Implement changes"
        )

        base_prompt = """You are an expert software engineer working on an autonomous build system.

**OUTPUT FORMAT: NDJSON (Newline-Delimited JSON) - TRUNCATION-TOLERANT**

Generate output in NDJSON format - one complete JSON object per line.
This format is truncation-tolerant: if output is cut off mid-generation, all complete lines are still valid.

"""
        # Add format instructions from NDJSONParser
        base_prompt += parser.format_for_prompt(deliverables, summary)

        base_prompt += """

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

        # BUILD-129 Phase 3: Tighten path correctness using deliverables_manifest (when present).
        # Many failures were due to writing outside the manifest or using wrong file paths (e.g. docs/* vs docs/research/*).
        # When a manifest is present, it is the authoritative allowlist for file_path values.
        if phase_spec:
            scope_cfg = phase_spec.get("scope") or {}
            manifest = None
            if isinstance(scope_cfg, dict):
                manifest = scope_cfg.get("deliverables_manifest")
            # Executor often attaches deliverables_manifest at the top-level phase spec.
            if manifest is None:
                manifest = phase_spec.get("deliverables_manifest")
            if isinstance(manifest, list) and manifest:
                # Keep prompt compact: list first N entries; rule remains "only these paths/prefixes".
                manifest_strs = [
                    str(p).strip() for p in manifest if isinstance(p, str) and str(p).strip()
                ]
                preview = manifest_strs[:60]
                base_prompt += (
                    "\n\n**FILE PATH CONSTRAINT (DELIVERABLES MANIFEST - STRICT)**:\n"
                )
                base_prompt += "- For EVERY operation line, `file_path` MUST be exactly one of the approved paths below.\n"
                base_prompt += "- If an approved entry ends with `/`, it is a directory prefix; then `file_path` MUST be under that prefix.\n"
                base_prompt += "- DO NOT create/modify/delete any file outside this manifest.\n"
                base_prompt += "- DO NOT improvise alternate locations (e.g. `docs/API.md` when `docs/research/API_REFERENCE.md` is required).\n"
                base_prompt += "\nApproved manifest (preview):\n"
                for p in preview:
                    base_prompt += f"- {p}\n"
                if len(manifest_strs) > len(preview):
                    base_prompt += f"- ... ({len(manifest_strs) - len(preview)} more)\n"

        return base_prompt
    elif use_structured_edit:
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
- Use COMPLETE file paths from repository root (e.g., src/autopack/main.py)
- Do NOT use relative or partial paths (e.g., autopack/main.py is WRONG)

Requirements:
- Generate clean, production-quality code
- Follow best practices (type hints, docstrings, tests)
- Apply learned rules from project history
- Output ONLY the raw git diff format patch (no JSON, no markdown fences, no explanations)"""

    # BUILD-044: Add protected path isolation guidance
    if phase_spec:
        # Get protected paths from phase spec (passed from executor)
        protected_paths = phase_spec.get("protected_paths", [])
        if protected_paths:
            isolation_guidance = """

CRITICAL ISOLATION RULES:
The following paths are PROTECTED and MUST NOT be modified under any circumstances:
"""
            for path in protected_paths:
                isolation_guidance += f"  - {path}\n"

            isolation_guidance += """
If your task requires functionality from these protected modules:
1. USE their existing APIs via imports (import statements)
2. CREATE NEW files in different directories outside protected paths
3. EXTEND functionality by creating wrapper/adapter modules
4. DO NOT modify, extend, or touch any protected files directly

VIOLATION CONSEQUENCES:
Any attempt to modify protected paths will cause immediate patch rejection.
Your changes will be lost and the phase will fail.

ALLOWED APPROACH:
✓ Import from protected modules: from src.autopack.embeddings import EmbeddingModel
✓ Create new files: src/my_feature/search.py
✓ Use APIs: embedding_model = EmbeddingModel(); results = embedding_model.search(query)

FORBIDDEN APPROACH:
✗ Modify protected files: src/autopack/embeddings/model.py
✗ Extend protected classes in-place
✗ Add methods to protected modules
"""
            base_prompt += isolation_guidance

    # Inject prevention rules from debug journal
    try:
        from autopack.journal_reader import get_prevention_prompt_injection

        prevention_rules = get_prevention_prompt_injection()
        if prevention_rules:
            base_prompt += "\n\n" + prevention_rules
    except Exception:
        # Gracefully continue if prevention rules can't be loaded
        pass

    # BUILD-127 Phase 3: Request deliverables manifest from Builder
    if phase_spec and phase_spec.get("deliverables"):
        manifest_request = """

**DELIVERABLES MANIFEST (BUILD-127 Phase 3)**:
After implementing the changes, provide a deliverables manifest at the end of your response (after the main output):

DELIVERABLES_MANIFEST:
```json
{
  "created": [
    {"path": "src/autopack/example.py", "symbols": ["ExampleClass", "example_function"]},
    {"path": "tests/test_example.py", "symbols": ["test_example_creation", "test_example_validation"]}
  ],
  "modified": [
    {"path": "src/autopack/main.py", "changes": "Added example import and initialization"}
  ]
}
```

This manifest will be validated to ensure all required deliverables are created with expected symbols.

MANIFEST REQUIREMENTS:
1. Include ALL created files with their key symbols (classes, functions, constants)
2. Include ALL modified files with a brief description of changes
3. Use complete paths from repository root
4. For test files, list test function names
5. For source files, list public classes and functions
"""
        base_prompt += manifest_request

    return base_prompt


def build_minimal_system_prompt(
    use_structured_edit: bool = False,
    use_ndjson_format: bool = False,
    phase_spec: Optional[Dict] = None,
) -> str:
    """Build minimal system prompt for simple phases (BUILD-043)

    Trimmed version saves ~3K tokens for low-complexity tasks.

    Args:
        use_structured_edit: If True, use structured edit JSON format.
        use_ndjson_format: If True, use NDJSON format (BUILD-129 Phase 3).
        phase_spec: Phase specification for protected path guidance (BUILD-044).

    Returns:
        Minimal system prompt optimized for token efficiency.
    """
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

    # BUILD-044: Add protected path isolation guidance
    if phase_spec:
        protected_paths = phase_spec.get("protected_paths", [])
        if protected_paths:
            isolation_guidance = """

CRITICAL: The following paths are PROTECTED - DO NOT modify them:
"""
            for path in protected_paths:
                isolation_guidance += f"  - {path}\n"

            isolation_guidance += """
Instead: Use their APIs via imports, create new files elsewhere.
"""
            base_prompt += isolation_guidance

    return base_prompt


def build_user_prompt(
    phase_spec: Dict,
    file_context: Optional[Dict],
    project_rules: Optional[List],
    run_hints: Optional[List],
    use_full_file_mode: bool = True,
    config=None,  # NEW: BuilderOutputConfig for thresholds
    retrieved_context: Optional[str] = None,  # NEW: Vector memory context
    context_budget_tokens: Optional[
        int
    ] = None,  # NEW: Hard cap for file_context inclusion (approx tokens)
) -> str:
    """Build user prompt with phase details

    Args:
        phase_spec: Phase specification
        file_context: Repository file context
        project_rules: Persistent learned rules
        run_hints: Within-run hints
        use_full_file_mode: If True, include FULL file content for accurate editing
        config: BuilderOutputConfig instance (per IMPLEMENTATION_PLAN2.md)
        retrieved_context: Retrieved context from vector memory (formatted string)
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
        prompt_parts.append(
            "- Emit COMPLETE, well-formed output for every file you touch; no stubs or truncated content."
        )
        prompt_parts.append(
            "- For YAML/JSON/TOML, include required top-level keys/sections; do not omit document starts when applicable."
        )
        prompt_parts.append(
            "- Do not emit patches that reference files outside the allowed scope."
        )
        prompt_parts.append(
            "- If unsure or lacking context, leave the file unchanged rather than emitting partial output."
        )

    # Explicit format contract (applies to all modes)
    prompt_parts.append("\n# Output Format (strict)")
    prompt_parts.append("- Output JSON ONLY with a top-level `files` array.")
    prompt_parts.append(
        "- Each entry MUST include: path, mode (replace|create|modify), new_content."
    )
    prompt_parts.append("- Do NOT output git diff, markdown fences, or prose.")
    prompt_parts.append("- No code fences, no surrounding text. Return only JSON.")

    # Inject scope constraints if provided
    if scope_paths:
        prompt_parts.append("\n## File Modification Constraints")
        prompt_parts.append("CRITICAL: You may ONLY modify these files:\n")
        for allowed in scope_paths:
            # BUILD-141 Telemetry Unblock: Clarify directory prefix semantics
            if allowed.endswith("/"):
                prompt_parts.append(
                    f"- {allowed} (directory prefix - creating/modifying files under this path is ALLOWED)"
                )
            else:
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

    # BUILD-141 Telemetry Unblock: Add explicit deliverables contract
    # Extract deliverables from phase_spec (same logic as token estimation)
    deliverables_list = phase_spec.get("deliverables")
    if not deliverables_list:
        scope_cfg = phase_spec.get("scope") or {}
        if isinstance(scope_cfg, dict):
            deliverables_list = scope_cfg.get("deliverables")

    if deliverables_list and isinstance(deliverables_list, list):
        prompt_parts.append("\n## REQUIRED DELIVERABLES")
        prompt_parts.append("Your output MUST include at least these files:\n")
        for deliverable in deliverables_list:
            prompt_parts.append(f"- {deliverable}")
        prompt_parts.append(
            "\n⚠️ CRITICAL: The 'files' array in your JSON output MUST contain at least one file "
            "and MUST cover all deliverables listed above. Empty files array is NOT allowed."
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
                prompt_parts.append(f"- {hint}")

    # Milestone 2: Inject intention anchor (canonical project goal)
    if run_id := phase_spec.get("run_id"):
        from autopack.intention_anchor import load_and_render_for_builder

        anchor_section = load_and_render_for_builder(
            run_id=run_id,
            phase_id=phase_spec.get("phase_id", "unknown"),
            base_dir=".",  # Use current directory (.autonomous_runs/<run_id>/)
        )
        if anchor_section:
            prompt_parts.append("\n")
            prompt_parts.append(anchor_section)

    # NEW: Include retrieved context from vector memory (per IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md)
    if retrieved_context:
        prompt_parts.append("\n# Retrieved Context (from previous runs/phases):")
        prompt_parts.append(retrieved_context)

    if file_context:
        # Extract existing_files dict (autonomous_executor returns {"existing_files": {path: content}})
        files = file_context.get("existing_files", file_context)
        scope_metadata = file_context.get("scope_metadata", {})
        missing_scope_files = file_context.get("missing_scope_files", [])

        # Safety check: ensure files is a dict, not a list or other type
        if not isinstance(files, dict):
            logger.warning(
                f"[Builder] file_context.get('existing_files') returned non-dict type: {type(files)}, using empty dict"
            )
            files = {}

        # ------------------------------------------------------------------
        # Hard context budgeting: keep prompt under provider limits even when
        # scope expansion loads hundreds of files (e.g., research phases).
        # We prefer deliverables, then small modifiable files, then read-only.
        # ------------------------------------------------------------------
        if context_budget_tokens is not None and context_budget_tokens > 0 and files:
            try:
                scope_cfg = phase_spec.get("scope") or {}
                try:
                    from autopack.deliverables_validator import extract_deliverables_from_scope

                    deliverables_list = (
                        extract_deliverables_from_scope(scope_cfg)
                        if isinstance(scope_cfg, dict)
                        else []
                    )
                except Exception:
                    deliverables_list = []
                if not deliverables_list and isinstance(scope_cfg, dict):
                    deliverables_list = scope_cfg.get("deliverables") or []
                from autopack.context_budgeter import select_files_for_context

                query = " ".join(
                    [
                        str(phase_spec.get("description") or ""),
                        str(phase_spec.get("name") or ""),
                        "Deliverables: "
                        + ", ".join([d for d in deliverables_list if isinstance(d, str)][:20]),
                    ]
                ).strip()

                selection = select_files_for_context(
                    files=files,
                    scope_metadata=scope_metadata,
                    deliverables=[d for d in deliverables_list if isinstance(d, str)],
                    query=query,
                    budget_tokens=int(context_budget_tokens),
                    semantic=os.getenv("AUTOPACK_CONTEXT_SEMANTIC_RELEVANCE", "1")
                    in ("1", "true", "True"),
                )

                if selection.omitted:
                    prompt_parts.append("\n# Context Budgeting (Autopack)")
                    prompt_parts.append(
                        f"Autopack kept {len(selection.kept)} files (mode={selection.mode}) "
                        f"and omitted {len(selection.omitted)} files to stay within budget."
                    )
                    prompt_parts.append(
                        "If you need a missing file, proceed with best effort; do NOT invent its contents."
                    )
                    prompt_parts.append("Omitted files (sample):")
                    for fp in selection.omitted[:40]:
                        prompt_parts.append(f"- {fp}")

                files = selection.kept
            except Exception as exc:
                logger.warning(f"[Builder] Context budgeting failed (non-fatal): {exc}")

        # Check if we need structured edit mode (files >1000 lines IN SCOPE)
        # NOTE: This should match the logic in execute_phase() above
        use_structured_edit_mode = False
        if config:
            # Get explicit scope paths from phase_spec
            scope_config = phase_spec.get("scope") or {}
            scope_paths = (
                scope_config.get("paths", []) if isinstance(scope_config, dict) else []
            )
            if not isinstance(scope_paths, list):
                scope_paths = []
            scope_paths = [sp for sp in scope_paths if isinstance(sp, str)]

            # Only check files in scope (or skip if no scope defined)
            if scope_paths:
                for file_path, content in files.items():
                    if isinstance(content, str) and isinstance(file_path, str):
                        # Only check if file is in scope
                        if any(file_path.startswith(sp) for sp in scope_paths):
                            line_count = content.count("\n") + 1
                            if line_count > config.max_lines_hard_limit:
                                use_structured_edit_mode = True
                                break

        if missing_scope_files:
            prompt_parts.append("\n# Missing Scoped Files")
            prompt_parts.append(
                "The following scoped files are within scope but do not exist yet. You may create them:"
            )
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

                line_count = content.count("\n") + 1
                prompt_parts.append(f"\n## {file_path} ({line_count} lines)")

                # Show file with line numbers
                lines = content.split("\n")

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
            modifiable_files: List[tuple[str, str, int, Dict[str, Any]]] = []
            readonly_files: List[tuple[str, str, int, Dict[str, Any]]] = []
            fallback_readonly: List[tuple[str, str, int]] = []

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

            # Add explicit contract (per GPT_RESPONSE14 Q1)
            if modifiable_files or readonly_files:
                prompt_parts.append("\n# File Modification Rules")
                prompt_parts.append(
                    "You are only allowed to modify files that are fully shown below."
                )
                prompt_parts.append(
                    "Any file marked as READ-ONLY CONTEXT must NOT appear in the `files` list in your JSON output."
                )
                prompt_parts.append(
                    "For each file you modify, return the COMPLETE new file content in `new_content`."
                )
                prompt_parts.append(
                    "Do NOT use ellipses (...) or omit any code that should remain."
                )

            # Show modifiable files with full content (Bucket A: ≤500 lines)
            if modifiable_files:
                prompt_parts.append("\n# Files You May Modify (COMPLETE CONTENT):")
                for file_path, content, line_count, meta in modifiable_files:
                    missing_note = (
                        " — file does not exist yet, create it." if meta.get("missing") else ""
                    )
                    prompt_parts.append(f"\n## {file_path} ({line_count} lines){missing_note}")
                    if meta.get("missing"):
                        prompt_parts.append(
                            "This file is currently missing. Provide the complete new content below."
                        )
                    prompt_parts.append(f"```\n{content}\n```")

            # Show read-only files with truncated content (Bucket B+C: >500 lines)
            readonly_combined = readonly_files + [
                (path, content, line_count, {})
                for path, content, line_count in fallback_readonly
            ]
            if readonly_combined:
                prompt_parts.append("\n# Read-Only Context Files (DO NOT MODIFY):")
                for file_path, content, line_count, meta in readonly_combined:
                    prompt_parts.append(f"\n## {file_path} (READ-ONLY CONTEXT — DO NOT MODIFY)")
                    prompt_parts.append(
                        f"This file has {line_count} lines (too large for full-file replacement)."
                    )
                    prompt_parts.append(
                        "You may read this snippet as context, but you must NOT include it in your JSON output."
                    )

                    # Show first 200 + last 50 lines for context
                    lines = content.split("\n")
                    first_part = "\n".join(lines[:200])
                    last_part = "\n".join(lines[-50:])
                    prompt_parts.append(
                        f"```\n{first_part}\n\n... [{line_count - 250} lines omitted] ...\n\n{last_part}\n```"
                    )
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
