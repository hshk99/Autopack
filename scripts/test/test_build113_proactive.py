"""Test BUILD-113 Proactive Decision Mode

Tests the make_proactive_decision() method with sample patches
to validate decision logic before integrating into autonomous_executor.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from autopack.diagnostics.goal_aware_decision import GoalAwareDecisionMaker
from autopack.diagnostics.diagnostics_models import PhaseSpec, DecisionType


def test_clear_fix_decision():
    """Test LOW risk patch (<100 lines, meets deliverables) → CLEAR_FIX"""
    print("\n" + "=" * 80)
    print("TEST 1: CLEAR_FIX Decision (LOW risk, high confidence)")
    print("=" * 80)

    decision_maker = GoalAwareDecisionMaker(
        low_risk_threshold=100,
        medium_risk_threshold=200,
        min_confidence_for_auto_fix=0.7,
    )

    # Simulate small patch (gold_set.json - 50 lines)
    patch_content = """diff --git a/src/autopack/research/evaluation/gold_set.json b/src/autopack/research/evaluation/gold_set.json
index 1234567..abcdefg 100644
--- a/src/autopack/research/evaluation/gold_set.json
+++ b/src/autopack/research/evaluation/gold_set.json
@@ -1 +1,50 @@
-{}
+{
+  "test_cases": [
+    {
+      "query": "How to implement OAuth2 in Python?",
+      "expected_findings": ["Use authlib library", "Configure redirect URIs"],
+      "expected_recommendations": ["Use refresh tokens", "Store tokens securely"]
+    }
+  ]
+}
"""

    phase_spec = PhaseSpec(
        phase_id="research-gold-set-data",
        deliverables=["src/autopack/research/evaluation/gold_set.json"],
        acceptance_criteria=["JSON file is valid", "Contains test cases"],
        allowed_paths=["src/autopack/research/"],
        protected_paths=["src/autopack/core/", "src/autopack/database.py"],
        complexity="simple",
        category="data",
    )

    decision = decision_maker.make_proactive_decision(patch_content, phase_spec)

    print(f"\n[RESULT] Decision Type: {decision.type.value}")
    print(f"[RESULT] Risk Level: {decision.risk_level}")
    print(f"[RESULT] Confidence: {decision.confidence:.0%}")
    print(f"[RESULT] Deliverables Met: {decision.deliverables_met}")
    print(f"[RESULT] Rationale: {decision.rationale}")

    assert decision.type == DecisionType.CLEAR_FIX, f"Expected CLEAR_FIX, got {decision.type.value}"
    assert decision.risk_level == "LOW", f"Expected LOW risk, got {decision.risk_level}"
    assert decision.confidence >= 0.7, f"Expected confidence ≥0.7, got {decision.confidence}"

    print("\n✓ TEST 1 PASSED: CLEAR_FIX decision for low-risk patch")


def test_risky_decision():
    """Test HIGH risk patch (>200 lines, integration) → RISKY"""
    print("\n" + "=" * 80)
    print("TEST 2: RISKY Decision (HIGH risk, requires approval)")
    print("=" * 80)

    decision_maker = GoalAwareDecisionMaker(
        low_risk_threshold=100,
        medium_risk_threshold=200,
        min_confidence_for_auto_fix=0.7,
    )

    # Simulate large patch (build_history_integrator.py - 250 lines)
    patch_content = """diff --git a/src/autopack/integrations/build_history_integrator.py b/src/autopack/integrations/build_history_integrator.py
index 1234567..abcdefg 100644
--- a/src/autopack/integrations/build_history_integrator.py
+++ b/src/autopack/integrations/build_history_integrator.py
@@ -1 +1,250 @@
-# Stub
+\"\"\"BUILD_HISTORY Integration for Research System\"\"\"
+
+import logging
+from typing import Dict, List, Optional
+""" + "\n".join(
        [f"+# Line {i}" for i in range(4, 250)]
    )

    phase_spec = PhaseSpec(
        phase_id="research-build-history-integrator",
        deliverables=["src/autopack/integrations/build_history_integrator.py"],
        acceptance_criteria=["Integrates with BUILD_HISTORY", "Handles errors gracefully"],
        allowed_paths=["src/autopack/integrations/", "src/autopack/research/"],
        protected_paths=["src/autopack/core/", "src/autopack/database.py"],
        complexity="high",
        category="integration",
    )

    decision = decision_maker.make_proactive_decision(patch_content, phase_spec)

    print(f"\n[RESULT] Decision Type: {decision.type.value}")
    print(f"[RESULT] Risk Level: {decision.risk_level}")
    print(f"[RESULT] Confidence: {decision.confidence:.0%}")
    print(f"[RESULT] Deliverables Met: {decision.deliverables_met}")
    print(f"[RESULT] Rationale: {decision.rationale}")
    print(f"[RESULT] Questions for Human: {decision.questions_for_human}")

    assert decision.type == DecisionType.RISKY, f"Expected RISKY, got {decision.type.value}"
    assert decision.risk_level == "HIGH", f"Expected HIGH risk, got {decision.risk_level}"

    print("\n✓ TEST 2 PASSED: RISKY decision for high-risk patch")


def test_database_risk_detection():
    """Test database file detection → HIGH risk → RISKY"""
    print("\n" + "=" * 80)
    print("TEST 3: Database Risk Detection (database-related file → RISKY)")
    print("=" * 80)

    decision_maker = GoalAwareDecisionMaker(
        low_risk_threshold=100,
        medium_risk_threshold=200,
        min_confidence_for_auto_fix=0.7,
    )

    # Simulate medium-sized database patch (research_phase.py - 150 lines)
    patch_content = """diff --git a/src/autopack/models.py b/src/autopack/models.py
