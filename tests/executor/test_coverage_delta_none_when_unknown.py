"""Contract-first tests for coverage delta handling (BUILD-181 Phase 0).

These tests define the contract BEFORE implementation:
- Coverage delta returns None when unknown, not 0.0
- No placeholder metrics emitted
- Explicit "unknown" state when data unavailable
"""

from __future__ import annotations


import pytest


def test_coverage_delta_none_when_ci_result_missing():
    """Coverage delta is None when CI result is missing."""
    from autopack.executor.coverage_metrics import compute_coverage_delta

    result = compute_coverage_delta(None)

    assert result is None


def test_coverage_delta_none_when_coverage_data_absent():
    """Coverage delta is None when CI result lacks coverage data."""
    from autopack.executor.coverage_metrics import compute_coverage_delta

    ci_result = {
        "status": "passed",
        "tests_run": 42,
        "tests_passed": 42,
        # No coverage data
    }

    result = compute_coverage_delta(ci_result)

    assert result is None


def test_coverage_delta_returns_real_value_when_available():
    """Coverage delta returns real value when coverage data is present."""
    from autopack.executor.coverage_metrics import compute_coverage_delta

    ci_result = {
        "status": "passed",
        "tests_run": 42,
        "tests_passed": 42,
        "coverage": {
            "baseline": 85.5,
            "current": 87.2,
            "delta": 1.7,
        },
    }

    result = compute_coverage_delta(ci_result)

    assert result == pytest.approx(1.7)


def test_coverage_delta_not_zero_when_unknown():
    """Coverage delta is NEVER 0.0 as placeholder for unknown."""
    from autopack.executor.coverage_metrics import compute_coverage_delta

    # Various cases that should NOT return 0.0
    cases = [
        None,
        {},
        {"status": "passed"},
        {"coverage": None},
        {"coverage": {}},
    ]

    for ci_result in cases:
        result = compute_coverage_delta(ci_result)
        # Must be None, never 0.0 as placeholder
        assert result is None, f"Expected None for {ci_result}, got {result}"


def test_coverage_delta_zero_when_actually_zero():
    """Coverage delta CAN be 0.0 when that's the actual measured value."""
    from autopack.executor.coverage_metrics import compute_coverage_delta

    ci_result = {
        "status": "passed",
        "coverage": {
            "baseline": 85.5,
            "current": 85.5,
            "delta": 0.0,  # Actual zero delta
        },
    }

    result = compute_coverage_delta(ci_result)

    assert result == 0.0


def test_coverage_status_unknown_deterministic():
    """Coverage status is deterministically 'unknown' when data unavailable."""
    from autopack.executor.coverage_metrics import get_coverage_status

    # No coverage data
    status1 = get_coverage_status(None)
    status2 = get_coverage_status(None)
    status3 = get_coverage_status({})

    assert status1 == "unknown"
    assert status2 == "unknown"
    assert status3 == "unknown"


def test_coverage_status_available_when_data_present():
    """Coverage status is 'available' when real data is present."""
    from autopack.executor.coverage_metrics import get_coverage_status

    ci_result = {
        "coverage": {
            "baseline": 85.5,
            "current": 87.2,
            "delta": 1.7,
        }
    }

    status = get_coverage_status(ci_result)

    assert status == "available"


def test_coverage_delta_negative_allowed():
    """Coverage delta can be negative (regression)."""
    from autopack.executor.coverage_metrics import compute_coverage_delta

    ci_result = {
        "coverage": {
            "baseline": 90.0,
            "current": 88.5,
            "delta": -1.5,
        }
    }

    result = compute_coverage_delta(ci_result)

    assert result == pytest.approx(-1.5)


def test_coverage_info_model():
    """CoverageInfo model captures all coverage state."""
    from autopack.executor.coverage_metrics import compute_coverage_info

    # Unknown case
    info_unknown = compute_coverage_info(None)
    assert info_unknown.status == "unknown"
    assert info_unknown.delta is None
    assert info_unknown.baseline is None
    assert info_unknown.current is None

    # Known case
    ci_result = {
        "coverage": {
            "baseline": 85.5,
            "current": 87.2,
            "delta": 1.7,
        }
    }
    info_known = compute_coverage_info(ci_result)
    assert info_known.status == "available"
    assert info_known.delta == pytest.approx(1.7)
    assert info_known.baseline == pytest.approx(85.5)
    assert info_known.current == pytest.approx(87.2)
