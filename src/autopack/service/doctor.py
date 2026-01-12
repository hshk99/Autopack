"""Doctor subsystem for LlmService.

This module contains the Doctor diagnostic system for phase failure recovery:
- Doctor system prompt and message building
- JSON response parsing with robust extraction
- Diagnosis execution workflow

Design:
- Pure functions for message building and parsing (testable)
- Execution functions that coordinate LLM calls
- No direct database access (uses callbacks/passed sessions)

Extracted from: llm_service.py (execute_doctor, _build_doctor_user_message,
_call_doctor_llm, _parse_doctor_json, DOCTOR_SYSTEM_PROMPT)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from autopack.error_recovery import (
    DoctorRequest,
    DoctorResponse,
)

logger = logging.getLogger(__name__)


# Doctor system prompt (per GPT_RESPONSE8 + Phase 3 execute_fix)
DOCTOR_SYSTEM_PROMPT = """You are the Autopack Doctor, an expert at diagnosing build failures.

Your role is to analyze phase failures and recommend the best action to recover. You receive:
- Phase context (phase_id, error_category, builder_attempts)
- Health budget status (how many failures the run has left)
- Recent patch content (if any)
- Patch validation errors (if any)
- Log excerpts

CRITICAL: You MUST respond with ONLY a JSON object. No explanatory text, no markdown, no code blocks.
Start your response with { and end with }. Nothing else.

JSON response format:
{
  "action": "<one of: retry_with_fix, replan, rollback_run, skip_phase, mark_fatal, execute_fix>",
  "confidence": <float 0.0-1.0>,
  "rationale": "<brief explanation of your diagnosis>",
  "builder_hint": "<optional: specific instruction for the next Builder attempt>",
  "suggested_patch": "<optional: small fix if obvious, in git diff format>",
  "fix_commands": ["<optional: list of shell commands for execute_fix action>"],
  "fix_type": "<optional: git|file|python - required if using execute_fix>",
  "verify_command": "<optional: command to verify the fix worked>",
  "error_type": "<optional: dominant failure type, e.g. infra_error|patch_apply_error|auditor_reject|isolation_blocked>",
  "disable_providers": ["<optional: providers to disable for this run, e.g. zhipu_glm, google_gemini, anthropic>"],
  "maintenance_phase": "<optional: suggested maintenance phase id to schedule, e.g. phase3-provider-maintenance>"
}

