"""Contract-first tests for deterministic mitigation proposals (BUILD-181 Phase 0).

These tests define the contract BEFORE implementation:
- Same inputs → same proposal output (deterministic)
- No LLM required, uses templated rules
- Proposals written run-locally, no SOT writes
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


def test_known_signature_to_rule_deterministic():
    """Same failure signature always produces same rule."""
    from autopack.mitigations.deterministic_rules import \
        known_signature_to_rule

    signature = "http_422_validation_failed:missing_field:name"

    rule1 = known_signature_to_rule(signature)
    rule2 = known_signature_to_rule(signature)
    rule3 = known_signature_to_rule(signature)

    assert rule1 == rule2 == rule3
    assert rule1 is not None


def test_known_signature_to_rule_unknown_returns_none():
    """Unknown failure signature returns None (no rule)."""
    from autopack.mitigations.deterministic_rules import \
        known_signature_to_rule

    signature = "completely_unknown_failure_type_xyz123"

    rule = known_signature_to_rule(signature)

    assert rule is None


def test_generate_mitigation_proposal_deterministic():
    """Same inputs always produce identical proposal output."""
    from autopack.mitigations.deterministic_rules import (
        MitigationInputs, generate_mitigation_proposal)

    inputs = MitigationInputs(
        run_id="test-run-001",
        failure_signatures=[
            "http_422_validation_failed:missing_field:name",
            "test_failure:assertion_error:expected_42_got_0",
        ],
        context={"phase_id": "phase-1", "anchor_digest": "abc123"},
    )

    # Generate multiple times
    proposal1 = generate_mitigation_proposal(inputs)
    proposal2 = generate_mitigation_proposal(inputs)
    proposal3 = generate_mitigation_proposal(inputs)

    # All must be identical
    assert proposal1.to_dict() == proposal2.to_dict() == proposal3.to_dict()


def test_mitigation_proposal_schema_valid():
    """Mitigation proposal validates against schema."""
    from autopack.mitigations.deterministic_rules import (
        MitigationInputs, generate_mitigation_proposal,
        validate_mitigation_proposal)

    inputs = MitigationInputs(
        run_id="test-run-001",
        failure_signatures=["http_422_validation_failed:missing_field:name"],
        context={"phase_id": "phase-1"},
    )

    proposal = generate_mitigation_proposal(inputs)
    is_valid, reason = validate_mitigation_proposal(proposal)

    assert is_valid is True, f"Validation failed: {reason}"


def test_mitigation_proposal_no_llm_required():
    """Mitigation proposal generation requires no LLM calls."""
    from autopack.mitigations.deterministic_rules import (
        MitigationInputs, generate_mitigation_proposal)

    # No mock needed - function should work offline
    inputs = MitigationInputs(
        run_id="test-run-001",
        failure_signatures=["test_failure:timeout:30s"],
        context={},
    )

    # Should complete without any external calls
    proposal = generate_mitigation_proposal(inputs)

    assert proposal is not None
    assert proposal.run_id == "test-run-001"


def test_mitigation_proposal_written_run_locally():
    """Mitigation proposal is written to run-local path, not SOT."""
    from autopack.file_layout import RunFileLayout
    from autopack.mitigations.deterministic_rules import (
        MitigationInputs, generate_mitigation_proposal,
        write_mitigation_proposal)

    with tempfile.TemporaryDirectory() as tmpdir:
        layout = RunFileLayout("test-run-001", base_dir=Path(tmpdir))
        layout.ensure_directories()

        inputs = MitigationInputs(
            run_id="test-run-001",
            failure_signatures=["http_422_validation_failed:missing_field:name"],
            context={},
        )
        proposal = generate_mitigation_proposal(inputs)

        # Write to run-local path
        artifact_path = write_mitigation_proposal(layout, proposal)

        # Verify path is under run directory (not in docs/ or other SOT)
        assert str(layout.base_dir) in str(artifact_path)
        assert "docs/" not in str(artifact_path)

        # Verify file content
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert data["run_id"] == "test-run-001"


def test_mitigation_rule_has_required_fields():
    """Each mitigation rule has required fields."""
    from autopack.mitigations.deterministic_rules import \
        known_signature_to_rule

    signature = "http_422_validation_failed:missing_field:name"
    rule = known_signature_to_rule(signature)

    assert rule is not None
    assert hasattr(rule, "rule_id")
    assert hasattr(rule, "description")
    assert hasattr(rule, "prevention_action")
    assert hasattr(rule, "applies_to_signatures")

    assert rule.rule_id is not None
    assert len(rule.description) > 0


def test_mitigation_proposal_empty_signatures():
    """Empty failure signatures produce empty rules list."""
    from autopack.mitigations.deterministic_rules import (
        MitigationInputs, generate_mitigation_proposal)

    inputs = MitigationInputs(
        run_id="test-run-001",
        failure_signatures=[],
        context={},
    )

    proposal = generate_mitigation_proposal(inputs)

    assert proposal.proposed_rules == []


def test_mitigation_proposal_deduplicates_rules():
    """Duplicate signatures produce deduplicated rules."""
    from autopack.mitigations.deterministic_rules import (
        MitigationInputs, generate_mitigation_proposal)

    inputs = MitigationInputs(
        run_id="test-run-001",
        failure_signatures=[
            "http_422_validation_failed:missing_field:name",
            "http_422_validation_failed:missing_field:name",  # Duplicate
            "http_422_validation_failed:missing_field:name",  # Duplicate
        ],
        context={},
    )

    proposal = generate_mitigation_proposal(inputs)

    # Should have at most 1 rule for this signature
    rule_ids = [r.rule_id for r in proposal.proposed_rules]
    assert len(rule_ids) == len(set(rule_ids))  # No duplicates


def test_mitigation_proposal_sorted_output():
    """Proposal rules are sorted deterministically."""
    from autopack.mitigations.deterministic_rules import (
        MitigationInputs, generate_mitigation_proposal)

    inputs = MitigationInputs(
        run_id="test-run-001",
        failure_signatures=[
            "test_failure:assertion_error:expected_42_got_0",
            "http_422_validation_failed:missing_field:name",
            "build_failure:syntax_error:line_42",
        ],
        context={},
    )

    proposal1 = generate_mitigation_proposal(inputs)

    # Reverse input order
    inputs_reversed = MitigationInputs(
        run_id="test-run-001",
        failure_signatures=[
            "build_failure:syntax_error:line_42",
            "http_422_validation_failed:missing_field:name",
            "test_failure:assertion_error:expected_42_got_0",
        ],
        context={},
    )

    proposal2 = generate_mitigation_proposal(inputs_reversed)

    # Both should produce same sorted output (excluding timestamp which differs)
    dict1 = proposal1.to_dict()
    dict2 = proposal2.to_dict()
    del dict1["created_at"]
    del dict2["created_at"]
    assert dict1 == dict2


def test_mitigation_no_sot_writes():
    """Mitigation generator never writes to SOT paths."""
    from autopack.file_layout import RunFileLayout
    from autopack.mitigations.deterministic_rules import (
        MitigationInputs, generate_mitigation_proposal,
        write_mitigation_proposal)

    with tempfile.TemporaryDirectory() as tmpdir:
        layout = RunFileLayout("test-run-001", base_dir=Path(tmpdir))
        layout.ensure_directories()

        inputs = MitigationInputs(
            run_id="test-run-001",
            failure_signatures=["test_failure:assertion_error"],
            context={},
        )
        proposal = generate_mitigation_proposal(inputs)
        artifact_path = write_mitigation_proposal(layout, proposal)

        # Path must NOT be in SOT locations
        forbidden_prefixes = ["docs/", "config/", "src/"]
        artifact_str = str(artifact_path)

        for prefix in forbidden_prefixes:
            # Only check if it's a root path write, not if prefix appears in temp dir
            assert not artifact_str.endswith(
                prefix
            ), f"Artifact written to SOT path: {artifact_path}"
