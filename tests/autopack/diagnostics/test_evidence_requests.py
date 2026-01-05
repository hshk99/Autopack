"""Tests for Evidence Request System.

Tests the compact evidence request mechanism that allows Autopack to request
missing evidence from humans without token blowups.
"""

import json
import pytest
from autopack.diagnostics.evidence_requests import (
    EvidenceRequest,
    EvidenceRequestType,
    format_evidence_request,
    format_multiple_requests,
    create_clarification_request,
    create_decision_request,
    create_example_request,
    save_evidence_requests,
    load_evidence_requests,
)


class TestEvidenceRequest:
    """Tests for EvidenceRequest dataclass."""

    def test_create_basic_request(self):
        """Test creating a basic evidence request."""
        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.CLARIFICATION,
            question="Should we use async?",
            context="Implementing database layer",
        )

        assert request.phase_id == "test-phase"
        assert request.request_type == EvidenceRequestType.CLARIFICATION
        assert request.question == "Should we use async?"
        assert request.context == "Implementing database layer"
        assert request.blocking is True
        assert request.options is None

    def test_create_request_with_options(self):
        """Test creating request with multiple options."""
        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.DECISION,
            question="Which API style?",
            context="Choosing API design",
            options=["REST", "GraphQL", "gRPC"],
            blocking=True,
        )

        assert request.options == ["REST", "GraphQL", "gRPC"]
        assert len(request.options) == 3

    def test_non_blocking_request(self):
        """Test creating non-blocking request."""
        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.EXAMPLE,
            question="Example input format?",
            context="Need sample data",
            blocking=False,
        )

        assert request.blocking is False

    def test_to_dict(self):
        """Test serialization to dictionary."""
        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.VALIDATION,
            question="Is this approach correct?",
            context="Before implementing",
            options=["Yes", "No", "Modify"],
            blocking=True,
        )

        data = request.to_dict()

        assert data["phase_id"] == "test-phase"
        assert data["request_type"] == "validation"
        assert data["question"] == "Is this approach correct?"
        assert data["context"] == "Before implementing"
        assert data["options"] == ["Yes", "No", "Modify"]
        assert data["blocking"] is True

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "phase_id": "test-phase",
            "request_type": "clarification",
            "question": "Test question?",
            "context": "Test context",
            "options": None,
            "blocking": True,
        }

        request = EvidenceRequest.from_dict(data)

        assert request.phase_id == "test-phase"
        assert request.request_type == EvidenceRequestType.CLARIFICATION
        assert request.question == "Test question?"
        assert request.context == "Test context"
        assert request.options is None
        assert request.blocking is True

    def test_round_trip_serialization(self):
        """Test that serialization round-trips correctly."""
        original = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.DECISION,
            question="Which option?",
            context="Need decision",
            options=["A", "B", "C"],
            blocking=False,
        )

        data = original.to_dict()
        restored = EvidenceRequest.from_dict(data)

        assert restored.phase_id == original.phase_id
        assert restored.request_type == original.request_type
        assert restored.question == original.question
        assert restored.context == original.context
        assert restored.options == original.options
        assert restored.blocking == original.blocking


