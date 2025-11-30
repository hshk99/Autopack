"""
Application configuration management.

Handles environment-specific settings and provides different configurations
for development, testing, and production environments.
"""
import os
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings with environment variable support.
    
    Attributes:
        testing: Whether the application is running in test mode
        database_url: Database connection string
        redis_url: Redis connection string (optional)
        celery_broker_url: Celery broker URL (optional)
        debug: Enable debug mode
    """
    
    testing: bool = False
    database_url: str = "postgresql://user:password@localhost/autopack"
    redis_url: Optional[str] = None
    celery_broker_url: Optional[str] = None
    debug: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Allow extra fields from .env without validation errors


def get_settings() -> Settings:
    """
    Get application settings based on environment.

    Returns:
        Settings: Configured settings instance
    """
    # Check if we're in testing mode
    if os.getenv("TESTING") == "1":
        return Settings(
            testing=True,
            database_url="sqlite:///:memory:",
            redis_url=None,
            celery_broker_url=None,
            debug=True,
        )

    return Settings()


# Global settings instance for imports
settings = get_settings()
