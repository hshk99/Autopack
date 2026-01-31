"""QAController - Wire validate_pivot_completeness to User Interaction.

Provides interactive Q&A flow for clarifying pivot intentions based on
questions generated from validate_pivot_completeness().

Supports:
- CLI-based interactive Q&A using rich
- File-based answers for automation
- Sensible defaults per project type
- Priority classification (critical/important/optional)
"""

from __future__ import annotations

import json
import logging
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..intention_anchor.v2 import (BudgetCostIntention,
                                   EvidenceVerificationIntention,
                                   GovernanceReviewIntention,
                                   IntentionAnchorV2,
                                   MemoryContinuityIntention,
                                   NorthStarIntention,
                                   ParallelismIsolationIntention,
                                   SafetyRiskIntention,
                                   ScopeBoundariesIntention,
                                   validate_pivot_completeness)
from .idea_parser import ProjectType

logger = logging.getLogger(__name__)


class QuestionPriority(str, Enum):
    """Priority classification for questions."""

    CRITICAL = "critical"
    IMPORTANT = "important"
    OPTIONAL = "optional"


class AnswerSource(str, Enum):
    """Source of answers for Q&A session."""

    CLI = "cli"
    FILE = "file"
    DEFAULT = "default"


class Question(BaseModel):
    """Question model with priority and pivot field association."""

    text: str = Field(..., description="The question text")
    priority: QuestionPriority = Field(..., description="Priority classification")
    pivot_field: str = Field(..., description="Associated pivot field name")
    default_answer: Optional[str] = Field(default=None, description="Default answer if available")


class Answer(BaseModel):
    """Answer to a question."""

    question_text: str = Field(..., description="Original question text")
    answer_text: str = Field(..., description="The answer provided")
    source: AnswerSource = Field(..., description="Source of the answer")
    pivot_field: str = Field(..., description="Associated pivot field")


class QASessionResult(BaseModel):
    """Result of a Q&A session."""

    anchor: IntentionAnchorV2 = Field(..., description="Updated anchor")
    answers: list[Answer] = Field(default_factory=list, description="Collected answers")
    skipped_optional: list[str] = Field(
        default_factory=list, description="Optional questions skipped with defaults"
    )
    unanswered_critical: list[str] = Field(
        default_factory=list, description="Critical questions that remain unanswered"
    )


# Question patterns to pivot field mapping
_QUESTION_TO_PIVOT: dict[str, str] = {
    "desired outcomes": "north_star",
    "success signals": "north_star",
    "never be allowed": "safety_risk",
    "NEVER": "safety_risk",
    "requires approval": "safety_risk",
    "risk tolerance": "safety_risk",
    "hard blocks": "evidence_verification",
    "proof artifacts": "evidence_verification",
    "verification gates": "evidence_verification",
    "paths are allowed": "scope_boundaries",
    "protected": "scope_boundaries",
    "network": "scope_boundaries",
    "token/time": "budget_cost",
    "budget": "budget_cost",
    "cost": "budget_cost",
    "persist to SOT": "memory_continuity",
    "retention": "memory_continuity",
    "derived indexes": "memory_continuity",
    "approval policy": "governance_review",
    "auto-approval": "governance_review",
    "parallelism": "parallelism_isolation",
    "isolation": "parallelism_isolation",
    "concurrent": "parallelism_isolation",
}