class TestFormatEvidenceRequest:
    """Tests for formatting evidence requests."""

    def test_format_basic_request(self):
        """Test formatting a basic request."""
        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.CLARIFICATION,
            question="Should we use async?",
            context="Implementing database layer",
        )

        formatted = format_evidence_request(request)

        assert "🔍 EVIDENCE REQUEST [test-phase]" in formatted
        assert "Type: clarification" in formatted
        assert "Question: Should we use async?" in formatted
        assert "Context: Implementing database layer" in formatted
        assert "⏸️ BLOCKING" in formatted

    def test_format_request_with_options(self):
        """Test formatting request with options."""
        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.DECISION,
            question="Which API?",
            context="Choosing design",
            options=["REST", "GraphQL", "gRPC"],
        )

        formatted = format_evidence_request(request)

        assert "Options:" in formatted
        assert "1. REST" in formatted
        assert "2. GraphQL" in formatted
        assert "3. gRPC" in formatted

    def test_format_non_blocking_request(self):
        """Test formatting non-blocking request."""
        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.EXAMPLE,
            question="Example format?",
            context="Need sample",
            blocking=False,
        )

        formatted = format_evidence_request(request)

        assert "⚠️ NON-BLOCKING" in formatted
        assert "best guess" in formatted

    def test_format_is_compact(self):
        """Test that formatted output is reasonably compact."""
        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.CLARIFICATION,
            question="Short question?",
            context="Brief context",
        )

        formatted = format_evidence_request(request)

        # Should be under 200 characters for basic request
        assert len(formatted) < 200

    def test_format_multiple_requests_empty(self):
        """Test formatting empty request list."""
        formatted = format_multiple_requests([])
        assert formatted == ""

    def test_format_multiple_requests_single(self):
        """Test formatting single request in list."""
        requests = [
            EvidenceRequest(
                phase_id="test-phase",
                request_type=EvidenceRequestType.CLARIFICATION,
                question="Question?",
                context="Context",
            )
        ]

        formatted = format_multiple_requests(requests)

        assert "📋 EVIDENCE REQUESTS" in formatted
        assert "[Request 1/1]" in formatted
        assert "autopack respond" in formatted

    def test_format_multiple_requests_many(self):
        """Test formatting multiple requests."""
        requests = [
            EvidenceRequest(
                phase_id="phase-1",
                request_type=EvidenceRequestType.CLARIFICATION,
                question="Question 1?",
                context="Context 1",
            ),
            EvidenceRequest(
                phase_id="phase-2",
                request_type=EvidenceRequestType.DECISION,
                question="Question 2?",
                context="Context 2",
                options=["A", "B"],
            ),
            EvidenceRequest(
                phase_id="phase-3",
                request_type=EvidenceRequestType.EXAMPLE,
                question="Question 3?",
                context="Context 3",
            ),
        ]

        formatted = format_multiple_requests(requests)

        assert "[Request 1/3]" in formatted
        assert "[Request 2/3]" in formatted
        assert "[Request 3/3]" in formatted
        assert "phase-1" in formatted
        assert "phase-2" in formatted
        assert "phase-3" in formatted


class TestConvenienceFunctions:
    """Tests for convenience request creation functions."""

    def test_create_clarification_request(self):
        """Test creating clarification request."""
        request = create_clarification_request(
            phase_id="test-phase", question="Need clarification?", context="Unclear requirement"
        )

        assert request.phase_id == "test-phase"
        assert request.request_type == EvidenceRequestType.CLARIFICATION
        assert request.question == "Need clarification?"
        assert request.context == "Unclear requirement"
        assert request.blocking is True

    def test_create_clarification_request_non_blocking(self):
        """Test creating non-blocking clarification request."""
        request = create_clarification_request(
            phase_id="test-phase",
            question="Optional clarification?",
            context="Would help but not critical",
            blocking=False,
        )

        assert request.blocking is False

    def test_create_decision_request(self):
        """Test creating decision request."""
        request = create_decision_request(
            phase_id="test-phase",
            question="Which approach?",
            options=["Approach A", "Approach B", "Approach C"],
            context="Multiple valid options",
        )

        assert request.phase_id == "test-phase"
        assert request.request_type == EvidenceRequestType.DECISION
        assert request.question == "Which approach?"
        assert request.options == ["Approach A", "Approach B", "Approach C"]
        assert request.context == "Multiple valid options"
        assert request.blocking is True

    def test_create_example_request(self):
        """Test creating example request."""
        request = create_example_request(
            phase_id="test-phase",
            question="Example input format?",
            context="Need sample data structure",
        )

        assert request.phase_id == "test-phase"
        assert request.request_type == EvidenceRequestType.EXAMPLE
        assert request.question == "Example input format?"
        assert request.context == "Need sample data structure"
        assert request.blocking is False  # Examples default to non-blocking

    def test_create_example_request_blocking(self):
        """Test creating blocking example request."""
        request = create_example_request(
            phase_id="test-phase",
            question="Critical example needed?",
            context="Cannot proceed without example",
            blocking=True,
        )

        assert request.blocking is True


