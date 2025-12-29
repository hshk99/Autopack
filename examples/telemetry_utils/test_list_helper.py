"""Comprehensive tests for list_helper module.

This module provides comprehensive test coverage for the list_helper module,
including tests for chunk, flatten, unique, and group_by functions.
"""

import pytest
from examples.telemetry_utils.list_helper import chunk, flatten, unique, group_by


class TestChunk:
    """Test suite for chunk function."""

    def test_chunk_basic(self):
        """Test basic chunking functionality."""
        assert chunk([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
        assert chunk([1, 2, 3, 4, 5, 6], 3) == [[1, 2, 3], [4, 5, 6]]
        assert chunk([1, 2, 3, 4, 5, 6, 7], 3) == [[1, 2, 3], [4, 5, 6], [7]]

    def test_chunk_empty_list(self):
        """Test chunking an empty list."""
        assert chunk([], 2) == []
        assert chunk([], 5) == []
        assert chunk([], 100) == []

    def test_chunk_single_element(self):
        """Test chunking a single element."""
        assert chunk([1], 1) == [[1]]
        assert chunk([1], 5) == [[1]]
        assert chunk([1], 100) == [[1]]

    def test_chunk_size_one(self):
        """Test chunking with size 1."""
        assert chunk([1, 2, 3], 1) == [[1], [2], [3]]
        assert chunk([1, 2, 3, 4, 5], 1) == [[1], [2], [3], [4], [5]]

    def test_chunk_size_equals_length(self):
        """Test chunking when size equals list length."""
        assert chunk([1, 2, 3], 3) == [[1, 2, 3]]
        assert chunk([1, 2, 3, 4, 5], 5) == [[1, 2, 3, 4, 5]]

    def test_chunk_size_larger_than_length(self):
        """Test chunking when size is larger than list length."""
        assert chunk([1, 2, 3], 10) == [[1, 2, 3]]
        assert chunk([1], 100) == [[1]]

    def test_chunk_invalid_size(self):
        """Test that invalid chunk size raises ValueError."""
        with pytest.raises(ValueError, match="Chunk size must be at least 1"):
            chunk([1, 2, 3], 0)
        
        with pytest.raises(ValueError, match="Chunk size must be at least 1"):
            chunk([1, 2, 3], -1)
        
        with pytest.raises(ValueError, match="Chunk size must be at least 1"):
            chunk([], 0)

    def test_chunk_strings(self):
        """Test chunking with strings."""
        assert chunk(['a', 'b', 'c', 'd', 'e'], 2) == [['a', 'b'], ['c', 'd'], ['e']]
        assert chunk(['hello', 'world', 'test'], 2) == [['hello', 'world'], ['test']]

    def test_chunk_mixed_types(self):
        """Test chunking with mixed types."""
        assert chunk([1, 'a', 2, 'b', 3], 2) == [[1, 'a'], [2, 'b'], [3]]
        assert chunk([True, False, 1, 0], 2) == [[True, False], [1, 0]]

    def test_chunk_preserves_order(self):
        """Test that chunking preserves element order."""
        items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        result = chunk(items, 3)
        flattened = [item for sublist in result for item in sublist]
        assert flattened == items

    def test_chunk_large_list(self):
        """Test chunking a large list."""
        large_list = list(range(1000))
        result = chunk(large_list, 100)
        assert len(result) == 10
        assert all(len(chunk_item) == 100 for chunk_item in result)


class TestFlatten:
    """Test suite for flatten function."""

    def test_flatten_basic(self):
        """Test basic flattening functionality."""
        assert flatten([[1, 2], [3, 4], [5]]) == [1, 2, 3, 4, 5]
        assert flatten([[1], [2], [3]]) == [1, 2, 3]
        assert flatten([[1, 2, 3]]) == [1, 2, 3]

    def test_flatten_empty_list(self):
        """Test flattening an empty list."""
        assert flatten([]) == []

    def test_flatten_empty_sublists(self):
        """Test flattening with empty sublists."""
        assert flatten([[], [], []]) == []
        assert flatten([[1], [], [2]]) == [1, 2]
        assert flatten([[], [1, 2], []]) == [1, 2]

    def test_flatten_mixed_nested_and_flat(self):
        """Test flattening with mixed nested and flat elements."""
        assert flatten([1, [2, 3], 4]) == [1, 2, 3, 4]
        assert flatten([1, [2], 3, [4, 5]]) == [1, 2, 3, 4, 5]
        assert flatten([[1], 2, [3], 4]) == [1, 2, 3, 4]

    def test_flatten_single_level_only(self):
        """Test that flatten only flattens one level."""
        assert flatten([[1, [2, 3]], [4]]) == [1, [2, 3], 4]
        assert flatten([[[1, 2]], [[3, 4]]]) == [[1, 2], [3, 4]]

    def test_flatten_strings(self):
        """Test flattening with strings."""
        assert flatten([['a', 'b'], ['c', 'd']]) == ['a', 'b', 'c', 'd']
        assert flatten([['hello'], ['world']]) == ['hello', 'world']

    def test_flatten_mixed_types(self):
        """Test flattening with mixed types."""
        assert flatten([[1, 'a'], [2, 'b']]) == [1, 'a', 2, 'b']
        assert flatten([[True, False], [1, 0]]) == [True, False, 1, 0]

    def test_flatten_preserves_order(self):
        """Test that flattening preserves element order."""
        nested = [[1, 2], [3, 4], [5, 6]]
        result = flatten(nested)
        assert result == [1, 2, 3, 4, 5, 6]

    def test_flatten_large_list(self):
        """Test flattening a large nested list."""
        nested = [[i, i+1] for i in range(0, 1000, 2)]
        result = flatten(nested)
        assert len(result) == 1000
        assert result == list(range(1000))


class TestUnique:
    """Test suite for unique function."""

    def test_unique_basic(self):
        """Test basic deduplication functionality."""
        assert unique([1, 2, 2, 3, 1, 4]) == [1, 2, 3, 4]
        assert unique([1, 1, 1, 1]) == [1]
        assert unique([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]

    def test_unique_empty_list(self):
        """Test deduplicating an empty list."""
        assert unique([]) == []

    def test_unique_single_element(self):
        """Test deduplicating a single element."""
        assert unique([1]) == [1]
        assert unique(['a']) == ['a']

    def test_unique_no_duplicates(self):
        """Test deduplicating a list with no duplicates."""
        assert unique([1, 2, 3, 4, 5]) == [1, 2, 3, 4, 5]
        assert unique(['a', 'b', 'c']) == ['a', 'b', 'c']

    def test_unique_all_duplicates(self):
        """Test deduplicating a list with all duplicates."""
        assert unique([1, 1, 1, 1, 1]) == [1]
        assert unique(['a', 'a', 'a']) == ['a']

    def test_unique_preserves_order(self):
        """Test that unique preserves first occurrence order."""
        assert unique([3, 1, 2, 1, 3, 2]) == [3, 1, 2]
        assert unique([5, 4, 3, 2, 1, 1, 2, 3, 4, 5]) == [5, 4, 3, 2, 1]

    def test_unique_strings(self):
        """Test deduplicating strings."""
        assert unique(['apple', 'banana', 'apple', 'cherry', 'banana']) == ['apple', 'banana', 'cherry']
        assert unique(['a', 'b', 'a', 'c']) == ['a', 'b', 'c']

    def test_unique_mixed_types(self):
        """Test deduplicating with mixed types."""
        assert unique([1, '1', 1, '1']) == [1, '1']
        assert unique([True, 1, False, 0]) == [True, False]  # True == 1, False == 0 in Python

    def test_unique_with_none(self):
        """Test deduplicating with None values."""
        assert unique([1, None, 2, None, 3]) == [1, None, 2, 3]
        assert unique([None, None, None]) == [None]

    def test_unique_large_list(self):
        """Test deduplicating a large list."""
        # Create list with many duplicates
        items = [i % 100 for i in range(1000)]
        result = unique(items)
        assert len(result) == 100
        assert result == list(range(100))


class TestGroupBy:
    """Test suite for group_by function."""

    def test_group_by_basic(self):
        """Test basic grouping functionality."""
        result = group_by([1, 2, 3, 4, 5, 6], lambda x: x % 2)
        assert result == {1: [1, 3, 5], 0: [2, 4, 6]}

    def test_group_by_empty_list(self):
        """Test grouping an empty list."""
        assert group_by([], lambda x: x) == {}
        assert group_by([], lambda x: x % 2) == {}

    def test_group_by_single_element(self):
        """Test grouping a single element."""
        assert group_by([1], lambda x: x % 2) == {1: [1]}
        assert group_by(['a'], lambda x: x[0]) == {'a': ['a']}

    def test_group_by_all_same_group(self):
        """Test grouping when all items belong to same group."""
        assert group_by([1, 2, 3], lambda x: 'all') == {'all': [1, 2, 3]}
        assert group_by([2, 4, 6], lambda x: x % 2) == {0: [2, 4, 6]}

    def test_group_by_strings(self):
        """Test grouping strings."""
        result = group_by(['apple', 'apricot', 'banana', 'blueberry'], lambda x: x[0])
        assert result == {'a': ['apple', 'apricot'], 'b': ['banana', 'blueberry']}

    def test_group_by_string_length(self):
        """Test grouping by string length."""
        result = group_by(['a', 'bb', 'ccc', 'dd', 'e'], lambda x: len(x))
        assert result == {1: ['a', 'e'], 2: ['bb', 'dd'], 3: ['ccc']}

    def test_group_by_even_odd(self):
        """Test grouping by even/odd."""
        result = group_by([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], lambda x: 'even' if x % 2 == 0 else 'odd')
        assert result == {'odd': [1, 3, 5, 7, 9], 'even': [2, 4, 6, 8, 10]}

    def test_group_by_preserves_order(self):
        """Test that grouping preserves order within groups."""
        result = group_by([5, 1, 4, 2, 3], lambda x: x % 2)
        assert result[1] == [5, 1, 3]
        assert result[0] == [4, 2]

    def test_group_by_complex_key(self):
        """Test grouping with complex key function."""
        items = [{'name': 'Alice', 'age': 30}, {'name': 'Bob', 'age': 25}, {'name': 'Charlie', 'age': 30}]
        result = group_by(items, lambda x: x['age'])
        assert result[30] == [{'name': 'Alice', 'age': 30}, {'name': 'Charlie', 'age': 30}]
        assert result[25] == [{'name': 'Bob', 'age': 25}]

    def test_group_by_boolean_key(self):
        """Test grouping with boolean key."""
        result = group_by([1, 2, 3, 4, 5], lambda x: x > 3)
        assert result[False] == [1, 2, 3]
        assert result[True] == [4, 5]

    def test_group_by_none_key(self):
        """Test grouping with None as a key."""
        result = group_by([1, None, 2, None, 3], lambda x: x)
        assert result[None] == [None, None]
        assert result[1] == [1]
        assert result[2] == [2]
        assert result[3] == [3]

    def test_group_by_large_list(self):
        """Test grouping a large list."""
        items = list(range(1000))
        result = group_by(items, lambda x: x % 10)
        assert len(result) == 10
        for key in range(10):
            assert len(result[key]) == 100


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_chunk_then_flatten(self):
        """Test chunking then flattening returns original."""
        items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        chunked = chunk(items, 3)
        flattened = flatten(chunked)
        assert flattened == items

    def test_flatten_then_unique(self):
        """Test flattening then deduplicating."""
        nested = [[1, 2, 2], [3, 1], [4, 2, 3]]
        flattened = flatten(nested)
        result = unique(flattened)
        assert result == [1, 2, 3, 4]

    def test_unique_then_chunk(self):
        """Test deduplicating then chunking."""
        items = [1, 2, 2, 3, 1, 4, 3, 5]
        deduplicated = unique(items)
        chunked = chunk(deduplicated, 2)
        assert chunked == [[1, 2], [3, 4], [5]]

    def test_group_by_then_flatten(self):
        """Test grouping then flattening values."""
        items = [1, 2, 3, 4, 5, 6]
        grouped = group_by(items, lambda x: x % 2)
        values = list(grouped.values())
        flattened = flatten(values)
        assert sorted(flattened) == items

    def test_chunk_flatten_unique_pipeline(self):
        """Test a pipeline of chunk, flatten, and unique."""
        items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        # Chunk into groups of 3
        chunked = chunk(items, 3)
        # Add duplicates to each chunk
        duplicated = [chunk_item + chunk_item for chunk_item in chunked]
        # Flatten
        flattened = flatten(duplicated)
        # Remove duplicates
        result = unique(flattened)
        assert result == items

    def test_group_by_with_chunked_data(self):
        """Test grouping chunked data."""
        items = list(range(20))
        chunked = chunk(items, 5)
        # Group chunks by their first element's parity
        grouped = group_by(chunked, lambda chunk_item: chunk_item[0] % 2)
        assert len(grouped[0]) == 2  # Chunks starting with even numbers
        assert len(grouped[1]) == 2  # Chunks starting with odd numbers

    def test_complex_pipeline(self):
        """Test a complex pipeline of operations."""
        # Start with nested data with duplicates
        data = [[1, 2, 2], [3, 4, 4], [5, 6, 6], [7, 8, 8]]
        # Flatten
        flattened = flatten(data)
        # Remove duplicates
        deduplicated = unique(flattened)
        # Group by even/odd
        grouped = group_by(deduplicated, lambda x: x % 2)
        # Chunk each group
        result = {k: chunk(v, 2) for k, v in grouped.items()}
        
        assert result[1] == [[1, 3], [5, 7]]
        assert result[0] == [[2, 4], [6, 8]]


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_chunk_with_negative_numbers(self):
        """Test chunking with negative numbers."""
        assert chunk([-1, -2, -3, -4], 2) == [[-1, -2], [-3, -4]]

    def test_flatten_with_none(self):
        """Test flattening with None values."""
        assert flatten([[1, None], [2, None]]) == [1, None, 2, None]
        assert flatten([None, [1, 2], None]) == [None, 1, 2, None]

    def test_unique_with_zero(self):
        """Test unique with zero values."""
        assert unique([0, 1, 0, 2, 0]) == [0, 1, 2]
        assert unique([0, 0, 0]) == [0]

    def test_group_by_with_zero_key(self):
        """Test grouping when key function returns zero."""
        result = group_by([0, 1, 2, 3], lambda x: 0)
        assert result == {0: [0, 1, 2, 3]}

    def test_chunk_preserves_type(self):
        """Test that chunk preserves element types."""
        items = [1.5, 2.5, 3.5, 4.5]
        result = chunk(items, 2)
        assert result == [[1.5, 2.5], [3.5, 4.5]]
        assert isinstance(result[0][0], float)

    def test_flatten_with_tuples(self):
        """Test that flatten doesn't flatten tuples."""
        items = [(1, 2), (3, 4)]
        result = flatten(items)
        assert result == [(1, 2), (3, 4)]

    def test_unique_with_unhashable_warning(self):
        """Test unique behavior with hashable types only."""
        # unique uses set internally, so only hashable types work
        assert unique([1, 2, 1, 3, 2]) == [1, 2, 3]
        assert unique(['a', 'b', 'a']) == ['a', 'b']

    def test_group_by_with_tuple_key(self):
        """Test grouping with tuple keys."""
        items = [1, 2, 3, 4, 5, 6]
        result = group_by(items, lambda x: (x % 2, x % 3))
        assert (1, 1) in result
        assert (0, 0) in result


class TestPerformance:
    """Test performance with larger inputs."""

    @pytest.mark.slow
    def test_chunk_large_list_performance(self):
        """Test chunking performance with large list."""
        large_list = list(range(100000))
        result = chunk(large_list, 1000)
        assert len(result) == 100
        assert len(result[0]) == 1000

    @pytest.mark.slow
    def test_flatten_large_nested_list_performance(self):
        """Test flattening performance with large nested list."""
        nested = [[i] for i in range(100000)]
        result = flatten(nested)
        assert len(result) == 100000

    @pytest.mark.slow
    def test_unique_large_list_performance(self):
        """Test unique performance with large list."""
        # List with many duplicates
        items = [i % 1000 for i in range(100000)]
        result = unique(items)
        assert len(result) == 1000

    @pytest.mark.slow
    def test_group_by_large_list_performance(self):
        """Test grouping performance with large list."""
        items = list(range(100000))
        result = group_by(items, lambda x: x % 100)
        assert len(result) == 100
        assert all(len(v) == 1000 for v in result.values())
