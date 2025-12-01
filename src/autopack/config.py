"""Configuration for Autopack Supervisor"""

"""Configuration module for Autopack settings - test task"""

"""Configuration module for Autopack settings - test task"""

"""Configuration module for Autopack settings - test task"""

"""Configuration module for Autopack settings - test task"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # Allow extra fields from .env without validation errors


settings = Settings()
