"""Tests for Human Response Parser.

Tests the compact mechanism for ingesting human responses to evidence requests
without token blowups.
"""

import json
from datetime import datetime

from autopack.diagnostics.human_response_parser import (
    HumanResponse, create_response_from_cli_args, extract_choice_number,
    format_response_for_context, format_response_summary,
    inject_response_into_context, load_human_response, parse_human_response,
    save_human_response, validate_response_for_decision)


class TestHumanResponse:
    """Tests for HumanResponse dataclass."""

    def test_create_basic_response(self):
        """Test creating a basic human response."""
        timestamp = datetime.utcnow()
        response = HumanResponse(
            phase_id="test-phase", response_text="Yes, use async API", timestamp=timestamp
        )

        assert response.phase_id == "test-phase"
        assert response.response_text == "Yes, use async API"
        assert response.timestamp == timestamp
        assert response.metadata is None

    def test_create_response_with_metadata(self):
        """Test creating response with metadata."""
        timestamp = datetime.utcnow()
        metadata = {"confidence": "high", "reasoning": "Better performance"}

        response = HumanResponse(
            phase_id="test-phase", response_text="Use async", timestamp=timestamp, metadata=metadata
        )

        assert response.metadata == metadata
        assert response.metadata["confidence"] == "high"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        timestamp = datetime(2025, 12, 17, 10, 30, 0)
        response = HumanResponse(
            phase_id="test-phase",
            response_text="Test response",
            timestamp=timestamp,
            metadata={"key": "value"},
        )

        data = response.to_dict()

        assert data["phase_id"] == "test-phase"
        assert data["response_text"] == "Test response"
        assert data["timestamp"] == "2025-12-17T10:30:00"
        assert data["metadata"] == {"key": "value"}

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "phase_id": "test-phase",
            "response_text": "Test response",
            "timestamp": "2025-12-17T10:30:00",
            "metadata": {"key": "value"},
        }

        response = HumanResponse.from_dict(data)

        assert response.phase_id == "test-phase"
        assert response.response_text == "Test response"
        assert response.timestamp == datetime(2025, 12, 17, 10, 30, 0)
        assert response.metadata == {"key": "value"}

    def test_round_trip_serialization(self):
        """Test that serialization round-trips correctly."""
        original = HumanResponse(
            phase_id="test-phase",
            response_text="Test response",
            timestamp=datetime(2025, 12, 17, 10, 30, 0),
            metadata={"confidence": "medium"},
        )

        data = original.to_dict()
        restored = HumanResponse.from_dict(data)

        assert restored.phase_id == original.phase_id
        assert restored.response_text == original.response_text
        assert restored.timestamp == original.timestamp
        assert restored.metadata == original.metadata


class TestParseHumanResponse:
    """Tests for parsing human responses."""

    def test_parse_plain_text(self):
        """Test parsing plain text response."""
        response = parse_human_response(
            phase_id="test-phase", response_text="Yes, include Scotland fields"
        )

        assert response.phase_id == "test-phase"
        assert response.response_text == "Yes, include Scotland fields"
        assert isinstance(response.timestamp, datetime)

    def test_parse_strips_whitespace(self):
        """Test that parsing strips leading/trailing whitespace."""
        response = parse_human_response(
            phase_id="test-phase", response_text="  \n  Test response  \n  "
        )

        assert response.response_text == "Test response"

    def test_parse_json_with_answer_field(self):
        """Test parsing JSON response with answer field."""
        json_text = json.dumps(
            {"answer": "Use async API", "reasoning": "Better performance", "confidence": "high"}
        )

        response = parse_human_response(phase_id="test-phase", response_text=json_text)

        assert response.response_text == "Use async API"
        assert response.metadata["reasoning"] == "Better performance"
        assert response.metadata["confidence"] == "high"

    def test_parse_json_without_answer_field(self):
        """Test parsing JSON without answer field treats as plain text."""
        json_text = json.dumps({"reasoning": "Some reasoning", "confidence": "medium"})

        response = parse_human_response(phase_id="test-phase", response_text=json_text)

        # Should treat entire JSON as response text
        assert json_text in response.response_text

    def test_parse_invalid_json_as_plain_text(self):
        """Test that invalid JSON is treated as plain text."""
        response = parse_human_response(phase_id="test-phase", response_text="{invalid json}")

        assert response.response_text == "{invalid json}"

    def test_parse_with_metadata(self):
        """Test parsing with explicit metadata."""
        metadata = {"source": "CLI", "user": "developer"}

        response = parse_human_response(
            phase_id="test-phase", response_text="Test response", metadata=metadata
        )

        assert response.metadata == metadata

    def test_parse_merges_json_metadata(self):
        """Test that JSON fields merge with explicit metadata."""
        json_text = json.dumps({"answer": "Use async", "reasoning": "Performance"})

        response = parse_human_response(
            phase_id="test-phase", response_text=json_text, metadata={"source": "CLI"}
        )

        assert response.response_text == "Use async"
        assert response.metadata["reasoning"] == "Performance"
        assert response.metadata["source"] == "CLI"


