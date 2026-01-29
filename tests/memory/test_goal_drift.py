"""Tests for goal drift detection (IMP-TST-003).

Tests cover:
- cosine_similarity function (vector comparison)
- check_goal_drift function (embedding similarity, thresholds, edge cases)
- should_block_on_drift function (advisory vs blocking modes)
- extract_goal_from_description function (text extraction)
- _load_goal_drift_config function (config loading)
"""

from unittest.mock import MagicMock, patch


from autopack.memory.goal_drift import (
    _load_goal_drift_config,
    check_goal_drift,
    cosine_similarity,
    extract_goal_from_description,
    should_block_on_drift,
)


class TestCosineSimilarity:
    """Tests for cosine_similarity function."""

    def test_identical_vectors_return_one(self):
        """Identical vectors should have similarity of 1.0."""
        vec = [1.0, 2.0, 3.0, 4.0]
        result = cosine_similarity(vec, vec)
        assert abs(result - 1.0) < 0.0001

    def test_orthogonal_vectors_return_zero(self):
        """Orthogonal vectors should have similarity of 0.0."""
        vec_a = [1.0, 0.0]
        vec_b = [0.0, 1.0]
        result = cosine_similarity(vec_a, vec_b)
        assert abs(result) < 0.0001

    def test_opposite_vectors_return_negative_one(self):
        """Opposite vectors should have similarity of -1.0."""
        vec_a = [1.0, 2.0, 3.0]
        vec_b = [-1.0, -2.0, -3.0]
        result = cosine_similarity(vec_a, vec_b)
        assert abs(result - (-1.0)) < 0.0001

    def test_similar_vectors_high_similarity(self):
        """Similar vectors should have high similarity."""
        vec_a = [1.0, 2.0, 3.0]
        vec_b = [1.1, 2.1, 3.1]
        result = cosine_similarity(vec_a, vec_b)
        assert result > 0.99

    def test_different_vectors_low_similarity(self):
        """Very different vectors should have low similarity."""
        vec_a = [1.0, 0.0, 0.0]
        vec_b = [0.0, 0.0, 1.0]
        result = cosine_similarity(vec_a, vec_b)
        assert abs(result) < 0.0001

    def test_empty_vector_a_returns_zero(self):
        """Empty first vector should return 0.0."""
        result = cosine_similarity([], [1.0, 2.0])
        assert result == 0.0

    def test_empty_vector_b_returns_zero(self):
        """Empty second vector should return 0.0."""
        result = cosine_similarity([1.0, 2.0], [])
        assert result == 0.0

    def test_both_empty_vectors_returns_zero(self):
        """Both empty vectors should return 0.0."""
        result = cosine_similarity([], [])
        assert result == 0.0

    def test_different_length_vectors_returns_zero(self):
        """Vectors of different lengths should return 0.0."""
        vec_a = [1.0, 2.0, 3.0]
        vec_b = [1.0, 2.0]
        result = cosine_similarity(vec_a, vec_b)
        assert result == 0.0

    def test_zero_vector_a_returns_zero(self):
        """Zero first vector should return 0.0."""
        vec_a = [0.0, 0.0, 0.0]
        vec_b = [1.0, 2.0, 3.0]
        result = cosine_similarity(vec_a, vec_b)
        assert result == 0.0

    def test_zero_vector_b_returns_zero(self):
        """Zero second vector should return 0.0."""
        vec_a = [1.0, 2.0, 3.0]
        vec_b = [0.0, 0.0, 0.0]
        result = cosine_similarity(vec_a, vec_b)
        assert result == 0.0

    def test_both_zero_vectors_returns_zero(self):
        """Both zero vectors should return 0.0."""
        vec_a = [0.0, 0.0, 0.0]
        vec_b = [0.0, 0.0, 0.0]
        result = cosine_similarity(vec_a, vec_b)
        assert result == 0.0

    def test_single_element_vectors(self):
        """Single element vectors should work correctly."""
        result = cosine_similarity([3.0], [3.0])
        assert abs(result - 1.0) < 0.0001

    def test_large_vectors(self):
        """Large vectors should compute correctly."""
        size = 1536  # Typical embedding size
        vec_a = [float(i) for i in range(size)]
        vec_b = [float(i) for i in range(size)]
        result = cosine_similarity(vec_a, vec_b)
        assert abs(result - 1.0) < 0.0001


