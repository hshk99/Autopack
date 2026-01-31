"""
Startup Validation Module

Extracted from autonomous_executor.py as part of IMP-GOD-001.

Handles API key validation, startup checks, and configuration validation
that runs before the executor begins processing phases.

Key responsibilities:
- Validate API keys (GLM, Anthropic, OpenAI, Autopack) with regex patterns (IMP-SEC-008)
- Run proactive startup checks from DEBUG_JOURNAL.md
- Validate database schema on startup
- Load and validate configuration from models.yaml
"""

import logging
import re
from pathlib import Path
from typing import Optional

import yaml

from autopack.utils import mask_credential

logger = logging.getLogger(__name__)

# IMP-SEC-008: API Key Validation Patterns
# Provider-specific regex patterns for validating API key formats
API_KEY_PATTERNS = {
    "glm": re.compile(
        r"^[a-zA-Z0-9\-_]{10,}$"
    ),  # GLM: alphanumeric, dash, underscore, min 10 chars
    "anthropic": re.compile(
        r"^sk-[a-zA-Z0-9\-_]{20,}$"
    ),  # Anthropic: sk- prefix + alphanumeric/dash/underscore
    "openai": re.compile(
        r"^sk-[a-zA-Z0-9\-_]{20,}$"
    ),  # OpenAI: sk- prefix + alphanumeric/dash/underscore
    "autopack": re.compile(
        r"^[a-zA-Z0-9\-_]{10,}$"
    ),  # Autopack: alphanumeric, dash, underscore, min 10 chars
    "together_ai": re.compile(r"^[a-z0-9]{10,}$"),  # Together AI: lowercase alphanumeric
    "runpod": re.compile(r"^[a-z0-9\-]{10,}$"),  # RunPod: lowercase alphanumeric with dash
}


