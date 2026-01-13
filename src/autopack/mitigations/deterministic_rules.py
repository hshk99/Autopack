"""Deterministic mitigation rule generation (BUILD-181 Phase 7).

Maps known failure signatures to templated mitigation rules.
No LLM required - purely deterministic.

Properties:
- Same inputs → same proposal output
- No SOT writes during runtime
- Proposals written to run-local artifacts
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from autopack.file_layout import RunFileLayout

logger = logging.getLogger(__name__)

DETERMINISTIC_CREATED_AT = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


class Rule(BaseModel):
    """Mitigation rule for a known failure signature."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Unique rule identifier")
    description: str = Field(..., description="Human-readable description")
    prevention_action: str = Field(..., description="Action to prevent this failure")
    applies_to_signatures: List[str] = Field(
        ..., description="Failure signatures this rule handles"
    )
    severity: str = Field(default="medium", description="Severity: low, medium, high")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "rule_id": self.rule_id,
            "description": self.description,
            "prevention_action": self.prevention_action,
            "applies_to_signatures": self.applies_to_signatures,
            "severity": self.severity,
        }


class MitigationInputs(BaseModel):
    """Inputs for mitigation proposal generation."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., description="Run identifier")
    failure_signatures: List[str] = Field(..., description="List of failure signatures")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context")


class MitigationProposalV1(BaseModel):
    """Mitigation proposal artifact (v1 schema)."""

    model_config = ConfigDict(extra="forbid")

    format_version: str = Field(default="v1", description="Schema version")
    proposal_id: str = Field(..., description="Unique proposal identifier")
    run_id: str = Field(..., description="Run this proposal belongs to")
    # Deterministic timestamp: proposal output must be stable for identical inputs.
    created_at: datetime = Field(default_factory=lambda: DETERMINISTIC_CREATED_AT)
    failure_signatures: List[str] = Field(..., description="Input failure signatures")
    proposed_rules: List[Rule] = Field(default_factory=list, description="Generated rules")
    unmatched_signatures: List[str] = Field(
        default_factory=list, description="Signatures with no matching rule"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "format_version": self.format_version,
            "proposal_id": self.proposal_id,
            "run_id": self.run_id,
            "created_at": self.created_at.isoformat(),
            "failure_signatures": self.failure_signatures,
            "proposed_rules": [r.to_dict() for r in self.proposed_rules],
            "unmatched_signatures": self.unmatched_signatures,
        }


# Known failure signature patterns and their mitigation rules
KNOWN_RULES: Dict[str, Rule] = {
    "http_422_validation_failed:missing_field": Rule(
        rule_id="rule-http422-missing-field",
        description="HTTP 422 validation failure due to missing required field",
        prevention_action=(
            "Add schema validation before API calls. "
            "Ensure all required fields are populated using default values or user prompts."
        ),
        applies_to_signatures=["http_422_validation_failed:missing_field"],
        severity="medium",
    ),
    "http_422_validation_failed:invalid_type": Rule(
        rule_id="rule-http422-invalid-type",
        description="HTTP 422 validation failure due to incorrect field type",
        prevention_action=(
            "Add type coercion layer before API calls. Validate field types match expected schema."
        ),
        applies_to_signatures=["http_422_validation_failed:invalid_type"],
        severity="medium",
    ),
    "test_failure:assertion_error": Rule(
        rule_id="rule-test-assertion",
        description="Test failure due to assertion error",
        prevention_action=(
            "Review test expectations against implementation. "
            "Check for edge cases and boundary conditions."
        ),
        applies_to_signatures=["test_failure:assertion_error"],
        severity="high",
    ),
    "test_failure:timeout": Rule(
        rule_id="rule-test-timeout",
        description="Test failure due to timeout",
        prevention_action=(
            "Review async operations and network calls. "
            "Add appropriate timeout handling and retry logic."
        ),
        applies_to_signatures=["test_failure:timeout"],
        severity="medium",
    ),
    "build_failure:syntax_error": Rule(
        rule_id="rule-build-syntax",
        description="Build failure due to syntax error",
        prevention_action=(
            "Run linter/formatter before commits. Enable pre-commit hooks for syntax validation."
        ),
        applies_to_signatures=["build_failure:syntax_error"],
        severity="high",
    ),
    "build_failure:import_error": Rule(
        rule_id="rule-build-import",
        description="Build failure due to import error",
        prevention_action=(
            "Verify all imports exist and are correctly spelled. Check for circular import issues."
        ),
        applies_to_signatures=["build_failure:import_error"],
        severity="high",
    ),
    "runtime_error:attribute_error": Rule(
        rule_id="rule-runtime-attr",
        description="Runtime AttributeError (accessing non-existent attribute)",
        prevention_action=(
            "Add null checks before attribute access. Use Optional types and hasattr() guards."
        ),
        applies_to_signatures=["runtime_error:attribute_error"],
        severity="medium",
    ),
    "runtime_error:key_error": Rule(
        rule_id="rule-runtime-key",
        description="Runtime KeyError (accessing non-existent dict key)",
        prevention_action=(
            "Use dict.get() with defaults instead of direct access. "
            "Validate dict structure before access."
        ),
        applies_to_signatures=["runtime_error:key_error"],
        severity="medium",
    ),
}


def _normalize_signature(signature: str) -> str:
    """Normalize failure signature for matching."""
    # Remove trailing specifics for broader matching
    # e.g., "http_422_validation_failed:missing_field:name" -> "http_422_validation_failed:missing_field"
    parts = signature.split(":")
    if len(parts) >= 2:
        return ":".join(parts[:2])
    return signature


def known_signature_to_rule(signature: str) -> Optional[Rule]:
    """Map a failure signature to its mitigation rule.

    Args:
        signature: Failure signature string

    Returns:
        Rule if known, None otherwise
    """
    # Try exact match first
    if signature in KNOWN_RULES:
        return KNOWN_RULES[signature]

    # Try normalized match
    normalized = _normalize_signature(signature)
    if normalized in KNOWN_RULES:
        return KNOWN_RULES[normalized]

    # Try prefix matching
    for pattern, rule in KNOWN_RULES.items():
        if signature.startswith(pattern):
            return rule

    return None


def generate_mitigation_proposal(inputs: MitigationInputs) -> MitigationProposalV1:
    """Generate mitigation proposal from failure signatures.

    Deterministic: same inputs always produce identical output.

    Args:
        inputs: MitigationInputs with failure signatures

    Returns:
        MitigationProposalV1 with generated rules
    """
    # Deduplicate and sort signatures for determinism
    unique_signatures = sorted(set(inputs.failure_signatures))

    # Map signatures to rules
    rules: Dict[str, Rule] = {}  # rule_id -> Rule (deduplicated)
    unmatched: List[str] = []

    for sig in unique_signatures:
        rule = known_signature_to_rule(sig)
        if rule:
            rules[rule.rule_id] = rule
        else:
            unmatched.append(sig)

    # Sort rules by rule_id for determinism
    sorted_rules = sorted(rules.values(), key=lambda r: r.rule_id)

    # Generate deterministic proposal ID
    content_hash = hashlib.sha256(
        f"{inputs.run_id}:{','.join(unique_signatures)}".encode()
    ).hexdigest()[:8]
    proposal_id = f"mit-{content_hash}"

    return MitigationProposalV1(
        proposal_id=proposal_id,
        run_id=inputs.run_id,
        failure_signatures=unique_signatures,
        proposed_rules=sorted_rules,
        unmatched_signatures=sorted(unmatched),
    )


def validate_mitigation_proposal(proposal: MitigationProposalV1) -> Tuple[bool, str]:
    """Validate mitigation proposal.

    Args:
        proposal: MitigationProposalV1 to validate

    Returns:
        Tuple of (is_valid, reason)
    """
    if not proposal.proposal_id:
        return False, "Missing proposal_id"

    if not proposal.run_id:
        return False, "Missing run_id"

    if proposal.format_version != "v1":
        return False, f"Unknown format_version: {proposal.format_version}"

    # Validate rules have required fields
    for rule in proposal.proposed_rules:
        if not rule.rule_id:
            return False, "Rule missing rule_id"
        if not rule.description:
            return False, f"Rule {rule.rule_id} missing description"
        if not rule.prevention_action:
            return False, f"Rule {rule.rule_id} missing prevention_action"

    return True, "Valid"


def write_mitigation_proposal(
    layout: "RunFileLayout",
    proposal: MitigationProposalV1,
) -> Path:
    """Write mitigation proposal to run-local artifact path.

    Never writes to SOT paths.

    Args:
        layout: RunFileLayout for the run
        proposal: MitigationProposalV1 to write

    Returns:
        Path where proposal was written
    """
    # Ensure mitigations directory exists under run
    mitigations_dir = layout.base_dir / "mitigations"
    mitigations_dir.mkdir(parents=True, exist_ok=True)

    # Write proposal
    artifact_path = mitigations_dir / f"mitigation_proposal_{proposal.proposal_id}.json"
    artifact_path.write_text(
        json.dumps(proposal.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(f"[Mitigations] Wrote proposal {proposal.proposal_id} to {artifact_path}")
    return artifact_path