# Default answers per project type
_PROJECT_TYPE_DEFAULTS: dict[ProjectType, dict[str, dict[str, Any]]] = {
    ProjectType.ECOMMERCE: {
        "north_star": {
            "desired_outcomes": ["Secure online transactions", "User-friendly checkout"],
            "success_signals": ["Order completion rate > 80%", "Payment success rate > 95%"],
            "non_goals": ["Social media integration"],
        },
        "scope_boundaries": {
            "allowed_write_roots": ["./src", "./data"],
            "protected_paths": [".git", ".env", "credentials", "secrets"],
            "network_allowlist": ["payment.gateway.com", "api.shipping.com"],
        },
        "budget_cost": {
            "token_cap_global": 500000,
            "time_cap_seconds": 7200,
            "cost_escalation_policy": "request_approval",
        },
        "parallelism_isolation": {
            "allowed": False,
            "isolation_model": "none",
            "max_concurrent_runs": 1,
        },
    },
    ProjectType.TRADING: {
        "north_star": {
            "desired_outcomes": ["Automated trade execution", "Risk management"],
            "success_signals": ["Win rate tracking", "Max drawdown limits"],
            "non_goals": ["Manual trading interface"],
        },
        "scope_boundaries": {
            "allowed_write_roots": ["./src", "./logs"],
            "protected_paths": [".git", ".env", "credentials", "api_keys", "secrets"],
            "network_allowlist": [],  # Must be explicitly configured
        },
        "budget_cost": {
            "token_cap_global": 200000,
            "time_cap_seconds": 3600,
            "cost_escalation_policy": "block",  # High risk = block on cost
        },
        "parallelism_isolation": {
            "allowed": False,
            "isolation_model": "none",
            "max_concurrent_runs": 1,
        },
    },
    ProjectType.CONTENT: {
        "north_star": {
            "desired_outcomes": ["Content creation automation", "Publishing workflow"],
            "success_signals": ["Content quality score", "Publishing success rate"],
            "non_goals": ["Content moderation"],
        },
        "scope_boundaries": {
            "allowed_write_roots": ["./content", "./src", "./output"],
            "protected_paths": [".git", ".env"],
            "network_allowlist": ["api.cms.com", "cdn.content.com"],
        },
        "budget_cost": {
            "token_cap_global": 1000000,
            "time_cap_seconds": 14400,
            "cost_escalation_policy": "warn",
        },
        "parallelism_isolation": {
            "allowed": True,
            "isolation_model": "four_layer",
            "max_concurrent_runs": 4,
        },
    },
    ProjectType.AUTOMATION: {
        "north_star": {
            "desired_outcomes": ["Process automation", "Workflow efficiency"],
            "success_signals": ["Task completion rate", "Error rate < 5%"],
            "non_goals": ["Manual intervention points"],
        },
        "scope_boundaries": {
            "allowed_write_roots": ["./src", "./scripts", "./output"],
            "protected_paths": [".git", ".env", "credentials"],
            "network_allowlist": [],
        },
        "budget_cost": {
            "token_cap_global": 300000,
            "time_cap_seconds": 7200,
            "cost_escalation_policy": "request_approval",
        },
        "parallelism_isolation": {
            "allowed": True,
            "isolation_model": "four_layer",
            "max_concurrent_runs": 2,
        },
    },
    ProjectType.OTHER: {
        "north_star": {
            "desired_outcomes": [],
            "success_signals": [],
            "non_goals": [],
        },
        "scope_boundaries": {
            "allowed_write_roots": ["./src"],
            "protected_paths": [".git", ".env", "credentials", "secrets"],
            "network_allowlist": [],
        },
        "budget_cost": {
            "token_cap_global": 100000,
            "time_cap_seconds": 3600,
            "cost_escalation_policy": "request_approval",
        },
        "parallelism_isolation": {
            "allowed": False,
            "isolation_model": "none",
            "max_concurrent_runs": 1,
        },
    },
}

# Default values for pivots that require explicit user input (minimal safe defaults)
_SAFE_DEFAULTS: dict[str, dict[str, Any]] = {
    "safety_risk": {
        "never_allow": [],  # NEVER auto-populate - must come from user
        "requires_approval": ["file deletion", "network access", "credential access"],
        "risk_tolerance": "low",
    },
    "evidence_verification": {
        "hard_blocks": ["tests must pass"],
        "required_proofs": [],
        "verification_gates": ["linting", "type checking"],
    },
    "memory_continuity": {
        "persist_to_sot": ["intention_anchor", "execution_logs"],
        "derived_indexes": [],
        "retention_rules": {"execution_logs": "30_days", "intention_anchor": "permanent"},
    },
    "governance_review": {
        "default_policy": "deny",
        "auto_approve_rules": [],
        "approval_channels": ["cli"],
    },
}


