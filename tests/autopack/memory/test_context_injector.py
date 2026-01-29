"""Tests for context_injector.py (IMP-DISC-001, IMP-LOOP-019).

Tests cover:
- ContextInjection dataclass with discovery_insights field
- get_context_for_phase method integration with discovery context
- get_discovery_context method
- format_for_prompt including discovery insights
- IMP-LOOP-019: EnrichedContextInjection with metadata
- IMP-LOOP-019: get_context_for_phase_with_metadata method
- IMP-LOOP-019: format_enriched_for_prompt with confidence warnings
"""

from unittest.mock import MagicMock, Mock, patch

from autopack.memory.context_injector import (ContextInjection,
                                              ContextInjector,
                                              EnrichedContextInjection)
from autopack.memory.memory_service import ContextMetadata


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


# ---------------------------------------------------------------------------
# IMP-LOOP-019: Context Relevance/Confidence Metadata Tests
# ---------------------------------------------------------------------------


class TestContextMetadataDataclass:
    """Tests for ContextMetadata dataclass."""

    def test_context_metadata_has_required_fields(self):
        """IMP-LOOP-019: ContextMetadata should have all required fields."""
        metadata = ContextMetadata(
            content="test content",
            relevance_score=0.85,
            age_hours=12.5,
            confidence=0.75,
            is_low_confidence=False,
            source_type="error",
            source_id="error:123",
        )

        assert metadata.content == "test content"
        assert metadata.relevance_score == 0.85
        assert metadata.age_hours == 12.5
        assert metadata.confidence == 0.75
        assert metadata.is_low_confidence is False
        assert metadata.source_type == "error"
        assert metadata.source_id == "error:123"

    def test_context_metadata_confidence_level_property(self):
        """IMP-LOOP-019: confidence_level should return human-readable level."""
        # High confidence
        high = ContextMetadata(
            content="test",
            relevance_score=0.9,
            age_hours=1.0,
            confidence=0.7,
            is_low_confidence=False,
        )
        assert high.confidence_level == "high"

        # Medium confidence
        medium = ContextMetadata(
            content="test",
            relevance_score=0.5,
            age_hours=50.0,
            confidence=0.45,
            is_low_confidence=False,
        )
        assert medium.confidence_level == "medium"

        # Low confidence
        low = ContextMetadata(
            content="test",
            relevance_score=0.2,
            age_hours=200.0,
            confidence=0.2,
            is_low_confidence=True,
        )
        assert low.confidence_level == "low"