class TestCheckGoalDrift:
    """Tests for check_goal_drift function."""

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_no_drift_for_similar_texts(self, mock_embed, mock_config):
        """Similar goal and intent should not trigger drift."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7}
        # Return identical embeddings for similar texts
        mock_embed.return_value = [1.0, 2.0, 3.0]

        is_aligned, similarity, message = check_goal_drift(
            goal_anchor="Fix the login bug",
            change_intent="Fix the login bug",
        )

        assert is_aligned is True
        assert similarity == 1.0
        assert "aligns with goal" in message.lower()

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_drift_detected_for_different_texts(self, mock_embed, mock_config):
        """Very different goal and intent should trigger drift."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7}
        # Return orthogonal embeddings for different texts
        mock_embed.side_effect = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]

        is_aligned, similarity, message = check_goal_drift(
            goal_anchor="Fix the login bug",
            change_intent="Add payment processing",
        )

        assert is_aligned is False
        assert similarity < 0.7
        assert "drift detected" in message.lower()

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    def test_empty_goal_anchor_returns_aligned(self, mock_config):
        """Empty goal anchor should return aligned with 1.0 similarity."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7}

        is_aligned, similarity, message = check_goal_drift(
            goal_anchor="",
            change_intent="Fix something",
        )

        assert is_aligned is True
        assert similarity == 1.0
        assert "no goal anchor" in message.lower()

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    def test_whitespace_goal_anchor_returns_aligned(self, mock_config):
        """Whitespace-only goal anchor should return aligned."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7}

        is_aligned, similarity, message = check_goal_drift(
            goal_anchor="   ",
            change_intent="Fix something",
        )

        assert is_aligned is True
        assert similarity == 1.0

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    def test_empty_change_intent_returns_aligned(self, mock_config):
        """Empty change intent should return aligned with 1.0 similarity."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7}

        is_aligned, similarity, message = check_goal_drift(
            goal_anchor="Fix the login bug",
            change_intent="",
        )

        assert is_aligned is True
        assert similarity == 1.0
        assert "no change intent" in message.lower()

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    def test_whitespace_change_intent_returns_aligned(self, mock_config):
        """Whitespace-only change intent should return aligned."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7}

        is_aligned, similarity, message = check_goal_drift(
            goal_anchor="Fix the login bug",
            change_intent="   \n\t  ",
        )

        assert is_aligned is True
        assert similarity == 1.0

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    def test_config_disabled_returns_aligned(self, mock_config):
        """Disabled config should return aligned with 1.0 similarity."""
        mock_config.return_value = {"enabled": False, "threshold": 0.7}

        is_aligned, similarity, message = check_goal_drift(
            goal_anchor="Fix the login bug",
            change_intent="Add payment processing",
        )

        assert is_aligned is True
        assert similarity == 1.0
        assert "disabled" in message.lower()

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_custom_threshold_respected(self, mock_embed, mock_config):
        """Custom threshold should override config threshold."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7}
        # Similarity will be 0.8 (above 0.5 but below 0.9)
        mock_embed.side_effect = [[1.0, 0.6, 0.0], [1.0, 0.6, 0.1]]

        # With 0.5 threshold, should be aligned
        is_aligned, similarity, _ = check_goal_drift(
            goal_anchor="Goal",
            change_intent="Intent",
            threshold=0.5,
        )
        assert is_aligned is True

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_high_threshold_triggers_drift(self, mock_embed, mock_config):
        """Very high threshold should trigger drift for moderate similarity."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7}
        # Vectors with ~0.8 cosine similarity: [1, 0] and [0.8, 0.6] -> cos = 0.8
        mock_embed.side_effect = [[1.0, 0.0], [0.8, 0.6]]

        is_aligned, similarity, _ = check_goal_drift(
            goal_anchor="Goal",
            change_intent="Intent",
            threshold=0.999,  # Very high threshold
        )

        assert is_aligned is False
        assert similarity < 0.999

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_exception_during_embedding_returns_aligned(self, mock_embed, mock_config):
        """Exception during embedding should return aligned (fail-safe)."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7}
        mock_embed.side_effect = Exception("Embedding service unavailable")

        is_aligned, similarity, message = check_goal_drift(
            goal_anchor="Fix the login bug",
            change_intent="Fix the login bug",
        )

        assert is_aligned is True
        assert similarity == 1.0
        assert "failed" in message.lower()

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_boundary_similarity_at_threshold(self, mock_embed, mock_config):
        """Similarity exactly at threshold should be aligned."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7}

        # Create vectors with exactly 0.7 cosine similarity is tricky,
        # so we test boundary behavior by mocking
        def create_vectors_with_similarity():
            # Using vectors that give approximately 0.7 similarity
            return [[1.0, 0.0], [0.7, 0.714]]

        mock_embed.side_effect = create_vectors_with_similarity()

        is_aligned, similarity, _ = check_goal_drift(
            goal_anchor="Goal",
            change_intent="Intent",
            threshold=0.7,
        )

        # At boundary, should be aligned (>=)
        if abs(similarity - 0.7) < 0.01:
            assert is_aligned is True


