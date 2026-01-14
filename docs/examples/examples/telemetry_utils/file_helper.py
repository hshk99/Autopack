"""File helper functions for file I/O operations.

This module provides common file utilities including JSON file operations
and line-based file reading/writing.
"""

import json
from typing import Any, List, Optional
from pathlib import Path


def read_json(filepath: str, encoding: str = "utf-8") -> Any:
    """Read and parse a JSON file.

    Args:
        filepath: Path to the JSON file to read
        encoding: File encoding (default: "utf-8")

    Returns:
        The parsed JSON data (dict, list, or other JSON-compatible type)

    Raises:
        FileNotFoundError: If the file does not exist
        json.JSONDecodeError: If the file contains invalid JSON
        IOError: If there's an error reading the file

    Examples:
        >>> # Assuming 'data.json' contains {"name": "John", "age": 30}
        >>> data = read_json("data.json")
        >>> print(data)
        {'name': 'John', 'age': 30}
        >>> print(data["name"])
        'John'
    """
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    with open(path, "r", encoding=encoding) as f:
        return json.load(f)


def write_json(
    filepath: str,
    data: Any,
    encoding: str = "utf-8",
    indent: Optional[int] = 2,
    ensure_ascii: bool = False,
) -> None:
    """Write data to a JSON file.

    Args:
        filepath: Path to the JSON file to write
        data: The data to write (must be JSON-serializable)
        encoding: File encoding (default: "utf-8")
        indent: Number of spaces for indentation (default: 2, None for compact)
        ensure_ascii: If True, escape non-ASCII characters (default: False)

    Raises:
        TypeError: If the data is not JSON-serializable
        IOError: If there's an error writing the file

    Examples:
        >>> data = {"name": "John", "age": 30, "city": "NYC"}
        >>> write_json("output.json", data)
        >>> # File now contains formatted JSON

        >>> # Write compact JSON
        >>> write_json("compact.json", data, indent=None)

        >>> # Write list data
        >>> items = [1, 2, 3, 4, 5]
        >>> write_json("items.json", items)
    """
    path = Path(filepath)

    # Create parent directories if they don't exist
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding=encoding) as f:
        json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)


def read_lines(
    filepath: str, encoding: str = "utf-8", strip_whitespace: bool = True, skip_empty: bool = False
) -> List[str]:
    """Read lines from a text file.

    Args:
        filepath: Path to the text file to read
        encoding: File encoding (default: "utf-8")
        strip_whitespace: If True, strip leading/trailing whitespace from each line
        skip_empty: If True, skip empty lines (after stripping if enabled)

    Returns:
        A list of lines from the file

    Raises:
        FileNotFoundError: If the file does not exist
        IOError: If there's an error reading the file

    Examples:
        >>> # Assuming 'data.txt' contains:
        >>> # line 1
        >>> # line 2
        >>> # line 3
        >>> lines = read_lines("data.txt")
        >>> print(lines)
        ['line 1', 'line 2', 'line 3']

        >>> # Read without stripping whitespace
        >>> lines = read_lines("data.txt", strip_whitespace=False)
        >>> print(lines)
        ['line 1\n', 'line 2\n', 'line 3\n']

        >>> # Skip empty lines
        >>> lines = read_lines("data.txt", skip_empty=True)
        >>> # Empty lines will be excluded
    """
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    with open(path, "r", encoding=encoding) as f:
        lines = f.readlines()

    if strip_whitespace:
        lines = [line.strip() for line in lines]

    if skip_empty:
        lines = [line for line in lines if line]

    return lines


def write_lines(
    filepath: str,
    lines: List[str],
    encoding: str = "utf-8",
    append: bool = False,
    add_newlines: bool = True,
) -> None:
    """Write lines to a text file.

    Args:
        filepath: Path to the text file to write
        lines: List of strings to write as lines
        encoding: File encoding (default: "utf-8")
        append: If True, append to file; if False, overwrite (default: False)
        add_newlines: If True, add newline after each line (default: True)

    Raises:
        IOError: If there's an error writing the file

    Examples:
        >>> lines = ["line 1", "line 2", "line 3"]
        >>> write_lines("output.txt", lines)
        >>> # File now contains three lines

        >>> # Append to existing file
        >>> more_lines = ["line 4", "line 5"]
        >>> write_lines("output.txt", more_lines, append=True)

        >>> # Write without automatic newlines
        >>> lines_with_newlines = ["line 1\n", "line 2\n"]
        >>> write_lines("output.txt", lines_with_newlines, add_newlines=False)
    """
    path = Path(filepath)

    # Create parent directories if they don't exist
    path.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if append else "w"

    with open(path, mode, encoding=encoding) as f:
        for line in lines:
            if add_newlines and not line.endswith("\n"):
                f.write(line + "\n")
            else:
                f.write(line)


if __name__ == "__main__":
    # Simple demonstration
    import tempfile
    import os

    print("File Helper Demo")
    print("=" * 40)

    # Create a temporary directory for demo
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test write_json and read_json
        print("\nJSON Operations:")
        json_file = os.path.join(tmpdir, "test.json")

        test_data = {
            "name": "John Doe",
            "age": 30,
            "city": "New York",
            "hobbies": ["reading", "coding", "hiking"],
        }

        write_json(json_file, test_data)
        print(f"  Wrote JSON to: {json_file}")

        loaded_data = read_json(json_file)
        print(f"  Read JSON: {loaded_data}")
        print(f"  Name: {loaded_data['name']}")
        print(f"  Hobbies: {loaded_data['hobbies']}")

        # Test write_lines and read_lines
        print("\nLine Operations:")
        text_file = os.path.join(tmpdir, "test.txt")

        test_lines = ["First line", "Second line", "Third line", "", "Fifth line after empty"]

        write_lines(text_file, test_lines)
        print(f"  Wrote {len(test_lines)} lines to: {text_file}")

        loaded_lines = read_lines(text_file)
        print(f"  Read {len(loaded_lines)} lines (with empty): {loaded_lines}")

        loaded_lines_no_empty = read_lines(text_file, skip_empty=True)
        print(f"  Read {len(loaded_lines_no_empty)} lines (skip empty): {loaded_lines_no_empty}")

        # Test append mode
        print("\nAppend Mode:")
        more_lines = ["Appended line 1", "Appended line 2"]
        write_lines(text_file, more_lines, append=True)
        print(f"  Appended {len(more_lines)} lines")

        all_lines = read_lines(text_file, skip_empty=True)
        print(f"  Total lines now: {len(all_lines)}")
        print(f"  All lines: {all_lines}")

        # Test nested directory creation
        print("\nNested Directory Creation:")
        nested_file = os.path.join(tmpdir, "subdir", "nested", "file.json")
        write_json(nested_file, {"test": "nested"})
        print(f"  Created nested file: {nested_file}")
        print(f"  File exists: {os.path.exists(nested_file)}")
