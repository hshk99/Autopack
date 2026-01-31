"""Tests for MCP Discovery module."""

import asyncio
import json
import time

import pytest

from autopack.research.discovery.mcp_discovery import (MCPRegistryCache,
                                                       MCPRegistryScanner,
                                                       MCPScanResult,
                                                       MCPToolCapability,
                                                       MCPToolDescriptor,
                                                       MCPToolMaintainer,
                                                       MCPToolMaturity)


class TestMCPToolCapability:
    """Test cases for MCPToolCapability."""

    def test_capability_creation(self):
        """Test creating a capability."""
        cap = MCPToolCapability(
            name="search",
            description="Web search capability",
            version="1.0",
            supported_formats=["json", "text"],
        )

        assert cap.name == "search"
        assert cap.description == "Web search capability"
        assert cap.version == "1.0"
        assert "json" in cap.supported_formats

    def test_capability_defaults(self):
        """Test capability with default values."""
        cap = MCPToolCapability(
            name="query",
            description="Query database",
        )

        assert cap.version == "1.0"
        assert cap.supported_formats == []


class TestMCPToolDescriptor:
    """Test cases for MCPToolDescriptor."""

    def setup_method(self):
        """Set up test fixtures."""
        self.capability = MCPToolCapability(
            name="search",
            description="Web search",
            version="1.0",
        )
        self.descriptor = MCPToolDescriptor(
            name="test-tool",
            description="Test tool for searching",
            capabilities=[self.capability],
            maturity=MCPToolMaturity.STABLE,
            maintainer=MCPToolMaintainer.OFFICIAL,
            requirements={"api_key": True},
            url="https://example.com",
            npm_package="@test/tool",
            tags=["search", "web"],
        )

    def test_descriptor_creation(self):
        """Test creating a tool descriptor."""
        assert self.descriptor.name == "test-tool"
        assert self.descriptor.description == "Test tool for searching"
        assert self.descriptor.maturity == MCPToolMaturity.STABLE
        assert self.descriptor.maintainer == MCPToolMaintainer.OFFICIAL

    def test_descriptor_defaults(self):
        """Test descriptor with default values."""
        descriptor = MCPToolDescriptor(
            name="minimal",
            description="Minimal descriptor",
        )

        assert descriptor.maturity == MCPToolMaturity.STABLE
        assert descriptor.maintainer == MCPToolMaintainer.COMMUNITY
        assert descriptor.capabilities == []
        assert descriptor.support_async is True
        assert descriptor.installation_difficulty == "low"

    def test_descriptor_to_dict(self):
        """Test converting descriptor to dictionary."""
        desc_dict = self.descriptor.to_dict()

        assert isinstance(desc_dict, dict)
        assert desc_dict["name"] == "test-tool"
        assert desc_dict["maturity"] == "stable"
        assert desc_dict["maintainer"] == "official"
        assert len(desc_dict["capabilities"]) == 1
        assert desc_dict["capabilities"][0]["name"] == "search"

    def test_descriptor_from_dict(self):
        """Test creating descriptor from dictionary."""
        data = {
            "name": "from-dict",
            "description": "Created from dict",
            "maturity": "beta",
            "maintainer": "community",
            "capabilities": [
                {
                    "name": "query",
                    "description": "Query data",
                    "version": "2.0",
                    "supported_formats": ["json"],
                }
            ],
            "tags": ["data", "query"],
            "npm_package": "@pkg/tool",
        }

        descriptor = MCPToolDescriptor.from_dict(data)

        assert descriptor.name == "from-dict"
        assert descriptor.maturity == MCPToolMaturity.BETA
        assert descriptor.maintainer == MCPToolMaintainer.COMMUNITY
        assert len(descriptor.capabilities) == 1
        assert descriptor.capabilities[0].name == "query"
        assert "data" in descriptor.tags

    def test_descriptor_round_trip(self):
        """Test converting to dict and back."""
        original_dict = self.descriptor.to_dict()
        restored = MCPToolDescriptor.from_dict(original_dict)

        assert restored.name == self.descriptor.name
        assert restored.maturity == self.descriptor.maturity
        assert len(restored.capabilities) == len(self.descriptor.capabilities)