class TestFormatResponseForContext:
    """Tests for formatting responses for context injection."""

    def test_format_basic_response(self):
        """Test formatting a basic response."""
        response = HumanResponse(
            phase_id="test-phase",
            response_text="Use async API",
            timestamp=datetime(2025, 12, 17, 10, 30, 0),
        )

        formatted = format_response_for_context(response)

        assert "💬 HUMAN GUIDANCE [test-phase]" in formatted
        assert "Response: Use async API" in formatted
        assert "2025-12-17 10:30 UTC" in formatted

    def test_format_response_with_reasoning(self):
        """Test formatting response with reasoning metadata."""
        response = HumanResponse(
            phase_id="test-phase",
            response_text="Use async",
            timestamp=datetime.utcnow(),
            metadata={"reasoning": "Better performance"},
        )

        formatted = format_response_for_context(response)

        assert "Reasoning: Better performance" in formatted

    def test_format_response_with_confidence(self):
        """Test formatting response with confidence metadata."""
        response = HumanResponse(
            phase_id="test-phase",
            response_text="Use async",
            timestamp=datetime.utcnow(),
            metadata={"confidence": "high"},
        )

        formatted = format_response_for_context(response)

        assert "Confidence: high" in formatted

    def test_format_response_with_both_metadata(self):
        """Test formatting response with both reasoning and confidence."""
        response = HumanResponse(
            phase_id="test-phase",
            response_text="Use async",
            timestamp=datetime.utcnow(),
            metadata={"reasoning": "Better performance", "confidence": "high"},
        )

        formatted = format_response_for_context(response)

        assert "Reasoning: Better performance" in formatted
        assert "Confidence: high" in formatted

    def test_format_is_compact(self):
        """Test that formatted output is reasonably compact."""
        response = HumanResponse(
            phase_id="test-phase", response_text="Short response", timestamp=datetime.utcnow()
        )

        formatted = format_response_for_context(response)

        # Should be under 200 characters for basic response
        assert len(formatted) < 200


class TestInjectResponseIntoContext:
    """Tests for injecting responses into context."""

    def test_inject_into_empty_context(self):
        """Test injecting response into empty context."""
        response = HumanResponse(
            phase_id="test-phase", response_text="Use async", timestamp=datetime.utcnow()
        )

        result = inject_response_into_context("", response)

        assert "💬 HUMAN GUIDANCE" in result
        assert "Use async" in result

    def test_inject_into_existing_context(self):
        """Test injecting response into existing context."""
        original_context = "Original context about the phase\nWith multiple lines"

        response = HumanResponse(
            phase_id="test-phase", response_text="Use async", timestamp=datetime.utcnow()
        )

        result = inject_response_into_context(original_context, response)

        # Response should be at the beginning
        assert result.startswith("💬 HUMAN GUIDANCE")
        # Original context should be preserved
        assert "Original context about the phase" in result
        assert "With multiple lines" in result

    def test_inject_includes_separator(self):
        """Test that injection includes visual separator."""
        response = HumanResponse(
            phase_id="test-phase", response_text="Use async", timestamp=datetime.utcnow()
        )

        result = inject_response_into_context("Original context", response)

        # Should have separator line
        assert "─" in result


