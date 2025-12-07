"""
Application configuration management.
"""
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # Application
    app_name: str = "Autopack API"
    debug: bool = False
    
    # Database
    database_url: str = Field(
        default="postgresql://autopack:autopack@localhost:5432/autopack",
        description="PostgreSQL database connection URL"
    )
    
    # JWT Authentication
    jwt_private_key: str = Field(
        default="",
        description="PEM-encoded private key for JWT signing (RS256)",
    )
    jwt_public_key: str = Field(
        default="",
        description="PEM-encoded public key for JWT verification",
    )
    jwt_algorithm: str = Field(
        default="RS256",
        description="JWT signing algorithm",
    )
    jwt_issuer: str = Field(
        default="autopack-backend",
        description="JWT issuer (iss claim)",
    )
    jwt_audience: str = Field(
        default="autopack-clients",
        description="JWT audience (aud claim)",
    )
    access_token_expire_minutes: int = 30
    
    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    
settings = Settings()
