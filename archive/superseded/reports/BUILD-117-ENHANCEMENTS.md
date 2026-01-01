# BUILD-117: Approval Endpoint Enhancements

## Overview

BUILD-117 implements a comprehensive approval system for BUILD-113 autonomous investigations. When the autonomous executor needs human approval for risky or ambiguous decisions, it can request approval through multiple channels with full audit trail and timeout handling.

## Four Core Enhancements

### 1. Telegram Integration
- Send approval requests to your phone via Telegram bot
- Interactive buttons for Approve/Reject
- Real-time notifications when decisions are needed
- Completion notices after approval/rejection/timeout

### 2. Database Audit Trail
- All approval requests stored in `approval_requests` table
- Full history of who approved/rejected and when
- Timeout tracking and automatic cleanup
- Integration with run/phase tracking

### 3. Timeout Mechanism
- Configurable timeout (default: 15 minutes)
- Background task checks for expired requests every 60 seconds
- Configurable default action on timeout (approve/reject)
- Automatic cleanup and notification

### 4. Dashboard UI Support
- `/approval/pending` endpoint lists all pending approvals
- `/approval/status/{id}` endpoint for polling
- Ready for future dashboard implementation
- Real-time status updates

## Configuration

All configuration is done via environment variables in your `.env` file:

```bash
# Auto-approval mode (bypass Telegram notifications)
AUTO_APPROVE_BUILD113=true  # Set to "false" to require human approval

# Timeout configuration
APPROVAL_TIMEOUT_MINUTES=15  # How long to wait before timeout
APPROVAL_DEFAULT_ON_TIMEOUT=reject  # "approve" or "reject"

# Telegram configuration (optional)
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_telegram_user_id
NGROK_URL=https://yourname.ngrok.app  # For webhook callbacks

# Autopack API URL (for Telegram button callbacks)
AUTOPACK_CALLBACK_URL=http://localhost:8001
```

## Database Schema

### ApprovalRequest Table

```python
class ApprovalRequest(Base):
    """Approval requests for BUILD-113 risky or ambiguous decisions."""

    # Identity
    id: int (primary key)
    run_id: str (indexed)
    phase_id: str (indexed)
    context: str  # "build113_risky_decision", "build113_ambiguous_decision", "troubleshoot"

    # Decision metadata
    decision_info: JSON  # Decision details from BUILD-113
    deletion_info: JSON  # File deletion statistics if applicable

    # Timestamps
    requested_at: DateTime (indexed, UTC)
    responded_at: DateTime (nullable, UTC)
    timeout_at: DateTime (nullable, UTC)

    # Status tracking
    status: str  # "pending", "approved", "rejected", "timeout", "error"
    response_method: str  # "telegram", "dashboard", "auto", "timeout"
    approval_reason: Text (nullable)
    rejected_reason: Text (nullable)

    # Telegram integration
    telegram_message_id: str (nullable)
    telegram_sent: bool (default: False)
    telegram_error: Text (nullable)
```

## API Endpoints

### POST /approval/request

Request approval for a risky or ambiguous decision.

**Request Body**:
```json
{
  "run_id": "build113-test-run",
  "phase_id": "P1.2",
  "context": "build113_risky_decision",
  "decision_info": {
    "risk_level": "high",
    "risk_score": 85,
    "description": "Large refactoring with cross-cutting changes"
  },
  "deletion_info": {
    "net_deletion": 150,
    "loc_removed": 200,
    "loc_added": 50,
    "files": ["src/core.py", "src/utils.py"],
    "risk_level": "high",
    "risk_score": 85
  }
}
```

**Response (Auto-Approve Mode)**:
```json
{
  "status": "approved",
  "reason": "Auto-approved (BUILD-117 - auto-approve mode enabled)",
  "approval_id": 42
}
```

**Response (Pending Approval)**:
```json
{
  "status": "pending",
  "reason": "Awaiting human approval (timeout in 15 minutes, default: reject)",
  "approval_id": 42,
  "telegram_sent": true,
  "timeout_at": "2025-12-22T04:00:00+00:00"
}
```

### POST /telegram/webhook

Handle Telegram button callbacks (Approve/Reject).

**Request Body** (from Telegram):
```json
{
  "callback_query": {
    "data": "approve:P1.2",
    "from": {
      "username": "yourname"
    }
  }
}
```

**Response**:
```json
{
  "ok": true
}
```

### GET /approval/status/{approval_id}

Check the status of an approval request.

**Response**:
```json
{
  "approval_id": 42,
  "run_id": "build113-test-run",
  "phase_id": "P1.2",
  "status": "approved",
  "requested_at": "2025-12-22T03:45:00+00:00",
  "responded_at": "2025-12-22T03:47:30+00:00",
  "timeout_at": "2025-12-22T04:00:00+00:00",
  "approval_reason": "Approved by Telegram user @yourname",
  "rejected_reason": null,
  "response_method": "telegram"
}
```

