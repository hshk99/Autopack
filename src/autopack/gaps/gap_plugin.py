"""Plugin architecture for custom gap detectors."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class GapResult:
    """Result from a gap detector."""

    gap_type: str
    description: str
    file_path: Optional[str] = None
    severity: str = "medium"
    auto_fixable: bool = False
    suggested_fix: Optional[str] = None


class GapDetectorPlugin(ABC):
    """Base class for gap detector plugins."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name."""
        pass

    @property
    @abstractmethod
    def gap_type(self) -> str:
        """Gap type this plugin detects."""
        pass

    @abstractmethod
    def detect(self, context: dict) -> List[GapResult]:
        """Detect gaps and return results.

        Args:
            context: Context dictionary with project_root and other metadata

        Returns:
            List of detected GapResult objects
        """
        pass


class PluginRegistry:
    """Registry for gap detector plugins."""

    def __init__(self):
        """Initialize empty plugin registry."""
        self._plugins: dict[str, GapDetectorPlugin] = {}

    def register(self, plugin: GapDetectorPlugin) -> None:
        """Register a plugin.

        Args:
            plugin: GapDetectorPlugin instance to register
        """
        self._plugins[plugin.name] = plugin
        logger.debug(f"Registered plugin: {plugin.name} (detects {plugin.gap_type})")

    def get_all(self) -> List[GapDetectorPlugin]:
        """Get all registered plugins.

        Returns:
            List of all registered GapDetectorPlugin instances
        """
        return list(self._plugins.values())

    def load_from_config(self, config_path: Path | str) -> None:
        """Load plugins from YAML config file.

        Args:
            config_path: Path to gap_plugins.yaml configuration

        Raises:
            FileNotFoundError: If config file not found
            Exception: If plugin loading fails
        """
        import yaml

        config_path = Path(config_path)
        if not config_path.exists():
            logger.warning(f"Plugin config not found: {config_path}")
            return

        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

        for plugin_config in config.get("plugins", []):
            if not plugin_config.get("enabled", True):
                logger.debug(f"Skipping disabled plugin: {plugin_config.get('name')}")
                continue

            try:
                module = import_module(plugin_config["module"])
                plugin_class = getattr(module, plugin_config["class"])
                self.register(plugin_class())
                logger.info(f"Loaded plugin: {plugin_config['name']}")
            except Exception as e:
                logger.error(f"Failed to load plugin {plugin_config.get('name')}: {e}")
