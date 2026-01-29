"""Approval and Telegram webhook endpoints.

Extracted from main.py as part of PR-API-3f.

Includes:
- Approval request endpoints (BUILD-117)
- Telegram webhook handlers for approval buttons
- Storage optimizer Telegram callbacks (BUILD-150 Phase 3)
"""

import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from autopack import models
from autopack.api.deps import limiter, verify_api_key, verify_read_access
from autopack.database import get_db
from autopack.notifications.telegram_notifier import answer_telegram_callback
from autopack.notifications.telegram_webhook_security import \
    verify_telegram_webhook as verify_telegram_webhook_crypto

logger = logging.getLogger(__name__)

router = APIRouter(tags=["approvals"])


@router.post("/approval/request", dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def request_approval(request: Request, db: Session = Depends(get_db)):
    """Handle approval requests from BUILD-113 autonomous executor.

    Rate limited to 10 requests/minute to prevent approval spam and DoS attacks.

    BUILD-117 Enhanced Implementation with:
    - Telegram notifications with approve/reject buttons
    - Database audit trail for all approval requests
    - Approval timeout mechanism (default: 15 minutes)
    - Dashboard UI integration

    Expected payload:
    {
        "phase_id": str,
        "run_id": str,
        "context": str,  # "build113_risky_decision", "build113_ambiguous_decision", or "troubleshoot"
        "decision_info": dict  # Decision metadata
        "deletion_info": dict  # (optional) For deletion approvals
    }

    Returns:
    {
        "status": "approved" | "rejected" | "pending",
        "reason": str (optional),
        "approval_id": int (if stored in database)
    }
    """
    try:
        from datetime import timedelta

        from autopack.notifications.telegram_notifier import TelegramNotifier

        data = await request.json()
        phase_id = data.get("phase_id")
        run_id = data.get("run_id")
        context = data.get("context", "unknown")
        decision_info = data.get("decision_info", {})
        deletion_info = data.get("deletion_info")

        # Sanitize user-controlled values for logging (prevent log injection)
        def _sanitize_for_log(val: str | None) -> str:
            if val is None:
                return "None"
            return str(val).replace("\r", "").replace("\n", "")[:200]

        safe_phase_id = _sanitize_for_log(phase_id)
        safe_run_id = _sanitize_for_log(run_id)
        safe_context = _sanitize_for_log(context)
        safe_decision_type = _sanitize_for_log(decision_info.get("type"))

        logger.info(
            f"[APPROVAL] Request received: run={safe_run_id}, phase={safe_phase_id}, "
            f"context={safe_context}, decision_type={safe_decision_type}"
        )

        # Configuration
        # PR-01 (P0): Safe-by-default - AUTO_APPROVE_BUILD113 defaults to "false" (DEC-046 compliance)
        # Production never allows auto-approve to prevent governance bypass
        env_mode = os.getenv("AUTOPACK_ENV", "development").lower()
        auto_approve_env = os.getenv("AUTO_APPROVE_BUILD113", "false").lower() == "true"
        auto_approve = auto_approve_env and env_mode != "production"
        timeout_minutes = int(os.getenv("APPROVAL_TIMEOUT_MINUTES", "15"))
        default_on_timeout = os.getenv(
            "APPROVAL_DEFAULT_ON_TIMEOUT", "reject"
        )  # "approve" or "reject"

        # Calculate timeout
        timeout_at = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)

        # Store approval request in database for audit trail
        approval_request = models.ApprovalRequest(
            run_id=run_id,
            phase_id=phase_id,
            context=context,
            decision_info=decision_info,
            deletion_info=deletion_info,
            timeout_at=timeout_at,
            status="pending",
        )
        db.add(approval_request)
        db.commit()
        db.refresh(approval_request)

        logger.info(f"[APPROVAL] Stored request #{approval_request.id} in database")

        # Auto-approve mode: immediate approval without notification
        # PR-01 (P0): Only allowed when AUTO_APPROVE_BUILD113=true AND not in production
        if auto_approve:
            approval_request.status = "approved"
            approval_request.response_method = "auto"
            approval_request.approval_reason = (
                f"Auto-approved (AUTO_APPROVE_BUILD113=true, env={env_mode})"
            )
            approval_request.responded_at = datetime.now(timezone.utc)
            db.commit()

            logger.warning(
                f"[APPROVAL] AUTO-APPROVING request #{approval_request.id} for {safe_phase_id} "
                f"(env={env_mode}, AUTO_APPROVE_BUILD113=true)"
            )
            return {
                "status": "approved",
                "reason": f"Auto-approved (BUILD-117 legacy, env={env_mode})",
                "approval_id": approval_request.id,
            }

        # Send Telegram notification
        notifier = TelegramNotifier()
        telegram_sent = False
        telegram_error = None

        if notifier.is_configured():
            logger.info(
                f"[APPROVAL] Sending Telegram notification for request #{approval_request.id}"
            )

            # Prepare deletion info for notification
            telegram_deletion_info = deletion_info or {
                "net_deletion": 0,
                "loc_removed": 0,
                "loc_added": 0,
                "files": [],
                "risk_level": decision_info.get("risk_level", "medium"),
                "risk_score": decision_info.get("risk_score", 50),
            }

            telegram_sent = notifier.send_approval_request(
                phase_id=phase_id,
                deletion_info=telegram_deletion_info,
                run_id=run_id,
                context=context,
            )

            if not telegram_sent:
                telegram_error = "Failed to send Telegram notification (check bot configuration)"
                logger.error(f"[APPROVAL] {telegram_error}")
        else:
            telegram_error = (
                "Telegram not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)"
            )
            logger.warning(f"[APPROVAL] {telegram_error}")

        # Update approval request with Telegram status
        approval_request.telegram_sent = telegram_sent
        approval_request.telegram_error = telegram_error
        db.commit()

        # Return pending status (will be updated via webhook or timeout)
        return {
            "status": "pending",
            "reason": f"Awaiting human approval (timeout in {timeout_minutes} minutes, default: {default_on_timeout})",
            "approval_id": approval_request.id,
            "telegram_sent": telegram_sent,
            "timeout_at": timeout_at.isoformat(),
        }

    except Exception as e:
        logger.error(f"[APPROVAL] Error processing approval request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Approval request processing failed")


