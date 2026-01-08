"""Payload schema correction for HTTP 422 validation errors (BUILD-195).

Implements bounded correction for FastAPI 422 validation failures on builder_result POST.
These are PAYLOAD SCHEMA errors (missing fields, wrong types, extra keys), not patch format errors.

Max 1 correction attempt per 422 event, with evidence recording.

Properties:
- Max 1 correction attempt per event
- Evidence recorded regardless of outcome
- Stops after one attempt (no retry loop)
- Deterministic fixes for common schema drift
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# Minimum budget fraction required to attempt correction
MIN_BUDGET_FOR_CORRECTION = 0.10


class PayloadCorrectionResult(BaseModel):
    """Result of a payload correction attempt.

    Captures all information needed for evidence and debugging.
    """

    model_config = ConfigDict(extra="forbid")

    attempted: bool = Field(..., description="Whether correction was attempted")
    original_payload: Dict[str, Any] = Field(default_factory=dict, description="Original payload")
    error_detail: List[Dict[str, Any]] = Field(
        default_factory=list, description="FastAPI 422 error detail"
    )
    corrected_payload: Optional[Dict[str, Any]] = Field(
        default=None, description="Corrected payload if successful"
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
            "original_payload": self.original_payload,
            "error_detail": self.error_detail,
            "corrected_payload": self.corrected_payload,
            "correction_successful": self.correction_successful,
            "evidence": self.evidence,
            "blocked_reason": self.blocked_reason,
        }


def should_attempt_payload_correction(
    http_422_detail: Any,
    budget_remaining: float,
) -> bool:
    """Determine if payload correction should be attempted.

    Args:
        http_422_detail: Error detail from HTTP 422 response (usually list of errors)
        budget_remaining: Fraction of budget remaining (0.0-1.0)

    Returns:
        True if correction should be attempted
    """
    # Don't attempt if budget is too low
    if budget_remaining < MIN_BUDGET_FOR_CORRECTION:
        logger.debug(f"[PayloadCorrection] Budget too low ({budget_remaining:.1%}), skipping")
        return False

    # Check if error detail has actionable information
    if not http_422_detail:
        logger.debug("[PayloadCorrection] Empty error detail, skipping correction")
        return False

    # We have budget and error detail - attempt correction
    return True


def _compute_inputs_hash(payload: Dict[str, Any], error_detail: Any) -> str:
    """Compute deterministic hash of correction inputs."""
    content = f"{json.dumps(payload, sort_keys=True)}:{json.dumps(error_detail, sort_keys=True, default=str)}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _generate_evidence(
    original_payload: Dict[str, Any],
    error_detail: Any,
    corrected_payload: Optional[Dict[str, Any]],
    success: bool,
    corrections_made: List[str],
) -> Dict[str, Any]:
    """Generate evidence record for correction attempt."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "inputs_hash": _compute_inputs_hash(original_payload, error_detail),
        "error_count": len(error_detail) if isinstance(error_detail, list) else 1,
        "corrections_made": corrections_made,
        "correction_attempted": True,
        "correction_successful": success,
    }


def _parse_fastapi_422_detail(error_detail: Any) -> List[Dict[str, Any]]:
    """Parse FastAPI 422 detail format into structured errors.

    FastAPI returns errors as: {"detail": [{"loc": [...], "msg": "...", "type": "..."}]}

    Args:
        error_detail: Raw error detail (could be list or dict with 'detail' key)

    Returns:
        List of error dicts with loc, msg, type
    """
    if isinstance(error_detail, list):
        return error_detail
    if isinstance(error_detail, dict):
        detail = error_detail.get("detail", [])
        if isinstance(detail, list):
            return detail
        return [error_detail]
    return []


# Default values for known BuilderResult fields
BUILDER_RESULT_DEFAULTS: Dict[str, Any] = {
    "run_type": "project_build",
    "allowed_paths": [],
    "patch_content": None,
    "files_changed": [],
    "lines_added": 0,
    "lines_removed": 0,
    "builder_attempts": 1,
    "tokens_used": 0,
    "duration_minutes": 0.0,
    "probe_results": [],
    "suggested_issues": [],
    "notes": "",
}