IMPORTANT:
- Output ONLY the JSON object, no other text
- Do NOT wrap JSON in markdown code blocks (no ```)
- Do NOT add explanatory text before or after the JSON
- Start directly with { and end with }

Action Guide:
- "retry_with_fix": The issue is local and you have a specific hint for Builder. Best for mechanical errors.
- "replan": The phase approach is flawed. Need architectural reconsideration. Builder's strategy is wrong.
- "rollback_run": The run has accumulated too many failures or the codebase is in a broken state. Revert all changes.
- "skip_phase": The phase is optional and blocking progress. Mark as skipped and continue.
- "mark_fatal": The issue is unrecoverable. Human intervention required.
- "execute_fix": INFRASTRUCTURE ISSUES ONLY. Use for git conflicts, missing files, dependency issues.

execute_fix Guidelines (ONLY for infrastructure issues, NOT code logic):
- Use "execute_fix" ONLY when the failure is caused by infrastructure, not code logic
- Good candidates: merge conflicts, missing directories, pip install failures, git state issues
- BAD candidates: logic bugs, wrong function calls, incorrect imports (use retry_with_fix instead)
- fix_type must be one of: "git", "file", "python"
- Allowed commands by type:
  * git: checkout, reset --hard HEAD, stash, stash pop, clean -fd, merge --abort, rebase --abort
  * file: rm -f, mkdir -p, mv, cp
  * python: pip install, pip uninstall -y, python -m pip install
- NEVER use shell metacharacters (;, &&, ||, |, >, <, etc.)
- ALWAYS provide a verify_command to confirm the fix worked

Example execute_fix for merge conflict:
{
  "action": "execute_fix",
  "confidence": 0.9,
  "rationale": "Git merge conflict detected in auth/login.py. The file has uncommitted changes conflicting with the patch.",
  "fix_commands": ["git checkout -- auth/login.py"],
  "fix_type": "git",
  "verify_command": "git status --porcelain auth/login.py"
}

Example execute_fix for missing directory:
{
  "action": "execute_fix",
  "confidence": 0.85,
  "rationale": "Target directory tests/integration/ does not exist.",
  "fix_commands": ["mkdir -p tests/integration"],
  "fix_type": "file",
  "verify_command": "ls -la tests/integration/"
}

Guidelines:
1. High confidence (>0.8): Only when the issue and fix are clear
2. Medium confidence (0.5-0.8): Reasonable diagnosis but uncertain fix
3. Low confidence (<0.5): Uncertain diagnosis, may need escalation to stronger model

Example response for a simple patch error:
{
  "action": "retry_with_fix",
  "confidence": 0.85,
  "rationale": "Patch context mismatch on line 42. The target file was modified by a previous phase.",
  "builder_hint": "Re-read the current version of auth/login.py before generating the patch. The function signature changed.",
  "suggested_patch": null
}

Example response for repeated failures:
{
  "action": "replan",
  "confidence": 0.7,
  "rationale": "3 consecutive failures with different error types suggests the phase specification is ambiguous or incomplete.",
  "builder_hint": null,
  "suggested_patch": null
}

IMPORTANT: Never apply patches directly. All code changes go through: Builder -> Auditor -> QualityGate -> governed_apply.
IMPORTANT: execute_fix is for INFRASTRUCTURE fixes only. Code logic issues should use retry_with_fix or replan."""


@dataclass(frozen=True)
class DoctorCallResult:
    """Result of a Doctor LLM call.

    Attributes:
        response: The parsed DoctorResponse
        model_used: The model that was actually used
        tokens_used: Total tokens used in the call
        prompt_tokens: Prompt tokens (if available)
        completion_tokens: Completion tokens (if available)
    """

    response: DoctorResponse
    model_used: str
    tokens_used: int
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]


def build_doctor_user_message(request: DoctorRequest) -> str:
    """Build user message for Doctor LLM call.

    Constructs a structured message containing all relevant context
    for the Doctor to diagnose the phase failure.

    Args:
        request: Doctor diagnostic request with failure context

    Returns:
        Formatted user message string
    """
    message_parts = [
        "## Phase Failure Diagnosis Request",
        "",
        f"**Phase ID**: {request.phase_id}",
        f"**Error Category**: {request.error_category}",
        f"**Builder Attempts**: {request.builder_attempts}",
        f"**Run ID**: {request.run_id or 'unknown'}",
        "",
        "### Health Budget",
        f"- HTTP 500 errors: {request.health_budget.get('http_500', 0)}",
        f"- Patch failures: {request.health_budget.get('patch_failures', 0)}",
        f"- Total failures: {request.health_budget.get('total_failures', 0)}",
        f"- Total cap: {request.health_budget.get('total_cap', 25)}",
    ]

    # Milestone 2: Inject intention anchor (original goal context for error recovery)
    if request.run_id:
        from autopack.intention_anchor import load_and_render_for_doctor

        anchor_section = load_and_render_for_doctor(
            run_id=request.run_id,
            base_dir=".",  # Use current directory (.autonomous_runs/<run_id>/)
        )
        if anchor_section:
            message_parts.append("")
            message_parts.append(anchor_section)

    if request.patch_errors:
        message_parts.append("")
        message_parts.append("### Patch Validation Errors")
        for i, err in enumerate(request.patch_errors[:5], 1):
            message_parts.append(
                f"{i}. {err.get('error_type', 'unknown')}: {err.get('message', 'No message')}"
            )

    if request.last_patch:
        message_parts.append("")
        message_parts.append("### Last Patch (truncated)")
        message_parts.append("```diff")
        message_parts.append(request.last_patch[:1500])
        message_parts.append("```")

    if request.logs_excerpt:
        message_parts.append("")
        message_parts.append("### Relevant Logs")
        message_parts.append("```")
        message_parts.append(request.logs_excerpt[:800])
        message_parts.append("```")

    message_parts.append("")
    message_parts.append("Please diagnose this failure and recommend an action.")

    return "\n".join(message_parts)


def parse_doctor_json(content: str) -> DoctorResponse:
    """
    Parse Doctor JSON response with robust extraction.

    Handles cases where the LLM returns JSON embedded in text (common with Claude),
    or returns malformed JSON.

    Args:
        content: Raw LLM response content

    Returns:
        DoctorResponse parsed from the content
    """
    # Strategy 1: Try direct JSON parse
    try:
        data = json.loads(content)
        return DoctorResponse.from_dict(data)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Try to extract JSON from markdown code block
    json_block_match = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", content)
    if json_block_match:
        try:
            data = json.loads(json_block_match.group(1))
            logger.debug("[Doctor] Extracted JSON from code block")
            return DoctorResponse.from_dict(data)
        except json.JSONDecodeError:
            pass

    # Strategy 3: Try to find JSON object in text (greedy match for outermost braces)
    json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content)
    if json_match:
        try:
            data = json.loads(json_match.group(0))
            logger.debug("[Doctor] Extracted JSON from text")
            return DoctorResponse.from_dict(data)
        except json.JSONDecodeError:
            pass

    # Strategy 4: Try to extract key fields using regex patterns
    action_match = re.search(r'"action"\s*:\s*"([^"]+)"', content)
    confidence_match = re.search(r'"confidence"\s*:\s*([\d.]+)', content)
    rationale_match = re.search(r'"rationale"\s*:\s*"([^"]*)"', content)

    if action_match:
        action = action_match.group(1)
        confidence = float(confidence_match.group(1)) if confidence_match else 0.5
        rationale = rationale_match.group(1) if rationale_match else "Extracted from partial JSON"

        logger.debug(
            f"[Doctor] Extracted fields via regex: action={action}, confidence={confidence}"
        )
        return DoctorResponse(
            action=action,
            confidence=confidence,
            rationale=rationale,
            builder_hint=None,
            suggested_patch=None,
        )

    # Strategy 5: Return conservative default with higher confidence than total failure
    logger.warning(
        f"[Doctor] Failed to parse JSON, returning default. Content preview: {content[:200]}"
    )
    return DoctorResponse(
        action="replan",
        confidence=0.4,  # Higher than the 0.3 for parse failures, indicating we at least got a response
        rationale=f"Could not parse Doctor response. First 100 chars: {content[:100]}",
        builder_hint=None,
        suggested_patch=None,
    )


