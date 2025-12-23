"""File validation service.

Provides validation for uploaded files including type checking,
size limits, and content validation.
"""
from PIL import Image
import magic
import os
from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class FileValidator:
    """Validates uploaded files."""
    
    # Maximum file size (10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024
    
    # Allowed MIME types
    ALLOWED_MIME_TYPES = {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "application/pdf",
        "text/plain",
        "application/json",
    }
    
    def __init__(self):
        """Initialize file validator."""
        self.mime = magic.Magic(mime=True)
    
    def validate_file(self, file_path: Path) -> Tuple[bool, Optional[str]]:
        """Validate a file.
        
        Args:
            file_path: Path to file to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check file exists
        if not file_path.exists():
            return False, "File does not exist"
        
        # Check file size
        file_size = os.path.getsize(file_path)
        if file_size > self.MAX_FILE_SIZE:
            return False, f"File size {file_size} exceeds maximum {self.MAX_FILE_SIZE}"
        
        # Check MIME type
        try:
            mime_type = self.mime.from_file(str(file_path))
            if mime_type not in self.ALLOWED_MIME_TYPES:
                return False, f"File type {mime_type} not allowed"
        except Exception as e:
            logger.error(f"Failed to detect MIME type: {e}")
            return False, "Failed to detect file type"
        
        # Additional validation for images
        if mime_type.startswith("image/"):
            try:
                with Image.open(file_path) as img:
                    img.verify()
            except Exception as e:
                logger.error(f"Image validation failed: {e}")
                return False, "Invalid image file"
        
        return True, None
    
    def get_file_info(self, file_path: Path) -> dict:
        """Get information about a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            Dictionary with file information
        """
        info = {
            "path": str(file_path),
            "size": os.path.getsize(file_path),
            "mime_type": None,
            "is_valid": False,
        }
        
        try:
            info["mime_type"] = self.mime.from_file(str(file_path))
            is_valid, _ = self.validate_file(file_path)
            info["is_valid"] = is_valid
        except Exception as e:
            logger.error(f"Failed to get file info: {e}")
        
        return info
