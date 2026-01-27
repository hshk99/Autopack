"""File operations endpoints.

Extracted from main.py as part of PR-API-3b.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request

from autopack.api.deps import verify_api_key
from autopack.config import settings

logger = logging.getLogger(__name__)

# IMP-REL-004: Max iteration limits for file reading loops
# 100000 chunks * 64KB = ~6.4GB max file size before safety limit
MAX_FILE_CHUNKS = 100000

router = APIRouter(prefix="/files", tags=["files"])


@router.post("/upload", dependencies=[Depends(verify_api_key)])
async def upload_file(request: Request):
    """
    Upload a file to the server.

    This endpoint accepts multipart/form-data uploads. The file is saved
    to the uploads directory with a unique filename.

    Args:
        request: FastAPI request object containing the file

    Returns:
        JSON with upload status and file metadata (relative path only for security)

    Example:
        ```bash
        curl -X POST http://localhost:8000/files/upload \\
          -F "file=@myfile.txt"
        ```

    Note:
        - Maximum file size is controlled by nginx (50MB default)
        - Requires API key authentication in production mode
        - Uses streaming to avoid loading entire file into memory
    """
    import uuid

    # Get form data
    form = await request.form()
    file = form.get("file")

    if not file or not hasattr(file, "filename"):
        raise HTTPException(status_code=400, detail="No file provided")

    # Generate unique filename to prevent collisions
    file_ext = Path(file.filename).suffix if file.filename else ""
    unique_filename = f"{uuid.uuid4().hex}{file_ext}"

    # Ensure uploads directory exists
    uploads_dir = Path(settings.autonomous_runs_dir) / "_uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    file_path = uploads_dir / unique_filename

    try:
        # Stream file content in chunks to avoid loading entire file into memory
        # This is critical for large uploads to prevent OOM issues
        CHUNK_SIZE = 64 * 1024  # 64KB chunks
        total_size = 0

        with open(file_path, "wb") as f:
            # IMP-REL-004: Add iteration counter to prevent unbounded loops
            chunk_count = 0
            while chunk_count < MAX_FILE_CHUNKS:
                chunk_count += 1
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
                total_size += len(chunk)
            else:
                # Max chunks reached - log warning and raise error
                logger.warning(
                    f"File upload exceeded max chunks ({MAX_FILE_CHUNKS}), "
                    "possible infinite loop or extremely large file"
                )
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large or corrupted (exceeded {MAX_FILE_CHUNKS} chunks)",
                )

        # Return relative path only (security: never expose absolute filesystem paths)
        relative_path = f"_uploads/{unique_filename}"

        return {
            "status": "success",
            "filename": file.filename,
            "stored_as": unique_filename,
            "size": total_size,
            "relative_path": relative_path,
        }
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        # Clean up partial file on failure
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass
        raise HTTPException(status_code=500, detail="Upload failed")
