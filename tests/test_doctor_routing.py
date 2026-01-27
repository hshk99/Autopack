"""Unit tests for Doctor routing logic.

Tests the decision-making logic for:
- Identifying complex failures
- Choosing appropriate doctor models
- Escalating to stronger models
- Creating context summaries
"""

from typing import Any, Dict, List


class MockContext:
    """Mock context object for testing."""

    def __init__(self):
        self.error_categories = ["syntax_error"]
        self.patch_errors = []
        self.attempt_count = 1
        self.health_ratio = 0.5
        self.budget_remaining = 1000
        self.prior_escalated_action = False
        self.model_confidence = 0.8
        self.current_model = "claude-sonnet-4-5"


def is_complex_failure(context: MockContext) -> bool:
    """Determine if a failure is complex based on context.

    Args:
        context: Context object with failure information

    Returns:
        True if failure is complex, False otherwise
    """
    # Multiple error categories
    if len(context.error_categories) >= 2:
        return True

    # Multiple patch errors
    if len(context.patch_errors) >= 2:
        return True

    # Many attempts (4 or more)
    if context.attempt_count >= 4:
        return True

    # Health ratio near limit (>= 0.8)
    if context.health_ratio >= 0.8:
        return True

    # Prior escalated action
    if context.prior_escalated_action:
        return True

    return False


def choose_doctor_model(context: MockContext) -> str:
    """Choose appropriate doctor model based on context.

    Args:
        context: Context object with failure information

    Returns:
        Model name ('claude-opus-4-5' for strong, 'claude-sonnet-4-5' for cheap)
    """
    # Health ratio >= 0.8 always returns strong model
    if context.health_ratio >= 0.8:
        return "claude-opus-4-5"

    # Complex failure returns strong model
    if is_complex_failure(context):
        return "claude-opus-4-5"

    # Routine failure returns cheap model
    return "claude-sonnet-4-5"


def should_escalate_doctor_model(context: MockContext) -> bool:
    """Determine if doctor model should be escalated.

    Args:
        context: Context object with failure information

    Returns:
        True if should escalate, False otherwise
    """
    # Strong model never escalates (already at top)
    if context.current_model == "claude-opus-4-5":
        return False

    # High confidence prevents escalation
    if context.model_confidence >= 0.7:
        return False

    # Cheap model + low confidence + attempts >= 2 -> escalate
    if (
        context.current_model == "claude-sonnet-4-5"
        and context.model_confidence < 0.7
        and context.attempt_count >= 2
    ):
        return True

    return False


