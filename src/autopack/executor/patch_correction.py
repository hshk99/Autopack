"""Patch correction one-shot loop (BUILD-181 Phase 4).

Implements bounded correction for HTTP 422 validation failures.
Max 1 correction attempt per 422 event, with evidence recording.

BUILD-195: Added LLM-based correction for complex validation errors.

Properties:
- Max 1 correction attempt per event
- Evidence recorded regardless of outcome
- Stops after one attempt (no retry loop)
- Uses LLM for complex corrections when simple rules fail
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# Minimum budget fraction required to attempt correction
MIN_BUDGET_FOR_CORRECTION = 0.10


class CorrectedPatchResult(BaseModel):
    """Result of a patch correction attempt.

    Captures all information needed for evidence and debugging.
    """

    model_config = ConfigDict(extra="forbid")

    attempted: bool = Field(..., description="Whether correction was attempted")
    original_patch: str = Field(default="", description="Original patch content")
    error_detail: Dict[str, Any] = Field(default_factory=dict, description="Validator error")
    corrected_patch: Optional[str] = Field(
        default=None, description="Corrected patch if successful"
    )
    correction_successful: Optional[bool] = Field(
        default=None, description="Whether correction fixed the issue"
    )
    evidence: Optional[Dict[str, Any]] = Field(default=None, description="Evidence record")
    blocked_reason: Optional[str] = Field(
        default=None, description="Why correction was blocked (if not attempted)"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "attempted": self.attempted,
            "original_patch": self.original_patch,
            "error_detail": self.error_detail,
            "corrected_patch": self.corrected_patch,
            "correction_successful": self.correction_successful,
            "evidence": self.evidence,
            "blocked_reason": self.blocked_reason,
        }


def should_attempt_patch_correction(
    http_422_detail: Dict[str, Any],
    budget_remaining: float,
) -> bool:
    """Determine if patch correction should be attempted.

    Args:
        http_422_detail: Error detail from HTTP 422 response
        budget_remaining: Fraction of budget remaining (0.0-1.0)

    Returns:
        True if correction should be attempted
    """
    # Don't attempt if budget is too low
    if budget_remaining < MIN_BUDGET_FOR_CORRECTION:
        logger.debug(
            f"[PatchCorrection] Budget too low ({budget_remaining:.1%}), skipping correction"
        )
        return False

    # Check if error detail has actionable information
    if not http_422_detail:
        logger.debug("[PatchCorrection] Empty error detail, skipping correction")
        return False

    # We have budget and error detail - attempt correction
    return True


def _compute_inputs_hash(original_patch: str, error_detail: Dict[str, Any]) -> str:
    """Compute deterministic hash of correction inputs."""
    content = f"{original_patch}:{json.dumps(error_detail, sort_keys=True)}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _generate_evidence(
    original_patch: str,
    error_detail: Dict[str, Any],
    corrected_patch: Optional[str],
    success: bool,
) -> Dict[str, Any]:
    """Generate evidence record for correction attempt."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "inputs_hash": _compute_inputs_hash(original_patch, error_detail),
        "error_summary": _summarize_error(error_detail),
        "correction_attempted": True,
        "correction_successful": success,
        "corrected_patch_length": len(corrected_patch) if corrected_patch else 0,
    }


def _summarize_error(error_detail: Dict[str, Any]) -> str:
    """Generate concise error summary for evidence."""
    error_type = error_detail.get("error", "unknown")
    message = error_detail.get("message", "")
    path = error_detail.get("path", "")

    parts = [error_type]
    if message:
        # Truncate long messages
        parts.append(message[:100])
    if path:
        parts.append(f"at {path}")

    return " | ".join(parts)


def correct_patch_once(
    original_patch: str,
    validator_error_detail: Dict[str, Any],
    context: Dict[str, Any],
    llm_caller: Optional[Callable[[str], str]] = None,
) -> CorrectedPatchResult:
    """Attempt to correct a patch based on validator error.

    This is a single-shot correction: no retries even on failure.
    Evidence is recorded regardless of outcome.

    BUILD-195: Now uses LLM correction when simple rules fail.

    Args:
        original_patch: The original patch that failed validation
        validator_error_detail: Error details from HTTP 422 response
        context: Additional context (phase_id, run_id, etc.)
        llm_caller: Optional callable for LLM-based correction

    Returns:
        CorrectedPatchResult with outcome and evidence
    """
    logger.info(
        f"[PatchCorrection] Attempting one-shot correction for "
        f"run={context.get('run_id')}, phase={context.get('phase_id')}"
    )

    # Step 1: Try simple rule-based correction first (fast, no API call)
    corrected_patch = _attempt_simple_correction(original_patch, validator_error_detail)
    correction_method = "rule_based"

    # Step 2: If simple rules failed, try LLM correction (BUILD-195)
    if corrected_patch is None or corrected_patch == original_patch:
        logger.info("[PatchCorrection] Simple rules failed, attempting LLM correction")
        corrected_patch = _attempt_llm_correction(
            original_patch, validator_error_detail, llm_caller
        )
        correction_method = "llm" if corrected_patch else "failed"

    # Determine if correction was successful
    success = corrected_patch is not None and corrected_patch != original_patch

    # Generate evidence with correction method
    evidence = _generate_evidence(original_patch, validator_error_detail, corrected_patch, success)
    evidence["correction_method"] = correction_method

    return CorrectedPatchResult(
        attempted=True,
        original_patch=original_patch,
        error_detail=validator_error_detail,
        corrected_patch=corrected_patch,
        correction_successful=success,
        evidence=evidence,
        blocked_reason=None,
    )


