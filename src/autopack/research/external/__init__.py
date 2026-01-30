"""External registry scanners for discovering available tools and services.

This module provides scanners for external registries like MCP (Model Context Protocol)
and package registries (NPM, PyPI) to identify tools, servers, and packages that can be
integrated into projects.
"""

from __future__ import annotations

from autopack.research.external.mcp_scanner import (
    MCPRegistryScanner,
    MCPServer,
    MCPServerMaintainer,
    MCPServerMaturity,
    ScanResult,
)
from autopack.research.external.package_scanner import (
    PackageInfo,
    PackageRegistry,
    PackageScanner,
    SearchResult,
)

__all__ = [
    "MCPRegistryScanner",
    "MCPServer",
    "MCPServerMaturity",
    "MCPServerMaintainer",
    "ScanResult",
    "PackageScanner",
    "PackageInfo",
    "PackageRegistry",
    "SearchResult",
]
