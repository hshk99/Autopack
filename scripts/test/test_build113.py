"""Test BUILD-113 Iterative Autonomous Investigation

This script tests the complete flow:
1. IterativeInvestigator analyzes a simulated failure
2. GoalAwareDecisionMaker makes a decision
3. DecisionExecutor applies the fix (if CLEAR_FIX)

Simulates a real import error scenario.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from autopack.diagnostics.iterative_investigator import IterativeInvestigator
from autopack.diagnostics.goal_aware_decision import GoalAwareDecisionMaker
from autopack.diagnostics.decision_executor import DecisionExecutor
from autopack.diagnostics.diagnostics_models import PhaseSpec, DecisionType
from autopack.diagnostics.diagnostics_agent import DiagnosticsAgent


def test_autonomous_investigation():
    """Test autonomous investigation with a simulated import error."""

    print("=" * 80)
    print("BUILD-113 TEST: Iterative Autonomous Investigation")
    print("=" * 80)

    # Setup
    workspace = Path.cwd()
    run_id = "test-build113"

    # Initialize components
    print("\n[1/5] Initializing components...")

    diagnostics_agent = DiagnosticsAgent(
        run_id=run_id,
        workspace=workspace,
        memory_service=None,
        decision_logger=None,
        diagnostics_dir=workspace / ".autonomous_runs" / run_id / "diagnostics",
        max_probes=3,
        max_seconds=60,
    )

    decision_maker = GoalAwareDecisionMaker(
        low_risk_threshold=100,
        medium_risk_threshold=200,
        min_confidence_for_auto_fix=0.7,
    )

    decision_executor = DecisionExecutor(
        run_id=run_id,
        workspace=workspace,
        memory_service=None,
        decision_logger=None,
    )

    investigator = IterativeInvestigator(
        run_id=run_id,
        workspace=workspace,
        diagnostics_agent=diagnostics_agent,
        decision_maker=decision_maker,
        memory_service=None,
        max_rounds=5,
        max_probes_per_round=3,
    )

    print("✓ Components initialized")

    # Simulate failure context (import error)
    print("\n[2/5] Simulating failure scenario (ImportError)...")

    failure_context = {
        "failure_class": "import_error",
        "error_message": "ImportError: cannot import name 'TestModule' from 'autopack.test_package'",
        "stack_trace": """Traceback (most recent call last):
  File "test.py", line 1, in <module>
    from autopack.test_package import TestModule
ImportError: cannot import name 'TestModule' from 'autopack.test_package'
""",
        "attempt_index": 1,
    }

    print(f"✓ Failure: {failure_context['error_message']}")

    # Define phase spec (what we're trying to achieve)
    print("\n[3/5] Defining phase specification...")

    phase_spec = PhaseSpec(
        phase_id="test-import-fix",
        deliverables=[
            "src/autopack/test_package/__init__.py"
        ],
        acceptance_criteria=[
            "Import statement works",
            "No import errors",
        ],
        allowed_paths=[
            "src/autopack/test_package/",
        ],
        protected_paths=[
            "src/autopack/core/",
            "config/",
        ],
        complexity="simple",
        category="bugfix",
    )

    print(f"✓ Phase: {phase_spec.phase_id}")
    print(f"  Deliverables: {phase_spec.deliverables}")
    print(f"  Allowed paths: {phase_spec.allowed_paths}")

    # Run investigation
    print("\n[4/5] Running iterative investigation...")
    print("-" * 80)

    try:
        result = investigator.investigate_and_resolve(
            failure_context=failure_context,
            phase_spec=phase_spec
        )

        print("-" * 80)
        print(f"✓ Investigation completed in {result.rounds} rounds")
        print(f"  Total time: {result.total_time_seconds:.2f}s")
        print(f"  Probes executed: {len(result.probes_executed)}")

        # Analyze decision
        print("\n[5/5] Decision Analysis:")
        print("-" * 80)

        decision = result.decision
        print(f"Decision Type: {decision.type.value}")
        print(f"Fix Strategy: {decision.fix_strategy}")
        print(f"Risk Level: {decision.risk_level}")
        print(f"Confidence: {decision.confidence:.0%}")
        print(f"\nRationale:\n{decision.rationale}")

        if decision.alternatives_considered:
            print(f"\nAlternatives Considered:")
            for alt in decision.alternatives_considered:
                print(f"  - {alt}")

        # Execution test (if CLEAR_FIX)
        if decision.type == DecisionType.CLEAR_FIX:
            print("\n" + "=" * 80)
            print("CLEAR_FIX Decision - Testing Execution Flow")
            print("=" * 80)
            print("\nNOTE: Not actually executing (test mode)")
            print("In production, would:")
            print("  1. Create git save point")
            print("  2. Apply patch")
            print("  3. Validate deliverables")
            print("  4. Run acceptance tests")
            print("  5. Commit or rollback")

            if decision.patch:
                print(f"\nGenerated Patch Preview:")
                print("-" * 40)
                print(decision.patch[:500] if len(decision.patch) > 500 else decision.patch)
                if len(decision.patch) > 500:
                    print("... (truncated)")

        elif decision.type == DecisionType.RISKY:
            print("\n⚠️  RISKY Decision - Would require human approval")
            if decision.questions_for_human:
                print("\nQuestions for human:")
                for q in decision.questions_for_human:
                    print(f"  - {q}")

        elif decision.type == DecisionType.AMBIGUOUS:
            print("\n⚠️  AMBIGUOUS Decision - Would escalate to human")
            if decision.questions_for_human:
                print("\nQuestions for human:")
                for q in decision.questions_for_human:
                    print(f"  - {q}")

        elif decision.type == DecisionType.NEED_MORE_EVIDENCE:
            print("\n🔍 NEED_MORE_EVIDENCE - Would continue investigation")

        # Timeline
        print("\n" + "=" * 80)
        print("Investigation Timeline:")
        print("=" * 80)
        for i, event in enumerate(result.timeline, 1):
            print(f"{i}. {event}")

        print("\n" + "=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)

        return result

    except Exception as e:
        print(f"\n❌ ERROR during investigation: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    result = test_autonomous_investigation()

    if result:
        print("\n✓ BUILD-113 test completed successfully")
        sys.exit(0)
    else:
        print("\n❌ BUILD-113 test failed")
        sys.exit(1)
