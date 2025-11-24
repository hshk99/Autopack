"""Standalone test runner for learned rules (bypasses conftest issues)"""

import sys
import os

# Set UTF-8 encoding for console output
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Run a simple integration test
from src.autopack.learned_rules import (
    RunRuleHint,
    LearnedRule,
    record_run_rule_hint,
    load_run_rule_hints,
    get_relevant_hints_for_phase,
    promote_hints_to_rules,
    load_project_learned_rules,
    get_relevant_rules_for_phase,
    format_hints_for_prompt,
    format_rules_for_prompt,
    _detect_resolved_issues,
    _extract_pattern,
)
from datetime import datetime


def test_basic_functionality():
    """Test basic learned rules functionality"""
    print("\n=== Testing Learned Rules System ===\n")

    # Test 1: Create RunRuleHint
    print("Test 1: Create RunRuleHint")
    hint = RunRuleHint(
        run_id="test_run_001",
        phase_index=3,
        phase_id="P1.3",
        tier_id="T1",
        task_category="feature_scaffolding",
        scope_paths=["auth.py", "auth_test.py"],
        source_issue_keys=["missing_type_hints_auth_py"],
        hint_text="Resolved missing_type_hints_auth_py in auth.py - ensure all functions have type annotations",
        created_at=datetime.utcnow().isoformat()
    )
    assert hint.run_id == "test_run_001"
    print("✅ RunRuleHint created successfully")

    # Test 2: Create LearnedRule
    print("\nTest 2: Create LearnedRule")
    rule = LearnedRule(
        rule_id="feature_scaffolding.missing_type_hints",
        task_category="feature_scaffolding",
        scope_pattern="*.py",
        constraint="Ensure all functions have type annotations",
        source_hint_ids=["run1:P1.1"],
        promotion_count=2,
        first_seen=datetime.utcnow().isoformat(),
        last_seen=datetime.utcnow().isoformat(),
        status="active"
    )
    assert rule.rule_id == "feature_scaffolding.missing_type_hints"
    print("✅ LearnedRule created successfully")

    # Test 3: Detect resolved issues
    print("\nTest 3: Detect resolved issues")
    issues_before = [
        {"issue_key": "missing_type_hints_auth_py", "severity": "major"},
        {"issue_key": "missing_tests_auth_py", "severity": "minor"},
    ]
    issues_after = [
        {"issue_key": "missing_tests_auth_py", "severity": "minor"},
    ]
    resolved = _detect_resolved_issues(issues_before, issues_after)
    assert len(resolved) == 1
    assert resolved[0]["issue_key"] == "missing_type_hints_auth_py"
    print(f"✅ Detected {len(resolved)} resolved issue(s)")

    # Test 4: Extract pattern
    print("\nTest 4: Extract pattern from issue key")
    assert _extract_pattern("missing_type_hints_auth_py") == "missing_type_hints"
    assert _extract_pattern("placeholder_code_handler_py") == "placeholder_code_handler"  # Takes up to 3 parts
    assert _extract_pattern("import_error_utils_123") == "import_error_utils"  # Takes up to 3 parts
    print("✅ Pattern extraction working")

    # Test 5: Format hints for prompt
    print("\nTest 5: Format hints for prompt")
    hints = [hint]
    formatted = format_hints_for_prompt(hints)
    assert "Lessons from Earlier Phases" in formatted
    assert "type annotations" in formatted.lower()
    print("✅ Hint formatting working")
    print(f"\nFormatted output:\n{formatted}\n")

    # Test 6: Format rules for prompt
    print("Test 6: Format rules for prompt")
    rules = [rule]
    formatted = format_rules_for_prompt(rules)
    assert "Project Learned Rules" in formatted
    assert "type annotations" in formatted.lower()
    print("✅ Rule formatting working")
    print(f"\nFormatted output:\n{formatted}\n")

    # Test 7: Serialization
    print("Test 7: Serialization")
    hint_dict = hint.to_dict()
    restored_hint = RunRuleHint.from_dict(hint_dict)
    assert restored_hint.run_id == hint.run_id
    assert restored_hint.phase_index == hint.phase_index
    print("✅ Hint serialization working")

    rule_dict = rule.to_dict()
    restored_rule = LearnedRule.from_dict(rule_dict)
    assert restored_rule.rule_id == rule.rule_id
    assert restored_rule.promotion_count == rule.promotion_count
    print("✅ Rule serialization working")

    print("\n=== All Basic Tests Passed! ===\n")


