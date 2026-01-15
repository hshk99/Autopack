"""Configuration module for Autopack settings.

This module is intentionally small and stable. Several subsystems import it at
startup (DB, executor, API). Accidental deletion breaks telemetry tooling and
scripts that rely on `DATABASE_URL` resolution.

PR-03 (R-03 G4): *_FILE secrets support
Secrets can be loaded from files via *_FILE env vars. Precedence:
  *_FILE > direct env var > defaults
This enables Docker secrets and Kubernetes secret mounts.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .exceptions import ConfigurationError

# Local/loopback addresses that are always safe to bind to
_LOCAL_ADDRESSES = frozenset(
    {
        "127.0.0.1",
        "localhost",
        "::1",
        "0.0.0.0",  # nosec B104 - intentionally included as allowed bind address
    }
)

logger = logging.getLogger(__name__)


class ConfigError(ConfigurationError):
    """Raised when configuration is invalid.

    Deprecated: Use ConfigurationError instead.
    This class is kept for backward compatibility.
    """

    pass


def _read_secret_file(file_path: str, secret_name: str) -> Optional[str]:
    """Read secret value from a file.

    Args:
        file_path: Path to the secret file.
        secret_name: Name of the secret (for error messages).

    Returns:
        Secret value with whitespace stripped, or None if file doesn't exist.

    Raises:
        ConfigurationError: If file exists but cannot be read or is empty.
    """
    path = Path(file_path)
    if not path.exists():
        return None

    try:
        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise ConfigurationError(
                f"{secret_name}_FILE points to empty file: {file_path}. "
                f"Secret files must contain non-empty values."
            )
        return content
    except PermissionError as e:
        raise ConfigurationError(
            f"{secret_name}_FILE is unreadable (permission denied): {file_path}. "
            f"Check file permissions."
        ) from e
    except ConfigurationError:
        raise
    except Exception as e:
        raise ConfigurationError(f"Failed to read {secret_name}_FILE from {file_path}: {e}") from e


def _get_secret(
    env_var: str,
    file_env_var: Optional[str] = None,
    default: str = "",
    required_in_production: bool = False,
) -> str:
    """Get secret value with *_FILE precedence.

    Precedence: file_env_var > env_var > default

    Args:
        env_var: Environment variable name for direct value.
        file_env_var: Environment variable name for file path (e.g., DATABASE_URL_FILE).
        default: Default value if neither env var is set.
        required_in_production: If True, fail fast in production when missing.

    Returns:
        The secret value.

    Raises:
        ConfigurationError: If required in production and not set, or if file read fails.
    """
    value = default

    # First, try direct env var
    if os.getenv(env_var):
        value = os.getenv(env_var, default)

    # Second, try *_FILE env var (takes precedence)
    if file_env_var:
        file_path = os.getenv(file_env_var)
        if file_path:
            file_value = _read_secret_file(file_path, env_var)
            if file_value is not None:
                value = file_value
                # Log that we loaded from file (without revealing path in production)
                if os.getenv("AUTOPACK_ENV", "development").lower() != "production":
                    logger.debug(f"Loaded {env_var} from {file_env_var}={file_path}")
                else:
                    logger.debug(f"Loaded {env_var} from secret file")

    # Production check: fail fast if required secret is missing
    if required_in_production and not value:
        env_mode = os.getenv("AUTOPACK_ENV", "development").lower()
        if env_mode == "production":
            raise ConfigurationError(
                f"FATAL: {env_var} is required in production but not set. "
                f"Set {env_var} or {file_env_var or env_var + '_FILE'} environment variable."
            )

    return value


class Config:
    """Application configuration with environment variable validation.

    Validates all required environment variables at startup with clear error messages.
    Fails fast on misconfiguration instead of runtime errors.
    """

    def __init__(self):
        """Initialize configuration and validate all required environment variables."""
        self.validate()

    def validate(self):
        """Validate all required environment variables.

        Checks:
        - Required vars: DATABASE_URL, REDIS_URL, QDRANT_URL, ANTHROPIC_API_KEY
        - Optional with defaults: LOG_LEVEL, PORT

        Raises:
            ConfigError: If any required variables are missing or invalid.
        """
        errors = []

        # Database
        if not os.getenv("DATABASE_URL"):
            errors.append("DATABASE_URL is required")

        # Redis
        if not os.getenv("REDIS_URL"):
            errors.append("REDIS_URL is required")

        # Qdrant
        if not os.getenv("QDRANT_URL"):
            errors.append("QDRANT_URL is required")

        # LLM API keys
        if not os.getenv("ANTHROPIC_API_KEY"):
            errors.append("ANTHROPIC_API_KEY is required")

        # Optional with defaults
        self.log_level = os.getenv("LOG_LEVEL", "INFO")
        if self.log_level not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            errors.append(f"Invalid LOG_LEVEL: {self.log_level}")

        # Port validation
        port = os.getenv("PORT", "8000")
        try:
            self.port = int(port)
            if not (1 <= self.port <= 65535):
                errors.append(f"Invalid PORT: {port} (must be 1-65535)")
        except ValueError:
            errors.append(f"Invalid PORT: {port} (must be integer)")

        if errors:
            print("❌ Configuration errors detected:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            # Include error details in the exception message for better debugging
            error_details = "\n".join(errors)
            raise ConfigError(f"{len(errors)} configuration error(s):\n{error_details}")


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Operational mode: development | staging | production
    # - development: permissive (default) - auto-approval, lenient error handling
    # - staging: strict logging, auth required for sensitive ops
    # - production: full hardening - auth enforced, strict governance, no auto-approve unsafe paths
    autopack_env: str = Field(
        default="development",
        validation_alias=AliasChoices("AUTOPACK_ENV", "ENVIRONMENT"),
        description="Operational mode: development | staging | production",
    )

    # Default remains Postgres for production environments; most scripts/tests override via DATABASE_URL.
    database_url: str = "postgresql://autopack:autopack@localhost:5432/autopack"
    autonomous_runs_dir: str = ".autonomous_runs"

    # Git repository path (per v7 architect recommendation)
    # In Docker: /workspace (mounted volume)
    # Outside Docker: current directory
    repo_path: str = "/workspace"

    # Run defaults (per §9.1 of v7 playbook)
    run_token_cap: int = 5_000_000
    run_max_phases: int = 25
    run_max_duration_minutes: int = 120

    # IMP-COST-002: Per-phase budget controls
    # Default max tokens per phase (10% of run cap)
    phase_token_cap_default: int = Field(
        default=500_000,
        validation_alias=AliasChoices("AUTOPACK_PHASE_TOKEN_CAP", "PHASE_TOKEN_CAP_DEFAULT"),
        description="Default max tokens per phase (10% of run cap)",
    )

    # Phase type multipliers (some phases need more budget)
    # Format: "research:1.5,implementation:1.0,verification:0.5,audit:0.3"
    phase_token_cap_multipliers_str: str = Field(
        default="research:1.5,implementation:1.0,verification:0.5,audit:0.3",
        validation_alias=AliasChoices(
            "AUTOPACK_PHASE_TOKEN_MULTIPLIERS", "PHASE_TOKEN_CAP_MULTIPLIERS"
        ),
        description="Per-phase type budget multipliers (comma-separated key:value pairs)",
    )

    @property
    def phase_token_cap_multipliers(self) -> dict[str, float]:
        """Parse phase token cap multipliers from string config."""
        result = {}
        for pair in self.phase_token_cap_multipliers_str.split(","):
            if ":" in pair:
                key, value = pair.strip().split(":", 1)
                try:
                    result[key.strip()] = float(value.strip())
                except ValueError:
                    pass  # Skip invalid entries
        return result

    def get_phase_token_cap(self, phase_type: str) -> int:
        """Calculate token cap for specific phase type.

        Args:
            phase_type: Phase type (e.g., 'research', 'implementation', 'verification')

        Returns:
            Token cap for this phase type based on default and multipliers
        """
        multiplier = self.phase_token_cap_multipliers.get(phase_type, 1.0)
        return int(self.phase_token_cap_default * multiplier)

    # BUILD-145: Git-based executor rollback (opt-in, disabled by default)
    # When enabled, creates git savepoints before applying patches and rolls back on failure
    # Set via environment variable: AUTOPACK_ROLLBACK_ENABLED=true or EXECUTOR_ROLLBACK_ENABLED=true
    executor_rollback_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("AUTOPACK_ROLLBACK_ENABLED", "EXECUTOR_ROLLBACK_ENABLED"),
        description="Enable git-based rollback on patch application failure",
    )

    # BUILD-145 P2: Extended artifact-first substitution (opt-in, disabled by default)
    # When enabled, automatically pins run/tier/phase summaries as 'history pack' in context
    # and optionally substitutes large SOT docs with their summaries
    # Env vars supported:
    # - Canonical (pydantic default): ARTIFACT_HISTORY_PACK_ENABLED=true
    # - Legacy alias: AUTOPACK_ARTIFACT_HISTORY_PACK=true
    artifact_history_pack_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "ARTIFACT_HISTORY_PACK_ENABLED", "AUTOPACK_ARTIFACT_HISTORY_PACK"
        ),
    )

    # P0.4: DB safety guardrails - explicit opt-in for schema bootstrap
    # When enabled, allows create_all() to run (creates missing tables)
    # When disabled (default), app fails fast if schema is missing/outdated
    # This prevents accidental schema drift between SQLite/Postgres
    db_bootstrap_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("AUTOPACK_DB_BOOTSTRAP", "DB_BOOTSTRAP_ENABLED"),
        description="Allow automatic DB schema creation (disable in production)",
    )

    # Maximum number of recent phase summaries to include in history pack
    artifact_history_pack_max_phases: int = 5

    # Maximum number of recent tier summaries to include in history pack
    artifact_history_pack_max_tiers: int = 3

    # Enable substitution of large SOT docs (BUILD_HISTORY, BUILD_LOG) with summaries
    # Env vars supported:
    # - Canonical (pydantic default): ARTIFACT_SUBSTITUTE_SOT_DOCS=true
    # - Legacy alias: AUTOPACK_ARTIFACT_SUBSTITUTE_SOT_DOCS=true
    artifact_substitute_sot_docs: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "ARTIFACT_SUBSTITUTE_SOT_DOCS", "AUTOPACK_ARTIFACT_SUBSTITUTE_SOT_DOCS"
        ),
    )

    # Enable artifact substitution in additional safe contexts beyond read_only_context
    # When enabled, applies artifact-first loading to phase descriptions, tier summaries, etc.
    # Env vars supported:
    # - Canonical (pydantic default): ARTIFACT_EXTENDED_CONTEXTS_ENABLED=true
    # - Legacy alias: AUTOPACK_ARTIFACT_EXTENDED_CONTEXTS=true
    artifact_extended_contexts_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "ARTIFACT_EXTENDED_CONTEXTS_ENABLED", "AUTOPACK_ARTIFACT_EXTENDED_CONTEXTS"
        ),
    )

    # Embedding cache configuration
    # Maximum number of embedding API calls per phase (0 = unlimited)
    embedding_cache_max_calls_per_phase: int = 100

    # Context budget configuration (BUILD-145 P1.1)
    # Maximum tokens for context selection (rough estimate used by context_budgeter)
    # Default: 100k tokens (conservative estimate for read_only_context in phases)
    context_budget_tokens: int = 100_000

    # SOT (Source of Truth) Memory Indexing Configuration
    # Enable indexing of SOT ledgers (BUILD_HISTORY, DEBUG_LOG, ARCHITECTURE_DECISIONS) into vector memory
    autopack_enable_sot_memory_indexing: bool = False

    # Enable retrieval of SOT context at runtime (requires indexing to be enabled)
    autopack_sot_retrieval_enabled: bool = False

    # Maximum characters to return from SOT retrieval (to prevent prompt bloat)
    autopack_sot_retrieval_max_chars: int = 4000

    # Top-k chunks to retrieve from SOT collections
    autopack_sot_retrieval_top_k: int = 3

    # Maximum characters per chunk when indexing SOT files
    autopack_sot_chunk_max_chars: int = 1200

    # Overlap between chunks (for context continuity)
    autopack_sot_chunk_overlap_chars: int = 150

    # JWT Authentication configuration (BUILD-146 P12 Phase 5)
    # RS256 key pair for signing/verifying access tokens
    jwt_private_key: str = ""  # RSA private key in PEM format (env: JWT_PRIVATE_KEY)
    jwt_public_key: str = ""  # RSA public key in PEM format (env: JWT_PUBLIC_KEY)
    jwt_algorithm: str = "RS256"  # JWT signing algorithm (MUST be RS256; see CVE-2024-23342)
    jwt_issuer: str = "autopack"  # Token issuer
    jwt_audience: str = "autopack-api"  # Token audience
    access_token_expire_minutes: int = 1440  # Token expiration (24 hours)

    # PR-06 (R-06 G5): Artifact boundary hardening
    # Size cap for artifact file reads (bytes). 0 = unlimited (dev only).
    # Default: 1MB - prevents memory exhaustion from large artifacts.
    artifact_read_size_cap_bytes: int = Field(
        default=1_048_576,  # 1MB
        validation_alias=AliasChoices(
            "AUTOPACK_ARTIFACT_READ_SIZE_CAP", "ARTIFACT_READ_SIZE_CAP_BYTES"
        ),
        description="Max bytes to read from artifact files (0=unlimited, dev only)",
    )

    # Enable redaction of sensitive data in artifact reads (PII, credentials).
    # Default: False in dev, should be True in production for hosted usage.
    artifact_redaction_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("AUTOPACK_ARTIFACT_REDACTION", "ARTIFACT_REDACTION_ENABLED"),
        description="Enable PII/credential redaction in artifact reads",
    )

    # Configurable timeout values (IMP-033)
    health_check_timeout: float = Field(
        default=2.0,
        validation_alias=AliasChoices("AUTOPACK_HEALTH_CHECK_TIMEOUT", "HEALTH_CHECK_TIMEOUT"),
        description="Timeout for health check operations in seconds",
    )

    approval_check_interval: float = Field(
        default=60.0,
        validation_alias=AliasChoices(
            "AUTOPACK_APPROVAL_CHECK_INTERVAL", "APPROVAL_CHECK_INTERVAL"
        ),
        description="Interval between approval status checks in seconds",
    )

    db_operation_timeout: float = Field(
        default=30.0,
        validation_alias=AliasChoices("AUTOPACK_DB_OPERATION_TIMEOUT", "DB_OPERATION_TIMEOUT"),
        description="Timeout for database operations in seconds",
    )

    # PR-08 Phase 5: Outbound egress allowlist / SSRF guardrails
    # List of allowed external hosts for outbound HTTP calls (comma-separated)
    # Empty list (default) allows all hosts (permissive for private/internal use)
    # Example: "api.anthropic.com,api.openai.com,github.com"
    allowed_external_hosts: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("AUTOPACK_ALLOWED_EXTERNAL_HOSTS", "ALLOWED_EXTERNAL_HOSTS"),
        description="Comma-separated list of allowed external hosts (empty=all allowed)",
    )

    # IMP-SEC-001: Explicit bind address configuration
    # Prevents accidental exposure by defaulting to localhost-only binding
    autopack_bind_address: str = Field(
        default="127.0.0.1",
        validation_alias=AliasChoices("AUTOPACK_BIND_ADDRESS", "BIND_ADDRESS"),
        description="IP address to bind the API server to (default: 127.0.0.1)",
    )

    # IMP-SEC-001: Opt-in flag for non-local binding
    # Must be explicitly set to True to allow binding to non-local addresses
    autopack_allow_non_local: bool = Field(
        default=False,
        validation_alias=AliasChoices("AUTOPACK_ALLOW_NON_LOCAL", "ALLOW_NON_LOCAL_BIND"),
        description="Allow binding to non-local addresses (requires explicit opt-in)",
    )

    @model_validator(mode="before")
    @classmethod
    def parse_allowed_hosts(cls, values):
        """Parse allowed_external_hosts from comma-separated string or list."""
        if isinstance(values, dict):
            hosts = values.get("allowed_external_hosts")
            if isinstance(hosts, str):
                if hosts:
                    values["allowed_external_hosts"] = [
                        h.strip() for h in hosts.split(",") if h.strip()
                    ]
                else:
                    values["allowed_external_hosts"] = []
            elif hosts is None:
                values["allowed_external_hosts"] = []
        return values

    @model_validator(mode="after")
    def validate_bind_address_security(self) -> "Settings":
        """Validate bind address after all fields are set.

        Rejects non-local addresses unless autopack_allow_non_local=True.
        This is a security guardrail to prevent accidentally exposing the API
        to the network.
        """
        normalized = self.autopack_bind_address.strip().lower()

        if normalized in _LOCAL_ADDRESSES:
            return self

        if not self.autopack_allow_non_local:
            raise ValueError(
                f"Non-local bind address '{self.autopack_bind_address}' is not allowed. "
                f"Set AUTOPACK_ALLOW_NON_LOCAL=true to enable."
            )

        return self

    @model_validator(mode="after")
    def validate_jwt_algorithm(self) -> "Settings":
        """
        Validate security-critical configuration after initialization.

        CVE-2024-23342 Guardrail:
        - ECDSA signature malleability vulnerability in python-jose dependency (via ecdsa package)
        - Autopack exclusively uses RS256 (RSA-based) JWT signing
        - This validation enforces RS256-only and fails fast on any other algorithm
        - See docs/SECURITY_EXCEPTIONS.md for full CVE-2024-23342 rationale
        """
        if self.jwt_algorithm != "RS256":
            raise ValueError(
                f"FATAL: jwt_algorithm must be 'RS256' (got '{self.jwt_algorithm}'). "
                f"ECDSA algorithms (ES256/ES384/ES512) are not supported due to CVE-2024-23342. "
                f"See docs/SECURITY_EXCEPTIONS.md for details."
            )
        return self


settings = Settings()


def is_production() -> bool:
    """Check if running in production mode.

    Returns True if AUTOPACK_ENV is 'production'.
    Use this to enforce stricter behavior (auth, governance, etc.).
    """
    return settings.autopack_env.lower() == "production"


def is_development() -> bool:
    """Check if running in development mode.

    Returns True if AUTOPACK_ENV is 'development' (the default).
    """
    return settings.autopack_env.lower() == "development"


# Configuration version constant
CONFIG_VERSION = "1.0.0"


def get_config_version() -> str:
    """Return the current configuration version."""

    return CONFIG_VERSION


def get_database_url() -> str:
    """Get database URL from environment or config.

    Priority (PR-03 G4):
    1. DATABASE_URL_FILE (secret file path)
    2. DATABASE_URL environment variable
    3. settings.database_url from config

    P0: Normalize SQLite URLs to absolute paths to prevent
    different processes from using different files due to
    different working directories.
    """
    url = _get_secret(
        env_var="DATABASE_URL",
        file_env_var="DATABASE_URL_FILE",
        default=settings.database_url,
        required_in_production=True,  # DB is required in production
    )

    # Normalize relative SQLite paths to absolute (stable across subprocess cwd differences).
    # IMPORTANT: We resolve relative paths against the repo root derived from this file's location,
    # not Path.cwd(), because cwd can differ between scripts, uvicorn subprocesses, and terminals.
    if (
        isinstance(url, str)
        and url.startswith("sqlite:///")
        and not url.startswith("sqlite:///:memory:")
    ):
        db_path_str = url[len("sqlite:///") :]

        # Detect Windows drive absolute paths (e.g., C:\... or C:/...).
        is_windows_drive_abs = (
            len(db_path_str) >= 3
            and db_path_str[1] == ":"
            and (db_path_str[2] == "\\" or db_path_str[2] == "/")
        )

        db_path = Path(db_path_str)
        if not db_path.is_absolute() and not is_windows_drive_abs:
            # src/autopack/config.py -> src/autopack -> src -> repo root
            repo_root = Path(__file__).resolve().parents[2]
            db_path = (repo_root / db_path).resolve()
        else:
            # Still normalize slashes and resolve for consistency.
            db_path = db_path.resolve()

        # SQLAlchemy URLs want forward slashes even on Windows (sqlite:///C:/path/to.db).
        url = f"sqlite:///{db_path.as_posix()}"

    return url


def get_jwt_private_key() -> str:
    """Get JWT private key from environment or file.

    Priority (PR-03 G4):
    1. JWT_PRIVATE_KEY_FILE (secret file path)
    2. JWT_PRIVATE_KEY environment variable
    3. settings.jwt_private_key

    In production, logs a warning if keys are missing (JWT auth won't work).
    """
    key = _get_secret(
        env_var="JWT_PRIVATE_KEY",
        file_env_var="JWT_PRIVATE_KEY_FILE",
        default=settings.jwt_private_key,
        required_in_production=False,  # JWT is optional (X-API-Key is primary)
    )
    if not key and is_production():
        logger.warning(
            "JWT_PRIVATE_KEY not set in production. "
            "JWT authentication will fail. Set JWT_PRIVATE_KEY or JWT_PRIVATE_KEY_FILE."
        )
    return key


def get_jwt_public_key() -> str:
    """Get JWT public key from environment or file.

    Priority (PR-03 G4):
    1. JWT_PUBLIC_KEY_FILE (secret file path)
    2. JWT_PUBLIC_KEY environment variable
    3. settings.jwt_public_key

    In production, logs a warning if keys are missing (JWT verification won't work).
    """
    key = _get_secret(
        env_var="JWT_PUBLIC_KEY",
        file_env_var="JWT_PUBLIC_KEY_FILE",
        default=settings.jwt_public_key,
        required_in_production=False,  # JWT is optional (X-API-Key is primary)
    )
    if not key and is_production():
        logger.warning(
            "JWT_PUBLIC_KEY not set in production. "
            "JWT verification will fail. Set JWT_PUBLIC_KEY or JWT_PUBLIC_KEY_FILE."
        )
    return key


def get_api_key() -> str:
    """Get API key from environment or file.

    Priority (PR-03 G4):
    1. AUTOPACK_API_KEY_FILE (secret file path)
    2. AUTOPACK_API_KEY environment variable
    3. Empty string (no auth in dev mode)

    In production, this is required and the lifespan check will fail if missing.
    """
    return _get_secret(
        env_var="AUTOPACK_API_KEY",
        file_env_var="AUTOPACK_API_KEY_FILE",
        default="",
        required_in_production=True,  # API key required in production
    )
