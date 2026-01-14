"""List utility functions for list manipulation.

This module provides common list manipulation utilities including:
- chunk: Split a list into chunks of specified size
- flatten: Flatten a nested list structure
- unique: Remove duplicate elements while preserving order
- rotate: Rotate list elements by a specified number of positions
"""

from typing import List, Any, TypeVar


T = TypeVar("T")


def chunk(lst: List[T], size: int) -> List[List[T]]:
    """Split a list into chunks of specified size.

    Args:
        lst: The input list to chunk
        size: The size of each chunk (must be positive)

    Returns:
        A list of lists, where each inner list has at most 'size' elements

    Raises:
        ValueError: If size is less than 1

    Examples:
        >>> chunk([1, 2, 3, 4, 5], 2)
        [[1, 2], [3, 4], [5]]
        >>> chunk(['a', 'b', 'c', 'd'], 3)
        [['a', 'b', 'c'], ['d']]
        >>> chunk([1, 2, 3], 5)
        [[1, 2, 3]]
        >>> chunk([], 2)
        []
    """
    if size < 1:
        raise ValueError("Chunk size must be at least 1")

    if not lst:
        return []

    return [lst[i : i + size] for i in range(0, len(lst), size)]


def flatten(lst: List[Any]) -> List[Any]:
    """Flatten a nested list structure into a single-level list.

    This function recursively flattens nested lists. Non-list elements
    are preserved as-is.

    Args:
        lst: The nested list to flatten

    Returns:
        A flattened list containing all elements from nested structures

    Examples:
        >>> flatten([1, [2, 3], [4, [5, 6]]])
        [1, 2, 3, 4, 5, 6]
        >>> flatten([[1, 2], [3, 4]])
        [1, 2, 3, 4]
        >>> flatten([1, 2, 3])
        [1, 2, 3]
        >>> flatten([])
        []
        >>> flatten([1, [2, [3, [4]]]])
        [1, 2, 3, 4]
    """
    result = []

    for item in lst:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)

    return result


def unique(lst: List[T]) -> List[T]:
    """Remove duplicate elements from a list while preserving order.

    This function maintains the first occurrence of each element and
    removes subsequent duplicates.

    Args:
        lst: The input list

    Returns:
        A new list with duplicates removed, preserving original order

    Examples:
        >>> unique([1, 2, 2, 3, 1, 4])
        [1, 2, 3, 4]
        >>> unique(['a', 'b', 'a', 'c'])
        ['a', 'b', 'c']
        >>> unique([1, 2, 3])
        [1, 2, 3]
        >>> unique([])
        []
        >>> unique([1, 1, 1, 1])
        [1]
    """
    seen = set()
    result = []

    for item in lst:
        # For unhashable types, fall back to linear search
        try:
            if item not in seen:
                seen.add(item)
                result.append(item)
        except TypeError:
            if item not in result:
                result.append(item)

    return result


def rotate(lst: List[T], positions: int) -> List[T]:
    """Rotate list elements by a specified number of positions.

    Positive values rotate to the right (elements move toward the end),
    negative values rotate to the left (elements move toward the start).

    Args:
        lst: The input list to rotate
        positions: Number of positions to rotate (positive=right, negative=left)

    Returns:
        A new list with elements rotated by the specified positions

    Examples:
        >>> rotate([1, 2, 3, 4, 5], 2)
        [4, 5, 1, 2, 3]
        >>> rotate([1, 2, 3, 4, 5], -2)
        [3, 4, 5, 1, 2]
        >>> rotate(['a', 'b', 'c'], 1)
        ['c', 'a', 'b']
        >>> rotate([1, 2, 3], 0)
        [1, 2, 3]
        >>> rotate([], 5)
        []
        >>> rotate([1, 2, 3], 10)
        [2, 3, 1]
    """
    if not lst:
        return []

    # Normalize positions to be within list length
    n = len(lst)
    positions = positions % n if n > 0 else 0

    if positions == 0:
        return lst[:]

    # Rotate right: take last 'positions' elements and move to front
    return lst[-positions:] + lst[:-positions]
