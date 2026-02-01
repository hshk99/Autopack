"""
MCP Registry Integration - Discover and integrate MCP servers.

Provides integration support for Model Context Protocol (MCP) server discovery,
validation, and integration into Autopack's tool ecosystem.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..research.external.mcp_scanner import \
    MCPRegistryScanner as BaseMCPScanner
from ..research.external.mcp_scanner import (MCPServer, MCPServerMaturity,
                                             ScanResult)

logger = logging.getLogger(__name__)


class MCPIntegrationStatus(Enum):
    """Status of MCP server integration."""

    UNDISCOVERED = "undiscovered"
    DISCOVERED = "discovered"
    VALIDATED = "validated"
    INTEGRATED = "integrated"
    FAILED = "failed"


@dataclass
class MCPIntegrationResult:
    """Result of MCP server integration."""

    server: MCPServer
    status: MCPIntegrationStatus
    integrated_at: Optional[datetime] = None
    error_message: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "server": self.server.to_dict(),
            "status": self.status.value,
            "integrated_at": self.integrated_at.isoformat() if self.integrated_at else None,
            "error_message": self.error_message,
            "validation_errors": self.validation_errors,
            "metadata": self.metadata,
        }


@dataclass
class MCPIntegrationConfig:
    """Configuration for MCP integration."""

    auto_validate: bool = True
    auto_integrate: bool = False
    timeout_seconds: float = 30.0
    include_experimental: bool = False
    verify_ssl: bool = True
    max_concurrent_validations: int = 3


class MCPRegistryIntegration:
    """
    MCP Registry Integration for discovering and managing MCP servers.

    Features:
    - Scan public MCP registry (GitHub, NPM)
    - Validate MCP server availability and compatibility
    - Integrate discovered servers into Autopack
    - Track integration history and status
    """

    def __init__(
        self,
        github_token: Optional[str] = None,
        config: Optional[MCPIntegrationConfig] = None,
    ) -> None:
        """Initialize MCP Registry Integration.

        Args:
            github_token: Optional GitHub token for API authentication.
            config: Integration configuration.
        """
        self._scanner = BaseMCPScanner(github_token=github_token)
        self._config = config or MCPIntegrationConfig()
        self._integrations: Dict[str, MCPIntegrationResult] = {}
        self._discovery_cache: Optional[ScanResult] = None
        self._last_scan_time: Optional[datetime] = None

    async def discover_servers(
        self,
        query: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        force_refresh: bool = False,
    ) -> ScanResult:
        """Discover available MCP servers.

        Args:
            query: Optional search query to filter servers.
            capabilities: Optional list of required capabilities.
            force_refresh: Force fresh scan, bypass cache.

        Returns:
            ScanResult containing discovered servers.
        """
        # Use cache if available and not forcing refresh
        if self._discovery_cache and not force_refresh:
            logger.debug("Using cached discovery results")
            return self._discovery_cache

        logger.info(f"Discovering MCP servers (query={query}, capabilities={capabilities})")

        try:
            result = await self._scanner.scan_registry(
                query=query,
                capabilities=capabilities,
                include_experimental=self._config.include_experimental,
            )

            # Cache the result
            self._discovery_cache = result
            self._last_scan_time = datetime.now()

            logger.info(f"Discovered {result.total_found} MCP servers")
            return result

        except Exception as e:
            logger.error(f"MCP discovery failed: {e}")
            raise

    async def validate_server(
        self,
        server: MCPServer,
    ) -> MCPIntegrationResult:
        """Validate MCP server availability and compatibility.

        Args:
            server: MCPServer to validate.

        Returns:
            MCPIntegrationResult with validation status.
        """
        logger.info(f"Validating MCP server: {server.name}")

        result = MCPIntegrationResult(
            server=server,
            status=MCPIntegrationStatus.DISCOVERED,
        )

        validation_errors: List[str] = []

        # Validate server has required metadata
        if not server.name:
            validation_errors.append("Server name is required")

        if not server.url and not server.npm_package:
            validation_errors.append("Server must have URL or NPM package")

        if not server.capabilities:
            validation_errors.append("Server must declare at least one capability")

        if server.maturity == MCPServerMaturity.UNKNOWN:
            validation_errors.append("Server maturity level unknown - may be unstable")

        # Try to connect to server (if URL is available)
        if server.url and not validation_errors:
            try:
                is_healthy = await self._validate_server_connection(server)
                if is_healthy:
                    result.status = MCPIntegrationStatus.VALIDATED
                else:
                    validation_errors.append(f"Failed to connect to server at {server.url}")
            except Exception as e:
                validation_errors.append(f"Connection validation error: {str(e)}")

        if validation_errors:
            result.status = MCPIntegrationStatus.FAILED
            result.validation_errors = validation_errors
            result.error_message = "; ".join(validation_errors)
            logger.warning(f"Server {server.name} validation failed: {result.error_message}")
        else:
            result.status = MCPIntegrationStatus.VALIDATED
            logger.info(f"Server {server.name} validation passed")

        return result

    async def _validate_server_connection(self, server: MCPServer) -> bool:
        """Validate MCP server connection.

        Args:
            server: MCPServer to validate.

        Returns:
            True if server is reachable and healthy, False otherwise.
        """
        if not server.url:
            return True  # Can't validate without URL

        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=self._config.timeout_seconds,
                verify=self._config.verify_ssl,
            ) as client:
                # Try to reach the server's health endpoint
                health_urls = [
                    f"{server.url}/health",
                    f"{server.url}/ping",
                    server.url,
                ]

                for url in health_urls:
                    try:
                        response = await client.get(url, timeout=5.0)
                        if response.status_code < 500:
                            return True
                    except Exception:
                        continue

                return False
        except Exception as e:
            logger.warning(f"Connection validation error for {server.name}: {e}")
            return False

    async def integrate_server(
        self,
        server: MCPServer,
        skip_validation: bool = False,
    ) -> MCPIntegrationResult:
        """Integrate an MCP server into Autopack.

        Args:
            server: MCPServer to integrate.
            skip_validation: Skip validation if True.

        Returns:
            MCPIntegrationResult with integration status.
        """
        logger.info(f"Integrating MCP server: {server.name}")

        # Validate first if configured
        if self._config.auto_validate and not skip_validation:
            validation_result = await self.validate_server(server)
            if validation_result.status == MCPIntegrationStatus.FAILED:
                logger.error(f"Cannot integrate {server.name}: validation failed")
                return validation_result

        result = MCPIntegrationResult(
            server=server,
            status=MCPIntegrationStatus.VALIDATED,
        )

        try:
            # Register server in integrations registry
            await self._register_server(server)

            result.status = MCPIntegrationStatus.INTEGRATED
            result.integrated_at = datetime.now()
            result.metadata = {
                "integration_type": "mcp_server",
                "capabilities": server.capabilities,
                "maturity": server.maturity.value,
                "maintainer": server.maintainer.value,
            }

            # Store integration result
            self._integrations[server.name] = result

            logger.info(f"Successfully integrated MCP server: {server.name}")
            return result

        except Exception as e:
            result.status = MCPIntegrationStatus.FAILED
            result.error_message = str(e)
            logger.error(f"Failed to integrate {server.name}: {e}")
            return result

    async def _register_server(self, server: MCPServer) -> None:
        """Register MCP server in the system.

        Args:
            server: MCPServer to register.
        """
        # TODO: Implement server registration
        # This would integrate with the tool loading system
        # to register the MCP server as an available tool source
        logger.debug(f"Registering MCP server: {server.name}")

    async def get_integrated_servers(self) -> List[MCPServer]:
        """Get list of integrated MCP servers.

        Returns:
            List of successfully integrated MCPServer objects.
        """
        integrated = [
            result.server
            for result in self._integrations.values()
            if result.status == MCPIntegrationStatus.INTEGRATED
        ]
        return integrated

    async def get_server_by_name(self, name: str) -> Optional[MCPServer]:
        """Get integrated server by name.

        Args:
            name: Server name to look up.

        Returns:
            MCPServer if found, None otherwise.
        """
        if name in self._integrations:
            return self._integrations[name].server
        return None

    async def get_servers_by_capability(self, capability: str) -> List[MCPServer]:
        """Get integrated servers that provide a specific capability.

        Args:
            capability: Capability to search for.

        Returns:
            List of MCPServer objects providing the capability.
        """
        return [
            result.server
            for result in self._integrations.values()
            if result.status == MCPIntegrationStatus.INTEGRATED
            and capability in [c.lower() for c in result.server.capabilities]
        ]

    async def find_servers_for_requirement(
        self,
        requirement: str,
    ) -> List[MCPServer]:
        """Find MCP servers that satisfy a requirement.

        Args:
            requirement: Required capability or feature.

        Returns:
            List of recommended MCPServer objects.
        """
        logger.info(f"Finding servers for requirement: {requirement}")
        return await self._scanner.find_servers_for_capability(requirement)

    async def get_recommendation_stack(
        self,
        requirements: List[str],
    ) -> Dict[str, List[MCPServer]]:
        """Get recommended MCP servers for a set of requirements.

        Args:
            requirements: List of required capabilities.

        Returns:
            Dictionary mapping requirements to recommended servers.
        """
        logger.info(f"Getting recommendations for {len(requirements)} requirements")
        recommendations = await self._scanner.get_recommended_stack(requirements)
        return recommendations

    def get_integration_history(self) -> Dict[str, MCPIntegrationResult]:
        """Get history of all integration attempts.

        Returns:
            Dictionary mapping server names to integration results.
        """
        return dict(self._integrations)

    def clear_cache(self) -> None:
        """Clear discovery cache."""
        self._discovery_cache = None
        self._last_scan_time = None
        logger.debug("MCP discovery cache cleared")

    async def close(self) -> None:
        """Close scanner and clean up resources."""
        await self._scanner.close()
        logger.info("MCP Registry Integration closed")
