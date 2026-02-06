"""
BUILD-155: Test format_retrieved_context() character cap enforcement.

Tests that the MemoryService.format_retrieved_context() method correctly
enforces the max_chars parameter and never returns output exceeding the cap.

Critical for preventing silent prompt bloat from uncapped context assembly.
"""

import pytest

from autopack.memory.memory_service import MemoryService


class TestFormatRetrievedContextCaps:
    """Test char cap enforcement in format_retrieved_context()"""

    @pytest.fixture
    def memory_service(self):
        """Create a MemoryService instance (disabled, no vector store needed)"""
        return MemoryService(enabled=False, use_qdrant=False)

    def test_empty_context_respects_cap(self, memory_service):
        """Empty context should return empty string (within cap)"""
        context = {"code": [], "summaries": [], "errors": [], "hints": [], "sot": []}

        formatted = memory_service.format_retrieved_context(context, max_chars=1000)

        assert len(formatted) <= 1000, "Empty context should be within cap"
        assert formatted == "", "Empty context should return empty string"

    def test_small_context_under_cap(self, memory_service):
        """Small context well under cap should be returned unmodified"""
        context = {
            "code": [{"payload": {"content_preview": "def foo(): pass", "path": "test.py"}}],
            "summaries": [],
            "errors": [],
            "hints": [],
            "planning": [],
            "plan_changes": [],
            "decisions": [],
            "sot": [],
        }

        formatted = memory_service.format_retrieved_context(context, max_chars=1000)

        assert len(formatted) <= 1000, "Small context should be within cap"
        assert "def foo(): pass" in formatted, "Small context should include content"

    def test_large_context_exceeds_cap_is_truncated(self, memory_service):
        """Large context exceeding cap should be truncated"""
        # Create context with 10KB of content
        large_content = "x" * 10000
        context = {
            "code": [{"payload": {"content_preview": large_content, "path": "large.py"}}],
            "summaries": [],
            "errors": [],
            "hints": [],
            "planning": [],
            "plan_changes": [],
            "decisions": [],
            "sot": [],
        }

        formatted = memory_service.format_retrieved_context(context, max_chars=2000)

        assert len(formatted) <= 2000, (
            f"Output ({len(formatted)} chars) exceeds max_chars=2000. "
            "format_retrieved_context() MUST enforce the cap."
        )

    def test_multiple_sections_all_truncated_proportionally(self, memory_service):
        """When multiple sections exceed cap, all should be truncated"""
        context = {
            "code": [{"payload": {"content_preview": "c" * 5000, "path": "code.py"}}],
            "summaries": [{"payload": {"summary": "s" * 5000, "phase_id": "phase_1"}}],
            "errors": [{"payload": {"error_type": "Error", "error_text": "e" * 5000}}],
            "hints": [],
            "planning": [],
            "plan_changes": [],
            "decisions": [],
            "sot": [{"payload": {"content_preview": "t" * 5000}}],
        }

        # Total raw content: 20KB, cap: 3KB → expect proportional truncation
        formatted = memory_service.format_retrieved_context(context, max_chars=3000)

        assert len(formatted) <= 3000, (
            f"Output ({len(formatted)} chars) exceeds max_chars=3000. "
            "Multi-section truncation must respect total cap."
        )

    def test_sot_section_respects_overall_cap(self, memory_service):
        """SOT section should be truncated to fit within overall cap"""
        # SOT has its own budget (AUTOPACK_SOT_RETRIEVAL_MAX_CHARS=4000 default),
        # but format_retrieved_context(max_chars=...) is the final enforcer
        context = {
            "code": [],
            "summaries": [],
            "errors": [],
            "hints": [],
            "planning": [],
            "plan_changes": [],
            "decisions": [],
            "sot": [{"payload": {"content_preview": "t" * 8000}}],  # 8KB of SOT content
        }

        # Cap at 2KB total → SOT must be truncated
        formatted = memory_service.format_retrieved_context(context, max_chars=2000)

        assert len(formatted) <= 2000, (
            f"SOT section ({len(formatted)} chars) exceeds max_chars=2000. "
            "format_retrieved_context() must cap SOT along with other sections."
        )

    def test_zero_max_chars_returns_empty(self, memory_service):
        """max_chars=0 should return empty string"""
        context = {
            "code": [{"payload": {"content_preview": "def foo(): pass", "path": "test.py"}}],
            "summaries": [],
            "errors": [],
            "hints": [],
            "planning": [],
            "plan_changes": [],
            "decisions": [],
            "sot": [],
        }

        formatted = memory_service.format_retrieved_context(context, max_chars=0)

        assert len(formatted) == 0, "max_chars=0 should return empty string"

    def test_very_small_cap_edge_case(self, memory_service):
        """Very small cap (100 chars) should still be respected"""
        context = {
            "code": [{"payload": {"content_preview": "x" * 1000, "path": "test.py"}}],
            "summaries": [],
            "errors": [],
            "hints": [],
            "planning": [],
            "plan_changes": [],
            "decisions": [],
            "sot": [],
        }

        formatted = memory_service.format_retrieved_context(context, max_chars=100)

        assert len(formatted) <= 100, (
            f"Output ({len(formatted)} chars) exceeds max_chars=100. "
            "Even tiny caps must be enforced."
        )

    def test_cap_enforcement_with_section_headers(self, memory_service):
        """Cap should include section headers in total char count"""
        context = {
            "code": [{"payload": {"content_preview": "c" * 500, "path": "code.py"}}],
            "summaries": [{"payload": {"summary": "s" * 500, "phase_id": "phase_1"}}],
            "errors": [],
            "hints": [],
            "planning": [],
            "plan_changes": [],
            "decisions": [],
            "sot": [],
        }

        # Total raw content: 1KB, but headers add overhead
        # Cap should include headers in the total
        formatted = memory_service.format_retrieved_context(context, max_chars=1000)

        assert len(formatted) <= 1000, "Section headers must be counted toward max_chars cap"

    def test_idempotent_formatting_with_same_cap(self, memory_service):
        """Calling format_retrieved_context() twice with same cap should give same result"""
        context = {
            "code": [{"payload": {"content_preview": "x" * 5000, "path": "test.py"}}],
            "summaries": [],
            "errors": [],
            "hints": [],
            "planning": [],
            "plan_changes": [],
            "decisions": [],
            "sot": [],
        }

        formatted1 = memory_service.format_retrieved_context(context, max_chars=2000)
        formatted2 = memory_service.format_retrieved_context(context, max_chars=2000)

        assert len(formatted1) == len(formatted2), "Formatting should be deterministic"
        assert len(formatted1) <= 2000, "Both calls should respect cap"