def _attempt_simple_correction(
    original_patch: str,
    error_detail: Dict[str, Any],
) -> Optional[str]:
    """Attempt simple rule-based correction.

    This is a placeholder for more sophisticated correction logic.
    In practice, this would use:
    - Structured prompting with error context
    - Rule-based fixes for common issues
    - Schema-guided corrections
    """
    # Simple heuristic: if error mentions "missing field", add placeholder
    message = error_detail.get("message", "").lower()
    path = error_detail.get("path", "")

    if "required" in message or "missing" in message:
        # Try to add missing field (simplified)
        try:
            data = json.loads(original_patch)
            # Extract field name from path or message
            field_name = _extract_field_name(path, message)
            if field_name:
                _add_field_to_path(data, path, field_name, "")
                return json.dumps(data, indent=2)
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # Return None if no correction could be made
    return None


# BUILD-195: LLM-based patch correction

PATCH_CORRECTION_PROMPT = """You are a patch correction assistant. \
A patch failed validation with the following error.

ORIGINAL PATCH:
```
{original_patch}
```

VALIDATION ERROR:
{error_detail}

Your task: Fix the patch to resolve the validation error. \
Return ONLY the corrected patch content, no explanations.

Rules:
1. Preserve the original intent of the patch
2. Fix only what's needed to pass validation
3. Do not add unrelated changes
4. Return the complete corrected patch
"""


def _attempt_llm_correction(
    original_patch: str,
    error_detail: Dict[str, Any],
    llm_caller: Optional[Callable[[str], str]] = None,
) -> Optional[str]:
    """Attempt LLM-based correction when simple rules fail.

    BUILD-195: Uses LLM to intelligently fix validation errors.

    Args:
        original_patch: The original patch that failed validation
        error_detail: Error details from HTTP 422 response
        llm_caller: Optional callable that takes a prompt and returns LLM response.
                   If None, uses default Anthropic client.

    Returns:
        Corrected patch string, or None if correction failed
    """
    # Format error detail for prompt
    if isinstance(error_detail, dict):
        error_str = json.dumps(error_detail, indent=2)
    else:
        error_str = str(error_detail)

    prompt = PATCH_CORRECTION_PROMPT.format(
        original_patch=original_patch,
        error_detail=error_str,
    )

    try:
        if llm_caller:
            # Use provided caller (for testing or custom routing)
            corrected = llm_caller(prompt)
        else:
            # Use default Anthropic client
            corrected = _call_anthropic_for_correction(prompt)

        if corrected and corrected.strip():
            # Clean up response - remove markdown code blocks if present
            corrected = corrected.strip()
            if corrected.startswith("```"):
                lines = corrected.split("\n")
                # Remove first line (```json or ```) and last line (```)
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                corrected = "\n".join(lines)

            logger.info("[PatchCorrection] LLM correction generated successfully")
            return corrected

    except Exception as e:
        logger.warning(f"[PatchCorrection] LLM correction failed: {e}")

    return None


def _call_anthropic_for_correction(prompt: str) -> Optional[str]:
    """Call Anthropic API for patch correction.

    Uses haiku model for fast, cheap corrections.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.debug("[PatchCorrection] No ANTHROPIC_API_KEY, skipping LLM correction")
        return None

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)

        response = client.messages.create(
            model="claude-3-5-haiku-20241022",  # Fast, cheap model for corrections
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )

        if response.content and len(response.content) > 0:
            return response.content[0].text

    except ImportError:
        logger.debug("[PatchCorrection] anthropic package not installed")
    except Exception as e:
        logger.warning(f"[PatchCorrection] Anthropic API call failed: {e}")

    return None


def _extract_field_name(path: str, message: str) -> Optional[str]:
    """Extract field name from error path or message."""
    # Try path first (e.g., "$.data.name" -> "name")
    if path and "." in path:
        return path.split(".")[-1]

    # Try message (e.g., "Field 'name' is required" -> "name")
    import re

    match = re.search(r"['\"](\w+)['\"]", message)
    if match:
        return match.group(1)

    return None


def _add_field_to_path(data: Dict, path: str, field_name: str, value: Any) -> None:
    """Add a field at the specified path."""
    # Simplified path navigation
    parts = [p for p in path.replace("$.", "").split(".") if p]

    current = data
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]

    if isinstance(current, dict):
        current[field_name] = value


class PatchCorrectionTracker:
    """Tracks patch correction attempts to enforce one-shot limit.

    Ensures max 1 correction attempt per 422 event.
    BUILD-195: Now supports LLM-based correction.
    """

    def __init__(self, llm_caller: Optional[Callable[[str], str]] = None) -> None:
        self._attempted_events: Set[str] = set()
        self._llm_caller = llm_caller

    def attempt_correction(
        self,
        original_patch: str,
        validator_error_detail: Dict[str, Any],
        context: Dict[str, Any],
    ) -> CorrectedPatchResult:
        """Attempt correction with tracking.

        Args:
            original_patch: The original patch
            validator_error_detail: Error details
            context: Must include 'event_id' for tracking

        Returns:
            CorrectedPatchResult (blocked if already attempted)
        """
        event_id = context.get(
            "event_id", _compute_inputs_hash(original_patch, validator_error_detail)
        )

        # Check if already attempted
        if event_id in self._attempted_events:
            logger.debug(f"[PatchCorrection] Event {event_id} already attempted, blocking")
            return CorrectedPatchResult(
                attempted=False,
                original_patch=original_patch,
                error_detail=validator_error_detail,
                blocked_reason="max_attempts_exceeded",
            )

        # Mark as attempted
        self._attempted_events.add(event_id)

        # Perform correction with LLM support
        return correct_patch_once(
            original_patch, validator_error_detail, context, llm_caller=self._llm_caller
        )

    def reset(self) -> None:
        """Reset tracking (for testing)."""
        self._attempted_events.clear()
