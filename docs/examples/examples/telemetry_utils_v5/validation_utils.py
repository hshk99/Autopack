"""Validation utility functions for data validation.

This module provides common validation utilities including:
- is_email: Validate if a string is a valid email address
- is_url: Validate if a string is a valid URL
- is_int: Check if a string can be converted to an integer
- is_float: Check if a string can be converted to a float
- validate_range: Validate if a number is within a specified range
"""

import re
from typing import Union, Optional
from urllib.parse import urlparse


def is_email(email: str) -> bool:
    """Validate if a string is a valid email address.

    Uses a regular expression to check if the string matches a basic
    email format (local@domain). This is a simplified validation and
    may not catch all edge cases.

    Args:
        email: The string to validate as an email address

    Returns:
        True if the string is a valid email format, False otherwise

    Examples:
        >>> is_email('user@example.com')
        True
        >>> is_email('john.doe@company.co.uk')
        True
        >>> is_email('invalid.email')
        False
        >>> is_email('missing@domain')
        False
        >>> is_email('@nodomain.com')
        False
        >>> is_email('')
        False
    """
    if not email or not isinstance(email, str):
        return False

    # Basic email pattern: local-part@domain
    # Local part: alphanumeric, dots, hyphens, underscores
    # Domain: alphanumeric, dots, hyphens, must have at least one dot
    pattern = r"^[a-zA-Z0-9._%-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    return bool(re.match(pattern, email))


def is_url(url: str, require_scheme: bool = True) -> bool:
    """Validate if a string is a valid URL.

    Checks if the string is a properly formatted URL. Can optionally
    require a scheme (http://, https://, etc.).

    Args:
        url: The string to validate as a URL
        require_scheme: If True, URL must have a scheme (default: True)

    Returns:
        True if the string is a valid URL format, False otherwise

    Examples:
        >>> is_url('https://www.example.com')
        True
        >>> is_url('http://example.com/path?query=value')
        True
        >>> is_url('ftp://files.example.com')
        True
        >>> is_url('www.example.com')
        False
        >>> is_url('www.example.com', require_scheme=False)
        True
        >>> is_url('not a url')
        False
        >>> is_url('')
        False
    """
    if not url or not isinstance(url, str):
        return False

    try:
        result = urlparse(url)

        # Check if scheme is present when required
        if require_scheme and not result.scheme:
            return False

        # Must have a netloc (domain) or path
        if not result.netloc and not result.path:
            return False

        # If no scheme required, check for basic domain pattern
        if not require_scheme and not result.scheme:
            # Simple check for domain-like pattern
            domain_pattern = r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
            return bool(re.match(domain_pattern, url.split("/")[0]))

        return True
    except Exception:
        return False


def is_int(value: str) -> bool:
    """Check if a string can be converted to an integer.

    Attempts to convert the string to an integer and returns True if
    successful, False otherwise. Handles negative numbers and whitespace.

    Args:
        value: The string to check

    Returns:
        True if the string can be converted to an integer, False otherwise

    Examples:
        >>> is_int('123')
        True
        >>> is_int('-456')
        True
        >>> is_int('  789  ')
        True
        >>> is_int('12.34')
        False
        >>> is_int('abc')
        False
        >>> is_int('')
        False
        >>> is_int('1e5')
        False
    """
    if not isinstance(value, str):
        return False

    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False


def is_float(value: str) -> bool:
    """Check if a string can be converted to a float.

    Attempts to convert the string to a float and returns True if
    successful, False otherwise. Handles negative numbers, decimals,
    scientific notation, and whitespace.

    Args:
        value: The string to check

    Returns:
        True if the string can be converted to a float, False otherwise

    Examples:
        >>> is_float('123.45')
        True
        >>> is_float('-67.89')
        True
        >>> is_float('1e5')
        True
        >>> is_float('  3.14  ')
        True
        >>> is_float('123')
        True
        >>> is_float('abc')
        False
        >>> is_float('')
        False
        >>> is_float('12.34.56')
        False
    """
    if not isinstance(value, str):
        return False

    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def validate_range(
    value: Union[int, float],
    min_value: Optional[Union[int, float]] = None,
    max_value: Optional[Union[int, float]] = None,
    inclusive: bool = True,
) -> bool:
    """Validate if a number is within a specified range.

    Checks if a numeric value falls within the specified minimum and maximum
    bounds. Can be inclusive or exclusive of the bounds.

    Args:
        value: The numeric value to validate
        min_value: Optional minimum bound (None means no minimum)
        max_value: Optional maximum bound (None means no maximum)
        inclusive: If True, bounds are inclusive; if False, exclusive (default: True)

    Returns:
        True if the value is within the specified range, False otherwise

    Examples:
        >>> validate_range(5, min_value=0, max_value=10)
        True
        >>> validate_range(10, min_value=0, max_value=10)
        True
        >>> validate_range(10, min_value=0, max_value=10, inclusive=False)
        False
        >>> validate_range(15, min_value=0, max_value=10)
        False
        >>> validate_range(-5, min_value=0)
        False
        >>> validate_range(100, max_value=50)
        False
        >>> validate_range(5, min_value=None, max_value=None)
        True
        >>> validate_range(3.14, min_value=3.0, max_value=4.0)
        True
    """
    if not isinstance(value, (int, float)):
        return False

    # Check minimum bound
    if min_value is not None:
        if inclusive:
            if value < min_value:
                return False
        else:
            if value <= min_value:
                return False

    # Check maximum bound
    if max_value is not None:
        if inclusive:
            if value > max_value:
                return False
        else:
            if value >= max_value:
                return False

    return True
