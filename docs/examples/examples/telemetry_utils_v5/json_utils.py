"""JSON utility functions for JSON manipulation.

This module provides common JSON manipulation utilities including:
- load_json: Load JSON data from a file
- save_json: Save data to a JSON file
- pretty_print: Format JSON data as a pretty-printed string
- validate_json: Validate if a string is valid JSON
"""

import json
from pathlib import Path
from typing import Any, Union, Optional


def load_json(path: Union[str, Path], encoding: str = 'utf-8') -> Any:
    """Load JSON data from a file.
    
    Reads a JSON file and parses it into a Python object (dict, list, etc.).
    
    Args:
        path: Path to the JSON file to read (string or Path object)
        encoding: Character encoding to use (default: 'utf-8')
        
    Returns:
        The parsed JSON data as a Python object
        
    Raises:
        FileNotFoundError: If the file does not exist
        json.JSONDecodeError: If the file contains invalid JSON
        PermissionError: If the file cannot be read due to permissions
        IOError: If there is an error reading the file
        
    Examples:
        >>> # Assuming 'data.json' contains {"name": "John", "age": 30}
        >>> load_json('data.json')
        {'name': 'John', 'age': 30}
        >>> load_json(Path('config.json'))
        {'setting': 'value'}
        >>> load_json('array.json')  # [1, 2, 3]
        [1, 2, 3]
    """
    file_path = Path(path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    if not file_path.is_file():
        raise IOError(f"Path is not a file: {path}")
    
    try:
        with open(file_path, 'r', encoding=encoding) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"Invalid JSON in file {path}: {e.msg}", e.doc, e.pos)
    except PermissionError:
        raise PermissionError(f"Permission denied reading file: {path}")
    except Exception as e:
        raise IOError(f"Error reading file {path}: {e}")


def save_json(path: Union[str, Path], data: Any, encoding: str = 'utf-8',
              indent: Optional[int] = 2, create_dirs: bool = False,
              sort_keys: bool = False) -> None:
    """Save data to a JSON file.
    
    Serializes a Python object to JSON and writes it to a file.
    
    Args:
        path: Path to the JSON file to write (string or Path object)
        data: Python object to serialize to JSON
        encoding: Character encoding to use (default: 'utf-8')
        indent: Number of spaces for indentation (None for compact, default: 2)
        create_dirs: If True, create parent directories if they don't exist
        sort_keys: If True, sort dictionary keys in output (default: False)
        
    Raises:
        TypeError: If the data cannot be serialized to JSON
        PermissionError: If the file cannot be written due to permissions
        IOError: If there is an error writing the file
        
    Examples:
        >>> save_json('output.json', {'name': 'Alice', 'age': 25})
        >>> save_json('data.json', [1, 2, 3], indent=None)  # Compact format
        >>> save_json('config/settings.json', {'key': 'value'}, create_dirs=True)
        >>> save_json(Path('sorted.json'), {'z': 1, 'a': 2}, sort_keys=True)
    """
    file_path = Path(path)
    
    # Create parent directories if requested
    if create_dirs and not file_path.parent.exists():
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise IOError(f"Error creating directories for {path}: {e}")
    
    try:
        with open(file_path, 'w', encoding=encoding) as f:
            json.dump(data, f, indent=indent, sort_keys=sort_keys, ensure_ascii=False)
    except TypeError as e:
        raise TypeError(f"Data is not JSON serializable: {e}")
    except PermissionError:
        raise PermissionError(f"Permission denied writing to file: {path}")
    except Exception as e:
        raise IOError(f"Error writing to file {path}: {e}")


def pretty_print(data: Any, indent: int = 2, sort_keys: bool = False) -> str:
    """Format JSON data as a pretty-printed string.
    
    Converts a Python object to a formatted JSON string with indentation.
    
    Args:
        data: Python object to format as JSON
        indent: Number of spaces for indentation (default: 2)
        sort_keys: If True, sort dictionary keys in output (default: False)
        
    Returns:
        A formatted JSON string
        
    Raises:
        TypeError: If the data cannot be serialized to JSON
        
    Examples:
        >>> pretty_print({'name': 'Bob', 'age': 30})
        '{\n  "name": "Bob",\n  "age": 30\n}'
        >>> pretty_print([1, 2, 3])
        '[\n  1,\n  2,\n  3\n]'
        >>> pretty_print({'z': 1, 'a': 2}, sort_keys=True)
        '{\n  "a": 2,\n  "z": 1\n}'
        >>> pretty_print({'key': 'value'}, indent=4)
        '{\n    "key": "value"\n}'
    """
    try:
        return json.dumps(data, indent=indent, sort_keys=sort_keys, ensure_ascii=False)
    except TypeError as e:
        raise TypeError(f"Data is not JSON serializable: {e}")


def validate_json(json_string: str) -> bool:
    """Validate if a string is valid JSON.
    
    Attempts to parse the string as JSON and returns True if successful,
    False otherwise.
    
    Args:
        json_string: String to validate as JSON
        
    Returns:
        True if the string is valid JSON, False otherwise
        
    Examples:
        >>> validate_json('{"name": "Charlie"}')
        True
        >>> validate_json('[1, 2, 3]')
        True
        >>> validate_json('"simple string"')
        True
        >>> validate_json('123')
        True
        >>> validate_json('true')
        True
        >>> validate_json('{invalid json}')
        False
        >>> validate_json('')
        False
        >>> validate_json('undefined')
        False
    """
    if not json_string:
        return False
    
    try:
        json.loads(json_string)
        return True
    except (json.JSONDecodeError, ValueError, TypeError):
        return False
