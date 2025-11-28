"""
Core configuration settings
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "FileOrganizer"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "sqlite:///./fileorganizer.db"

    # OpenAI
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # OCR
    TESSERACT_CMD: Optional[str] = None  # Auto-detect if None

    # File processing
    MAX_FILE_SIZE_MB: int = 50
    SUPPORTED_FORMATS: list = [".pdf", ".png", ".jpg", ".jpeg", ".docx", ".xlsx"]

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
