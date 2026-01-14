"""Dictionary helper functions for dict manipulation.

This module provides common dictionary utilities including
deep merging, nested access, nested setting, and key filtering.
"""

from typing import Any, Callable, Dict
from copy import deepcopy


def deep_merge(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries.

    Recursively merges dict2 into dict1. If both dictionaries have the same key
    and both values are dictionaries, they are merged recursively. Otherwise,
    the value from dict2 overwrites the value from dict1.

    Args:
        dict1: The base dictionary
        dict2: The dictionary to merge into dict1

    Returns:
        A new dictionary with merged values

    Examples:
        >>> deep_merge({'a': 1, 'b': 2}, {'c': 3})
        {'a': 1, 'b': 2, 'c': 3}
        >>> deep_merge({'a': {'x': 1}}, {'a': {'y': 2}})
        {'a': {'x': 1, 'y': 2}}
        >>> deep_merge({'a': 1}, {'a': 2})
        {'a': 2}
        >>> deep_merge({}, {'a': 1})
        {'a': 1}
    """
    result = deepcopy(dict1)

    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)

    return result


def get_nested(data: Dict[str, Any], path: str, default: Any = None, separator: str = ".") -> Any:
    """Get a value from a nested dictionary using a path string.

    Args:
        data: The dictionary to search
        path: A string path to the value (e.g., "user.address.city")
        default: The value to return if the path is not found
        separator: The separator used in the path string (default: ".")

    Returns:
        The value at the specified path, or default if not found

    Examples:
        >>> data = {'user': {'name': 'John', 'address': {'city': 'NYC'}}}
        >>> get_nested(data, 'user.name')
        'John'
        >>> get_nested(data, 'user.address.city')
        'NYC'
        >>> get_nested(data, 'user.age', default=0)
        0
        >>> get_nested(data, 'user.address.country', default='Unknown')
        'Unknown'
    """
    keys = path.split(separator)
    current = data

    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]

    return current


def set_nested(data: Dict[str, Any], path: str, value: Any, separator: str = ".") -> Dict[str, Any]:
    """Set a value in a nested dictionary using a path string.

    Creates intermediate dictionaries as needed. Returns a new dictionary
    with the value set at the specified path.

    Args:
        data: The dictionary to modify
        path: A string path to the value (e.g., "user.address.city")
        value: The value to set
        separator: The separator used in the path string (default: ".")

    Returns:
        A new dictionary with the value set at the specified path

    Examples:
        >>> set_nested({}, 'user.name', 'John')
        {'user': {'name': 'John'}}
        >>> set_nested({'user': {'name': 'John'}}, 'user.age', 30)
        {'user': {'name': 'John', 'age': 30}}
        >>> set_nested({}, 'a.b.c.d', 'value')
        {'a': {'b': {'c': {'d': 'value'}}}}
        >>> set_nested({'x': 1}, 'y.z', 2)
        {'x': 1, 'y': {'z': 2}}
    """
    result = deepcopy(data)
    keys = path.split(separator)
    current = result

    # Navigate to the parent of the target key, creating dicts as needed
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        elif not isinstance(current[key], dict):
            # If the intermediate value is not a dict, replace it
            current[key] = {}
        current = current[key]

    # Set the final value
    current[keys[-1]] = value

    return result


def filter_keys(data: Dict[str, Any], predicate: Callable[[str], bool]) -> Dict[str, Any]:
    """Filter dictionary keys based on a predicate function.

    Args:
        data: The dictionary to filter
        predicate: A function that takes a key and returns True to keep it

    Returns:
        A new dictionary containing only keys where predicate returns True

    Examples:
        >>> filter_keys({'a': 1, 'b': 2, 'c': 3}, lambda k: k in ['a', 'c'])
        {'a': 1, 'c': 3}
        >>> filter_keys({'name': 'John', 'age': 30, 'city': 'NYC'}, lambda k: k.startswith('n'))
        {'name': 'John'}
        >>> filter_keys({'x': 1, 'y': 2, 'z': 3}, lambda k: k > 'x')
        {'y': 2, 'z': 3}
        >>> filter_keys({}, lambda k: True)
        {}
    """
    return {key: value for key, value in data.items() if predicate(key)}


if __name__ == "__main__":
    # Simple demonstration
    print("Dictionary Helper Demo")
    print("=" * 40)

    # Test deep_merge
    print("\nDeep Merge:")
    dict1 = {"a": 1, "b": {"x": 10, "y": 20}}
    dict2 = {"b": {"y": 25, "z": 30}, "c": 3}
    merged = deep_merge(dict1, dict2)
    print(f"  dict1: {dict1}")
    print(f"  dict2: {dict2}")
    print(f"  merged: {merged}")

    dict3 = {"user": {"name": "John", "age": 30}}
    dict4 = {"user": {"age": 31, "city": "NYC"}}
    merged2 = deep_merge(dict3, dict4)
    print(f"  dict3: {dict3}")
    print(f"  dict4: {dict4}")
    print(f"  merged: {merged2}")

    # Test get_nested
    print("\nGet Nested:")
    data = {"user": {"name": "John", "address": {"city": "NYC", "zip": "10001"}}, "active": True}
    print(f"  data: {data}")
    print(f"  get_nested(data, 'user.name'): {get_nested(data, 'user.name')}")
    print(f"  get_nested(data, 'user.address.city'): {get_nested(data, 'user.address.city')}")
    print(f"  get_nested(data, 'user.age', default=0): {get_nested(data, 'user.age', default=0)}")
    print(f"  get_nested(data, 'active'): {get_nested(data, 'active')}")

    # Test set_nested
    print("\nSet Nested:")
    empty_dict = {}
    result1 = set_nested(empty_dict, "user.name", "Alice")
    print(f"  set_nested({{}}, 'user.name', 'Alice'): {result1}")

    result2 = set_nested(result1, "user.age", 25)
    print(f"  set_nested(result1, 'user.age', 25): {result2}")

    result3 = set_nested(result2, "user.address.city", "Boston")
    print(f"  set_nested(result2, 'user.address.city', 'Boston'): {result3}")

    # Test filter_keys
    print("\nFilter Keys:")
    test_dict = {"name": "John", "age": 30, "city": "NYC", "country": "USA", "active": True}
    print(f"  original: {test_dict}")

    filtered1 = filter_keys(test_dict, lambda k: k.startswith("c"))
    print(f"  filter (starts with 'c'): {filtered1}")

    filtered2 = filter_keys(test_dict, lambda k: len(k) <= 4)
    print(f"  filter (length <= 4): {filtered2}")

    filtered3 = filter_keys(test_dict, lambda k: k in ["name", "age", "city"])
    print(f"  filter (in whitelist): {filtered3}")
