"""
Security configuration for production
"""
from app.core.config import settings


# CORS allowed origins (production)
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# File upload security
MAX_FILENAME_LENGTH = 255
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".docx", ".xlsx"}

# Rate limiting (requests per minute)
RATE_LIMIT_UPLOADS = 10
RATE_LIMIT_CLASSIFICATION = 20
RATE_LIMIT_EXPORT = 5


def validate_filename(filename: str) -> bool:
    """Validate uploaded filename"""
    if len(filename) > MAX_FILENAME_LENGTH:
        return False

    # Check for path traversal attempts
    if ".." in filename or "/" in filename or "\\" in filename:
        return False

    return True


def sanitize_filename(filename: str) -> str:
    """Sanitize filename for security"""
    # Remove path components
    filename = filename.replace("..", "").replace("/", "_").replace("\\", "_")

    # Limit length
    if len(filename) > MAX_FILENAME_LENGTH:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        filename = name[:MAX_FILENAME_LENGTH - len(ext) - 1] + "." + ext

    return filename