# Fields that must exist (no safe default)
BUILDER_RESULT_REQUIRED = {"phase_id", "run_id", "status"}

# Known extra fields that can be safely dropped
KNOWN_EXTRA_FIELDS = {
    "extra_data",
    "metadata",
    "debug_info",
    "_internal",
}


def correct_payload_once(
    original_payload: Dict[str, Any],
    validator_error_detail: Any,
    context: Dict[str, Any],
    llm_caller: Optional[Callable[[str], str]] = None,
) -> PayloadCorrectionResult:
    """Attempt to correct a payload based on 422 validation errors.

    This is a single-shot correction: no retries even on failure.
    Evidence is recorded regardless of outcome.

    Applies deterministic fixes:
    1. Drop unknown/extra fields if extra="forbid" error
    2. Add defaults for missing optional fields
    3. Coerce types for known type mismatches

    Args:
        original_payload: The original payload that failed validation
        validator_error_detail: Error details from HTTP 422 response
        context: Additional context (phase_id, run_id, etc.)
        llm_caller: Optional callable for LLM-based correction (used as fallback)

    Returns:
        PayloadCorrectionResult with outcome and evidence
    """
    logger.info(
        f"[PayloadCorrection] Attempting one-shot correction for "
        f"run={context.get('run_id')}, phase={context.get('phase_id')}"
    )

    errors = _parse_fastapi_422_detail(validator_error_detail)
    corrections_made: List[str] = []
    corrected_payload = original_payload.copy()

    for error in errors:
        loc = error.get("loc", [])
        msg = error.get("msg", "")
        error_type = error.get("type", "")

        # Build field path from loc (e.g., ["body", "files_changed"] -> "files_changed")
        field_path = loc[-1] if loc else None

        # Handle extra field errors (extra="forbid")
        if "extra" in error_type.lower() or "extra fields" in msg.lower():
            if field_path and field_path in corrected_payload:
                del corrected_payload[field_path]
                corrections_made.append(f"dropped_extra_field:{field_path}")
                logger.debug(f"[PayloadCorrection] Dropped extra field: {field_path}")
            continue

        # Handle missing field errors
        if "missing" in error_type.lower() or "field required" in msg.lower():
            if field_path and field_path not in corrected_payload:
                if field_path in BUILDER_RESULT_DEFAULTS:
                    corrected_payload[field_path] = BUILDER_RESULT_DEFAULTS[field_path]
                    corrections_made.append(f"added_default:{field_path}")
                    logger.debug(f"[PayloadCorrection] Added default for: {field_path}")
                elif field_path in BUILDER_RESULT_REQUIRED:
                    # Cannot fix missing required field without context
                    logger.warning(
                        f"[PayloadCorrection] Cannot fix missing required field: {field_path}"
                    )
            continue

        # Handle type errors
        if "type" in error_type.lower():
            if field_path and field_path in corrected_payload:
                value = corrected_payload[field_path]
                # Try common type coercions
                fixed_value = _attempt_type_coercion(field_path, value, msg)
                if fixed_value is not None:
                    corrected_payload[field_path] = fixed_value
                    corrections_made.append(f"coerced_type:{field_path}")
                    logger.debug(f"[PayloadCorrection] Coerced type for: {field_path}")

    # Check if we made any corrections
    success = len(corrections_made) > 0 and corrected_payload != original_payload

    # If deterministic rules didn't work and LLM caller provided, try LLM fallback
    if not success and llm_caller:
        logger.info("[PayloadCorrection] Deterministic rules failed, attempting LLM correction")
        llm_result = _attempt_llm_payload_correction(original_payload, errors, llm_caller)
        if llm_result:
            corrected_payload = llm_result
            corrections_made.append("llm_correction")
            success = True

    # Generate evidence
    evidence = _generate_evidence(
        original_payload, validator_error_detail, corrected_payload, success, corrections_made
    )
    evidence["correction_method"] = "llm" if "llm_correction" in corrections_made else "rule_based"

    return PayloadCorrectionResult(
        attempted=True,
        original_payload=original_payload,
        error_detail=errors,
        corrected_payload=corrected_payload if success else None,
        correction_successful=success,
        evidence=evidence,
        blocked_reason=None,
    )


