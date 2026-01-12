"""LLM response parsers package.

This package contains parsers for different LLM output formats.
"""

# Re-export JSONRepair from the parsers.py module (sibling file at autopack/llm/parsers.py)
# When both parsers.py and parsers/ directory exist, Python picks the directory.
# We use __import__ with fromlist to load the .py module directly.
import sys
from pathlib import Path

# Direct import using importlib to avoid recursion
import importlib.util

_parsers_file = Path(__file__).parent.parent / "parsers.py"
_spec = importlib.util.spec_from_file_location("autopack.llm._parsers_impl", _parsers_file)
_parsers_impl = importlib.util.module_from_spec(_spec)
sys.modules["autopack.llm._parsers_impl"] = _parsers_impl
_spec.loader.exec_module(_parsers_impl)

# Re-export all classes for backward compatibility
ParseResult = _parsers_impl.ParseResult
JSONRepair = _parsers_impl.JSONRepair
DiffExtractor = _parsers_impl.DiffExtractor
ResponseParser = _parsers_impl.ResponseParser
NDJSONOperation = _parsers_impl.NDJSONOperation
NDJSONParseResult = _parsers_impl.NDJSONParseResult
NDJSONParser = _parsers_impl.NDJSONParser

__all__ = [
    "ParseResult",
    "JSONRepair",
    "DiffExtractor",
    "ResponseParser",
    "NDJSONOperation",
    "NDJSONParseResult",
    "NDJSONParser",
]