class TestEnrichedContextInjectionDataclass:
    """Tests for EnrichedContextInjection dataclass."""

    def test_enriched_context_injection_has_metadata_fields(self):
        """IMP-LOOP-019: EnrichedContextInjection should have metadata fields."""
        error_meta = ContextMetadata(
            content="error1",
            relevance_score=0.8,
            age_hours=5.0,
            confidence=0.7,
            is_low_confidence=False,
        )

        enriched = EnrichedContextInjection(
            past_errors=[error_meta],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=["discovery1"],
            total_token_estimate=100,
            quality_summary={"total_items": 1, "low_confidence_count": 0},
            has_low_confidence_warning=False,
        )

        assert len(enriched.past_errors) == 1
        assert enriched.past_errors[0].content == "error1"
        assert enriched.quality_summary["total_items"] == 1
        assert enriched.has_low_confidence_warning is False

    def test_enriched_context_injection_to_plain_injection(self):
        """IMP-LOOP-019: to_plain_injection should convert to ContextInjection."""
        error_meta = ContextMetadata(
            content="error1",
            relevance_score=0.8,
            age_hours=5.0,
            confidence=0.7,
            is_low_confidence=False,
        )
        strategy_meta = ContextMetadata(
            content="strategy1",
            relevance_score=0.9,
            age_hours=10.0,
            confidence=0.8,
            is_low_confidence=False,
        )

        enriched = EnrichedContextInjection(
            past_errors=[error_meta],
            successful_strategies=[strategy_meta],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=["discovery1"],
            total_token_estimate=100,
        )

        plain = enriched.to_plain_injection()

        assert isinstance(plain, ContextInjection)
        assert plain.past_errors == ["error1"]
        assert plain.successful_strategies == ["strategy1"]
        assert plain.discovery_insights == ["discovery1"]

    def test_enriched_context_injection_avg_confidence_property(self):
        """IMP-LOOP-019: avg_confidence should calculate average."""
        meta1 = ContextMetadata(
            content="c1",
            relevance_score=0.8,
            age_hours=5.0,
            confidence=0.6,
            is_low_confidence=False,
        )
        meta2 = ContextMetadata(
            content="c2",
            relevance_score=0.9,
            age_hours=10.0,
            confidence=0.8,
            is_low_confidence=False,
        )

        enriched = EnrichedContextInjection(
            past_errors=[meta1],
            successful_strategies=[meta2],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=100,
        )

        assert enriched.avg_confidence == 0.7  # (0.6 + 0.8) / 2

    def test_enriched_context_injection_low_confidence_count_property(self):
        """IMP-LOOP-019: low_confidence_count should count low confidence items."""
        high_conf = ContextMetadata(
            content="c1",
            relevance_score=0.8,
            age_hours=5.0,
            confidence=0.7,
            is_low_confidence=False,
        )
        low_conf = ContextMetadata(
            content="c2",
            relevance_score=0.2,
            age_hours=200.0,
            confidence=0.2,
            is_low_confidence=True,
        )

        enriched = EnrichedContextInjection(
            past_errors=[high_conf, low_conf],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=100,
        )

        assert enriched.low_confidence_count == 1