class TestExtractChoiceNumber:
    """Tests for extracting choice numbers from responses."""

    def test_extract_plain_number(self):
        """Test extracting plain number."""
        assert extract_choice_number("2") == 2
        assert extract_choice_number("1") == 1
        assert extract_choice_number("10") == 10

    def test_extract_option_pattern(self):
        """Test extracting from 'Option N' pattern."""
        assert extract_choice_number("Option 2") == 2
        assert extract_choice_number("option 3") == 3
        assert extract_choice_number("OPTION 1") == 1

    def test_extract_choice_pattern(self):
        """Test extracting from 'Choice N' pattern."""
        assert extract_choice_number("Choice 2") == 2
        assert extract_choice_number("choice 3") == 3

    def test_extract_with_description(self):
        """Test extracting when number is followed by description."""
        assert extract_choice_number("Option 2: Use async API") == 2
        assert extract_choice_number("2: Use async API") == 2

    def test_extract_with_whitespace(self):
        """Test extracting with extra whitespace."""
        assert extract_choice_number("  2  ") == 2
        assert extract_choice_number("Option  2") == 2

    def test_extract_returns_none_for_text(self):
        """Test that text without numbers returns None."""
        assert extract_choice_number("Use async API") is None
        assert extract_choice_number("I prefer the second option") is None
        assert extract_choice_number("No clear choice") is None

    def test_extract_number_at_start(self):
        """Test extracting number at start of text."""
        assert extract_choice_number("2 is my choice") == 2
        assert extract_choice_number("3 - Use async") == 3


class TestValidateResponseForDecision:
    """Tests for validating decision responses."""

    def test_validate_valid_choice(self):
        """Test validating a valid choice."""
        response = HumanResponse(
            phase_id="test-phase", response_text="Option 2", timestamp=datetime.utcnow()
        )

        is_valid, error = validate_response_for_decision(response, num_options=3)

        assert is_valid is True
        assert error is None

    def test_validate_choice_out_of_range_high(self):
        """Test validating choice that's too high."""
        response = HumanResponse(
            phase_id="test-phase", response_text="Option 5", timestamp=datetime.utcnow()
        )

        is_valid, error = validate_response_for_decision(response, num_options=3)

        assert is_valid is False
        assert "out of range" in error
        assert "5" in error

    def test_validate_choice_out_of_range_low(self):
        """Test validating choice that's too low."""
        response = HumanResponse(
            phase_id="test-phase", response_text="0", timestamp=datetime.utcnow()
        )

        is_valid, error = validate_response_for_decision(response, num_options=3)

        assert is_valid is False
        assert "out of range" in error

    def test_validate_no_choice_number(self):
        """Test validating response without choice number."""
        response = HumanResponse(
            phase_id="test-phase",
            response_text="I prefer the async approach",
            timestamp=datetime.utcnow(),
        )

        is_valid, error = validate_response_for_decision(response, num_options=3)

        assert is_valid is False
        assert "valid choice number" in error

    def test_validate_boundary_choices(self):
        """Test validating boundary choices (1 and max)."""
        response1 = HumanResponse(
            phase_id="test-phase", response_text="1", timestamp=datetime.utcnow()
        )
        response3 = HumanResponse(
            phase_id="test-phase", response_text="3", timestamp=datetime.utcnow()
        )

        is_valid1, _ = validate_response_for_decision(response1, num_options=3)
        is_valid3, _ = validate_response_for_decision(response3, num_options=3)

        assert is_valid1 is True
        assert is_valid3 is True


class TestPersistence:
    """Tests for saving and loading human responses."""

    def test_save_and_load_basic_response(self, tmp_path):
        """Test saving and loading a basic response."""
        filepath = tmp_path / "response.json"

        original = HumanResponse(
            phase_id="test-phase",
            response_text="Test response",
            timestamp=datetime(2025, 12, 17, 10, 30, 0),
        )

        save_human_response(original, str(filepath))
        loaded = load_human_response(str(filepath))

        assert loaded.phase_id == original.phase_id
        assert loaded.response_text == original.response_text
        assert loaded.timestamp == original.timestamp

    def test_save_and_load_response_with_metadata(self, tmp_path):
        """Test saving and loading response with metadata."""
        filepath = tmp_path / "response.json"

        original = HumanResponse(
            phase_id="test-phase",
            response_text="Test response",
            timestamp=datetime(2025, 12, 17, 10, 30, 0),
            metadata={"confidence": "high", "reasoning": "Clear requirement"},
        )

        save_human_response(original, str(filepath))
        loaded = load_human_response(str(filepath))

        assert loaded.metadata == original.metadata

    def test_save_creates_valid_json(self, tmp_path):
        """Test that saved file is valid JSON."""
        filepath = tmp_path / "response.json"

        response = HumanResponse(
            phase_id="test-phase", response_text="Test response", timestamp=datetime.utcnow()
        )

        save_human_response(response, str(filepath))

        # Should be able to parse as JSON
        with open(filepath) as f:
            data = json.load(f)

        assert isinstance(data, dict)
        assert data["phase_id"] == "test-phase"


