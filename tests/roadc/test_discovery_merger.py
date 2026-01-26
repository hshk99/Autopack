"""Tests for discovery_context_merger.py (IMP-DISC-001).

Tests cover:
- DiscoveryInsight dataclass
- DiscoveryContextMerger.merge_sources()
- DiscoveryContextMerger.deduplicate()
- DiscoveryContextMerger.rank_by_relevance()
"""

from unittest.mock import patch

from autopack.roadc.discovery_context_merger import (
    DiscoveryContextMerger,
    DiscoveryInsight,
)


class TestDiscoveryInsight:
    """Tests for DiscoveryInsight dataclass."""

    def test_discovery_insight_creation(self):
        """DiscoveryInsight should be creatable with required fields."""
        insight = DiscoveryInsight(
            content="Test content",
            source="github",
        )

        assert insight.content == "Test content"
        assert insight.source == "github"
        assert insight.relevance_score == 0.0
        assert insight.url is None
        assert insight.metadata is None

    def test_discovery_insight_with_all_fields(self):
        """DiscoveryInsight should accept all optional fields."""
        insight = DiscoveryInsight(
            content="Test content",
            source="reddit",
            relevance_score=0.8,
            url="https://reddit.com/r/test",
            metadata={"subreddit": "python"},
        )

        assert insight.relevance_score == 0.8
        assert insight.url == "https://reddit.com/r/test"
        assert insight.metadata == {"subreddit": "python"}


class TestDiscoveryContextMergerInit:
    """Tests for DiscoveryContextMerger initialization."""

    def test_merger_init_with_no_credentials(self):
        """Merger should initialize without credentials."""
        merger = DiscoveryContextMerger()

        assert merger._github_token is None
        assert merger._reddit_client_id is None
        assert merger._reddit_client_secret is None

    def test_merger_init_with_credentials(self):
        """Merger should accept API credentials."""
        merger = DiscoveryContextMerger(
            github_token="gh_token",
            reddit_client_id="reddit_id",
            reddit_client_secret="reddit_secret",
        )

        assert merger._github_token == "gh_token"
        assert merger._reddit_client_id == "reddit_id"
        assert merger._reddit_client_secret == "reddit_secret"


class TestDiscoveryContextMergerMergeSources:
    """Tests for merge_sources method."""

    def test_merge_sources_returns_list(self):
        """merge_sources should return a list of DiscoveryInsight."""
        merger = DiscoveryContextMerger()

        with (
            patch.object(merger, "_fetch_github_insights", return_value=[]),
            patch.object(merger, "_fetch_reddit_insights", return_value=[]),
            patch.object(merger, "_fetch_web_insights", return_value=[]),
        ):
            result = merger.merge_sources(query="test query")

            assert isinstance(result, list)

    def test_merge_sources_combines_all_sources(self):
        """merge_sources should combine results from all sources."""
        merger = DiscoveryContextMerger()

        github_insight = DiscoveryInsight(content="github result", source="github")
        reddit_insight = DiscoveryInsight(content="reddit result", source="reddit")
        web_insight = DiscoveryInsight(content="web result", source="web")

        with (
            patch.object(merger, "_fetch_github_insights", return_value=[github_insight]),
            patch.object(merger, "_fetch_reddit_insights", return_value=[reddit_insight]),
            patch.object(merger, "_fetch_web_insights", return_value=[web_insight]),
        ):
            result = merger.merge_sources(query="test query")

            assert len(result) == 3
            sources = {r.source for r in result}
            assert sources == {"github", "reddit", "web"}

    def test_merge_sources_filters_by_source(self):
        """merge_sources should only query specified sources."""
        merger = DiscoveryContextMerger()

        github_insight = DiscoveryInsight(content="github result", source="github")

        with (
            patch.object(
                merger, "_fetch_github_insights", return_value=[github_insight]
            ) as mock_github,
            patch.object(merger, "_fetch_reddit_insights", return_value=[]) as mock_reddit,
            patch.object(merger, "_fetch_web_insights", return_value=[]) as mock_web,
        ):
            result = merger.merge_sources(query="test query", sources=["github"])

            mock_github.assert_called_once()
            mock_reddit.assert_not_called()
            mock_web.assert_not_called()
            assert len(result) == 1

    def test_merge_sources_handles_fetch_errors(self):
        """merge_sources should continue if one source fails."""
        merger = DiscoveryContextMerger()

        web_insight = DiscoveryInsight(content="web result", source="web")

        with (
            patch.object(merger, "_fetch_github_insights", side_effect=Exception("API error")),
            patch.object(merger, "_fetch_reddit_insights", side_effect=Exception("API error")),
            patch.object(merger, "_fetch_web_insights", return_value=[web_insight]),
        ):
            result = merger.merge_sources(query="test query")

            # Should still return web results despite errors
            assert len(result) == 1
            assert result[0].source == "web"