class StartupValidator:
    """Handles executor startup validation and checks.

    IMP-GOD-001: Extracted from AutonomousExecutor to reduce god file complexity.
    """

    def __init__(
        self,
        glm_key: Optional[str] = None,
        anthropic_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        autopack_key: Optional[str] = None,
    ):
        """Initialize startup validator.

        Args:
            glm_key: GLM (Zhipu AI) API key
            anthropic_key: Anthropic API key
            openai_key: OpenAI API key
            autopack_key: Autopack API key (optional)
        """
        self.glm_key = glm_key
        self.anthropic_key = anthropic_key
        self.openai_key = openai_key
        self.autopack_key = autopack_key

    def validate_api_keys(self) -> None:
        """IMP-R06, IMP-SEC-008: Validate API keys before execution.

        Ensures at least one LLM API key is configured and validates format
        using provider-specific regex patterns.
        Prevents execution with invalid/missing API keys.

        Raises:
            ValueError: If no valid API keys are configured or keys have invalid format
        """
        invalid_keys = []

        # Check if at least one key is present
        if not self.glm_key and not self.anthropic_key and not self.openai_key:
            raise ValueError(
                "At least one LLM API key required: GLM_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY"
            )

        # Validate GLM key format if present (IMP-SEC-008)
        if self.glm_key:
            if not isinstance(self.glm_key, str) or len(self.glm_key.strip()) == 0:
                invalid_keys.append("GLM_API_KEY (empty or invalid format)")
            elif not API_KEY_PATTERNS["glm"].match(self.glm_key):
                invalid_keys.append(
                    "GLM_API_KEY (invalid format - expected alphanumeric with dash/underscore, min 10 chars)"
                )

        # Validate Anthropic key format if present (IMP-SEC-008)
        if self.anthropic_key:
            if not isinstance(self.anthropic_key, str) or len(self.anthropic_key.strip()) == 0:
                invalid_keys.append("ANTHROPIC_API_KEY (empty or invalid format)")
            elif not API_KEY_PATTERNS["anthropic"].match(self.anthropic_key):
                invalid_keys.append(
                    "ANTHROPIC_API_KEY (invalid format - expected sk- prefix followed by alphanumeric, min 23 chars total)"
                )

        # Validate OpenAI key format if present (IMP-SEC-008)
        if self.openai_key:
            if not isinstance(self.openai_key, str) or len(self.openai_key.strip()) == 0:
                invalid_keys.append("OPENAI_API_KEY (empty or invalid format)")
            elif not API_KEY_PATTERNS["openai"].match(self.openai_key):
                invalid_keys.append(
                    "OPENAI_API_KEY (invalid format - expected sk- prefix followed by alphanumeric, min 23 chars total)"
                )

        # Validate Autopack key format if present (IMP-SEC-008)
        if self.autopack_key:
            if not isinstance(self.autopack_key, str) or len(self.autopack_key.strip()) == 0:
                invalid_keys.append("AUTOPACK_API_KEY (empty or invalid format)")
            elif not API_KEY_PATTERNS["autopack"].match(self.autopack_key):
                invalid_keys.append(
                    "AUTOPACK_API_KEY (invalid format - expected alphanumeric with dash/underscore, min 10 chars)"
                )

        # Raise error if any keys are invalid
        if invalid_keys:
            raise ValueError("Invalid API key(s) detected:\n  - " + "\n  - ".join(invalid_keys))

        # IMP-SEC-002: Log masked credentials for debugging (never log full credentials)
        configured_keys = []
        if self.glm_key:
            configured_keys.append(f"GLM_API_KEY={mask_credential(self.glm_key)}")
        if self.anthropic_key:
            configured_keys.append(f"ANTHROPIC_API_KEY={mask_credential(self.anthropic_key)}")
        if self.openai_key:
            configured_keys.append(f"OPENAI_API_KEY={mask_credential(self.openai_key)}")
        if self.autopack_key:
            configured_keys.append(f"AUTOPACK_API_KEY={mask_credential(self.autopack_key)}")

        logger.info(f"API key validation passed. Configured: {', '.join(configured_keys)}")

    def run_startup_checks(self) -> None:
        """
        Phase 1.4-1.5: Run proactive startup checks from DEBUG_JOURNAL.md

        This implements the prevention system from ref5.md by applying
        learned fixes BEFORE errors occur (proactive vs reactive).
        """
        from autopack.journal_reader import get_startup_checks

        logger.info("Running proactive startup checks from DEBUG_JOURNAL.md...")

        try:
            checks = get_startup_checks()

            for check_config in checks:
                check_name = check_config.get("name")
                check_fn = check_config.get("check")
                fix_fn = check_config.get("fix")
                priority = check_config.get("priority", "MEDIUM")
                reason = check_config.get("reason", "")

                # Skip placeholder checks (implemented elsewhere)
                if check_fn == "implemented_in_executor":
                    continue

                logger.info(f"[{priority}] Checking: {check_name}")
                logger.info(f"  Reason: {reason}")

                try:
                    # Run the check
                    if callable(check_fn):
                        passed = check_fn()
                    else:
                        # Skip non-callable checks
                        continue

                    if not passed:
                        logger.warning("  Check FAILED - applying proactive fix...")
                        if callable(fix_fn):
                            fix_fn()
                            logger.info("  Fix applied successfully")
                        else:
                            logger.warning("  No fix function available")
                    else:
                        logger.info("  Check PASSED")

                except Exception as e:
                    logger.warning(f"  Startup check failed with error: {e}")
                    # Continue with other checks even if one fails

        except Exception as e:
            # Gracefully continue if startup checks system fails
            logger.warning(f"Startup checks system unavailable: {e}")

        # BUILD-130: Schema validation on startup (fail-fast if schema invalid)
        self._run_schema_validation()

        logger.info("Startup checks complete")

    def _run_schema_validation(self) -> None:
        """Run database schema validation on startup."""
        try:
            from autopack.config import get_database_url
            from autopack.schema_validator import SchemaValidator

            database_url = get_database_url()
            if database_url:
                validator = SchemaValidator(database_url)
                schema_result = validator.validate_on_startup()

                if not schema_result.is_valid:
                    logger.error("[FATAL] Schema validation failed on startup!")
                    logger.error(f"[FATAL] Found {len(schema_result.errors)} schema violations")
                    logger.error("[FATAL] Run: python scripts/break_glass_repair.py diagnose")
                    raise RuntimeError(
                        f"Database schema validation failed: {len(schema_result.errors)} violations detected. "
                        f"Run 'python scripts/break_glass_repair.py diagnose' to see details."
                    )
            else:
                logger.warning(
                    "[SchemaValidator] No database URL found - skipping schema validation"
                )

        except ImportError as e:
            logger.warning(f"[SchemaValidator] Schema validator not available: {e}")
        except RuntimeError:
            # Re-raise RuntimeError from schema validation
            raise
        except Exception as e:
            logger.warning(f"[SchemaValidator] Schema validation failed: {e}")

    def validate_config_at_startup(self) -> None:
        """
        Run startup validations from config_loader.

        Per GPT_RESPONSE26: Validate token_soft_caps configuration at startup.
        """
        try:
            config_path = Path(__file__).parent.parent.parent / "config" / "models.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                    from autopack.config_loader import validate_token_soft_caps

                    validate_token_soft_caps(config)
        except Exception as e:
            logger.debug(f"[Config] Startup validation skipped: {e}")

    def load_execute_fix_flag(self, config_path: Path) -> bool:
        """
        Read doctor.allow_execute_fix_global from models.yaml to decide whether
        Doctor is permitted to run execute_fix during a run.

        Defaults to False on missing/invalid config to stay safe.

        Args:
            config_path: Path to models.yaml config file

        Returns:
            True if execute_fix is allowed, False otherwise
        """
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            doctor_cfg = config.get("doctor", {}) or {}
            return bool(doctor_cfg.get("allow_execute_fix_global", False))
        except Exception as e:  # pragma: no cover - defensive guard
            logger.warning(f"Failed to load execute_fix flag from {config_path}: {e}")
            return False

    @staticmethod
    def detect_project_id(run_id: str) -> str:
        """Detect project ID from run_id prefix.

        Args:
            run_id: Run identifier (e.g., 'fileorg-country-uk-20251205-132826')

        Returns:
            Project identifier (e.g., 'file-organizer-app-v1', 'autopack')
        """
        if run_id.startswith("fileorg-"):
            return "file-organizer-app-v1"
        elif run_id.startswith("backlog-"):
            return "file-organizer-app-v1"
        elif run_id.startswith("maintenance-"):
            return "file-organizer-app-v1"
        else:
            return "autopack"