class TestPersistence:
    """Tests for saving and loading evidence requests."""

    def test_save_and_load_single_request(self, tmp_path):
        """Test saving and loading a single request."""
        filepath = tmp_path / "request.json"

        original = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.CLARIFICATION,
            question="Test question?",
            context="Test context",
        )

        save_evidence_requests([original], str(filepath))
        loaded = load_evidence_requests(str(filepath))

        assert len(loaded) == 1
        assert loaded[0].phase_id == original.phase_id
        assert loaded[0].request_type == original.request_type
        assert loaded[0].question == original.question
        assert loaded[0].context == original.context

    def test_save_and_load_multiple_requests(self, tmp_path):
        """Test saving and loading multiple requests."""
        filepath = tmp_path / "requests.json"

        originals = [
            EvidenceRequest(
                phase_id="phase-1",
                request_type=EvidenceRequestType.CLARIFICATION,
                question="Question 1?",
                context="Context 1",
            ),
            EvidenceRequest(
                phase_id="phase-2",
                request_type=EvidenceRequestType.DECISION,
                question="Question 2?",
                context="Context 2",
                options=["A", "B", "C"],
            ),
            EvidenceRequest(
                phase_id="phase-3",
                request_type=EvidenceRequestType.EXAMPLE,
                question="Question 3?",
                context="Context 3",
                blocking=False,
            ),
        ]

        save_evidence_requests(originals, str(filepath))
        loaded = load_evidence_requests(str(filepath))

        assert len(loaded) == 3

        for original, restored in zip(originals, loaded):
            assert restored.phase_id == original.phase_id
            assert restored.request_type == original.request_type
            assert restored.question == original.question
            assert restored.context == original.context
            assert restored.options == original.options
            assert restored.blocking == original.blocking

    def test_save_creates_valid_json(self, tmp_path):
        """Test that saved file is valid JSON."""
        filepath = tmp_path / "request.json"

        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.VALIDATION,
            question="Valid approach?",
            context="Need validation",
        )

        save_evidence_requests([request], str(filepath))

        # Should be able to parse as JSON
        with open(filepath) as f:
            data = json.load(f)

        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["phase_id"] == "test-phase"

    def test_load_empty_list(self, tmp_path):
        """Test loading empty request list."""
        filepath = tmp_path / "empty.json"

        save_evidence_requests([], str(filepath))
        loaded = load_evidence_requests(str(filepath))

        assert loaded == []


class TestEvidenceRequestTypes:
    """Tests for EvidenceRequestType enum."""

    def test_all_types_have_values(self):
        """Test that all request types have string values."""
        assert EvidenceRequestType.CLARIFICATION.value == "clarification"
        assert EvidenceRequestType.EXAMPLE.value == "example"
        assert EvidenceRequestType.CONTEXT.value == "context"
        assert EvidenceRequestType.VALIDATION.value == "validation"
        assert EvidenceRequestType.DECISION.value == "decision"

    def test_can_create_from_string(self):
        """Test creating enum from string value."""
        request_type = EvidenceRequestType("clarification")
        assert request_type == EvidenceRequestType.CLARIFICATION

    def test_invalid_type_raises_error(self):
        """Test that invalid type string raises error."""
        with pytest.raises(ValueError):
            EvidenceRequestType("invalid_type")


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_empty_question(self):
        """Test request with empty question."""
        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.CLARIFICATION,
            question="",
            context="Some context",
        )

        assert request.question == ""
        formatted = format_evidence_request(request)
        assert "Question:" in formatted

    def test_empty_context(self):
        """Test request with empty context."""
        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.CLARIFICATION,
            question="Some question?",
            context="",
        )

        assert request.context == ""
        formatted = format_evidence_request(request)
        assert "Context:" in formatted

    def test_very_long_question(self):
        """Test request with very long question."""
        long_question = "Should we " + "really " * 100 + "do this?"

        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.CLARIFICATION,
            question=long_question,
            context="Context",
        )

        assert request.question == long_question
        formatted = format_evidence_request(request)
        assert long_question in formatted

    def test_special_characters_in_text(self):
        """Test request with special characters."""
        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.CLARIFICATION,
            question="Should we use <tag> & 'quotes' and \"escapes\"?",
            context="Context with €, £, ¥ symbols",
        )

        formatted = format_evidence_request(request)
        assert "<tag>" in formatted
        assert "&" in formatted
        assert "'quotes'" in formatted

    def test_empty_options_list(self):
        """Test decision request with empty options list."""
        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.DECISION,
            question="Which option?",
            context="Context",
            options=[],
        )

        formatted = format_evidence_request(request)
        # Should still format without error
        assert "Options:" in formatted

    def test_single_option(self):
        """Test decision request with single option."""
        request = EvidenceRequest(
            phase_id="test-phase",
            request_type=EvidenceRequestType.DECISION,
            question="Confirm?",
            context="Context",
            options=["Yes"],
        )

        formatted = format_evidence_request(request)
        assert "1. Yes" in formatted