class TestMCPRegistryScanner:
    """Test cases for MCPRegistryScanner."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scanner = MCPRegistryScanner()

    def test_scanner_initialization(self):
        """Test scanner initializes with default registry."""
        assert len(self.scanner.registry) > 0
        assert any(tool.name == "brave-search" for tool in self.scanner.registry)
        assert any(tool.name == "github" for tool in self.scanner.registry)

    def test_get_tool_by_name(self):
        """Test retrieving a tool by name."""
        tool = self.scanner.get_tool_by_name("github")

        assert tool is not None
        assert tool.name == "github"
        assert tool.maturity == MCPToolMaturity.STABLE

    def test_get_tool_by_name_not_found(self):
        """Test retrieving non-existent tool."""
        tool = self.scanner.get_tool_by_name("non-existent")

        assert tool is None

    def test_list_all_tools(self):
        """Test listing all tools."""
        all_tools = self.scanner.list_all_tools()

        assert isinstance(all_tools, list)
        assert len(all_tools) > 0
        assert all(isinstance(tool, MCPToolDescriptor) for tool in all_tools)

    def test_get_tools_by_tag(self):
        """Test retrieving tools by tag."""
        search_tools = self.scanner.get_tools_by_tag("search")

        assert len(search_tools) > 0
        assert all("search" in tool.tags for tool in search_tools)

    def test_get_tools_by_tag_none_found(self):
        """Test retrieving tools with non-existent tag."""
        tools = self.scanner.get_tools_by_tag("non-existent-tag")

        assert tools == []

    def test_get_tools_by_maturity(self):
        """Test retrieving tools by maturity level."""
        stable_tools = self.scanner.get_tools_by_maturity(MCPToolMaturity.STABLE)

        assert len(stable_tools) > 0
        assert all(tool.maturity == MCPToolMaturity.STABLE for tool in stable_tools)

    def test_register_custom_tool(self):
        """Test registering a custom tool."""
        custom_tool = MCPToolDescriptor(
            name="custom-tool",
            description="Custom MCP tool",
            tags=["custom"],
        )

        self.scanner.register_custom_tool(custom_tool)

        retrieved = self.scanner.get_tool_by_name("custom-tool")
        assert retrieved is not None
        assert retrieved.name == "custom-tool"

    def test_register_custom_tool_duplicate(self):
        """Test registering duplicate tool replaces original."""
        original_count = len(self.scanner.registry)

        tool1 = MCPToolDescriptor(
            name="duplicate",
            description="First version",
        )
        self.scanner.register_custom_tool(tool1)
        count_after_first = len(self.scanner.registry)

        tool2 = MCPToolDescriptor(
            name="duplicate",
            description="Second version",
        )
        self.scanner.register_custom_tool(tool2)
        count_after_second = len(self.scanner.registry)

        # Should not grow beyond original + 1
        assert count_after_first == original_count + 1
        assert count_after_second == original_count + 1

        # Should have updated description
        retrieved = self.scanner.get_tool_by_name("duplicate")
        assert retrieved.description == "Second version"

    def test_match_requirements_search(self):
        """Test matching tools for search requirement."""
        matches = self.scanner.match_requirements("needs_search", True)

        assert len(matches) > 0
        assert any(tool.name == "brave-search" for tool in matches)

    def test_match_requirements_database(self):
        """Test matching tools for database requirement."""
        matches = self.scanner.match_requirements("needs_database", True)

        assert len(matches) > 0
        assert any(tool.name == "postgres" for tool in matches)

    def test_match_requirements_filesystem(self):
        """Test matching tools for filesystem requirement."""
        matches = self.scanner.match_requirements("needs_filesystem", True)

        assert len(matches) > 0
        assert any(tool.name == "filesystem" for tool in matches)

    def test_match_requirements_async(self):
        """Test matching tools for async support."""
        matches = self.scanner.match_requirements("needs_async", True)

        assert len(matches) > 0
        assert all(tool.support_async for tool in matches)

    def test_match_requirements_no_matches(self):
        """Test matching requirement with no tools."""
        matches = self.scanner.match_requirements("nonexistent_req", True)

        assert matches == []

    def test_evaluate_tool_fit_stable_official(self):
        """Test evaluating tool fit for stable official tool."""
        tool = self.scanner.get_tool_by_name("github")

        score = self.scanner.evaluate_tool_fit(tool, {})

        # Stable + official should have high score
        assert score >= 0.6

    def test_evaluate_tool_fit_with_requirements(self):
        """Test evaluating tool fit with matching requirements."""
        tool = self.scanner.get_tool_by_name("brave-search")
        requirements = {"needs_search": True, "needs_async": True}

        score = self.scanner.evaluate_tool_fit(tool, requirements)

        assert 0.0 <= score <= 1.0
        assert score > 0.5

    def test_evaluate_tool_fit_beta_community(self):
        """Test evaluating tool fit for beta community tool."""
        tool = self.scanner.get_tool_by_name("memory")

        score = self.scanner.evaluate_tool_fit(tool, {})

        # Beta + community should have moderate score (base 0.5 + beta 0.1 + medium difficulty 0.05)
        assert 0.5 < score <= 0.8

    def test_evaluate_tool_fit_normalization(self):
        """Test that tool fit scores are normalized to 0-1."""
        tool = self.scanner.get_tool_by_name("github")

        score = self.scanner.evaluate_tool_fit(tool, {})

        assert 0.0 <= score <= 1.0

    @pytest.mark.asyncio
    async def test_scan_mcp_registry_basic(self):
        """Test basic MCP registry scan."""
        result = await self.scanner.scan_mcp_registry(
            "web-app",
            {"needs_search": True, "needs_async": True},
        )

        assert isinstance(result, MCPScanResult)
        assert result.project_type == "web-app"
        assert result.total_matches >= 0
        assert isinstance(result.discovered_tools, list)

    @pytest.mark.asyncio
    async def test_scan_mcp_registry_search_requirement(self):
        """Test scanning for search tools."""
        result = await self.scanner.scan_mcp_registry(
            "data-app",
            {"needs_search": True},
        )

        assert result.total_matches > 0
        assert any(tool.name == "brave-search" for tool in result.discovered_tools)

    @pytest.mark.asyncio
    async def test_scan_mcp_registry_multiple_requirements(self):
        """Test scanning with multiple requirements."""
        result = await self.scanner.scan_mcp_registry(
            "complex-app",
            {
                "needs_search": True,
                "needs_database": True,
                "needs_filesystem": True,
            },
        )

        assert result.total_matches > 0
        assert len(result.matches_by_requirement) >= 2

    @pytest.mark.asyncio
    async def test_scan_mcp_registry_no_matches(self):
        """Test scanning with no matching requirements."""
        result = await self.scanner.scan_mcp_registry(
            "minimal-app",
            {},
        )

        # Empty requirements should result in no matches
        assert result.total_matches == 0
        assert result.discovered_tools == []

    @pytest.mark.asyncio
    async def test_scan_mcp_registry_duplicates(self):
        """Test that scan results don't have duplicate tools."""
        result = await self.scanner.scan_mcp_registry(
            "app",
            {
                "needs_search": True,
                "needs_web": True,  # Both might match same tool
            },
        )

        tool_names = [tool.name for tool in result.discovered_tools]
        assert len(tool_names) == len(set(tool_names)), "Duplicate tools found"

    @pytest.mark.asyncio
    async def test_scan_mcp_registry_results_sorted(self):
        """Test that scan results are sorted by fit score."""
        result = await self.scanner.scan_mcp_registry(
            "app",
            {
                "needs_search": True,
                "needs_async": True,
            },
        )

        # Results should be ordered by relevance
        # We can verify this by checking that fit scores are descending
        if len(result.discovered_tools) > 1:
            scores = [
                self.scanner.evaluate_tool_fit(tool, result.requirements)
                for tool in result.discovered_tools
            ]
            # Check if scores are in descending order (sorted)
            assert scores == sorted(scores, reverse=True)


