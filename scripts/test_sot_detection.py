"""
BUILD-129 Phase 3 P3: Test SOT File Detection

Quick test to verify SOT (Source of Truth) file detection and estimation.

Usage:
    PYTHONUTF8=1 PYTHONPATH=src python scripts/test_sot_detection.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.token_estimator import TokenEstimator


def test_sot_detection():
    """Test SOT file detection logic"""
    estimator = TokenEstimator()

    # Test cases: (deliverable, expected_is_sot)
    test_cases = [
        ("BUILD_LOG.md", True),
        ("docs/BUILD_LOG.md", True),
        ("build_log.md", True),
        ("BUILD_HISTORY.md", True),
        ("CHANGELOG.md", True),
        ("HISTORY.md", True),
        ("RELEASE_NOTES.md", True),
        ("docs/API_REFERENCE.md", False),
        ("README.md", False),
        ("docs/EXAMPLES.md", False),
        ("src/main.py", False),
    ]

    print("=" * 70)
    print("BUILD-129 Phase 3 P3: SOT File Detection Test")
    print("=" * 70)
    print()

    passed = 0
    failed = 0

    for deliverable, expected_is_sot in test_cases:
        is_sot = estimator._is_sot_file(deliverable)
        status = "✓" if is_sot == expected_is_sot else "✗"
        result = "SOT" if is_sot else "NOT SOT"

        if is_sot == expected_is_sot:
            passed += 1
        else:
            failed += 1

        print(f"{status} {deliverable:30} → {result:10} (expected: {'SOT' if expected_is_sot else 'NOT SOT'})")

    print()
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


def test_sot_estimation():
    """Test SOT file estimation"""
    estimator = TokenEstimator()

    print("\n" + "=" * 70)
    print("BUILD-129 Phase 3 P3: SOT Estimation Test")
    print("=" * 70)
    print()

    # Test SOT estimation
    deliverables = ["BUILD_LOG.md"]
    estimate = estimator.estimate(
        deliverables=deliverables,
        category="documentation",
        complexity="medium",
        scope_paths=["src/autopack/main.py"],  # Some context
        task_description="Update BUILD_LOG.md with phase results"
    )

    print(f"Deliverables: {deliverables}")
    print(f"Category: {estimate.category}")
    print(f"Estimated tokens: {estimate.estimated_tokens}")
    print(f"Deliverable count: {estimate.deliverable_count}")
    print(f"Confidence: {estimate.confidence:.2f}")
    print(f"Breakdown:")
    for key, value in estimate.breakdown.items():
        print(f"  - {key}: {value}")

    # Verify it was detected as SOT
    is_sot_category = estimate.category == "doc_sot_update"
    has_sot_breakdown = "sot_context_reconstruction" in estimate.breakdown

    print()
    if is_sot_category and has_sot_breakdown:
        print("✓ SOT file correctly detected and estimated")
        print("  - Category: doc_sot_update")
        print("  - SOT-specific breakdown present")
        return True
    else:
        print("✗ SOT file not properly detected")
        print(f"  - Category: {estimate.category} (expected: doc_sot_update)")
        print(f"  - Has SOT breakdown: {has_sot_breakdown}")
        return False


def test_non_sot_still_works():
    """Verify regular doc estimation still works"""
    estimator = TokenEstimator()

    print("\n" + "=" * 70)
    print("BUILD-129 Phase 3 P3: Non-SOT Doc Estimation Test")
    print("=" * 70)
    print()

    # Test regular doc estimation (should use doc_synthesis or regular model)
    deliverables = ["docs/API_REFERENCE.md", "docs/EXAMPLES.md"]
    estimate = estimator.estimate(
        deliverables=deliverables,
        category="documentation",
        complexity="medium",
        scope_paths=["src/autopack/main.py"],
        task_description="Create API reference and examples from scratch"
    )

    print(f"Deliverables: {deliverables}")
    print(f"Category: {estimate.category}")
    print(f"Estimated tokens: {estimate.estimated_tokens}")
    print(f"Deliverable count: {estimate.deliverable_count}")
    print(f"Confidence: {estimate.confidence:.2f}")

    # Verify it was NOT detected as SOT (should be doc_synthesis)
    is_sot = estimate.category == "doc_sot_update"
    is_doc_synthesis = estimate.category == "doc_synthesis"

    print()
    if not is_sot and is_doc_synthesis:
        print("✓ Non-SOT docs correctly use DOC_SYNTHESIS model")
        print(f"  - Category: {estimate.category}")
        return True
    else:
        print("✗ Non-SOT docs incorrectly categorized")
        print(f"  - Category: {estimate.category} (expected: doc_synthesis)")
        print(f"  - Is SOT: {is_sot} (should be False)")
        return False


if __name__ == "__main__":
    print("\n")

    # Run all tests
    test1 = test_sot_detection()
    test2 = test_sot_estimation()
    test3 = test_non_sot_still_works()

    print("\n" + "=" * 70)
    print("OVERALL TEST RESULTS")
    print("=" * 70)
    print(f"SOT Detection: {'PASS' if test1 else 'FAIL'}")
    print(f"SOT Estimation: {'PASS' if test2 else 'FAIL'}")
    print(f"Non-SOT Estimation: {'PASS' if test3 else 'FAIL'}")
    print("=" * 70)

    if test1 and test2 and test3:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)
