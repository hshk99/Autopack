"""OpenAI-based Builder and Auditor implementations

Per v7 GPT architect recommendation:
- Direct OpenAI API integration (not Cursor)
- BuilderClient uses GPT-4.1/o-mini for code generation
- AuditorClient uses GPT-4.1 for code review
- JSON schema outputs for structured responses
"""

import os
import json
from typing import Dict, List, Optional
from openai import OpenAI

from .llm_client import BuilderResult, AuditorResult


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
        model: str = "gpt-4o"
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

        Returns:
            BuilderResult with patch_content and metadata
        """
        try:
            # Build system prompt for Builder
            system_prompt = self._build_system_prompt()

            # Build user prompt with phase details
            user_prompt = self._build_user_prompt(phase_spec, file_context)

            # Call OpenAI API with JSON schema response
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens or 4096,
                response_format={"type": "json_object"},
                temperature=0.2  # Lower temperature for more consistent code
            )

            # Parse response
            result_json = json.loads(response.choices[0].message.content)

            # Extract tokens used
            tokens_used = response.usage.total_tokens

            return BuilderResult(
                success=True,
                patch_content=result_json.get("patch", ""),
                builder_messages=result_json.get("messages", []),
                tokens_used=tokens_used,
                model_used=model
            )

        except Exception as e:
            return BuilderResult(
                success=False,
                patch_content="",
                builder_messages=[f"Builder error: {str(e)}"],
                tokens_used=0,
                model_used=model,
                error=str(e)
            )

    def _build_system_prompt(self) -> str:
        """Build system prompt for Builder"""
        return """You are an expert software engineer working as the Builder in an autonomous build system.

Your role:
1. Read the phase specification carefully
2. Generate clean, working code that implements the requirements
3. Return a unified git diff/patch format
4. Include clear commit messages
5. Ensure code follows best practices and is production-ready

Output format (JSON):
{
  "patch": "unified diff format patch content",
  "messages": ["list of messages about implementation choices"],
  "files_modified": ["list of files changed"],
  "tests_included": true/false
}

Guidelines:
- Write idiomatic code for the language/framework
- Include error handling where appropriate
- Add docstrings/comments for complex logic
- Follow existing code style in the repository
- Don't over-engineer - keep it simple and focused
- For test phases, ensure good coverage
- For docs phases, be clear and concise"""

    def _build_user_prompt(
        self,
        phase_spec: Dict,
        file_context: Optional[Dict]
    ) -> str:
        """Build user prompt with phase details"""
        prompt_parts = []

        # Add phase details
        prompt_parts.append(f"## Phase Specification\n")
        prompt_parts.append(f"**Phase ID:** {phase_spec.get('phase_id')}\n")
        prompt_parts.append(f"**Task Category:** {phase_spec.get('task_category')}\n")
        prompt_parts.append(f"**Complexity:** {phase_spec.get('complexity')}\n")
        prompt_parts.append(f"**Description:** {phase_spec.get('description')}\n")

        # Add acceptance criteria if present
        if acceptance_criteria := phase_spec.get('acceptance_criteria'):
            prompt_parts.append(f"\n**Acceptance Criteria:**\n")
            for idx, criterion in enumerate(acceptance_criteria, 1):
                prompt_parts.append(f"{idx}. {criterion}\n")

        # Add file context if provided
        if file_context:
            prompt_parts.append(f"\n## Repository Context\n")
            if existing_files := file_context.get('existing_files'):
                prompt_parts.append(f"**Existing Files:**\n")
                for file_path, content in existing_files.items():
                    prompt_parts.append(f"\n### {file_path}\n```\n{content}\n```\n")

        # Add instructions
        prompt_parts.append(f"\n## Instructions\n")
        prompt_parts.append("Generate a complete implementation as a unified git diff/patch.")
        prompt_parts.append("Return your response in the specified JSON format.")

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
        model: str = "gpt-4o"
    ) -> AuditorResult:
        """Review a patch and find issues

        Args:
            patch_content: Git diff/patch to review
            phase_spec: Phase specification for context
            max_tokens: Token budget limit for this call
            model: OpenAI model to use

        Returns:
            AuditorResult with issues_found and metadata
        """
        try:
            # Build system prompt for Auditor
            system_prompt = self._build_system_prompt()

            # Build user prompt with patch and context
            user_prompt = self._build_user_prompt(patch_content, phase_spec)

            # Call OpenAI API with JSON schema response
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens or 2048,
                response_format={"type": "json_object"},
                temperature=0.1  # Very low temperature for consistent reviews
            )

            # Parse response
            result_json = json.loads(response.choices[0].message.content)

            # Extract tokens used
            tokens_used = response.usage.total_tokens

            # Determine approval
            issues = result_json.get("issues", [])
            has_major_issues = any(
                issue.get("severity") == "major" for issue in issues
            )
            approved = not has_major_issues

            return AuditorResult(
                approved=approved,
                issues_found=issues,
                auditor_messages=result_json.get("messages", []),
                tokens_used=tokens_used,
                model_used=model
            )

        except Exception as e:
            return AuditorResult(
                approved=False,
                issues_found=[{
                    "severity": "major",
                    "category": "auditor_error",
                    "description": f"Auditor error: {str(e)}",
                    "location": "unknown"
                }],
                auditor_messages=[f"Auditor error: {str(e)}"],
                tokens_used=0,
                model_used=model,
                error=str(e)
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
        phase_spec: Dict
    ) -> str:
        """Build user prompt with patch and context"""
        prompt_parts = []

        # Add phase context
        prompt_parts.append(f"## Phase Context\n")
        prompt_parts.append(f"**Task Category:** {phase_spec.get('task_category')}\n")
        prompt_parts.append(f"**Complexity:** {phase_spec.get('complexity')}\n")
        prompt_parts.append(f"**Description:** {phase_spec.get('description')}\n")

        # Add patch
        prompt_parts.append(f"\n## Patch to Review\n```diff\n{patch_content}\n```\n")

        # Add review instructions
        prompt_parts.append(f"\n## Review Instructions\n")
        prompt_parts.append("Review this patch carefully for:")
        prompt_parts.append("1. Security vulnerabilities (SQL injection, XSS, etc.)")
        prompt_parts.append("2. Bugs and logic errors")
        prompt_parts.append("3. Code quality and best practices")
        prompt_parts.append("4. Test coverage (if this is a test phase)")
        prompt_parts.append("5. Documentation clarity (if this is a docs phase)")
        prompt_parts.append("\nReturn your review in the specified JSON format.")

        return "\n".join(prompt_parts)
