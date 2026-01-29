"""Tests for content compression integration in memory write path (IMP-MEM-012).

Tests cover:
- _compress_content() helper function
- write_error() compression behavior
- write_phase_summary() compression behavior
- Compression metadata tracking (compressed flag)
"""

from unittest.mock import MagicMock, patch

import pytest

from autopack.memory.memory_service import (MAX_CONTENT_LENGTH, MemoryService,
                                            _compress_content)


class TestCompressContent:
    """Tests for _compress_content helper function."""

    def test_short_content_not_compressed(self):
        """Verify content under threshold is not modified."""
        content = "Short content"

        result, was_compressed = _compress_content(content)

        assert result == content
        assert was_compressed is False

    def test_exact_threshold_not_compressed(self):
        """Verify content at exactly max length is not compressed."""
        content = "x" * MAX_CONTENT_LENGTH

        result, was_compressed = _compress_content(content)

        assert result == content
        assert was_compressed is False

    def test_long_content_compressed(self):
        """Verify content over threshold is compressed."""
        content = "x" * (MAX_CONTENT_LENGTH + 1000)

        result, was_compressed = _compress_content(content)

        assert was_compressed is True
        assert len(result) <= MAX_CONTENT_LENGTH
        assert "[... truncated middle section ...]" in result

    def test_compression_preserves_start_and_end(self):
        """Verify compression keeps important start and end sections."""
        # Create content with distinctive start and end markers
        start_marker = "START_MARKER_ABC123"
        end_marker = "END_MARKER_XYZ789"
        middle_content = "m" * (MAX_CONTENT_LENGTH + 1000)
        content = start_marker + middle_content + end_marker

        result, was_compressed = _compress_content(content)

        assert was_compressed is True
        assert start_marker in result
        assert end_marker in result

    def test_custom_max_length(self):
        """Verify custom max_length parameter works."""
        content = "x" * 1000

        result, was_compressed = _compress_content(content, max_length=500)

        assert was_compressed is True
        assert len(result) <= 500

    def test_compression_result_shorter_than_original(self):
        """Verify compressed content is always shorter than original."""
        content = "x" * (MAX_CONTENT_LENGTH * 3)

        result, was_compressed = _compress_content(content)

        assert was_compressed is True
        assert len(result) < len(content)


class TestWriteErrorCompression:
    """Tests for compression in write_error method."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a MemoryService with mocked store."""
        with patch.object(MemoryService, "__init__", lambda self: None):
            with patch("autopack.memory.memory_service.sync_embed_text", return_value=[0.0] * 384):
                service = MemoryService()
                service.enabled = True
                service.store = MagicMock()
                yield service, service.store

    def test_short_error_not_compressed(self, mock_memory_service):
        """Verify short error text is stored without compression flag."""
        service, mock_store = mock_memory_service
        short_error = "Error: Something went wrong"

        service.write_error(
            run_id="run-1",
            phase_id="phase-1",
            project_id="project-1",
            error_text=short_error,
        )

        # Verify upsert was called
        mock_store.upsert.assert_called_once()
        call_args = mock_store.upsert.call_args
        payload = call_args[0][1][0]["payload"]

        assert payload["error_text"] == short_error
        assert payload["compressed"] is False

    def test_long_error_compressed(self, mock_memory_service):
        """Verify long error text is compressed and flagged."""
        service, mock_store = mock_memory_service
        long_error = "E" * (MAX_CONTENT_LENGTH + 2000)

        service.write_error(
            run_id="run-1",
            phase_id="phase-1",
            project_id="project-1",
            error_text=long_error,
        )

        # Verify upsert was called
        mock_store.upsert.assert_called_once()
        call_args = mock_store.upsert.call_args
        payload = call_args[0][1][0]["payload"]

        assert payload["compressed"] is True
        assert len(payload["error_text"]) <= MAX_CONTENT_LENGTH
        assert "[... truncated middle section ...]" in payload["error_text"]

    def test_compressed_error_preserves_key_info(self, mock_memory_service):
        """Verify compressed error preserves start (error type) and end (stack trace)."""
        service, mock_store = mock_memory_service
        # Simulate typical error: type at start, stack trace at end
        error_start = "TypeError: cannot subscript 'NoneType' object\n"
        error_middle = "... lots of traceback ...\n" * 500
        error_end = "\nFile 'main.py', line 42, in process_data"
        long_error = error_start + error_middle + error_end

        service.write_error(
            run_id="run-1",
            phase_id="phase-1",
            project_id="project-1",
            error_text=long_error,
            error_type="type_error",
        )

        call_args = mock_store.upsert.call_args
        payload = call_args[0][1][0]["payload"]

        # Both key sections should be preserved
        assert "TypeError: cannot subscript" in payload["error_text"]
        assert "main.py" in payload["error_text"]


