"""Hetzner Cloud API client for provisioning CPU servers.

Provides interfaces for creating, managing, and deleting Hetzner Cloud servers
suitable for batch processing and non-GPU compute workloads.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class ServerStatus(Enum):
    """Status of a Hetzner server."""

    INITIALIZING = "initializing"
    RUNNING = "running"
    STOPPED = "stopped"
    DELETING = "deleting"
    MIGRATING = "migrating"
    UNKNOWN = "unknown"


class ServerType(Enum):
    """Hetzner server type categories."""

    SHARED = "shared"  # Shared CPU
    DEDICATED = "dedicated"  # Dedicated CPU
    OPTIMIZED = "optimized"  # Memory optimized
    STORAGE = "storage"  # Storage optimized


@dataclass
class Server:
    """Represents a Hetzner Cloud server."""

    id: str
    name: str
    status: ServerStatus = ServerStatus.UNKNOWN
    public_ip: Optional[str] = None
    private_ip: Optional[str] = None
    server_type: str = ""
    created: Optional[datetime] = None
    image: str = ""
    location: str = ""
    datacenter: str = ""
    labels: Dict[str, str] = field(default_factory=dict)
    protection: Dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "public_ip": self.public_ip,
            "private_ip": self.private_ip,
            "server_type": self.server_type,
            "created": self.created.isoformat() if self.created else None,
            "image": self.image,
            "location": self.location,
            "datacenter": self.datacenter,
            "labels": self.labels,
            "protection": self.protection,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Server:
        """Create Server from dictionary."""
        status = ServerStatus.UNKNOWN
        if "status" in data:
            try:
                status = ServerStatus(data["status"])
            except ValueError:
                pass

        created = None
        if data.get("created"):
            try:
                created = datetime.fromisoformat(data["created"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            status=status,
            public_ip=data.get("public_ip"),
            private_ip=data.get("private_ip"),
            server_type=data.get("server_type", ""),
            created=created,
            image=data.get("image", ""),
            location=data.get("location", ""),
            datacenter=data.get("datacenter", ""),
            labels=data.get("labels", {}),
            protection=data.get("protection", {}),
        )


@dataclass
class ServerConfig:
    """Configuration for creating a new Hetzner server."""

    name: str
    server_type: str = "cx22"  # 2vCPU, 4GB RAM (affordable CPU-optimized)
    image: str = "ubuntu-24.04"
    ssh_keys: List[str] = field(default_factory=list)
    location: str = "fsn1"  # Falkenstein, Germany
    labels: Dict[str, str] = field(default_factory=dict)
    automount: bool = True
    public_net: Optional[Dict[str, Any]] = None
    volumes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API request."""
        return {
            "name": self.name,
            "server_type": self.server_type,
            "image": self.image,
            "ssh_keys": self.ssh_keys,
            "location": self.location,
            "labels": self.labels,
            "automount": self.automount,
            "public_net": self.public_net,
            "volumes": self.volumes,
        }


@dataclass
class OperationResult:
    """Result of an operation on a Hetzner server."""

    success: bool
    message: str = ""
    server_id: Optional[str] = None
    action_id: Optional[str] = None
    errors: List[str] = field(default_factory=list)


