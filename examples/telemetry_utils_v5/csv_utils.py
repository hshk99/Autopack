"""CSV utility functions for CSV file manipulation.

This module provides common CSV manipulation utilities including:
- read_csv: Read CSV file and return rows as list of lists
- write_csv: Write rows to a CSV file
- to_dicts: Convert CSV rows to list of dictionaries
- from_dicts: Convert list of dictionaries to CSV rows
"""

import csv
from pathlib import Path
from typing import List, Dict, Any, Union, Optional


def read_csv(path: Union[str, Path], encoding: str = 'utf-8', 
             delimiter: str = ',', skip_header: bool = False) -> List[List[str]]:
    """Read CSV file and return rows as list of lists.
    
    Reads a CSV file and returns its content as a list of lists, where each
    inner list represents a row in the CSV file.
    
    Args:
        path: Path to the CSV file to read (string or Path object)
        encoding: Character encoding to use (default: 'utf-8')
        delimiter: Field delimiter character (default: ',')
        skip_header: If True, skip the first row (default: False)
        
    Returns:
        A list of lists, where each inner list contains the fields of a row
        
    Raises:
        FileNotFoundError: If the file does not exist
        PermissionError: If the file cannot be read due to permissions
        IOError: If there is an error reading the file
        
    Examples:
        >>> # Assuming 'data.csv' contains:
        >>> # name,age,city
        >>> # Alice,30,NYC
        >>> # Bob,25,LA
        >>> read_csv('data.csv')
        [['name', 'age', 'city'], ['Alice', '30', 'NYC'], ['Bob', '25', 'LA']]
        >>> read_csv('data.csv', skip_header=True)
        [['Alice', '30', 'NYC'], ['Bob', '25', 'LA']]
        >>> read_csv('data.tsv', delimiter='\t')
        [['col1', 'col2'], ['val1', 'val2']]
    """
    file_path = Path(path)
    
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    if not file_path.is_file():
        raise IOError(f"Path is not a file: {path}")
    
    try:
        with open(file_path, 'r', encoding=encoding, newline='') as f:
            reader = csv.reader(f, delimiter=delimiter)
            rows = list(reader)
            
            if skip_header and rows:
                rows = rows[1:]
            
            return rows
    except PermissionError:
        raise PermissionError(f"Permission denied reading file: {path}")
    except Exception as e:
        raise IOError(f"Error reading file {path}: {e}")


def write_csv(path: Union[str, Path], rows: List[List[Any]], encoding: str = 'utf-8',
              delimiter: str = ',', create_dirs: bool = False) -> None:
    """Write rows to a CSV file.
    
    Writes a list of lists to a CSV file, where each inner list represents
    a row in the output file.
    
    Args:
        path: Path to the CSV file to write (string or Path object)
        rows: List of lists to write, where each inner list is a row
        encoding: Character encoding to use (default: 'utf-8')
        delimiter: Field delimiter character (default: ',')
        create_dirs: If True, create parent directories if they don't exist
        
    Raises:
        PermissionError: If the file cannot be written due to permissions
        IOError: If there is an error writing the file
        
    Examples:
        >>> write_csv('output.csv', [['name', 'age'], ['Alice', 30], ['Bob', 25]])
        >>> write_csv('data.tsv', [['col1', 'col2'], ['val1', 'val2']], delimiter='\t')
        >>> write_csv('dir/file.csv', [['a', 'b']], create_dirs=True)
    """
    file_path = Path(path)
    
    # Create parent directories if requested
    if create_dirs and not file_path.parent.exists():
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise IOError(f"Error creating directories for {path}: {e}")
    
    try:
        with open(file_path, 'w', encoding=encoding, newline='') as f:
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerows(rows)
    except PermissionError:
        raise PermissionError(f"Permission denied writing to file: {path}")
    except Exception as e:
        raise IOError(f"Error writing to file {path}: {e}")


def to_dicts(rows: List[List[str]], headers: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Convert CSV rows to list of dictionaries.
    
    Converts a list of lists (CSV rows) to a list of dictionaries, where
    each dictionary represents a row with column names as keys.
    
    Args:
        rows: List of lists representing CSV rows
        headers: Optional list of header names. If None, uses first row as headers
        
    Returns:
        A list of dictionaries, where each dict represents a row
        
    Raises:
        ValueError: If rows is empty and headers is None
        ValueError: If row length doesn't match header length
        
    Examples:
        >>> rows = [['name', 'age'], ['Alice', '30'], ['Bob', '25']]
        >>> to_dicts(rows)
        [{'name': 'Alice', 'age': '30'}, {'name': 'Bob', 'age': '25'}]
        >>> to_dicts([['Alice', '30'], ['Bob', '25']], headers=['name', 'age'])
        [{'name': 'Alice', 'age': '30'}, {'name': 'Bob', 'age': '25'}]
        >>> to_dicts([])
        []
    """
    if not rows:
        return []
    
    # Determine headers
    if headers is None:
        if not rows:
            raise ValueError("Cannot determine headers from empty rows")
        headers = rows[0]
        data_rows = rows[1:]
    else:
        data_rows = rows
    
    # Convert rows to dictionaries
    result = []
    for row in data_rows:
        if len(row) != len(headers):
            raise ValueError(f"Row length {len(row)} doesn't match header length {len(headers)}")
        result.append(dict(zip(headers, row)))
    
    return result


def from_dicts(dicts: List[Dict[str, Any]], headers: Optional[List[str]] = None,
               include_header: bool = True) -> List[List[str]]:
    """Convert list of dictionaries to CSV rows.
    
    Converts a list of dictionaries to a list of lists (CSV rows), where
    each inner list represents a row.
    
    Args:
        dicts: List of dictionaries to convert
        headers: Optional list of keys to use as columns. If None, uses keys from first dict
        include_header: If True, include header row as first row (default: True)
        
    Returns:
        A list of lists representing CSV rows, optionally with header row
        
    Raises:
        ValueError: If dicts is empty and headers is None
        
    Examples:
        >>> dicts = [{'name': 'Alice', 'age': 30}, {'name': 'Bob', 'age': 25}]
        >>> from_dicts(dicts)
        [['name', 'age'], ['Alice', '30'], ['Bob', '25']]
        >>> from_dicts(dicts, include_header=False)
        [['Alice', '30'], ['Bob', '25']]
        >>> from_dicts(dicts, headers=['age', 'name'])
        [['age', 'name'], ['30', 'Alice'], ['25', 'Bob']]
        >>> from_dicts([])
        []
    """
    if not dicts:
        return []
    
    # Determine headers
    if headers is None:
        if not dicts:
            raise ValueError("Cannot determine headers from empty dicts")
        headers = list(dicts[0].keys())
    
    # Build rows
    rows = []
    
    # Add header row if requested
    if include_header:
        rows.append(headers)
    
    # Add data rows
    for d in dicts:
        row = [str(d.get(key, '')) for key in headers]
        rows.append(row)
    
    return rows
