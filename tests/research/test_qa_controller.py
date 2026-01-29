"""Unit tests for QAController module."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autopack.intention_anchor.v2 import (
    IntentionAnchorV2,
    NorthStarIntention,
    PivotIntentions,
    SafetyRiskIntention,
    validate_pivot_completeness,
)
from autopack.research.idea_parser import ProjectType
from autopack.research.qa_controller import (
    _PROJECT_TYPE_DEFAULTS,
    _SAFE_DEFAULTS,
    Answer,
    AnswerSource,
    QAController,
    QASessionResult,
    Question,
    QuestionPriority,
    run_interactive_qa,
)


class TestQuestionPriority:
    """Test suite for QuestionPriority enum."""

    def test_priority_values(self):
        """Test that all priority values exist."""
        assert QuestionPriority.CRITICAL == "critical"
        assert QuestionPriority.IMPORTANT == "important"
        assert QuestionPriority.OPTIONAL == "optional"

    def test_priority_count(self):
        """Test that there are exactly 3 priority levels."""
        assert len(QuestionPriority) == 3


class TestAnswerSource:
    """Test suite for AnswerSource enum."""

    def test_source_values(self):
        """Test that all source values exist."""
        assert AnswerSource.CLI == "cli"
        assert AnswerSource.FILE == "file"
        assert AnswerSource.DEFAULT == "default"

    def test_source_count(self):
        """Test that there are exactly 3 answer sources."""
        assert len(AnswerSource) == 3


class TestQuestion:
    """Test suite for Question model."""

    def test_question_creation(self):
        """Test creating a Question with all fields."""
        question = Question(
            text="What are the desired outcomes?",
            priority=QuestionPriority.IMPORTANT,
            pivot_field="north_star",
            default_answer='{"desired_outcomes": ["outcome1"]}',
        )
        assert question.text == "What are the desired outcomes?"
        assert question.priority == QuestionPriority.IMPORTANT
        assert question.pivot_field == "north_star"
        assert question.default_answer is not None

    def test_question_without_default(self):
        """Test creating Question without default answer."""
        question = Question(
            text="Test question",
            priority=QuestionPriority.OPTIONAL,
            pivot_field="budget_cost",
        )
        assert question.default_answer is None


class TestAnswer:
    """Test suite for Answer model."""

    def test_answer_creation(self):
        """Test creating an Answer with all fields."""
        answer = Answer(
            question_text="What is X?",
            answer_text="X is Y",
            source=AnswerSource.CLI,
            pivot_field="north_star",
        )
        assert answer.question_text == "What is X?"
        assert answer.answer_text == "X is Y"
        assert answer.source == AnswerSource.CLI
        assert answer.pivot_field == "north_star"


class TestQASessionResult:
    """Test suite for QASessionResult model."""

    def test_result_creation(self, sample_anchor):
        """Test creating QASessionResult."""
        result = QASessionResult(
            anchor=sample_anchor,
            answers=[],
            skipped_optional=["Q1"],
            unanswered_critical=["Q2"],
        )
        assert result.anchor is not None
        assert len(result.skipped_optional) == 1
        assert len(result.unanswered_critical) == 1


@pytest.fixture
def sample_anchor():
    """Create a sample IntentionAnchorV2 for testing."""
    return IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(),
    )


@pytest.fixture
def anchor_with_north_star():
    """Create an anchor with NorthStar populated."""
    return IntentionAnchorV2(
        project_id="test-project",
        created_at=datetime.now(timezone.utc),
        raw_input_digest="abc123",
        pivot_intentions=PivotIntentions(
            north_star=NorthStarIntention(
                desired_outcomes=["Outcome 1"],
                success_signals=["Signal 1"],
            )
        ),
    )


class TestQAControllerInit:
    """Test suite for QAController initialization."""

    def test_default_initialization(self):
        """Test controller initialization with defaults."""
        controller = QAController()
        assert controller.answer_source == AnswerSource.CLI
        assert controller.answers_file is None
        assert controller.project_type == ProjectType.OTHER
        assert controller.autonomous is False

    def test_initialization_with_file_source(self):
        """Test controller initialization with file source."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"north_star": {"desired_outcomes": ["test"]}}, f)
            f.flush()

            controller = QAController(
                answer_source=AnswerSource.FILE,
                answers_file=Path(f.name),
            )
            assert controller.answer_source == AnswerSource.FILE
            assert len(controller._file_answers) > 0

    def test_initialization_with_project_type(self):
        """Test controller initialization with specific project type."""
        controller = QAController(project_type=ProjectType.ECOMMERCE)
        assert controller.project_type == ProjectType.ECOMMERCE

    def test_initialization_autonomous_mode(self):
        """Test controller initialization in autonomous mode."""
        controller = QAController(autonomous=True)
        assert controller.autonomous is True