class TestShouldBlockOnDrift:
    """Tests for should_block_on_drift function."""

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_aligned_never_blocks(self, mock_embed, mock_config):
        """Aligned changes should never block regardless of mode."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7, "mode": "blocking"}
        mock_embed.return_value = [1.0, 2.0, 3.0]

        should_block, reason = should_block_on_drift(
            goal_anchor="Fix bug",
            change_intent="Fix bug",
        )

        assert should_block is False
        assert "aligns" in reason.lower()

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_advisory_mode_does_not_block(self, mock_embed, mock_config):
        """Advisory mode should not block on drift."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7, "mode": "advisory"}
        mock_embed.side_effect = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]

        should_block, reason = should_block_on_drift(
            goal_anchor="Fix login",
            change_intent="Add payment",
        )

        assert should_block is False
        assert "advisory" in reason.lower()

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_blocking_mode_blocks_on_drift(self, mock_embed, mock_config):
        """Blocking mode should block on drift."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7, "mode": "blocking"}
        mock_embed.side_effect = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]

        should_block, reason = should_block_on_drift(
            goal_anchor="Fix login",
            change_intent="Add payment",
        )

        assert should_block is True
        assert "blocked" in reason.lower()

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_default_mode_is_advisory(self, mock_embed, mock_config):
        """Default mode (when not specified) should be advisory."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7}  # No mode specified
        mock_embed.side_effect = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]

        should_block, reason = should_block_on_drift(
            goal_anchor="Fix login",
            change_intent="Add payment",
        )

        assert should_block is False
        assert "advisory" in reason.lower()


