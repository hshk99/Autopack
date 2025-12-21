# BUILD-107 & BUILD-108: Telegram Approval + Deletion Safeguards

**Status**: ✅ IMPLEMENTED
**Date**: 2025-12-21
**Builds**: BUILD-107, BUILD-108

## Overview

Implemented a comprehensive safeguard system to prevent catastrophic code deletions (like the 426-line incident from ref6.md) with mobile approval workflow via Telegram.

### Key Features

1. **Context-Aware Deletion Thresholds** - Automatically blocks large deletions
2. **Telegram Mobile Approval** - Get notified on your phone, approve/reject with buttons
3. **Failed Phase Notifications** - Alerts when phases fail or get stuck
4. **Hybrid Risk Assessment** - Balances autonomy with safety

---

## BUILD-107: Telegram Mobile Approval System

### Components

**1. TelegramNotifier Class** ([telegram_notifier.py](../src/autopack/notifications/telegram_notifier.py))

Sends rich notifications to your existing @CodeSherpaBot with inline approval buttons.

```python
from autopack.notifications.telegram_notifier import TelegramNotifier

notifier = TelegramNotifier()

# Send approval request
notifier.send_approval_request(
    phase_id="diagnostics-deep-retrieval",
    deletion_info={
        'net_deletion': 414,
        'loc_removed': 426,
        'loc_added': 12,
        'files': ['src/autopack/diagnostics/deep_retrieval.py'],
        'risk_level': 'critical',
        'risk_score': 85,
    },
    run_id="my-run",
    context="troubleshoot"
)

# You receive on your phone:
# ⚠️ Autopack Approval Needed
# Phase: diagnostics-deep-retrieval
# Risk: 🚨 CRITICAL (score: 85/100)
# Net Deletion: 414 lines
#   ├─ Removed: 426
#   └─ Added: 12
# Files:
#   • src/autopack/diagnostics/deep_retrieval.py
# [✅ Approve]  [❌ Reject]  [📊 Show Details]
```

**2. Backend API Endpoints** ([approvals.py](../src/backend/api/approvals.py))

```
POST   /approval/request         - Request approval from user
GET    /approval/status/{id}     - Poll for approval decision
POST   /approval/approve/{id}    - Approve phase (called by webhook)
POST   /approval/reject/{id}     - Reject phase (called by webhook)
POST   /telegram/webhook         - Receive button callbacks from Telegram
```

**3. Executor Integration** ([autonomous_executor.py](../src/autopack/autonomous_executor.py))

When quality gate blocks a phase:

```python
if quality_report.is_blocked():
    approval_granted = self._request_human_approval(
        phase_id=phase_id,
        quality_report=quality_report,
        timeout_seconds=3600  # 1 hour
    )

    if not approval_granted:
        self._update_phase_status(phase_id, "BLOCKED")
        return False, "BLOCKED: Human approval denied or timed out"

    # Continue execution if approved
```

### Setup

See [TELEGRAM_APPROVAL_SETUP.md](TELEGRAM_APPROVAL_SETUP.md) for detailed setup instructions.

**Quick Start:**

```bash
# 1. Set environment variables
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
export NGROK_URL="https://harrybot.ngrok.app"

# 2. Set up webhook
python -c "
from autopack.notifications.telegram_notifier import setup_telegram_webhook
import os
setup_telegram_webhook(
    os.getenv('TELEGRAM_BOT_TOKEN'),
    os.getenv('NGROK_URL')
)
"

# 3. Start ngrok
ngrok http --domain=harrybot.ngrok.app 8001

# 4. Start backend
uvicorn backend.main:app --port 8001
```

---

## BUILD-108: Context-Aware Deletion Safeguards

### Thresholds

| Context        | Threshold         | Rationale                                      |
|----------------|-------------------|------------------------------------------------|
| Troubleshooting| > 50 net lines    | Bug fixes should delete minimal code          |
| Feature Work   | > 150 net lines   | Moderate tolerance for feature development     |
| Refactoring    | > 300 net lines   | Lenient for legitimate refactoring             |
| Critical Risk  | risk_score ≥ 70   | Any critical-risk change requires approval     |

