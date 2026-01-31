"""Doctor subsystem for diagnosing and fixing project issues.

Extracted from llm_service.py as part of Item 1.1 god file refactoring (PR-SVC-3).

The Doctor is an expert system that analyzes phase failures and recommends
recovery actions. It operates as a pre-filter in the error recovery pipeline.
"""

import json
import logging
from typing import Any, Optional

from ..error_recovery import (DoctorContextSummary, DoctorRequest,
                              DoctorResponse, choose_doctor_model,
                              should_escalate_doctor_model)

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


def execute_doctor(
    client: Any,
    request: DoctorRequest,
    ctx_summary: Optional[DoctorContextSummary] = None,
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    allow_escalation: bool = True,
    model_to_provider_fn: Optional[callable] = None,
    record_usage_fn: Optional[callable] = None,
    record_usage_total_only_fn: Optional[callable] = None,
) -> DoctorResponse:
    """
    Invoke the Autopack Doctor to diagnose a phase failure.

    Per GPT_RESPONSE8 Section 3.2: Doctor wrapper that:
    1. Resolves client/model via choose_doctor_model()
    2. Builds system + user messages using Doctor prompt template
    3. Parses JSON into DoctorResponse.from_dict()
    4. Records usage via provided callbacks
    5. Optionally escalates to strong model if confidence is low

    Args:
        client: LLM client instance (has .client attribute with chat/messages API)
        request: Doctor diagnostic request with failure context
        ctx_summary: Optional summary of phase-level error context
        run_id: Run identifier for usage tracking
        phase_id: Phase identifier for logging
        allow_escalation: Whether to escalate to strong model if needed
        model_to_provider_fn: Optional function to map model name to provider
        record_usage_fn: Optional function to record usage with exact token splits
        record_usage_total_only_fn: Optional function to record total-only usage

    Returns:
        DoctorResponse with action, confidence, rationale, and optional hints
    """
    from ..config_loader import load_doctor_config

    config = load_doctor_config()

    # 1. Choose Doctor model based on failure complexity
    # Per GPT_RESPONSE10: choose_doctor_model returns (model, is_complex) tuple
    model, is_complex = choose_doctor_model(request, ctx_summary)

    # Per GPT_RESPONSE10: Track error category in context
    if ctx_summary:
        ctx_summary.record_error_category(request.error_category)

    # 2. Build messages
    user_message = _build_doctor_user_message(request)

    # 3. Invoke LLM
    response = _call_doctor_llm(
        client,
        model,
        user_message,
        run_id,
        phase_id,
        model_to_provider_fn,
        record_usage_fn,
        record_usage_total_only_fn,
    )
    escalated = False

    # 4. Check for escalation (per GPT_RESPONSE7 + GPT_RESPONSE10 guardrails)
    if allow_escalation and should_escalate_doctor_model(
        response, model, request.builder_attempts, ctx_summary
    ):
        strong_response = _call_doctor_llm(
            client,
            config.strong_model,
            user_message,
            run_id,
            phase_id,
            model_to_provider_fn,
            record_usage_fn,
            record_usage_total_only_fn,
        )
        # Prefer strong response if its confidence is higher
        if strong_response.confidence >= response.confidence:
            response = strong_response
            escalated = True
            model = config.strong_model

    # Per GPT_RESPONSE10: Update context with Doctor response
    if ctx_summary:
        ctx_summary.record_doctor_response(response, escalated=escalated)

    # 5. Log structured Doctor decision (per GPT_RESPONSE10: single unified log)
    health_ratio = request.health_budget.get("total_failures", 0) / max(
        request.health_budget.get("total_cap", 25), 1
    )
    logger.info(
        f"[Doctor] Diagnosis complete: action={response.action}, confidence={response.confidence:.2f}, "
        f"phase={phase_id or request.phase_id}, model={model}, is_complex={is_complex}, "
        f"escalated={escalated}, health_ratio={health_ratio:.2f}"
    )

    return response


