"""Configuration module for Autopack settings"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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

settings = Settings()


# Configuration version constant
CONFIG_VERSION = "1.0.0"


def get_config_version() -> str:
    """Return the current configuration version.

    This utility function provides a simple way to query the configuration
    version for testing and validation purposes.

    Returns:
        str: The current configuration version (e.g., "1.0.0")

    Example:
        >>> from autopack.config import get_config_version
        >>> version = get_config_version()
        >>> print(f"Config version: {version}")
        Config version: 1.0.0
    """
    return CONFIG_VERSION


def get_database_url() -> str:
    """Get database URL from environment or config.

    Priority:
    1. DATABASE_URL environment variable
    2. settings.database_url from config

    Returns:
        str: Database URL for SQLAlchemy

    Example:
        >>> from autopack.config import get_database_url
        >>> db_url = get_database_url()
        >>> print(db_url)
        sqlite:///autopack.db
    """
    import os
    return os.getenv("DATABASE_URL", settings.database_url)
