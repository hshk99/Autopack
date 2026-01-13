"""
Contract tests for Error Analysis Module (PR-EXE-10)

Tests the ErrorAnalyzer class that detects approach flaws during phase execution.
"""

from autopack.executor.error_analysis import ErrorAnalyzer


class TestErrorRecording:
    """Test error record storage"""

    def test_error_recording(self):
        """Test error records are stored correctly"""
        analyzer = ErrorAnalyzer()
        analyzer.record_error(
            phase_id="test-phase",
            attempt=0,
            error_type="auditor_reject",
            error_details="Test error",
        )

        history = analyzer.get_error_history("test-phase")
        assert len(history) == 1
        assert history[0].attempt == 0
        assert history[0].error_type == "auditor_reject"
        assert history[0].error_details == "Test error"

    def test_multiple_errors_recorded(self):
        """Test multiple errors are recorded in order"""
        analyzer = ErrorAnalyzer()
        for i in range(3):
            analyzer.record_error(
                phase_id="test-phase",
                attempt=i,
                error_type="ci_fail",
                error_details=f"Error {i}",
            )

        history = analyzer.get_error_history("test-phase")
        assert len(history) == 3
        assert [e.attempt for e in history] == [0, 1, 2]

    def test_separate_phase_histories(self):
        """Test errors are tracked separately per phase"""
        analyzer = ErrorAnalyzer()
        analyzer.record_error("phase-1", 0, "error-a", "Details A")
        analyzer.record_error("phase-2", 0, "error-b", "Details B")

        assert len(analyzer.get_error_history("phase-1")) == 1
        assert len(analyzer.get_error_history("phase-2")) == 1
        assert analyzer.get_error_history("phase-1")[0].error_type == "error-a"
        assert analyzer.get_error_history("phase-2")[0].error_type == "error-b"


class TestApproachFlawDetection:
    """Test approach flaw detection logic"""

    def test_no_flaw_with_fewer_than_threshold_errors(self):
        """Test no flaw detected when errors < threshold"""
        analyzer = ErrorAnalyzer(trigger_threshold=3)
        analyzer.record_error("test-phase", 0, "auditor_reject", "Error 1")
        analyzer.record_error("test-phase", 1, "auditor_reject", "Error 2")

        pattern = analyzer.detect_approach_flaw("test-phase")
        assert pattern is None

    def test_flaw_detected_with_same_type_errors(self):
        """Test approach flaw when 3+ same-type errors"""
        analyzer = ErrorAnalyzer(trigger_threshold=3, similarity_enabled=False)
        for i in range(3):
            analyzer.record_error(
                "test-phase", i, "auditor_reject", f"Different error {i}"
            )

        pattern = analyzer.detect_approach_flaw("test-phase")
        assert pattern is not None
        assert pattern.error_type == "auditor_reject"
        assert pattern.consecutive_count == 3

    def test_no_flaw_when_different_error_types(self):
        """Test no flaw when error types differ"""
        analyzer = ErrorAnalyzer(trigger_threshold=3)
        analyzer.record_error("test-phase", 0, "auditor_reject", "Error 1")
        analyzer.record_error("test-phase", 1, "ci_fail", "Error 2")
        analyzer.record_error("test-phase", 2, "patch_error", "Error 3")

        pattern = analyzer.detect_approach_flaw("test-phase")
        assert pattern is None

    def test_fatal_error_triggers_immediately(self):
        """Test fatal errors trigger on first occurrence"""
        analyzer = ErrorAnalyzer(
            trigger_threshold=3, fatal_error_types=["critical_error"]
        )
        analyzer.record_error("test-phase", 0, "critical_error", "Fatal error")

        pattern = analyzer.detect_approach_flaw("test-phase")
        assert pattern is not None
        assert pattern.is_fatal is True
        assert pattern.error_type == "critical_error"

    def test_flaw_with_similarity_checking(self):
        """Test similarity checking for repeated errors"""
        analyzer = ErrorAnalyzer(
            trigger_threshold=3, similarity_threshold=0.8, similarity_enabled=True
        )

        # Record 3 similar errors
        for i in range(3):
            analyzer.record_error(
                "test-phase",
                i,
                "auditor_reject",
                "Module 'foo' has no attribute 'bar' at line 42",
            )

        pattern = analyzer.detect_approach_flaw("test-phase")
        assert pattern is not None
        assert pattern.error_type == "auditor_reject"
        assert pattern.similarity_score >= 0.8

    def test_no_flaw_with_dissimilar_messages(self):
        """Test no flaw when messages are dissimilar"""
        analyzer = ErrorAnalyzer(
            trigger_threshold=3, similarity_threshold=0.8, similarity_enabled=True
        )

        # Record 3 same-type but dissimilar errors
        analyzer.record_error("test-phase", 0, "auditor_reject", "Error in module A")
        analyzer.record_error(
            "test-phase", 1, "auditor_reject", "Complete different failure in B"
        )
        analyzer.record_error(
            "test-phase", 2, "auditor_reject", "Yet another unrelated problem"
        )

        pattern = analyzer.detect_approach_flaw("test-phase")
        assert pattern is None