### GET /approval/pending

Get all pending approval requests (for dashboard UI).

**Response**:
```json
{
  "count": 2,
  "requests": [
    {
      "id": 43,
      "run_id": "build113-test-run",
      "phase_id": "P1.3",
      "context": "build113_ambiguous_decision",
      "requested_at": "2025-12-22T03:50:00+00:00",
      "timeout_at": "2025-12-22T04:05:00+00:00",
      "decision_info": {
        "risk_level": "medium",
        "risk_score": 60
      },
      "deletion_info": null,
      "telegram_sent": true
    }
  ]
}
```

## Telegram Setup

### 1. Create Bot (if you don't have one)

```bash
# Chat with @BotFather on Telegram
/newbot
# Follow prompts to get your bot token
```

### 2. Get Your Chat ID

```python
# Run this script to get your chat ID
import os
from autopack.notifications.telegram_notifier import get_my_chat_id

bot_token = "YOUR_BOT_TOKEN"
chat_id = get_my_chat_id(bot_token)
print(f"Your chat ID: {chat_id}")
```

Or use curl:
```bash
# Send a message to your bot first, then:
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates"
# Look for "chat":{"id": YOUR_CHAT_ID} in response
```

### 3. Set Up Webhook (for button callbacks)

```python
from autopack.notifications.telegram_notifier import setup_telegram_webhook

setup_telegram_webhook(
    bot_token="YOUR_BOT_TOKEN",
    ngrok_url="https://yourname.ngrok.app"
)
```

Or use the startup script:
```bash
# The backend will automatically set up webhook on startup
# if TELEGRAM_BOT_TOKEN and NGROK_URL are configured
```

### 4. Configure Environment Variables

```bash
# Add to .env
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
TELEGRAM_CHAT_ID=your_chat_id_from_step_2
NGROK_URL=https://yourname.ngrok.app
AUTO_APPROVE_BUILD113=false  # Enable human approval
```

### 5. Test the Integration

```bash
# Start the backend
cd c:/dev/Autopack
PYTHONUTF8=1 PYTHONPATH=src python -m uvicorn autopack.main:app --host 0.0.0.0 --port 8001

# In another terminal, send test approval request
curl -X POST http://localhost:8001/approval/request \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "test-run",
    "phase_id": "test-phase",
    "context": "build113_risky_decision",
    "deletion_info": {
      "net_deletion": 150,
      "loc_removed": 200,
      "loc_added": 50,
      "files": ["test.py"],
      "risk_level": "high",
      "risk_score": 85
    }
  }'
```

You should receive a Telegram message with Approve/Reject buttons!

## Background Task