def _attempt_type_coercion(field_name: str, value: Any, error_msg: str) -> Optional[Any]:
    """Attempt to coerce value to expected type based on error message.

    Args:
        field_name: Name of the field
        value: Current value
        error_msg: Error message describing expected type

    Returns:
        Coerced value or None if coercion not possible
    """
    error_msg_lower = error_msg.lower()

    # String to int coercion
    if "int" in error_msg_lower and isinstance(value, str):
        try:
            return int(value)
        except (ValueError, TypeError):
            pass

    # String to float coercion
    if "float" in error_msg_lower and isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            pass

    # Int/float to string coercion
    if "str" in error_msg_lower and isinstance(value, (int, float)):
        return str(value)

    # Single value to list coercion
    if "list" in error_msg_lower and not isinstance(value, list):
        return [value]

    # Empty string to None for optional fields
    if value == "" and field_name in BUILDER_RESULT_DEFAULTS:
        default = BUILDER_RESULT_DEFAULTS[field_name]
        if default is None:
            return None

    return None


def _attempt_llm_payload_correction(
    original_payload: Dict[str, Any],
    errors: List[Dict[str, Any]],
    llm_caller: Callable[[str], str],
) -> Optional[Dict[str, Any]]:
    """Attempt LLM-based payload correction as fallback.

    Args:
        original_payload: The original payload
        errors: List of validation errors
        llm_caller: Callable that takes prompt and returns LLM response

    Returns:
        Corrected payload dict or None if correction failed
    """
    prompt = f"""You are a payload correction assistant.
A BuilderResult payload failed schema validation.

ORIGINAL PAYLOAD:
```json
{json.dumps(original_payload, indent=2)}
```

VALIDATION ERRORS:
```json
{json.dumps(errors, indent=2)}
```

Fix the payload to resolve validation errors. Return ONLY valid JSON, no explanations.

Rules:
1. Remove extra fields that aren't in the schema
2. Add missing required fields with sensible defaults
3. Fix type mismatches (e.g., string "5" -> integer 5)
4. Keep all valid fields unchanged
"""

    try:
        response = llm_caller(prompt)
        if response:
            # Clean up response - remove markdown code blocks if present
            cleaned = response.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                cleaned = "\n".join(lines)

            return json.loads(cleaned)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"[PayloadCorrection] LLM correction failed: {e}")

    return None


class PayloadCorrectionTracker:
    """Tracks payload correction attempts to enforce one-shot limit.

    Ensures max 1 correction attempt per 422 event.
    """

    def __init__(self, llm_caller: Optional[Callable[[str], str]] = None) -> None:
        self._attempted_events: Set[str] = set()
        self._llm_caller = llm_caller

    def attempt_correction(
        self,
        original_payload: Dict[str, Any],
        validator_error_detail: Any,
        context: Dict[str, Any],
    ) -> PayloadCorrectionResult:
        """Attempt correction with tracking.

        Args:
            original_payload: The original payload
            validator_error_detail: Error details
            context: Must include 'event_id' for tracking

        Returns:
            PayloadCorrectionResult (blocked if already attempted)
        """
        event_id = context.get(
            "event_id", _compute_inputs_hash(original_payload, validator_error_detail)
        )

        # Check if already attempted
        if event_id in self._attempted_events:
            logger.debug(f"[PayloadCorrection] Event {event_id} already attempted, blocking")
            return PayloadCorrectionResult(
                attempted=False,
                original_payload=original_payload,
                error_detail=_parse_fastapi_422_detail(validator_error_detail),
                blocked_reason="max_attempts_exceeded",
            )

        # Mark as attempted
        self._attempted_events.add(event_id)

        # Perform correction with LLM support
        return correct_payload_once(
            original_payload, validator_error_detail, context, llm_caller=self._llm_caller
        )

    def reset(self) -> None:
        """Reset tracking (for testing)."""
        self._attempted_events.clear()
