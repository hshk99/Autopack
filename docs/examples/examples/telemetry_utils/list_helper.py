"""List helper functions for collection operations.

This module provides common list manipulation utilities including
chunking, flattening, deduplication, and grouping operations.
"""

from typing import Any, Callable, Dict, List, TypeVar


T = TypeVar('T')
K = TypeVar('K')


def chunk(items: List[T], size: int) -> List[List[T]]:
    """Split a list into chunks of specified size.
    
    Args:
        items: The list to split into chunks
        size: The maximum size of each chunk
    
    Returns:
        A list of lists, where each inner list has at most 'size' elements
    
    Raises:
        ValueError: If size is less than 1
    
    Examples:
        >>> chunk([1, 2, 3, 4, 5], 2)
        [[1, 2], [3, 4], [5]]
        >>> chunk([1, 2, 3, 4, 5, 6], 3)
        [[1, 2, 3], [4, 5, 6]]
        >>> chunk([], 2)
        []
        >>> chunk([1], 5)
        [[1]]
    """
    if size < 1:
        raise ValueError("Chunk size must be at least 1")
    
    if not items:
        return []
    
    result = []
    for i in range(0, len(items), size):
        result.append(items[i:i + size])
    
    return result


def flatten(items: List[Any]) -> List[Any]:
    """Flatten a nested list structure by one level.
    
    Args:
        items: A list that may contain nested lists
    
    Returns:
        A flattened list with one level of nesting removed
    
    Examples:
        >>> flatten([[1, 2], [3, 4], [5]])
        [1, 2, 3, 4, 5]
        >>> flatten([[1], [2], [3]])
        [1, 2, 3]
        >>> flatten([])
        []
        >>> flatten([[1, 2, 3]])
        [1, 2, 3]
        >>> flatten([1, [2, 3], 4])
        [1, 2, 3, 4]
    """
    result = []
    for item in items:
        if isinstance(item, list):
            result.extend(item)
        else:
            result.append(item)
    return result


def unique(items: List[T]) -> List[T]:
    """Remove duplicate elements from a list while preserving order.
    
    Args:
        items: The list to deduplicate
    
    Returns:
        A new list with duplicates removed, maintaining first occurrence order
    
    Examples:
        >>> unique([1, 2, 2, 3, 1, 4])
        [1, 2, 3, 4]
        >>> unique(['a', 'b', 'a', 'c'])
        ['a', 'b', 'c']
        >>> unique([])
        []
        >>> unique([1, 1, 1])
        [1]
    """
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def group_by(items: List[T], key_func: Callable[[T], K]) -> Dict[K, List[T]]:
    """Group list elements by a key function.
    
    Args:
        items: The list to group
        key_func: A function that extracts the grouping key from each item
    
    Returns:
        A dictionary mapping keys to lists of items with that key
    
    Examples:
        >>> group_by([1, 2, 3, 4, 5, 6], lambda x: x % 2)
        {1: [1, 3, 5], 0: [2, 4, 6]}
        >>> group_by(['apple', 'apricot', 'banana', 'blueberry'], lambda x: x[0])
        {'a': ['apple', 'apricot'], 'b': ['banana', 'blueberry']}
        >>> group_by([], lambda x: x)
        {}
        >>> group_by([1, 2, 3], lambda x: 'all')
        {'all': [1, 2, 3]}
    """
    result: Dict[K, List[T]] = {}
    for item in items:
        key = key_func(item)
        if key not in result:
            result[key] = []
        result[key].append(item)
    return result


if __name__ == "__main__":
    # Simple demonstration
    print("List Helper Demo")
    print("=" * 40)
    
    # Test chunk
    test_list = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    print("\nChunk Function:")
    print(f"  Original: {test_list}")
    print(f"  Chunk(3): {chunk(test_list, 3)}")
    print(f"  Chunk(4): {chunk(test_list, 4)}")
    
    # Test flatten
    nested_list = [[1, 2], [3, 4], [5, 6, 7]]
    print("\nFlatten Function:")
    print(f"  Original: {nested_list}")
    print(f"  Flattened: {flatten(nested_list)}")
    
    mixed_list = [1, [2, 3], 4, [5]]
    print(f"  Mixed: {mixed_list}")
    print(f"  Flattened: {flatten(mixed_list)}")
    
    # Test unique
    duplicate_list = [1, 2, 2, 3, 1, 4, 3, 5]
    print("\nUnique Function:")
    print(f"  Original: {duplicate_list}")
    print(f"  Unique: {unique(duplicate_list)}")
    
    string_list = ['apple', 'banana', 'apple', 'cherry', 'banana']
    print(f"  Original: {string_list}")
    print(f"  Unique: {unique(string_list)}")
    
    # Test group_by
    numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    print("\nGroup By Function:")
    print(f"  Original: {numbers}")
    print(f"  Group by even/odd: {group_by(numbers, lambda x: 'even' if x % 2 == 0 else 'odd')}")
    
    words = ['apple', 'apricot', 'banana', 'blueberry', 'cherry', 'cranberry']
    print(f"  Original: {words}")
    print(f"  Group by first letter: {group_by(words, lambda x: x[0])}")