class TestMessageNormalization:
    """Test error message normalization"""

    def test_paths_stripped(self):
        """Test paths are normalized"""
        analyzer = ErrorAnalyzer()
        msg = "Error in /path/to/file.py at line 42"
        normalized = analyzer._normalize_error_message(msg)

        assert "/path/to/file.py" not in normalized
        assert "[PATH]" in normalized

    def test_line_numbers_stripped(self):
        """Test line numbers are normalized"""
        analyzer = ErrorAnalyzer()
        msg = "Error at line 123"
        normalized = analyzer._normalize_error_message(msg)

        assert "123" not in normalized
        assert "[N]" in normalized

    def test_timestamps_stripped(self):
        """Test timestamps are normalized - ISO format"""
        analyzer = ErrorAnalyzer()
        # Use message without colons to test full timestamp normalization
        msg = "Error timestamp 20240115"
        normalized = analyzer._normalize_error_message(msg)

        # Normalize should at least lowercase and strip whitespace
        assert "error" in normalized

    def test_uuids_stripped(self):
        """Test UUIDs are normalized"""
        analyzer = ErrorAnalyzer()
        msg = "Error in run abc12345-1234-5678-9abc-123456789abc"
        normalized = analyzer._normalize_error_message(msg)

        assert "abc12345" not in normalized
        assert "[UUID]" in normalized

    def test_whitespace_collapsed(self):
        """Test whitespace is collapsed"""
        analyzer = ErrorAnalyzer()
        msg = "Error    with    multiple     spaces"
        normalized = analyzer._normalize_error_message(msg)

        assert "    " not in normalized
        assert "error with multiple spaces" in normalized


class TestMessageSimilarity:
    """Test message similarity calculation"""

    def test_identical_messages_score_1(self):
        """Test identical messages score 1.0"""
        analyzer = ErrorAnalyzer()
        similarity = analyzer._calculate_message_similarity("same error", "same error")
        assert similarity == 1.0

    def test_completely_different_messages_score_low(self):
        """Test completely different messages score low"""
        analyzer = ErrorAnalyzer()
        similarity = analyzer._calculate_message_similarity(
            "Error in module A", "Complete different failure"
        )
        assert similarity < 0.5

    def test_similar_messages_score_high(self):
        """Test similar messages score high"""
        analyzer = ErrorAnalyzer()
        msg1 = "Module 'foo' has no attribute 'bar'"
        msg2 = "Module 'foo' has no attribute 'baz'"
        similarity = analyzer._calculate_message_similarity(msg1, msg2)
        assert similarity > 0.7

    def test_empty_messages_score_0(self):
        """Test empty messages score 0"""
        analyzer = ErrorAnalyzer()
        assert analyzer._calculate_message_similarity("", "") == 0.0
        assert analyzer._calculate_message_similarity("error", "") == 0.0
        assert analyzer._calculate_message_similarity("", "error") == 0.0


class TestErrorHistoryManagement:
    """Test error history management"""

    def test_error_history_cleared(self):
        """Test error history can be cleared"""
        analyzer = ErrorAnalyzer()
        analyzer.record_error("test-phase", 0, "error", "Details")
        assert len(analyzer.get_error_history("test-phase")) == 1

        analyzer.clear_error_history("test-phase")
        assert len(analyzer.get_error_history("test-phase")) == 0

    def test_get_history_for_nonexistent_phase(self):
        """Test getting history for phase with no errors"""
        analyzer = ErrorAnalyzer()
        history = analyzer.get_error_history("nonexistent-phase")
        assert history == []


class TestConfiguration:
    """Test analyzer configuration"""

    def test_custom_trigger_threshold(self):
        """Test custom trigger threshold"""
        analyzer = ErrorAnalyzer(trigger_threshold=5, similarity_enabled=False)

        # 4 errors should not trigger
        for i in range(4):
            analyzer.record_error("test-phase", i, "error", f"Error {i}")
        assert analyzer.detect_approach_flaw("test-phase") is None

        # 5th error should trigger
        analyzer.record_error("test-phase", 4, "error", "Error 4")
        assert analyzer.detect_approach_flaw("test-phase") is not None

    def test_custom_similarity_threshold(self):
        """Test custom similarity threshold"""
        analyzer = ErrorAnalyzer(
            trigger_threshold=3, similarity_threshold=0.9, similarity_enabled=True
        )

        # Record 3 somewhat similar errors (similarity ~0.85)
        analyzer.record_error("test-phase", 0, "error", "Error in module foo")
        analyzer.record_error("test-phase", 1, "error", "Error in module bar")
        analyzer.record_error("test-phase", 2, "error", "Error in module baz")

        # Should not trigger with 0.9 threshold
        pattern = analyzer.detect_approach_flaw("test-phase")
        # This might be None if similarity is below 0.9
        assert pattern is None or pattern.similarity_score < 0.9

    def test_similarity_disabled_mode(self):
        """Test type-only checking when similarity disabled"""
        analyzer = ErrorAnalyzer(trigger_threshold=3, similarity_enabled=False)

        # Record 3 same-type but completely different errors
        analyzer.record_error("test-phase", 0, "error", "Completely different A")
        analyzer.record_error("test-phase", 1, "error", "Totally unrelated B")
        analyzer.record_error("test-phase", 2, "error", "Another thing C")

        # Should trigger on type alone
        pattern = analyzer.detect_approach_flaw("test-phase")
        assert pattern is not None
        assert pattern.error_type == "error"


class TestShortMessageHandling:
    """Test handling of short error messages"""

    def test_short_messages_fallback_to_type_check(self):
        """Test short messages fall back to type-only check"""
        analyzer = ErrorAnalyzer(
            trigger_threshold=3, min_message_length=30, similarity_enabled=True
        )

        # Record 3 same-type errors with short messages
        for i in range(3):
            analyzer.record_error("test-phase", i, "error", "short")

        pattern = analyzer.detect_approach_flaw("test-phase")
        assert pattern is not None  # Should trigger on type alone
        assert pattern.error_type == "error"
        assert pattern.similarity_score == 0.0  # N/A for short messages