class TestContextInjectorGetContextForPhaseWithMetadata:
    """Tests for get_context_for_phase_with_metadata method."""

    def test_get_context_for_phase_with_metadata_returns_enriched_injection(self):
        """IMP-LOOP-019: Should return EnrichedContextInjection."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.retrieve_context_with_metadata.return_value = {
            "errors": [],
            "summaries": [],
            "hints": [],
            "code": [],
        }

        injector = ContextInjector(memory_service=mock_memory)

        with patch.object(injector, "get_discovery_context", return_value=[]):
            result = injector.get_context_for_phase_with_metadata(
                phase_type="build",
                current_goal="fix compilation",
                project_id="test-project",
            )

            assert isinstance(result, EnrichedContextInjection)

    def test_get_context_for_phase_with_metadata_memory_disabled(self):
        """IMP-LOOP-019: Should return empty when memory disabled."""
        mock_memory = Mock()
        mock_memory.enabled = False

        injector = ContextInjector(memory_service=mock_memory)

        result = injector.get_context_for_phase_with_metadata(
            phase_type="build",
            current_goal="fix compilation",
            project_id="test-project",
        )

        assert isinstance(result, EnrichedContextInjection)
        assert len(result.past_errors) == 0
        assert result.has_low_confidence_warning is False

    def test_get_context_for_phase_with_metadata_includes_quality_summary(self):
        """IMP-LOOP-019: Should include quality_summary in result."""
        mock_memory = Mock()
        mock_memory.enabled = True

        error_meta = ContextMetadata(
            content="error1",
            relevance_score=0.8,
            age_hours=5.0,
            confidence=0.7,
            is_low_confidence=False,
        )

        mock_memory.retrieve_context_with_metadata.return_value = {
            "errors": [error_meta],
            "summaries": [],
            "hints": [],
            "code": [],
        }

        injector = ContextInjector(memory_service=mock_memory)

        with patch.object(injector, "get_discovery_context", return_value=[]):
            result = injector.get_context_for_phase_with_metadata(
                phase_type="build",
                current_goal="fix compilation",
                project_id="test-project",
            )

            assert "total_items" in result.quality_summary
            assert "avg_confidence" in result.quality_summary


class TestContextInjectorFormatEnrichedForPrompt:
    """Tests for format_enriched_for_prompt method."""

    def test_format_enriched_for_prompt_basic(self):
        """IMP-LOOP-019: Should format enriched context correctly."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        error_meta = ContextMetadata(
            content="ImportError in module",
            relevance_score=0.85,
            age_hours=5.0,
            confidence=0.75,
            is_low_confidence=False,
        )

        enriched = EnrichedContextInjection(
            past_errors=[error_meta],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=50,
            has_low_confidence_warning=False,
        )

        result = injector.format_enriched_for_prompt(enriched)

        assert "Past Errors to Avoid" in result
        assert "ImportError in module" in result
        assert "low confidence" not in result.lower()

    def test_format_enriched_for_prompt_with_low_confidence_warning(self):
        """IMP-LOOP-019: Should include warning when has_low_confidence_warning is True."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        low_conf_meta = ContextMetadata(
            content="Old error",
            relevance_score=0.3,
            age_hours=200.0,
            confidence=0.25,
            is_low_confidence=True,
        )

        enriched = EnrichedContextInjection(
            past_errors=[low_conf_meta],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=50,
            quality_summary={"avg_confidence": 0.25},
            has_low_confidence_warning=True,
        )

        result = injector.format_enriched_for_prompt(enriched)

        assert "Context Quality Warning" in result
        assert "low confidence" in result.lower()

    def test_format_enriched_for_prompt_marks_low_confidence_items(self):
        """IMP-LOOP-019: Should mark individual low confidence items."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        high_conf = ContextMetadata(
            content="Recent error",
            relevance_score=0.9,
            age_hours=5.0,
            confidence=0.8,
            is_low_confidence=False,
        )
        low_conf = ContextMetadata(
            content="Old error",
            relevance_score=0.3,
            age_hours=200.0,
            confidence=0.25,
            is_low_confidence=True,
        )

        enriched = EnrichedContextInjection(
            past_errors=[high_conf, low_conf],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=50,
            has_low_confidence_warning=False,
        )

        result = injector.format_enriched_for_prompt(enriched)

        assert "Recent error" in result
        assert "Old error" in result
        # Only the low confidence item should be marked
        assert result.count("_(low confidence)_") == 1

    def test_format_enriched_for_prompt_without_confidence_warnings(self):
        """IMP-LOOP-019: Should omit confidence warnings when disabled."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        low_conf = ContextMetadata(
            content="Old error",
            relevance_score=0.3,
            age_hours=200.0,
            confidence=0.25,
            is_low_confidence=True,
        )

        enriched = EnrichedContextInjection(
            past_errors=[low_conf],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=50,
            has_low_confidence_warning=True,
        )

        result = injector.format_enriched_for_prompt(enriched, include_confidence_warnings=False)

        assert "Context Quality Warning" not in result
        assert "_(low confidence)_" not in result


# ---------------------------------------------------------------------------
# IMP-MEM-002: Cross-Phase Conflict Detection Tests
# ---------------------------------------------------------------------------


class TestExtractTopic:
    """Tests for _extract_topic method."""

    def test_extract_topic_from_technical_term(self):
        """IMP-MEM-002: Should extract technical terms as topics."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        assert injector._extract_topic("Always use async for I/O operations") == "async"
        assert injector._extract_topic("Prefer caching for repeated queries") == "caching"
        assert injector._extract_topic("Add proper error handling") == "error"

    def test_extract_topic_empty_content(self):
        """IMP-MEM-002: Should handle empty content."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        assert injector._extract_topic("") == ""
        assert injector._extract_topic(None) == ""

    def test_extract_topic_removes_common_prefixes(self):
        """IMP-MEM-002: Should remove 'always', 'never' prefixes."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        # Both should extract 'async' as topic
        topic1 = injector._extract_topic("Always use async patterns")
        topic2 = injector._extract_topic("Never use async patterns")
        assert topic1 == topic2 == "async"


