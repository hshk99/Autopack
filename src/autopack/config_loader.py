"""Configuration loader for Doctor system.

Loads Doctor configuration from config/models.yaml with fallback to sensible defaults.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class DoctorConfig:
    """Configuration for the Doctor error recovery system.
    
    Attributes:
        cheap_model: Model name for cheap/fast operations
        strong_model: Model name for complex/strong operations
        max_attempts: Maximum number of recovery attempts
        timeout_seconds: Timeout for Doctor operations
        retry_delay_seconds: Delay between retry attempts
        escalation_threshold: Number of failures before escalating to strong model
        confidence_threshold: Minimum confidence score to accept a fix
        allowed_error_types: List of error types that Doctor can handle
    """
    
    cheap_model: str = "claude-sonnet-4-5"
    strong_model: str = "claude-sonnet-4-5"
    max_attempts: int = 3
    timeout_seconds: int = 300
    retry_delay_seconds: int = 5
    escalation_threshold: int = 2
    confidence_threshold: float = 0.7
    allowed_error_types: list[str] = field(default_factory=lambda: [
        "syntax_error",
        "import_error",
        "type_error",
        "test_failure",
        "lint_error"
    ])


def load_doctor_config() -> DoctorConfig:
    """Load Doctor configuration from config/models.yaml.
    
    Falls back to default values if:
    - File doesn't exist
    - File is malformed
    - Required keys are missing
    
    Returns:
        DoctorConfig instance with loaded or default values
    """
    config_path = Path("config/models.yaml")
    
    if not config_path.exists():
        logger.warning(
            f"Config file {config_path} not found, using default Doctor configuration"
        )
        return DoctorConfig()
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        if not data or "doctor_models" not in data:
            logger.warning(
                "No 'doctor_models' section in config/models.yaml, using defaults"
            )
            return DoctorConfig()
        
        doctor_data = data["doctor_models"]
        
        # Extract values with fallback to defaults
        return DoctorConfig(
            cheap_model=doctor_data.get("cheap_model", DoctorConfig.cheap_model),
            strong_model=doctor_data.get("strong_model", DoctorConfig.strong_model),
        )
        
    except Exception as e:
        logger.warning(f"Error loading config/models.yaml: {e}, using defaults")
        return DoctorConfig()


# Module-level config instance
doctor_config = load_doctor_config()