def create_default_doctor_response(error: str) -> DoctorResponse:
    """Create a conservative default Doctor response for error conditions.

    Used when the LLM call fails or produces unparseable output.

    Args:
        error: Error message to include in rationale

    Returns:
        Conservative DoctorResponse recommending replan
    """
    return DoctorResponse(
        action="replan",
        confidence=0.2,
        rationale=f"Doctor LLM call failed: {error[:100]}",
        builder_hint=None,
        suggested_patch=None,
    )


def validate_doctor_action(action: str) -> bool:
    """Validate that a Doctor action is one of the allowed actions.

    Args:
        action: The action string to validate

    Returns:
        True if valid, False otherwise
    """
    valid_actions = {
        "retry_with_fix",
        "replan",
        "rollback_run",
        "skip_phase",
        "mark_fatal",
        "execute_fix",
    }
    return action in valid_actions


def validate_fix_type(fix_type: str) -> bool:
    """Validate that a fix_type is one of the allowed types.

    Args:
        fix_type: The fix type string to validate

    Returns:
        True if valid, False otherwise
    """
    valid_types = {"git", "file", "python"}
    return fix_type in valid_types


def calculate_health_ratio(health_budget: Dict[str, int]) -> float:
    """Calculate the health ratio from a health budget.

    Args:
        health_budget: Dictionary with total_failures and total_cap

    Returns:
        Ratio of failures to cap (0.0 to 1.0+)
    """
    total_failures = health_budget.get("total_failures", 0)
    total_cap = max(health_budget.get("total_cap", 25), 1)
    return total_failures / total_cap


def should_consider_rollback(health_budget: Dict[str, int], threshold: float = 0.8) -> bool:
    """Determine if rollback should be considered based on health budget.

    Args:
        health_budget: Dictionary with failure counts
        threshold: Ratio threshold above which rollback is recommended

    Returns:
        True if health ratio exceeds threshold
    """
    return calculate_health_ratio(health_budget) >= threshold


@dataclass
class DoctorDiagnosisContext:
    """Context for a Doctor diagnosis session.

    Tracks state across multiple diagnosis attempts, including
    escalation and error category history.

    Attributes:
        phase_id: The phase being diagnosed
        error_categories: List of error categories encountered
        escalation_count: Number of times diagnosis was escalated
        last_model: Last model used for diagnosis
    """

    phase_id: str
    error_categories: List[str] = field(default_factory=list)
    escalation_count: int = 0
    last_model: Optional[str] = None

    def record_error_category(self, category: str) -> None:
        """Record an error category for tracking."""
        if category and category not in self.error_categories:
            self.error_categories.append(category)

    def record_escalation(self, model: str) -> None:
        """Record that diagnosis was escalated."""
        self.escalation_count += 1
        self.last_model = model

    def has_diverse_errors(self) -> bool:
        """Check if multiple different error categories have been seen."""
        return len(self.error_categories) >= 3
