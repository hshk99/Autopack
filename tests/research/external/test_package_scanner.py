"""Tests for Package Scanner."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autopack.research.external.package_scanner import (
    PackageInfo,
    PackageRegistry,
    PackageScanner,
    SearchResult,
)


class TestPackageInfo:
    """Test cases for PackageInfo dataclass."""

    def test_create_package(self):
        """Test creating a package info."""
        pkg = PackageInfo(
            name="react",
            registry=PackageRegistry.NPM,
            version="18.2.0",
            description="A JavaScript library for building user interfaces",
            downloads=10000000,
            stars=200000,
        )

        assert pkg.name == "react"
        assert pkg.registry == PackageRegistry.NPM
        assert pkg.version == "18.2.0"
        assert pkg.downloads == 10000000

    def test_package_defaults(self):
        """Test default values for PackageInfo."""
        pkg = PackageInfo(name="test-pkg", registry=PackageRegistry.PYPI)

        assert pkg.version == ""
        assert pkg.description == ""
        assert pkg.downloads == 0
        assert pkg.stars == 0
        assert pkg.maintainers == []
        assert pkg.keywords == []

    def test_to_dict(self):
        """Test package conversion to dictionary."""
        pkg = PackageInfo(
            name="requests",
            registry=PackageRegistry.PYPI,
            version="2.28.0",
            description="HTTP library",
            downloads=50000000,
            stars=50000,
            license="Apache 2.0",
            keywords=["http", "requests"],
        )

        result = pkg.to_dict()

        assert isinstance(result, dict)
        assert result["name"] == "requests"
        assert result["registry"] == "pypi"
        assert result["version"] == "2.28.0"
        assert result["license"] == "Apache 2.0"
        assert "http" in result["keywords"]

    def test_from_dict(self):
        """Test creating package from dictionary."""
        data = {
            "name": "django",
            "registry": "pypi",
            "version": "4.0.0",
            "description": "Web framework",
            "downloads": 100000000,
            "stars": 70000,
            "license": "BSD",
            "keywords": ["web", "framework"],
            "last_updated": "2024-01-15T10:00:00Z",
        }

        pkg = PackageInfo.from_dict(data)

        assert pkg.name == "django"
        assert pkg.registry == PackageRegistry.PYPI
        assert pkg.version == "4.0.0"
        assert pkg.downloads == 100000000
        assert pkg.last_updated is not None

    def test_from_dict_with_invalid_registry(self):
        """Test creating package with invalid registry."""
        data = {
            "name": "test",
            "registry": "invalid_registry",
        }

        pkg = PackageInfo.from_dict(data)

        assert pkg.registry == PackageRegistry.NPM  # Default


class TestSearchResult:
    """Test cases for SearchResult dataclass."""

    def test_create_result(self):
        """Test creating a search result."""
        packages = [
            PackageInfo(name="pkg1", registry=PackageRegistry.NPM),
            PackageInfo(name="pkg2", registry=PackageRegistry.NPM),
        ]
        result = SearchResult(
            packages=packages,
            total_found=2,
            query="test",
            registry=PackageRegistry.NPM,
        )

        assert len(result.packages) == 2
        assert result.total_found == 2
        assert result.query == "test"
        assert result.registry == PackageRegistry.NPM

    def test_to_dict(self):
        """Test search result conversion to dictionary."""
        result = SearchResult(
            packages=[PackageInfo(name="test", registry=PackageRegistry.NPM)],
            total_found=1,
            query="react",
            registry=PackageRegistry.NPM,
        )

        data = result.to_dict()

        assert isinstance(data, dict)
        assert data["total_found"] == 1
        assert data["query"] == "react"
        assert data["registry"] == "npm"
        assert len(data["packages"]) == 1


class TestPackageScanner:
    """Test cases for PackageScanner."""

    def setup_method(self):
        """Set up test fixtures."""
        self.scanner = PackageScanner()

    @pytest.mark.asyncio
    async def test_search_npm_empty(self):
        """Test NPM search with no results."""
        with patch.object(self.scanner, "_search_npm", new_callable=AsyncMock) as mock_npm:
            mock_npm.return_value = []

            result = await self.scanner.search_packages("nonexistent", PackageRegistry.NPM)

            assert isinstance(result, SearchResult)
            assert result.total_found == 0
            assert result.packages == []
            assert result.registry == PackageRegistry.NPM

    @pytest.mark.asyncio
    async def test_search_pypi_empty(self):
        """Test PyPI search with no results."""
        with patch.object(self.scanner, "_search_pypi", new_callable=AsyncMock) as mock_pypi:
            mock_pypi.return_value = []

            result = await self.scanner.search_packages("nonexistent", PackageRegistry.PYPI)

            assert isinstance(result, SearchResult)
            assert result.total_found == 0
            assert result.packages == []
            assert result.registry == PackageRegistry.PYPI

    @pytest.mark.asyncio
    async def test_search_with_results(self):
        """Test search with results."""
        packages = [
            PackageInfo(
                name="react",
                registry=PackageRegistry.NPM,
                version="18.0.0",
                downloads=10000000,
            ),
            PackageInfo(
                name="vue",
                registry=PackageRegistry.NPM,
                version="3.0.0",
                downloads=5000000,
            ),
        ]

        with patch.object(self.scanner, "_search_npm", new_callable=AsyncMock) as mock_npm:
            mock_npm.return_value = packages

            result = await self.scanner.search_packages("javascript framework", PackageRegistry.NPM)

            assert result.total_found == 2
            assert len(result.packages) == 2

    @pytest.mark.asyncio
    async def test_search_with_min_downloads_filter(self):
        """Test filtering by minimum downloads."""
        packages = [
            PackageInfo(
                name="popular",
                registry=PackageRegistry.NPM,
                downloads=10000000,
            ),
            PackageInfo(
                name="unpopular",
                registry=PackageRegistry.NPM,
                downloads=1000,
            ),
        ]

        with patch.object(self.scanner, "_search_npm", new_callable=AsyncMock) as mock_npm:
            mock_npm.return_value = packages

            result = await self.scanner.search_packages(
                "library",
                PackageRegistry.NPM,
                min_downloads=5000000,
            )

            assert result.total_found == 1
            assert result.packages[0].name == "popular"

    @pytest.mark.asyncio
    async def test_search_with_min_stars_filter(self):
        """Test filtering by minimum stars."""
        packages = [
            PackageInfo(
                name="well-starred",
                registry=PackageRegistry.PYPI,
                stars=5000,
            ),
            PackageInfo(
                name="low-starred",
                registry=PackageRegistry.PYPI,
                stars=100,
            ),
        ]

        with patch.object(self.scanner, "_search_pypi", new_callable=AsyncMock) as mock_pypi:
            mock_pypi.return_value = packages

            result = await self.scanner.search_packages(
                "library",
                PackageRegistry.PYPI,
                min_stars=1000,
            )

            assert result.total_found == 1
            assert result.packages[0].name == "well-starred"

    @pytest.mark.asyncio
    async def test_search_handles_error(self):
        """Test handling search errors gracefully."""
        with patch.object(self.scanner, "_search_npm", new_callable=AsyncMock) as mock_npm:
            mock_npm.side_effect = Exception("Network error")

            result = await self.scanner.search_packages("test", PackageRegistry.NPM)

            assert result.total_found == 0
            assert "Search error" in result.errors[0]

    def test_parse_npm_package(self):
        """Test parsing NPM package data."""
        package_data = {
            "name": "lodash",
            "version": "4.17.21",
            "description": "Utility library",
            "keywords": ["utility", "functional"],
            "links": {
                "repository": "https://github.com/lodash/lodash",
                "homepage": "https://lodash.com",
                "npm": "https://www.npmjs.com/package/lodash",
            },
            "score": {
                "final": 0.95,
                "detail": {
                    "popularity": 0.99,
                },
            },
            "date": "2024-01-20T12:00:00Z",
            "license": "MIT",
        }

        pkg = self.scanner._parse_npm_package(package_data)

        assert pkg is not None
        assert pkg.name == "lodash"
        assert pkg.registry == PackageRegistry.NPM
        assert pkg.version == "4.17.21"
        assert pkg.license == "MIT"
        assert "utility" in pkg.keywords

    def test_parse_npm_package_empty_name(self):
        """Test parsing NPM package with empty name returns None."""
        package_data = {"name": "", "description": "Test"}

        pkg = self.scanner._parse_npm_package(package_data)

        assert pkg is None

    def test_parse_pypi_search_result(self):
        """Test parsing PyPI search result."""
        result_data = {
            "name": "numpy",
            "version": "1.24.0",
            "summary": "Numerical computing library",
        }

        pkg = self.scanner._parse_pypi_search_result(result_data)

        assert pkg is not None
        assert pkg.name == "numpy"
        assert pkg.registry == PackageRegistry.PYPI
        assert pkg.version == "1.24.0"

    def test_parse_pypi_search_result_empty_name(self):
        """Test parsing PyPI result with empty name returns None."""
        result_data = {"name": "", "summary": "Test"}

        pkg = self.scanner._parse_pypi_search_result(result_data)

        assert pkg is None

    @pytest.mark.asyncio
    async def test_fetch_pypi_package_info(self):
        """Test fetching detailed PyPI package information."""
        mock_response = {
            "info": {
                "name": "requests",
                "version": "2.31.0",
                "summary": "HTTP library",
                "home_page": "https://requests.readthedocs.io",
                "license": "Apache 2.0",
                "keywords": "http requests",
                "created": "2024-01-01T10:00:00Z",
            },
            "last_serial": 12345,
        }

        with patch.object(self.scanner, "_get_client", new_callable=AsyncMock) as mock_get_client:
            mock_client = AsyncMock()
            mock_response_obj = MagicMock()
            mock_response_obj.status_code = 200
            mock_response_obj.json.return_value = mock_response
            mock_client.get.return_value = mock_response_obj
            mock_get_client.return_value = mock_client

            pkg = await self.scanner._fetch_pypi_package_info("requests")

            assert pkg is not None
            assert pkg.name == "requests"
            assert pkg.registry == PackageRegistry.PYPI
            assert pkg.version == "2.31.0"
            assert pkg.license == "Apache 2.0"

    @pytest.mark.asyncio
    async def test_fetch_pypi_package_info_not_found(self):
        """Test fetching non-existent PyPI package."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_client.get.return_value = mock_response

        self.scanner._client = mock_client

        pkg = await self.scanner._fetch_pypi_package_info("nonexistent-package-xyz")

        assert pkg is None

    @pytest.mark.asyncio
    async def test_search_by_category(self):
        """Test searching packages by category."""
        packages = [
            PackageInfo(
                name="pytest",
                registry=PackageRegistry.PYPI,
                keywords=["testing", "unit-test"],
            ),
        ]

        with patch.object(self.scanner, "search_packages", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = SearchResult(
                packages=packages,
                total_found=1,
                query="testing",
                registry=PackageRegistry.PYPI,
            )

            result = await self.scanner.search_by_category(
                "testing",
                PackageRegistry.PYPI,
            )

            assert result.total_found == 1
            assert result.packages[0].name == "pytest"

    @pytest.mark.asyncio
    async def test_compare_packages_mixed_registries(self):
        """Test comparing packages across registries."""
        npm_pkg = PackageInfo(
            name="react",
            registry=PackageRegistry.NPM,
            version="18.0.0",
        )
        pypi_pkg = PackageInfo(
            name="django",
            registry=PackageRegistry.PYPI,
            version="4.0.0",
        )

        with patch.object(self.scanner, "search_packages", new_callable=AsyncMock) as mock_search:

            async def search_side_effect(query, registry, limit=1):
                if query == "react":
                    return SearchResult(
                        packages=[npm_pkg], total_found=1, query=query, registry=PackageRegistry.NPM
                    )
                elif query == "django":
                    return SearchResult(
                        packages=[pypi_pkg],
                        total_found=1,
                        query=query,
                        registry=PackageRegistry.PYPI,
                    )
                return SearchResult(packages=[], total_found=0, query=query, registry=registry)

            mock_search.side_effect = search_side_effect

            result = await self.scanner.compare_packages(["react", "django"])

            assert len(result) == 2
            assert "react" in result
            assert "django" in result
            assert result["react"].registry == PackageRegistry.NPM
            assert result["django"].registry == PackageRegistry.PYPI

    @pytest.mark.asyncio
    async def test_close_client(self):
        """Test closing the HTTP client."""
        mock_client = MagicMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        self.scanner._client = mock_client

        await self.scanner.close()

        mock_client.aclose.assert_called_once()


class TestPackageRegistry:
    """Test cases for PackageRegistry enum."""

    def test_registry_values(self):
        """Test registry enum values."""
        assert PackageRegistry.NPM.value == "npm"
        assert PackageRegistry.PYPI.value == "pypi"