def _build_doctor_user_message(request: DoctorRequest) -> str:
    """Build user message for Doctor LLM call."""
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
        from ..intention_anchor import load_and_render_for_doctor

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


def _call_doctor_llm(
    client: Any,
    model: str,
    user_message: str,
    run_id: Optional[str],
    phase_id: Optional[str],
    model_to_provider_fn: Optional[callable] = None,
    record_usage_fn: Optional[callable] = None,
    record_usage_total_only_fn: Optional[callable] = None,
) -> DoctorResponse:
    """
    Call LLM for Doctor diagnosis and parse response.

    Args:
        client: LLM client instance (has .client attribute)
        model: Model to use (cheap or strong)
        user_message: Formatted user message
        run_id: Run identifier for usage tracking
        phase_id: Phase identifier for logging
        model_to_provider_fn: Optional function to map model name to provider
        record_usage_fn: Optional function to record usage with exact token splits
        record_usage_total_only_fn: Optional function to record total-only usage

    Returns:
        DoctorResponse parsed from LLM output
    """
    # Build messages
    messages = [
        {"role": "system", "content": DOCTOR_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    try:
        # Use the client's underlying API call
        if hasattr(client, "client") and hasattr(client.client, "chat"):
            # OpenAI client
            completion = client.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,  # Lower temperature for more consistent diagnosis
                max_tokens=1000,
                response_format={"type": "json_object"},
            )
            content = completion.choices[0].message.content
            # BUILD-144 P0: Use exact token counts from OpenAI
            if completion.usage:
                prompt_tokens = completion.usage.prompt_tokens
                completion_tokens = completion.usage.completion_tokens
                tokens_used = completion.usage.total_tokens
            else:
                prompt_tokens = None
                completion_tokens = None
                tokens_used = 0
        elif hasattr(client, "client") and hasattr(client.client, "messages"):
            # Anthropic client
            completion = client.client.messages.create(
                model=model,
                max_tokens=1000,
                system=DOCTOR_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            content = completion.content[0].text
            # BUILD-144 P0: Use exact token counts from Anthropic
            if completion.usage:
                prompt_tokens = completion.usage.input_tokens
                completion_tokens = completion.usage.output_tokens
                tokens_used = prompt_tokens + completion_tokens
            else:
                prompt_tokens = None
                completion_tokens = None
                tokens_used = 0
        else:
            raise RuntimeError(f"Unknown client type for model {model}")

        # Parse JSON response with robust extraction
        response = _parse_doctor_json(content)

        # Record usage with exact token counts (no guessing)
        if tokens_used > 0 and (record_usage_fn or record_usage_total_only_fn):
            provider = model_to_provider_fn(model) if model_to_provider_fn else "openai"

            if prompt_tokens is not None and completion_tokens is not None and record_usage_fn:
                # Exact counts available
                record_usage_fn(
                    provider=provider,
                    model=model,
                    role="doctor",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    run_id=run_id,
                    phase_id=phase_id,
                )
            elif record_usage_total_only_fn:
                # No exact splits - record total-only
                logger.warning(
                    f"[TOKEN-ACCOUNTING] Doctor call missing exact token counts (model={model}). "
                    f"Recording total_tokens={tokens_used} without split."
                )
                record_usage_total_only_fn(
                    provider=provider,
                    model=model,
                    role="doctor",
                    total_tokens=tokens_used,
                    run_id=run_id,
                    phase_id=phase_id,
                )

        return response

    except Exception as e:
        logger.error(f"[Doctor] LLM call failed: {e}")
        # Return conservative default on failure
        return DoctorResponse(
            action="replan",
            confidence=0.2,
            rationale=f"Doctor LLM call failed: {str(e)[:100]}",
            builder_hint=None,
            suggested_patch=None,
        )


def _parse_doctor_json(content: str) -> DoctorResponse:
    """
    Parse Doctor JSON response with robust extraction.

    Handles cases where the LLM returns JSON embedded in text (common with Claude),
    or returns malformed JSON.

    Args:
        content: Raw LLM response content

    Returns:
        DoctorResponse parsed from the content
    """
    import re

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