class TestCreateResponseFromCliArgs:
    """Tests for creating responses from CLI arguments."""

    def test_create_from_single_arg(self):
        """Test creating response from single argument."""
        response = create_response_from_cli_args(phase_id="test-phase", response_parts=["Yes"])

        assert response.phase_id == "test-phase"
        assert response.response_text == "Yes"

    def test_create_from_multiple_args(self):
        """Test creating response from multiple arguments."""
        response = create_response_from_cli_args(
            phase_id="test-phase", response_parts=["Use", "async", "API"]
        )

        assert response.response_text == "Use async API"

    def test_create_with_metadata(self):
        """Test creating response with metadata."""
        metadata = {"source": "CLI"}

        response = create_response_from_cli_args(
            phase_id="test-phase", response_parts=["Test", "response"], metadata=metadata
        )

        assert response.metadata == metadata

    def test_create_from_empty_args(self):
        """Test creating response from empty argument list."""
        response = create_response_from_cli_args(phase_id="test-phase", response_parts=[])

        assert response.response_text == ""


class TestFormatResponseSummary:
    """Tests for formatting response summaries."""

    def test_format_short_response(self):
        """Test formatting short response."""
        response = HumanResponse(
            phase_id="test-phase", response_text="Short response", timestamp=datetime.utcnow()
        )

        summary = format_response_summary(response)

        assert "[test-phase]" in summary
        assert "Short response" in summary

    def test_format_long_response_truncates(self):
        """Test that long responses are truncated."""
        long_text = "A" * 200

        response = HumanResponse(
            phase_id="test-phase", response_text=long_text, timestamp=datetime.utcnow()
        )

        summary = format_response_summary(response, max_length=50)

        assert len(summary) <= 50
        assert "..." in summary

    def test_format_respects_max_length(self):
        """Test that summary respects max_length parameter."""
        response = HumanResponse(
            phase_id="test-phase", response_text="Some response text", timestamp=datetime.utcnow()
        )

        summary = format_response_summary(response, max_length=30)

        assert len(summary) <= 30

    def test_format_includes_phase_id(self):
        """Test that summary includes phase ID."""
        response = HumanResponse(
            phase_id="my-phase-123", response_text="Response", timestamp=datetime.utcnow()
        )

        summary = format_response_summary(response)

        assert "[my-phase-123]" in summary


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_empty_response_text(self):
        """Test handling empty response text."""
        response = HumanResponse(
            phase_id="test-phase", response_text="", timestamp=datetime.utcnow()
        )

        formatted = format_response_for_context(response)
        assert "Response:" in formatted

    def test_very_long_response_text(self):
        """Test handling very long response text."""
        long_text = "Response " * 1000

        response = HumanResponse(
            phase_id="test-phase", response_text=long_text, timestamp=datetime.utcnow()
        )

        formatted = format_response_for_context(response)
        assert long_text in formatted

    def test_special_characters_in_response(self):
        """Test handling special characters in response."""
        response = HumanResponse(
            phase_id="test-phase",
            response_text="Use <tag> & 'quotes' and \"escapes\"",
            timestamp=datetime.utcnow(),
        )

        formatted = format_response_for_context(response)
        assert "<tag>" in formatted
        assert "&" in formatted

    def test_unicode_in_response(self):
        """Test handling unicode characters in response."""
        response = HumanResponse(
            phase_id="test-phase",
            response_text="Use €, £, ¥ symbols and emoji 🚀",
            timestamp=datetime.utcnow(),
        )

        formatted = format_response_for_context(response)
        assert "€" in formatted
        assert "🚀" in formatted

    def test_multiline_response(self):
        """Test handling multiline response text."""
        response = HumanResponse(
            phase_id="test-phase",
            response_text="Line 1\nLine 2\nLine 3",
            timestamp=datetime.utcnow(),
        )

        formatted = format_response_for_context(response)
        assert "Line 1" in formatted
        assert "Line 2" in formatted
        assert "Line 3" in formatted
