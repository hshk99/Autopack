"""LLM integration package for Autopack.

This package contains extracted modules from anthropic_clients.py:
- transport: Anthropic API client wrapper and streaming utilities
- prompts: System and user prompt builders
- parsers: Response parsing for various output formats (JSON, NDJSON, diff)
- diff_generator: Unified diff generation utilities

Usage:
    from autopack.llm.transport import AnthropicTransport
    from autopack.llm.prompts import PromptBuilder
    from autopack.llm.parsers import ResponseParser
    from autopack.llm.diff_generator import DiffGenerator
"""

from autopack.llm.transport import AnthropicTransport
# from autopack.llm.prompts import PromptBuilder  # TODO: Will be added in future PR
from autopack.llm.parsers import ResponseParser
from autopack.llm.diff_generator import DiffGenerator

__all__ = [
    "AnthropicTransport",
    # "PromptBuilder",  # TODO: Will be added in future PR
    "ResponseParser",
    "DiffGenerator",
]
