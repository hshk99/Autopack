"""Tests for MCP Registry Integration."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.autopack.integrations.mcp_registry import (MCPIntegrationConfig,
                                                    MCPIntegrationResult,
                                                    MCPIntegrationStatus,
                                                    MCPRegistryIntegration)
from src.autopack.research.external.mcp_scanner import (MCPServer,
                                                        MCPServerMaintainer,
                                                        MCPServerMaturity,
                                                        ScanResult)


@pytest.fixture
def sample_mcp_server() -> MCPServer:
    """Create a sample MCP server for testing."""
    return MCPServer(
        name="test-server",
        description="Test MCP server",
        url="http://localhost:8000",
        repository="https://github.com/test/test-server",
        npm_package="@test/test-server",
        capabilities=["filesystem", "database"],
        maturity=MCPServerMaturity.STABLE,
        maintainer=MCPServerMaintainer.OFFICIAL,
        stars=100,
        last_updated=datetime.now(),
        documentation="https://example.com/docs",
        setup_complexity="low",
    )


@pytest.fixture
def mcp_integration() -> MCPRegistryIntegration:
    """Create MCPRegistryIntegration instance for testing."""
    config = MCPIntegrationConfig(
        auto_validate=True,
        auto_integrate=False,
        timeout_seconds=10.0,
        include_experimental=False,
    )
    return MCPRegistryIntegration(config=config)


@pytest.mark.asyncio
async def test_discover_servers(mcp_integration, sample_mcp_server):
    """Test MCP server discovery."""
    mock_result = ScanResult(
        servers=[sample_mcp_server],
        total_found=1,
        query="filesystem",
        errors=[],
    )

    with patch.object(
        mcp_integration._scanner, "scan_registry", new_callable=AsyncMock
    ) as mock_scan:
        mock_scan.return_value = mock_result

        result = await mcp_integration.discover_servers(query="filesystem")

        assert result.total_found == 1
        assert len(result.servers) == 1
        assert result.servers[0].name == "test-server"
        mock_scan.assert_called_once()


@pytest.mark.asyncio
async def test_discover_servers_cache(mcp_integration, sample_mcp_server):
    """Test MCP server discovery caching."""
    mock_result = ScanResult(
        servers=[sample_mcp_server],
        total_found=1,
        query="filesystem",
        errors=[],
    )

    with patch.object(
        mcp_integration._scanner, "scan_registry", new_callable=AsyncMock
    ) as mock_scan:
        mock_scan.return_value = mock_result

        # First call should hit the scanner
        result1 = await mcp_integration.discover_servers(query="filesystem")
        assert result1.total_found == 1

        # Second call should use cache
        result2 = await mcp_integration.discover_servers(query="filesystem")
        assert result2.total_found == 1
        assert mock_scan.call_count == 1  # Only called once due to cache

        # Force refresh should call scanner again
        result3 = await mcp_integration.discover_servers(query="filesystem", force_refresh=True)
        assert result3.total_found == 1
        assert mock_scan.call_count == 2


@pytest.mark.asyncio
async def test_validate_server_success(mcp_integration, sample_mcp_server):
    """Test successful server validation."""
    with patch.object(
        mcp_integration, "_validate_server_connection", new_callable=AsyncMock
    ) as mock_validate:
        mock_validate.return_value = True

        result = await mcp_integration.validate_server(sample_mcp_server)

        assert result.status == MCPIntegrationStatus.VALIDATED
        assert result.server.name == "test-server"
        assert len(result.validation_errors) == 0


@pytest.mark.asyncio
async def test_validate_server_connection_failure(mcp_integration, sample_mcp_server):
    """Test server validation with connection failure."""
    with patch.object(
        mcp_integration, "_validate_server_connection", new_callable=AsyncMock
    ) as mock_validate:
        mock_validate.return_value = False

        result = await mcp_integration.validate_server(sample_mcp_server)

        assert result.status == MCPIntegrationStatus.FAILED
        assert len(result.validation_errors) > 0
        assert "Failed to connect" in result.error_message


@pytest.mark.asyncio
async def test_validate_server_missing_metadata(mcp_integration):
    """Test validation of server with missing metadata."""
    incomplete_server = MCPServer(
        name="",  # Missing name
        description="Test server without name",
        capabilities=[],  # Missing capabilities
    )

    result = await mcp_integration.validate_server(incomplete_server)

    assert result.status == MCPIntegrationStatus.FAILED
    assert "Server name is required" in result.validation_errors
    assert "Server must declare at least one capability" in result.validation_errors


@pytest.mark.asyncio
async def test_integrate_server(mcp_integration, sample_mcp_server):
    """Test MCP server integration."""
    with patch.object(
        mcp_integration, "_validate_server_connection", new_callable=AsyncMock
    ) as mock_validate:
        mock_validate.return_value = True

        result = await mcp_integration.integrate_server(sample_mcp_server)

        assert result.status == MCPIntegrationStatus.INTEGRATED
        assert result.server.name == "test-server"
        assert result.integrated_at is not None
        assert sample_mcp_server.name in mcp_integration._integrations


@pytest.mark.asyncio
async def test_integrate_server_skip_validation(mcp_integration, sample_mcp_server):
    """Test integration with validation skipped."""
    result = await mcp_integration.integrate_server(sample_mcp_server, skip_validation=True)

    assert result.status == MCPIntegrationStatus.INTEGRATED
    assert sample_mcp_server.name in mcp_integration._integrations


@pytest.mark.asyncio
async def test_get_integrated_servers(mcp_integration, sample_mcp_server):
    """Test retrieving integrated servers."""
    # Start with empty integrations
    assert len(await mcp_integration.get_integrated_servers()) == 0

    # Integrate a server
    await mcp_integration.integrate_server(sample_mcp_server, skip_validation=True)

    # Should now have one integrated server
    integrated = await mcp_integration.get_integrated_servers()
    assert len(integrated) == 1
    assert integrated[0].name == "test-server"


@pytest.mark.asyncio
async def test_get_server_by_name(mcp_integration, sample_mcp_server):
    """Test retrieving server by name."""
    # Not found initially
    result = await mcp_integration.get_server_by_name("test-server")
    assert result is None

    # Integrate server
    await mcp_integration.integrate_server(sample_mcp_server, skip_validation=True)

    # Should now be found
    result = await mcp_integration.get_server_by_name("test-server")
    assert result is not None
    assert result.name == "test-server"


@pytest.mark.asyncio
async def test_get_servers_by_capability(mcp_integration, sample_mcp_server):
    """Test retrieving servers by capability."""
    # No servers initially
    servers = await mcp_integration.get_servers_by_capability("filesystem")
    assert len(servers) == 0

    # Integrate server with filesystem capability
    await mcp_integration.integrate_server(sample_mcp_server, skip_validation=True)

    # Should find server by capability
    servers = await mcp_integration.get_servers_by_capability("filesystem")
    assert len(servers) == 1
    assert servers[0].name == "test-server"

    # Should not find unrelated capability
    servers = await mcp_integration.get_servers_by_capability("nonexistent")
    assert len(servers) == 0


@pytest.mark.asyncio
async def test_find_servers_for_requirement(mcp_integration, sample_mcp_server):
    """Test finding servers for a requirement."""
    with patch.object(
        mcp_integration._scanner, "find_servers_for_capability", new_callable=AsyncMock
    ) as mock_find:
        mock_find.return_value = [sample_mcp_server]

        servers = await mcp_integration.find_servers_for_requirement("filesystem")

        assert len(servers) == 1
        assert servers[0].name == "test-server"
        mock_find.assert_called_once_with("filesystem")


@pytest.mark.asyncio
async def test_get_recommendation_stack(mcp_integration, sample_mcp_server):
    """Test getting recommendation stack."""
    mock_recommendations = {
        "filesystem": [sample_mcp_server],
        "database": [sample_mcp_server],
    }

    with patch.object(
        mcp_integration._scanner, "get_recommended_stack", new_callable=AsyncMock
    ) as mock_recommend:
        mock_recommend.return_value = mock_recommendations

        recommendations = await mcp_integration.get_recommendation_stack(["filesystem", "database"])

        assert "filesystem" in recommendations
        assert "database" in recommendations
        assert len(recommendations["filesystem"]) == 1
        assert recommendations["filesystem"][0].name == "test-server"


@pytest.mark.asyncio
async def test_get_integration_history(mcp_integration, sample_mcp_server):
    """Test getting integration history."""
    # No history initially
    history = mcp_integration.get_integration_history()
    assert len(history) == 0

    # Integrate a server
    await mcp_integration.integrate_server(sample_mcp_server, skip_validation=True)

    # Should have history
    history = mcp_integration.get_integration_history()
    assert len(history) == 1
    assert "test-server" in history
    assert history["test-server"].status == MCPIntegrationStatus.INTEGRATED


def test_clear_cache(mcp_integration, sample_mcp_server):
    """Test cache clearing."""
    # Set some cache data
    mcp_integration._discovery_cache = ScanResult(
        servers=[sample_mcp_server],
        total_found=1,
    )
    mcp_integration._last_scan_time = datetime.now()

    # Clear cache
    mcp_integration.clear_cache()

    # Should be cleared
    assert mcp_integration._discovery_cache is None
    assert mcp_integration._last_scan_time is None


@pytest.mark.asyncio
async def test_close(mcp_integration):
    """Test closing the integration."""
    with patch.object(mcp_integration._scanner, "close", new_callable=AsyncMock) as mock_close:
        await mcp_integration.close()
        mock_close.assert_called_once()


def test_mcp_integration_result_serialization(sample_mcp_server):
    """Test MCPIntegrationResult serialization."""
    result = MCPIntegrationResult(
        server=sample_mcp_server,
        status=MCPIntegrationStatus.INTEGRATED,
        integrated_at=datetime.now(),
        metadata={"test": "data"},
    )

    result_dict = result.to_dict()

    assert result_dict["status"] == "integrated"
    assert result_dict["server"]["name"] == "test-server"
    assert result_dict["metadata"]["test"] == "data"