class QAController:
    """Controller for interactive Q&A sessions.

    Wires validate_pivot_completeness() to user interaction, supporting
    CLI Q&A, file-based answers, and sensible defaults.
    """

    def __init__(
        self,
        answer_source: AnswerSource = AnswerSource.CLI,
        answers_file: Optional[Path] = None,
        project_type: ProjectType = ProjectType.OTHER,
        autonomous: bool = False,
    ):
        """Initialize the QAController.

        Args:
            answer_source: Source for answers (CLI, FILE, DEFAULT)
            answers_file: Path to file with pre-defined answers (for FILE source)
            project_type: Project type for default answers
            autonomous: If True, use defaults for optional questions without prompting
        """
        self.answer_source = answer_source
        self.answers_file = answers_file
        self.project_type = project_type
        self.autonomous = autonomous
        self._file_answers: dict[str, str] = {}

        if answer_source == AnswerSource.FILE and answers_file:
            self._load_file_answers()

    def _load_file_answers(self) -> None:
        """Load answers from file."""
        if not self.answers_file or not self.answers_file.exists():
            logger.warning(f"Answers file not found: {self.answers_file}")
            return

        try:
            content = self.answers_file.read_text(encoding="utf-8")
            self._file_answers = json.loads(content)
            logger.info(f"Loaded {len(self._file_answers)} answers from file")
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load answers file: {e}")

    def classify_questions(self, questions: list[str]) -> list[Question]:
        """Classify questions by priority and pivot field.

        Args:
            questions: List of question strings from validate_pivot_completeness()

        Returns:
            List of classified Question objects
        """
        classified: list[Question] = []

        for question_text in questions:
            pivot_field = self._identify_pivot_field(question_text)
            priority = self._determine_priority(question_text, pivot_field)
            default_answer = self._get_default_answer(pivot_field)

            classified.append(
                Question(
                    text=question_text,
                    priority=priority,
                    pivot_field=pivot_field,
                    default_answer=default_answer,
                )
            )

        return classified

    def _identify_pivot_field(self, question_text: str) -> str:
        """Identify which pivot field a question relates to.

        Args:
            question_text: The question text

        Returns:
            Pivot field name
        """
        for pattern, pivot in _QUESTION_TO_PIVOT.items():
            if pattern.lower() in question_text.lower():
                return pivot

        # Default to unknown
        return "unknown"

    def _determine_priority(self, question_text: str, pivot_field: str) -> QuestionPriority:
        """Determine the priority of a question.

        Args:
            question_text: The question text
            pivot_field: Associated pivot field

        Returns:
            QuestionPriority
        """
        # CRITICAL: never_allow questions (safety-critical)
        if "NEVER" in question_text or "never_allow" in question_text.lower():
            return QuestionPriority.CRITICAL

        # CRITICAL: Other explicitly marked critical questions
        if "CRITICAL" in question_text:
            return QuestionPriority.CRITICAL

        # IMPORTANT: Core pivots that significantly impact behavior
        if pivot_field in ["north_star", "safety_risk", "evidence_verification"]:
            return QuestionPriority.IMPORTANT

        # OPTIONAL: Less critical pivots with sensible defaults
        return QuestionPriority.OPTIONAL

    def _get_default_answer(self, pivot_field: str) -> Optional[str]:
        """Get default answer for a pivot field based on project type.

        Args:
            pivot_field: The pivot field name

        Returns:
            Default answer string or None
        """
        # Check project-type specific defaults
        type_defaults = _PROJECT_TYPE_DEFAULTS.get(self.project_type, {})
        if pivot_field in type_defaults:
            return json.dumps(type_defaults[pivot_field])

        # Fall back to safe defaults
        if pivot_field in _SAFE_DEFAULTS:
            return json.dumps(_SAFE_DEFAULTS[pivot_field])

        return None

    def run_qa_session(self, questions: list[str], anchor: IntentionAnchorV2) -> QASessionResult:
        """Run interactive Q&A session.

        Args:
            questions: List of question strings from validate_pivot_completeness()
            anchor: Current IntentionAnchorV2 to update

        Returns:
            QASessionResult with updated anchor and session info
        """
        logger.info(f"Starting Q&A session with {len(questions)} questions")

        # Classify questions
        classified = self.classify_questions(questions)

        # Separate by priority
        critical = [q for q in classified if q.priority == QuestionPriority.CRITICAL]
        important = [q for q in classified if q.priority == QuestionPriority.IMPORTANT]
        optional = [q for q in classified if q.priority == QuestionPriority.OPTIONAL]

        logger.info(
            f"Questions classified: {len(critical)} critical, "
            f"{len(important)} important, {len(optional)} optional"
        )

        answers: list[Answer] = []
        skipped_optional: list[str] = []
        unanswered_critical: list[str] = []

        # Process critical questions first (always block)
        for question in critical:
            answer = self._get_answer(question, block=True)
            if answer:
                answers.append(answer)
            else:
                unanswered_critical.append(question.text)

        # Process important questions
        for question in important:
            answer = self._get_answer(question, block=not self.autonomous)
            if answer:
                answers.append(answer)

        # Process optional questions (use defaults in autonomous mode)
        for question in optional:
            if self.autonomous and question.default_answer:
                # Use default
                answers.append(
                    Answer(
                        question_text=question.text,
                        answer_text=question.default_answer,
                        source=AnswerSource.DEFAULT,
                        pivot_field=question.pivot_field,
                    )
                )
                skipped_optional.append(question.text)
            else:
                answer = self._get_answer(question, block=False)
                if answer:
                    answers.append(answer)

        # Apply answers to anchor
        updated_anchor = self._apply_answers_to_anchor(anchor, answers)

        return QASessionResult(
            anchor=updated_anchor,
            answers=answers,
            skipped_optional=skipped_optional,
            unanswered_critical=unanswered_critical,
        )

    def _get_answer(self, question: Question, block: bool = True) -> Optional[Answer]:
        """Get answer for a question from configured source.

        Args:
            question: The question to answer
            block: If True, block until answer is provided (for critical questions)

        Returns:
            Answer or None if skipped
        """
        if self.answer_source == AnswerSource.FILE:
            return self._get_answer_from_file(question)
        elif self.answer_source == AnswerSource.DEFAULT:
            return self._get_answer_from_defaults(question)
        else:  # CLI
            return self._get_answer_from_cli(question, block)

    def _get_answer_from_file(self, question: Question) -> Optional[Answer]:
        """Get answer from pre-loaded answers file.

        Args:
            question: The question to answer

        Returns:
            Answer or None if not found
        """
        # Try to find answer by pivot field or question text
        answer_text = self._file_answers.get(question.pivot_field)
        if not answer_text:
            # Try matching question text
            for key, value in self._file_answers.items():
                if key.lower() in question.text.lower():
                    answer_text = value
                    break

        if answer_text:
            return Answer(
                question_text=question.text,
                answer_text=(
                    answer_text if isinstance(answer_text, str) else json.dumps(answer_text)
                ),
                source=AnswerSource.FILE,
                pivot_field=question.pivot_field,
            )

        # Fall back to default if available
        if question.default_answer:
            return Answer(
                question_text=question.text,
                answer_text=question.default_answer,
                source=AnswerSource.DEFAULT,
                pivot_field=question.pivot_field,
            )

        return None

    def _get_answer_from_defaults(self, question: Question) -> Optional[Answer]:
        """Get answer from defaults.

        Args:
            question: The question to answer

        Returns:
            Answer or None if no default available
        """
        if question.default_answer:
            return Answer(
                question_text=question.text,
                answer_text=question.default_answer,
                source=AnswerSource.DEFAULT,
                pivot_field=question.pivot_field,
            )
        return None

    def _get_answer_from_cli(self, question: Question, block: bool) -> Optional[Answer]:
        """Get answer interactively from CLI.

        Args:
            question: The question to answer
            block: If True, require an answer

        Returns:
            Answer or None if skipped
        """
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.text import Text

            console = Console()

            # Display question with priority indicator
            priority_colors = {
                QuestionPriority.CRITICAL: "red",
                QuestionPriority.IMPORTANT: "yellow",
                QuestionPriority.OPTIONAL: "blue",
            }
            color = priority_colors.get(question.priority, "white")

            # Build question display
            question_text = Text()
            question_text.append(f"[{question.priority.value.upper()}] ", style=f"bold {color}")
            question_text.append(question.text)

            console.print()
            console.print(
                Panel(
                    question_text,
                    title=f"[bold]Pivot: {question.pivot_field}[/bold]",
                    border_style=color,
                )
            )

            # Show default if available
            if question.default_answer:
                console.print(f"[dim]Default: {question.default_answer[:100]}...[/dim]")
                console.print("[dim]Press Enter to accept default, or type your answer.[/dim]")

            # Get input
            while True:
                prompt = "[bold]Your answer[/bold]"
                if not block and question.default_answer:
                    prompt += " [dim](or Enter to skip)[/dim]"
                prompt += ": "

                answer_text = console.input(prompt).strip()

                # Handle empty input
                if not answer_text:
                    if question.default_answer:
                        return Answer(
                            question_text=question.text,
                            answer_text=question.default_answer,
                            source=AnswerSource.DEFAULT,
                            pivot_field=question.pivot_field,
                        )
                    elif block:
                        console.print(
                            f"[{color}]This is a {question.priority.value} question. "
                            "An answer is required.[/{color}]"
                        )
                        continue
                    else:
                        return None

                return Answer(
                    question_text=question.text,
                    answer_text=answer_text,
                    source=AnswerSource.CLI,
                    pivot_field=question.pivot_field,
                )

        except ImportError:
            # Fallback to basic input if rich is not available
            logger.warning("rich not available, using basic input")
            return self._get_answer_basic_cli(question, block)

    def _get_answer_basic_cli(self, question: Question, block: bool) -> Optional[Answer]:
        """Basic CLI fallback without rich.

        Args:
            question: The question to answer
            block: If True, require an answer

        Returns:
            Answer or None if skipped
        """
        print(f"\n[{question.priority.value.upper()}] {question.text}")
        if question.default_answer:
            print(f"Default: {question.default_answer[:100]}...")

        while True:
            answer_text = input("Your answer: ").strip()

            if not answer_text:
                if question.default_answer:
                    return Answer(
                        question_text=question.text,
                        answer_text=question.default_answer,
                        source=AnswerSource.DEFAULT,
                        pivot_field=question.pivot_field,
                    )
                elif block:
                    print(f"This is a {question.priority.value} question. An answer is required.")
                    continue
                else:
                    return None

            return Answer(
                question_text=question.text,
                answer_text=answer_text,
                source=AnswerSource.CLI,
                pivot_field=question.pivot_field,
            )

    def _apply_answers_to_anchor(
        self, anchor: IntentionAnchorV2, answers: list[Answer]
    ) -> IntentionAnchorV2:
        """Apply collected answers to update the anchor.

        Args:
            anchor: Current anchor
            answers: Collected answers

        Returns:
            Updated IntentionAnchorV2
        """
        # Group answers by pivot field
        grouped: dict[str, list[Answer]] = {}
        for answer in answers:
            if answer.pivot_field not in grouped:
                grouped[answer.pivot_field] = []
            grouped[answer.pivot_field].append(answer)

        # Apply updates to each pivot
        pivot = anchor.pivot_intentions

        for pivot_field, field_answers in grouped.items():
            try:
                self._update_pivot(pivot, pivot_field, field_answers)
            except Exception as e:
                logger.warning(f"Failed to update pivot {pivot_field}: {e}")

        return anchor

    def _update_pivot(self, pivot_intentions: Any, pivot_field: str, answers: list[Answer]) -> None:
        """Update a specific pivot with answer data.

        Args:
            pivot_intentions: PivotIntentions object
            pivot_field: Field name to update
            answers: Answers for this field
        """
        # Merge all answers for this pivot
        merged_data: dict[str, Any] = {}
        for answer in answers:
            try:
                data = json.loads(answer.answer_text)
                if isinstance(data, dict):
                    merged_data.update(data)
                else:
                    # Single value - try to infer the key
                    merged_data["value"] = data
            except json.JSONDecodeError:
                # Plain text answer - store as value
                merged_data["value"] = answer.answer_text

        # Apply to the appropriate pivot
        if pivot_field == "north_star":
            if not pivot_intentions.north_star:
                pivot_intentions.north_star = NorthStarIntention()
            self._apply_dict_to_model(pivot_intentions.north_star, merged_data)

        elif pivot_field == "safety_risk":
            if not pivot_intentions.safety_risk:
                pivot_intentions.safety_risk = SafetyRiskIntention()
            self._apply_dict_to_model(pivot_intentions.safety_risk, merged_data)

        elif pivot_field == "evidence_verification":
            if not pivot_intentions.evidence_verification:
                pivot_intentions.evidence_verification = EvidenceVerificationIntention()
            self._apply_dict_to_model(pivot_intentions.evidence_verification, merged_data)

        elif pivot_field == "scope_boundaries":
            if not pivot_intentions.scope_boundaries:
                pivot_intentions.scope_boundaries = ScopeBoundariesIntention()
            self._apply_dict_to_model(pivot_intentions.scope_boundaries, merged_data)

        elif pivot_field == "budget_cost":
            if not pivot_intentions.budget_cost:
                pivot_intentions.budget_cost = BudgetCostIntention()
            self._apply_dict_to_model(pivot_intentions.budget_cost, merged_data)

        elif pivot_field == "memory_continuity":
            if not pivot_intentions.memory_continuity:
                pivot_intentions.memory_continuity = MemoryContinuityIntention()
            self._apply_dict_to_model(pivot_intentions.memory_continuity, merged_data)

        elif pivot_field == "governance_review":
            if not pivot_intentions.governance_review:
                pivot_intentions.governance_review = GovernanceReviewIntention()
            self._apply_dict_to_model(pivot_intentions.governance_review, merged_data)

        elif pivot_field == "parallelism_isolation":
            if not pivot_intentions.parallelism_isolation:
                pivot_intentions.parallelism_isolation = ParallelismIsolationIntention()
            self._apply_dict_to_model(pivot_intentions.parallelism_isolation, merged_data)

    def _apply_dict_to_model(self, model: BaseModel, data: dict[str, Any]) -> None:
        """Apply dictionary data to a Pydantic model.

        Args:
            model: Pydantic model instance
            data: Data to apply
        """
        for key, value in data.items():
            if hasattr(model, key):
                current = getattr(model, key)
                if isinstance(current, list) and isinstance(value, list):
                    # Extend lists
                    current.extend(v for v in value if v not in current)
                elif isinstance(current, dict) and isinstance(value, dict):
                    # Merge dicts
                    current.update(value)
                else:
                    # Replace value
                    setattr(model, key, value)

    def get_project_defaults(self) -> dict[str, dict[str, Any]]:
        """Get all defaults for the configured project type.

        Returns:
            Dictionary of defaults by pivot field
        """
        type_defaults = _PROJECT_TYPE_DEFAULTS.get(self.project_type, {}).copy()

        # Merge with safe defaults
        for field, values in _SAFE_DEFAULTS.items():
            if field not in type_defaults:
                type_defaults[field] = values

        return type_defaults