class TestWritePhaseSummaryCompression:
    """Tests for compression in write_phase_summary method."""

    @pytest.fixture
    def mock_memory_service(self):
        """Create a MemoryService with mocked store."""
        with patch.object(MemoryService, "__init__", lambda self: None):
            with patch("autopack.memory.memory_service.sync_embed_text", return_value=[0.0] * 384):
                service = MemoryService()
                service.enabled = True
                service.store = MagicMock()
                yield service, service.store

    def test_short_summary_not_compressed(self, mock_memory_service):
        """Verify short summary is stored without compression."""
        service, mock_store = mock_memory_service
        short_summary = "Added new feature X"

        service.write_phase_summary(
            run_id="run-1",
            phase_id="phase-1",
            project_id="project-1",
            summary=short_summary,
            changes=["file1.py"],
        )

        mock_store.upsert.assert_called_once()
        call_args = mock_store.upsert.call_args
        payload = call_args[0][1][0]["payload"]

        assert payload["summary"] == short_summary
        assert payload["compressed"] is False

    def test_long_summary_compressed(self, mock_memory_service):
        """Verify long summary is compressed and flagged."""
        service, mock_store = mock_memory_service
        long_summary = "S" * (MAX_CONTENT_LENGTH + 1000)

        service.write_phase_summary(
            run_id="run-1",
            phase_id="phase-1",
            project_id="project-1",
            summary=long_summary,
            changes=["file1.py", "file2.py"],
        )

        mock_store.upsert.assert_called_once()
        call_args = mock_store.upsert.call_args
        payload = call_args[0][1][0]["payload"]

        assert payload["compressed"] is True
        assert len(payload["summary"]) <= MAX_CONTENT_LENGTH

    def test_compressed_summary_preserves_context(self, mock_memory_service):
        """Verify compressed summary keeps start and end context."""
        service, mock_store = mock_memory_service
        summary_start = "PHASE OBJECTIVE: Implement user authentication\n"
        summary_middle = "Details... " * 1000
        summary_end = "\nRESULT: Successfully implemented OAuth2 flow"
        long_summary = summary_start + summary_middle + summary_end

        service.write_phase_summary(
            run_id="run-1",
            phase_id="phase-1",
            project_id="project-1",
            summary=long_summary,
            changes=["auth.py"],
        )

        call_args = mock_store.upsert.call_args
        payload = call_args[0][1][0]["payload"]

        assert "PHASE OBJECTIVE" in payload["summary"]
        assert "OAuth2" in payload["summary"]


class TestCompressionLogging:
    """Tests for compression logging behavior."""

    def test_compression_logs_size_reduction(self, caplog):
        """Verify compression logs the size reduction."""
        import logging

        caplog.set_level(logging.DEBUG)
        content = "x" * (MAX_CONTENT_LENGTH + 5000)

        _compress_content(content)

        assert "[IMP-MEM-012]" in caplog.text
        assert "Compressed content from" in caplog.text
