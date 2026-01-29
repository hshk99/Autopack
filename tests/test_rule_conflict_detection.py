"""Unit tests for rule conflict detection (IMP-LOOP-020)

Tests cover:
- detect_rule_conflicts() main function
- _scopes_overlap() scope pattern matching
- _directives_conflict() semantic conflict detection
- _patterns_can_intersect() glob pattern analysis
- detect_hint_conflicts() for run-local hints
- format_conflicts_report() output formatting
- get_active_rules_with_conflicts() integration
"""

from datetime import datetime, timezone

from autopack.learned_rules import (
    DiscoveryStage,
    LearnedRule,
    RunRuleHint,
    _directives_conflict,
    _extract_directory,
    _extract_extension,
    _hint_directives_conflict,
    _hint_scopes_overlap,
    _patterns_can_intersect,
    _scopes_overlap,
    _share_topic_keywords,
    detect_hint_conflicts,
    detect_rule_conflicts,
    format_conflicts_report,
)

# ============================================================================
# Helper to create test rules
# ============================================================================


def create_test_rule(
    rule_id: str,
    constraint: str,
    scope_pattern: str | None = None,
    task_category: str = "testing",
    status: str = "active",
    stage: str = DiscoveryStage.RULE.value,
) -> LearnedRule:
    """Create a test LearnedRule with minimal required fields."""
    now = datetime.now(timezone.utc).isoformat()
    return LearnedRule(
        rule_id=rule_id,
        task_category=task_category,
        scope_pattern=scope_pattern,
        constraint=constraint,
        source_hint_ids=["test:phase1"],
        promotion_count=1,
        first_seen=now,
        last_seen=now,
        status=status,
        stage=stage,
    )


def create_test_hint(
    hint_text: str,
    scope_paths: list[str] | None = None,
    task_category: str | None = "testing",
) -> RunRuleHint:
    """Create a test RunRuleHint with minimal required fields."""
    now = datetime.now(timezone.utc).isoformat()
    return RunRuleHint(
        run_id="test_run",
        phase_index=0,
        phase_id="phase_0",
        tier_id=None,
        task_category=task_category,
        scope_paths=scope_paths or [],
        source_issue_keys=[],
        hint_text=hint_text,
        created_at=now,
    )


# ============================================================================
# Scope Overlap Tests
# ============================================================================


class TestScopesOverlap:
    """Tests for _scopes_overlap function."""

    def test_both_global_overlap(self):
        """Two rules with no scope_pattern (global) should overlap."""
        rule1 = create_test_rule("rule1", "constraint1", scope_pattern=None)
        rule2 = create_test_rule("rule2", "constraint2", scope_pattern=None)
        assert _scopes_overlap(rule1, rule2) is True

    def test_one_global_overlaps(self):
        """A global rule overlaps with any scoped rule."""
        rule1 = create_test_rule("rule1", "constraint1", scope_pattern=None)
        rule2 = create_test_rule("rule2", "constraint2", scope_pattern="*.py")
        assert _scopes_overlap(rule1, rule2) is True
        assert _scopes_overlap(rule2, rule1) is True

    def test_same_pattern_overlaps(self):
        """Identical patterns should overlap."""
        rule1 = create_test_rule("rule1", "constraint1", scope_pattern="*.py")
        rule2 = create_test_rule("rule2", "constraint2", scope_pattern="*.py")
        assert _scopes_overlap(rule1, rule2) is True

    def test_different_extensions_no_overlap(self):
        """Different file extensions should not overlap."""
        rule1 = create_test_rule("rule1", "constraint1", scope_pattern="*.py")
        rule2 = create_test_rule("rule2", "constraint2", scope_pattern="*.js")
        assert _scopes_overlap(rule1, rule2) is False

    def test_subdirectory_patterns_overlap(self):
        """A pattern in a subdirectory overlaps with parent pattern."""
        rule1 = create_test_rule("rule1", "constraint1", scope_pattern="src/*.py")
        rule2 = create_test_rule("rule2", "constraint2", scope_pattern="src/auth/*.py")
        assert _scopes_overlap(rule1, rule2) is True


class TestPatternsCanIntersect:
    """Tests for _patterns_can_intersect helper function."""

    def test_exact_match(self):
        """Exact pattern match should intersect."""
        assert _patterns_can_intersect("*.py", "*.py") is True

    def test_different_extensions(self):
        """Different extensions should not intersect."""
        assert _patterns_can_intersect("*.py", "*.js") is False

    def test_same_extension_different_dirs(self):
        """Same extension in different dirs should intersect (both match .py files)."""
        assert _patterns_can_intersect("src/*.py", "tests/*.py") is True

    def test_nested_directory(self):
        """Nested directories should intersect with parent."""
        assert _patterns_can_intersect("src/*", "src/autopack/*") is True

    def test_wildcard_extension(self):
        """Wildcard extension patterns should be checked."""
        assert _patterns_can_intersect("*.py", "src/*.py") is True