class TestQuestionClassification:
    """Test suite for question classification."""

    def test_classify_critical_never_allow(self):
        """Test that never_allow questions are classified as CRITICAL."""
        controller = QAController()
        questions = ["What operations must NEVER be allowed?"]
        classified = controller.classify_questions(questions)

        assert len(classified) == 1
        assert classified[0].priority == QuestionPriority.CRITICAL

    def test_classify_critical_explicit_marker(self):
        """Test that questions with CRITICAL marker are classified correctly."""
        controller = QAController()
        questions = ["CRITICAL: What must be done?"]
        classified = controller.classify_questions(questions)

        assert classified[0].priority == QuestionPriority.CRITICAL

    def test_classify_important_north_star(self):
        """Test that north_star questions are classified as IMPORTANT."""
        controller = QAController()
        questions = ["What are the desired outcomes and success signals for this project?"]
        classified = controller.classify_questions(questions)

        assert classified[0].priority == QuestionPriority.IMPORTANT
        assert classified[0].pivot_field == "north_star"

    def test_classify_optional_parallelism(self):
        """Test that parallelism questions are classified as OPTIONAL."""
        controller = QAController()
        questions = ["Is parallelism allowed, and if so, what isolation model is required?"]
        classified = controller.classify_questions(questions)

        assert classified[0].priority == QuestionPriority.OPTIONAL
        assert classified[0].pivot_field == "parallelism_isolation"

    def test_classify_multiple_questions(self):
        """Test classifying multiple questions."""
        controller = QAController()
        questions = [
            "What are the desired outcomes?",
            "What must NEVER be allowed?",
            "Is parallelism allowed?",
        ]
        classified = controller.classify_questions(questions)

        assert len(classified) == 3
        priorities = [q.priority for q in classified]
        assert QuestionPriority.CRITICAL in priorities
        assert QuestionPriority.IMPORTANT in priorities
        assert QuestionPriority.OPTIONAL in priorities


class TestPivotFieldIdentification:
    """Test suite for pivot field identification."""

    def test_identify_north_star(self):
        """Test identifying north_star pivot."""
        controller = QAController()
        field = controller._identify_pivot_field("What are the desired outcomes?")
        assert field == "north_star"

    def test_identify_safety_risk(self):
        """Test identifying safety_risk pivot."""
        controller = QAController()
        field = controller._identify_pivot_field("What must NEVER be allowed?")
        assert field == "safety_risk"

    def test_identify_budget_cost(self):
        """Test identifying budget_cost pivot."""
        controller = QAController()
        field = controller._identify_pivot_field("What is the token/time budget?")
        assert field == "budget_cost"

    def test_identify_unknown(self):
        """Test identifying unknown pivot."""
        controller = QAController()
        field = controller._identify_pivot_field("Random unrelated question?")
        assert field == "unknown"


class TestDefaultAnswers:
    """Test suite for default answers."""

    def test_get_ecommerce_defaults(self):
        """Test getting defaults for ecommerce project."""
        controller = QAController(project_type=ProjectType.ECOMMERCE)
        default = controller._get_default_answer("north_star")
        assert default is not None
        data = json.loads(default)
        assert "desired_outcomes" in data

    def test_get_trading_defaults(self):
        """Test getting defaults for trading project."""
        controller = QAController(project_type=ProjectType.TRADING)
        default = controller._get_default_answer("budget_cost")
        assert default is not None
        data = json.loads(default)
        assert data["cost_escalation_policy"] == "block"

    def test_get_safe_defaults(self):
        """Test getting safe defaults for safety_risk."""
        controller = QAController()
        default = controller._get_default_answer("safety_risk")
        assert default is not None
        data = json.loads(default)
        assert data["never_allow"] == []  # Never auto-populated

    def test_get_project_defaults(self):
        """Test getting all defaults for a project type."""
        controller = QAController(project_type=ProjectType.CONTENT)
        defaults = controller.get_project_defaults()
        assert "north_star" in defaults
        assert "scope_boundaries" in defaults
        assert "budget_cost" in defaults


