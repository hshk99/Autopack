"""Artifact Generators Registry for research projects.

Provides a central registry for all artifact generators that produce
deployment configurations, documentation, and other outputs from
research findings.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Type

from autopack.research.generators.cicd_generator import CICDWorkflowGenerator

logger = logging.getLogger(__name__)


class ArtifactGeneratorRegistry:
    """Registry for artifact generators.

    Provides a central place to register and retrieve generators
    for different artifact types.
    """

    def __init__(self):
        """Initialize the registry with default generators."""
        self._generators: Dict[str, Any] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register default generators."""
        self.register("cicd", CICDWorkflowGenerator)

    def register(
        self,
        name: str,
        generator_class: Type[Any],
        description: str = "",
    ) -> None:
        """Register a generator class.

        Args:
            name: Unique name for the generator
            generator_class: The generator class to register
            description: Optional description of what this generator produces
        """
        self._generators[name] = {
            "class": generator_class,
            "description": description or f"Generator for {name} artifacts",
        }
        logger.debug(f"[ArtifactGeneratorRegistry] Registered generator: {name}")

    def get(self, name: str, **kwargs: Any) -> Optional[Any]:
        """Get an instantiated generator by name.

        Args:
            name: Name of the generator
            **kwargs: Arguments to pass to the generator constructor

        Returns:
            Instantiated generator or None if not found
        """
        if name not in self._generators:
            logger.warning(f"[ArtifactGeneratorRegistry] Generator not found: {name}")
            return None

        generator_class = self._generators[name]["class"]
        return generator_class(**kwargs)

    def list_generators(self) -> List[Dict[str, str]]:
        """List all registered generators.

        Returns:
            List of dicts with generator name and description
        """
        return [
            {"name": name, "description": info["description"]}
            for name, info in self._generators.items()
        ]

    def has_generator(self, name: str) -> bool:
        """Check if a generator is registered.

        Args:
            name: Name of the generator

        Returns:
            True if generator exists
        """
        return name in self._generators


# Default global registry instance
_default_registry: Optional[ArtifactGeneratorRegistry] = None


def get_registry() -> ArtifactGeneratorRegistry:
    """Get the default artifact generator registry.

    Returns:
        The global ArtifactGeneratorRegistry instance
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = ArtifactGeneratorRegistry()
    return _default_registry


def get_cicd_generator(**kwargs: Any) -> CICDWorkflowGenerator:
    """Convenience function to get the CI/CD workflow generator.

    Args:
        **kwargs: Arguments to pass to CICDWorkflowGenerator

    Returns:
        CICDWorkflowGenerator instance
    """
    generator = get_registry().get("cicd", **kwargs)
    if generator is None:
        # Fallback to direct instantiation
        return CICDWorkflowGenerator(**kwargs)
    return generator
