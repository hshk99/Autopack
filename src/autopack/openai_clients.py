"""OpenAI-based Builder and Auditor implementations

Per v7 GPT architect recommendation:
- Direct OpenAI API integration (not Cursor)
- BuilderClient uses GPT-4.1/o-mini for code generation
- AuditorClient uses GPT-4.1 for code review
- JSON schema outputs for structured responses
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from openai import OpenAI

from .llm_client import AuditorResult, BuilderResult
from .token_estimator import TokenEstimator

logger = logging.getLogger(__name__)


class OpenAIBuilderClient:
    """Builder implementation using OpenAI API

    Generates code patches from phase specifications.
    Uses GPT-4.1/Codex family models for code generation.
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize OpenAI client

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    def execute_phase(
        self,
        phase_spec: Dict,
        file_context: Optional[Dict] = None,
        max_tokens: Optional[int] = None,
        # OpenAI client default model (fallback provider).
        model: str = "gpt-4o",
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
        use_full_file_mode: bool = True,
        config=None,
        retrieved_context: Optional[str] = None,
    ) -> BuilderResult:
        """Execute a phase and generate code patch

        Args:
            phase_spec: Phase specification with fields:
                - phase_id: str
                - task_category: str
                - complexity: str
                - description: str
                - acceptance_criteria: List[str]
            file_context: Current repo files (optional, for context)
            max_tokens: Token budget limit for this call
            model: OpenAI model to use
            project_rules: Persistent project learned rules (Stage 0B)
            run_hints: Within-run hints from earlier phases (Stage 0A)
            use_full_file_mode: Use full-file mode (not used by OpenAI yet)
            config: BuilderOutputConfig (not used by OpenAI yet)
            retrieved_context: Vector memory context (not used by OpenAI yet)

        Returns:
            BuilderResult with patch_content and metadata
        """
        try:
            # BUILD-142 PARITY: Token estimation with category-aware budgets
            # Defensive: ensure phase_spec is always a dict
            if phase_spec is None:
                phase_spec = {}

            # Extract metadata for token estimation
            task_category = phase_spec.get("task_category", "")
            complexity = phase_spec.get("complexity", "medium")
            deliverables = phase_spec.get("deliverables")
            if not deliverables:
                scope_cfg = phase_spec.get("scope") or {}
                if isinstance(scope_cfg, dict):
                    deliverables = scope_cfg.get("deliverables")
            deliverables = TokenEstimator.normalize_deliverables(deliverables)
            task_description = phase_spec.get("description", "")

            # BUILD-142 PARITY: Compute token budget using TokenEstimator
            token_estimate = None
            token_selected_budget = None

            if deliverables:
                try:
                    estimator = TokenEstimator(workspace=Path.cwd())
                    effective_category = task_category or (
                        "documentation"
                        if estimator._all_doc_deliverables(deliverables)
                        else "implementation"
                    )
                    token_estimate = estimator.estimate(
                        deliverables=deliverables,
                        category=effective_category,
                        complexity=complexity,
                        scope_paths=[],
                        task_description=task_description,
                    )
                    token_selected_budget = estimator.select_budget(token_estimate, complexity)

                    # Persist estimator output for telemetry
                    phase_spec["_estimated_output_tokens"] = token_estimate.estimated_tokens
                    phase_spec.setdefault("metadata", {}).setdefault("token_prediction", {}).update(
                        {
                            "predicted_output_tokens": token_estimate.estimated_tokens,
                            "selected_budget": token_selected_budget,
                            "confidence": token_estimate.confidence,
                            "source": "token_estimator",
                            "estimated_category": token_estimate.category,
                        }
                    )

                    logger.info(
                        f"[BUILD-142:OpenAI] Token estimate: {token_estimate.estimated_tokens} output tokens "
                        f"({token_estimate.deliverable_count} deliverables, confidence={token_estimate.confidence:.2f}), "
                        f"selected budget: {token_selected_budget}"
                    )
                except Exception as e:
                    logger.warning(
                        f"[BUILD-142:OpenAI] Token estimation failed, using fallback: {e}"
                    )
                    token_estimate = None
                    token_selected_budget = None

            # BUILD-142 PARITY: Apply complexity-based fallback or use category-aware budget
            if max_tokens is None:
                if token_selected_budget:
                    max_tokens = token_selected_budget
                elif complexity == "low":
                    max_tokens = 8192
                elif complexity == "medium":
                    max_tokens = 12288
                elif complexity == "high":
                    max_tokens = 16384
                else:
                    max_tokens = 8192

            # BUILD-142 PARITY: Conditional override for special modes (preserve category-aware budgets)
            # Note: OpenAI client doesn't have builder_mode="full_file", but we implement the logic
            # for consistency and future-proofing
            normalized_category = task_category.lower() if task_category else ""
            is_docs_like = normalized_category in [
                "docs",
                "documentation",
                "doc_synthesis",
                "doc_sot_update",
            ]

            # Apply 16384 floor conditionally (skip for docs-like with intentionally low budgets)
            should_apply_floor = (
                not token_selected_budget or token_selected_budget >= 16384 or not is_docs_like
            )

            if should_apply_floor:
                max_tokens = max(max_tokens, 16384)
                logger.debug(
                    f"[BUILD-142:OpenAI] Applied 16384 floor: max_tokens={max_tokens} "
                    f"(category={task_category}, selected_budget={token_selected_budget})"
                )
            else:
                logger.debug(
                    f"[BUILD-142:OpenAI] Preserving category-aware budget={token_selected_budget} for docs-like category={task_category} "
                    f"(skipping 16384 floor override)"
                )

            # BUILD-142 PARITY: Store selected_budget (estimator intent) BEFORE P4 enforcement
            if token_selected_budget:
                phase_spec.setdefault("metadata", {}).setdefault("token_prediction", {})[
                    "selected_budget"
                ] = token_selected_budget

            # BUILD-142 PARITY: P4 enforcement (final max_tokens >= selected_budget)
            if token_selected_budget:
                max_tokens = max(max_tokens or 0, token_selected_budget)
                # Store actual_max_tokens (final ceiling) AFTER P4 enforcement
                phase_spec.setdefault("metadata", {}).setdefault("token_prediction", {})[
                    "actual_max_tokens"
                ] = max_tokens
                logger.info(
                    f"[BUILD-142:OpenAI:P4] Final max_tokens enforcement: {max_tokens} (token_selected_budget={token_selected_budget})"
                )

            # Build system prompt for Builder
            system_prompt = self._build_system_prompt()

            # Build user prompt with phase details
            user_prompt = self._build_user_prompt(
                phase_spec, file_context, project_rules, run_hints
            )

            # Call OpenAI API - NO JSON mode (raw diff output like Anthropic)
            # GPT-5 models use max_completion_tokens instead of max_tokens
            params = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.2,
            }
            # Use calculated token budget (category-aware if available)
            token_budget = max_tokens
            if model.startswith("gpt-5"):
                params["max_completion_tokens"] = token_budget
            else:
                params["max_tokens"] = token_budget  # Backwards-compatible for earlier models

            response = self.client.chat.completions.create(**params)

            # Extract content
            content = response.choices[0].message.content

            # BUILD-143: Extract exact token counts from response.usage
            tokens_used = response.usage.total_tokens
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens

            # Extract patch from raw text (like Anthropic does)
            patch_content = self._extract_diff_from_text(content)

            if not patch_content:
                error_msg = "LLM output invalid format - no git diff markers found. Output must start with 'diff --git'"
                logger.error(f"{error_msg}\nFirst 500 chars: {content[:500]}")
                return BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=[error_msg],
                    tokens_used=tokens_used,
                    model_used=model,
                    error=error_msg,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )

            # Log successful completion
            logger.debug(
                f"Builder completed: {tokens_used} tokens (prompt={prompt_tokens}, completion={completion_tokens}), patch length: {len(patch_content)}"
            )

            return BuilderResult(
                success=True,
                patch_content=patch_content,
                builder_messages=["Generated by OpenAI Builder"],
                tokens_used=tokens_used,
                model_used=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except Exception as e:
            # GPT-4o Priority 3 Fix: Enhanced error logging
            logger.error(f"Builder execution failed: {str(e)}")
            logger.debug(
                f"Response content: {response.choices[0].message.content if 'response' in locals() else 'No response'}"
            )
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[f"Builder error: {str(e)}"],
                tokens_used=0,
                model_used=model,
                error=str(e),
            )

    def _extract_diff_from_text(self, text: str) -> str:
        """Extract git diff content from text that may contain explanations.

        Args:
            text: Raw text that may contain diff content

        Returns:
            Extracted diff content or empty string
        """
        import re

        lines = text.split("\n")
        diff_lines = []
        in_diff = False

        # Regex to match valid hunk headers: @@ -start,count +start,count @@
        re.compile(r"^@@\s+-\d+,\d+\s+\+\d+,\d+\s+@@\s*$")

        for line in lines:
            # Start of diff
            if line.startswith("diff --git"):
                in_diff = True
                diff_lines.append(line)
            # Continuation of diff
            elif in_diff:
                # Clean up malformed hunk headers (remove trailing context)
                if line.startswith("@@"):
                    # Extract the valid hunk header part only
                    # Match pattern: @@ -start,count +start,count @@
                    match = re.match(r"^(@@\s+-\d+,\d+\s+\+\d+,\d+\s+@@)", line)
                    if match:
                        # Use only the valid hunk header, discard anything after
                        clean_line = match.group(1)
                        diff_lines.append(clean_line)
                    else:
                        # Malformed hunk header, skip it
                        logger.warning(f"Skipping malformed hunk header: {line[:80]}")
                        continue
                # Check if still in diff (various diff markers)
                elif (
                    line.startswith(("index ", "---", "+++", "+", "-", " "))
                    or line.startswith("new file mode")
                    or line.startswith("deleted file mode")
                    or line.startswith("similarity index")
                    or line.startswith("rename from")
                    or line.startswith("rename to")
                    or line == ""
                ):
                    diff_lines.append(line)
                # Next diff section
                elif line.startswith("diff --git"):
                    diff_lines.append(line)
                # End of diff (explanatory text or other content)
                else:
                    # Stop if we hit markdown fence or explanatory text
                    if line.startswith("```") or line.startswith("#"):
                        break

        return "\n".join(diff_lines) if diff_lines else ""

    def _build_system_prompt(self) -> str:
        """Build system prompt for Builder"""
        return """You are an expert software engineer working as the Builder in an autonomous build system.

Your role:
1. Read the phase specification carefully
2. Generate clean, working code that implements the requirements
3. Return a unified git diff/patch format
4. Ensure code follows best practices and is production-ready

CRITICAL REQUIREMENTS:
1. Output ONLY a raw git diff format patch
2. Do NOT wrap it in JSON, markdown code blocks, or any other format
3. Do NOT add explanatory text before or after the patch
4. Start directly with: diff --git a/path/to/file.py b/path/to/file.py
5. NEVER use "..." or any abbreviation - show COMPLETE code
6. NEVER truncate or abbreviate ANY part of the diff
7. Show the ENTIRE file content - do NOT use ellipsis (...) ANYWHERE

GIT DIFF FORMAT RULES:
- Each file change MUST start with: diff --git a/PATH b/PATH
- Followed by: index HASH..HASH
- Then: --- a/PATH and +++ b/PATH
- Then: @@ -LINE,COUNT +LINE,COUNT @@ CONTEXT
- Then the actual changes with +/- prefixes
- Use COMPLETE file paths from repository root (e.g., src/autopack/main.py)
- Do NOT use relative or partial paths
- Do NOT abbreviate variable names, function names, or ANY code
- Write out ALL code in FULL - no shortcuts, no "...", no truncation

Guidelines:
- Write idiomatic code for the language/framework
- Include error handling where appropriate
- Add docstrings/comments for complex logic
- Follow existing code style in the repository
- Don't over-engineer - keep it simple and focused
- For test phases, ensure good coverage
- For docs phases, be clear and concise
- Output ONLY the raw git diff format patch (no JSON, no markdown fences, no explanations)
- Show COMPLETE code - never use ellipsis (...) to abbreviate"""

    def _build_user_prompt(
        self,
        phase_spec: Dict,
        file_context: Optional[Dict],
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
    ) -> str:
        """Build user prompt with phase details"""
        prompt_parts = []

        # Stage 0A + 0B: Inject learned rules and hints
        if project_rules or run_hints:
            from .learned_rules import (format_hints_for_prompt,
                                        format_rules_for_prompt)

            if project_rules:
                rules_section = format_rules_for_prompt(project_rules)
                if rules_section:
                    prompt_parts.append(rules_section)
                    prompt_parts.append("\n")

            if run_hints:
                hints_section = format_hints_for_prompt(run_hints)
                if hints_section:
                    prompt_parts.append(hints_section)
                    prompt_parts.append("\n")

        # Milestone 2: Inject intention anchor (canonical project goal)
        if run_id := phase_spec.get("run_id"):
            from .intention_anchor import load_and_render_for_builder

            anchor_section = load_and_render_for_builder(
                run_id=run_id,
                phase_id=phase_spec.get("phase_id", "unknown"),
                base_dir=".",  # Use current directory (.autonomous_runs/<run_id>/)
            )
            if anchor_section:
                prompt_parts.append(anchor_section)
                prompt_parts.append("\n")

        # Add phase details
        prompt_parts.append("## Phase Specification\n")
        prompt_parts.append(f"**Phase ID:** {phase_spec.get('phase_id')}\n")
        prompt_parts.append(f"**Task Category:** {phase_spec.get('task_category')}\n")
        prompt_parts.append(f"**Complexity:** {phase_spec.get('complexity')}\n")
        prompt_parts.append(f"**Description:** {phase_spec.get('description')}\n")

        # Add acceptance criteria if present
        if acceptance_criteria := phase_spec.get("acceptance_criteria"):
            prompt_parts.append("\n**Acceptance Criteria:**\n")
            for idx, criterion in enumerate(acceptance_criteria, 1):
                prompt_parts.append(f"{idx}. {criterion}\n")

        # Add file context if provided
        if file_context:
            prompt_parts.append("\n## Repository Context\n")
            if existing_files := file_context.get("existing_files"):
                prompt_parts.append("**Existing Files:**\n")
                for file_path, content in existing_files.items():
                    prompt_parts.append(f"\n### {file_path}\n```\n{content}\n```\n")

        # Add instructions
        prompt_parts.append("\n## Instructions\n")
        prompt_parts.append("Generate a complete implementation as a unified git diff/patch.")

        return "\n".join(prompt_parts)