class TestExtractExtension:
    """Tests for _extract_extension helper function."""

    def test_simple_extension(self):
        """Extract extension from simple pattern."""
        assert _extract_extension("*.py") == ".py"

    def test_path_with_extension(self):
        """Extract extension from path pattern."""
        assert _extract_extension("src/*.py") == ".py"

    def test_no_extension(self):
        """Pattern without extension should return None."""
        assert _extract_extension("src/*") is None

    def test_double_star_extension(self):
        """Handle **/*.py patterns."""
        assert _extract_extension("**/*.py") == ".py"


class TestExtractDirectory:
    """Tests for _extract_directory helper function."""

    def test_simple_directory(self):
        """Extract directory from pattern."""
        assert _extract_directory("src/*.py") == "src"

    def test_nested_directory(self):
        """Extract nested directory from pattern."""
        assert _extract_directory("src/autopack/*.py") == "src/autopack"

    def test_no_directory(self):
        """Pattern without directory should return None."""
        assert _extract_directory("*.py") is None

    def test_wildcard_start(self):
        """Pattern starting with wildcard should return None."""
        assert _extract_directory("*/*.py") is None


# ============================================================================
# Directive Conflict Tests
# ============================================================================


class TestDirectivesConflict:
    """Tests for _directives_conflict function."""

    def test_always_vs_never_conflict(self):
        """'Always add X' vs 'Never add X' should conflict."""
        rule1 = create_test_rule("rule1", "Always add type hints to functions")
        rule2 = create_test_rule("rule2", "Never add type hints to test functions")
        assert _directives_conflict(rule1, rule2) is True

    def test_require_vs_avoid_conflict(self):
        """'Require X' vs 'Avoid X' should conflict."""
        rule1 = create_test_rule("rule1", "Require docstrings for public methods")
        rule2 = create_test_rule("rule2", "Avoid docstrings for private methods")
        # Both mention docstrings and methods - conflict
        assert _directives_conflict(rule1, rule2) is True

    def test_add_vs_skip_conflict(self):
        """'Add X' vs 'Skip X' should conflict."""
        rule1 = create_test_rule("rule1", "Add logging to API handlers")
        rule2 = create_test_rule("rule2", "Skip logging for test handlers")
        # Both mention logging and handlers - conflict
        assert _directives_conflict(rule1, rule2) is True

    def test_same_directive_no_conflict(self):
        """Two rules with same directive type should not conflict."""
        rule1 = create_test_rule("rule1", "Always add type hints")
        rule2 = create_test_rule("rule2", "Always add docstrings")
        assert _directives_conflict(rule1, rule2) is False

    def test_different_topics_no_conflict(self):
        """Opposing keywords on different topics should not conflict."""
        rule1 = create_test_rule("rule1", "Always apply type annotations")
        rule2 = create_test_rule("rule2", "Never hardcode magic constants")
        assert _directives_conflict(rule1, rule2) is False

    def test_enable_vs_disable_conflict(self):
        """'Enable X' vs 'Disable X' should conflict."""
        rule1 = create_test_rule("rule1", "Enable strict mode for linting")
        rule2 = create_test_rule("rule2", "Disable strict mode for tests")
        assert _directives_conflict(rule1, rule2) is True


class TestShareTopicKeywords:
    """Tests for _share_topic_keywords helper function."""

    def test_shared_topic(self):
        """Words with shared meaningful topic should return True."""
        words1 = {"always", "add", "type", "hints", "functions"}
        words2 = {"never", "add", "type", "hints", "tests"}
        assert _share_topic_keywords(words1, words2) is True

    def test_no_shared_topic(self):
        """Words with no shared meaningful topic should return False."""
        words1 = {"always", "use", "logging"}
        words2 = {"never", "use", "magic", "numbers"}
        # "use" is meaningful, so this returns True
        # Let's use truly different words
        words1 = {"logging", "handlers", "api"}
        words2 = {"magic", "numbers", "constants"}
        assert _share_topic_keywords(words1, words2) is False

    def test_only_stop_words_shared(self):
        """Sharing only stop words should return False."""
        words1 = {"the", "a", "always", "type"}
        words2 = {"the", "a", "never", "magic"}
        # "type" and "magic" are different topics
        assert _share_topic_keywords(words1, words2) is False


