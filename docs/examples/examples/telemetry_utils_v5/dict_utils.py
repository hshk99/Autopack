"""Dictionary utility functions for dict manipulation.

This module provides common dictionary manipulation utilities including:
- merge: Deep merge two dictionaries
- get_nested: Get a value from a nested dictionary using a key path
- filter_keys: Filter dictionary by keeping only specified keys
- invert: Invert a dictionary (swap keys and values)
"""

from typing import Dict, Any, List, Optional, Hashable
from copy import deepcopy


def merge(dict1: Dict[str, Any], dict2: Dict[str, Any], deep: bool = True) -> Dict[str, Any]:
    """Deep merge two dictionaries.
    
    Merges dict2 into dict1, with dict2 values taking precedence.
    If deep=True, recursively merges nested dictionaries.
    
    Args:
        dict1: The base dictionary
        dict2: The dictionary to merge into dict1
        deep: If True, recursively merge nested dicts; if False, shallow merge
        
    Returns:
        A new dictionary with merged values
        
    Examples:
        >>> merge({'a': 1, 'b': 2}, {'b': 3, 'c': 4})
        {'a': 1, 'b': 3, 'c': 4}
        >>> merge({'a': {'x': 1}}, {'a': {'y': 2}})
        {'a': {'x': 1, 'y': 2}}
        >>> merge({'a': {'x': 1}}, {'a': {'y': 2}}, deep=False)
        {'a': {'y': 2}}
        >>> merge({}, {'a': 1})
        {'a': 1}
    """
    if deep:
        result = deepcopy(dict1)
        
        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = merge(result[key], value, deep=True)
            else:
                result[key] = deepcopy(value)
        
        return result
    else:
        result = dict1.copy()
        result.update(dict2)
        return result


def get_nested(data: Dict[str, Any], key_path: str, default: Any = None, separator: str = '.') -> Any:
    """Get a value from a nested dictionary using a key path.
    
    Traverses nested dictionaries using a dot-separated (or custom separator)
    key path. Returns the default value if any key in the path is not found.
    
    Args:
        data: The dictionary to search
        key_path: Dot-separated path to the value (e.g., 'user.address.city')
        default: Value to return if key path is not found
        separator: Character used to separate keys in the path (default: '.')
        
    Returns:
        The value at the key path, or default if not found
        
    Examples:
        >>> get_nested({'a': {'b': {'c': 1}}}, 'a.b.c')
        1
        >>> get_nested({'user': {'name': 'John'}}, 'user.name')
        'John'
        >>> get_nested({'a': {'b': 1}}, 'a.c', default='not found')
        'not found'
        >>> get_nested({'a': 1}, 'a')
        1
        >>> get_nested({'a': {'b': 1}}, 'a/b', separator='/')
        1
    """
    if not key_path:
        return default
    
    keys = key_path.split(separator)
    current = data
    
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    
    return current


def filter_keys(data: Dict[str, Any], keys: List[str], exclude: bool = False) -> Dict[str, Any]:
    """Filter dictionary by keeping or excluding specified keys.
    
    Args:
        data: The dictionary to filter
        keys: List of keys to keep (or exclude if exclude=True)
        exclude: If True, exclude the specified keys; if False, keep only these keys
        
    Returns:
        A new dictionary with filtered keys
        
    Examples:
        >>> filter_keys({'a': 1, 'b': 2, 'c': 3}, ['a', 'c'])
        {'a': 1, 'c': 3}
        >>> filter_keys({'a': 1, 'b': 2, 'c': 3}, ['b'], exclude=True)
        {'a': 1, 'c': 3}
        >>> filter_keys({'x': 1, 'y': 2}, ['z'])
        {}
        >>> filter_keys({}, ['a', 'b'])
        {}
    """
    if exclude:
        return {k: v for k, v in data.items() if k not in keys}
    else:
        return {k: v for k, v in data.items() if k in keys}


def invert(data: Dict[Hashable, Hashable]) -> Dict[Hashable, Hashable]:
    """Invert a dictionary by swapping keys and values.
    
    Note: Values must be hashable. If multiple keys have the same value,
    only one key-value pair will be retained (the last one encountered).
    
    Args:
        data: The dictionary to invert
        
    Returns:
        A new dictionary with keys and values swapped
        
    Raises:
        TypeError: If any value is not hashable
        
    Examples:
        >>> invert({'a': 1, 'b': 2, 'c': 3})
        {1: 'a', 2: 'b', 3: 'c'}
        >>> invert({'x': 'foo', 'y': 'bar'})
        {'foo': 'x', 'bar': 'y'}
        >>> invert({1: 'one', 2: 'two'})
        {'one': 1, 'two': 2}
        >>> invert({})
        {}
    """
    try:
        return {v: k for k, v in data.items()}
    except TypeError as e:
        raise TypeError(f"All dictionary values must be hashable: {e}")