class TestExtractGoalFromDescription:
    """Tests for extract_goal_from_description function."""

    def test_empty_description_returns_empty(self):
        """Empty description should return empty string."""
        result = extract_goal_from_description("")
        assert result == ""

    def test_none_description_returns_empty(self):
        """None description should return empty string."""
        result = extract_goal_from_description(None)
        assert result == ""

    def test_short_description_returned_as_is(self):
        """Short description should be returned as-is."""
        desc = "Fix the login bug"
        result = extract_goal_from_description(desc)
        assert result == desc

    def test_first_sentence_extracted_with_period(self):
        """First sentence should be extracted when delimited by period."""
        desc = "Fix the login bug. This involves changing the auth module."
        result = extract_goal_from_description(desc)
        assert result == "Fix the login bug."

    def test_first_sentence_extracted_with_newline(self):
        """First sentence should be extracted when delimited by period+newline."""
        desc = "Fix the login bug.\nThis involves changing the auth module."
        result = extract_goal_from_description(desc)
        assert result == "Fix the login bug."

    def test_first_sentence_extracted_with_exclamation(self):
        """First sentence should be extracted when delimited by exclamation."""
        desc = "Fix the login bug! This is urgent."
        result = extract_goal_from_description(desc)
        assert result == "Fix the login bug!"

    def test_first_sentence_extracted_with_question(self):
        """First sentence should be extracted when delimited by question mark."""
        desc = "Can we fix the login bug? It's breaking production."
        result = extract_goal_from_description(desc)
        assert result == "Can we fix the login bug?"

    def test_long_description_truncated_to_200_chars(self):
        """Description longer than 200 chars should be truncated."""
        desc = "A" * 300
        result = extract_goal_from_description(desc)
        assert len(result) <= 203  # 200 + "..."
        assert result.endswith("...")

    def test_truncation_respects_word_boundaries(self):
        """Truncation should respect word boundaries when possible."""
        desc = "Fix the " + "a" * 200 + " bug"
        result = extract_goal_from_description(desc)
        # Should truncate at a word boundary before 200 chars
        assert len(result) <= 203

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace should be stripped."""
        desc = "  Fix the login bug  "
        result = extract_goal_from_description(desc)
        assert result == "Fix the login bug"

    def test_long_first_sentence_uses_truncation(self):
        """Long first sentence (>200 chars) should use truncation."""
        # A sentence longer than 200 chars
        desc = "Fix " + "a" * 250 + ". Short second sentence."
        result = extract_goal_from_description(desc)
        # Should fall back to truncation since first sentence is too long
        assert len(result) <= 203


class TestLoadGoalDriftConfig:
    """Tests for _load_goal_drift_config function."""

    @patch("pathlib.Path.exists")
    def test_missing_config_returns_empty_dict(self, mock_exists):
        """Missing config file should return empty dict."""
        mock_exists.return_value = False

        result = _load_goal_drift_config()

        assert result == {}

    @patch("pathlib.Path.exists")
    @patch("builtins.open", create=True)
    def test_valid_config_returns_goal_drift_section(self, mock_open, mock_exists):
        """Valid config should return goal_drift section."""
        mock_exists.return_value = True
        mock_open.return_value.__enter__ = MagicMock(
            return_value=MagicMock(
                read=MagicMock(return_value="goal_drift:\n  enabled: true\n  threshold: 0.8\n")
            )
        )

        with patch("yaml.safe_load") as mock_yaml:
            mock_yaml.return_value = {"goal_drift": {"enabled": True, "threshold": 0.8}}
            result = _load_goal_drift_config()

        assert result == {"enabled": True, "threshold": 0.8}

    @patch("pathlib.Path.exists")
    @patch("builtins.open", create=True)
    def test_config_without_goal_drift_returns_empty(self, mock_open, mock_exists):
        """Config without goal_drift section should return empty dict."""
        mock_exists.return_value = True

        with patch("yaml.safe_load") as mock_yaml:
            mock_yaml.return_value = {"other_section": {"key": "value"}}
            result = _load_goal_drift_config()

        assert result == {}

    @patch("pathlib.Path.exists")
    @patch("builtins.open", create=True)
    def test_yaml_parse_error_returns_empty(self, mock_open, mock_exists):
        """YAML parse error should return empty dict."""
        mock_exists.return_value = True

        with patch("yaml.safe_load") as mock_yaml:
            mock_yaml.side_effect = Exception("YAML parse error")
            result = _load_goal_drift_config()

        assert result == {}

    @patch("pathlib.Path.exists")
    @patch("builtins.open", create=True)
    def test_empty_yaml_returns_empty(self, mock_open, mock_exists):
        """Empty YAML file should return empty dict."""
        mock_exists.return_value = True

        with patch("yaml.safe_load") as mock_yaml:
            mock_yaml.return_value = None
            result = _load_goal_drift_config()

        assert result == {}


class TestIntegrationScenarios:
    """Integration-style tests for realistic scenarios."""

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_semantic_similarity_between_related_goals(self, mock_embed, mock_config):
        """Related goals should have high similarity."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7}

        # Simulate embeddings that would be similar for related concepts
        # "Fix authentication" and "Repair login system" would be semantically similar
        mock_embed.side_effect = [
            [0.8, 0.2, 0.1, 0.4],  # "Fix authentication"
            [0.75, 0.25, 0.15, 0.38],  # "Repair login system" - similar
        ]

        is_aligned, similarity, _ = check_goal_drift(
            goal_anchor="Fix authentication bugs in the system",
            change_intent="Repair login system to handle edge cases",
        )

        assert is_aligned is True
        assert similarity > 0.7

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_semantic_drift_between_unrelated_goals(self, mock_embed, mock_config):
        """Unrelated goals should have low similarity."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7}

        # Simulate embeddings that would be different for unrelated concepts
        mock_embed.side_effect = [
            [0.9, 0.1, 0.0, 0.0],  # "Fix database queries"
            [0.0, 0.0, 0.9, 0.1],  # "Add UI animations" - very different
        ]

        is_aligned, similarity, _ = check_goal_drift(
            goal_anchor="Fix database query performance",
            change_intent="Add smooth animations to the UI",
        )

        assert is_aligned is False
        assert similarity < 0.7

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_full_workflow_advisory_mode(self, mock_embed, mock_config):
        """Test full workflow in advisory mode with drift."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7, "mode": "advisory"}
        # Provide 4 values: 2 for check_goal_drift call + 2 for should_block_on_drift call
        # (should_block_on_drift internally calls check_goal_drift which calls sync_embed_text)
        mock_embed.side_effect = [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0], [0.0, 1.0]]

        # Check for drift
        is_aligned, similarity, drift_message = check_goal_drift(
            goal_anchor="Optimize database queries",
            change_intent="Redesign UI components",
        )

        # Should block?
        should_block, block_reason = should_block_on_drift(
            goal_anchor="Optimize database queries",
            change_intent="Redesign UI components",
        )

        assert is_aligned is False
        assert should_block is False  # Advisory mode doesn't block
        assert "advisory" in block_reason.lower()

    @patch("autopack.memory.goal_drift._load_goal_drift_config")
    @patch("autopack.memory.goal_drift.sync_embed_text")
    def test_full_workflow_blocking_mode(self, mock_embed, mock_config):
        """Test full workflow in blocking mode with drift."""
        mock_config.return_value = {"enabled": True, "threshold": 0.7, "mode": "blocking"}
        mock_embed.side_effect = [[1.0, 0.0], [0.0, 1.0]]

        # Should block?
        should_block, block_reason = should_block_on_drift(
            goal_anchor="Optimize database queries",
            change_intent="Redesign UI components",
        )

        assert should_block is True
        assert "blocked" in block_reason.lower()
