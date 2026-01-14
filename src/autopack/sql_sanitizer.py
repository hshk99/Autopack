"""SQL input validation and sanitization utilities."""

import re
from typing import Any


class SQLSanitizer:
    """Validates and sanitizes SQL parameters to prevent injection attacks."""

    UNSAFE_PATTERNS = [
        r"--",  # SQL comment
        r";\s*DROP",  # DROP statement
        r";\s*DELETE",  # DELETE statement
        r"UNION\s+SELECT",  # UNION injection
        r"OR\s+1\s*=\s*1",  # Always-true condition
        r"OR\s+.*\s*=\s*.*",  # Generic OR condition
        r"';",  # Quote + semicolon
        r"xp_cmdshell",  # SQL Server command execution
        r"exec\s*\(",  # Exec statement
    ]

    @staticmethod
    def validate_parameter(param: Any) -> Any:
        """
        Validate parameter for SQL safety.

        Args:
            param: Parameter to validate

        Returns:
            Validated parameter

        Raises:
            ValueError: If parameter contains unsafe SQL patterns
        """
        if param is None:
            return None

        if not isinstance(param, (str, int, float, bool)):
            raise ValueError(
                f"Invalid parameter type: {type(param).__name__}. "
                "Only str, int, float, bool are allowed."
            )

        if isinstance(param, str):
            for pattern in SQLSanitizer.UNSAFE_PATTERNS:
                if re.search(pattern, param, re.IGNORECASE):
                    raise ValueError(f"Unsafe SQL pattern detected in parameter: {pattern}")

        return param
