"""Run Lifecycle Manager for AutonomousExecutor.

Extracted from autonomous_executor.py as part of IMP-MAINT-001.
Handles run initialization, validation, and lifecycle management.

This module provides:
- API key validation (IMP-R06)
- Startup checks from DEBUG_JOURNAL.md
- Project ID detection from run_id
- Configuration validation at startup
- Execute fix flag loading from config
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from autopack.utils import mask_credential

logger = logging.getLogger(__name__)


class ApiKeyValidationError(ValueError):
    """Raised when API key validation fails."""

    pass


class RunLifecycleManager:
    """Manages run initialization and lifecycle.

    Centralizes validation and setup logic that runs at executor startup:
    - API key format validation
    - Proactive startup checks
    - Configuration validation
    - Project ID detection
    """

    def __init__(
        self,
        run_id: str,
        glm_key: Optional[str] = None,
        anthropic_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        config_path: Optional[Path] = None,
    ):
        """Initialize run lifecycle manager.

        Args:
            run_id: Unique run identifier
            glm_key: GLM (Zhipu AI) API key
            anthropic_key: Anthropic API key
            openai_key: OpenAI API key
            config_path: Path to models.yaml config
        """
        self.run_id = run_id
        self.glm_key = glm_key
        self.anthropic_key = anthropic_key
        self.openai_key = openai_key
        self.config_path = config_path or (
            Path(__file__).parent.parent.parent / "config" / "models.yaml"
        )

    def validate_api_keys(self) -> None:
        """IMP-R06: Validate API keys before execution.

        Ensures at least one LLM API key is configured and validates format.
        Prevents execution with invalid/missing API keys.

        Raises:
            ApiKeyValidationError: If no valid API keys are configured or
                keys have invalid format
        """
        invalid_keys = []

        # Check if at least one key is present
        if not self.glm_key and not self.anthropic_key and not self.openai_key:
            raise ApiKeyValidationError(
                "At least one LLM API key required: "
                "GLM_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY"
            )

        # Validate GLM key format if present
        if self.glm_key:
            if not isinstance(self.glm_key, str) or len(self.glm_key.strip()) == 0:
                invalid_keys.append("GLM_API_KEY (empty or invalid format)")
            elif len(self.glm_key) < 10:  # Basic length check
                invalid_keys.append("GLM_API_KEY (suspiciously short)")

        # Validate Anthropic key format if present
        if self.anthropic_key:
            if not isinstance(self.anthropic_key, str) or len(self.anthropic_key.strip()) == 0:
                invalid_keys.append("ANTHROPIC_API_KEY (empty or invalid format)")
            elif not self.anthropic_key.startswith("sk-"):
                invalid_keys.append("ANTHROPIC_API_KEY (invalid format - must start with 'sk-')")
            elif len(self.anthropic_key) < 20:
                invalid_keys.append("ANTHROPIC_API_KEY (suspiciously short)")

        # Validate OpenAI key format if present
        if self.openai_key:
            if not isinstance(self.openai_key, str) or len(self.openai_key.strip()) == 0:
                invalid_keys.append("OPENAI_API_KEY (empty or invalid format)")
            elif not self.openai_key.startswith("sk-"):
                invalid_keys.append("OPENAI_API_KEY (invalid format - must start with 'sk-')")
            elif len(self.openai_key) < 20:
                invalid_keys.append("OPENAI_API_KEY (suspiciously short)")

        # Raise error if any keys are invalid
        if invalid_keys:
            raise ApiKeyValidationError(
                "Invalid API key(s) detected:\n  - " + "\n  - ".join(invalid_keys)
            )

        # IMP-SEC-002: Log masked credentials for debugging
        configured_keys = []
        if self.glm_key:
            configured_keys.append(f"GLM_API_KEY={mask_credential(self.glm_key)}")
        if self.anthropic_key:
            configured_keys.append(f"ANTHROPIC_API_KEY={mask_credential(self.anthropic_key)}")
        if self.openai_key:
            configured_keys.append(f"OPENAI_API_KEY={mask_credential(self.openai_key)}")

        logger.info(f"API key validation passed. Configured: {', '.join(configured_keys)}")

    def run_startup_checks(self) -> Dict[str, Any]:
        """Run proactive startup checks from DEBUG_JOURNAL.md.

        This implements the prevention system by applying learned fixes
        BEFORE errors occur (proactive vs reactive).

        Returns:
            Dict with check results and any errors
        """
        from autopack.journal_reader import get_startup_checks

        logger.info("Running proactive startup checks from DEBUG_JOURNAL.md...")
        results = {"passed": 0, "failed": 0, "skipped": 0, "errors": []}

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
                    results["skipped"] += 1
                    continue

                logger.info(f"[{priority}] Checking: {check_name}")
                logger.info(f"  Reason: {reason}")

                try:
                    # Run the check
                    if callable(check_fn):
                        passed = check_fn()
                    else:
                        results["skipped"] += 1
                        continue

                    if not passed:
                        logger.warning("  Check FAILED - applying proactive fix...")
                        results["failed"] += 1
                        if callable(fix_fn):
                            fix_fn()
                            logger.info("  Fix applied successfully")
                        else:
                            logger.warning("  No fix function available")
                    else:
                        logger.info("  Check PASSED")
                        results["passed"] += 1

                except Exception as e:
                    logger.warning(f"  Startup check failed with error: {e}")
                    results["errors"].append(f"{check_name}: {str(e)}")

        except Exception as e:
            logger.warning(f"Startup checks system unavailable: {e}")
            results["errors"].append(f"System: {str(e)}")

        # BUILD-130: Schema validation on startup
        self._run_schema_validation(results)

        logger.info("Startup checks complete")
        return results

    def _run_schema_validation(self, results: Dict[str, Any]) -> None:
        """Run database schema validation on startup.

        BUILD-130: Fail-fast if schema invalid.

        Args:
            results: Results dict to update with schema validation status
        """
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
                        f"Database schema validation failed: "
                        f"{len(schema_result.errors)} violations detected. "
                        "Run 'python scripts/break_glass_repair.py diagnose' to see details."
                    )
            else:
                logger.warning("[SchemaValidator] No database URL found - skipping validation")

        except ImportError as e:
            logger.warning(f"[SchemaValidator] Schema validator not available: {e}")
        except RuntimeError:
            raise  # Re-raise schema validation failures
        except Exception as e:
            logger.warning(f"[SchemaValidator] Schema validation failed: {e}")

    def detect_project_id(self) -> str:
        """Detect project ID from run_id prefix.

        Returns:
            Project identifier (e.g., 'file-organizer-app-v1', 'autopack')
        """
        if self.run_id.startswith("fileorg-"):
            return "file-organizer-app-v1"
        elif self.run_id.startswith("backlog-"):
            return "file-organizer-app-v1"
        elif self.run_id.startswith("maintenance-"):
            return "file-organizer-app-v1"
        else:
            return "autopack"

    def load_execute_fix_flag(self) -> bool:
        """Read doctor.allow_execute_fix_global from models.yaml.

        Determines whether Doctor is permitted to run execute_fix during a run.
        Defaults to False on missing/invalid config to stay safe.

        Returns:
            True if execute_fix is allowed, False otherwise
        """
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            doctor_cfg = config.get("doctor", {}) or {}
            return bool(doctor_cfg.get("allow_execute_fix_global", False))
        except Exception as e:
            logger.warning(f"Failed to load execute_fix flag from {self.config_path}: {e}")
            return False

    def validate_config_at_startup(self) -> None:
        """Run startup validations from config_loader.

        Per GPT_RESPONSE26: Validate token_soft_caps configuration at startup.
        """
        try:
            if self.config_path.exists():
                with open(self.config_path) as f:
                    config = yaml.safe_load(f)
                    from autopack.config_loader import validate_token_soft_caps

                    validate_token_soft_caps(config)
        except Exception as e:
            logger.debug(f"[Config] Startup validation skipped: {e}")