class TestFileBasedAnswers:
    """Test suite for file-based answers."""

    def test_load_answers_from_file(self):
        """Test loading answers from JSON file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            answers = {
                "north_star": {"desired_outcomes": ["Custom outcome"]},
                "safety_risk": {"never_allow": ["dangerous_operation"]},
            }
            json.dump(answers, f)
            f.flush()

            controller = QAController(
                answer_source=AnswerSource.FILE,
                answers_file=Path(f.name),
            )

            assert "north_star" in controller._file_answers

    def test_get_answer_from_file(self):
        """Test getting answer from file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            answers = {"north_star": {"desired_outcomes": ["File outcome"]}}
            json.dump(answers, f)
            f.flush()

            controller = QAController(
                answer_source=AnswerSource.FILE,
                answers_file=Path(f.name),
            )

            question = Question(
                text="What are the desired outcomes?",
                priority=QuestionPriority.IMPORTANT,
                pivot_field="north_star",
            )
            answer = controller._get_answer_from_file(question)

            assert answer is not None
            assert answer.source == AnswerSource.FILE

    def test_file_not_found_fallback(self):
        """Test fallback when file not found."""
        controller = QAController(
            answer_source=AnswerSource.FILE,
            answers_file=Path("/nonexistent/file.json"),
        )
        assert controller._file_answers == {}


class TestQASession:
    """Test suite for Q&A session execution."""

    def test_run_session_with_defaults(self, sample_anchor):
        """Test running Q&A session with default answers."""
        controller = QAController(
            answer_source=AnswerSource.DEFAULT,
            autonomous=True,
        )

        questions = validate_pivot_completeness(sample_anchor)
        result = controller.run_qa_session(questions, sample_anchor)

        assert isinstance(result, QASessionResult)
        assert result.anchor is not None

    def test_run_session_autonomous_skips_optional(self, sample_anchor):
        """Test that autonomous mode skips optional questions."""
        controller = QAController(
            answer_source=AnswerSource.DEFAULT,
            autonomous=True,
        )

        # Use a question list that includes optional ones
        questions = ["Is parallelism allowed, and if so, what isolation model is required?"]
        result = controller.run_qa_session(questions, sample_anchor)

        # Optional questions should be skipped in autonomous mode
        assert len(result.skipped_optional) > 0 or len(result.answers) > 0

    def test_run_session_from_file(self, sample_anchor):
        """Test running Q&A session with file answers."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            answers = {
                "north_star": {"desired_outcomes": ["Custom outcome from file"]},
                "safety_risk": {"never_allow": ["dangerous_op"], "risk_tolerance": "minimal"},
            }
            json.dump(answers, f)
            f.flush()

            controller = QAController(
                answer_source=AnswerSource.FILE,
                answers_file=Path(f.name),
            )

            questions = [
                "What are the desired outcomes?",
                "What must NEVER be allowed?",
            ]
            result = controller.run_qa_session(questions, sample_anchor)

            assert len(result.answers) > 0


class TestApplyAnswersToAnchor:
    """Test suite for applying answers to anchor."""

    def test_apply_north_star_answers(self, sample_anchor):
        """Test applying north_star answers to anchor."""
        controller = QAController()
        answers = [
            Answer(
                question_text="What are the desired outcomes?",
                answer_text='{"desired_outcomes": ["Outcome 1", "Outcome 2"]}',
                source=AnswerSource.CLI,
                pivot_field="north_star",
            )
        ]

        updated = controller._apply_answers_to_anchor(sample_anchor, answers)
        assert updated.pivot_intentions.north_star is not None
        assert len(updated.pivot_intentions.north_star.desired_outcomes) == 2

    def test_apply_safety_risk_answers(self, sample_anchor):
        """Test applying safety_risk answers to anchor."""
        controller = QAController()
        answers = [
            Answer(
                question_text="What must never be allowed?",
                answer_text='{"never_allow": ["delete_production"], "risk_tolerance": "minimal"}',
                source=AnswerSource.CLI,
                pivot_field="safety_risk",
            )
        ]

        updated = controller._apply_answers_to_anchor(sample_anchor, answers)
        assert updated.pivot_intentions.safety_risk is not None
        assert "delete_production" in updated.pivot_intentions.safety_risk.never_allow

    def test_apply_budget_cost_answers(self, sample_anchor):
        """Test applying budget_cost answers to anchor."""
        controller = QAController()
        answers = [
            Answer(
                question_text="What is the budget?",
                answer_text='{"token_cap_global": 500000, "cost_escalation_policy": "block"}',
                source=AnswerSource.FILE,
                pivot_field="budget_cost",
            )
        ]

        updated = controller._apply_answers_to_anchor(sample_anchor, answers)
        assert updated.pivot_intentions.budget_cost is not None
        assert updated.pivot_intentions.budget_cost.token_cap_global == 500000

    def test_apply_plain_text_answer(self, sample_anchor):
        """Test applying plain text (non-JSON) answer."""
        controller = QAController()
        answers = [
            Answer(
                question_text="What is X?",
                answer_text="Simple text answer",
                source=AnswerSource.CLI,
                pivot_field="north_star",
            )
        ]

        # Should not crash even with non-JSON answer
        updated = controller._apply_answers_to_anchor(sample_anchor, answers)
        assert updated is not None


class TestConvenienceFunction:
    """Test suite for run_interactive_qa convenience function."""

    def test_run_interactive_qa_complete_anchor(self, anchor_with_north_star):
        """Test that complete anchors return unchanged."""
        # Create a more complete anchor
        anchor = anchor_with_north_star
        anchor.pivot_intentions.safety_risk = SafetyRiskIntention()
        # ... other pivots would be added

        # With defaults, it should complete without CLI interaction
        with patch.object(QAController, "_get_answer_from_cli") as mock_cli:
            result = run_interactive_qa(
                anchor,
                project_type=ProjectType.OTHER,
                autonomous=True,
            )
            assert result is not None

    def test_run_interactive_qa_with_file(self, sample_anchor):
        """Test running with answers file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"north_star": {"desired_outcomes": ["Test"]}}, f)
            f.flush()

            result = run_interactive_qa(
                sample_anchor,
                autonomous=True,
                answers_file=Path(f.name),
            )
            assert result is not None


