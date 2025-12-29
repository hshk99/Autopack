"""Pytest tests for list_utils module.

This module contains comprehensive tests for all list utility functions
including chunk, flatten, unique, and rotate.
"""

import pytest
from examples.telemetry_utils_v5.list_utils import (
    chunk,
    flatten,
    unique,
    rotate,
)


class TestChunk:
    """Tests for chunk function."""
    
    def test_chunk_basic(self):
        """Test basic chunking with even division."""
        assert chunk([1, 2, 3, 4, 5, 6], 2) == [[1, 2], [3, 4], [5, 6]]
    
    def test_chunk_uneven(self):
        """Test chunking with uneven division."""
        assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    
    def test_chunk_larger_than_list(self):
        """Test chunk size larger than list."""
        assert chunk([1, 2, 3], 5) == [[1, 2, 3]]
    
    def test_chunk_empty_list(self):
        """Test chunking empty list."""
        assert chunk([], 2) == []
    
    def test_chunk_size_one(self):
        """Test chunk size of 1."""
        assert chunk([1, 2, 3], 1) == [[1], [2], [3]]
    
    def test_chunk_invalid_size(self):
        """Test that chunk raises ValueError for size < 1."""
        with pytest.raises(ValueError, match="Chunk size must be at least 1"):
            chunk([1, 2, 3], 0)


class TestFlatten:
    """Tests for flatten function."""
    
    def test_flatten_nested_lists(self):
        """Test flattening nested lists."""
        assert flatten([1, [2, 3], [4, [5, 6]]]) == [1, 2, 3, 4, 5, 6]
    
    def test_flatten_simple_list(self):
        """Test flattening already flat list."""
        assert flatten([1, 2, 3]) == [1, 2, 3]
    
    def test_flatten_empty_list(self):
        """Test flattening empty list."""
        assert flatten([]) == []
    
    def test_flatten_deeply_nested(self):
        """Test flattening deeply nested lists."""
        assert flatten([1, [2, [3, [4]]]]) == [1, 2, 3, 4]
    
    def test_flatten_mixed_types(self):
        """Test flattening with mixed types."""
        assert flatten([1, ['a', 'b'], [2, [3, 'c']]]) == [1, 'a', 'b', 2, 3, 'c']


class TestUnique:
    """Tests for unique function."""
    
    def test_unique_with_duplicates(self):
        """Test removing duplicates from list."""
        assert unique([1, 2, 2, 3, 1, 4]) == [1, 2, 3, 4]
    
    def test_unique_no_duplicates(self):
        """Test list with no duplicates."""
        assert unique([1, 2, 3]) == [1, 2, 3]
    
    def test_unique_empty_list(self):
        """Test unique with empty list."""
        assert unique([]) == []
    
    def test_unique_all_same(self):
        """Test list with all same elements."""
        assert unique([1, 1, 1, 1]) == [1]
    
    def test_unique_preserves_order(self):
        """Test that unique preserves original order."""
        assert unique([3, 1, 2, 1, 3, 2]) == [3, 1, 2]


class TestRotate:
    """Tests for rotate function."""
    
    def test_rotate_right(self):
        """Test rotating list to the right."""
        assert rotate([1, 2, 3, 4, 5], 2) == [4, 5, 1, 2, 3]
    
    def test_rotate_left(self):
        """Test rotating list to the left."""
        assert rotate([1, 2, 3, 4, 5], -2) == [3, 4, 5, 1, 2]
    
    def test_rotate_zero(self):
        """Test rotating by zero positions."""
        assert rotate([1, 2, 3], 0) == [1, 2, 3]
    
    def test_rotate_empty_list(self):
        """Test rotating empty list."""
        assert rotate([], 5) == []
    
    def test_rotate_full_cycle(self):
        """Test rotating by full list length."""
        assert rotate([1, 2, 3], 3) == [1, 2, 3]
    
    def test_rotate_more_than_length(self):
        """Test rotating by more than list length."""
        assert rotate([1, 2, 3], 10) == [2, 3, 1]