def test_file_persistence():
    """Test file-based persistence"""
    print("\n=== Testing File Persistence ===\n")

    # Clean up any existing test files
    import shutil
    from pathlib import Path

    test_dir = Path(".autonomous_runs_test")
    if test_dir.exists():
        shutil.rmtree(test_dir)

    # Temporarily patch the paths
    import src.autopack.learned_rules as lr_module

    def mock_get_run_hints_file(run_id: str) -> Path:
        base_dir = test_dir / "runs" / run_id
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir / "run_rule_hints.json"

    def mock_get_project_rules_file(project_id: str) -> Path:
        base_dir = test_dir / project_id
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir / "project_learned_rules.json"

    original_get_run = lr_module._get_run_hints_file
    original_get_project = lr_module._get_project_rules_file

    lr_module._get_run_hints_file = mock_get_run_hints_file
    lr_module._get_project_rules_file = mock_get_project_rules_file

    try:
        # Test 1: Record and load hints
        print("Test 1: Record and load run hints")
        run_id = "test_run_persistence_001"
        phase = {
            "phase_id": "P1.1",
            "phase_index": 0,
            "tier_id": "T1",
            "task_category": "feature_scaffolding"
        }
        issues_before = [{"issue_key": "missing_type_hints_auth_py", "severity": "major"}]
        issues_after = []
        context = {"file_paths": ["auth.py"]}

        hint = record_run_rule_hint(run_id, phase, issues_before, issues_after, context)
        assert hint is not None
        print(f"✅ Recorded hint: {hint.hint_text[:50]}...")

        # Load hints
        hints = load_run_rule_hints(run_id)
        assert len(hints) == 1
        assert hints[0].run_id == run_id
        print(f"✅ Loaded {len(hints)} hint(s) from file")

        # Test 2: Multiple hints
        print("\nTest 2: Record multiple hints")
        phase2 = {
            "phase_id": "P1.2",
            "phase_index": 1,
            "tier_id": "T1",
            "task_category": "feature_scaffolding"
        }
        issues_before2 = [{"issue_key": "missing_type_hints_models_py", "severity": "major"}]
        record_run_rule_hint(run_id, phase2, issues_before2, [], {"file_paths": ["models.py"]})

        hints = load_run_rule_hints(run_id)
        assert len(hints) == 2
        print(f"✅ Now have {len(hints)} hints in total")

        # Test 3: Get relevant hints
        print("\nTest 3: Get relevant hints for phase")
        target_phase = {
            "phase_id": "P1.5",
            "phase_index": 5,
            "task_category": "feature_scaffolding"
        }
        relevant = get_relevant_hints_for_phase(run_id, target_phase)
        assert len(relevant) == 2  # Both earlier phases match category
        print(f"✅ Found {len(relevant)} relevant hint(s)")

        # Test 4: Promote hints to rules
        print("\nTest 4: Promote hints to persistent rules")
        project_id = "test_project_persistence"
        promoted_count = promote_hints_to_rules(run_id, project_id)
        print(f"✅ Promoted {promoted_count} rule(s)")

        # Test 5: Load project rules
        print("\nTest 5: Load project rules")
        rules = load_project_learned_rules(project_id)
        print(f"✅ Loaded {len(rules)} rule(s)")
        if rules:
            print(f"   Rule ID: {rules[0].rule_id}")
            print(f"   Constraint: {rules[0].constraint}")

        # Test 6: Get relevant rules for phase
        print("\nTest 6: Get relevant rules for phase")
        if rules:
            relevant_rules = get_relevant_rules_for_phase(rules, target_phase)
            print(f"✅ Found {len(relevant_rules)} relevant rule(s)")

        print("\n=== File Persistence Tests Passed! ===\n")

    finally:
        # Restore original functions
        lr_module._get_run_hints_file = original_get_run
        lr_module._get_project_rules_file = original_get_project

        # Clean up
        if test_dir.exists():
            shutil.rmtree(test_dir)


if __name__ == "__main__":
    try:
        test_basic_functionality()
        test_file_persistence()
        print("\n🎉 All tests passed successfully! 🎉\n")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