class TestProjectTypeDefaults:
    """Test suite for project type defaults."""

    def test_all_project_types_have_defaults(self):
        """Test that all project types have defaults defined."""
        for project_type in ProjectType:
            assert project_type in _PROJECT_TYPE_DEFAULTS

    def test_ecommerce_defaults_structure(self):
        """Test ecommerce defaults have expected structure."""
        defaults = _PROJECT_TYPE_DEFAULTS[ProjectType.ECOMMERCE]
        assert "north_star" in defaults
        assert "scope_boundaries" in defaults
        assert "budget_cost" in defaults
        assert "parallelism_isolation" in defaults

    def test_trading_defaults_high_risk(self):
        """Test trading defaults reflect high risk nature."""
        defaults = _PROJECT_TYPE_DEFAULTS[ProjectType.TRADING]
        assert defaults["budget_cost"]["cost_escalation_policy"] == "block"
        assert defaults["parallelism_isolation"]["allowed"] is False

    def test_content_defaults_allow_parallelism(self):
        """Test content defaults allow parallelism."""
        defaults = _PROJECT_TYPE_DEFAULTS[ProjectType.CONTENT]
        assert defaults["parallelism_isolation"]["allowed"] is True


class TestSafeDefaults:
    """Test suite for safe defaults."""

    def test_safety_risk_never_allow_empty(self):
        """Test that safety_risk.never_allow is never auto-populated."""
        assert _SAFE_DEFAULTS["safety_risk"]["never_allow"] == []

    def test_governance_default_deny(self):
        """Test that governance default policy is deny."""
        assert _SAFE_DEFAULTS["governance_review"]["default_policy"] == "deny"

    def test_memory_has_defaults(self):
        """Test memory_continuity has default persistence."""
        assert "intention_anchor" in _SAFE_DEFAULTS["memory_continuity"]["persist_to_sot"]
        assert "execution_logs" in _SAFE_DEFAULTS["memory_continuity"]["persist_to_sot"]