class TestAreConflicting:
    """Tests for _are_conflicting method."""

    def test_conflicting_use_vs_avoid(self):
        """IMP-MEM-002: Should detect 'use' vs 'avoid' contradiction."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        assert injector._are_conflicting(
            "Use async for database calls",
            "Avoid async for database calls",
        )

    def test_conflicting_always_vs_never(self):
        """IMP-MEM-002: Should detect 'always' vs 'never' contradiction."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        assert injector._are_conflicting(
            "Always enable caching in production",
            "Never enable caching in production",
        )

    def test_conflicting_do_vs_dont(self):
        """IMP-MEM-002: Should detect 'do' vs 'don't' contradiction."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        assert injector._are_conflicting(
            "Do add retry logic for API calls",
            "Don't add retry logic for API calls",
        )

    def test_not_conflicting_different_topics(self):
        """IMP-MEM-002: Should not flag hints about different topics."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        assert not injector._are_conflicting(
            "Use async for I/O operations",
            "Avoid caching for real-time data",
        )

    def test_not_conflicting_same_advice(self):
        """IMP-MEM-002: Should not flag hints with same advice."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        assert not injector._are_conflicting(
            "Use async for database calls",
            "Use async for network operations",
        )

    def test_not_conflicting_empty_content(self):
        """IMP-MEM-002: Should handle empty content gracefully."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        assert not injector._are_conflicting("", "Some hint")
        assert not injector._are_conflicting("Some hint", "")
        assert not injector._are_conflicting("", "")


class TestResolveConflicts:
    """Tests for _resolve_conflicts method."""

    def test_resolve_conflicts_keeps_higher_confidence(self):
        """IMP-MEM-002: Should keep hint with higher confidence."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        high_conf = ContextMetadata(
            content="Use async for database calls",
            relevance_score=0.9,
            age_hours=5.0,
            confidence=0.8,
            is_low_confidence=False,
        )
        low_conf = ContextMetadata(
            content="Avoid async for database calls",
            relevance_score=0.7,
            age_hours=10.0,
            confidence=0.4,
            is_low_confidence=True,
        )

        result, conflicts = injector._resolve_conflicts([low_conf, high_conf])

        assert len(result) == 1
        assert result[0].content == "Use async for database calls"
        assert conflicts == 1

    def test_resolve_conflicts_no_conflicts(self):
        """IMP-MEM-002: Should return all hints when no conflicts."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        hint1 = ContextMetadata(
            content="Use async for I/O",
            relevance_score=0.9,
            age_hours=5.0,
            confidence=0.8,
            is_low_confidence=False,
        )
        hint2 = ContextMetadata(
            content="Enable caching for reads",
            relevance_score=0.7,
            age_hours=10.0,
            confidence=0.6,
            is_low_confidence=False,
        )

        result, conflicts = injector._resolve_conflicts([hint1, hint2])

        assert len(result) == 2
        assert conflicts == 0

    def test_resolve_conflicts_empty_list(self):
        """IMP-MEM-002: Should handle empty list."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        result, conflicts = injector._resolve_conflicts([])

        assert result == []
        assert conflicts == 0

    def test_resolve_conflicts_multiple_conflicts(self):
        """IMP-MEM-002: Should resolve multiple conflicts."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        hints = [
            ContextMetadata(
                content="Use async patterns",
                relevance_score=0.9,
                age_hours=5.0,
                confidence=0.9,
                is_low_confidence=False,
            ),
            ContextMetadata(
                content="Avoid async patterns",
                relevance_score=0.7,
                age_hours=10.0,
                confidence=0.3,
                is_low_confidence=True,
            ),
            ContextMetadata(
                content="Enable caching",
                relevance_score=0.8,
                age_hours=8.0,
                confidence=0.7,
                is_low_confidence=False,
            ),
            ContextMetadata(
                content="Disable caching",
                relevance_score=0.6,
                age_hours=15.0,
                confidence=0.4,
                is_low_confidence=True,
            ),
        ]

        result, conflicts = injector._resolve_conflicts(hints)

        assert len(result) == 2
        assert conflicts == 2
        # Should keep higher confidence versions
        contents = [h.content for h in result]
        assert "Use async patterns" in contents
        assert "Enable caching" in contents


