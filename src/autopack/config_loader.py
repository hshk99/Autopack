"""Minimal per-project configuration loader

Following GPT's recommendation: Start small, only what we actually use.
"""

from pathlib import Path
from typing import Dict, Optional
import yaml


class AutopackConfig:
    """Minimal project configuration"""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Load configuration from .autopack/config.yaml

        Args:
            config_path: Path to config file (defaults to .autopack/config.yaml)
        """
        self.config_path = config_path or Path(".autopack/config.yaml")
        self._config = self._load_config()

    def _load_config(self) -> Dict:
        """Load and validate config file"""
        if not self.config_path.exists():
            # Return sensible defaults if no config file
            return self._get_defaults()

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}

            # Merge with defaults
            return self._merge_with_defaults(config)
        except Exception as e:
            print(f"Warning: Failed to load config from {self.config_path}: {e}")
            return self._get_defaults()

    def _get_defaults(self) -> Dict:
        """Sensible defaults when no config file exists"""
        return {
            "project": {
                "name": "Autopack Project",
                "type": "backend"
            },
            "quality": {
                "test_strictness": "normal"
            },
            "documentation": {
                "mode": "minimal"
            }
        }

    def _merge_with_defaults(self, config: Dict) -> Dict:
        """Merge user config with defaults"""
        defaults = self._get_defaults()

        # Simple deep merge
        result = defaults.copy()
        for section in ["project", "quality", "documentation"]:
            if section in config:
                result[section].update(config[section])

        return result

    # Property accessors for type safety and convenience

    @property
    def project_name(self) -> str:
        """Project name"""
        return self._config["project"]["name"]

    @property
    def project_type(self) -> str:
        """Project type: backend|frontend|fullstack|library|cli"""
        return self._config["project"]["type"]

    @property
    def test_strictness(self) -> str:
        """Test strictness: lenient|normal|strict"""
        return self._config["quality"]["test_strictness"]

    @property
    def documentation_mode(self) -> str:
        """Documentation mode: skip|minimal|full"""
        return self._config["documentation"]["mode"]

    def is_strict_quality(self) -> bool:
        """Check if strict quality enforcement is enabled"""
        return self.test_strictness == "strict"

    def is_lenient_quality(self) -> bool:
        """Check if lenient quality mode is enabled"""
        return self.test_strictness == "lenient"

    def should_generate_docs(self) -> bool:
        """Check if documentation generation is enabled"""
        return self.documentation_mode != "skip"

    def should_generate_full_docs(self) -> bool:
        """Check if full documentation generation is enabled"""
        return self.documentation_mode == "full"


# Global config instance (lazy loaded)
_config: Optional[AutopackConfig] = None


def get_config(config_path: Optional[Path] = None) -> AutopackConfig:
    """
    Get global config instance (singleton pattern)

    Args:
        config_path: Path to config file (only used on first call)

    Returns:
        AutopackConfig instance
    """
    global _config
    if _config is None:
        _config = AutopackConfig(config_path)
    return _config


def reload_config(config_path: Optional[Path] = None):
    """
    Force reload of configuration (useful for testing)

    Args:
        config_path: Path to config file
    """
    global _config
    _config = AutopackConfig(config_path)
