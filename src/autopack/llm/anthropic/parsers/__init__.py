"""Parser factory for Anthropic Builder output formats.

This module provides a unified interface for parsing different Builder output formats:
- NDJSON: Newline-delimited JSON with truncation tolerance
- Structured Edit: JSON with explicit edit operations
- Full File: Complete file replacements in JSON pack structure

Created as part of PR-CLIENT-2 to extract ~1,551 lines from anthropic_clients.py.
"""

from .full_file_parser import FullFileParser
from .ndjson_parser import NDJSONParserWrapper
from .structured_edit_parser import StructuredEditParser

__all__ = [
    "NDJSONParserWrapper",
    "StructuredEditParser",
    "FullFileParser",
    "ParserFactory",
]


class ParserFactory:
    """Factory for creating appropriate parser based on output format.

    This factory provides a unified interface for all parser types and handles
    the creation and initialization of parser instances.
    """

    @staticmethod
    def create_ndjson_parser() -> NDJSONParserWrapper:
        """Create NDJSON parser with fallback support.

        Returns:
            NDJSONParserWrapper instance
        """
        return NDJSONParserWrapper()

    @staticmethod
    def create_structured_edit_parser() -> StructuredEditParser:
        """Create structured edit parser.

        Returns:
            StructuredEditParser instance
        """
        return StructuredEditParser()

    @staticmethod
    def create_full_file_parser() -> FullFileParser:
        """Create full file parser.

        Returns:
            FullFileParser instance
        """
        return FullFileParser()

    @classmethod
    def get_parser(cls, format_type: str):
        """Get parser instance for the specified format type.

        Args:
            format_type: One of 'ndjson', 'structured_edit', 'full_file'

        Returns:
            Parser instance for the specified format

        Raises:
            ValueError: If format_type is not recognized
        """
        parsers = {
            "ndjson": cls.create_ndjson_parser,
            "structured_edit": cls.create_structured_edit_parser,
            "full_file": cls.create_full_file_parser,
        }

        if format_type not in parsers:
            raise ValueError(
                f"Unknown format type: {format_type}. Valid types: {', '.join(parsers.keys())}"
            )

        return parsers[format_type]()