class TestResolveConflictsPlain:
    """Tests for _resolve_conflicts_plain method."""

    def test_resolve_conflicts_plain_keeps_first(self):
        """IMP-MEM-002: Should keep first hint when conflicts exist."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        hints = [
            "Use async for database calls",
            "Avoid async for database calls",
        ]

        result, conflicts = injector._resolve_conflicts_plain(hints)

        assert len(result) == 1
        assert result[0] == "Use async for database calls"
        assert conflicts == 1

    def test_resolve_conflicts_plain_no_conflicts(self):
        """IMP-MEM-002: Should return all when no conflicts."""
        mock_memory = Mock()
        mock_memory.enabled = True

        injector = ContextInjector(memory_service=mock_memory)

        hints = [
            "Use async for I/O",
            "Enable caching for reads",
        ]

        result, conflicts = injector._resolve_conflicts_plain(hints)

        assert len(result) == 2
        assert conflicts == 0


class TestConflictResolutionIntegration:
    """Integration tests for conflict resolution in context retrieval."""

    def test_get_context_for_phase_with_metadata_resolves_conflicts(self):
        """IMP-MEM-002: Should resolve conflicts in enriched context retrieval."""
        mock_memory = Mock()
        mock_memory.enabled = True

        # Create conflicting hints
        hint1 = ContextMetadata(
            content="Use async patterns",
            relevance_score=0.9,
            age_hours=5.0,
            confidence=0.8,
            is_low_confidence=False,
        )
        hint2 = ContextMetadata(
            content="Avoid async patterns",
            relevance_score=0.7,
            age_hours=10.0,
            confidence=0.4,
            is_low_confidence=True,
        )

        mock_memory.retrieve_context_with_metadata.return_value = {
            "errors": [],
            "summaries": [],
            "hints": [hint1, hint2],
            "code": [],
        }

        injector = ContextInjector(memory_service=mock_memory)

        with patch.object(injector, "get_discovery_context", return_value=[]):
            result = injector.get_context_for_phase_with_metadata(
                phase_type="build",
                current_goal="fix compilation",
                project_id="test-project",
            )

            # Should have resolved conflicts
            assert len(result.doctor_hints) == 1
            assert result.doctor_hints[0].content == "Use async patterns"
            assert result.quality_summary.get("conflicts_resolved", 0) == 1

    def test_get_context_for_phase_resolves_conflicts(self):
        """IMP-MEM-002: Should resolve conflicts in plain context retrieval."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.search_errors.return_value = []
        mock_memory.search_summaries.return_value = []
        mock_memory.search_code.return_value = []

        # Return conflicting hints
        mock_memory.search_doctor_hints.return_value = [
            {"payload": {"hint": "Use async patterns"}},
            {"payload": {"hint": "Avoid async patterns"}},
        ]

        injector = ContextInjector(memory_service=mock_memory)

        with patch.object(injector, "get_discovery_context", return_value=[]):
            result = injector.get_context_for_phase(
                phase_type="build",
                current_goal="fix compilation",
                project_id="test-project",
            )

            # Should have resolved conflicts
            assert len(result.doctor_hints) == 1
            assert result.doctor_hints[0] == "Use async patterns"


# IMP-LOOP-024: Tests for mandating EnrichedContextInjection everywhere


