"""MCP Registry Scanner for discovering available MCP servers and tools.

Scans the MCP registry to identify tools that can be integrated into projects.
Supports searching official and community MCP server registries.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class MCPServerMaturity(Enum):
    """Maturity level of an MCP server."""

    STABLE = "stable"
    BETA = "beta"
    EXPERIMENTAL = "experimental"
    UNKNOWN = "unknown"


class MCPServerMaintainer(Enum):
    """Maintainer type for an MCP server."""

    OFFICIAL = "official"
    COMMUNITY = "community"
    UNKNOWN = "unknown"


@dataclass
class MCPServer:
    """Represents an MCP server from the registry."""

    name: str
    description: str = ""
    url: str = ""
    repository: str = ""
    npm_package: str = ""
    capabilities: List[str] = field(default_factory=list)
    maturity: MCPServerMaturity = MCPServerMaturity.UNKNOWN
    maintainer: MCPServerMaintainer = MCPServerMaintainer.UNKNOWN
    stars: int = 0
    last_updated: Optional[datetime] = None
    documentation: str = ""
    setup_complexity: str = "medium"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "repository": self.repository,
            "npm_package": self.npm_package,
            "capabilities": self.capabilities,
            "maturity": self.maturity.value,
            "maintainer": self.maintainer.value,
            "stars": self.stars,
            "last_updated": (self.last_updated.isoformat() if self.last_updated else None),
            "documentation": self.documentation,
            "setup_complexity": self.setup_complexity,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPServer":
        """Create MCPServer from dictionary."""
        maturity = MCPServerMaturity.UNKNOWN
        if "maturity" in data:
            try:
                maturity = MCPServerMaturity(data["maturity"])
            except ValueError:
                pass

        maintainer = MCPServerMaintainer.UNKNOWN
        if "maintainer" in data:
            try:
                maintainer = MCPServerMaintainer(data["maintainer"])
            except ValueError:
                pass

        last_updated = None
        if data.get("last_updated"):
            try:
                last_updated = datetime.fromisoformat(data["last_updated"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            url=data.get("url", ""),
            repository=data.get("repository", ""),
            npm_package=data.get("npm_package", ""),
            capabilities=data.get("capabilities", []),
            maturity=maturity,
            maintainer=maintainer,
            stars=data.get("stars", 0),
            last_updated=last_updated,
            documentation=data.get("documentation", ""),
            setup_complexity=data.get("setup_complexity", "medium"),
        )


@dataclass
class ScanResult:
    """Result of an MCP registry scan."""

    servers: List[MCPServer] = field(default_factory=list)
    total_found: int = 0
    query: str = ""
    scan_timestamp: datetime = field(default_factory=datetime.now)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "servers": [s.to_dict() for s in self.servers],
            "total_found": self.total_found,
            "query": self.query,
            "scan_timestamp": self.scan_timestamp.isoformat(),
            "errors": self.errors,
        }


class MCPRegistryScanner:
    """Scans MCP registry for available servers and tools.

    Searches multiple sources including:
    - Anthropic MCP Registry
    - GitHub MCP repositories
    - NPM packages with @modelcontextprotocol
    """

    # Known MCP registry endpoints and search patterns
    GITHUB_API_BASE = "https://api.github.com"
    NPM_REGISTRY_BASE = "https://registry.npmjs.org"

    # Default search queries for MCP servers
    DEFAULT_SEARCH_QUERIES = [
        "mcp-server",
        "@modelcontextprotocol",
        "model context protocol server",
    ]

    def __init__(
        self,
        github_token: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the MCP registry scanner.

        Args:
            github_token: Optional GitHub token for API authentication.
            timeout: Request timeout in seconds.
        """
        self._github_token = github_token
        self._timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def scan_registry(
        self,
        query: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        include_experimental: bool = True,
    ) -> ScanResult:
        """Scan MCP registry for available servers.

        Args:
            query: Optional search query to filter servers.
            capabilities: Optional list of required capabilities to filter by.
            include_experimental: Whether to include experimental servers.

        Returns:
            ScanResult containing found MCP servers.
        """
        result = ScanResult(query=query or "")
        servers: List[MCPServer] = []
        errors: List[str] = []

        # Search GitHub for MCP repositories
        try:
            github_servers = await self._search_github(query)
            servers.extend(github_servers)
        except Exception as e:
            logger.warning(f"GitHub search failed: {e}")
            errors.append(f"GitHub search error: {str(e)}")

        # Search NPM for MCP packages
        try:
            npm_servers = await self._search_npm(query)
            servers.extend(npm_servers)
        except Exception as e:
            logger.warning(f"NPM search failed: {e}")
            errors.append(f"NPM search error: {str(e)}")

        # Deduplicate servers by name
        seen_names: set[str] = set()
        unique_servers: List[MCPServer] = []
        for server in servers:
            if server.name not in seen_names:
                seen_names.add(server.name)
                unique_servers.append(server)

        # Filter by capabilities if specified
        if capabilities:
            unique_servers = [
                s for s in unique_servers if any(cap in s.capabilities for cap in capabilities)
            ]

        # Filter experimental if not included
        if not include_experimental:
            unique_servers = [
                s for s in unique_servers if s.maturity != MCPServerMaturity.EXPERIMENTAL
            ]

        result.servers = unique_servers
        result.total_found = len(unique_servers)
        result.errors = errors
        result.scan_timestamp = datetime.now()

        return result

    async def _search_github(self, query: Optional[str] = None) -> List[MCPServer]:
        """Search GitHub for MCP repositories.

        Args:
            query: Optional search query.

        Returns:
            List of MCPServer objects found on GitHub.
        """
        servers: List[MCPServer] = []
        session = await self._get_session()

        search_query = query if query else "mcp-server"
        search_url = (
            f"{self.GITHUB_API_BASE}/search/repositories"
            f"?q={search_query}+topic:mcp+topic:model-context-protocol"
            f"&sort=stars&order=desc&per_page=50"
        )

        headers = {"Accept": "application/vnd.github.v3+json"}
        if self._github_token:
            headers["Authorization"] = f"token {self._github_token}"

        try:
            async with session.get(search_url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    items = data.get("items", [])

                    for item in items:
                        server = self._parse_github_repo(item)
                        if server:
                            servers.append(server)
                elif response.status == 403:
                    logger.warning("GitHub API rate limit exceeded")
                else:
                    logger.warning(f"GitHub API returned status {response.status}")
        except aiohttp.ClientError as e:
            logger.error(f"GitHub API request failed: {e}")
            raise

        return servers

    def _parse_github_repo(self, repo_data: Dict[str, Any]) -> Optional[MCPServer]:
        """Parse GitHub repository data into MCPServer.

        Args:
            repo_data: Repository data from GitHub API.

        Returns:
            MCPServer if valid, None otherwise.
        """
        name = repo_data.get("name", "")
        if not name:
            return None

        # Determine maturity from topics or description
        topics = repo_data.get("topics", [])
        maturity = MCPServerMaturity.UNKNOWN
        if "stable" in topics:
            maturity = MCPServerMaturity.STABLE
        elif "beta" in topics:
            maturity = MCPServerMaturity.BETA
        elif "experimental" in topics or "alpha" in topics:
            maturity = MCPServerMaturity.EXPERIMENTAL

        # Determine maintainer type
        owner = repo_data.get("owner", {}).get("login", "")
        maintainer = MCPServerMaintainer.COMMUNITY
        if owner.lower() in ["anthropics", "modelcontextprotocol"]:
            maintainer = MCPServerMaintainer.OFFICIAL

        # Parse last updated
        last_updated = None
        if repo_data.get("updated_at"):
            try:
                last_updated = datetime.fromisoformat(
                    repo_data["updated_at"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # Extract capabilities from topics
        capabilities = [
            topic
            for topic in topics
            if topic not in ["mcp", "model-context-protocol", "stable", "beta"]
        ]

        return MCPServer(
            name=name,
            description=repo_data.get("description", "") or "",
            url=repo_data.get("html_url", ""),
            repository=repo_data.get("html_url", ""),
            capabilities=capabilities,
            maturity=maturity,
            maintainer=maintainer,
            stars=repo_data.get("stargazers_count", 0),
            last_updated=last_updated,
            documentation=repo_data.get("homepage", "") or "",
        )

    async def _search_npm(self, query: Optional[str] = None) -> List[MCPServer]:
        """Search NPM for MCP packages.

        Args:
            query: Optional search query.

        Returns:
            List of MCPServer objects found on NPM.
        """
        servers: List[MCPServer] = []
        session = await self._get_session()

        search_query = query if query else "@modelcontextprotocol"
        search_url = f"{self.NPM_REGISTRY_BASE}/-/v1/search?text={search_query}&size=50"

        try:
            async with session.get(search_url) as response:
                if response.status == 200:
                    data = await response.json()
                    objects = data.get("objects", [])

                    for obj in objects:
                        package = obj.get("package", {})
                        server = self._parse_npm_package(package)
                        if server:
                            servers.append(server)
        except aiohttp.ClientError as e:
            logger.error(f"NPM registry request failed: {e}")
            raise

        return servers

    def _parse_npm_package(self, package_data: Dict[str, Any]) -> Optional[MCPServer]:
        """Parse NPM package data into MCPServer.

        Args:
            package_data: Package data from NPM registry.

        Returns:
            MCPServer if valid, None otherwise.
        """
        name = package_data.get("name", "")
        name_lower = name.lower()
        if not name or ("mcp" not in name_lower and "modelcontextprotocol" not in name_lower):
            return None

        # Determine maintainer type
        scope = package_data.get("scope", "")
        maintainer = MCPServerMaintainer.COMMUNITY
        if scope == "modelcontextprotocol":
            maintainer = MCPServerMaintainer.OFFICIAL

        # Extract repository URL
        links = package_data.get("links", {})
        repository = links.get("repository", "")

        # Parse date
        last_updated = None
        if package_data.get("date"):
            try:
                last_updated = datetime.fromisoformat(package_data["date"].replace("Z", "+00:00"))
            except ValueError:
                pass

        # Extract keywords as capabilities
        keywords = package_data.get("keywords", [])
        capabilities = [kw for kw in keywords if kw not in ["mcp", "model-context"]]

        return MCPServer(
            name=name,
            description=package_data.get("description", "") or "",
            url=links.get("npm", ""),
            repository=repository,
            npm_package=name,
            capabilities=capabilities,
            maintainer=maintainer,
            last_updated=last_updated,
            documentation=links.get("homepage", "") or "",
        )

    async def find_servers_for_capability(
        self,
        capability: str,
    ) -> List[MCPServer]:
        """Find MCP servers that provide a specific capability.

        Args:
            capability: The capability to search for (e.g., "database", "filesystem").

        Returns:
            List of MCPServer objects that provide the capability.
        """
        result = await self.scan_registry(query=capability)
        return [
            server
            for server in result.servers
            if capability.lower() in server.description.lower()
            or capability.lower() in [c.lower() for c in server.capabilities]
        ]

    async def get_recommended_stack(
        self,
        requirements: List[str],
    ) -> Dict[str, List[MCPServer]]:
        """Get recommended MCP servers for a set of requirements.

        Args:
            requirements: List of required capabilities.

        Returns:
            Dictionary mapping requirements to recommended servers.
        """
        recommendations: Dict[str, List[MCPServer]] = {}

        for req in requirements:
            servers = await self.find_servers_for_capability(req)
            # Sort by stars and maturity
            servers.sort(
                key=lambda s: (
                    s.maturity == MCPServerMaturity.STABLE,
                    s.maintainer == MCPServerMaintainer.OFFICIAL,
                    s.stars,
                ),
                reverse=True,
            )
            recommendations[req] = servers[:3]  # Top 3 recommendations

        return recommendations
