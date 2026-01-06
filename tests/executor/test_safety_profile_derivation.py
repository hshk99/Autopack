"""Contract-first tests for safety profile derivation (BUILD-181 Phase 0).

These tests define the contract BEFORE implementation:
- Deterministic mapping from IntentionAnchorV2.pivot_intentions.safety_risk.risk_tolerance
- Missing safety_risk pivot → default strict (fail-safe)
- No silent "normal" default when intention is missing
"""

from __future__ import annotations

from datetime import datetime, timezone



def test_derive_safety_profile_minimal_risk_is_strict():
    """risk_tolerance='minimal' maps to safety_profile='strict'."""
    from autopack.executor.safety_profile import derive_safety_profile
    from autopack.intention_anchor.v2 import (
        IntentionAnchorV2,
        PivotIntentions,
        SafetyRiskIntention,
    )

    anchor = IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(
            safety_risk=SafetyRiskIntention(risk_tolerance="minimal")
        ),
    )

    result = derive_safety_profile(anchor)

    assert result == "strict"


def test_derive_safety_profile_low_risk_is_strict():
    """risk_tolerance='low' maps to safety_profile='strict'."""
    from autopack.executor.safety_profile import derive_safety_profile
    from autopack.intention_anchor.v2 import (
        IntentionAnchorV2,
        PivotIntentions,
        SafetyRiskIntention,
    )

    anchor = IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(
            safety_risk=SafetyRiskIntention(risk_tolerance="low")
        ),
    )

    result = derive_safety_profile(anchor)

    assert result == "strict"


def test_derive_safety_profile_moderate_risk_is_normal():
    """risk_tolerance='moderate' maps to safety_profile='normal'."""
    from autopack.executor.safety_profile import derive_safety_profile
    from autopack.intention_anchor.v2 import (
        IntentionAnchorV2,
        PivotIntentions,
        SafetyRiskIntention,
    )

    anchor = IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(
            safety_risk=SafetyRiskIntention(risk_tolerance="moderate")
        ),
    )

    result = derive_safety_profile(anchor)

    assert result == "normal"


def test_derive_safety_profile_high_risk_is_normal():
    """risk_tolerance='high' maps to safety_profile='normal'."""
    from autopack.executor.safety_profile import derive_safety_profile
    from autopack.intention_anchor.v2 import (
        IntentionAnchorV2,
        PivotIntentions,
        SafetyRiskIntention,
    )

    anchor = IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(
            safety_risk=SafetyRiskIntention(risk_tolerance="high")
        ),
    )

    result = derive_safety_profile(anchor)

    assert result == "normal"


def test_derive_safety_profile_missing_safety_risk_defaults_strict():
    """Missing safety_risk pivot → default strict (fail-safe)."""
    from autopack.executor.safety_profile import derive_safety_profile
    from autopack.intention_anchor.v2 import IntentionAnchorV2, PivotIntentions

    anchor = IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(),  # No safety_risk
    )

    result = derive_safety_profile(anchor)

    assert result == "strict"


def test_derive_safety_profile_empty_pivot_intentions_defaults_strict():
    """Empty pivot_intentions → default strict (fail-safe)."""
    from autopack.executor.safety_profile import derive_safety_profile
    from autopack.intention_anchor.v2 import IntentionAnchorV2, PivotIntentions

    anchor = IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(),
    )

    result = derive_safety_profile(anchor)

    assert result == "strict"


def test_derive_safety_profile_deterministic():
    """Same anchor always produces same safety profile."""
    from autopack.executor.safety_profile import derive_safety_profile
    from autopack.intention_anchor.v2 import (
        IntentionAnchorV2,
        PivotIntentions,
        SafetyRiskIntention,
    )

    anchor = IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(
            safety_risk=SafetyRiskIntention(risk_tolerance="moderate")
        ),
    )

    # Multiple calls
    results = [derive_safety_profile(anchor) for _ in range(10)]

    # All must be identical
    assert all(r == "normal" for r in results)


def test_derive_safety_profile_returns_literal_type():
    """Return type is exactly Literal['normal', 'strict']."""
    from autopack.executor.safety_profile import derive_safety_profile
    from autopack.intention_anchor.v2 import IntentionAnchorV2, PivotIntentions

    anchor = IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(),
    )

    result = derive_safety_profile(anchor)

    assert result in ("normal", "strict")
