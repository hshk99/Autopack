"""Test BUILD-113 Integration - Quick Validation

Validates that BUILD-113 proactive mode integration:
1. Compiles without syntax errors
2. Imports work correctly
3. Helper methods are accessible
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))


def test_imports():
    """Test that all BUILD-113 components import correctly"""
    print("\n" + "=" * 80)
    print("TEST 1: Verify BUILD-113 imports")
    print("=" * 80)

    try:
        from autopack.diagnostics.goal_aware_decision import GoalAwareDecisionMaker
        from autopack.diagnostics.decision_executor import DecisionExecutor
        from autopack.diagnostics.iterative_investigator import IterativeInvestigator
        from autopack.diagnostics.diagnostics_models import PhaseSpec, Decision, DecisionType

        print("✓ All BUILD-113 imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_proactive_decision_method():
    """Test that make_proactive_decision method exists and is callable"""
    print("\n" + "=" * 80)
    print("TEST 2: Verify make_proactive_decision method exists")
    print("=" * 80)

    try:
        from autopack.diagnostics.goal_aware_decision import GoalAwareDecisionMaker

        decision_maker = GoalAwareDecisionMaker(
            low_risk_threshold=100,
            medium_risk_threshold=200,
            min_confidence_for_auto_fix=0.7,
        )

        # Check method exists
        assert hasattr(
            decision_maker, "make_proactive_decision"
        ), "make_proactive_decision method not found"

        # Check method is callable
        assert callable(
            decision_maker.make_proactive_decision
        ), "make_proactive_decision is not callable"

        print("✓ make_proactive_decision method exists and is callable")
        return True
    except Exception as e:
        print(f"✗ Method check failed: {e}")
        return False


def test_autonomous_executor_integration():
    """Test that autonomous_executor imports and has BUILD-113 helper methods"""
    print("\n" + "=" * 80)
    print("TEST 3: Verify autonomous_executor BUILD-113 integration")
    print("=" * 80)

    try:
        from autopack.autonomous_executor import AutonomousExecutor

        # Check helper methods exist
        assert hasattr(
            AutonomousExecutor, "_request_build113_approval"
        ), "_request_build113_approval method not found"

        assert hasattr(
            AutonomousExecutor, "_request_build113_clarification"
        ), "_request_build113_clarification method not found"

        print("✓ autonomous_executor has BUILD-113 helper methods")
        return True
    except Exception as e:
        print(f"✗ autonomous_executor check failed: {e}")
        return False


def test_syntax_validation():
    """Test that the autonomous_executor module compiles without syntax errors"""
    print("\n" + "=" * 80)
    print("TEST 4: Verify autonomous_executor.py syntax")
    print("=" * 80)

    try:
        import py_compile

        executor_path = Path(__file__).parent / "src" / "autopack" / "autonomous_executor.py"
        py_compile.compile(str(executor_path), doraise=True)

        print("✓ autonomous_executor.py compiles without syntax errors")
        return True
    except SyntaxError as e:
        print(f"✗ Syntax error in autonomous_executor.py: {e}")
        return False
    except Exception as e:
        print(f"✗ Compilation check failed: {e}")
        return False


if __name__ == "__main__":
    results = []

    results.append(("Imports", test_imports()))
    results.append(("Proactive decision method", test_proactive_decision_method()))
    results.append(("Autonomous executor integration", test_autonomous_executor_integration()))
    results.append(("Syntax validation", test_syntax_validation()))

    print("\n" + "=" * 80)
    print("INTEGRATION TEST RESULTS")
    print("=" * 80)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(result[1] for result in results)

    print("\n" + "=" * 80)
    if all_passed:
        print("✓ ALL INTEGRATION TESTS PASSED")
        print("=" * 80)
        print("\nBUILD-113 proactive mode is successfully integrated!")
        print("Ready to test with research-build113-test run.")
        sys.exit(0)
    else:
        print("✗ SOME INTEGRATION TESTS FAILED")
        print("=" * 80)
        sys.exit(1)