class HetznerClient:
    """Client for Hetzner Cloud API.

    Manages CPU-based servers suitable for batch processing, data preparation,
    and non-GPU compute workloads. Provides cost-effective compute for Autopack
    generative AI pipeline preprocessing.

    API Pricing (approximate):
    - cx22 (2vCPU, 4GB): €0.005/hour
    - cx32 (4vCPU, 8GB): €0.010/hour
    - cx42 (8vCPU, 16GB): €0.015/hour
    """

    API_BASE = "https://api.hetzner.cloud/v1"

    def __init__(
        self,
        api_token: str,
        timeout: float = 30.0,
    ) -> None:
        """Initialize Hetzner client.

        Args:
            api_token: Hetzner Cloud API token.
            timeout: Request timeout in seconds.
        """
        if not api_token:
            raise ValueError("API token is required")

        self._api_token = api_token
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx async client."""
        if self._client is None or self._client.is_closed:
            headers = {
                "Authorization": f"Bearer {self._api_token}",
                "Content-Type": "application/json",
            }
            self._client = httpx.AsyncClient(headers=headers, timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> HetznerClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def create_server(self, config: ServerConfig) -> OperationResult:
        """Create a new Hetzner server.

        Args:
            config: Server configuration.

        Returns:
            OperationResult with server creation status.
        """
        try:
            client = await self._get_client()
            url = f"{self.API_BASE}/servers"
            payload = config.to_dict()

            response = await client.post(url, json=payload)

            if response.status_code in (200, 201):
                data = response.json()
                server_data = data.get("server", {})
                server = Server.from_dict(server_data)
                action_id = data.get("action", {}).get("id")

                logger.info(f"Server created: {config.name} (ID: {server.id})")
                return OperationResult(
                    success=True,
                    message=f"Server {config.name} created successfully",
                    server_id=server.id,
                    action_id=action_id,
                )
            else:
                error_data = response.json()
                error_msg = error_data.get("message", "Unknown error")
                logger.error(f"Failed to create server: {error_msg}")
                return OperationResult(
                    success=False,
                    message=f"Failed to create server: {error_msg}",
                    errors=[error_msg],
                )
        except httpx.HTTPError as e:
            logger.error(f"HTTP error creating server: {e}")
            return OperationResult(
                success=False,
                message=f"HTTP error: {str(e)}",
                errors=[str(e)],
            )
        except Exception as e:
            logger.error(f"Unexpected error creating server: {e}")
            return OperationResult(
                success=False,
                message=f"Unexpected error: {str(e)}",
                errors=[str(e)],
            )

    async def list_servers(self) -> tuple[List[Server], List[str]]:
        """List all Hetzner servers.

        Returns:
            Tuple of (servers list, errors list).
        """
        servers: List[Server] = []
        errors: List[str] = []

        try:
            client = await self._get_client()
            url = f"{self.API_BASE}/servers"

            response = await client.get(url)

            if response.status_code == 200:
                data = response.json()
                for server_data in data.get("servers", []):
                    server = Server.from_dict(server_data)
                    servers.append(server)
                logger.info(f"Retrieved {len(servers)} servers")
            else:
                error_msg = response.json().get("message", "Unknown error")
                logger.error(f"Failed to list servers: {error_msg}")
                errors.append(error_msg)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error listing servers: {e}")
            errors.append(str(e))
        except Exception as e:
            logger.error(f"Unexpected error listing servers: {e}")
            errors.append(str(e))

        return servers, errors

    async def get_server(self, server_id: str) -> tuple[Optional[Server], Optional[str]]:
        """Get a specific server by ID.

        Args:
            server_id: Server ID.

        Returns:
            Tuple of (Server or None, error message or None).
        """
        try:
            client = await self._get_client()
            url = f"{self.API_BASE}/servers/{server_id}"

            response = await client.get(url)

            if response.status_code == 200:
                server_data = response.json().get("server", {})
                server = Server.from_dict(server_data)
                logger.info(f"Retrieved server: {server.name}")
                return server, None
            else:
                error_msg = response.json().get("message", "Server not found")
                logger.warning(f"Failed to get server {server_id}: {error_msg}")
                return None, error_msg

        except httpx.HTTPError as e:
            logger.error(f"HTTP error getting server: {e}")
            return None, str(e)
        except Exception as e:
            logger.error(f"Unexpected error getting server: {e}")
            return None, str(e)

    async def delete_server(self, server_id: str) -> OperationResult:
        """Delete a Hetzner server.

        Args:
            server_id: Server ID to delete.

        Returns:
            OperationResult with deletion status.
        """
        try:
            client = await self._get_client()
            url = f"{self.API_BASE}/servers/{server_id}"

            response = await client.delete(url)

            if response.status_code in (200, 204):
                logger.info(f"Server deleted: {server_id}")
                return OperationResult(
                    success=True,
                    message=f"Server {server_id} deleted successfully",
                    server_id=server_id,
                )
            else:
                error_data = response.json()
                error_msg = error_data.get("message", "Unknown error")
                logger.error(f"Failed to delete server: {error_msg}")
                return OperationResult(
                    success=False,
                    message=f"Failed to delete server: {error_msg}",
                    errors=[error_msg],
                )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error deleting server: {e}")
            return OperationResult(
                success=False,
                message=f"HTTP error: {str(e)}",
                errors=[str(e)],
            )
        except Exception as e:
            logger.error(f"Unexpected error deleting server: {e}")
            return OperationResult(
                success=False,
                message=f"Unexpected error: {str(e)}",
                errors=[str(e)],
            )

    async def reboot_server(self, server_id: str) -> OperationResult:
        """Reboot a Hetzner server.

        Args:
            server_id: Server ID to reboot.

        Returns:
            OperationResult with reboot status.
        """
        try:
            client = await self._get_client()
            url = f"{self.API_BASE}/servers/{server_id}/actions/reboot"

            response = await client.post(url, json={})

            if response.status_code in (200, 201):
                action_id = response.json().get("action", {}).get("id")
                logger.info(f"Server reboot initiated: {server_id}")
                return OperationResult(
                    success=True,
                    message=f"Server {server_id} reboot initiated",
                    server_id=server_id,
                    action_id=action_id,
                )
            else:
                error_msg = response.json().get("message", "Unknown error")
                logger.error(f"Failed to reboot server: {error_msg}")
                return OperationResult(
                    success=False,
                    message=f"Failed to reboot server: {error_msg}",
                    errors=[error_msg],
                )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error rebooting server: {e}")
            return OperationResult(
                success=False,
                message=f"HTTP error: {str(e)}",
                errors=[str(e)],
            )
        except Exception as e:
            logger.error(f"Unexpected error rebooting server: {e}")
            return OperationResult(
                success=False,
                message=f"Unexpected error: {str(e)}",
                errors=[str(e)],
            )
