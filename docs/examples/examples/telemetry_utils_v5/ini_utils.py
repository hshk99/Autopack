"""INI utility functions for INI file manipulation.

This module provides common INI file manipulation utilities including:
- read_ini: Read an INI file and return a ConfigParser object
- write_ini: Write a ConfigParser object to an INI file
- get_value: Get a value from an INI file
- set_value: Set a value in an INI file
"""

import configparser
from pathlib import Path
from typing import Union, Optional, Any


def read_ini(path: Union[str, Path], encoding: str = "utf-8") -> configparser.ConfigParser:
    """Read an INI file and return a ConfigParser object.

    Reads an INI configuration file and parses it into a ConfigParser object
    that can be used to access sections and values.

    Args:
        path: Path to the INI file to read (string or Path object)
        encoding: Character encoding to use (default: 'utf-8')

    Returns:
        A ConfigParser object containing the parsed INI data

    Raises:
        FileNotFoundError: If the file does not exist
        configparser.Error: If the file contains invalid INI syntax
        PermissionError: If the file cannot be read due to permissions
        IOError: If there is an error reading the file

    Examples:
        >>> # Assuming 'config.ini' contains:
        >>> # [database]
        >>> # host = localhost
        >>> # port = 5432
        >>> config = read_ini('config.ini')
        >>> config.get('database', 'host')
        'localhost'
        >>> config.sections()
        ['database']
    """
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if not file_path.is_file():
        raise IOError(f"Path is not a file: {path}")

    config = configparser.ConfigParser()

    try:
        config.read(file_path, encoding=encoding)
        return config
    except configparser.Error as e:
        raise configparser.Error(f"Invalid INI syntax in file {path}: {e}")
    except PermissionError:
        raise PermissionError(f"Permission denied reading file: {path}")
    except Exception as e:
        raise IOError(f"Error reading file {path}: {e}")


def write_ini(
    path: Union[str, Path],
    config: configparser.ConfigParser,
    encoding: str = "utf-8",
    create_dirs: bool = False,
) -> None:
    """Write a ConfigParser object to an INI file.

    Writes the contents of a ConfigParser object to an INI file.

    Args:
        path: Path to the INI file to write (string or Path object)
        config: ConfigParser object to write
        encoding: Character encoding to use (default: 'utf-8')
        create_dirs: If True, create parent directories if they don't exist

    Raises:
        PermissionError: If the file cannot be written due to permissions
        IOError: If there is an error writing the file

    Examples:
        >>> config = configparser.ConfigParser()
        >>> config['database'] = {'host': 'localhost', 'port': '5432'}
        >>> write_ini('config.ini', config)
        >>> write_ini('configs/app.ini', config, create_dirs=True)
    """
    file_path = Path(path)

    # Create parent directories if requested
    if create_dirs and not file_path.parent.exists():
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise IOError(f"Error creating directories for {path}: {e}")

    try:
        with open(file_path, "w", encoding=encoding) as f:
            config.write(f)
    except PermissionError:
        raise PermissionError(f"Permission denied writing to file: {path}")
    except Exception as e:
        raise IOError(f"Error writing to file {path}: {e}")


def get_value(
    path: Union[str, Path],
    section: str,
    key: str,
    default: Optional[Any] = None,
    encoding: str = "utf-8",
) -> Optional[str]:
    """Get a value from an INI file.

    Reads an INI file and retrieves a specific value from a section.
    Returns the default value if the section or key is not found.

    Args:
        path: Path to the INI file to read (string or Path object)
        section: The section name to read from
        key: The key name within the section
        default: Value to return if section or key is not found (default: None)
        encoding: Character encoding to use (default: 'utf-8')

    Returns:
        The value as a string, or the default value if not found

    Raises:
        FileNotFoundError: If the file does not exist
        PermissionError: If the file cannot be read due to permissions
        IOError: If there is an error reading the file

    Examples:
        >>> # Assuming 'config.ini' contains:
        >>> # [database]
        >>> # host = localhost
        >>> # port = 5432
        >>> get_value('config.ini', 'database', 'host')
        'localhost'
        >>> get_value('config.ini', 'database', 'port')
        '5432'
        >>> get_value('config.ini', 'database', 'user', default='admin')
        'admin'
        >>> get_value('config.ini', 'missing', 'key', default='default')
        'default'
    """
    try:
        config = read_ini(path, encoding=encoding)

        if not config.has_section(section):
            return default

        if not config.has_option(section, key):
            return default

        return config.get(section, key)
    except (FileNotFoundError, PermissionError, IOError):
        raise
    except Exception:
        return default


def set_value(
    path: Union[str, Path],
    section: str,
    key: str,
    value: Any,
    encoding: str = "utf-8",
    create_dirs: bool = False,
) -> None:
    """Set a value in an INI file.

    Reads an INI file (or creates a new one), sets a value in the specified
    section, and writes the file back. Creates the section if it doesn't exist.

    Args:
        path: Path to the INI file (string or Path object)
        section: The section name to write to
        key: The key name within the section
        value: The value to set (will be converted to string)
        encoding: Character encoding to use (default: 'utf-8')
        create_dirs: If True, create parent directories if they don't exist

    Raises:
        PermissionError: If the file cannot be read or written due to permissions
        IOError: If there is an error reading or writing the file

    Examples:
        >>> set_value('config.ini', 'database', 'host', 'localhost')
        >>> set_value('config.ini', 'database', 'port', 5432)
        >>> set_value('new.ini', 'app', 'name', 'MyApp')
        >>> set_value('configs/app.ini', 'settings', 'debug', 'true', create_dirs=True)
    """
    file_path = Path(path)

    # Read existing config or create new one
    if file_path.exists():
        try:
            config = read_ini(path, encoding=encoding)
        except configparser.Error:
            # If file exists but is invalid, create new config
            config = configparser.ConfigParser()
    else:
        config = configparser.ConfigParser()

    # Create section if it doesn't exist
    if not config.has_section(section):
        config.add_section(section)

    # Set the value
    config.set(section, key, str(value))

    # Write back to file
    write_ini(path, config, encoding=encoding, create_dirs=create_dirs)
