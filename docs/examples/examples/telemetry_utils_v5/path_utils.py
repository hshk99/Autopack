"""Path utility functions for path manipulation.

This module provides common path manipulation utilities including:
- join_paths: Join multiple path components into a single path
- get_extension: Get the file extension from a path
- change_extension: Change the file extension of a path
- is_subpath: Check if one path is a subpath of another
"""

from pathlib import Path
from typing import Union


def join_paths(*paths: Union[str, Path]) -> Path:
    """Join multiple path components into a single path.

    Uses pathlib to safely join path components, handling different
    operating system path separators automatically.

    Args:
        *paths: Variable number of path components (strings or Path objects)

    Returns:
        A Path object representing the joined path

    Examples:
        >>> join_paths('home', 'user', 'documents')
        PosixPath('home/user/documents')
        >>> join_paths('/var', 'log', 'app.log')
        PosixPath('/var/log/app.log')
        >>> join_paths('data', 'files')
        PosixPath('data/files')
        >>> join_paths('.')
        PosixPath('.')
    """
    if not paths:
        return Path(".")

    result = Path(paths[0])
    for path in paths[1:]:
        result = result / path

    return result


def get_extension(path: Union[str, Path]) -> str:
    """Get the file extension from a path.

    Returns the file extension including the leading dot. Returns an empty
    string if the path has no extension.

    Args:
        path: The file path (string or Path object)

    Returns:
        The file extension including the dot (e.g., '.txt'), or empty string

    Examples:
        >>> get_extension('document.txt')
        '.txt'
        >>> get_extension('/path/to/file.tar.gz')
        '.gz'
        >>> get_extension('README')
        ''
        >>> get_extension('archive.tar.gz')
        '.gz'
        >>> get_extension('.hidden')
        ''
    """
    p = Path(path)
    return p.suffix


def change_extension(path: Union[str, Path], new_extension: str) -> Path:
    """Change the file extension of a path.

    Replaces the current extension with a new one. If the new extension
    doesn't start with a dot, one will be added automatically.

    Args:
        path: The file path (string or Path object)
        new_extension: The new extension (with or without leading dot)

    Returns:
        A new Path object with the changed extension

    Examples:
        >>> change_extension('document.txt', '.md')
        PosixPath('document.md')
        >>> change_extension('file.old', 'new')
        PosixPath('file.new')
        >>> change_extension('/path/to/data.json', '.xml')
        PosixPath('/path/to/data.xml')
        >>> change_extension('README', '.txt')
        PosixPath('README.txt')
    """
    p = Path(path)

    # Ensure extension starts with a dot
    if new_extension and not new_extension.startswith("."):
        new_extension = "." + new_extension

    # Remove current extension and add new one
    if p.suffix:
        new_path = p.with_suffix(new_extension)
    else:
        # If no current extension, append the new one
        new_path = Path(str(p) + new_extension)

    return new_path


def is_subpath(path: Union[str, Path], parent: Union[str, Path]) -> bool:
    """Check if one path is a subpath of another.

    Determines whether 'path' is located within the directory tree of 'parent'.
    Both paths are resolved to absolute paths before comparison.

    Args:
        path: The potential subpath (string or Path object)
        parent: The potential parent path (string or Path object)

    Returns:
        True if path is a subpath of parent, False otherwise

    Examples:
        >>> is_subpath('/home/user/documents/file.txt', '/home/user')
        True
        >>> is_subpath('/home/user/file.txt', '/home/other')
        False
        >>> is_subpath('data/subfolder/file.txt', 'data')
        True
        >>> is_subpath('/var/log', '/var/log')
        True
    """
    try:
        path_obj = Path(path).resolve()
        parent_obj = Path(parent).resolve()

        # Check if path is relative to parent
        try:
            path_obj.relative_to(parent_obj)
            return True
        except ValueError:
            return False
    except (OSError, RuntimeError):
        # Handle cases where paths cannot be resolved
        return False
