"""
Application configuration management.
"""
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "Autopack API"
    debug: bool = False
    
    # Database
    database_url: str = Field(
        default="postgresql://autopack:autopack@localhost:5432/autopack",
        description="PostgreSQL database connection URL"
    )
    
    # JWT Authentication
    secret_key: str = Field(
        default="your-secret-key-change-in-production",
        description="Secret key for JWT token generation"
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    
    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Allow extra fields from .env without validation errors


settings = Settings()
