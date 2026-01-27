"""Unit tests for learned rules system (Stage 0A + 0B)

Tests cover:
- RunRuleHint creation and persistence
- LearnedRule creation and persistence
- Hint recording when issues resolved
- Rule promotion from hints
- Relevance filtering for phase
- Prompt formatting
- LearnedRuleAging decay monitoring (IMP-LOOP-013)
"""

from datetime import datetime, timedelta, timezone

from autopack.learned_rules import DiscoveryStage, LearnedRule, LearnedRuleAging

# ============================================================================
# LearnedRuleAging Tests (IMP-LOOP-013)
# ============================================================================


class TestLearnedRuleAging:
    """Tests for LearnedRuleAging decay monitoring."""

    def test_decay_score_fresh_rule(self):
        """A fresh rule with no age or failures should have low decay."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc),
            last_validation_date=datetime.now(timezone.utc),
            age_days=0,
            validation_failures=0,
            decay_score=0.0,
        )
        decay = aging.calculate_decay()
        assert decay == 0.0

    def test_decay_score_from_age_only(self):
        """Age contributes up to 0.5 to decay score."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc) - timedelta(days=365),
            last_validation_date=datetime.now(timezone.utc),
            age_days=365,
            validation_failures=0,
            decay_score=0.0,
        )
        decay = aging.calculate_decay()
        assert decay == 0.5  # 365/365 = 1.0, capped at 0.5

    def test_decay_score_from_failures_only(self):
        """Validation failures contribute up to 0.5 to decay score."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc),
            last_validation_date=datetime.now(timezone.utc),
            age_days=0,
            validation_failures=5,
            decay_score=0.0,
        )
        decay = aging.calculate_decay()
        assert decay == 0.5  # 5 * 0.1 = 0.5

    def test_decay_score_combined(self):
        """Combined age and failures should sum up to max 1.0."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc) - timedelta(days=180),
            last_validation_date=datetime.now(timezone.utc),
            age_days=180,
            validation_failures=3,
            decay_score=0.0,
        )
        decay = aging.calculate_decay()
        # age_factor = 180/365 ≈ 0.493
        # failure_factor = 3 * 0.1 = 0.3
        # total ≈ 0.793
        expected = min(180 / 365 + 0.3, 1.0)
        assert abs(decay - expected) < 0.001

    def test_decay_score_capped_at_one(self):
        """Decay score should never exceed 1.0."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc) - timedelta(days=1000),
            last_validation_date=datetime.now(timezone.utc),
            age_days=1000,
            validation_failures=10,
            decay_score=0.0,
        )
        decay = aging.calculate_decay()
        assert decay == 1.0

    def test_should_deprecate_below_threshold(self):
        """Rule with decay <= 0.7 should not be deprecated."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc),
            last_validation_date=datetime.now(timezone.utc),
            age_days=100,
            validation_failures=2,
            decay_score=0.0,
        )
        aging.decay_score = aging.calculate_decay()
        # age_factor = 100/365 ≈ 0.274
        # failure_factor = 2 * 0.1 = 0.2
        # total ≈ 0.474
        assert not aging.should_deprecate()

    def test_should_deprecate_above_threshold(self):
        """Rule with decay > 0.7 should be deprecated."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc) - timedelta(days=300),
            last_validation_date=datetime.now(timezone.utc),
            age_days=300,
            validation_failures=4,
            decay_score=0.0,
        )
        aging.decay_score = aging.calculate_decay()
        # age_factor = 300/365 ≈ 0.822, capped at 0.5
        # failure_factor = 4 * 0.1 = 0.4
        # total = 0.9
        assert aging.should_deprecate()

    def test_should_deprecate_at_boundary(self):
        """Rule with decay exactly at 0.7 should not be deprecated."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc),
            last_validation_date=datetime.now(timezone.utc),
            age_days=0,
            validation_failures=0,
            decay_score=0.7,  # Exactly at threshold
        )
        assert not aging.should_deprecate()

    def test_should_deprecate_just_above_boundary(self):
        """Rule with decay just above 0.7 should be deprecated."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc),
            last_validation_date=datetime.now(timezone.utc),
            age_days=0,
            validation_failures=0,
            decay_score=0.71,  # Just above threshold
        )
        assert aging.should_deprecate()

    def test_record_validation_failure(self):
        """Recording a failure should increase decay score."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc),
            last_validation_date=datetime.now(timezone.utc),
            age_days=0,
            validation_failures=0,
            decay_score=0.0,
        )
        initial_decay = aging.decay_score
        aging.record_validation_failure()
        assert aging.validation_failures == 1
        assert aging.decay_score > initial_decay
        assert aging.decay_score == 0.1  # 1 failure * 0.1

    def test_multiple_validation_failures(self):
        """Multiple failures should accumulate."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc),
            last_validation_date=datetime.now(timezone.utc),
            age_days=0,
            validation_failures=0,
            decay_score=0.0,
        )
        for _ in range(5):
            aging.record_validation_failure()
        assert aging.validation_failures == 5
        assert aging.decay_score == 0.5  # 5 * 0.1 = 0.5, capped

    def test_record_validation_success(self):
        """Recording success should update last_validation_date."""
        old_time = datetime.now(timezone.utc) - timedelta(days=30)
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=old_time,
            last_validation_date=old_time,
            age_days=30,
            validation_failures=0,
            decay_score=0.0,
        )
        aging.record_validation_success()
        # Last validation date should be updated to now
        assert aging.last_validation_date > old_time

    def test_from_rule_factory_method(self):
        """from_rule should create aging tracker from LearnedRule."""
        now = datetime.now(timezone.utc)
        creation = now - timedelta(days=100)
        rule = LearnedRule(
            rule_id="test.rule_001",
            task_category="testing",
            scope_pattern="*.py",
            constraint="Always use type hints",
            source_hint_ids=["run1:phase1"],
            promotion_count=3,
            first_seen=creation.isoformat(),
            last_seen=now.isoformat(),
            status="active",
            stage=DiscoveryStage.RULE.value,
        )
        aging = LearnedRuleAging.from_rule(rule)
        assert aging.rule_id == "test.rule_001"
        assert aging.age_days >= 100  # May be slightly more due to time elapsed
        assert aging.validation_failures == 0
        # Decay should be calculated based on age
        assert aging.decay_score > 0

    def test_deprecation_threshold_consistency(self):
        """Verify 0.7 threshold is correctly implemented."""
        # Test values around the threshold
        test_cases = [
            (0.69, False),
            (0.70, False),
            (0.701, True),
            (0.75, True),
            (1.0, True),
        ]
        for decay_score, expected_deprecate in test_cases:
            aging = LearnedRuleAging(
                rule_id="test.rule",
                creation_date=datetime.now(timezone.utc),
                last_validation_date=datetime.now(timezone.utc),
                age_days=0,
                validation_failures=0,
                decay_score=decay_score,
            )
            assert (
                aging.should_deprecate() == expected_deprecate
            ), f"decay_score={decay_score} should return {expected_deprecate}"


class TestLearnedRuleAgingEdgeCases:
    """Edge case tests for LearnedRuleAging."""

    def test_negative_age_days_handled(self):
        """Negative age_days should be handled gracefully."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc),
            last_validation_date=datetime.now(timezone.utc),
            age_days=-1,  # Edge case: negative age
            validation_failures=0,
            decay_score=0.0,
        )
        decay = aging.calculate_decay()
        # Negative age results in negative factor, but min caps it
        assert decay >= 0.0

    def test_very_old_rule_decay(self):
        """Very old rules should max out at 0.5 from age."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc) - timedelta(days=3650),  # 10 years
            last_validation_date=datetime.now(timezone.utc),
            age_days=3650,
            validation_failures=0,
            decay_score=0.0,
        )
        decay = aging.calculate_decay()
        assert decay == 0.5  # Age factor capped at 0.5

    def test_many_failures_decay(self):
        """Many failures should max out at 0.5 from failures."""
        aging = LearnedRuleAging(
            rule_id="test.rule_001",
            creation_date=datetime.now(timezone.utc),
            last_validation_date=datetime.now(timezone.utc),
            age_days=0,
            validation_failures=100,  # Many failures
            decay_score=0.0,
        )
        decay = aging.calculate_decay()
        assert decay == 0.5  # Failure factor capped at 0.5
