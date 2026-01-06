"""Mitigation modules (BUILD-181 Phase 7).

Provides deterministic failure-to-mitigation rule generation.
No LLM required - uses templated rules for known failure signatures.
Proposals written run-locally, never to SOT.
"""

from .deterministic_rules import (
    MitigationInputs,
    MitigationProposalV1,
    Rule,
    generate_mitigation_proposal,
    known_signature_to_rule,
    validate_mitigation_proposal,
    write_mitigation_proposal,
)

__all__ = [
    "MitigationInputs",
    "MitigationProposalV1",
    "Rule",
    "generate_mitigation_proposal",
    "known_signature_to_rule",
    "validate_mitigation_proposal",
    "write_mitigation_proposal",
]