class DoctorContextSummary:
    """Summary of doctor context for serialization."""

    def __init__(
        self,
        error_categories: List[str],
        patch_errors: List[str],
        attempt_count: int,
        health_ratio: float,
        budget_remaining: int,
    ):
        self.error_categories = error_categories
        self.patch_errors = patch_errors
        self.attempt_count = attempt_count
        self.health_ratio = health_ratio
        self.budget_remaining = budget_remaining

    @classmethod
    def from_context(cls, context: MockContext) -> "DoctorContextSummary":
        """Create summary from context object.

        Args:
            context: Context object to summarize

        Returns:
            DoctorContextSummary instance
        """
        return cls(
            error_categories=context.error_categories,
            patch_errors=context.patch_errors,
            attempt_count=context.attempt_count,
            health_ratio=context.health_ratio,
            budget_remaining=context.budget_remaining,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert summary to dictionary.

        Returns:
            Dictionary representation of summary
        """
        return {
            "error_categories": self.error_categories,
            "patch_errors": self.patch_errors,
            "attempt_count": self.attempt_count,
            "health_ratio": self.health_ratio,
            "budget_remaining": self.budget_remaining,
        }


class TestIsComplexFailure:
    """Test suite for is_complex_failure() function."""

    def test_simple_failure_returns_false(self):
        """Single category, 1 attempt, healthy budget -> False."""
        context = MockContext()
        context.error_categories = ["syntax_error"]
        context.attempt_count = 1
        context.health_ratio = 0.5

        result = is_complex_failure(context)
        assert result is False

    def test_multiple_error_categories_returns_true(self):
        """2+ error categories -> True."""
        context = MockContext()
        context.error_categories = ["syntax_error", "import_error"]

        result = is_complex_failure(context)
        assert result is True

    def test_multiple_patch_errors_returns_true(self):
        """2+ patch errors -> True."""
        context = MockContext()
        context.patch_errors = ["error1", "error2"]

        result = is_complex_failure(context)
        assert result is True

    def test_many_attempts_returns_true(self):
        """Many attempts (>=4) -> True."""
        context = MockContext()
        context.attempt_count = 4

        result = is_complex_failure(context)
        assert result is True

    def test_high_health_ratio_returns_true(self):
        """Health ratio >= 0.8 -> True."""
        context = MockContext()
        context.health_ratio = 0.8

        result = is_complex_failure(context)
        assert result is True

    def test_prior_escalated_action_returns_true(self):
        """Prior escalated action -> True."""
        context = MockContext()
        context.prior_escalated_action = True

        result = is_complex_failure(context)
        assert result is True

    def test_edge_case_just_below_thresholds(self):
        """Test values just below thresholds return False."""
        context = MockContext()
        context.error_categories = ["syntax_error"]  # Only 1
        context.patch_errors = ["error1"]  # Only 1
        context.attempt_count = 3  # Less than 4
        context.health_ratio = 0.79  # Less than 0.8
        context.prior_escalated_action = False

        result = is_complex_failure(context)
        assert result is False


class TestChooseDoctorModel:
    """Test suite for choose_doctor_model() function."""

    def test_high_health_ratio_returns_strong_model(self):
        """Health ratio >= 0.8 always returns strong model."""
        context = MockContext()
        context.health_ratio = 0.85

        result = choose_doctor_model(context)
        assert result == "claude-opus-4-5"

    def test_routine_failure_returns_cheap_model(self):
        """Routine failure returns cheap model."""
        context = MockContext()
        context.error_categories = ["syntax_error"]
        context.attempt_count = 1
        context.health_ratio = 0.5
        context.prior_escalated_action = False

        result = choose_doctor_model(context)
        assert result == "claude-sonnet-4-5"

    def test_complex_failure_returns_strong_model(self):
        """Complex failure returns strong model."""
        context = MockContext()
        context.attempt_count = 4  # Makes it complex
        context.health_ratio = 0.5

        result = choose_doctor_model(context)
        assert result == "claude-opus-4-5"

    def test_multiple_error_categories_returns_strong_model(self):
        """Multiple error categories trigger strong model."""
        context = MockContext()
        context.error_categories = ["syntax_error", "import_error", "type_error"]
        context.health_ratio = 0.5

        result = choose_doctor_model(context)
        assert result == "claude-opus-4-5"

    def test_multiple_patch_errors_returns_strong_model(self):
        """Multiple patch errors trigger strong model."""
        context = MockContext()
        context.patch_errors = ["error1", "error2"]
        context.health_ratio = 0.5

        result = choose_doctor_model(context)
        assert result == "claude-opus-4-5"


class TestShouldEscalateDoctorModel:
    """Test suite for should_escalate_doctor_model() function."""

    def test_cheap_model_low_confidence_multiple_attempts_returns_true(self):
        """Cheap model + low confidence + attempts >= 2 -> True."""
        context = MockContext()
        context.current_model = "claude-sonnet-4-5"
        context.model_confidence = 0.3
        context.attempt_count = 2

        result = should_escalate_doctor_model(context)
        assert result is True

    def test_strong_model_never_escalates(self):
        """Strong model -> False (already escalated)."""
        context = MockContext()
        context.current_model = "claude-opus-4-5"
        context.model_confidence = 0.3
        context.attempt_count = 5

        result = should_escalate_doctor_model(context)
        assert result is False

    def test_high_confidence_prevents_escalation(self):
        """High confidence -> False."""
        context = MockContext()
        context.current_model = "claude-sonnet-4-5"
        context.model_confidence = 0.9
        context.attempt_count = 3

        result = should_escalate_doctor_model(context)
        assert result is False

    def test_low_attempts_prevents_escalation(self):
        """Low attempts prevents escalation."""
        context = MockContext()
        context.current_model = "claude-sonnet-4-5"
        context.model_confidence = 0.3
        context.attempt_count = 1

        result = should_escalate_doctor_model(context)
        assert result is False

    def test_threshold_confidence_with_multiple_attempts(self):
        """Test escalation at exact threshold values."""
        context = MockContext()
        context.current_model = "claude-sonnet-4-5"
        context.model_confidence = 0.5  # Below 0.7 threshold
        context.attempt_count = 2

        result = should_escalate_doctor_model(context)
        assert result is True

    def test_confidence_at_threshold_prevents_escalation(self):
        """Confidence at 0.7 threshold prevents escalation."""
        context = MockContext()
        context.current_model = "claude-sonnet-4-5"
        context.model_confidence = 0.7  # At threshold
        context.attempt_count = 3

        result = should_escalate_doctor_model(context)
        assert result is False


class TestDoctorContextSummary:
    """Test suite for DoctorContextSummary class."""

    def test_from_context_creates_correct_summary(self):
        """Verify DoctorContextSummary.from_context() creates correct summary."""
        context = MockContext()
        context.error_categories = ["syntax_error", "import_error"]
        context.patch_errors = ["error1"]
        context.attempt_count = 3
        context.health_ratio = 0.6
        context.budget_remaining = 500

        summary = DoctorContextSummary.from_context(context)

        assert summary.error_categories == ["syntax_error", "import_error"]
        assert summary.patch_errors == ["error1"]
        assert summary.attempt_count == 3
        assert summary.health_ratio == 0.6
        assert summary.budget_remaining == 500

    def test_to_dict_produces_expected_json(self):
        """Verify to_dict() produces expected JSON."""
        context = MockContext()
        context.error_categories = ["syntax_error"]
        context.patch_errors = []
        context.attempt_count = 1
        context.health_ratio = 0.5
        context.budget_remaining = 1000

        summary = DoctorContextSummary.from_context(context)
        result = summary.to_dict()

        assert isinstance(result, dict)
        assert result["error_categories"] == ["syntax_error"]
        assert result["patch_errors"] == []
        assert result["attempt_count"] == 1
        assert result["health_ratio"] == 0.5
        assert result["budget_remaining"] == 1000

    def test_to_dict_has_all_required_keys(self):
        """Verify to_dict() contains all required keys."""
        context = MockContext()
        summary = DoctorContextSummary.from_context(context)
        result = summary.to_dict()

        expected_keys = [
            "error_categories",
            "patch_errors",
            "attempt_count",
            "health_ratio",
            "budget_remaining",
        ]

        for key in expected_keys:
            assert key in result

    def test_summary_with_complex_error_data(self):
        """Test summary creation with complex error data."""
        context = MockContext()
        context.error_categories = ["syntax_error", "import_error", "type_error"]
        context.patch_errors = ["patch_error_1", "patch_error_2", "patch_error_3"]
        context.attempt_count = 5
        context.health_ratio = 0.9
        context.budget_remaining = 100

        summary = DoctorContextSummary.from_context(context)
        result = summary.to_dict()

        assert len(result["error_categories"]) == 3
        assert len(result["patch_errors"]) == 3
        assert result["attempt_count"] == 5
        assert result["health_ratio"] == 0.9
        assert result["budget_remaining"] == 100

    def test_summary_with_empty_lists(self):
        """Test summary handles empty error lists correctly."""
        context = MockContext()
        context.error_categories = []
        context.patch_errors = []

        summary = DoctorContextSummary.from_context(context)
        result = summary.to_dict()

        assert result["error_categories"] == []
        assert result["patch_errors"] == []
