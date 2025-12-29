"""Date utility functions for date manipulation.

This module provides common date manipulation utilities including:
- format_date: Format a date object to a string
- parse_date: Parse a string to a date object
- add_days: Add a specified number of days to a date
- diff_days: Calculate the difference in days between two dates
- is_weekend: Check if a date falls on a weekend
"""

from datetime import datetime, date, timedelta
from typing import Union, Optional


def format_date(dt: Union[date, datetime], format_str: str = "%Y-%m-%d") -> str:
    """Format a date object to a string.
    
    Args:
        dt: The date or datetime object to format
        format_str: The format string (default: "%Y-%m-%d")
        
    Returns:
        The formatted date string
        
    Examples:
        >>> from datetime import date
        >>> format_date(date(2023, 12, 25))
        '2023-12-25'
        >>> format_date(date(2023, 12, 25), "%m/%d/%Y")
        '12/25/2023'
        >>> format_date(date(2023, 1, 5), "%B %d, %Y")
        'January 05, 2023'
    """
    return dt.strftime(format_str)


def parse_date(date_str: str, format_str: str = "%Y-%m-%d") -> date:
    """Parse a string to a date object.
    
    Args:
        date_str: The date string to parse
        format_str: The format string (default: "%Y-%m-%d")
        
    Returns:
        The parsed date object
        
    Raises:
        ValueError: If the date string doesn't match the format
        
    Examples:
        >>> parse_date("2023-12-25")
        datetime.date(2023, 12, 25)
        >>> parse_date("12/25/2023", "%m/%d/%Y")
        datetime.date(2023, 12, 25)
        >>> parse_date("2023-01-15")
        datetime.date(2023, 1, 15)
    """
    dt = datetime.strptime(date_str, format_str)
    return dt.date()


def add_days(dt: Union[date, datetime], days: int) -> date:
    """Add a specified number of days to a date.
    
    Args:
        dt: The date or datetime object
        days: Number of days to add (can be negative to subtract)
        
    Returns:
        A new date object with the days added
        
    Examples:
        >>> from datetime import date
        >>> add_days(date(2023, 12, 25), 7)
        datetime.date(2024, 1, 1)
        >>> add_days(date(2023, 12, 25), -5)
        datetime.date(2023, 12, 20)
        >>> add_days(date(2023, 1, 31), 1)
        datetime.date(2023, 2, 1)
        >>> add_days(date(2023, 12, 25), 0)
        datetime.date(2023, 12, 25)
    """
    if isinstance(dt, datetime):
        dt = dt.date()
    
    result = dt + timedelta(days=days)
    return result


def diff_days(dt1: Union[date, datetime], dt2: Union[date, datetime]) -> int:
    """Calculate the difference in days between two dates.
    
    Returns the number of days from dt1 to dt2 (dt2 - dt1).
    Positive if dt2 is later, negative if dt2 is earlier.
    
    Args:
        dt1: The first date or datetime object
        dt2: The second date or datetime object
        
    Returns:
        The number of days between the dates (dt2 - dt1)
        
    Examples:
        >>> from datetime import date
        >>> diff_days(date(2023, 12, 25), date(2024, 1, 1))
        7
        >>> diff_days(date(2024, 1, 1), date(2023, 12, 25))
        -7
        >>> diff_days(date(2023, 12, 25), date(2023, 12, 25))
        0
        >>> diff_days(date(2023, 1, 1), date(2023, 12, 31))
        364
    """
    if isinstance(dt1, datetime):
        dt1 = dt1.date()
    if isinstance(dt2, datetime):
        dt2 = dt2.date()
    
    delta = dt2 - dt1
    return delta.days


def is_weekend(dt: Union[date, datetime]) -> bool:
    """Check if a date falls on a weekend (Saturday or Sunday).
    
    Args:
        dt: The date or datetime object to check
        
    Returns:
        True if the date is a Saturday or Sunday, False otherwise
        
    Examples:
        >>> from datetime import date
        >>> is_weekend(date(2023, 12, 23))  # Saturday
        True
        >>> is_weekend(date(2023, 12, 24))  # Sunday
        True
        >>> is_weekend(date(2023, 12, 25))  # Monday
        False
        >>> is_weekend(date(2023, 12, 22))  # Friday
        False
    """
    if isinstance(dt, datetime):
        dt = dt.date()
    
    # weekday() returns 0 for Monday, 6 for Sunday
    # Saturday is 5, Sunday is 6
    return dt.weekday() in (5, 6)
