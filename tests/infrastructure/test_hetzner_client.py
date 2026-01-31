"""Tests for Hetzner Cloud API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autopack.infrastructure.hetzner_client import HetznerClient, Server, ServerConfig, ServerStatus


class TestHetznerClientInitialization:
    """Test HetznerClient initialization."""

    def test_client_initialization_with_token(self):
        """Test client initialization with valid API token."""
        client = HetznerClient(api_token="test-token-123")
        assert client._api_token == "test-token-123"
        assert client._timeout == 30.0

    def test_client_initialization_without_token_raises_error(self):
        """Test client initialization without token raises ValueError."""
        with pytest.raises(ValueError, match="API token is required"):
            HetznerClient(api_token="")

    def test_client_custom_timeout(self):
        """Test client initialization with custom timeout."""
        client = HetznerClient(api_token="test-token", timeout=60.0)
        assert client._timeout == 60.0


class TestServerDataStructures:
    """Test Server and ServerConfig data structures."""

    def test_server_from_dict(self):
        """Test Server creation from dictionary."""
        server_data = {
            "id": "123456",
            "name": "test-server",
            "status": "running",
            "public_ip": "192.0.2.1",
            "server_type": "cx22",
            "image": "ubuntu-24.04",
            "location": "fsn1",
        }

        server = Server.from_dict(server_data)

        assert server.id == "123456"
        assert server.name == "test-server"
        assert server.status == ServerStatus.RUNNING
        assert server.public_ip == "192.0.2.1"

    def test_server_to_dict(self):
        """Test Server conversion to dictionary."""
        server = Server(
            id="123456",
            name="test-server",
            status=ServerStatus.RUNNING,
            public_ip="192.0.2.1",
            server_type="cx22",
        )

        server_dict = server.to_dict()

        assert server_dict["id"] == "123456"
        assert server_dict["name"] == "test-server"
        assert server_dict["status"] == "running"
        assert server_dict["public_ip"] == "192.0.2.1"

    def test_server_config_to_dict(self):
        """Test ServerConfig conversion to dictionary."""
        config = ServerConfig(
            name="test-server",
            server_type="cx32",
            location="nbg1",
        )

        config_dict = config.to_dict()

        assert config_dict["name"] == "test-server"
        assert config_dict["server_type"] == "cx32"
        assert config_dict["location"] == "nbg1"
        assert config_dict["image"] == "ubuntu-24.04"


class TestHetznerClientAsyncOperations:
    """Test async operations of HetznerClient."""

    @pytest.mark.asyncio
    async def test_create_server_success(self):
        """Test successful server creation."""
        client = HetznerClient(api_token="test-token")

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "server": {
                "id": "123456",
                "name": "test-server",
                "status": "initializing",
            },
            "action": {"id": "action-123"},
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            config = ServerConfig(name="test-server")
            result = await client.create_server(config)

            assert result.success is True
            assert result.server_id == "123456"
            assert "created successfully" in result.message

        await client.close()

    @pytest.mark.asyncio
    async def test_create_server_failure(self):
        """Test failed server creation."""
        client = HetznerClient(api_token="test-token")

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"message": "Invalid request"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            config = ServerConfig(name="test-server")
            result = await client.create_server(config)

            assert result.success is False
            assert "Failed to create server" in result.message

        await client.close()

    @pytest.mark.asyncio
    async def test_list_servers_success(self):
        """Test successful server listing."""
        client = HetznerClient(api_token="test-token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "servers": [
                {
                    "id": "123456",
                    "name": "test-server-1",
                    "status": "running",
                },
                {
                    "id": "123457",
                    "name": "test-server-2",
                    "status": "stopped",
                },
            ]
        }

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            servers, errors = await client.list_servers()

            assert len(servers) == 2
            assert servers[0].name == "test-server-1"
            assert servers[1].name == "test-server-2"
            assert len(errors) == 0

        await client.close()

    @pytest.mark.asyncio
    async def test_delete_server_success(self):
        """Test successful server deletion."""
        client = HetznerClient(api_token="test-token")

        mock_response = MagicMock()
        mock_response.status_code = 204

        with patch("httpx.AsyncClient.delete", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = mock_response

            result = await client.delete_server("123456")

            assert result.success is True
            assert "deleted successfully" in result.message

        await client.close()

    @pytest.mark.asyncio
    async def test_delete_server_failure(self):
        """Test failed server deletion."""
        client = HetznerClient(api_token="test-token")

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Server not found"}

        with patch("httpx.AsyncClient.delete", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = mock_response

            result = await client.delete_server("999999")

            assert result.success is False
            assert "Failed to delete server" in result.message

        await client.close()


class TestHetznerClientContextManager:
    """Test async context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test using HetznerClient as async context manager."""
        async with HetznerClient(api_token="test-token") as client:
            assert client._api_token == "test-token"