# ==============================================================================
# PR Approval Telegram Callback Handler (IMPLEMENTATION_PLAN_PR_APPROVAL_PIPELINE)
# ==============================================================================


async def _handle_pr_callback(
    callback_data: str, callback_id: str, username: str, db: Session
) -> dict:
    """Handle PR approval Telegram callbacks.

    Callback formats:
    - pr_approve:{approval_id}
    - pr_reject:{approval_id}

    Updates ApprovalRequest by approval_id (not phase_id) to avoid collisions.
    """
    try:
        # Parse callback: "pr_approve:123" or "pr_reject:123"
        action, approval_id_str = callback_data.split(":", 1)
        approval_id = int(approval_id_str)

        action_verb = "approve" if action == "pr_approve" else "reject"

        logger.info(f"[TELEGRAM-PR] User @{username} {action_verb}d approval_id={approval_id}")

        # Find approval request by id (not phase_id!)
        approval_request = (
            db.query(models.ApprovalRequest)
            .filter(
                models.ApprovalRequest.id == approval_id, models.ApprovalRequest.status == "pending"
            )
            .first()
        )

        if not approval_request:
            logger.warning(f"[TELEGRAM-PR] No pending approval_id={approval_id}")
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            if bot_token:
                answer_telegram_callback(
                    bot_token,
                    callback_id,
                    "⚠️ Approval request not found or already processed",
                    show_alert=True,
                )
            return {"ok": True, "error": "approval_not_found"}

        # Update approval request
        # NOTE: Avoid "approveed" typo; store canonical terminal statuses.
        approval_request.status = "approved" if action == "pr_approve" else "rejected"
        approval_request.response_method = "telegram"
        approval_request.responded_at = datetime.now(timezone.utc)

        if action == "pr_approve":
            approval_request.approval_reason = f"Approved by Telegram user @{username}"
        else:
            approval_request.rejected_reason = f"Rejected by Telegram user @{username}"

        db.commit()

        logger.info(f"[TELEGRAM-PR] Approval {approval_id} {action_verb}ed by @{username}")

        # Answer callback to remove loading state
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if bot_token:
            answer_telegram_callback(bot_token, callback_id, f"✅ PR creation {action_verb}ed")

        return {"ok": True, "action": action_verb, "approval_id": approval_id}

    except Exception as e:
        logger.error(f"[TELEGRAM-PR] Callback error: {e}", exc_info=True)
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if bot_token:
            answer_telegram_callback(bot_token, callback_id, f"❌ Error: {str(e)}", show_alert=True)
        return {"ok": False, "error": str(e)}


# ==============================================================================
# Storage Optimizer Telegram Callback Handler (BUILD-150 Phase 3)
# ==============================================================================