class TestDiscoveryContextMergerDeduplicate:
    """Tests for deduplicate method."""

    def test_deduplicate_removes_exact_duplicates(self):
        """deduplicate should remove exact content duplicates."""
        merger = DiscoveryContextMerger()

        insights = [
            DiscoveryInsight(content="same content", source="github"),
            DiscoveryInsight(content="same content", source="reddit"),
            DiscoveryInsight(content="different content", source="web"),
        ]

        result = merger.deduplicate(insights)

        assert len(result) == 2
        contents = {r.content for r in result}
        assert "different content" in contents

    def test_deduplicate_keeps_higher_relevance(self):
        """deduplicate should keep the insight with higher relevance score."""
        merger = DiscoveryContextMerger()

        insights = [
            DiscoveryInsight(content="duplicate content", source="github", relevance_score=0.5),
            DiscoveryInsight(content="duplicate content", source="reddit", relevance_score=0.9),
        ]

        result = merger.deduplicate(insights)

        assert len(result) == 1
        assert result[0].relevance_score == 0.9

    def test_deduplicate_handles_empty_list(self):
        """deduplicate should handle empty input."""
        merger = DiscoveryContextMerger()

        result = merger.deduplicate([])

        assert result == []

    def test_deduplicate_normalizes_whitespace(self):
        """deduplicate should treat content with different whitespace as same."""
        merger = DiscoveryContextMerger()

        insights = [
            DiscoveryInsight(content="same   content", source="github"),
            DiscoveryInsight(content="same content", source="reddit"),
        ]

        result = merger.deduplicate(insights)

        assert len(result) == 1


class TestDiscoveryContextMergerRankByRelevance:
    """Tests for rank_by_relevance method."""

    def test_rank_by_relevance_returns_strings(self):
        """rank_by_relevance should return list of formatted strings."""
        merger = DiscoveryContextMerger()

        insights = [
            DiscoveryInsight(content="python error fix", source="github"),
        ]

        result = merger.rank_by_relevance(insights, context="python error")

        assert isinstance(result, list)
        assert all(isinstance(r, str) for r in result)

    def test_rank_by_relevance_includes_source_prefix(self):
        """rank_by_relevance should prefix content with source."""
        merger = DiscoveryContextMerger()

        insights = [
            DiscoveryInsight(content="test content", source="github"),
        ]

        result = merger.rank_by_relevance(insights, context="test")

        assert result[0].startswith("[GITHUB]")

    def test_rank_by_relevance_sorts_by_relevance(self):
        """rank_by_relevance should sort by keyword overlap."""
        merger = DiscoveryContextMerger()

        insights = [
            DiscoveryInsight(content="unrelated content", source="web"),
            DiscoveryInsight(content="python error handling fix", source="github"),
            DiscoveryInsight(content="error handling", source="reddit"),
        ]

        result = merger.rank_by_relevance(insights, context="python error handling")

        # Python error handling fix should rank higher due to more keyword overlap
        assert "python error handling fix" in result[0].lower()

    def test_rank_by_relevance_handles_empty_list(self):
        """rank_by_relevance should handle empty input."""
        merger = DiscoveryContextMerger()

        result = merger.rank_by_relevance([], context="test")

        assert result == []

    def test_rank_by_relevance_truncates_long_content(self):
        """rank_by_relevance should truncate content to 200 chars."""
        merger = DiscoveryContextMerger()

        long_content = "x" * 300
        insights = [
            DiscoveryInsight(content=long_content, source="github"),
        ]

        result = merger.rank_by_relevance(insights, context="test")

        # [GITHUB] prefix + 200 chars of content
        assert len(result[0]) <= 210  # [GITHUB] is 8 chars + space + 200 content


class TestDiscoveryContextMergerHelpers:
    """Tests for helper methods."""

    def test_normalize_content(self):
        """_normalize_content should lowercase and collapse whitespace."""
        merger = DiscoveryContextMerger()

        result = merger._normalize_content("  Test   CONTENT  here  ")

        assert result == "test content here"

    def test_content_similarity_identical(self):
        """_content_similarity should return 1.0 for identical content."""
        merger = DiscoveryContextMerger()

        result = merger._content_similarity("same words", "same words")

        assert result == 1.0

    def test_content_similarity_different(self):
        """_content_similarity should return 0.0 for completely different content."""
        merger = DiscoveryContextMerger()

        result = merger._content_similarity("abc def", "xyz uvw")

        assert result == 0.0

    def test_content_similarity_partial(self):
        """_content_similarity should return partial score for overlapping content."""
        merger = DiscoveryContextMerger()

        # 2 common words out of 4 total unique words = 0.5
        result = merger._content_similarity("word1 word2", "word1 word3")

        assert 0.3 < result < 0.7

    def test_content_similarity_empty(self):
        """_content_similarity should return 0.0 for empty content."""
        merger = DiscoveryContextMerger()

        result = merger._content_similarity("", "some content")

        assert result == 0.0
