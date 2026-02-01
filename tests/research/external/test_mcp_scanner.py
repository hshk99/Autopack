"""Tests for MCP Registry Scanner."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autopack.research.external.mcp_scanner import (MCPRegistryScanner,
                                                    MCPServer,
                                                    MCPServerMaintainer,
                                                    MCPServerMaturity,
                                                    ScanResult)


class TestMCPServer:
    """Test cases for MCPServer dataclass."""

    def test_create_server(self):
        """Test creating an MCP server."""
        server = MCPServer(
            name="mcp-server-postgres",
            description="PostgreSQL database access",
            url="https://github.com/example/mcp-server-postgres",
            capabilities=["query", "insert", "update"],
        )

        assert server.name == "mcp-server-postgres"
        assert server.description == "PostgreSQL database access"
        assert "query" in server.capabilities

    def test_server_defaults(self):
        """Test default values for MCPServer."""
        server = MCPServer(name="test-server")

        assert server.description == ""
        assert server.url == ""
        assert server.capabilities == []
        assert server.maturity == MCPServerMaturity.UNKNOWN
        assert server.maintainer == MCPServerMaintainer.UNKNOWN
        assert server.stars == 0

    def test_to_dict(self):
        """Test server conversion to dictionary."""
        server = MCPServer(
            name="test",
            description="Test server",
            capabilities=["read", "write"],
            maturity=MCPServerMaturity.STABLE,
            maintainer=MCPServerMaintainer.OFFICIAL,
            stars=100,
        )

        result = server.to_dict()

        assert isinstance(result, dict)
        assert result["name"] == "test"
        assert result["maturity"] == "stable"
        assert result["maintainer"] == "official"
        assert result["stars"] == 100

    def test_from_dict(self):
        """Test creating server from dictionary."""
        data = {
            "name": "mcp-server-test",
            "description": "Test MCP server",
            "capabilities": ["read"],
            "maturity": "stable",
            "maintainer": "official",
            "stars": 50,
            "last_updated": "2024-01-15T10:00:00Z",
        }

        server = MCPServer.from_dict(data)

        assert server.name == "mcp-server-test"
        assert server.maturity == MCPServerMaturity.STABLE
        assert server.maintainer == MCPServerMaintainer.OFFICIAL
        assert server.last_updated is not None

    def test_from_dict_with_invalid_enums(self):
        """Test creating server from dict with invalid enum values."""
        data = {
            "name": "test",
            "maturity": "invalid_value",
            "maintainer": "unknown_type",
        }

        server = MCPServer.from_dict(data)

        assert server.maturity == MCPServerMaturity.UNKNOWN
        assert server.maintainer == MCPServerMaintainer.UNKNOWN


class TestScanResult:
    """Test cases for ScanResult dataclass."""

    def test_create_result(self):
        """Test creating a scan result."""
        servers = [
            MCPServer(name="server1"),
            MCPServer(name="server2"),
        ]
        result = ScanResult(servers=servers, total_found=2, query="test")

        assert len(result.servers) == 2
        assert result.total_found == 2
        assert result.query == "test"

    def test_to_dict(self):
        """Test scan result conversion to dictionary."""
        result = ScanResult(
            servers=[MCPServer(name="test")],
            total_found=1,
            query="mcp",
        )

        data = result.to_dict()

        assert isinstance(data, dict)
        assert data["total_found"] == 1
        assert data["query"] == "mcp"
        assert len(data["servers"]) == 1


class TestMCPRegistryScanner:
    """Test cases for MCPRegistryScanner."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scanner = MCPRegistryScanner()

    @pytest.mark.asyncio
    async def test_scan_registry_empty(self):
        """Test scanning with no results."""
        with patch.object(self.scanner, "_search_github", new_callable=AsyncMock) as mock_github:
            with patch.object(self.scanner, "_search_npm", new_callable=AsyncMock) as mock_npm:
                mock_github.return_value = []
                mock_npm.return_value = []

                result = await self.scanner.scan_registry()

                assert isinstance(result, ScanResult)
                assert result.total_found == 0
                assert result.servers == []

    @pytest.mark.asyncio
    async def test_scan_registry_with_results(self):
        """Test scanning with results from GitHub and NPM."""
        github_servers = [
            MCPServer(name="mcp-server-postgres", stars=100),
            MCPServer(name="mcp-server-sqlite", stars=50),
        ]
        npm_servers = [
            MCPServer(name="@modelcontextprotocol/server-fetch"),
        ]

        with patch.object(self.scanner, "_search_github", new_callable=AsyncMock) as mock_github:
            with patch.object(self.scanner, "_search_npm", new_callable=AsyncMock) as mock_npm:
                mock_github.return_value = github_servers
                mock_npm.return_value = npm_servers

                result = await self.scanner.scan_registry()

                assert result.total_found == 3
                assert len(result.servers) == 3

    @pytest.mark.asyncio
    async def test_scan_registry_deduplicates(self):
        """Test that duplicate servers are deduplicated."""
        servers = [
            MCPServer(name="duplicate-server"),
            MCPServer(name="duplicate-server"),
            MCPServer(name="unique-server"),
        ]

        with patch.object(self.scanner, "_search_github", new_callable=AsyncMock) as mock_github:
            with patch.object(self.scanner, "_search_npm", new_callable=AsyncMock) as mock_npm:
                mock_github.return_value = servers
                mock_npm.return_value = []

                result = await self.scanner.scan_registry()

                assert result.total_found == 2
                names = [s.name for s in result.servers]
                assert names.count("duplicate-server") == 1

    @pytest.mark.asyncio
    async def test_scan_registry_filter_by_capabilities(self):
        """Test filtering by capabilities."""
        servers = [
            MCPServer(name="db-server", capabilities=["database", "sql"]),
            MCPServer(name="file-server", capabilities=["filesystem"]),
        ]

        with patch.object(self.scanner, "_search_github", new_callable=AsyncMock) as mock_github:
            with patch.object(self.scanner, "_search_npm", new_callable=AsyncMock) as mock_npm:
                mock_github.return_value = servers
                mock_npm.return_value = []

                result = await self.scanner.scan_registry(capabilities=["database"])

                assert result.total_found == 1
                assert result.servers[0].name == "db-server"

    @pytest.mark.asyncio
    async def test_scan_registry_exclude_experimental(self):
        """Test excluding experimental servers."""
        servers = [
            MCPServer(name="stable", maturity=MCPServerMaturity.STABLE),
            MCPServer(name="experimental", maturity=MCPServerMaturity.EXPERIMENTAL),
        ]

        with patch.object(self.scanner, "_search_github", new_callable=AsyncMock) as mock_github:
            with patch.object(self.scanner, "_search_npm", new_callable=AsyncMock) as mock_npm:
                mock_github.return_value = servers
                mock_npm.return_value = []

                result = await self.scanner.scan_registry(include_experimental=False)

                assert result.total_found == 1
                assert result.servers[0].name == "stable"

    @pytest.mark.asyncio
    async def test_scan_registry_handles_github_error(self):
        """Test handling GitHub API errors gracefully."""
        with patch.object(self.scanner, "_search_github", new_callable=AsyncMock) as mock_github:
            with patch.object(self.scanner, "_search_npm", new_callable=AsyncMock) as mock_npm:
                mock_github.side_effect = Exception("GitHub API error")
                mock_npm.return_value = [MCPServer(name="npm-server")]

                result = await self.scanner.scan_registry()

                assert result.total_found == 1
                assert "GitHub search error" in result.errors[0]

    def test_parse_github_repo(self):
        """Test parsing GitHub repository data."""
        repo_data = {
            "name": "mcp-server-postgres",
            "description": "PostgreSQL MCP server",
            "html_url": "https://github.com/example/mcp-server-postgres",
            "stargazers_count": 150,
            "topics": ["mcp", "database", "stable"],
            "owner": {"login": "anthropics"},
            "updated_at": "2024-01-15T10:00:00Z",
            "homepage": "https://docs.example.com",
        }

        server = self.scanner._parse_github_repo(repo_data)

        assert server is not None
        assert server.name == "mcp-server-postgres"
        assert server.stars == 150
        assert server.maturity == MCPServerMaturity.STABLE
        assert server.maintainer == MCPServerMaintainer.OFFICIAL
        assert "database" in server.capabilities

    def test_parse_github_repo_empty_name(self):
        """Test parsing repo with empty name returns None."""
        repo_data = {"name": "", "description": "Test"}

        server = self.scanner._parse_github_repo(repo_data)

        assert server is None

    def test_parse_npm_package(self):
        """Test parsing NPM package data."""
        package_data = {
            "name": "@modelcontextprotocol/server-fetch",
            "description": "HTTP fetch MCP server",
            "scope": "modelcontextprotocol",
            "keywords": ["mcp", "http", "fetch"],
            "links": {
                "npm": "https://www.npmjs.com/package/@modelcontextprotocol/server-fetch",
                "repository": "https://github.com/example/server-fetch",
                "homepage": "https://docs.example.com",
            },
            "date": "2024-01-20T12:00:00Z",
        }

        server = self.scanner._parse_npm_package(package_data)

        assert server is not None
        assert server.name == "@modelcontextprotocol/server-fetch"
        assert server.maintainer == MCPServerMaintainer.OFFICIAL
        assert server.npm_package == "@modelcontextprotocol/server-fetch"
        assert "http" in server.capabilities

    def test_parse_npm_package_not_mcp(self):
        """Test parsing non-MCP package returns None."""
        package_data = {
            "name": "some-random-package",
            "description": "Not an MCP package",
        }

        server = self.scanner._parse_npm_package(package_data)

        assert server is None

    @pytest.mark.asyncio
    async def test_find_servers_for_capability(self):
        """Test finding servers for a specific capability."""
        servers = [
            MCPServer(
                name="db-server",
                description="Database server",
                capabilities=["database"],
            ),
            MCPServer(
                name="file-server",
                description="File operations",
                capabilities=["filesystem"],
            ),
        ]

        with patch.object(self.scanner, "scan_registry", new_callable=AsyncMock) as mock_scan:
            mock_scan.return_value = ScanResult(servers=servers, total_found=2)

            result = await self.scanner.find_servers_for_capability("database")

            assert len(result) == 1
            assert result[0].name == "db-server"

    @pytest.mark.asyncio
    async def test_get_recommended_stack(self):
        """Test getting recommended MCP stack for requirements."""
        db_server = MCPServer(
            name="mcp-server-postgres",
            capabilities=["database"],
            maturity=MCPServerMaturity.STABLE,
            maintainer=MCPServerMaintainer.OFFICIAL,
            stars=100,
        )

        with patch.object(
            self.scanner, "find_servers_for_capability", new_callable=AsyncMock
        ) as mock_find:
            mock_find.return_value = [db_server]

            result = await self.scanner.get_recommended_stack(["database"])

            assert "database" in result
            assert len(result["database"]) == 1
            assert result["database"][0].name == "mcp-server-postgres"

    @pytest.mark.asyncio
    async def test_close_client(self):
        """Test closing the HTTP client."""
        # Create a mock client
        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        self.scanner._client = mock_client

        await self.scanner.close()

        mock_client.aclose.assert_called_once()


class TestMCPServerMaturity:
    """Test cases for MCPServerMaturity enum."""

    def test_maturity_values(self):
        """Test maturity enum values."""
        assert MCPServerMaturity.STABLE.value == "stable"
        assert MCPServerMaturity.BETA.value == "beta"
        assert MCPServerMaturity.EXPERIMENTAL.value == "experimental"
        assert MCPServerMaturity.UNKNOWN.value == "unknown"


class TestMCPServerMaintainer:
    """Test cases for MCPServerMaintainer enum."""

    def test_maintainer_values(self):
        """Test maintainer enum values."""
        assert MCPServerMaintainer.OFFICIAL.value == "official"
        assert MCPServerMaintainer.COMMUNITY.value == "community"
        assert MCPServerMaintainer.UNKNOWN.value == "unknown"
