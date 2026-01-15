"""Configuration loader for Doctor system and validation utilities.

Loads Doctor configuration from config/models.yaml with fallback to sensible defaults.

Per GPT_RESPONSE26: Adds startup validation for token_soft_caps.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

import yaml

logger = logging.getLogger(__name__)


# =============================================================================
# STARTUP VALIDATION (per GPT_RESPONSE26)
# =============================================================================


def validate_token_soft_caps(config: Dict) -> None:
    """
    Validate token soft caps configuration at startup.

    Per GPT_RESPONSE26 (GPT2 recommendation): Log error if token_soft_caps.enabled=true
    but 'medium' tier is missing, since 'medium' is used as the fallback for unknown
    complexity values.

    Args:
        config: Loaded models.yaml config dict
    """
    token_caps = config.get("token_soft_caps", {})
    if token_caps.get("enabled", False):
        per_phase_caps = token_caps.get("per_phase_soft_caps", {})
        if "medium" not in per_phase_caps:
            logger.error(
                "[CONFIG] token_soft_caps.enabled=true but 'medium' tier is missing from "
                "per_phase_soft_caps. Soft cap fallback will not work correctly. "
                "Add 'medium: <value>' to config/models.yaml token_soft_caps.per_phase_soft_caps"
            )
        else:
            logger.debug(
                "[CONFIG] token_soft_caps validated: enabled=true, medium tier=%d tokens",
                per_phase_caps["medium"],
            )


@dataclass
class DoctorConfig:
    """Configuration for the Doctor error recovery system.

    Loaded from config/models.yaml doctor_models section.
    See models.yaml for authoritative field documentation.

    Attributes:
        cheap_model: Model name for routine failures (config key: cheap)
        strong_model: Model name for complex failures (config key: strong)
        min_confidence_for_cheap: Threshold below which to escalate to strong model
        health_budget_near_limit_ratio: Budget ratio that triggers strong model
        max_builder_attempts_before_complex: Attempts threshold for complexity classification
        high_risk_categories: Error categories that warrant strong model
        low_risk_categories: Error categories suitable for cheap model
        max_escalations_per_phase: Limit escalations per phase to prevent bouncing
        allow_execute_fix_global: Enable Doctor execute_fix with whitelist & caps
        max_execute_fix_per_phase: Maximum execute_fix actions per phase
    """

    cheap_model: str = "claude-sonnet-4-5"
    strong_model: str = "claude-opus-4-5"
    min_confidence_for_cheap: float = 0.7
    health_budget_near_limit_ratio: float = 0.8
    max_builder_attempts_before_complex: int = 4
    high_risk_categories: list[str] = field(
        default_factory=lambda: ["import", "logic", "patch_apply_error"]
    )
    low_risk_categories: list[str] = field(
        default_factory=lambda: ["encoding", "network", "file_io", "validation"]
    )
    max_escalations_per_phase: int = 1
    allow_execute_fix_global: bool = True
    max_execute_fix_per_phase: int = 1


def load_doctor_config() -> DoctorConfig:
    """Load Doctor configuration from config/models.yaml.

    Falls back to default values if:
    - File doesn't exist
    - File is malformed
    - Required keys are missing

    Also performs startup validation per GPT_RESPONSE26.

    Returns:
        DoctorConfig instance with loaded or default values
    """
    config_path = Path("config/models.yaml")

    if not config_path.exists():
        logger.warning(f"Config file {config_path} not found, using default Doctor configuration")
        return DoctorConfig()

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Run startup validations (per GPT_RESPONSE26)
        if data:
            validate_token_soft_caps(data)

        if not data or "doctor_models" not in data:
            logger.warning("No 'doctor_models' section in config/models.yaml, using defaults")
            return DoctorConfig()

        doctor_data = data["doctor_models"]

        # Also load from top-level 'doctor' section for allow_execute_fix settings
        doctor_section = data.get("doctor", {})

        # Create defaults instance to get default values
        defaults = DoctorConfig()

        # Extract values with fallback to defaults
        # Note: config uses 'cheap' and 'strong' keys, not 'cheap_model' and 'strong_model'
        return DoctorConfig(
            cheap_model=doctor_data.get("cheap", defaults.cheap_model),
            strong_model=doctor_data.get("strong", defaults.strong_model),
            min_confidence_for_cheap=doctor_data.get(
                "min_confidence_for_cheap", defaults.min_confidence_for_cheap
            ),
            health_budget_near_limit_ratio=doctor_data.get(
                "health_budget_near_limit_ratio", defaults.health_budget_near_limit_ratio
            ),
            max_builder_attempts_before_complex=doctor_data.get(
                "max_builder_attempts_before_complex", defaults.max_builder_attempts_before_complex
            ),
            high_risk_categories=doctor_data.get(
                "high_risk_categories", defaults.high_risk_categories
            ),
            low_risk_categories=doctor_data.get(
                "low_risk_categories", defaults.low_risk_categories
            ),
            max_escalations_per_phase=doctor_data.get(
                "max_escalations_per_phase", defaults.max_escalations_per_phase
            ),
            allow_execute_fix_global=doctor_section.get(
                "allow_execute_fix_global", defaults.allow_execute_fix_global
            ),
            max_execute_fix_per_phase=doctor_section.get(
                "max_execute_fix_per_phase", defaults.max_execute_fix_per_phase
            ),
        )

    except Exception as e:
        logger.warning(f"Error loading config/models.yaml: {e}, using defaults")
        return DoctorConfig()


# Module-level config instance
doctor_config = load_doctor_config()
