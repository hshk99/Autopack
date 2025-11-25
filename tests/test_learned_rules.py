"""Unit tests for learned rules system (Stage 0A + 0B)

Tests cover:
- RunRuleHint creation and persistence
- LearnedRule creation and persistence
- Hint recording when issues resolved
- Rule promotion from hints
- Relevance filtering for phase
- Prompt formatting
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

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
    _extract_scope_paths,
    _generate_hint_text,
    _group_hints_by_pattern,
    _extract_pattern,
    _generate_rule_id,
)


@pytest.fixture
def temp_runs_dir(monkeypatch):
    """Create temporary .autonomous_runs directory for tests"""
    temp_dir = tempfile.mkdtemp()
    runs_dir = Path(temp_dir) / ".autonomous_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    # Monkeypatch the base directory in learned_rules module
    import src.autopack.learned_rules as lr_module
    original_base = Path(".autonomous_runs")

    def mock_get_run_hints_file(run_id: str) -> Path:
        base_dir = runs_dir / "runs" / run_id
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir / "run_rule_hints.json"

    def mock_get_project_rules_file(project_id: str) -> Path:
        base_dir = runs_dir / project_id
        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir / "project_learned_rules.json"

    monkeypatch.setattr(lr_module, "_get_run_hints_file", mock_get_run_hints_file)
    monkeypatch.setattr(lr_module, "_get_project_rules_file", mock_get_project_rules_file)

    yield runs_dir

    # Cleanup
    shutil.rmtree(temp_dir)


class TestRunRuleHint:
    """Tests for RunRuleHint (Stage 0A)"""

    def test_create_hint(self):
        """Test creating a RunRuleHint"""
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
        assert hint.phase_index == 3
        assert hint.task_category == "feature_scaffolding"
        assert len(hint.scope_paths) == 2

    def test_hint_serialization(self):
        """Test hint to_dict and from_dict"""
        hint = RunRuleHint(
            run_id="test_run_001",
            phase_index=3,
            phase_id="P1.3",
            tier_id="T1",
            task_category="feature_scaffolding",
            scope_paths=["auth.py"],
            source_issue_keys=["missing_type_hints"],
            hint_text="Test hint",
            created_at=datetime.utcnow().isoformat()
        )

        hint_dict = hint.to_dict()
        assert isinstance(hint_dict, dict)
        assert hint_dict["run_id"] == "test_run_001"

        restored_hint = RunRuleHint.from_dict(hint_dict)
        assert restored_hint.run_id == hint.run_id
        assert restored_hint.phase_index == hint.phase_index


class TestLearnedRule:
    """Tests for LearnedRule (Stage 0B)"""

    def test_create_rule(self):
        """Test creating a LearnedRule"""
        rule = LearnedRule(
            rule_id="feature_scaffolding.missing_type_hints",
            task_category="feature_scaffolding",
            scope_pattern="*.py",
            constraint="Ensure all functions have type annotations",
            source_hint_ids=["run1:P1.3", "run2:P2.1"],
            promotion_count=2,
            first_seen=datetime.utcnow().isoformat(),
            last_seen=datetime.utcnow().isoformat(),
            status="active"
        )

        assert rule.rule_id == "feature_scaffolding.missing_type_hints"
        assert rule.task_category == "feature_scaffolding"
        assert rule.promotion_count == 2
        assert rule.status == "active"

    def test_rule_serialization(self):
        """Test rule to_dict and from_dict"""
        rule = LearnedRule(
            rule_id="test.rule",
            task_category="test_category",
            scope_pattern=None,
            constraint="Test constraint",
            source_hint_ids=["run1:P1"],
            promotion_count=1,
            first_seen=datetime.utcnow().isoformat(),
            last_seen=datetime.utcnow().isoformat(),
            status="active"
        )

        rule_dict = rule.to_dict()
        assert isinstance(rule_dict, dict)
        assert rule_dict["rule_id"] == "test.rule"

        restored_rule = LearnedRule.from_dict(rule_dict)
        assert restored_rule.rule_id == rule.rule_id
        assert restored_rule.promotion_count == rule.promotion_count


class TestHintRecording:
    """Tests for recording hints when issues resolved"""

    def test_detect_resolved_issues(self):
        """Test detecting which issues were resolved"""
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

    def test_detect_no_resolved_issues(self):
        """Test when no issues resolved"""
        issues_before = [
            {"issue_key": "missing_type_hints", "severity": "major"},
        ]
        issues_after = [
            {"issue_key": "missing_type_hints", "severity": "major"},
        ]

        resolved = _detect_resolved_issues(issues_before, issues_after)
        assert len(resolved) == 0

    def test_extract_scope_paths_from_context(self):
        """Test extracting scope paths from context"""
        phase = {"phase_id": "P1.1"}
        context = {"file_paths": ["auth.py", "auth_test.py", "models.py"]}

        paths = _extract_scope_paths(phase, context)
        assert len(paths) <= 5  # Max 5 paths
        assert "auth.py" in paths

    def test_generate_hint_text_type_hints(self):
        """Test hint text generation for type hints pattern"""
        resolved = [
            {"issue_key": "missing_type_hints_auth_py", "severity": "major"}
        ]
        scope_paths = ["auth.py"]
        phase = {"phase_id": "P1.1"}

        hint_text = _generate_hint_text(resolved, scope_paths, phase)
        assert "type annotations" in hint_text.lower() or "type hints" in hint_text.lower()
        assert "auth.py" in hint_text

    def test_generate_hint_text_placeholder(self):
        """Test hint text generation for placeholder pattern"""
        resolved = [
            {"issue_key": "placeholder_code_handler_py", "severity": "major"}
        ]
        scope_paths = ["handler.py"]
        phase = {"phase_id": "P1.2"}

        hint_text = _generate_hint_text(resolved, scope_paths, phase)
        assert "placeholder" in hint_text.lower()

    def test_record_hint_with_resolved_issues(self, temp_runs_dir):
        """Test recording hint when issues were resolved"""
        run_id = "test_run_001"
        phase = {
            "phase_id": "P1.3",
            "phase_index": 2,
            "tier_id": "T1",
            "task_category": "feature_scaffolding"
        }
        issues_before = [
            {"issue_key": "missing_type_hints_auth_py", "severity": "major"}
        ]
        issues_after = []
        context = {"file_paths": ["auth.py"]}

        hint = record_run_rule_hint(run_id, phase, issues_before, issues_after, context)

        assert hint is not None
        assert hint.run_id == run_id
        assert hint.phase_id == "P1.3"
        assert len(hint.source_issue_keys) == 1

    def test_record_hint_no_resolved_issues(self, temp_runs_dir):
        """Test no hint recorded when no issues resolved"""
        run_id = "test_run_002"
        phase = {"phase_id": "P1.1", "phase_index": 0}
        issues_before = []
        issues_after = []

        hint = record_run_rule_hint(run_id, phase, issues_before, issues_after, None)

        assert hint is None


class TestHintPersistence:
    """Tests for hint loading and persistence"""

    def test_load_empty_hints(self, temp_runs_dir):
        """Test loading hints from non-existent file"""
        hints = load_run_rule_hints("nonexistent_run")
        assert hints == []

    def test_save_and_load_hints(self, temp_runs_dir):
        """Test saving and loading hints"""
        run_id = "test_run_003"
        phase = {
            "phase_id": "P1.1",
            "phase_index": 0,
            "tier_id": "T1",
            "task_category": "feature_scaffolding"
        }
        issues_before = [{"issue_key": "test_issue", "severity": "major"}]
        issues_after = []
        context = {"file_paths": ["test.py"]}

        # Record hint
        hint1 = record_run_rule_hint(run_id, phase, issues_before, issues_after, context)
        assert hint1 is not None

        # Load hints
        hints = load_run_rule_hints(run_id)
        assert len(hints) == 1
        assert hints[0].run_id == run_id

    def test_get_relevant_hints_for_phase(self, temp_runs_dir):
        """Test filtering hints by relevance to phase"""
        run_id = "test_run_004"

        # Create hints from earlier phases
        for i in range(3):
            phase = {
                "phase_id": f"P1.{i}",
                "phase_index": i,
                "task_category": "feature_scaffolding"
            }
            issues_before = [{"issue_key": f"issue_{i}", "severity": "major"}]
            issues_after = []
            context = {"file_paths": [f"file_{i}.py"]}
            record_run_rule_hint(run_id, phase, issues_before, issues_after, context)

        # Get hints for later phase
        target_phase = {
            "phase_id": "P1.5",
            "phase_index": 5,
            "task_category": "feature_scaffolding"
        }

        relevant = get_relevant_hints_for_phase(run_id, target_phase, max_hints=5)
        assert len(relevant) == 3  # All earlier phases match category

    def test_get_hints_filters_by_phase_index(self, temp_runs_dir):
        """Test hints only from earlier phases"""
        run_id = "test_run_005"

        # Create hint from phase 5
        phase = {
            "phase_id": "P1.5",
            "phase_index": 5,
            "task_category": "feature_scaffolding"
        }
        issues_before = [{"issue_key": "issue_5", "severity": "major"}]
        issues_after = []
        context = {"file_paths": ["file_5.py"]}
        record_run_rule_hint(run_id, phase, issues_before, issues_after, context)

        # Try to get hints for earlier phase 3
        target_phase = {
            "phase_id": "P1.3",
            "phase_index": 3,
            "task_category": "feature_scaffolding"
        }

        relevant = get_relevant_hints_for_phase(run_id, target_phase)
        assert len(relevant) == 0  # No hints from future phases


class TestRulePromotion:
    """Tests for promoting hints to persistent rules"""

    def test_extract_pattern_from_issue_key(self):
        """Test extracting base pattern from issue key"""
        assert _extract_pattern("missing_type_hints_auth_py") == "missing_type_hints"
        assert _extract_pattern("placeholder_code_handler_py") == "placeholder_code"
        assert _extract_pattern("import_error_utils_123") == "import_error"

    def test_group_hints_by_pattern(self):
        """Test grouping hints by pattern for promotion"""
        hints = [
            RunRuleHint(
                run_id="run1",
                phase_index=1,
                phase_id="P1.1",
                tier_id="T1",
                task_category="feature_scaffolding",
                scope_paths=["auth.py"],
                source_issue_keys=["missing_type_hints_auth_py"],
                hint_text="Type hints in auth.py",
                created_at=datetime.utcnow().isoformat()
            ),
            RunRuleHint(
                run_id="run1",
                phase_index=3,
                phase_id="P1.3",
                tier_id="T1",
                task_category="feature_scaffolding",
                scope_paths=["models.py"],
                source_issue_keys=["missing_type_hints_models_py"],
                hint_text="Type hints in models.py",
                created_at=datetime.utcnow().isoformat()
            ),
        ]

        patterns = _group_hints_by_pattern(hints)
        assert "missing_type_hints:feature_scaffolding" in patterns
        assert len(patterns["missing_type_hints:feature_scaffolding"]) == 2

    def test_generate_rule_id(self):
        """Test generating rule ID from hint"""
        hint = RunRuleHint(
            run_id="run1",
            phase_index=1,
            phase_id="P1.1",
            tier_id="T1",
            task_category="feature_scaffolding",
            scope_paths=["auth.py"],
            source_issue_keys=["missing_type_hints_auth_py"],
            hint_text="Test",
            created_at=datetime.utcnow().isoformat()
        )

        rule_id = _generate_rule_id(hint)
        assert rule_id == "feature_scaffolding.missing_type_hints"

    def test_promote_hints_to_rules(self, temp_runs_dir):
        """Test promoting recurring hints to persistent rules"""
        run_id = "test_run_006"
        project_id = "test_project"

        # Create 2 hints with same pattern
        for i in range(2):
            phase = {
                "phase_id": f"P1.{i}",
                "phase_index": i,
                "task_category": "feature_scaffolding"
            }
            issues_before = [{"issue_key": "missing_type_hints_file_py", "severity": "major"}]
            issues_after = []
            context = {"file_paths": [f"file_{i}.py"]}
            record_run_rule_hint(run_id, phase, issues_before, issues_after, context)

        # Promote hints to rules
        promoted_count = promote_hints_to_rules(run_id, project_id)

        assert promoted_count == 1  # One rule promoted

        # Load project rules
        rules = load_project_learned_rules(project_id)
        assert len(rules) == 1
        assert rules[0].rule_id == "feature_scaffolding.missing_type_hints"
        assert rules[0].status == "active"

    def test_promote_no_recurring_patterns(self, temp_runs_dir):
        """Test no promotion when no recurring patterns"""
        run_id = "test_run_007"
        project_id = "test_project_2"

        # Create 2 hints with different patterns
        phase1 = {
            "phase_id": "P1.0",
            "phase_index": 0,
            "task_category": "feature_scaffolding"
        }
        record_run_rule_hint(
            run_id, phase1,
            [{"issue_key": "missing_type_hints", "severity": "major"}],
            [],
            {"file_paths": ["file1.py"]}
        )

        phase2 = {
            "phase_id": "P1.1",
            "phase_index": 1,
            "task_category": "feature_scaffolding"
        }
        record_run_rule_hint(
            run_id, phase2,
            [{"issue_key": "missing_tests", "severity": "major"}],
            [],
            {"file_paths": ["file2.py"]}
        )

        # Promote (should promote nothing - need 2+ of same pattern)
        promoted_count = promote_hints_to_rules(run_id, project_id)

        assert promoted_count == 0


class TestRulePersistence:
    """Tests for rule loading and persistence"""

    def test_load_empty_rules(self, temp_runs_dir):
        """Test loading rules from non-existent project"""
        rules = load_project_learned_rules("nonexistent_project")
        assert rules == []

    def test_get_relevant_rules_for_phase(self, temp_runs_dir):
        """Test filtering rules by relevance to phase"""
        run_id = "test_run_008"
        project_id = "test_project_3"

        # Create hints and promote
        for i in range(3):
            phase = {
                "phase_id": f"P1.{i}",
                "phase_index": i,
                "task_category": "feature_scaffolding"
            }
            record_run_rule_hint(
                run_id, phase,
                [{"issue_key": "missing_type_hints", "severity": "major"}],
                [],
                {"file_paths": ["file.py"]}
            )

        promote_hints_to_rules(run_id, project_id)

        # Load rules
        all_rules = load_project_learned_rules(project_id)

        # Get relevant for matching category
        matching_phase = {
            "phase_id": "P2.1",
            "task_category": "feature_scaffolding"
        }
        relevant = get_relevant_rules_for_phase(all_rules, matching_phase)
        assert len(relevant) >= 1

        # Get relevant for non-matching category
        non_matching_phase = {
            "phase_id": "P2.2",
            "task_category": "different_category"
        }
        relevant = get_relevant_rules_for_phase(all_rules, non_matching_phase)
        assert len(relevant) == 0


class TestPromptFormatting:
    """Tests for formatting rules/hints for LLM prompts"""

    def test_format_hints_for_prompt(self):
        """Test formatting hints for prompt injection"""
        hints = [
            RunRuleHint(
                run_id="run1",
                phase_index=1,
                phase_id="P1.1",
                tier_id="T1",
                task_category="feature_scaffolding",
                scope_paths=["auth.py"],
                source_issue_keys=["missing_type_hints"],
                hint_text="Ensure type annotations in auth.py",
                created_at=datetime.utcnow().isoformat()
            ),
            RunRuleHint(
                run_id="run1",
                phase_index=2,
                phase_id="P1.2",
                tier_id="T1",
                task_category="feature_scaffolding",
                scope_paths=["models.py"],
                source_issue_keys=["placeholder_code"],
                hint_text="Remove placeholder code in models.py",
                created_at=datetime.utcnow().isoformat()
            ),
        ]

        formatted = format_hints_for_prompt(hints)
        assert "Lessons from Earlier Phases" in formatted
        assert "Ensure type annotations" in formatted
        assert "Remove placeholder code" in formatted

    def test_format_empty_hints(self):
        """Test formatting empty hints list"""
        formatted = format_hints_for_prompt([])
        assert formatted == ""

    def test_format_rules_for_prompt(self):
        """Test formatting rules for prompt injection"""
        rules = [
            LearnedRule(
                rule_id="feature_scaffolding.missing_type_hints",
                task_category="feature_scaffolding",
                scope_pattern="*.py",
                constraint="Ensure all functions have type annotations",
                source_hint_ids=["run1:P1.1"],
                promotion_count=2,
                first_seen=datetime.utcnow().isoformat(),
                last_seen=datetime.utcnow().isoformat(),
                status="active"
            ),
            LearnedRule(
                rule_id="feature_scaffolding.placeholder_code",
                task_category="feature_scaffolding",
                scope_pattern=None,
                constraint="Never leave placeholder code like 'TODO' or 'INSERT CODE HERE'",
                source_hint_ids=["run1:P1.2"],
                promotion_count=3,
                first_seen=datetime.utcnow().isoformat(),
                last_seen=datetime.utcnow().isoformat(),
                status="active"
            ),
        ]

        formatted = format_rules_for_prompt(rules)
        assert "Project Learned Rules" in formatted
        assert "feature_scaffolding.missing_type_hints" in formatted
        assert "type annotations" in formatted
        assert "placeholder_code" in formatted

    def test_format_empty_rules(self):
        """Test formatting empty rules list"""
        formatted = format_rules_for_prompt([])
        assert formatted == ""
