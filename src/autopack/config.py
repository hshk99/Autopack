"""Configuration module for Autopack settings.

This module is intentionally small and stable. Several subsystems import it at
startup (DB, executor, API). Accidental deletion breaks telemetry tooling and
scripts that rely on `DATABASE_URL` resolution.
"""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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


settings = Settings()


# Configuration version constant
CONFIG_VERSION = "1.0.0"


def get_config_version() -> str:
    """Return the current configuration version."""

    return CONFIG_VERSION


def get_database_url() -> str:
    """Get database URL from environment or config.

    Priority:
    1. DATABASE_URL environment variable
    2. settings.database_url from config

    P0: Normalize SQLite URLs to absolute paths to prevent
    different processes from using different files due to
    different working directories.
    """
    from pathlib import Path

    url = os.getenv("DATABASE_URL", settings.database_url)

    # Normalize relative SQLite paths to absolute (stable across subprocess cwd differences).
    # IMPORTANT: We resolve relative paths against the repo root derived from this file's location,
    # not Path.cwd(), because cwd can differ between scripts, uvicorn subprocesses, and terminals.
    if isinstance(url, str) and url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
        db_path_str = url[len("sqlite:///"):]

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


