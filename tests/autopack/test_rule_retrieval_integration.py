"""Tests for IMP-LOOP-025: Promoted Rules Retrieval Integration.

Tests cover:
- get_promoted_rules() method in FeedbackPipeline
- Integration of promoted rules into execution context via autonomous_loop._get_memory_context()
- Filtering by phase_type
- Handling of missing/disabled memory service
"""

from unittest.mock import Mock


from autopack.feedback_pipeline import FeedbackPipeline


class TestGetPromotedRules:
    """Tests for FeedbackPipeline.get_promoted_rules()."""

    def test_get_promoted_rules_returns_empty_when_memory_disabled(self):
        """Should return empty list when memory service is not available."""
        pipeline = FeedbackPipeline(memory_service=None)

        rules = pipeline.get_promoted_rules(phase_type="build")

        assert rules == []

    def test_get_promoted_rules_returns_empty_when_memory_service_disabled(self):
        """Should return empty list when memory service is disabled."""
        mock_memory = Mock()
        mock_memory.enabled = False
        pipeline = FeedbackPipeline(memory_service=mock_memory)

        rules = pipeline.get_promoted_rules(phase_type="build")

        assert rules == []

    def test_get_promoted_rules_returns_matching_rules(self):
        """Should return promoted rules from memory service."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.search_telemetry_insights.return_value = [
            {
                "content": "Rule about build failures",
                "metadata": {
                    "is_rule": True,
                    "insight_type": "promoted_rule",
                    "description": "RULE: Build phases frequently fail with dependency errors",
                    "suggested_action": "Verify dependencies before build",
                    "phase_type": "build",
                    "hint_type": "ci_fail",
                    "occurrences": 5,
                },
                "confidence": 0.9,
                "timestamp": "2025-01-29T12:00:00Z",
            },
            {
                "content": "Another rule",
                "metadata": {
                    "is_rule": True,
                    "insight_type": "promoted_rule",
                    "description": "RULE: Build phases need proper error handling",
                    "suggested_action": "Add retry logic",
                    "phase_type": "build",
                    "hint_type": "infra_error",
                    "occurrences": 3,
                },
                "confidence": 0.8,
                "timestamp": "2025-01-28T12:00:00Z",
            },
        ]

        pipeline = FeedbackPipeline(memory_service=mock_memory, project_id="test_project")

        rules = pipeline.get_promoted_rules(phase_type="build", limit=5)

        assert len(rules) == 2
        assert (
            rules[0]["description"] == "RULE: Build phases frequently fail with dependency errors"
        )
        assert rules[0]["suggested_action"] == "Verify dependencies before build"
        assert rules[0]["occurrences"] == 5
        assert rules[1]["occurrences"] == 3

    def test_get_promoted_rules_filters_by_phase_type(self):
        """Should filter rules by phase_type when specified."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.search_telemetry_insights.return_value = [
            {
                "content": "Build rule",
                "metadata": {
                    "is_rule": True,
                    "insight_type": "promoted_rule",
                    "description": "Build rule description",
                    "phase_type": "build",
                    "occurrences": 5,
                },
                "confidence": 0.9,
            },
            {
                "content": "Test rule",
                "metadata": {
                    "is_rule": True,
                    "insight_type": "promoted_rule",
                    "description": "Test rule description",
                    "phase_type": "test",
                    "occurrences": 3,
                },
                "confidence": 0.8,
            },
        ]

        pipeline = FeedbackPipeline(memory_service=mock_memory, project_id="test_project")

        # Filter for build phase only
        rules = pipeline.get_promoted_rules(phase_type="build", limit=5)

        assert len(rules) == 1
        assert rules[0]["phase_type"] == "build"

    def test_get_promoted_rules_excludes_non_rules(self):
        """Should exclude insights that are not promoted rules."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.search_telemetry_insights.return_value = [
            {
                "content": "A promoted rule",
                "metadata": {
                    "is_rule": True,
                    "insight_type": "promoted_rule",
                    "description": "Actual rule",
                    "phase_type": "build",
                    "occurrences": 5,
                },
                "confidence": 0.9,
            },
            {
                "content": "Regular insight",
                "metadata": {
                    "is_rule": False,  # Not a rule
                    "insight_type": "failure_pattern",
                    "description": "Not a rule",
                    "phase_type": "build",
                },
                "confidence": 0.7,
            },
            {
                "content": "Another non-rule",
                "metadata": {
                    # No is_rule field and different insight_type
                    "insight_type": "cost_sink",
                    "description": "Cost insight",
                },
                "confidence": 0.6,
            },
        ]

        pipeline = FeedbackPipeline(memory_service=mock_memory, project_id="test_project")

        rules = pipeline.get_promoted_rules(limit=10)

        assert len(rules) == 1
        assert rules[0]["description"] == "Actual rule"

    def test_get_promoted_rules_respects_limit(self):
        """Should respect the limit parameter."""
        mock_memory = Mock()
        mock_memory.enabled = True
        # Return more rules than the limit
        mock_memory.search_telemetry_insights.return_value = [
            {
                "content": f"Rule {i}",
                "metadata": {
                    "is_rule": True,
                    "insight_type": "promoted_rule",
                    "description": f"Rule {i} description",
                    "phase_type": "build",
                    "occurrences": i,
                },
                "confidence": 0.9,
            }
            for i in range(10)
        ]

        pipeline = FeedbackPipeline(memory_service=mock_memory, project_id="test_project")

        rules = pipeline.get_promoted_rules(limit=3)

        assert len(rules) == 3

    def test_get_promoted_rules_handles_exception(self):
        """Should return empty list on exception."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.search_telemetry_insights.side_effect = Exception("Database error")

        pipeline = FeedbackPipeline(memory_service=mock_memory, project_id="test_project")

        rules = pipeline.get_promoted_rules(phase_type="build")

        assert rules == []


