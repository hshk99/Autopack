"""
Discovery module for Autopack research.

Contains discovery integration modules for various sources including:
- Web discovery for general information retrieval
- GitHub discovery for code repository mining
- Reddit discovery for community discussions
- MCP registry discovery for Model Context Protocol tool integration
- Project history analysis for cross-project learning
"""

from autopack.research.discovery.github_discovery import GitHubDiscovery
from autopack.research.discovery.mcp_discovery import (MCPRegistryCache,
                                                       MCPRegistryScanner,
                                                       MCPScanResult,
                                                       MCPToolCapability,
                                                       MCPToolDescriptor,
                                                       MCPToolMaintainer,
                                                       MCPToolMaturity)
from autopack.research.discovery.reddit_discovery import RedditDiscovery
from autopack.research.discovery.web_discovery import WebDiscovery
from autopack.research.discovery.project_history_analyzer import (
    HistoryAnalysisResult,
    ProjectDecision,
    ProjectHistoryAnalyzer,
    ProjectSummary,
)

__all__ = [
    # Web discovery
    "WebDiscovery",
    # GitHub discovery
    "GitHubDiscovery",
    # Reddit discovery
    "RedditDiscovery",
    # MCP discovery
    "MCPRegistryScanner",
    "MCPRegistryCache",
    "MCPToolDescriptor",
    "MCPToolCapability",
    "MCPScanResult",
    "MCPToolMaturity",
    "MCPToolMaintainer",
    # Project history analyzer (cross-project learning)
    "ProjectHistoryAnalyzer",
    "ProjectSummary",
    "ProjectDecision",
    "HistoryAnalysisResult",
]