class TestDeprecationWarnings:
    """Tests for deprecation warnings on legacy methods (IMP-LOOP-024)."""

    def test_get_context_for_phase_raises_deprecation_warning(self):
        """IMP-LOOP-024: get_context_for_phase should emit deprecation warning."""
        import warnings

        mock_memory = Mock()
        mock_memory.enabled = False

        injector = ContextInjector(memory_service=mock_memory)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            injector.get_context_for_phase(
                phase_type="build",
                current_goal="test",
                project_id="test-project",
            )

            # Check that a deprecation warning was issued
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "get_context_for_phase_with_metadata" in str(w[0].message)
            assert "IMP-LOOP-024" in str(w[0].message)

    def test_format_for_prompt_raises_deprecation_warning(self):
        """IMP-LOOP-024: format_for_prompt should emit deprecation warning."""
        import warnings

        mock_memory = Mock()
        injector = ContextInjector(memory_service=mock_memory)

        injection = ContextInjection(
            past_errors=["error1"],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=10,
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            injector.format_for_prompt(injection)

            # Check that a deprecation warning was issued
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "format_enriched_for_prompt" in str(w[0].message)
            assert "IMP-LOOP-024" in str(w[0].message)


class TestEnrichedContextMandated:
    """Tests verifying enriched context is mandated (IMP-LOOP-024)."""

    def test_enriched_injection_has_metadata_fields(self):
        """IMP-LOOP-024: EnrichedContextInjection has required metadata."""
        error_meta = ContextMetadata(
            content="error content",
            relevance_score=0.9,
            age_hours=10.0,
            confidence=0.85,
            is_low_confidence=False,
        )

        enriched = EnrichedContextInjection(
            past_errors=[error_meta],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=50,
            quality_summary={"total_items": 1, "avg_confidence": 0.85},
            has_low_confidence_warning=False,
        )

        # Verify metadata is accessible
        assert len(enriched.past_errors) == 1
        assert enriched.past_errors[0].relevance_score == 0.9
        assert enriched.past_errors[0].age_hours == 10.0
        assert enriched.past_errors[0].confidence == 0.85
        assert enriched.avg_confidence == 0.85

    def test_enriched_injection_to_plain_preserves_content(self):
        """IMP-LOOP-024: to_plain_injection extracts content strings."""
        error_meta = ContextMetadata(
            content="error content",
            relevance_score=0.9,
            age_hours=10.0,
            confidence=0.85,
            is_low_confidence=False,
        )

        enriched = EnrichedContextInjection(
            past_errors=[error_meta],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=["discovery1"],
            total_token_estimate=50,
        )

        plain = enriched.to_plain_injection()

        assert isinstance(plain, ContextInjection)
        assert plain.past_errors == ["error content"]
        assert plain.discovery_insights == ["discovery1"]

    def test_get_context_for_phase_with_metadata_preferred(self):
        """IMP-LOOP-024: get_context_for_phase_with_metadata returns EnrichedContextInjection."""
        mock_memory = Mock()
        mock_memory.enabled = True
        mock_memory.retrieve_context_with_metadata.return_value = {
            "errors": [],
            "summaries": [],
            "hints": [],
            "code": [],
        }

        injector = ContextInjector(memory_service=mock_memory)

        with patch.object(injector, "get_discovery_context", return_value=[]):
            result = injector.get_context_for_phase_with_metadata(
                phase_type="build",
                current_goal="test goal",
                project_id="test-project",
            )

        # Should return EnrichedContextInjection, not plain ContextInjection
        assert isinstance(result, EnrichedContextInjection)
        assert hasattr(result, "quality_summary")
        assert hasattr(result, "has_low_confidence_warning")
        assert hasattr(result, "avg_confidence")

    def test_format_enriched_includes_confidence_warning(self):
        """IMP-LOOP-024: format_enriched_for_prompt includes confidence warnings."""
        mock_memory = Mock()
        injector = ContextInjector(memory_service=mock_memory)

        low_confidence_error = ContextMetadata(
            content="low confidence error",
            relevance_score=0.5,
            age_hours=100.0,
            confidence=0.3,
            is_low_confidence=True,
        )

        enriched = EnrichedContextInjection(
            past_errors=[low_confidence_error],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],
            total_token_estimate=50,
            quality_summary={"avg_confidence": 0.3},
            has_low_confidence_warning=True,
        )

        formatted = injector.format_enriched_for_prompt(enriched, include_confidence_warnings=True)

        assert "Context Quality Warning" in formatted
        assert "low confidence" in formatted.lower()
