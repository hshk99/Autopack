"""Builder output configuration

Centralized configuration for Builder output mode and file size limits.
Loaded once from models.yaml and passed to all components to ensure
consistent thresholds across pre-flight checks, prompt building, and parsing.

Per IMPLEMENTATION_PLAN2.md Phase 1.1
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import yaml

logger = logging.getLogger(__name__)


@dataclass
class BuilderOutputConfig:
    """Configuration for Builder output mode and file size limits

    Implements GPT_RESPONSE13 recommendations:
    - 3-bucket policy (≤500, 501-1000, >1000)
    - Centralized configuration (no re-reading YAML)
    - Global shrinkage/growth detection
    """

    # File size thresholds (3-bucket policy)
    max_lines_for_full_file: int = 500  # Bucket A: full-file mode
    max_lines_hard_limit: int = 1000  # Bucket C: reject above this

    # Churn and validation
    max_churn_percent_for_small_fix: int = 30
    max_shrinkage_percent: int = 60  # Global: reject >60% shrinkage
    max_growth_multiplier: float = 3.0  # Global: reject >3x growth
    # Optional: disable small-fix churn and/or growth guard for certain file types (e.g. YAML packs)
    disable_small_fix_churn_for_yaml: bool = True
    disable_growth_guard_for_yaml: bool = True

    # Symbol validation
    symbol_validation_enabled: bool = True
    strict_for_small_fixes: bool = True
    always_preserve: List[str] = field(default_factory=list)

    # Legacy fallback
    legacy_diff_fallback_enabled: bool = True

    @classmethod
    def from_yaml(cls, config_path: Path) -> "BuilderOutputConfig":
        """Load configuration from models.yaml

        This is called ONCE at application startup, not on every phase.

        Args:
            config_path: Path to models.yaml

        Returns:
            BuilderOutputConfig instance
        """
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            builder_config = config.get("builder_output_mode", {})

            return cls(
                max_lines_for_full_file=builder_config.get("max_lines_for_full_file", 500),
                max_lines_hard_limit=builder_config.get("max_lines_hard_limit", 1000),
                max_churn_percent_for_small_fix=builder_config.get(
                    "max_churn_percent_for_small_fix", 30
                ),
                max_shrinkage_percent=builder_config.get("max_shrinkage_percent", 60),
                max_growth_multiplier=builder_config.get("max_growth_multiplier", 3.0),
                disable_small_fix_churn_for_yaml=builder_config.get(
                    "disable_small_fix_churn_for_yaml", True
                ),
                disable_growth_guard_for_yaml=builder_config.get(
                    "disable_growth_guard_for_yaml", True
                ),
                symbol_validation_enabled=builder_config.get("symbol_validation", {}).get(
                    "enabled", True
                ),
                strict_for_small_fixes=builder_config.get("symbol_validation", {}).get(
                    "strict_for_small_fixes", True
                ),
                always_preserve=builder_config.get("symbol_validation", {}).get(
                    "always_preserve", []
                ),
                legacy_diff_fallback_enabled=builder_config.get(
                    "legacy_diff_fallback_enabled", True
                ),
            )
        except Exception as e:
            logger.warning(f"Failed to load BuilderOutputConfig: {e}, using defaults")
            return cls()
