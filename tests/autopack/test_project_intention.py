"""Tests for Project Intention Memory (Phase 0).

IMP-CLEAN-002: The v1 schema classes (ProjectIntention, ProjectIntentionManager,
create_and_store_intention) have been removed. These tests are marked as
aspirational/skipped as they test deprecated functionality.

For v2 intention anchor tests, see:
- test_intention_anchor_models.py
- test_intention_anchor_validation.py
- test_intention_anchor_integration.py
"""

import pytest

# All v1 tests are skipped as the deprecated classes have been removed (IMP-CLEAN-002)
pytestmark = pytest.mark.skip(
    reason="IMP-CLEAN-002: ProjectIntention v1 schema removed. Use IntentionAnchorV2 instead."
)


class TestProjectIntention:
    """Test ProjectIntention dataclass (DEPRECATED - v1 schema removed)."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        pass

    def test_from_dict(self):
        """Test creation from dictionary."""
        pass

    def test_from_dict_filters_unknown_fields(self):
        """Test that unknown fields are filtered during deserialization."""
        pass


class TestProjectIntentionManager:
    """Test ProjectIntentionManager (DEPRECATED - v1 manager removed)."""

    def test_init(self):
        """Test manager initialization."""
        pass

    def test_init_with_project_id(self):
        """Test manager initialization with explicit project_id."""
        pass

    def test_compute_digest_stability(self):
        """Test that digest is stable for same input."""
        pass

    def test_compute_digest_uniqueness(self):
        """Test that different inputs produce different digests."""
        pass

    def test_create_anchor_respects_size_cap(self):
        """Test that anchor is capped at MAX_INTENTION_ANCHOR_CHARS."""
        pass

    def test_create_anchor_includes_facts(self):
        """Test that anchor includes intent facts when provided."""
        pass

    def test_create_anchor_limits_facts(self):
        """Test that anchor limits number of facts included."""
        pass

    def test_get_intention_dir_uses_layout(self):
        """Test that intention directory path uses RunFileLayout."""
        pass

    def test_create_intention(self):
        """Test creating a complete intention object."""
        pass

    def test_write_intention_artifacts(self):
        """Test writing intention artifacts to disk."""
        pass

    def test_read_intention_from_disk(self):
        """Test reading intention from disk artifacts."""
        pass

    def test_read_intention_from_disk_missing(self):
        """Test reading intention when no artifacts exist."""
        pass

    def test_write_intention_to_memory_enabled(self):
        """Test writing intention to memory when enabled."""
        pass

    def test_write_intention_to_memory_disabled(self):
        """Test writing intention to memory when disabled (graceful degradation)."""
        pass

    def test_write_intention_to_memory_no_service(self):
        """Test writing intention when no memory service provided."""
        pass

    def test_retrieve_intention_from_memory_enabled(self):
        """Test retrieving intention from memory when enabled."""
        pass

    def test_retrieve_intention_from_memory_disabled(self):
        """Test retrieving intention from memory when disabled."""
        pass

    def test_retrieve_intention_from_memory_not_found(self):
        """Test retrieving intention when none exists in memory."""
        pass

    def test_get_intention_context_from_disk(self):
        """Test getting intention context from disk artifacts."""
        pass

    def test_get_intention_context_size_bounded(self):
        """Test that intention context respects max_chars limit."""
        pass

    def test_get_intention_context_from_memory_fallback(self):
        """Test getting intention context from memory when disk unavailable."""
        pass

    def test_get_intention_context_unavailable(self):
        """Test getting intention context when neither disk nor memory available."""
        pass


class TestConvenienceFunctions:
    """Test convenience functions (DEPRECATED - v1 removed)."""

    def test_create_and_store_intention(self):
        """Test create_and_store_intention convenience function."""
        pass