index 1234567..abcdefg 100644
--- a/src/autopack/models.py
+++ b/src/autopack/models.py
@@ -1 +1,150 @@
-# Existing models
+# Existing models
+
+class ResearchSession(Base):
+    \"\"\"Research session model\"\"\"
+    __tablename__ = "research_sessions"
+    id = Column(Integer, primary_key=True)
+""" + "\n".join([f"+    # Field {i}" for i in range(6, 150)])

    phase_spec = PhaseSpec(
        phase_id="research-phase-type",
        deliverables=["src/autopack/models.py"],
        acceptance_criteria=["Research session model added"],
        allowed_paths=["src/autopack/"],
        protected_paths=["src/autopack/core/"],
        complexity="high",
        category="feature",
    )

    decision = decision_maker.make_proactive_decision(patch_content, phase_spec)

    print(f"\n[RESULT] Decision Type: {decision.type.value}")
    print(f"[RESULT] Risk Level: {decision.risk_level}")
    print(f"[RESULT] Confidence: {decision.confidence:.0%}")
    print(f"[RESULT] Rationale: {decision.rationale}")

    assert decision.type == DecisionType.RISKY, f"Expected RISKY, got {decision.type.value}"
    assert (
        decision.risk_level == "HIGH"
    ), f"Expected HIGH risk (database file), got {decision.risk_level}"

    print("\n✓ TEST 3 PASSED: Database file correctly detected as HIGH risk")


def test_threshold_boundary():
    """Test MEDIUM risk threshold (100-200 lines) → MEDIUM risk"""
    print("\n" + "=" * 80)
    print("TEST 4: Threshold Boundary (100-200 lines → MEDIUM → CLEAR_FIX or RISKY)")
    print("=" * 80)

    decision_maker = GoalAwareDecisionMaker(
        low_risk_threshold=100,
        medium_risk_threshold=200,
        min_confidence_for_auto_fix=0.7,
    )

    # Simulate 150-line patch (research_hooks.py)
    patch_content = """diff --git a/src/autopack/autonomous/research_hooks.py b/src/autopack/autonomous/research_hooks.py
index 1234567..abcdefg 100644
--- a/src/autopack/autonomous/research_hooks.py
+++ b/src/autopack/autonomous/research_hooks.py
@@ -1 +1,150 @@
-# Stub
+\"\"\"Research hooks for autonomous mode\"\"\"
+
+import logging
+""" + "\n".join(
        [f"+# Line {i}" for i in range(4, 150)]
    )

    phase_spec = PhaseSpec(
        phase_id="research-autonomous-hooks",
        deliverables=["src/autopack/autonomous/research_hooks.py"],
        acceptance_criteria=["Hooks integrate with autonomous mode"],
        allowed_paths=["src/autopack/autonomous/", "src/autopack/research/"],
        protected_paths=["src/autopack/core/"],
        complexity="medium",
        category="integration",
    )

    decision = decision_maker.make_proactive_decision(patch_content, phase_spec)

    print(f"\n[RESULT] Decision Type: {decision.type.value}")
    print(f"[RESULT] Risk Level: {decision.risk_level}")
    print(f"[RESULT] Confidence: {decision.confidence:.0%}")
    print(f"[RESULT] Rationale: {decision.rationale}")

    # At 150 lines: MEDIUM risk, but should still be CLEAR_FIX if high confidence + meets deliverables
    assert decision.risk_level == "MEDIUM", f"Expected MEDIUM risk, got {decision.risk_level}"

    print(
        f"\n  Decision: {decision.type.value} (MEDIUM risk can be CLEAR_FIX with high confidence)"
    )
    print("\n✓ TEST 4 PASSED: Threshold boundary correctly assessed as MEDIUM risk")


if __name__ == "__main__":
    try:
        test_clear_fix_decision()
        test_risky_decision()
        test_database_risk_detection()
        test_threshold_boundary()

        print("\n" + "=" * 80)
        print("ALL TESTS PASSED ✓")
        print("=" * 80)
        print("\nBUILD-113 Proactive Mode is working correctly!")
        print("Ready to integrate into autonomous_executor.py")
        print()

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
