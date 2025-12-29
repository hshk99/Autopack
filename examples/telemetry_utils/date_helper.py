"""Date helper functions for date manipulation.

This module provides common date utilities including formatting,
parsing, date arithmetic, and difference calculations.
"""

from datetime import datetime, timedelta
from typing import Optional, Union


def format_date(date: datetime, format_string: str = "%Y-%m-%d") -> str:
    """Format a datetime object as a string.
    
    Args:
        date: The datetime object to format
        format_string: The format string to use (default: "%Y-%m-%d")
    
    Returns:
        A formatted date string
    
    Examples:
        >>> from datetime import datetime
        >>> dt = datetime(2024, 1, 15, 10, 30, 45)
        >>> format_date(dt)
        '2024-01-15'
        >>> format_date(dt, "%Y/%m/%d")
        '2024/01/15'
        >>> format_date(dt, "%B %d, %Y")
        'January 15, 2024'
        >>> format_date(dt, "%Y-%m-%d %H:%M:%S")
        '2024-01-15 10:30:45'
    """
    return date.strftime(format_string)


def parse_date(date_string: str, format_string: str = "%Y-%m-%d") -> datetime:
    """Parse a date string into a datetime object.
    
    Args:
        date_string: The date string to parse
        format_string: The format string to use (default: "%Y-%m-%d")
    
    Returns:
        A datetime object
    
    Raises:
        ValueError: If the date string doesn't match the format
    
    Examples:
        >>> parse_date("2024-01-15")
        datetime.datetime(2024, 1, 15, 0, 0)
        >>> parse_date("2024/01/15", "%Y/%m/%d")
        datetime.datetime(2024, 1, 15, 0, 0)
        >>> parse_date("January 15, 2024", "%B %d, %Y")
        datetime.datetime(2024, 1, 15, 0, 0)
        >>> parse_date("2024-01-15 10:30:45", "%Y-%m-%d %H:%M:%S")
        datetime.datetime(2024, 1, 15, 10, 30, 45)
    """
    return datetime.strptime(date_string, format_string)


def add_days(date: datetime, days: int) -> datetime:
    """Add a number of days to a date.
    
    Args:
        date: The starting datetime object
        days: The number of days to add (can be negative to subtract)
    
    Returns:
        A new datetime object with the days added
    
    Examples:
        >>> from datetime import datetime
        >>> dt = datetime(2024, 1, 15)
        >>> add_days(dt, 5)
        datetime.datetime(2024, 1, 20, 0, 0)
        >>> add_days(dt, -5)
        datetime.datetime(2024, 1, 10, 0, 0)
        >>> add_days(dt, 0)
        datetime.datetime(2024, 1, 15, 0, 0)
        >>> add_days(dt, 365)
        datetime.datetime(2025, 1, 15, 0, 0)
    """
    return date + timedelta(days=days)


def diff_days(date1: datetime, date2: datetime) -> int:
    """Calculate the difference in days between two dates.
    
    Args:
        date1: The first datetime object
        date2: The second datetime object
    
    Returns:
        The number of days between the dates (date1 - date2).
        Positive if date1 is later, negative if date1 is earlier.
    
    Examples:
        >>> from datetime import datetime
        >>> dt1 = datetime(2024, 1, 20)
        >>> dt2 = datetime(2024, 1, 15)
        >>> diff_days(dt1, dt2)
        5
        >>> diff_days(dt2, dt1)
        -5
        >>> diff_days(dt1, dt1)
        0
        >>> dt3 = datetime(2024, 12, 31)
        >>> dt4 = datetime(2024, 1, 1)
        >>> diff_days(dt3, dt4)
        365
    """
    delta = date1 - date2
    return delta.days


if __name__ == "__main__":
    # Simple demonstration
    print("Date Helper Demo")
    print("=" * 40)
    
    # Create test dates
    now = datetime.now()
    test_date = datetime(2024, 1, 15, 10, 30, 45)
    
    # Test format_date
    print("\nFormat Date:")
    print(f"  Default format: {format_date(test_date)}")
    print(f"  Custom format (Y/M/D): {format_date(test_date, '%Y/%m/%d')}")
    print(f"  Long format: {format_date(test_date, '%B %d, %Y')}")
    print(f"  With time: {format_date(test_date, '%Y-%m-%d %H:%M:%S')}")
    
    # Test parse_date
    print("\nParse Date:")
    date_strings = [
        ("2024-01-15", "%Y-%m-%d"),
        ("2024/01/15", "%Y/%m/%d"),
        ("January 15, 2024", "%B %d, %Y"),
    ]
    for date_str, fmt in date_strings:
        parsed = parse_date(date_str, fmt)
        print(f"  '{date_str}' -> {parsed}")
    
    # Test add_days
    print("\nAdd Days:")
    base_date = datetime(2024, 1, 15)
    day_offsets = [5, -5, 0, 30, 365]
    for offset in day_offsets:
        result = add_days(base_date, offset)
        print(f"  {format_date(base_date)} + {offset} days = {format_date(result)}")
    
    # Test diff_days
    print("\nDifference in Days:")
    date_pairs = [
        (datetime(2024, 1, 20), datetime(2024, 1, 15)),
        (datetime(2024, 1, 15), datetime(2024, 1, 20)),
        (datetime(2024, 12, 31), datetime(2024, 1, 1)),
        (datetime(2024, 1, 15), datetime(2024, 1, 15)),
    ]
    for d1, d2 in date_pairs:
        diff = diff_days(d1, d2)
        print(f"  {format_date(d1)} - {format_date(d2)} = {diff} days")