The timeout cleanup task runs automatically when the backend starts:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan and background tasks."""
    # Start timeout cleanup task
    cleanup_task = asyncio.create_task(approval_timeout_cleanup())

    yield

    # Cancel task on shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
```

The task:
- Runs every 60 seconds
- Queries for expired pending requests
- Applies default action (approve/reject)
- Sends Telegram completion notice
- Updates database with timeout status

## Usage Examples

### Example 1: Auto-Approve Mode (Development)

```bash
# .env configuration
AUTO_APPROVE_BUILD113=true
```

**Behavior**:
- All approval requests immediately return `{"status": "approved"}`
- No Telegram notifications sent
- Fast development/testing workflow
- Database audit trail still created

### Example 2: Human Approval via Telegram (Production)

```bash
# .env configuration
AUTO_APPROVE_BUILD113=false
TELEGRAM_BOT_TOKEN=123456:ABC-DEF
TELEGRAM_CHAT_ID=987654321
APPROVAL_TIMEOUT_MINUTES=15
APPROVAL_DEFAULT_ON_TIMEOUT=reject
```

**Behavior**:
1. Approval request comes in
2. Database record created with `status="pending"`
3. Telegram message sent with Approve/Reject buttons
4. User taps button on phone
5. Telegram webhook receives callback
6. Database updated with approval/rejection
7. Autonomous executor proceeds based on decision

### Example 3: Dashboard Polling (Future UI)

```javascript
// Frontend dashboard code
async function pollApprovalStatus(approvalId) {
  const response = await fetch(`/approval/status/${approvalId}`);
  const data = await response.json();

  if (data.status === "pending") {
    // Still waiting, poll again in 2 seconds
    setTimeout(() => pollApprovalStatus(approvalId), 2000);
  } else {
    // Decision made: approved, rejected, or timeout
    console.log(`Decision: ${data.status}`);
    console.log(`Method: ${data.response_method}`);
  }
}
```

### Example 4: Timeout Handling

**Scenario**: User doesn't respond within 15 minutes

**Behavior**:
1. Request created at 03:45:00, timeout_at set to 04:00:00
2. Background task checks at 04:00:30
3. Request marked as `status="timeout"`
4. Default action applied (e.g., "reject")
5. Telegram completion notice sent
6. Database updated with timeout details

## Integration with BUILD-113

BUILD-113's autonomous executor calls the approval endpoint when:

1. **Risky Decisions**: Large deletions, cross-cutting changes
2. **Ambiguous Decisions**: Multiple valid approaches
3. **Troubleshooting Context**: Unexpected large deletions during debugging

**Executor Flow**:
```python
# In autonomous_executor.py
approval_response = requests.post(
    f"{AUTOPACK_API_URL}/approval/request",
    json={
        "run_id": self.run_id,
        "phase_id": phase_id,
        "context": "build113_risky_decision",
        "decision_info": {...},
        "deletion_info": {...}
    }
)

if approval_response.json()["status"] == "approved":
    # Proceed with phase execution
    pass
elif approval_response.json()["status"] == "pending":
    # Wait for human approval (poll /approval/status endpoint)
    approval_id = approval_response.json()["approval_id"]
    # ... polling logic ...
else:
    # Rejected - mark phase as BUILD113_APPROVAL_DENIED
    pass
```

## Error Handling

### Telegram Not Configured

**Symptom**: `telegram_sent: false` in response

**Solution**:
- Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` environment variables
- Review logs for `[Telegram] API error` messages
- Verify bot token is valid

### Webhook Not Receiving Callbacks

**Symptom**: Buttons don't work, no `/telegram/webhook` logs

**Solution**:
1. Verify ngrok is running: `./ngrok.exe http 8001`
2. Check webhook registration:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
   ```
3. Re-register webhook:
   ```python
   setup_telegram_webhook(bot_token, ngrok_url)
   ```

### Timeout Task Not Running

**Symptom**: Expired requests stay in `pending` status

**Solution**:
- Check backend logs for `[APPROVAL-TIMEOUT] Background task started`
- Verify FastAPI lifespan manager is active
- Check for exceptions in `[APPROVAL-TIMEOUT] Error in cleanup task`

## Testing Checklist

- [ ] Auto-approve mode works (immediate approval)
- [ ] Telegram notification sent successfully
- [ ] Telegram buttons trigger webhook correctly
- [ ] Approval updates database correctly
- [ ] Rejection updates database correctly
- [ ] Timeout mechanism works after configured duration
- [ ] Default action applied on timeout (approve/reject)
- [ ] Telegram completion notice sent
- [ ] `/approval/status` endpoint returns correct data
- [ ] `/approval/pending` endpoint lists pending requests
- [ ] Background cleanup task runs every 60 seconds
- [ ] Database audit trail complete for all scenarios

## Files Modified

### src/autopack/models.py
- Added `ApprovalRequest` model (lines 308-339)

### src/autopack/main.py
- Added `approval_timeout_cleanup()` background task (lines 61-126)
- Updated lifespan manager to start background task (lines 129-147)
- Enhanced `/approval/request` endpoint (lines 768-899)
- Added `/telegram/webhook` endpoint (lines 902-986)
- Added `/approval/status/{approval_id}` endpoint (lines 989-1031)
- Added `/approval/pending` endpoint (lines 1034-1069)

### src/autopack/notifications/telegram_notifier.py
- No changes (pre-existing service, verified compatibility)

## Future Enhancements

Potential future improvements:

1. **Dashboard UI**: Web-based approval interface using `/approval/pending` endpoint
2. **Email Notifications**: Alternative to Telegram for approval requests
3. **Approval History**: Dedicated endpoint to query historical approvals
4. **Multi-User Approval**: Support for team-based approval workflows
5. **Custom Timeout Per Request**: Override default timeout on per-request basis
6. **Rich Notification Format**: Include code diffs in Telegram messages
7. **Approval Templates**: Pre-configured approval criteria for common scenarios
8. **Analytics**: Track approval rates, average response times, etc.

## References

- **BUILD-113**: Iterative Autonomous Investigation with Goal-Aware Judgment
- **BUILD-112**: Diagnostics Parity with Cursor (completion run using approval system)
- **BUILD-117**: This implementation (approval endpoint enhancements)
- **TelegramNotifier**: [src/autopack/notifications/telegram_notifier.py](../src/autopack/notifications/telegram_notifier.py)
- **Database Models**: [src/autopack/models.py](../src/autopack/models.py)
- **Main API**: [src/autopack/main.py](../src/autopack/main.py)