def run_interactive_qa(
    anchor: IntentionAnchorV2,
    project_type: ProjectType = ProjectType.OTHER,
    autonomous: bool = False,
    answers_file: Optional[Path] = None,
) -> IntentionAnchorV2:
    """Convenience function to run interactive Q&A for an anchor.

    Args:
        anchor: IntentionAnchorV2 to complete
        project_type: Project type for defaults
        autonomous: If True, use defaults for optional questions
        answers_file: Optional file with pre-defined answers

    Returns:
        Updated IntentionAnchorV2
    """
    # Get questions from validate_pivot_completeness
    questions = validate_pivot_completeness(anchor)

    if not questions:
        logger.info("No clarifying questions needed - anchor is complete")
        return anchor

    # Determine answer source
    if answers_file and answers_file.exists():
        source = AnswerSource.FILE
    elif autonomous:
        source = AnswerSource.DEFAULT
    else:
        source = AnswerSource.CLI

    # Run Q&A session
    controller = QAController(
        answer_source=source,
        answers_file=answers_file,
        project_type=project_type,
        autonomous=autonomous,
    )

    result = controller.run_qa_session(questions, anchor)

    if result.unanswered_critical:
        logger.warning(
            f"Q&A session completed with {len(result.unanswered_critical)} "
            "unanswered critical questions"
        )

    return result.anchor
