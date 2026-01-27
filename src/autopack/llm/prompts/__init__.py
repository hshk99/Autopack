"""
Prompt construction modules for LLM clients.

This package contains prompt builder functions extracted from client implementations
to separate prompt logic from transport and parsing concerns.
"""

import importlib.util

# Re-export classes from prompts.py module for backward compatibility
# When both prompts.py and prompts/ directory exist, Python picks the directory
import sys
from pathlib import Path

from .anthropic_builder_prompts import (
    build_minimal_system_prompt,
    build_system_prompt,
    build_user_prompt,
)

_prompts_file = Path(__file__).parent.parent / "prompts.py"
_spec = importlib.util.spec_from_file_location("autopack.llm._prompts_impl", _prompts_file)
_prompts_impl = importlib.util.module_from_spec(_spec)
sys.modules["autopack.llm._prompts_impl"] = _prompts_impl
_spec.loader.exec_module(_prompts_impl)

PromptConfig = _prompts_impl.PromptConfig
PromptParts = _prompts_impl.PromptParts
PromptBuilder = _prompts_impl.PromptBuilder

__all__ = [
    "build_system_prompt",
    "build_minimal_system_prompt",
    "build_user_prompt",
    "PromptConfig",
    "PromptParts",
    "PromptBuilder",
]
