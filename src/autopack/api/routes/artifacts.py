"""Artifacts router for artifact browsing endpoints.

Extracted from main.py as part of PR-API-3g.

Endpoints:
- GET /runs/{run_id}/artifacts/index - Get artifact file index for a run
- GET /runs/{run_id}/artifacts/file - Get artifact file content
- GET /runs/{run_id}/browser/artifacts - Get browser-specific artifacts
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from autopack import models
from autopack.api.deps import verify_read_access
from autopack.config import settings
from autopack.database import get_db
from autopack.file_layout import RunFileLayout

logger = logging.getLogger(__name__)

router = APIRouter(tags=["artifacts"])


@router.get("/runs/{run_id}/artifacts/index")
async def get_artifacts_index(
    run_id: str,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
) -> Dict[str, Any]:
    """Get artifact file index for a run (GAP-8.10.1 Artifact Browser).

    Returns list of artifact files with metadata.
    Auth: Required in production; dev opt-in via AUTOPACK_PUBLIC_READ=1.
    """
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    file_layout = RunFileLayout(run_id)
    artifacts = []
    total_size = 0

    if file_layout.base_dir.exists():
        for file_path in file_layout.base_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(file_layout.base_dir)
                file_size = file_path.stat().st_size
                total_size += file_size
                artifacts.append(
                    {
                        "path": str(rel_path),
                        "size_bytes": file_size,
                        "modified_at": datetime.fromtimestamp(
                            file_path.stat().st_mtime, tz=timezone.utc
                        ).isoformat(),
                    }
                )

    return {
        "run_id": run_id,
        "artifacts": artifacts,
        "total_size_bytes": total_size,
    }


@router.get("/runs/{run_id}/artifacts/file")
async def get_artifact_file(
    run_id: str,
    path: str,
    redact: bool = False,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
):
    """Get artifact file content (GAP-8.10.1 Artifact Browser).

    PR-06 (R-06 G5): Artifact boundary hardening.

    Security: Path traversal attacks are blocked.
    Auth: Required in production; dev opt-in via AUTOPACK_PUBLIC_READ=1.

    Query params:
        redact: Enable PII/credential redaction (default: use AUTOPACK_ARTIFACT_REDACTION setting)

    Response headers:
        X-Artifact-Truncated: "true" if content was truncated due to size cap
        X-Artifact-Redacted: "true" if content was redacted
        X-Artifact-Original-Size: Original file size in bytes
    """
    from autopack.artifacts.redaction import ArtifactRedactor

    # URL-decode path to catch encoded traversal attempts (e.g., %2e%2e = ..)
    decoded_path = unquote(path)

    # Security checks FIRST (defense in depth) - before any DB lookup
    if ".." in decoded_path or "\\.." in decoded_path:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")
    if decoded_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Absolute paths not allowed")
    if len(decoded_path) > 1 and decoded_path[1] == ":":
        raise HTTPException(status_code=400, detail="Windows drive letters not allowed")

    # Now check run exists
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    file_layout = RunFileLayout(run_id)
    file_path = file_layout.base_dir / decoded_path

    # Additional check: ensure resolved path is within base_dir
    try:
        file_path.resolve().relative_to(file_layout.base_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    # PR-06: Get file size for boundary enforcement
    file_size = file_path.stat().st_size
    size_cap = settings.artifact_read_size_cap_bytes
    truncated = False
    redacted = False
    redaction_count = 0

    # Read content with size cap
    if size_cap > 0 and file_size > size_cap:
        # Truncate at size cap
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(size_cap)
        content += f"\n\n[TRUNCATED: File size {file_size} bytes exceeds cap of {size_cap} bytes]"
        truncated = True
    else:
        content = file_path.read_text(encoding="utf-8", errors="replace")

    # PR-06: Apply redaction if enabled (via query param or config)
    should_redact = redact or settings.artifact_redaction_enabled
    if should_redact:
        redactor = ArtifactRedactor()
        content, redaction_count = redactor.redact_text(content)
        redacted = redaction_count > 0

    # Build response with metadata headers
    headers = {
        "X-Artifact-Original-Size": str(file_size),
        "X-Artifact-Truncated": "true" if truncated else "false",
        "X-Artifact-Redacted": "true" if redacted else "false",
    }
    if redacted:
        headers["X-Artifact-Redaction-Count"] = str(redaction_count)

    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers=headers,
    )


@router.get("/runs/{run_id}/browser/artifacts")
async def get_browser_artifacts(
    run_id: str,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
) -> Dict[str, Any]:
    """Get browser-specific artifacts for a run (GAP-8.10.3 Browser Artifacts).

    Returns screenshots and other browser-related artifacts.
    Auth: Required in production; dev opt-in via AUTOPACK_PUBLIC_READ=1.
    """
    run = db.query(models.Run).filter(models.Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    file_layout = RunFileLayout(run_id)
    browser_artifacts = []

    # Look for browser-related files (screenshots, etc.)
    browser_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".html"}
    browser_patterns = ["screenshot", "browser", "page", "capture"]

    if file_layout.base_dir.exists():
        for file_path in file_layout.base_dir.rglob("*"):
            if file_path.is_file():
                # Check if it's a browser-related file
                is_browser_file = file_path.suffix.lower() in browser_extensions or any(
                    pattern in file_path.name.lower() for pattern in browser_patterns
                )
                if is_browser_file:
                    rel_path = file_path.relative_to(file_layout.base_dir)
                    browser_artifacts.append(
                        {
                            "path": str(rel_path),
                            "type": (
                                "screenshot"
                                if file_path.suffix.lower()
                                in {".png", ".jpg", ".jpeg", ".gif", ".webp"}
                                else "html"
                            ),
                            "size_bytes": file_path.stat().st_size,
                            "modified_at": datetime.fromtimestamp(
                                file_path.stat().st_mtime, tz=timezone.utc
                            ).isoformat(),
                        }
                    )

    return {
        "run_id": run_id,
        "artifacts": browser_artifacts,
        "total_count": len(browser_artifacts),
    }
