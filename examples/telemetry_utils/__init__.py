"""Telemetry utilities package.

This package provides various utility functions for string and number operations.
"""

from examples.telemetry_utils.string_utils import capitalize_words, reverse_string
from examples.telemetry_utils.number_utils import is_even, is_prime, factorial

__all__ = [
    "capitalize_words",
    "reverse_string",
    "is_even",
    "is_prime",
    "factorial",
]