async def _handle_storage_callback(
    callback_data: str, callback_id: str, username: str, db: Session
) -> dict:
    """
    Handle storage optimizer Telegram callbacks.

    Callback formats:
    - storage_approve_all:{scan_id} - Approve all candidates
    - storage_details:{scan_id} - View scan details
    - storage_skip:{scan_id} - Skip this scan
    """
    from autopack.storage_optimizer.db import (create_approval_decision,
                                               get_cleanup_candidates_by_scan)
    from autopack.storage_optimizer.telegram_notifications import (
        StorageTelegramNotifier, answer_telegram_callback)

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    notifier = StorageTelegramNotifier()

    try:
        if callback_data.startswith("storage_approve_all:"):
            scan_id = int(callback_data.split(":")[1])

            logger.info(f"[TELEGRAM] User @{username} approving all candidates for scan {scan_id}")

            # Get all candidates
            candidates = get_cleanup_candidates_by_scan(db, scan_id)

            if not candidates:
                answer_telegram_callback(
                    bot_token, callback_id, "❌ No candidates found for this scan"
                )
                return {"ok": True}

            # Approve all
            candidate_ids = [c.id for c in candidates]
            total_size = sum(c.size_bytes for c in candidates)

            create_approval_decision(
                db,
                scan_id=scan_id,
                candidate_ids=candidate_ids,
                approved_by=f"telegram_@{username}",
                decision="approve",
                approval_method="telegram",
                notes="Approved all via Telegram inline button",
            )
            db.commit()

            # Answer callback
            answer_telegram_callback(
                bot_token,
                callback_id,
                f"✅ Approved {len(candidate_ids)} items ({total_size / (1024**3):.2f} GB)",
            )

            # Send confirmation message
            notifier.send_approval_confirmation(
                scan_id=scan_id,
                approved_count=len(candidate_ids),
                approved_size_gb=total_size / (1024**3),
            )

            logger.info(f"[TELEGRAM] Approved {len(candidate_ids)} candidates for scan {scan_id}")

        elif callback_data.startswith("storage_details:"):
            scan_id = int(callback_data.split(":")[1])

            logger.info(f"[TELEGRAM] User @{username} viewing details for scan {scan_id}")

            # Get API URL
            api_url = os.getenv("AUTOPACK_API_URL", "http://localhost:8000")
            details_url = f"{api_url}/storage/scans/{scan_id}"

            answer_telegram_callback(
                bot_token, callback_id, f"View details: {details_url}", show_alert=True
            )

        elif callback_data.startswith("storage_skip:"):
            scan_id = int(callback_data.split(":")[1])

            logger.info(f"[TELEGRAM] User @{username} skipping scan {scan_id}")

            answer_telegram_callback(bot_token, callback_id, "⏭️ Scan skipped")

        return {"ok": True}

    except Exception as e:
        logger.error(f"[TELEGRAM] Storage callback error: {e}", exc_info=True)
        answer_telegram_callback(bot_token, callback_id, f"❌ Error: {str(e)}", show_alert=True)
        return {"ok": False, "error": str(e)}


