"""IO utility functions for safe file operations.

This module provides safe file I/O utilities including:
- read_file: Read entire file content as a string
- write_file: Write string content to a file
- read_lines: Read file content as a list of lines
- write_lines: Write a list of lines to a file

All functions operate on local files only with no network operations.
"""

from pathlib import Path
from typing import Union, List


def read_file(path: Union[str, Path], encoding: str = "utf-8", errors: str = "strict") -> str:
    """Read entire file content as a string.

    Safely reads the complete content of a file and returns it as a string.
    Handles encoding and error handling options.

    Args:
        path: Path to the file to read (string or Path object)
        encoding: Character encoding to use (default: 'utf-8')
        errors: How to handle encoding errors (default: 'strict')
                Options: 'strict', 'ignore', 'replace', 'backslashreplace'

    Returns:
        The complete file content as a string

    Raises:
        FileNotFoundError: If the file does not exist
        PermissionError: If the file cannot be read due to permissions
        IOError: If there is an error reading the file

    Examples:
        >>> # Assuming 'test.txt' contains "Hello, World!"
        >>> read_file('test.txt')
        'Hello, World!'
        >>> read_file(Path('data/config.txt'))
        'config content...'
        >>> read_file('file.txt', encoding='latin-1')
        'content with latin-1 encoding'
    """
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not file_path.is_file():
        raise IOError(f"Path is not a file: {path}")

    try:
        with open(file_path, "r", encoding=encoding, errors=errors) as f:
            return f.read()
    except PermissionError:
        raise PermissionError(f"Permission denied reading file: {path}")
    except Exception as e:
        raise IOError(f"Error reading file {path}: {e}")


def write_file(
    path: Union[str, Path],
    content: str,
    encoding: str = "utf-8",
    create_dirs: bool = False,
    append: bool = False,
) -> None:
    """Write string content to a file.

    Safely writes string content to a file. Can optionally create parent
    directories and append to existing files.

    Args:
        path: Path to the file to write (string or Path object)
        content: String content to write to the file
        encoding: Character encoding to use (default: 'utf-8')
        create_dirs: If True, create parent directories if they don't exist
        append: If True, append to file; if False, overwrite (default: False)

    Raises:
        PermissionError: If the file cannot be written due to permissions
        IOError: If there is an error writing the file

    Examples:
        >>> write_file('output.txt', 'Hello, World!')
        >>> write_file('data/log.txt', 'Log entry\n', create_dirs=True, append=True)
        >>> write_file(Path('config.ini'), '[section]\nkey=value')
    """
    file_path = Path(path)

    # Create parent directories if requested
    if create_dirs and not file_path.parent.exists():
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise IOError(f"Error creating directories for {path}: {e}")

    # Determine write mode
    mode = "a" if append else "w"

    try:
        with open(file_path, mode, encoding=encoding) as f:
            f.write(content)
    except PermissionError:
        raise PermissionError(f"Permission denied writing to file: {path}")
    except Exception as e:
        raise IOError(f"Error writing to file {path}: {e}")


def read_lines(
    path: Union[str, Path],
    encoding: str = "utf-8",
    strip_newlines: bool = True,
    skip_empty: bool = False,
) -> List[str]:
    """Read file content as a list of lines.

    Reads a file and returns its content as a list of lines. Can optionally
    strip newline characters and skip empty lines.

    Args:
        path: Path to the file to read (string or Path object)
        encoding: Character encoding to use (default: 'utf-8')
        strip_newlines: If True, remove trailing newlines from each line
        skip_empty: If True, exclude empty lines from the result

    Returns:
        A list of strings, one per line in the file

    Raises:
        FileNotFoundError: If the file does not exist
        PermissionError: If the file cannot be read due to permissions
        IOError: If there is an error reading the file

    Examples:
        >>> # Assuming 'lines.txt' contains "Line 1\nLine 2\nLine 3\n"
        >>> read_lines('lines.txt')
        ['Line 1', 'Line 2', 'Line 3']
        >>> read_lines('lines.txt', strip_newlines=False)
        ['Line 1\n', 'Line 2\n', 'Line 3\n']
        >>> # Assuming 'data.txt' contains "A\n\nB\n\nC\n"
        >>> read_lines('data.txt', skip_empty=True)
        ['A', 'B', 'C']
    """
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not file_path.is_file():
        raise IOError(f"Path is not a file: {path}")

    try:
        with open(file_path, "r", encoding=encoding) as f:
            lines = f.readlines()

        # Strip newlines if requested
        if strip_newlines:
            lines = [line.rstrip("\n\r") for line in lines]

        # Skip empty lines if requested
        if skip_empty:
            lines = [line for line in lines if line.strip()]

        return lines
    except PermissionError:
        raise PermissionError(f"Permission denied reading file: {path}")
    except Exception as e:
        raise IOError(f"Error reading file {path}: {e}")


def write_lines(
    path: Union[str, Path],
    lines: List[str],
    encoding: str = "utf-8",
    add_newlines: bool = True,
    create_dirs: bool = False,
    append: bool = False,
) -> None:
    """Write a list of lines to a file.

    Writes a list of strings to a file, with each string on a separate line.
    Can optionally add newline characters and create parent directories.

    Args:
        path: Path to the file to write (string or Path object)
        lines: List of strings to write (one per line)
        encoding: Character encoding to use (default: 'utf-8')
        add_newlines: If True, add newline character after each line
        create_dirs: If True, create parent directories if they don't exist
        append: If True, append to file; if False, overwrite (default: False)

    Raises:
        PermissionError: If the file cannot be written due to permissions
        IOError: If there is an error writing the file

    Examples:
        >>> write_lines('output.txt', ['Line 1', 'Line 2', 'Line 3'])
        >>> write_lines('log.txt', ['Entry 1', 'Entry 2'], append=True)
        >>> write_lines('data/file.txt', ['A', 'B', 'C'], create_dirs=True)
        >>> write_lines('raw.txt', ['Line1', 'Line2'], add_newlines=False)
    """
    file_path = Path(path)

    # Create parent directories if requested
    if create_dirs and not file_path.parent.exists():
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise IOError(f"Error creating directories for {path}: {e}")

    # Determine write mode
    mode = "a" if append else "w"

    try:
        with open(file_path, mode, encoding=encoding) as f:
            for line in lines:
                if add_newlines:
                    f.write(line + "\n")
                else:
                    f.write(line)
    except PermissionError:
        raise PermissionError(f"Permission denied writing to file: {path}")
    except Exception as e:
        raise IOError(f"Error writing to file {path}: {e}")
