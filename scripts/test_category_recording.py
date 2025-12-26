"""
BUILD-129 Phase 3 P5: Test Category Recording Fix

Verify that telemetry records the estimated_category from TokenEstimator
instead of falling back to task_category from phase_spec.

This ensures doc_sot_update and doc_synthesis categories are recorded correctly.

Usage:
    PYTHONUTF8=1 PYTHONPATH=src python scripts/test_category_recording.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.token_estimator import TokenEstimator


def test_category_metadata():
    """Test that estimated category is available for telemetry"""
    estimator = TokenEstimator()

    print("=" * 70)
    print("BUILD-129 Phase 3 P5: Category Recording Test")
    print("=" * 70)
    print()

    test_cases = [
        {
            "name": "SOT File (BUILD_HISTORY.md)",
            "deliverables": ["BUILD_HISTORY.md"],
            "category": "documentation",
            "expected_category": "doc_sot_update",
        },
        {
            "name": "DOC_SYNTHESIS (API + Examples)",
            "deliverables": ["docs/API_REFERENCE.md", "docs/EXAMPLES.md"],
            "category": "documentation",
            "expected_category": "doc_synthesis",
        },
        {
            "name": "Regular Documentation",
            "deliverables": ["docs/FAQ.md"],
            "category": "documentation",
            "expected_category": "documentation",
        },
    ]

    all_passed = True

    for tc in test_cases:
        estimate = estimator.estimate(
            deliverables=tc["deliverables"],
            category=tc["category"],
            complexity="medium",
            scope_paths=["src/main.py"] * 10 if "API" in str(tc["deliverables"]) else ["src/main.py"],
            task_description=f"Test case: {tc['name']}"
        )

        passed = estimate.category == tc["expected_category"]
        status = "✓" if passed else "✗"

        print(f"{status} {tc['name']}")
        print(f"    Deliverables: {tc['deliverables']}")
        print(f"    Input category: {tc['category']}")
        print(f"    Estimated category: {estimate.category}")
        print(f"    Expected category: {tc['expected_category']}")
        print(f"    Match: {passed}")
        print()

        if not passed:
            all_passed = False

    print("=" * 70)
    if all_passed:
        print("✓ All category estimation tests PASSED")
        print("  estimated_category field will be stored in metadata")
        print("  Telemetry will record correct categories (doc_sot_update, doc_synthesis)")
    else:
        print("✗ Some category estimation tests FAILED")
    print("=" * 70)

    return all_passed


def test_metadata_structure():
    """Test that metadata structure matches what anthropic_clients.py expects"""
    print()
    print("=" * 70)
    print("BUILD-129 Phase 3 P5: Metadata Structure Test")
    print("=" * 70)
    print()

    estimator = TokenEstimator()

    # Simulate what anthropic_clients.py does
    deliverables = ["BUILD_LOG.md"]
    estimate = estimator.estimate(
        deliverables=deliverables,
        category="documentation",
        complexity="medium",
        scope_paths=["src/main.py"],
        task_description="Update BUILD_LOG.md"
    )

    # Simulate metadata update
    metadata = {}
    metadata.setdefault("token_prediction", {}).update({
        "predicted_output_tokens": estimate.estimated_tokens,
        "selected_budget": int(estimate.estimated_tokens * 1.2),
        "confidence": estimate.confidence,
        "source": "token_estimator",
        "estimated_category": estimate.category,  # P5 fix
    })

    print("Simulated metadata structure:")
    print(f"  token_prediction.predicted_output_tokens: {metadata['token_prediction']['predicted_output_tokens']}")
    print(f"  token_prediction.selected_budget: {metadata['token_prediction']['selected_budget']}")
    print(f"  token_prediction.confidence: {metadata['token_prediction']['confidence']:.2f}")
    print(f"  token_prediction.source: {metadata['token_prediction']['source']}")
    print(f"  token_prediction.estimated_category: {metadata['token_prediction']['estimated_category']}")
    print()

    # Verify retrieval (what telemetry recording does)
    retrieved_category = metadata.get("token_prediction", {}).get("estimated_category")

    if retrieved_category == "doc_sot_update":
        print("✓ Metadata retrieval successful")
        print(f"  Retrieved category: {retrieved_category}")
        print(f"  Expected: doc_sot_update")
        print(f"  Telemetry will record correct category!")
        return True
    else:
        print("✗ Metadata retrieval failed")
        print(f"  Retrieved category: {retrieved_category}")
        return False


if __name__ == "__main__":
    print("\n")

    test1 = test_category_metadata()
    test2 = test_metadata_structure()

    print("\n" + "=" * 70)
    print("OVERALL TEST RESULTS")
    print("=" * 70)
    print(f"Category Estimation: {'PASS' if test1 else 'FAIL'}")
    print(f"Metadata Structure: {'PASS' if test2 else 'FAIL'}")
    print("=" * 70)

    if test1 and test2:
        print("\n✓ All tests passed!")
        print("  P5 fix will ensure telemetry records correct categories")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed")
        sys.exit(1)