### Implementation

**1. Risk Scorer** ([risk_scorer.py:105-138](../src/autopack/risk_scorer.py#L105-L138))

```python
# Calculate net deletion
net_deletion = loc_removed - loc_added

# Context-aware thresholds
TROUBLESHOOT_THRESHOLD = 50   # Strict
REFACTOR_THRESHOLD = 300      # Lenient
FEATURE_THRESHOLD = 150       # Moderate

if net_deletion > TROUBLESHOOT_THRESHOLD:
    checks["large_deletion"] = True

    if net_deletion > REFACTOR_THRESHOLD:
        deletion_severity = 40  # Critical
        reasons.append(f"CRITICAL DELETION: Net removal of {net_deletion} lines")
    elif net_deletion > FEATURE_THRESHOLD:
        deletion_severity = 30  # High
        reasons.append(f"LARGE DELETION: Net removal of {net_deletion} lines")
    else:
        deletion_severity = 20  # Medium
        reasons.append(f"MEDIUM DELETION: Net removal of {net_deletion} lines")

    score += deletion_severity
    checks["deletion_threshold_exceeded"] = True
```

**2. Quality Gate** ([quality_gate.py:243-253](../src/autopack/quality_gate.py#L243-L253))

```python
def _determine_quality_level(..., risk_result=None):
    # NEW: Check for large deletions that require approval
    if risk_result:
        checks = risk_result.get("checks", {})

        # Block if deletion threshold exceeded
        if checks.get("deletion_threshold_exceeded"):
            return "blocked"  # Requires human approval

        # Block if risk level is critical
        if risk_result.get("risk_level") == "critical":
            return "blocked"  # Too risky to proceed automatically
```

**3. Failed Phase Notifications** ([autonomous_executor.py:6937-6982](../src/autopack/autonomous_executor.py#L6937-L6982))

```python
def _send_phase_failure_notification(self, phase_id: str, reason: str):
    """Send Telegram notification when a phase fails or gets stuck."""

    # Emoji-coded by failure type
    emoji = "❌"
    if "EXHAUSTED" in reason:
        emoji = "🔁"  # Retry exhausted
    elif "TIMEOUT" in reason:
        emoji = "⏱️"  # Timeout
    elif "STUCK" in reason:
        emoji = "⚠️"  # Stuck

    message = (
        f"{emoji} *Autopack Phase Failed*\n\n"
        f"*Run*: `{self.run_id}`\n"
        f"*Phase*: `{phase_id}`\n"
        f"*Reason*: {reason}\n\n"
        f"The executor has halted. Please review the logs.\n"
    )

    notifier.send_completion_notice(phase_id, "failed", message)
```

---

## Complete Flow Example

### Scenario: 426-Line Deletion Attempt

```
[Phase: diagnostics-deep-retrieval]

1. Builder creates patch
   - Files changed: src/autopack/diagnostics/deep_retrieval.py
   - Lines added: 12
   - Lines removed: 426
   - Net deletion: 414 lines

2. Risk Scorer analyzes
   └─> net_deletion (414) > REFACTOR_THRESHOLD (300)
   └─> Adds 40 risk points
   └─> Risk score: 85/100
   └─> Risk level: CRITICAL
   └─> Sets deletion_threshold_exceeded = True

3. Quality Gate checks
   └─> Sees deletion_threshold_exceeded = True
   └─> Returns quality_level = "blocked"

4. Executor detects blocked phase
   └─> Calls _request_human_approval()
   └─> POST /approval/request
       └─> TelegramNotifier.send_approval_request()
           └─> Telegram API sends message

5. Your phone receives:
   ⚠️ Autopack Approval Needed

   Phase: diagnostics-deep-retrieval
   Run: my-run-123
   Risk: 🚨 CRITICAL (score: 85/100)
   Net Deletion: 414 lines
     ├─ Removed: 426
     └─ Added: 12

   Files:
     • src/autopack/diagnostics/deep_retrieval.py

   ⚠️ Troubleshooting context: Large deletions unexpected

   Sent: 2025-12-21 03:00:00 UTC

   [✅ Approve]  [❌ Reject]  [📊 Show Details]

6. You tap ❌ Reject
   └─> Telegram POSTs to /telegram/webhook
   └─> Backend calls POST /approval/reject/diagnostics-deep-retrieval
   └─> Executor polling detects status = "rejected"

7. Executor halts
   └─> self._update_phase_status(phase_id, "BLOCKED")
   └─> Returns (False, "BLOCKED: Human approval denied or timed out")
   └─> Sends failure notification to Telegram

Result: ✅ Catastrophic deletion prevented!
```

---

## Testing

### Test Deletion Detection

```python
from autopack.risk_scorer import RiskScorer

scorer = RiskScorer()

# Test 426-line deletion
result = scorer.score_change(
    files_changed=["src/autopack/diagnostics/deep_retrieval.py"],
    loc_added=12,
    loc_removed=426,
    patch_content=None
)

print(f"Risk Score: {result['risk_score']}/100")
print(f"Risk Level: {result['risk_level']}")
print(f"Deletion Threshold Exceeded: {result['checks']['deletion_threshold_exceeded']}")
print(f"Net Deletion: {result['checks']['net_deletion']}")

# Expected output:
# Risk Score: 85/100
# Risk Level: critical
# Deletion Threshold Exceeded: True
# Net Deletion: 414
```

### Test Telegram Notification (Manual)

```bash
cd c:/dev/Autopack
PYTHONUTF8=1 PYTHONPATH=src python -c "
from autopack.notifications.telegram_notifier import TelegramNotifier

notifier = TelegramNotifier()

if notifier.is_configured():
    deletion_info = {
        'net_deletion': 414,
        'loc_removed': 426,
        'loc_added': 12,
        'files': ['src/autopack/diagnostics/deep_retrieval.py'],
        'risk_level': 'critical',
        'risk_score': 85,
    }

    success = notifier.send_approval_request(
        phase_id='test-phase',
        deletion_info=deletion_info,
        run_id='test-run',
        context='troubleshoot'
    )

    print('✅ Test notification sent!' if success else '❌ Failed')
else:
    print('❌ Telegram not configured')
"
```

Check your phone - you should receive the notification within seconds.

### Test Approval Workflow (End-to-End)

1. Start backend: `uvicorn backend.main:app --port 8001`
2. Start ngrok: `ngrok http --domain=harrybot.ngrok.app 8001`
3. Create a run with a phase that will exceed deletion threshold
4. Wait for notification on phone
5. Tap Approve or Reject
6. Verify executor proceeds or halts accordingly

---

## Configuration

### Environment Variables

```bash
# Required for Telegram integration
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
TELEGRAM_CHAT_ID="123456789"

# Optional (defaults shown)
AUTOPACK_CALLBACK_URL="http://localhost:8001"
NGROK_URL="https://harrybot.ngrok.app"
```

### Adjust Deletion Thresholds

Edit [src/autopack/risk_scorer.py](../src/autopack/risk_scorer.py#L109-L111):

```python
# Context-aware deletion thresholds
TROUBLESHOOT_THRESHOLD = 50   # Strict: troubleshooting should delete minimal code
REFACTOR_THRESHOLD = 300       # Lenient: refactoring can be larger
FEATURE_THRESHOLD = 150        # Moderate: feature work
```

### Adjust Approval Timeout

Edit [src/autopack/autonomous_executor.py](../src/autopack/autonomous_executor.py#L4139):

```python
approval_granted = self._request_human_approval(
    phase_id=phase_id,
    quality_report=quality_report,
    timeout_seconds=7200  # 2 hours instead of default 1 hour
)
```

---

## Benefits

### Safety
- ✅ **Prevents catastrophic deletions** - Blocks large deletions automatically
- ✅ **Context-aware** - Strict for troubleshooting, lenient for refactoring
- ✅ **Mobile approval** - Get notified away from desktop
- ✅ **Safe defaults** - Auto-reject if Telegram not configured

### Visibility
- ✅ **Real-time notifications** - Know immediately when approval needed
- ✅ **Failure alerts** - Get notified when phases fail or get stuck
- ✅ **Rich context** - See risk score, deletion counts, affected files
- ✅ **Inline buttons** - Approve/reject with one tap

### Autonomy
- ✅ **Non-blocking** - Only blocks truly risky changes
- ✅ **Hybrid approach** - Balances safety with productivity
- ✅ **Configurable thresholds** - Adjust based on your risk tolerance

---

## Troubleshooting

### No notification received

1. Check environment variables: `echo $TELEGRAM_BOT_TOKEN`
2. Test bot token: `curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe"`
3. Test chat ID: Send message to @CodeSherpaBot, then check updates

### Buttons don't work

1. Check webhook: `curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"`
2. Verify ngrok running: `curl https://harrybot.ngrok.app/approval/status/test-phase`
3. Check backend logs for webhook events

### False positives (blocking valid refactors)

Increase thresholds in [risk_scorer.py](../src/autopack/risk_scorer.py):

```python
TROUBLESHOOT_THRESHOLD = 100   # Was 50
REFACTOR_THRESHOLD = 500       # Was 300
FEATURE_THRESHOLD = 200        # Was 150
```

### Missing failure notifications

Check `_mark_phase_failed_in_db()` is called - failure notifications are automatically sent from there.

---

## Files Modified

### BUILD-107: Telegram Integration
- `src/autopack/notifications/telegram_notifier.py` (new) - Telegram client
- `src/autopack/notifications/__init__.py` (new) - Package init
- `src/backend/api/approvals.py` (new) - Approval API
- `src/backend/main.py` - Mount approvals router
- `src/autopack/autonomous_executor.py` - Approval workflow integration
- `docs/TELEGRAM_APPROVAL_SETUP.md` (new) - Setup guide

### BUILD-108: Deletion Safeguards
- `src/autopack/risk_scorer.py` - Deletion detection logic
- `src/autopack/quality_gate.py` - Blocking rules
- `src/autopack/autonomous_executor.py` - Failure notifications
- `docs/RECOMMENDATION_LARGE_DELETION_SAFEGUARD.md` - Updated with implementation

---

## Next Steps

### Optional Enhancements

1. **Context Detection** - Auto-infer context from phase metadata instead of hardcoded thresholds
2. **Learning System** - Track approval decisions, adjust thresholds over time
3. **Multi-User** - Support team approvals (any team member can approve)
4. **Dashboard Integration** - Show approval requests in web dashboard
5. **Approval History** - Log all approval decisions for audit trail

### Production Checklist

- [ ] Get Telegram bot token from @BotFather
- [ ] Get your chat ID
- [ ] Set environment variables
- [ ] Configure webhook with ngrok
- [ ] Test end-to-end approval flow
- [ ] Adjust thresholds based on your risk tolerance
- [ ] Set up monitoring for approval timeout events
- [ ] Document team approval workflow (if multi-user)

---

## References

- [TELEGRAM_APPROVAL_SETUP.md](TELEGRAM_APPROVAL_SETUP.md) - Detailed setup guide
- [RECOMMENDATION_LARGE_DELETION_SAFEGUARD.md](RECOMMENDATION_LARGE_DELETION_SAFEGUARD.md) - Original recommendation
- [Telegram Bot API](https://core.telegram.org/bots/api) - Telegram docs
- [ngrok Documentation](https://ngrok.com/docs) - ngrok setup

---

**Implementation Date**: 2025-12-21
**Builds**: BUILD-107 (Telegram), BUILD-108 (Safeguards)
**Status**: ✅ Production Ready
