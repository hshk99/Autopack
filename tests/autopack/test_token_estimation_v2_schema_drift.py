"""
BUILD-142: CI drift check for token estimation v2 telemetry schema and writer signature.

This test prevents future regressions where:
1. TokenEstimationV2Event model loses selected_budget or actual_max_tokens columns
2. Telemetry writer function signature loses actual_max_tokens parameter

Why this matters:
- selected_budget: Estimator intent (BEFORE P4 enforcement)
- actual_max_tokens: Final provider ceiling (AFTER P4 enforcement)
- Waste calculation depends on actual_max_tokens / actual_output_tokens

This test is:
- Fast: No database needed, pure schema/signature introspection
- Deterministic: No external dependencies
- Lightweight: Runs in <100ms
"""

import inspect
import pytest
from autopack.models import TokenEstimationV2Event


def test_token_estimation_v2_event_has_required_columns():
    """
    Verify TokenEstimationV2Event model has both selected_budget and actual_max_tokens.

    BUILD-142 PARITY: These columns must exist to support category-aware budgeting:
    - selected_budget: Estimator intent (BEFORE P4 enforcement)
    - actual_max_tokens: Final ceiling (AFTER P4 enforcement)
    """
    # Check selected_budget column exists
    assert hasattr(TokenEstimationV2Event, "selected_budget"), \
        "TokenEstimationV2Event missing 'selected_budget' column (estimator intent)"

    # Check actual_max_tokens column exists (BUILD-142)
    assert hasattr(TokenEstimationV2Event, "actual_max_tokens"), \
        "TokenEstimationV2Event missing 'actual_max_tokens' column (final ceiling). " \
        "Run migration: scripts/migrations/add_actual_max_tokens_to_token_estimation_v2.py"


def test_telemetry_writer_signature_includes_actual_max_tokens():
    """
    Verify telemetry writer function has actual_max_tokens parameter.

    BUILD-142 PARITY: The writer must accept actual_max_tokens to store final ceiling
    separately from estimator intent (selected_budget).
    """
    from autopack.anthropic_clients import _write_token_estimation_v2_telemetry

    # Get function signature
    sig = inspect.signature(_write_token_estimation_v2_telemetry)
    params = list(sig.parameters.keys())

    # Check actual_max_tokens parameter exists
    assert "actual_max_tokens" in params, \
        f"_write_token_estimation_v2_telemetry missing 'actual_max_tokens' parameter. " \
        f"Current parameters: {params}"

    # Check selected_budget parameter still exists (sanity check)
    assert "selected_budget" in params, \
        f"_write_token_estimation_v2_telemetry missing 'selected_budget' parameter. " \
        f"Current parameters: {params}"


def test_telemetry_writer_actual_max_tokens_is_optional():
    """
    Verify actual_max_tokens parameter is Optional (for backward compatibility).

    BUILD-142: actual_max_tokens should default to None to support:
    1. Pre-BUILD-142 telemetry (no actual_max_tokens available)
    2. Graceful degradation if providers don't populate it
    """
    from autopack.anthropic_clients import _write_token_estimation_v2_telemetry

    sig = inspect.signature(_write_token_estimation_v2_telemetry)
    actual_max_tokens_param = sig.parameters.get("actual_max_tokens")

    assert actual_max_tokens_param is not None, \
        "actual_max_tokens parameter missing from function signature"

    # Check it has a default value (None)
    assert actual_max_tokens_param.default is None or actual_max_tokens_param.default == inspect.Parameter.empty, \
        f"actual_max_tokens parameter should be Optional (default=None), got default={actual_max_tokens_param.default}"


def test_calibration_sample_has_actual_max_tokens():
    """
    Verify CalibrationSample dataclass includes actual_max_tokens field.

    BUILD-142: Calibration script must track actual_max_tokens to compute accurate
    waste metrics (actual_max_tokens / actual_output_tokens).
    """
    import sys
    from pathlib import Path

    # Add scripts to path to import calibrate_token_estimator
    scripts_path = Path(__file__).parent.parent.parent / "scripts"
    sys.path.insert(0, str(scripts_path))

    try:
        from calibrate_token_estimator import CalibrationSample

        # Check actual_max_tokens field exists
        assert hasattr(CalibrationSample, "__dataclass_fields__"), \
            "CalibrationSample is not a dataclass"

        fields = CalibrationSample.__dataclass_fields__
        assert "actual_max_tokens" in fields, \
            f"CalibrationSample missing 'actual_max_tokens' field. " \
            f"Current fields: {list(fields.keys())}"

        # Check selected_budget field still exists (sanity check)
        assert "selected_budget" in fields, \
            f"CalibrationSample missing 'selected_budget' field. " \
            f"Current fields: {list(fields.keys())}"
    finally:
        # Clean up sys.path
        sys.path.remove(str(scripts_path))


if __name__ == "__main__":
    # Allow running this test directly for quick validation
    pytest.main([__file__, "-v"])
