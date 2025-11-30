"""
File validation utilities for batch upload.

This module provides functions to validate uploaded files including
type checking, size limits, and content validation.
"""

import logging
from typing import Dict, Set

import magic


logger = logging.getLogger(__name__)


def validate_file(
    content: bytes,
    filename: str,
    max_size: int,
    allowed_types: Set[str],
) -> Dict[str, any]:
    """
    Validate an uploaded file.

    Args:
        content: File content as bytes
        filename: Original filename
        max_size: Maximum allowed file size in bytes
        allowed_types: Set of allowed MIME types

    Returns:
        Dictionary with validation result:
        {
            "valid": bool,
            "mime_type": str or None,
            "error": str or None
        }
    """
    # Check file size
    if len(content) == 0:
        return {
            "valid": False,
            "mime_type": None,
            "error": "File is empty",
        }

    if len(content) > max_size:
        size_mb = len(content) / (1024 * 1024)
        max_mb = max_size / (1024 * 1024)
        return {
            "valid": False,
            "mime_type": None,
            "error": f"File size ({size_mb:.2f}MB) exceeds maximum ({max_mb:.2f}MB)",
        }

    # Detect MIME type
    try:
        mime = magic.Magic(mime=True)
        mime_type = mime.from_buffer(content)
    except Exception as e:
        logger.error(f"Error detecting MIME type for {filename}: {e}")
        return {
            "valid": False,
            "mime_type": None,
            "error": "Could not determine file type",
        }

    # Check if MIME type is allowed
    if mime_type not in allowed_types:
        return {
            "valid": False,
            "mime_type": mime_type,
            "error": f"File type '{mime_type}' is not supported",
        }

    # Additional content validation for images
    if mime_type.startswith("image/"):
        if not validate_image_content(content):
            return {
                "valid": False,
                "mime_type": mime_type,
                "error": "Invalid or corrupted image file",
            }

    return {
        "valid": True,
        "mime_type": mime_type,
        "error": None,
    }


def validate_image_content(content: bytes) -> bool:
    """
    Validate image file content.

    Args:
        content: Image file content as bytes

    Returns:
        True if image is valid, False otherwise
    """
    try:
        from PIL import Image
        import io

        image = Image.open(io.BytesIO(content))
        image.verify()
        return True
    except Exception as e:
        logger.warning(f"Image validation failed: {e}")
        return False