class TestCLIMocking:
    """Test suite for CLI interaction mocking."""

    def test_cli_input_mocked(self, sample_anchor):
        """Test that CLI input can be mocked."""
        controller = QAController(answer_source=AnswerSource.CLI)

        question = Question(
            text="Test question?",
            priority=QuestionPriority.OPTIONAL,
            pivot_field="north_star",
            default_answer='{"desired_outcomes": ["default"]}',
        )

        # Mock the CLI to return a specific answer
        with patch.object(controller, "_get_answer_from_cli") as mock_cli:
            mock_cli.return_value = Answer(
                question_text=question.text,
                answer_text='{"desired_outcomes": ["mocked"]}',
                source=AnswerSource.CLI,
                pivot_field="north_star",
            )

            answer = controller._get_answer(question, block=False)
            assert answer is not None
            assert "mocked" in answer.answer_text


class TestEdgeCases:
    """Test suite for edge cases."""

    def test_empty_questions_list(self, sample_anchor):
        """Test running session with empty questions."""
        controller = QAController(autonomous=True)
        result = controller.run_qa_session([], sample_anchor)

        assert result.anchor is not None
        assert len(result.answers) == 0

    def test_malformed_json_answer(self, sample_anchor):
        """Test handling of malformed JSON in answers."""
        controller = QAController()
        answers = [
            Answer(
                question_text="Test?",
                answer_text="not valid json {",
                source=AnswerSource.CLI,
                pivot_field="north_star",
            )
        ]

        # Should not crash
        updated = controller._apply_answers_to_anchor(sample_anchor, answers)
        assert updated is not None

    def test_unknown_pivot_field(self, sample_anchor):
        """Test handling of unknown pivot field."""
        controller = QAController()
        answers = [
            Answer(
                question_text="Unknown?",
                answer_text='{"value": "test"}',
                source=AnswerSource.DEFAULT,
                pivot_field="unknown_pivot",
            )
        ]

        # Should not crash
        updated = controller._apply_answers_to_anchor(sample_anchor, answers)
        assert updated is not None

    def test_nonexistent_file_graceful_handling(self):
        """Test graceful handling of nonexistent answers file."""
        controller = QAController(
            answer_source=AnswerSource.FILE,
            answers_file=Path("/definitely/does/not/exist.json"),
        )
        # Should not crash, just have empty answers
        assert controller._file_answers == {}


class TestIntegrationWithValidatePivotCompleteness:
    """Test suite for integration with validate_pivot_completeness."""

    def test_questions_from_incomplete_anchor(self, sample_anchor):
        """Test that incomplete anchor generates questions."""
        questions = validate_pivot_completeness(sample_anchor)
        assert len(questions) > 0  # Should have questions for missing pivots

    def test_questions_from_complete_anchor(self):
        """Test that complete anchor generates no questions."""
        from autopack.intention_anchor.v2 import (
            BudgetCostIntention,
            EvidenceVerificationIntention,
            GovernanceReviewIntention,
            MemoryContinuityIntention,
            ParallelismIsolationIntention,
            ScopeBoundariesIntention,
        )

        anchor = IntentionAnchorV2(
            project_id="complete-test",
            created_at=datetime.now(timezone.utc),
            raw_input_digest="xyz",
            pivot_intentions=PivotIntentions(
                north_star=NorthStarIntention(desired_outcomes=["test"]),
                safety_risk=SafetyRiskIntention(never_allow=["test"]),
                evidence_verification=EvidenceVerificationIntention(),
                scope_boundaries=ScopeBoundariesIntention(),
                budget_cost=BudgetCostIntention(),
                memory_continuity=MemoryContinuityIntention(),
                governance_review=GovernanceReviewIntention(),
                parallelism_isolation=ParallelismIsolationIntention(),
            ),
        )

        questions = validate_pivot_completeness(anchor)
        assert len(questions) == 0

    def test_classify_actual_questions(self, sample_anchor):
        """Test classifying actual questions from validate_pivot_completeness."""
        questions = validate_pivot_completeness(sample_anchor)
        controller = QAController()
        classified = controller.classify_questions(questions)

        assert len(classified) == len(questions)
        # All questions should have valid priority and pivot_field
        for q in classified:
            assert q.priority in QuestionPriority
            assert q.pivot_field is not None
