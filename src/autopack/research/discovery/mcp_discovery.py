"""
MCP Registry Discovery Module

This module provides functionality to scan and discover available MCP (Model Context Protocol)
tools and servers that are relevant to project requirements. It integrates with the research
pipeline to recommend available MCP integrations.
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MCPToolMaturity(Enum):
    """Maturity levels for MCP tools/servers."""

    STABLE = "stable"
    BETA = "beta"
    EXPERIMENTAL = "experimental"


class MCPToolMaintainer(Enum):
    """Maintainer types for MCP tools."""

    OFFICIAL = "official"
    COMMUNITY = "community"


@dataclass
class MCPToolCapability:
    """Represents a capability of an MCP tool."""

    name: str
    description: str
    version: str = "1.0"
    supported_formats: List[str] = field(default_factory=list)


@dataclass
class MCPToolDescriptor:
    """Describes an available MCP tool/server."""

    name: str
    description: str
    capabilities: List[MCPToolCapability] = field(default_factory=list)
    maturity: MCPToolMaturity = MCPToolMaturity.STABLE
    maintainer: MCPToolMaintainer = MCPToolMaintainer.COMMUNITY
    requirements: Dict[str, Any] = field(default_factory=dict)
    url: Optional[str] = None
    documentation_url: Optional[str] = None
    npm_package: Optional[str] = None
    github_url: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    compatibility_version: str = "0.1.0"
    installation_difficulty: str = "low"  # low, medium, high
    support_async: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert descriptor to dictionary for serialization."""
        return {
            "name": self.name,
            "description": self.description,
            "capabilities": [
                {
                    "name": cap.name,
                    "description": cap.description,
                    "version": cap.version,
                    "supported_formats": cap.supported_formats,
                }
                for cap in self.capabilities
            ],
            "maturity": self.maturity.value,
            "maintainer": self.maintainer.value,
            "requirements": self.requirements,
            "url": self.url,
            "documentation_url": self.documentation_url,
            "npm_package": self.npm_package,
            "github_url": self.github_url,
            "tags": self.tags,
            "compatibility_version": self.compatibility_version,
            "installation_difficulty": self.installation_difficulty,
            "support_async": self.support_async,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPToolDescriptor":
        """Create descriptor from dictionary."""
        capabilities = [
            MCPToolCapability(
                name=cap["name"],
                description=cap["description"],
                version=cap.get("version", "1.0"),
                supported_formats=cap.get("supported_formats", []),
            )
            for cap in data.get("capabilities", [])
        ]

        return cls(
            name=data["name"],
            description=data["description"],
            capabilities=capabilities,
            maturity=MCPToolMaturity(data.get("maturity", "stable")),
            maintainer=MCPToolMaintainer(data.get("maintainer", "community")),
            requirements=data.get("requirements", {}),
            url=data.get("url"),
            documentation_url=data.get("documentation_url"),
            npm_package=data.get("npm_package"),
            github_url=data.get("github_url"),
            tags=data.get("tags", []),
            compatibility_version=data.get("compatibility_version", "0.1.0"),
            installation_difficulty=data.get("installation_difficulty", "low"),
            support_async=data.get("support_async", True),
        )


@dataclass
class MCPScanResult:
    """Result of MCP registry scan."""

    project_type: str
    requirements: Dict[str, Any]
    discovered_tools: List[MCPToolDescriptor] = field(default_factory=list)
    matches_by_requirement: Dict[str, List[MCPToolDescriptor]] = field(default_factory=dict)
    total_matches: int = 0
    scan_timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert scan result to dictionary."""
        return {
            "project_type": self.project_type,
            "requirements": self.requirements,
            "discovered_tools": [tool.to_dict() for tool in self.discovered_tools],
            "matches_by_requirement": {
                req: [tool.to_dict() for tool in tools]
                for req, tools in self.matches_by_requirement.items()
            },
            "total_matches": self.total_matches,
            "scan_timestamp": self.scan_timestamp,
        }

    def to_json(self) -> str:
        """Convert scan result to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPScanResult":
        """
        Create MCPScanResult from dictionary.

        Args:
            data: Dictionary with scan result data

        Returns:
            MCPScanResult instance
        """
        discovered_tools = [
            MCPToolDescriptor.from_dict(tool_data) for tool_data in data.get("discovered_tools", [])
        ]

        matches_by_requirement = {}
        for req, tools_data in data.get("matches_by_requirement", {}).items():
            matches_by_requirement[req] = [
                MCPToolDescriptor.from_dict(tool_data) for tool_data in tools_data
            ]

        return cls(
            project_type=data.get("project_type", "unknown"),
            requirements=data.get("requirements", {}),
            discovered_tools=discovered_tools,
            matches_by_requirement=matches_by_requirement,
            total_matches=data.get("total_matches", 0),
            scan_timestamp=data.get("scan_timestamp"),
        )


class MCPRegistryCache:
    """Cache manager for MCP registry scan results with TTL support."""

    def __init__(self, ttl_seconds: int = 3600):
        """
        Initialize the cache manager.

        Args:
            ttl_seconds: Time-to-live for cached results in seconds (default 1 hour)
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl_seconds = ttl_seconds
        self._cache_stats = {"hits": 0, "misses": 0, "evictions": 0}
        logger.debug(f"Initialized MCPRegistryCache with TTL={ttl_seconds}s")

    def _make_key(self, project_type: str, requirements: Dict[str, Any]) -> str:
        """
        Create a cache key from project type and requirements.

        Args:
            project_type: Type of project
            requirements: Project requirements dict

        Returns:
            Hash key for caching
        """
        # Create stable hash from requirements
        req_json = json.dumps(requirements, sort_keys=True)
        combined = f"{project_type}:{req_json}"
        return hashlib.sha256(combined.encode()).hexdigest()

    def get(self, project_type: str, requirements: Dict[str, Any]) -> Optional[MCPScanResult]:
        """
        Get cached scan result if available and not expired.

        Args:
            project_type: Type of project
            requirements: Project requirements dict

        Returns:
            Cached MCPScanResult or None if not in cache or expired
        """
        key = self._make_key(project_type, requirements)

        if key not in self._cache:
            self._cache_stats["misses"] += 1
            return None

        cache_entry = self._cache[key]
        current_time = time.time()

        # Check if cache entry has expired
        if current_time - cache_entry["timestamp"] > self._ttl_seconds:
            del self._cache[key]
            self._cache_stats["evictions"] += 1
            self._cache_stats["misses"] += 1
            logger.debug(f"Cache entry expired for key: {key[:8]}...")
            return None

        self._cache_stats["hits"] += 1
        logger.debug(
            f"Cache hit for key: {key[:8]}... (age: {current_time - cache_entry['timestamp']:.1f}s)"
        )
        return cache_entry["result"]

    def set(self, project_type: str, requirements: Dict[str, Any], result: MCPScanResult) -> None:
        """
        Store a scan result in cache.

        Args:
            project_type: Type of project
            requirements: Project requirements dict
            result: MCPScanResult to cache
        """
        key = self._make_key(project_type, requirements)
        self._cache[key] = {
            "timestamp": time.time(),
            "result": result,
            "project_type": project_type,
        }
        logger.debug(f"Cached scan result for key: {key[:8]}... (cache size: {len(self._cache)})")

    def clear(self) -> None:
        """Clear all cached entries."""
        evicted = len(self._cache)
        self._cache.clear()
        self._cache_stats["evictions"] += evicted
        logger.debug(f"Cleared cache ({evicted} entries evicted)")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache hits, misses, and evictions
        """
        total_requests = self._cache_stats["hits"] + self._cache_stats["misses"]
        hit_rate = self._cache_stats["hits"] / total_requests * 100 if total_requests > 0 else 0

        return {
            "size": len(self._cache),
            "hits": self._cache_stats["hits"],
            "misses": self._cache_stats["misses"],
            "evictions": self._cache_stats["evictions"],
            "hit_rate_percent": hit_rate,
        }


class MCPRegistryScanner:
    """Scans MCP registry for tools relevant to project requirements."""

    # Built-in MCP registry (would be extended with external API calls in production)
    _DEFAULT_REGISTRY = [
        MCPToolDescriptor(
            name="brave-search",
            description="Web search integration for Brave Search API",
            capabilities=[
                MCPToolCapability(
                    name="web_search",
                    description="Search the web using Brave Search",
                    version="1.0",
                    supported_formats=["json", "text"],
                ),
                MCPToolCapability(
                    name="news_search",
                    description="Search news articles",
                    version="1.0",
                    supported_formats=["json"],
                ),
            ],
            maturity=MCPToolMaturity.STABLE,
            maintainer=MCPToolMaintainer.OFFICIAL,
            requirements={"api_key_required": True, "rate_limit": "1000/day"},
            url="https://search.brave.com/",
            npm_package="@modelcontextprotocol/server-brave-search",
            github_url="https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search",
            tags=["search", "web", "news", "discovery"],
            installation_difficulty="low",
        ),
        MCPToolDescriptor(
            name="github",
            description="GitHub API integration for repository and code search",
            capabilities=[
                MCPToolCapability(
                    name="repo_search",
                    description="Search GitHub repositories",
                    version="1.0",
                    supported_formats=["json"],
                ),
                MCPToolCapability(
                    name="code_search",
                    description="Search code across repositories",
                    version="1.0",
                    supported_formats=["json"],
                ),
                MCPToolCapability(
                    name="issue_search",
                    description="Search issues and discussions",
                    version="1.0",
                    supported_formats=["json"],
                ),
            ],
            maturity=MCPToolMaturity.STABLE,
            maintainer=MCPToolMaintainer.OFFICIAL,
            requirements={"token_required": True, "rate_limit": "5000/hour"},
            npm_package="@modelcontextprotocol/server-github",
            github_url="https://github.com/modelcontextprotocol/servers/tree/main/src/github",
            tags=["code", "collaboration", "repository", "discovery"],
            installation_difficulty="low",
        ),
        MCPToolDescriptor(
            name="postgres",
            description="PostgreSQL database integration",
            capabilities=[
                MCPToolCapability(
                    name="query_database",
                    description="Execute SQL queries against PostgreSQL",
                    version="1.0",
                    supported_formats=["json"],
                ),
                MCPToolCapability(
                    name="schema_introspection",
                    description="Inspect database schema",
                    version="1.0",
                    supported_formats=["json"],
                ),
            ],
            maturity=MCPToolMaturity.STABLE,
            maintainer=MCPToolMaintainer.OFFICIAL,
            requirements={"connection_string_required": True, "postgres_version": "12+"},
            npm_package="@modelcontextprotocol/server-postgres",
            github_url="https://github.com/modelcontextprotocol/servers/tree/main/src/postgres",
            tags=["database", "data", "sql"],
            installation_difficulty="medium",
        ),
        MCPToolDescriptor(
            name="filesystem",
            description="Local filesystem access and file operations",
            capabilities=[
                MCPToolCapability(
                    name="read_file",
                    description="Read file contents",
                    version="1.0",
                    supported_formats=["text", "json", "binary"],
                ),
                MCPToolCapability(
                    name="write_file",
                    description="Write files to disk",
                    version="1.0",
                    supported_formats=["text", "json"],
                ),
                MCPToolCapability(
                    name="list_files",
                    description="List directory contents",
                    version="1.0",
                    supported_formats=["json"],
                ),
            ],
            maturity=MCPToolMaturity.STABLE,
            maintainer=MCPToolMaintainer.OFFICIAL,
            requirements={"filesystem_access": True, "permissions_required": True},
            npm_package="@modelcontextprotocol/server-filesystem",
            github_url="https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem",
            tags=["filesystem", "files", "io"],
            installation_difficulty="low",
        ),
        MCPToolDescriptor(
            name="memory",
            description="Memory and knowledge base operations",
            capabilities=[
                MCPToolCapability(
                    name="store_memory",
                    description="Store facts and knowledge",
                    version="1.0",
                    supported_formats=["text", "json"],
                ),
                MCPToolCapability(
                    name="retrieve_memory",
                    description="Query stored knowledge",
                    version="1.0",
                    supported_formats=["json"],
                ),
                MCPToolCapability(
                    name="update_memory",
                    description="Update stored information",
                    version="1.0",
                    supported_formats=["json"],
                ),
            ],
            maturity=MCPToolMaturity.BETA,
            maintainer=MCPToolMaintainer.OFFICIAL,
            requirements={"storage_backend": "required", "query_capability": True},
            npm_package="@modelcontextprotocol/server-memory",
            github_url="https://github.com/modelcontextprotocol/servers/tree/main/src/memory",
            tags=["memory", "knowledge", "storage"],
            installation_difficulty="medium",
        ),
    ]

    def __init__(self, cache_ttl_seconds: int = 3600):
        """
        Initialize the MCP registry scanner with default tools.

        Args:
            cache_ttl_seconds: TTL for scan result cache in seconds
        """
        self.registry = self._DEFAULT_REGISTRY.copy()
        self._cache = MCPRegistryCache(ttl_seconds=cache_ttl_seconds)
        logger.debug(
            f"Initialized MCPRegistryScanner with {len(self.registry)} tools and cache TTL={cache_ttl_seconds}s"
        )

    async def scan_mcp_registry(
        self, project_type: str, requirements: Dict[str, Any]
    ) -> MCPScanResult:
        """
        Scan MCP registry for tools matching project requirements.

        Results are cached for performance. Check cache first before performing full scan.

        Args:
            project_type: Type of project (e.g., 'web-app', 'data-pipeline', 'api')
            requirements: Dictionary of project requirements

        Returns:
            MCPScanResult with discovered tools and matches
        """
        # Check cache first
        cached_result = self._cache.get(project_type, requirements)
        if cached_result is not None:
            logger.info(
                f"Cache hit: returning cached scan for {project_type} "
                f"({len(cached_result.discovered_tools)} tools)"
            )
            return cached_result

        logger.info(
            f"Scanning MCP registry for {project_type} with requirements: {list(requirements.keys())}"
        )

        discovered = []
        matches_by_requirement = {}

        # Match tools against each requirement
        for requirement, value in requirements.items():
            matching_tools = self.match_requirements(requirement, value)
            if matching_tools:
                matches_by_requirement[requirement] = matching_tools
                discovered.extend(matching_tools)

        # Remove duplicates while preserving order
        unique_discovered = []
        seen_names = set()
        for tool in discovered:
            if tool.name not in seen_names:
                unique_discovered.append(tool)
                seen_names.add(tool.name)

        # Score and sort by fit
        scored_tools = [
            (tool, self.evaluate_tool_fit(tool, requirements)) for tool in unique_discovered
        ]
        scored_tools.sort(key=lambda x: x[1], reverse=True)
        final_tools = [tool for tool, score in scored_tools]

        result = MCPScanResult(
            project_type=project_type,
            requirements=requirements,
            discovered_tools=final_tools,
            matches_by_requirement=matches_by_requirement,
            total_matches=len(final_tools),
            scan_timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        # Cache the result
        self._cache.set(project_type, requirements, result)

        logger.info(f"Scan complete: found {result.total_matches} tools matching requirements")
        return result

    def match_requirements(self, requirement: str, value: Any) -> List[MCPToolDescriptor]:
        """
        Find tools that match a specific requirement.

        Args:
            requirement: Requirement key (e.g., 'needs_search', 'needs_database')
            value: Requirement value

        Returns:
            List of matching MCPToolDescriptor objects
        """
        matching = []

        # Map requirements to tool capabilities/tags
        requirement_map = {
            "needs_search": ["search", "web", "news"],
            "needs_code_search": ["code", "repository"],
            "needs_database": ["database", "sql"],
            "needs_filesystem": ["filesystem", "files"],
            "needs_memory": ["memory", "knowledge"],
            "needs_collaboration": ["collaboration", "repository"],
            "needs_async": None,  # Check support_async flag
        }

        search_tags = requirement_map.get(requirement.lower(), [])

        for tool in self.registry:
            # Check tag matches
            if search_tags and any(tag in tool.tags for tag in search_tags):
                matching.append(tool)
            # Check async support if needed
            elif requirement.lower() == "needs_async" and tool.support_async:
                matching.append(tool)
            # Check capability names
            elif any(cap.name == requirement.lower() for cap in tool.capabilities):
                matching.append(tool)

        logger.debug(f"Found {len(matching)} tools matching requirement '{requirement}'")
        return matching

    def evaluate_tool_fit(self, tool: MCPToolDescriptor, requirements: Dict[str, Any]) -> float:
        """
        Evaluate how well a tool fits the project requirements.

        Args:
            tool: MCPToolDescriptor to evaluate
            requirements: Project requirements

        Returns:
            Compatibility score from 0.0 to 1.0
        """
        score = 0.5  # Base score

        # Bonus for stable maturity
        if tool.maturity == MCPToolMaturity.STABLE:
            score += 0.2
        elif tool.maturity == MCPToolMaturity.BETA:
            score += 0.1

        # Bonus for official maintainer
        if tool.maintainer == MCPToolMaintainer.OFFICIAL:
            score += 0.15

        # Bonus for low installation difficulty
        if tool.installation_difficulty == "low":
            score += 0.1
        elif tool.installation_difficulty == "medium":
            score += 0.05

        # Bonus for async support if needed
        if requirements.get("needs_async") and tool.support_async:
            score += 0.1

        # Count matching tags
        requirement_tags = []
        for req_key in requirements.keys():
            req_map = {
                "needs_search": ["search"],
                "needs_code": ["code"],
                "needs_database": ["database"],
                "needs_filesystem": ["filesystem"],
                "needs_memory": ["memory"],
            }
            requirement_tags.extend(req_map.get(req_key, []))

        matching_tags = sum(1 for tag in tool.tags if tag in requirement_tags)
        tag_score = min(0.15 * matching_tags, 0.3)  # Max 0.3 bonus
        score += tag_score

        # Normalize to 0.0-1.0
        return min(max(score, 0.0), 1.0)

    def register_custom_tool(self, tool: MCPToolDescriptor) -> None:
        """
        Register a custom MCP tool in the registry.

        Args:
            tool: MCPToolDescriptor to register
        """
        # Check for duplicates
        if any(t.name == tool.name for t in self.registry):
            logger.warning(f"Tool '{tool.name}' already registered, updating")
            self.registry = [t for t in self.registry if t.name != tool.name]

        self.registry.append(tool)
        logger.info(f"Registered custom MCP tool: {tool.name}")

    def get_tool_by_name(self, name: str) -> Optional[MCPToolDescriptor]:
        """
        Get a specific tool by name.

        Args:
            name: Name of the tool

        Returns:
            MCPToolDescriptor if found, None otherwise
        """
        for tool in self.registry:
            if tool.name == name:
                return tool
        return None

    def list_all_tools(self) -> List[MCPToolDescriptor]:
        """
        Get list of all available tools.

        Returns:
            List of all MCPToolDescriptor objects
        """
        return self.registry.copy()

    def get_tools_by_tag(self, tag: str) -> List[MCPToolDescriptor]:
        """
        Get tools that have a specific tag.

        Args:
            tag: Tag to search for

        Returns:
            List of matching MCPToolDescriptor objects
        """
        return [tool for tool in self.registry if tag in tool.tags]

    def get_tools_by_maturity(self, maturity: MCPToolMaturity) -> List[MCPToolDescriptor]:
        """
        Get tools with specific maturity level.

        Args:
            maturity: MCPToolMaturity level

        Returns:
            List of matching MCPToolDescriptor objects
        """
        return [tool for tool in self.registry if tool.maturity == maturity]

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache performance metrics
        """
        return self._cache.get_stats()

    def clear_cache(self) -> None:
        """Clear all cached scan results."""
        self._cache.clear()

    def set_cache_ttl(self, ttl_seconds: int) -> None:
        """
        Set the time-to-live for cache entries.

        Args:
            ttl_seconds: TTL in seconds
        """
        self._cache._ttl_seconds = ttl_seconds
        logger.info(f"Updated cache TTL to {ttl_seconds} seconds")