class OpenAIAuditorClient:
    """Auditor implementation using OpenAI API

    Reviews code patches and finds issues.
    Uses GPT-4.1 for code review and analysis.
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize OpenAI client

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    def review_patch(
        self,
        patch_content: str,
        phase_spec: Dict,
        max_tokens: Optional[int] = None,
        # OpenAI client default model (fallback provider).
        model: str = "gpt-4o",
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
    ) -> AuditorResult:
        """Review a patch and find issues

        Args:
            patch_content: Git diff/patch to review
            phase_spec: Phase specification for context
            max_tokens: Token budget limit for this call
            model: OpenAI model to use
            project_rules: Persistent project learned rules (Stage 0B)
            run_hints: Within-run hints from earlier phases (Stage 0A)

        Returns:
            AuditorResult with issues_found and metadata
        """
        try:
            # Build system prompt for Auditor
            system_prompt = self._build_system_prompt()

            # Build user prompt with patch and context
            user_prompt = self._build_user_prompt(
                patch_content, phase_spec, project_rules, run_hints
            )

            # Call OpenAI API with JSON schema response
            params = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
            }
            # Higher token limit for complex reviews (actual usage ~500 tokens)
            token_budget = max_tokens or 8192
            if model.startswith("gpt-5"):
                params["max_completion_tokens"] = token_budget
            else:
                params["max_tokens"] = token_budget

            response = self.client.chat.completions.create(**params)

            # Parse response
            result_json = json.loads(response.choices[0].message.content)

            # BUILD-143: Extract exact token counts from response.usage
            tokens_used = response.usage.total_tokens
            prompt_tokens = response.usage.prompt_tokens
            completion_tokens = response.usage.completion_tokens

            # Determine approval
            issues = result_json.get("issues", [])
            has_major_issues = any(issue.get("severity") == "major" for issue in issues)
            approved = not has_major_issues

            return AuditorResult(
                approved=approved,
                issues_found=issues,
                auditor_messages=result_json.get("messages", []),
                tokens_used=tokens_used,
                model_used=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except Exception as e:
            return AuditorResult(
                approved=False,
                issues_found=[
                    {
                        "severity": "major",
                        "category": "auditor_error",
                        "description": f"Auditor error: {str(e)}",
                        "location": "unknown",
                    }
                ],
                auditor_messages=[f"Auditor error: {str(e)}"],
                tokens_used=0,
                model_used=model,
                error=str(e),
            )

    def _build_system_prompt(self) -> str:
        """Build system prompt for Auditor"""
        return """You are an expert code reviewer working as the Auditor in an autonomous build system.

