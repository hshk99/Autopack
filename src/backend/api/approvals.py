"""Approval workflow API endpoints for Telegram integration."""

import os
import logging
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory approval state (in production, use Redis or database)
# Format: {phase_id: {"status": "pending"|"approved"|"rejected", "timestamp": ISO datetime}}
approval_state: Dict[str, Dict] = {}


class ApprovalRequest(BaseModel):
    """Request for approval."""
    phase_id: str
    deletion_info: Dict
    run_id: str = ""
    context: str = ""


class ApprovalDecision(BaseModel):
    """Approval decision."""
    phase_id: str
    decision: str  # "approved" | "rejected"


@router.post("/approval/request")
async def request_approval(request: ApprovalRequest):
    """
    Request approval for a risky phase change.

    This endpoint is called by autonomous_executor.py when quality gate
    blocks a phase due to large deletions or other high-risk changes.

    Flow:
    1. Executor calls this endpoint
    2. We send Telegram notification
    3. User taps Approve/Reject button
    4. Telegram webhook calls /approval/approve or /approval/reject
    5. Executor polls /approval/status to get decision
    """
    from autopack.notifications.telegram_notifier import TelegramNotifier

    phase_id = request.phase_id

    # Initialize approval state
    approval_state[phase_id] = {
        "status": "pending",
        "timestamp": datetime.utcnow().isoformat(),
        "deletion_info": request.deletion_info,
        "run_id": request.run_id,
        "context": request.context,
    }

    # Send Telegram notification
    notifier = TelegramNotifier()

    if not notifier.is_configured():
        logger.warning(f"[Approval] Telegram not configured - auto-rejecting {phase_id}")
        approval_state[phase_id]["status"] = "rejected"
        approval_state[phase_id]["reason"] = "Telegram not configured"
        return {
            "status": "rejected",
            "reason": "Telegram notifications not configured",
            "phase_id": phase_id,
        }

    success = notifier.send_approval_request(
        phase_id=phase_id,
        deletion_info=request.deletion_info,
        run_id=request.run_id,
        context=request.context,
    )

    if not success:
        logger.error(f"[Approval] Failed to send Telegram notification for {phase_id}")
        approval_state[phase_id]["status"] = "rejected"
        approval_state[phase_id]["reason"] = "Failed to send notification"
        return {
            "status": "rejected",
            "reason": "Failed to send Telegram notification",
            "phase_id": phase_id,
        }

    logger.info(f"[Approval] Notification sent for {phase_id}, awaiting user decision")
    return {
        "status": "pending",
        "message": "Approval request sent to Telegram",
        "phase_id": phase_id,
    }


@router.get("/approval/status/{phase_id}")
async def get_approval_status(phase_id: str):
    """
    Get current approval status for a phase.

    Executor polls this endpoint to check if user has approved/rejected.
    """
    if phase_id not in approval_state:
        raise HTTPException(status_code=404, detail=f"No approval request found for {phase_id}")

    state = approval_state[phase_id]
    return {
        "phase_id": phase_id,
        "status": state["status"],
        "timestamp": state["timestamp"],
    }


@router.post("/approval/approve/{phase_id}")
async def approve_phase(phase_id: str):
    """
    Approve a phase (called by Telegram webhook or manual API).

    When user taps "Approve" button in Telegram, webhook calls this endpoint.
    """
    if phase_id not in approval_state:
        raise HTTPException(status_code=404, detail=f"No approval request found for {phase_id}")

    approval_state[phase_id]["status"] = "approved"
    approval_state[phase_id]["approved_at"] = datetime.utcnow().isoformat()

    # Send confirmation to Telegram
    from autopack.notifications.telegram_notifier import TelegramNotifier
    notifier = TelegramNotifier()
    notifier.send_completion_notice(
        phase_id=phase_id,
        status="approved",
        message="Phase has been approved and will proceed."
    )

    logger.info(f"[Approval] Phase {phase_id} APPROVED")
    return {
        "status": "approved",
        "phase_id": phase_id,
        "message": "Phase approved successfully",
    }


@router.post("/approval/reject/{phase_id}")
async def reject_phase(phase_id: str):
    """
    Reject a phase (called by Telegram webhook or manual API).

    When user taps "Reject" button in Telegram, webhook calls this endpoint.
    """
    if phase_id not in approval_state:
        raise HTTPException(status_code=404, detail=f"No approval request found for {phase_id}")

    approval_state[phase_id]["status"] = "rejected"
    approval_state[phase_id]["rejected_at"] = datetime.utcnow().isoformat()

    # Send confirmation to Telegram
    from autopack.notifications.telegram_notifier import TelegramNotifier
    notifier = TelegramNotifier()
    notifier.send_completion_notice(
        phase_id=phase_id,
        status="rejected",
        message="Phase has been rejected and will not proceed."
    )

    logger.info(f"[Approval] Phase {phase_id} REJECTED")
    return {
        "status": "rejected",
        "phase_id": phase_id,
        "message": "Phase rejected successfully",
    }


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """
    Receive Telegram webhook callbacks.

    When user taps Approve/Reject buttons, Telegram POSTs to this endpoint.

    Setup:
        1. Set webhook URL: https://api.telegram.org/bot{TOKEN}/setWebhook
        2. Body: {"url": "https://harrybot.ngrok.app/telegram/webhook"}
    """
    try:
        data = await request.json()
        logger.debug(f"[Telegram] Webhook received: {data}")

        # Handle callback_query (button taps)
        if "callback_query" in data:
            callback = data["callback_query"]
            callback_data = callback.get("data", "")

            # Parse callback_data: "approve:phase_id" or "reject:phase_id"
            if ":" in callback_data:
                action, phase_id = callback_data.split(":", 1)

                if action == "approve":
                    await approve_phase(phase_id)

                    # Answer callback to remove loading state
                    await _answer_callback(callback["id"], "✅ Approved!")

                elif action == "reject":
                    await reject_phase(phase_id)

                    # Answer callback to remove loading state
                    await _answer_callback(callback["id"], "❌ Rejected!")

                else:
                    logger.warning(f"[Telegram] Unknown action: {action}")

        return {"ok": True}

    except Exception as e:
        logger.error(f"[Telegram] Webhook error: {e}")
        return {"ok": False, "error": str(e)}


async def _answer_callback(callback_query_id: str, text: str):
    """Answer Telegram callback query to remove loading state."""
    import requests

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return

    url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"

    try:
        requests.post(url, json={
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": False,
        }, timeout=5)
    except Exception as e:
        logger.error(f"[Telegram] Failed to answer callback: {e}")
