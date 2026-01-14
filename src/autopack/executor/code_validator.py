"""Code validation with input sanitization.

IMP-S01: Provides secure code validation with input sanitization to prevent
code injection attacks.
"""

import ast
import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class CodeValidator:
    """Validates code with input sanitization to prevent injection attacks."""

    # Dangerous patterns that should be rejected or sanitized
    DANGEROUS_PATTERNS = [
        r"__import__\s*\(",  # Dynamic imports
        r"eval\s*\(",  # eval() calls
        r"exec\s*\(",  # exec() calls
        r"compile\s*\(",  # compile() calls
        r"globals\s*\(",  # globals() access
        r"locals\s*\(",  # locals() access
        r"__builtins__",  # Direct builtins access
        r"__subclasses__",  # Class hierarchy traversal
        r"__bases__",  # Base class access for exploitation
        r"\.im_func",  # Method function access
        r"\.func_globals",  # Function globals access
    ]

    # Maximum code length to prevent DoS
    MAX_CODE_LENGTH = 100000  # 100KB

    @staticmethod
    def sanitize_input(code: str) -> str:
        """IMP-S01: Sanitize code input before validation.

        Args:
            code: Raw code input to sanitize

        Returns:
            Sanitized code string

        Raises:
            ValueError: If input contains dangerous patterns or is too large
        """
        if not isinstance(code, str):
            raise ValueError("Code input must be a string")

        # Check for empty input
        if not code.strip():
            return ""

        # Check code length to prevent DoS
        if len(code) > CodeValidator.MAX_CODE_LENGTH:
            raise ValueError(
                f"Code input exceeds maximum length ({CodeValidator.MAX_CODE_LENGTH} characters)"
            )

        # Check for dangerous patterns
        for pattern in CodeValidator.DANGEROUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                raise ValueError(f"Code contains potentially dangerous pattern: {pattern}")

        # Remove null bytes and other control characters (except newlines/tabs)
        sanitized = "".join(
            char for char in code if char.isprintable() or char in ["\n", "\r", "\t"]
        )

        return sanitized

    @staticmethod
    def validate_python_syntax(code: str, sanitize: bool = True) -> Tuple[bool, Optional[str]]:
        """Validate Python code syntax with optional sanitization.

        Args:
            code: Python code to validate
            sanitize: Whether to sanitize input first (default: True)

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # IMP-S01: Sanitize input by default
            if sanitize:
                code = CodeValidator.sanitize_input(code)

            # Parse code to check syntax
            ast.parse(code)
            return True, None

        except ValueError as e:
            # Sanitization error
            return False, f"Sanitization error: {str(e)}"

        except SyntaxError as e:
            # Python syntax error
            return False, f"Syntax error at line {e.lineno}: {e.msg}"

        except Exception as e:
            # Other errors
            return False, f"Validation error: {str(e)}"

    @staticmethod
    def is_safe_for_execution(code: str) -> Tuple[bool, Optional[str]]:
        """Check if code is safe for execution.

        More strict than syntax validation - checks for potentially dangerous constructs.

        Args:
            code: Python code to check

        Returns:
            Tuple of (is_safe, reason)
        """
        try:
            # First sanitize and validate syntax
            code = CodeValidator.sanitize_input(code)
            is_valid, error = CodeValidator.validate_python_syntax(code, sanitize=False)

            if not is_valid:
                return False, error

            # Parse AST and check for dangerous node types
            tree = ast.parse(code)

            for node in ast.walk(tree):
                # Check for eval/exec usage
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ["eval", "exec", "compile", "__import__"]:
                            return False, f"Dangerous function call: {node.func.id}"

                # Check for attribute access to dangerous methods
                if isinstance(node, ast.Attribute):
                    if node.attr in [
                        "__import__",
                        "__builtins__",
                        "__subclasses__",
                        "func_globals",
                    ]:
                        return False, f"Dangerous attribute access: {node.attr}"

            return True, None

        except ValueError as e:
            return False, f"Safety check failed: {str(e)}"

        except Exception as e:
            logger.warning(f"Unexpected error during safety check: {e}")
            return False, f"Safety check error: {str(e)}"


def validate_code(code: str, strict: bool = False) -> Tuple[bool, Optional[str]]:
    """Convenience function for code validation.

    Args:
        code: Python code to validate
        strict: If True, perform safety checks in addition to syntax validation

    Returns:
        Tuple of (is_valid, error_message)
    """
    if strict:
        return CodeValidator.is_safe_for_execution(code)
    else:
        return CodeValidator.validate_python_syntax(code)