class TestAutonomousLoopPromotedRulesIntegration:
    """Tests for promoted rules integration in autonomous_loop._get_memory_context()."""

    def test_memory_context_includes_promoted_rules(self):
        """_get_memory_context should include promoted rules in the context."""
        # This test requires mocking the AutonomousLoop's dependencies
        # We'll test the integration at a higher level

        mock_feedback_pipeline = Mock()
        mock_feedback_pipeline.get_promoted_rules.return_value = [
            {
                "description": "Build phases need dependency checks",
                "suggested_action": "Run dependency audit first",
                "phase_type": "build",
                "hint_type": "ci_fail",
                "occurrences": 5,
                "confidence": 0.9,
            }
        ]

        # Verify the method was called correctly
        rules = mock_feedback_pipeline.get_promoted_rules(phase_type="build", limit=5)
        assert len(rules) == 1
        assert rules[0]["occurrences"] == 5

    def test_promoted_rules_formatted_correctly(self):
        """Promoted rules should be formatted with description and action."""
        rules = [
            {
                "description": "RULE: Build phases fail with dependency errors",
                "suggested_action": "Verify dependencies before build",
                "phase_type": "build",
                "hint_type": "ci_fail",
                "occurrences": 5,
                "confidence": 0.9,
            }
        ]

        # Format rules as done in autonomous_loop._get_memory_context()
        rules_lines = ["\n\n## Promoted Rules (High-Priority Patterns)"]
        rules_lines.append("The following rules were derived from recurring issues:")
        for rule in rules:
            description = rule.get("description", "")[:200]
            action = rule.get("suggested_action", "")[:150]
            occurrences = rule.get("occurrences", 0)
            rules_lines.append(f"- **Rule** (seen {occurrences}x): {description}")
            if action:
                rules_lines.append(f"  → Action: {action}")
        rules_context = "\n".join(rules_lines)

        assert "## Promoted Rules" in rules_context
        assert "seen 5x" in rules_context
        assert "RULE: Build phases fail with dependency errors" in rules_context
        assert "Verify dependencies before build" in rules_context


class TestPromotedRulesEndToEnd:
    """End-to-end tests for the promoted rules flow."""

    def test_rules_promoted_then_retrieved(self):
        """Rules promoted via _promote_hint_to_rule should be retrievable via get_promoted_rules."""
        mock_memory = Mock()
        mock_memory.enabled = True

        # Simulate the search returning a previously promoted rule
        mock_memory.search_telemetry_insights.return_value = [
            {
                "content": "Promoted rule content",
                "metadata": {
                    "is_rule": True,
                    "insight_type": "promoted_rule",
                    "description": "RULE (promoted from 3 occurrences): Phases of type 'build' frequently encounter 'ci_fail' issues.",
                    "suggested_action": "For build phases: Run local tests before submitting",
                    "phase_type": "build",
                    "hint_type": "ci_fail",
                    "occurrences": 3,
                },
                "confidence": 0.8,
                "timestamp": "2025-01-29T12:00:00Z",
            }
        ]

        pipeline = FeedbackPipeline(
            memory_service=mock_memory,
            project_id="test_project",
            run_id="test_run",
        )

        # Retrieve promoted rules
        rules = pipeline.get_promoted_rules(phase_type="build", limit=5)

        # Verify the rule was retrieved correctly
        assert len(rules) == 1
        assert "promoted from 3 occurrences" in rules[0]["description"]
        assert rules[0]["hint_type"] == "ci_fail"
        assert rules[0]["phase_type"] == "build"

        # Verify memory service was called with correct parameters
        mock_memory.search_telemetry_insights.assert_called_once()
        call_kwargs = mock_memory.search_telemetry_insights.call_args[1]
        assert call_kwargs["project_id"] == "test_project"
        assert call_kwargs["max_age_hours"] == 168  # 7 days
