"""Package Scanner for NPM and PyPI registries.

Scans package registries to identify useful libraries and SDKs.
Supports searching NPM and PyPI packages for project dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class PackageRegistry(Enum):
    """Package registry type."""

    NPM = "npm"
    PYPI = "pypi"


@dataclass
class PackageInfo:
    """Information about a package."""

    name: str
    registry: PackageRegistry
    version: str = ""
    description: str = ""
    downloads: int = 0
    stars: int = 0
    repository_url: str = ""
    homepage: str = ""
    license: str = ""
    maintainers: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    last_updated: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "registry": self.registry.value,
            "version": self.version,
            "description": self.description,
            "downloads": self.downloads,
            "stars": self.stars,
            "repository_url": self.repository_url,
            "homepage": self.homepage,
            "license": self.license,
            "maintainers": self.maintainers,
            "keywords": self.keywords,
            "last_updated": (self.last_updated.isoformat() if self.last_updated else None),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PackageInfo":
        """Create PackageInfo from dictionary."""
        registry = PackageRegistry.NPM
        if "registry" in data:
            try:
                registry = PackageRegistry(data["registry"])
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
            registry=registry,
            version=data.get("version", ""),
            description=data.get("description", ""),
            downloads=data.get("downloads", 0),
            stars=data.get("stars", 0),
            repository_url=data.get("repository_url", ""),
            homepage=data.get("homepage", ""),
            license=data.get("license", ""),
            maintainers=data.get("maintainers", []),
            keywords=data.get("keywords", []),
            last_updated=last_updated,
        )


@dataclass
class SearchResult:
    """Result of a package registry search."""

    packages: List[PackageInfo] = field(default_factory=list)
    total_found: int = 0
    query: str = ""
    registry: PackageRegistry = PackageRegistry.NPM
    search_timestamp: datetime = field(default_factory=datetime.now)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "packages": [p.to_dict() for p in self.packages],
            "total_found": self.total_found,
            "query": self.query,
            "registry": self.registry.value,
            "search_timestamp": self.search_timestamp.isoformat(),
            "errors": self.errors,
        }


class PackageScanner:
    """Scans NPM and PyPI registries for relevant packages.

    Supports searching packages in both NPM and PyPI registries,
    with filtering by keywords, downloads, stars, and other metadata.
    """

    # Registry endpoints
    NPM_REGISTRY_BASE = "https://registry.npmjs.org"
    PYPI_REGISTRY_BASE = "https://pypi.org/pypi"

    def __init__(
        self,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the package scanner.

        Args:
            timeout: Request timeout in seconds.
        """
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def search_packages(
        self,
        query: str,
        registry: PackageRegistry,
        limit: int = 50,
        min_downloads: int = 0,
        min_stars: int = 0,
    ) -> SearchResult:
        """Search for packages in a registry.

        Args:
            query: Search query string.
            registry: Which registry to search (NPM or PyPI).
            limit: Maximum number of results to return.
            min_downloads: Minimum download count filter.
            min_stars: Minimum stars/score filter.

        Returns:
            SearchResult containing found packages.
        """
        result = SearchResult(query=query, registry=registry)
        errors: List[str] = []

        try:
            if registry == PackageRegistry.NPM:
                packages = await self._search_npm(query, limit)
            elif registry == PackageRegistry.PYPI:
                packages = await self._search_pypi(query, limit)
            else:
                errors.append(f"Unknown registry: {registry}")
                packages = []

            # Apply filters
            filtered_packages = [
                p for p in packages if p.downloads >= min_downloads and p.stars >= min_stars
            ]

            result.packages = filtered_packages
            result.total_found = len(filtered_packages)
            result.errors = errors
            result.search_timestamp = datetime.now()

        except Exception as e:
            logger.error(f"Search failed for {registry.value}: {e}")
            errors.append(f"Search error: {str(e)}")
            result.errors = errors

        return result

    async def _search_npm(self, query: str, limit: int = 50) -> List[PackageInfo]:
        """Search NPM registry for packages.

        Args:
            query: Search query.
            limit: Maximum results to return.

        Returns:
            List of PackageInfo objects found on NPM.
        """
        packages: List[PackageInfo] = []
        client = await self._get_client()

        search_url = f"{self.NPM_REGISTRY_BASE}/-/v1/search?text={query}&size={limit}"

        try:
            response = await client.get(search_url)
            if response.status_code == 200:
                data = response.json()
                objects = data.get("objects", [])

                for obj in objects:
                    package_data = obj.get("package", {})
                    package = self._parse_npm_package(package_data)
                    if package:
                        packages.append(package)
            else:
                logger.warning(f"NPM API returned status {response.status_code}")

        except httpx.HTTPError as e:
            logger.error(f"NPM registry request failed: {e}")
            raise

        return packages

    def _parse_npm_package(self, package_data: Dict[str, Any]) -> Optional[PackageInfo]:
        """Parse NPM package data into PackageInfo.

        Args:
            package_data: Package data from NPM registry.

        Returns:
            PackageInfo if valid, None otherwise.
        """
        name = package_data.get("name", "")
        if not name:
            return None

        # Parse date
        last_updated = None
        if package_data.get("date"):
            try:
                last_updated = datetime.fromisoformat(package_data["date"].replace("Z", "+00:00"))
            except ValueError:
                pass

        # Extract links
        links = package_data.get("links", {})
        repository = links.get("repository", "")
        homepage = links.get("homepage", "")

        # Extract keywords
        keywords = package_data.get("keywords", [])

        # Get score as a proxy for quality/popularity
        score = package_data.get("score", {})
        score_detail = score.get("detail", {})
        downloads_score = int(score_detail.get("popularity", 0) * 1000)

        return PackageInfo(
            name=name,
            registry=PackageRegistry.NPM,
            version=package_data.get("version", ""),
            description=package_data.get("description", "") or "",
            downloads=downloads_score,
            stars=int(score.get("final", 0) * 10),  # Scale final score
            repository_url=repository,
            homepage=homepage,
            license=package_data.get("license", ""),
            keywords=keywords,
            last_updated=last_updated,
        )

    async def _search_pypi(self, query: str, limit: int = 50) -> List[PackageInfo]:
        """Search PyPI registry for packages.

        Args:
            query: Search query.
            limit: Maximum results to return.

        Returns:
            List of PackageInfo objects found on PyPI.
        """
        packages: List[PackageInfo] = []
        client = await self._get_client()

        # Use PyPI JSON API for search
        search_url = f"{self.PYPI_REGISTRY_BASE}/__legacy__/pypi/search?c=Development%20Status%20::%20Alpha&search={query}&page={1}"

        try:
            response = await client.get(search_url)
            if response.status_code == 200:
                data = response.json()
                results = data.get("result", [])

                for result in results[:limit]:
                    package = self._parse_pypi_search_result(result)
                    if package:
                        packages.append(package)

                # For each package, fetch detailed info
                for i, package in enumerate(packages):
                    try:
                        detailed_info = await self._fetch_pypi_package_info(package.name)
                        if detailed_info:
                            packages[i] = detailed_info
                    except Exception as e:
                        logger.warning(f"Failed to fetch details for {package.name}: {e}")

            else:
                logger.warning(f"PyPI API returned status {response.status_code}")

        except httpx.HTTPError as e:
            logger.error(f"PyPI registry request failed: {e}")
            raise

        return packages

    def _parse_pypi_search_result(self, result: Dict[str, Any]) -> Optional[PackageInfo]:
        """Parse PyPI search result into PackageInfo.

        Args:
            result: Package data from PyPI search.

        Returns:
            PackageInfo if valid, None otherwise.
        """
        name = result.get("name", "")
        if not name:
            return None

        return PackageInfo(
            name=name,
            registry=PackageRegistry.PYPI,
            version=result.get("version", ""),
            description=result.get("summary", "") or "",
            keywords=[],  # Will be populated in detailed fetch
            last_updated=None,  # Will be populated in detailed fetch
        )

    async def _fetch_pypi_package_info(self, package_name: str) -> Optional[PackageInfo]:
        """Fetch detailed information for a PyPI package.

        Args:
            package_name: Name of the package.

        Returns:
            PackageInfo with detailed information.
        """
        client = await self._get_client()
        info_url = f"{self.PYPI_REGISTRY_BASE}/{package_name}/json"

        try:
            response = await client.get(info_url)
            if response.status_code == 200:
                data = response.json()
                info = data.get("info", {})

                # Parse date if available
                last_updated = None
                if info.get("created"):
                    try:
                        last_updated = datetime.fromisoformat(
                            info["created"].replace("Z", "+00:00")
                        )
                    except ValueError:
                        pass

                return PackageInfo(
                    name=info.get("name", package_name),
                    registry=PackageRegistry.PYPI,
                    version=info.get("version", ""),
                    description=info.get("summary", "") or "",
                    repository_url=info.get("home_page", ""),
                    homepage=info.get("project_url", ""),
                    license=info.get("license", ""),
                    maintainers=info.get("maintainers", []),
                    keywords=info.get("keywords", "").split() if info.get("keywords") else [],
                    last_updated=last_updated,
                )

        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch PyPI package info for {package_name}: {e}")

        return None

    async def search_by_category(
        self,
        category: str,
        registry: PackageRegistry,
        limit: int = 20,
    ) -> SearchResult:
        """Search packages by category or keyword.

        Args:
            category: Category or keyword to search for.
            registry: Which registry to search.
            limit: Maximum number of results.

        Returns:
            SearchResult containing packages in the category.
        """
        return await self.search_packages(category, registry, limit=limit)

    async def compare_packages(
        self,
        package_names: List[str],
    ) -> Dict[str, PackageInfo]:
        """Fetch detailed info for multiple packages to compare.

        Args:
            package_names: List of package names to compare.

        Returns:
            Dictionary mapping package names to PackageInfo.
        """
        packages: Dict[str, PackageInfo] = {}

        for name in package_names:
            # Try NPM first
            try:
                npm_result = await self.search_packages(name, PackageRegistry.NPM, limit=1)
                if npm_result.packages:
                    packages[name] = npm_result.packages[0]
                    continue
            except Exception as e:
                logger.debug(f"NPM search failed for {name}: {e}")

            # Try PyPI
            try:
                pypi_result = await self.search_packages(name, PackageRegistry.PYPI, limit=1)
                if pypi_result.packages:
                    packages[name] = pypi_result.packages[0]
            except Exception as e:
                logger.debug(f"PyPI search failed for {name}: {e}")

        return packages
