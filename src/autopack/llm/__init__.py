"""LLM integration package for Autopack.

This package contains extracted modules from anthropic_clients.py as part of
the god file refactoring (Item 1.1 - PR-LLM-1).

Current modules:
- providers: Provider-specific transport wrappers (Anthropic, OpenAI, etc.)
- client_resolution: Client resolution and provider fallback logic (PR-SVC-1)

Future modules (to be extracted):
- prompts: System and user prompt builders
- parsers: Response parsing for various output formats (JSON, NDJSON, diff)
- diff_generator: Unified diff generation utilities

Usage:
    from autopack.llm.providers import AnthropicTransport
    from autopack.llm.client_resolution import resolve_client_and_model
"""

# Import client resolution functions (PR-SVC-1)
from autopack.llm.client_resolution import (  # noqa: F401
    resolve_auditor_client,
    resolve_builder_client,
    resolve_client_and_model,
)

__all__ = [
    "resolve_client_and_model",
    "resolve_builder_client",
    "resolve_auditor_client",
]