@router.post("/telegram/webhook")
@limiter.limit("30/minute")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Telegram webhook callbacks for approval buttons.

    Rate limited to 30 requests/minute to prevent webhook abuse while allowing
    legitimate rapid button presses.

    This endpoint receives callbacks when users tap Approve/Reject buttons
    in Telegram notifications.

    Security (PR7 - P1-SEC-TELEGRAM-001):
    - Uses verify_telegram_webhook_crypto for cryptographic verification
    - In production, requires TELEGRAM_WEBHOOK_SECRET to be configured
    - Uses hmac.compare_digest for constant-time comparison (timing attack prevention)

    Callback data formats:
    - Phase approvals: "approve:{phase_id}" or "reject:{phase_id}"
    - Storage scans (BUILD-150): "storage_approve_all:{scan_id}", "storage_details:{scan_id}", "storage_skip:{scan_id}"
    """
    # Verify webhook authenticity (PR7: cryptographic verification)
    # Skip in testing mode for convenience
    if os.getenv("TESTING") != "1":
        if not await verify_telegram_webhook_crypto(request):
            raise HTTPException(
                status_code=403,
                detail="Invalid or missing Telegram webhook secret token",
            )

    try:
        from autopack.notifications.telegram_notifier import TelegramNotifier

        data = await request.json()
        logger.info(f"[TELEGRAM] Webhook received: {data}")

        # Extract callback query
        callback_query = data.get("callback_query")
        if not callback_query:
            logger.warning("[TELEGRAM] No callback_query in webhook data")
            return {"ok": True}

        callback_data = callback_query.get("data")
        callback_id = callback_query.get("id")
        message_id = callback_query.get("message", {}).get("message_id")
        callback_query.get("message", {}).get("chat", {}).get("id")
        user_id = callback_query.get("from", {}).get("id")
        username = callback_query.get("from", {}).get("username", "unknown")

        if not callback_data:
            logger.warning("[TELEGRAM] No callback data in query")
            return {"ok": True}

        # BUILD-150 Phase 3: Handle storage optimizer callbacks
        if callback_data.startswith("storage_"):
            return await _handle_storage_callback(callback_data, callback_id, username, db)

        # PR approval callbacks: "pr_approve:{approval_id}" or "pr_reject:{approval_id}"
        if callback_data.startswith("pr_approve:") or callback_data.startswith("pr_reject:"):
            return await _handle_pr_callback(callback_data, callback_id, username, db)

        # Parse callback data: "approve:{phase_id}" or "reject:{phase_id}"
        action, phase_id = callback_data.split(":", 1)

        logger.info(f"[TELEGRAM] User @{username} ({user_id}) {action}d phase {phase_id}")

        # Find the approval request
        approval_request = (
            db.query(models.ApprovalRequest)
            .filter(
                models.ApprovalRequest.phase_id == phase_id,
                models.ApprovalRequest.status == "pending",
            )
            .order_by(models.ApprovalRequest.requested_at.desc())
            .first()
        )

        if not approval_request:
            logger.warning(f"[TELEGRAM] No pending approval request found for {phase_id}")
            # Still acknowledge the callback
            notifier = TelegramNotifier()
            if notifier.is_configured():
                notifier.send_completion_notice(
                    phase_id=phase_id,
                    status="error",
                    message="⚠️ Approval request not found or already processed",
                )
            return {"ok": True}

        # Update approval request
        approval_request.status = action + "ed"  # "approve" -> "approved", "reject" -> "rejected"
        approval_request.response_method = "telegram"
        approval_request.responded_at = datetime.now(timezone.utc)
        approval_request.telegram_message_id = str(message_id)

        if action == "approve":
            approval_request.approval_reason = f"Approved by Telegram user @{username}"
        else:
            approval_request.rejected_reason = f"Rejected by Telegram user @{username}"

        db.commit()

        logger.info(f"[TELEGRAM] Approval request #{approval_request.id} {action}ed by @{username}")

        # Send confirmation message
        notifier = TelegramNotifier()
        if notifier.is_configured():
            notifier.send_completion_notice(
                phase_id=phase_id,
                status=action + "ed",
                message=f"Phase `{phase_id}` has been {action}ed.",
            )

        return {"ok": True}

    except Exception as e:
        logger.error(f"[TELEGRAM] Webhook error: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


@router.get("/approval/status/{approval_id}")
async def get_approval_status(
    approval_id: int,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
):
    """Check the status of an approval request.

    Used by autonomous executor to poll for approval decisions.

    Returns:
    {
        "approval_id": int,
        "status": "pending" | "approved" | "rejected" | "timeout",
        "requested_at": datetime,
        "responded_at": datetime (if responded),
        "timeout_at": datetime,
        "approval_reason": str (if approved),
        "rejected_reason": str (if rejected)
    }
    """
    try:
        approval_request = (
            db.query(models.ApprovalRequest)
            .filter(models.ApprovalRequest.id == approval_id)
            .first()
        )

        if not approval_request:
            raise HTTPException(
                status_code=404, detail=f"Approval request #{approval_id} not found"
            )

        return {
            "approval_id": approval_request.id,
            "run_id": approval_request.run_id,
            "phase_id": approval_request.phase_id,
            "status": approval_request.status,
            "requested_at": approval_request.requested_at.isoformat(),
            "responded_at": (
                approval_request.responded_at.isoformat() if approval_request.responded_at else None
            ),
            "timeout_at": (
                approval_request.timeout_at.isoformat() if approval_request.timeout_at else None
            ),
            "approval_reason": approval_request.approval_reason,
            "rejected_reason": approval_request.rejected_reason,
            "response_method": approval_request.response_method,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[APPROVAL] Error fetching status for #{approval_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch approval status")


@router.get("/approval/pending")
async def get_pending_approvals(
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_read_access),
):
    """Get all pending approval requests (for dashboard UI).

    Returns:
    {
        "count": int,
        "requests": [...]
    }
    """
    try:
        pending_requests = (
            db.query(models.ApprovalRequest)
            .filter(models.ApprovalRequest.status == "pending")
            .order_by(models.ApprovalRequest.requested_at.desc())
            .all()
        )

        return {
            "count": len(pending_requests),
            "requests": [
                {
                    "id": req.id,
                    "run_id": req.run_id,
                    "phase_id": req.phase_id,
                    "context": req.context,
                    "requested_at": req.requested_at.isoformat(),
                    "timeout_at": req.timeout_at.isoformat() if req.timeout_at else None,
                    "decision_info": req.decision_info,
                    "deletion_info": req.deletion_info,
                    "telegram_sent": req.telegram_sent,
                }
                for req in pending_requests
            ],
        }

    except Exception as e:
        logger.error(f"[APPROVAL] Error fetching pending approvals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch pending approvals")