class TestMCPScanResult:
    """Test cases for MCPScanResult."""

    def test_scan_result_creation(self):
        """Test creating a scan result."""
        tool = MCPToolDescriptor(
            name="test-tool",
            description="Test",
        )

        result = MCPScanResult(
            project_type="web-app",
            requirements={"needs_search": True},
            discovered_tools=[tool],
            total_matches=1,
        )

        assert result.project_type == "web-app"
        assert len(result.discovered_tools) == 1
        assert result.total_matches == 1

    def test_scan_result_to_dict(self):
        """Test converting scan result to dictionary."""
        tool = MCPToolDescriptor(
            name="test",
            description="Test tool",
        )

        result = MCPScanResult(
            project_type="app",
            requirements={"needs": "value"},
            discovered_tools=[tool],
            total_matches=1,
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["project_type"] == "app"
        assert result_dict["total_matches"] == 1
        assert len(result_dict["discovered_tools"]) == 1


class TestAsyncIntegration:
    """Test async integration and concurrent operations."""

    def test_async_scan_execution(self):
        """Test executing async scan method."""
        scanner = MCPRegistryScanner()

        # Use asyncio.run for test compatibility
        result = asyncio.run(
            scanner.scan_mcp_registry(
                "test-project",
                {"needs_search": True},
            )
        )

        assert isinstance(result, MCPScanResult)
        assert result.total_matches >= 0

    @pytest.mark.asyncio
    async def test_multiple_concurrent_scans(self):
        """Test running multiple scans concurrently."""
        scanner = MCPRegistryScanner()

        scan_tasks = [
            scanner.scan_mcp_registry(f"app{i}", {"needs_search": True}) for i in range(3)
        ]

        results = await asyncio.gather(*scan_tasks)

        assert len(results) == 3
        assert all(isinstance(r, MCPScanResult) for r in results)


class TestMCPRegistryCache:
    """Test cases for MCPRegistryCache."""

    def setup_method(self):
        """Set up test fixtures."""
        self.cache = MCPRegistryCache(ttl_seconds=3600)

    def test_cache_initialization(self):
        """Test cache initializes with correct TTL."""
        cache = MCPRegistryCache(ttl_seconds=1800)

        assert cache._ttl_seconds == 1800
        assert len(cache._cache) == 0
        assert cache.get_stats()["size"] == 0

    def test_cache_make_key_consistency(self):
        """Test that same input produces same cache key."""
        project_type = "web-app"
        requirements = {"needs_search": True, "needs_async": True}

        key1 = self.cache._make_key(project_type, requirements)
        key2 = self.cache._make_key(project_type, requirements)

        assert key1 == key2

    def test_cache_make_key_different_requirements(self):
        """Test that different requirements produce different keys."""
        project_type = "web-app"
        req1 = {"needs_search": True}
        req2 = {"needs_database": True}

        key1 = self.cache._make_key(project_type, req1)
        key2 = self.cache._make_key(project_type, req2)

        assert key1 != key2

    def test_cache_set_and_get(self):
        """Test storing and retrieving from cache."""
        tool = MCPToolDescriptor(
            name="test-tool",
            description="Test",
        )
        result = MCPScanResult(
            project_type="web-app",
            requirements={"needs_search": True},
            discovered_tools=[tool],
            total_matches=1,
        )

        project_type = "web-app"
        requirements = {"needs_search": True}

        # Store in cache
        self.cache.set(project_type, requirements, result)

        # Retrieve from cache
        cached = self.cache.get(project_type, requirements)

        assert cached is not None
        assert cached.project_type == "web-app"
        assert len(cached.discovered_tools) == 1

    def test_cache_miss(self):
        """Test cache miss on non-existent key."""
        cached = self.cache.get("unknown", {"unknown": True})

        assert cached is None

    def test_cache_statistics_hits(self):
        """Test cache hit statistics."""
        tool = MCPToolDescriptor(name="test", description="Test")
        result = MCPScanResult(
            project_type="app",
            requirements={"test": True},
            discovered_tools=[tool],
            total_matches=1,
        )

        self.cache.set("app", {"test": True}, result)

        # First hit
        self.cache.get("app", {"test": True})
        stats = self.cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 0

        # Second hit
        self.cache.get("app", {"test": True})
        stats = self.cache.get_stats()
        assert stats["hits"] == 2

    def test_cache_statistics_misses(self):
        """Test cache miss statistics."""
        self.cache.get("missing", {"test": True})
        stats = self.cache.get_stats()

        assert stats["misses"] == 1
        assert stats["hits"] == 0

    def test_cache_hit_rate(self):
        """Test cache hit rate calculation."""
        tool = MCPToolDescriptor(name="test", description="Test")
        result = MCPScanResult(
            project_type="app",
            requirements={"test": True},
            discovered_tools=[tool],
            total_matches=1,
        )

        self.cache.set("app", {"test": True}, result)

        # 2 hits
        self.cache.get("app", {"test": True})
        self.cache.get("app", {"test": True})

        # 1 miss
        self.cache.get("missing", {"test": True})

        stats = self.cache.get_stats()
        assert stats["hit_rate_percent"] == pytest.approx(66.66, abs=1)

    def test_cache_expiration(self):
        """Test cache expiration after TTL."""
        cache = MCPRegistryCache(ttl_seconds=1)

        tool = MCPToolDescriptor(name="test", description="Test")
        result = MCPScanResult(
            project_type="app",
            requirements={"test": True},
            discovered_tools=[tool],
            total_matches=1,
        )

        cache.set("app", {"test": True}, result)

        # Should be in cache
        cached = cache.get("app", {"test": True})
        assert cached is not None

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired
        cached = cache.get("app", {"test": True})
        assert cached is None

    def test_cache_clear(self):
        """Test clearing the cache."""
        tool = MCPToolDescriptor(name="test", description="Test")
        result = MCPScanResult(
            project_type="app",
            requirements={"test": True},
            discovered_tools=[tool],
            total_matches=1,
        )

        self.cache.set("app", {"test": True}, result)
        assert self.cache.get_stats()["size"] == 1

        self.cache.clear()
        assert self.cache.get_stats()["size"] == 0

    def test_cache_performance(self):
        """Test cache performance is acceptable (<1s for cached queries)."""
        tool = MCPToolDescriptor(name="test", description="Test")
        result = MCPScanResult(
            project_type="app",
            requirements={"test": True},
            discovered_tools=[tool],
            total_matches=1,
        )

        self.cache.set("app", {"test": True}, result)

        # Measure retrieval time
        start_time = time.time()
        for _ in range(100):
            self.cache.get("app", {"test": True})
        elapsed = time.time() - start_time

        # 100 queries should take less than 1 second
        assert elapsed < 1.0


class TestMCPScannerWithCache:
    """Test cases for MCPRegistryScanner with caching."""

    def test_scanner_has_cache(self):
        """Test scanner initializes with cache."""
        scanner = MCPRegistryScanner()

        assert hasattr(scanner, "_cache")
        assert isinstance(scanner._cache, MCPRegistryCache)

    def test_scanner_cache_ttl_configuration(self):
        """Test scanner accepts cache TTL configuration."""
        scanner = MCPRegistryScanner(cache_ttl_seconds=1800)

        assert scanner._cache._ttl_seconds == 1800

    @pytest.mark.asyncio
    async def test_scan_caches_result(self):
        """Test that scan results are cached."""
        scanner = MCPRegistryScanner()

        result1 = await scanner.scan_mcp_registry(
            "web-app",
            {"needs_search": True},
        )

        # Modify registry to verify we're getting cached result
        original_count = len(scanner.registry)
        scanner.registry.pop()

        result2 = await scanner.scan_mcp_registry(
            "web-app",
            {"needs_search": True},
        )

        # Results should be identical (from cache)
        assert result1.total_matches == result2.total_matches
        assert len(result1.discovered_tools) == len(result2.discovered_tools)

        # Restore registry
        scanner.registry.append(MCPToolDescriptor(
            name="restored",
            description="Restored tool",
        ))

    @pytest.mark.asyncio
    async def test_scan_cache_hit_statistics(self):
        """Test cache hit statistics for scans."""
        scanner = MCPRegistryScanner()

        # First scan - cache miss
        await scanner.scan_mcp_registry("web-app", {"needs_search": True})

        # Second scan - cache hit
        await scanner.scan_mcp_registry("web-app", {"needs_search": True})

        stats = scanner.get_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_scanner_get_cache_stats(self):
        """Test retrieving cache stats from scanner."""
        scanner = MCPRegistryScanner()

        stats = scanner.get_cache_stats()

        assert isinstance(stats, dict)
        assert "size" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate_percent" in stats

    def test_scanner_clear_cache(self):
        """Test clearing cache from scanner."""
        scanner = MCPRegistryScanner()

        # Add something to cache
        tool = MCPToolDescriptor(name="test", description="Test")
        result = MCPScanResult(
            project_type="app",
            requirements={"test": True},
            discovered_tools=[tool],
            total_matches=1,
        )
        scanner._cache.set("app", {"test": True}, result)
        assert scanner.get_cache_stats()["size"] == 1

        # Clear cache
        scanner.clear_cache()
        assert scanner.get_cache_stats()["size"] == 0

    def test_scanner_set_cache_ttl(self):
        """Test updating cache TTL."""
        scanner = MCPRegistryScanner(cache_ttl_seconds=3600)

        scanner.set_cache_ttl(1800)
        assert scanner._cache._ttl_seconds == 1800

    @pytest.mark.asyncio
    async def test_different_requirements_different_cache(self):
        """Test that different requirements produce separate cache entries."""
        scanner = MCPRegistryScanner()

        result1 = await scanner.scan_mcp_registry(
            "app",
            {"needs_search": True},
        )

        result2 = await scanner.scan_mcp_registry(
            "app",
            {"needs_database": True},
        )

        # Different requirements should produce different results
        # (unless they happen to find the same tools)
        stats = scanner.get_cache_stats()
        assert stats["size"] == 2  # Two cache entries


class TestMCPScanResultSerialization:
    """Test cases for MCPScanResult serialization."""

    def test_scan_result_to_json(self):
        """Test converting scan result to JSON."""
        tool = MCPToolDescriptor(
            name="test",
            description="Test tool",
            tags=["test"],
        )
        result = MCPScanResult(
            project_type="web-app",
            requirements={"needs_search": True},
            discovered_tools=[tool],
            total_matches=1,
            scan_timestamp="2024-01-31T12:00:00Z",
        )

        json_str = result.to_json()

        assert isinstance(json_str, str)
        assert "test" in json_str
        assert "web-app" in json_str

        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert parsed["project_type"] == "web-app"

    def test_scan_result_from_dict(self):
        """Test creating scan result from dictionary."""
        data = {
            "project_type": "web-app",
            "requirements": {"needs_search": True},
            "discovered_tools": [
                {
                    "name": "test",
                    "description": "Test tool",
                    "capabilities": [],
                    "maturity": "stable",
                    "maintainer": "official",
                    "tags": [],
                }
            ],
            "matches_by_requirement": {},
            "total_matches": 1,
            "scan_timestamp": "2024-01-31T12:00:00Z",
        }

        result = MCPScanResult.from_dict(data)

        assert result.project_type == "web-app"
        assert len(result.discovered_tools) == 1
        assert result.total_matches == 1

    def test_scan_result_round_trip(self):
        """Test converting to dict and back preserves data."""
        tool = MCPToolDescriptor(
            name="test-tool",
            description="Test tool",
            tags=["test", "search"],
        )
        original = MCPScanResult(
            project_type="data-app",
            requirements={"needs_search": True, "needs_async": True},
            discovered_tools=[tool],
            total_matches=1,
            scan_timestamp="2024-01-31T12:00:00Z",
        )

        # Convert to dict and back
        data_dict = original.to_dict()
        restored = MCPScanResult.from_dict(data_dict)

        assert restored.project_type == original.project_type
        assert restored.total_matches == original.total_matches
        assert len(restored.discovered_tools) == len(original.discovered_tools)
        assert restored.discovered_tools[0].name == original.discovered_tools[0].name