Your role:
1. Review code patches for issues
2. Check for security vulnerabilities, bugs, code quality problems
3. Classify issues by severity (minor/major)
4. Approve patches with no major issues

Output format (JSON):
{
  "approved": true/false,
  "issues": [
    {
      "severity": "minor|major",
      "category": "security|bug|quality|style|test|documentation",
      "description": "Clear description of the issue",
      "location": "file:line or general area",
      "suggestion": "How to fix (optional)"
    }
  ],
  "messages": ["list of review comments"],
  "tests_verified": true/false
}

Severity guidelines:
- **major**: Security vulnerabilities, critical bugs, missing error handling, broken functionality
- **minor**: Style issues, minor improvements, missing comments, test coverage gaps

Review checklist:
✓ Security: SQL injection, XSS, command injection, auth/authz issues
✓ Bugs: Logic errors, edge cases, null/undefined handling
✓ Quality: Code structure, duplication, complexity
✓ Tests: Coverage, test quality, missing test cases
✓ Documentation: Docstrings, comments for complex logic

Be thorough but fair. Approve patches that work correctly even if they have minor style issues."""

    def _build_user_prompt(
        self,
        patch_content: str,
        phase_spec: Dict,
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
    ) -> str:
        """Build user prompt with patch and context"""
        prompt_parts = []

        # Stage 0A + 0B: Inject learned rules and hints
        if project_rules or run_hints:
            from .learned_rules import (format_hints_for_prompt,
                                        format_rules_for_prompt)

            if project_rules:
                rules_section = format_rules_for_prompt(project_rules)
                if rules_section:
                    prompt_parts.append(rules_section)
                    prompt_parts.append("\n")

            if run_hints:
                hints_section = format_hints_for_prompt(run_hints)
                if hints_section:
                    prompt_parts.append(hints_section)
                    prompt_parts.append("\n")

        # Milestone 2: Inject intention anchor (for validation context)
        if run_id := phase_spec.get("run_id"):
            from .intention_anchor import load_and_render_for_auditor

            anchor_section = load_and_render_for_auditor(
                run_id=run_id,
                base_dir=".",  # Use current directory (.autonomous_runs/<run_id>/)
            )
            if anchor_section:
                prompt_parts.append(anchor_section)
                prompt_parts.append("\n")

        # Add phase context
        prompt_parts.append("## Phase Context\n")
        prompt_parts.append(f"**Task Category:** {phase_spec.get('task_category')}\n")
        prompt_parts.append(f"**Complexity:** {phase_spec.get('complexity')}\n")
        prompt_parts.append(f"**Description:** {phase_spec.get('description')}\n")

        # Add patch
        prompt_parts.append(f"\n## Patch to Review\n```diff\n{patch_content}\n```\n")

        # Add review instructions
        prompt_parts.append("\n## Review Instructions\n")
        prompt_parts.append("Review this patch carefully for:")
        prompt_parts.append("1. Security vulnerabilities (SQL injection, XSS, etc.)")
        prompt_parts.append("2. Bugs and logic errors")
        prompt_parts.append("3. Code quality and best practices")
        prompt_parts.append("4. Test coverage (if this is a test phase)")
        prompt_parts.append("5. Documentation clarity (if this is a docs phase)")
        prompt_parts.append("\nReturn your review in the specified JSON format.")

        return "\n".join(prompt_parts)
