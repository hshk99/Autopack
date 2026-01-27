"""Toolchain adapters for universal language/framework support.

This package provides modular toolchain detection and command inference
for different programming languages and frameworks.
"""

from .adapter import ToolchainAdapter, ToolchainDetectionResult
from .go_adapter import GoAdapter
from .java_adapter import JavaAdapter
from .node_adapter import NodeAdapter
from .python_adapter import PythonAdapter
from .rust_adapter import RustAdapter

__all__ = [
    "ToolchainAdapter",
    "ToolchainDetectionResult",
    "PythonAdapter",
    "NodeAdapter",
    "GoAdapter",
    "RustAdapter",
    "JavaAdapter",
]
