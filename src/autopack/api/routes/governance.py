"""Governance endpoints.

Extracted from main.py as part of PR-API-3e.
BUILD-127 Phase 2: Governance Request Endpoints.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from autopack.api.deps import verify_api_key, verify_read_access
from autopack.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/governance", tags=["governance"])


@router.get("/pending")
async def get_pending_governance_requests(
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
):
    """Get all pending governance requests (BUILD-127 Phase 2).

    Returns:
        JSON response with pending governance requests
    """
    try:
        from autopack.governance_requests import get_pending_requests

        pending = get_pending_requests(db)

        return {"count": len(pending), "pending_requests": [req.to_dict() for req in pending]}

    except Exception as e:
        logger.error(f"[GOVERNANCE] Error fetching pending requests: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch pending requests")


@router.post("/approve/{request_id}", dependencies=[Depends(verify_api_key)])
async def approve_governance_request(
    request_id: str, approved: bool = True, user_id: str = "human", db: Session = Depends(get_db)
):
    """Approve or deny a governance request (BUILD-127 Phase 2).

    Args:
        request_id: Governance request ID
        approved: True to approve, False to deny
        user_id: ID of approving user

    Returns:
        JSON response with approval status
    """
    try:
        from autopack.governance_requests import approve_request, deny_request

        if approved:
            success = approve_request(db, request_id, approved_by=user_id)
            status = "approved"
        else:
            success = deny_request(db, request_id, denied_by=user_id)
            status = "denied"

        if success:
            return {
                "status": status,
                "request_id": request_id,
                "message": f"Governance request {status}",
            }
        else:
            raise HTTPException(status_code=404, detail="Governance request not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GOVERNANCE] Error updating request {request_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update request")
