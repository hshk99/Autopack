"""
I/O utilities for tidy system.

Provides atomic file writing and other I/O helpers with error handling,
retry logic, and platform-specific tolerance (Windows antivirus/indexing).
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def atomic_write(
    path: Path,
    content: str,
    encoding: str = "utf-8",
    max_retries: int = 3,
    retry_delay_ms: int = 100,
) -> None:
    """
    Write file atomically using temp-file + replace pattern.

    Ensures file is either fully written or not written at all (no partial writes).
    Includes retry logic for transient failures (antivirus, indexing, etc.).

    Args:
        path: Target file path
        content: String content to write
        encoding: Text encoding (default: utf-8)
        max_retries: Maximum retry attempts for replace operation
        retry_delay_ms: Delay between retries in milliseconds

    Raises:
        OSError: If write fails after all retries
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temporary file first
    tmp_path = path.with_suffix(path.suffix + ".tmp")

    try:
        tmp_path.write_text(content, encoding=encoding)
    except OSError as e:
        # Clean up partial temp file
        tmp_path.unlink(missing_ok=True)
        raise OSError(f"Failed to write temp file {tmp_path}: {e}") from e

    # Atomic replace with retry (tolerance for antivirus/indexing locks)
    for attempt in range(max_retries):
        try:
            tmp_path.replace(path)
            logger.debug(f"[IO] Atomic write successful: {path}")
            return

        except OSError as e:
            if attempt < max_retries - 1:
                delay_seconds = (retry_delay_ms / 1000.0) * (attempt + 1)
                logger.debug(
                    f"[IO] Replace attempt {attempt + 1}/{max_retries} failed for {path}: {e}, "
                    f"retrying in {delay_seconds:.2f}s..."
                )
                time.sleep(delay_seconds)
            else:
                # Clean up temp file on final failure
                tmp_path.unlink(missing_ok=True)
                raise OSError(
                    f"Failed to atomically replace {path} after {max_retries} attempts: {e}"
                ) from e


def atomic_write_json(
    path: Path,
    data: Dict[str, Any],
    indent: Optional[int] = 2,
    encoding: str = "utf-8",
    max_retries: int = 3,
    retry_delay_ms: int = 100,
) -> None:
    """
    Write JSON file atomically.

    Wrapper around atomic_write for JSON serialization with consistent formatting.

    Args:
        path: Target file path
        data: Dictionary to serialize as JSON
        indent: JSON indentation (default: 2, None for compact)
        encoding: Text encoding (default: utf-8)
        max_retries: Maximum retry attempts for replace operation
        retry_delay_ms: Delay between retries in milliseconds

    Raises:
        OSError: If write fails after all retries
        TypeError: If data is not JSON-serializable
    """
    try:
        content = json.dumps(data, indent=indent)
    except (TypeError, ValueError) as e:
        raise TypeError(f"Failed to serialize data to JSON for {path}: {e}") from e

    atomic_write(
        path=path,
        content=content,
        encoding=encoding,
        max_retries=max_retries,
        retry_delay_ms=retry_delay_ms,
    )


def safe_read_json(
    path: Path, default: Optional[Dict[str, Any]] = None, encoding: str = "utf-8"
) -> Dict[str, Any]:
    """
    Read JSON file with fallback to default on failure.

    Args:
        path: File path to read
        default: Default value if file missing or invalid (default: {})
        encoding: Text encoding (default: utf-8)

    Returns:
        Parsed JSON dict or default value
    """
    if default is None:
        default = {}

    try:
        content = path.read_text(encoding=encoding)
        return json.loads(content)
    except FileNotFoundError:
        logger.debug(f"[IO] File not found, using default: {path}")
        return default
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"[IO] Failed to read JSON from {path}: {e}, using default")
        return default