# ============================================================================
# Full Conflict Detection Tests
# ============================================================================


class TestDetectRuleConflicts:
    """Tests for detect_rule_conflicts main function."""

    def test_no_conflicts_empty_list(self):
        """Empty rule list should return no conflicts."""
        conflicts = detect_rule_conflicts([])
        assert conflicts == []

    def test_no_conflicts_single_rule(self):
        """Single rule cannot conflict with itself."""
        rules = [create_test_rule("rule1", "Always add type hints")]
        conflicts = detect_rule_conflicts(rules)
        assert conflicts == []

    def test_detects_overlapping_conflicting_rules(self):
        """Should detect conflict between overlapping rules with opposing directives."""
        rules = [
            create_test_rule("rule1", "Always add type hints to functions", scope_pattern="*.py"),
            create_test_rule("rule2", "Never add type hints to test files", scope_pattern="*.py"),
        ]
        conflicts = detect_rule_conflicts(rules)
        assert len(conflicts) == 1
        assert conflicts[0][0].rule_id == "rule1"
        assert conflicts[0][1].rule_id == "rule2"
        assert "conflicting directives" in conflicts[0][2]

    def test_no_conflict_different_categories(self):
        """Rules in different task categories should not conflict."""
        rules = [
            create_test_rule(
                "rule1",
                "Always add type hints",
                scope_pattern="*.py",
                task_category="typing",
            ),
            create_test_rule(
                "rule2",
                "Never add type hints",
                scope_pattern="*.py",
                task_category="testing",
            ),
        ]
        conflicts = detect_rule_conflicts(rules)
        assert len(conflicts) == 0

    def test_inactive_rules_ignored(self):
        """Inactive rules should not be checked for conflicts."""
        rules = [
            create_test_rule("rule1", "Always add type hints", scope_pattern="*.py"),
            create_test_rule(
                "rule2", "Never add type hints", scope_pattern="*.py", status="deprecated"
            ),
        ]
        conflicts = detect_rule_conflicts(rules)
        assert len(conflicts) == 0

    def test_multiple_conflicts_detected(self):
        """Should detect multiple conflicts when present."""
        rules = [
            create_test_rule("rule1", "Always add type hints", scope_pattern="*.py"),
            create_test_rule("rule2", "Never add type hints", scope_pattern="*.py"),
            create_test_rule("rule3", "Always add docstrings", scope_pattern="*.py"),
            create_test_rule("rule4", "Skip adding docstrings", scope_pattern="*.py"),
        ]
        conflicts = detect_rule_conflicts(rules)
        assert len(conflicts) == 2

    def test_global_rules_conflict(self):
        """Global rules with opposing directives should conflict."""
        rules = [
            create_test_rule("rule1", "Always require authentication", scope_pattern=None),
            create_test_rule(
                "rule2", "Skip authentication for public endpoints", scope_pattern=None
            ),
        ]
        conflicts = detect_rule_conflicts(rules)
        assert len(conflicts) == 1


# ============================================================================
# Hint Conflict Detection Tests
# ============================================================================


class TestHintScopesOverlap:
    """Tests for _hint_scopes_overlap function."""

    def test_both_empty_overlap(self):
        """Two hints with no scope_paths should overlap."""
        hint1 = create_test_hint("hint1", scope_paths=[])
        hint2 = create_test_hint("hint2", scope_paths=[])
        assert _hint_scopes_overlap(hint1, hint2) is True

    def test_one_empty_overlaps(self):
        """A hint with no scope overlaps with any scoped hint."""
        hint1 = create_test_hint("hint1", scope_paths=[])
        hint2 = create_test_hint("hint2", scope_paths=["src/main.py"])
        assert _hint_scopes_overlap(hint1, hint2) is True

    def test_direct_path_overlap(self):
        """Hints with shared paths should overlap."""
        hint1 = create_test_hint("hint1", scope_paths=["src/main.py", "src/utils.py"])
        hint2 = create_test_hint("hint2", scope_paths=["src/main.py", "src/config.py"])
        assert _hint_scopes_overlap(hint1, hint2) is True

    def test_directory_overlap(self):
        """Hints in same directory should overlap."""
        hint1 = create_test_hint("hint1", scope_paths=["src/autopack/main.py"])
        hint2 = create_test_hint("hint2", scope_paths=["src/autopack/utils.py"])
        assert _hint_scopes_overlap(hint1, hint2) is True

    def test_no_overlap_different_dirs(self):
        """Hints in different directories should not overlap."""
        hint1 = create_test_hint("hint1", scope_paths=["src/main.py"])
        hint2 = create_test_hint("hint2", scope_paths=["tests/test_main.py"])
        assert _hint_scopes_overlap(hint1, hint2) is False


