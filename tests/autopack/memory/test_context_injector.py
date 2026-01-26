"""Tests for context_injector.py (IMP-DISC-001).

Tests cover:
- ContextInjection dataclass with discovery_insights field
- get_context_for_phase method integration with discovery context
- get_discovery_context method
- format_for_prompt including discovery insights
"""

from unittest.mock import Mock, patch, MagicMock

from autopack.memory.context_injector import ContextInjector, ContextInjection


class TestContextInjectionDataclass:
    """Tests for ContextInjection dataclass."""

    def test_context_injection_has_discovery_insights_field(self):
        """IMP-DISC-001: ContextInjection should have discovery_insights field."""
        injection = ContextInjection(
            past_errors=["error1"],
            successful_strategies=["strategy1"],
            doctor_hints=["hint1"],
            relevant_insights=["insight1"],
            discovery_insights=["discovery1"],
            total_token_estimate=100,
        )

        assert hasattr(injection, "discovery_insights")
        assert injection.discovery_insights == ["discovery1"]

    def test_context_injection_with_empty_discovery_insights(self):
        """ContextInjection should work with empty discovery_insights."""
        injection = ContextInjection(
            past_errors=[],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=0,
        )

        assert injection.discovery_insights == []


class TestContextInjectorGetDiscoveryContext:
    """Tests for get_discovery_context method."""

    def test_get_discovery_context_returns_list(self):
        """get_discovery_context should return a list of strings."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        # Patch the DiscoveryContextMerger class in the roadc module
        with patch(
            "autopack.roadc.discovery_context_merger.DiscoveryContextMerger"
        ) as mock_merger_class:
            mock_merger = MagicMock()
            mock_merger.merge_sources.return_value = []
            mock_merger.rank_by_relevance.return_value = ["discovery1", "discovery2"]
            mock_merger_class.return_value = mock_merger

            result = injector.get_discovery_context(
                phase_type="build",
                current_goal="fix compilation error",
                limit=3,
            )

            assert isinstance(result, list)
            assert result == ["discovery1", "discovery2"]

    def test_get_discovery_context_handles_import_error_gracefully(self):
        """get_discovery_context should handle import failures gracefully.

        Note: Since DiscoveryContextMerger is already importable, this tests
        the exception handling path by mocking the merger to raise an exception.
        """
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        # Mock the merger to raise an exception during merge_sources
        with patch(
            "autopack.roadc.discovery_context_merger.DiscoveryContextMerger"
        ) as mock_merger_class:
            mock_merger_class.return_value.merge_sources.side_effect = Exception("Module not found")

            result = injector.get_discovery_context(
                phase_type="build",
                current_goal="fix compilation error",
            )

            assert result == []

    def test_get_discovery_context_handles_exception(self):
        """get_discovery_context should return empty list on exception."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        with patch(
            "autopack.roadc.discovery_context_merger.DiscoveryContextMerger"
        ) as mock_merger_class:
            mock_merger_class.return_value.merge_sources.side_effect = Exception("API error")

            result = injector.get_discovery_context(
                phase_type="build",
                current_goal="fix compilation error",
            )

            assert result == []

    def test_get_discovery_context_respects_limit(self):
        """get_discovery_context should respect the limit parameter."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        with patch(
            "autopack.roadc.discovery_context_merger.DiscoveryContextMerger"
        ) as mock_merger_class:
            mock_merger = MagicMock()
            mock_merger.merge_sources.return_value = []
            mock_merger.rank_by_relevance.return_value = [
                "d1",
                "d2",
                "d3",
                "d4",
                "d5",
            ]
            mock_merger_class.return_value = mock_merger

            result = injector.get_discovery_context(
                phase_type="build",
                current_goal="fix compilation error",
                limit=2,
            )

            assert len(result) == 2


class TestContextInjectorGetContextForPhase:
    """Tests for get_context_for_phase integration with discovery context."""

    def test_get_context_for_phase_includes_discovery_insights(self):
        """get_context_for_phase should include discovery_insights in result."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.search_errors.return_value = []
        mock_memory.search_summaries.return_value = []
        mock_memory.search_doctor_hints.return_value = []
        mock_memory.search_code.return_value = []

        injector = ContextInjector(memory_service=mock_memory)

        with patch.object(injector, "get_discovery_context", return_value=["discovered solution"]):
            result = injector.get_context_for_phase(
                phase_type="build",
                current_goal="fix compilation",
                project_id="test-project",
            )

            assert isinstance(result, ContextInjection)
            assert result.discovery_insights == ["discovered solution"]

    def test_get_context_for_phase_with_memory_disabled(self):
        """get_context_for_phase should return empty discovery_insights when memory disabled."""
        mock_memory = Mock()
        mock_memory.enabled = False

        injector = ContextInjector(memory_service=mock_memory)

        result = injector.get_context_for_phase(
            phase_type="build",
            current_goal="fix compilation",
            project_id="test-project",
        )

        assert result.discovery_insights == []

    def test_get_context_for_phase_includes_discovery_in_token_estimate(self):
        """Token estimate should include discovery insights."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.search_errors.return_value = []
        mock_memory.search_summaries.return_value = []
        mock_memory.search_doctor_hints.return_value = []
        mock_memory.search_code.return_value = []

        injector = ContextInjector(memory_service=mock_memory)

        # Discovery insight with 40 chars = 10 tokens
        with patch.object(injector, "get_discovery_context", return_value=["a" * 40]):
            result = injector.get_context_for_phase(
                phase_type="build",
                current_goal="fix compilation",
                project_id="test-project",
            )

            assert result.total_token_estimate >= 10


class TestContextInjectorFormatForPrompt:
    """Tests for format_for_prompt including discovery insights."""

    def test_format_for_prompt_includes_discovery_section(self):
        """format_for_prompt should include discovery insights section."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        injection = ContextInjection(
            past_errors=[],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=["[GITHUB] Found similar issue in repo"],
            total_token_estimate=50,
        )

        result = injector.format_for_prompt(injection)

        assert "Discovery Insights (External Sources)" in result
        assert "[GITHUB] Found similar issue in repo" in result

    def test_format_for_prompt_omits_empty_discovery_section(self):
        """format_for_prompt should not include discovery section if empty."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        injection = ContextInjection(
            past_errors=[],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=0,
        )

        result = injector.format_for_prompt(injection)

        assert "Discovery Insights" not in result

    def test_format_for_prompt_truncates_long_discovery_insights(self):
        """format_for_prompt should truncate discovery insights to 150 chars."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        long_insight = "x" * 200

        injection = ContextInjection(
            past_errors=[],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[long_insight],
            total_token_estimate=50,
        )

        result = injector.format_for_prompt(injection)

        # Should be truncated to 150 chars (not the full 200)
        assert "x" * 150 in result
        assert "x" * 151 not in result