class TestHintDirectivesConflict:
    """Tests for _hint_directives_conflict function."""

    def test_hint_conflict_detection(self):
        """Hints with opposing keywords should conflict."""
        hint1 = create_test_hint("Always add type hints to functions")
        hint2 = create_test_hint("Never add type hints to tests")
        assert _hint_directives_conflict(hint1, hint2) is True

    def test_hint_no_conflict(self):
        """Hints without opposing keywords should not conflict."""
        hint1 = create_test_hint("Watch out for import errors")
        hint2 = create_test_hint("Check for missing dependencies")
        assert _hint_directives_conflict(hint1, hint2) is False


class TestDetectHintConflicts:
    """Tests for detect_hint_conflicts function."""

    def test_detects_hint_conflicts(self):
        """Should detect conflicts between hints with overlapping scope and opposing directives."""
        hints = [
            create_test_hint("Always add logging", scope_paths=["src/api.py"]),
            create_test_hint("Never add logging to handlers", scope_paths=["src/api.py"]),
        ]
        conflicts = detect_hint_conflicts(hints)
        assert len(conflicts) == 1

    def test_different_categories_no_conflict(self):
        """Hints in different categories should not conflict."""
        hint1 = create_test_hint("Always add type hints", task_category="typing")
        hint2 = create_test_hint("Never add type hints", task_category="testing")
        conflicts = detect_hint_conflicts([hint1, hint2])
        assert len(conflicts) == 0


# ============================================================================
# Format Report Tests
# ============================================================================


class TestFormatConflictsReport:
    """Tests for format_conflicts_report function."""

    def test_empty_conflicts(self):
        """Empty conflicts should return 'No conflicts detected'."""
        report = format_conflicts_report([])
        assert "No conflicts detected" in report

    def test_single_conflict_format(self):
        """Single conflict should be formatted properly."""
        rule1 = create_test_rule("rule1", "Always add type hints", scope_pattern="*.py")
        rule2 = create_test_rule("rule2", "Never add type hints", scope_pattern="*.py")
        conflicts = [(rule1, rule2, "Scope overlap with conflicting directives")]

        report = format_conflicts_report(conflicts)

        assert "1 potential rule conflict" in report
        assert "rule1" in report
        assert "rule2" in report
        assert "Always add type hints" in report
        assert "Never add type hints" in report
        assert "Scope overlap with conflicting directives" in report

    def test_multiple_conflicts_format(self):
        """Multiple conflicts should all be included in report."""
        rules = [
            create_test_rule("rule1", "constraint1"),
            create_test_rule("rule2", "constraint2"),
            create_test_rule("rule3", "constraint3"),
            create_test_rule("rule4", "constraint4"),
        ]
        conflicts = [
            (rules[0], rules[1], "reason1"),
            (rules[2], rules[3], "reason2"),
        ]

        report = format_conflicts_report(conflicts)

        assert "2 potential rule conflict" in report
        assert "Conflict 1" in report
        assert "Conflict 2" in report
        assert "reason1" in report
        assert "reason2" in report


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Edge case tests for conflict detection."""

    def test_case_insensitive_keyword_matching(self):
        """Keyword matching should be case-insensitive."""
        rule1 = create_test_rule("rule1", "ALWAYS ADD type hints")
        rule2 = create_test_rule("rule2", "never add TYPE hints")
        assert _directives_conflict(rule1, rule2) is True

    def test_empty_constraint_no_crash(self):
        """Empty constraint should not crash."""
        rule1 = create_test_rule("rule1", "")
        rule2 = create_test_rule("rule2", "Always add type hints")
        # Should not raise, just return False (no conflict detected)
        assert _directives_conflict(rule1, rule2) is False

    def test_special_characters_in_constraint(self):
        """Special characters should not affect matching."""
        rule1 = create_test_rule("rule1", "Always add type-hints!")
        rule2 = create_test_rule("rule2", "Never add type-hints.")
        # The tokenization splits on spaces, so "type-hints!" is one token
        # This may or may not match depending on implementation
        # At minimum, should not crash
        result = _directives_conflict(rule1, rule2)
        assert isinstance(result, bool)

    def test_very_long_constraint(self):
        """Very long constraints should be handled."""
        long_text = "Always " + "add type hints " * 100
        rule1 = create_test_rule("rule1", long_text)
        rule2 = create_test_rule("rule2", "Never add type hints")
        # Should not timeout or crash
        result = _directives_conflict(rule1, rule2)
        assert isinstance(result, bool)
