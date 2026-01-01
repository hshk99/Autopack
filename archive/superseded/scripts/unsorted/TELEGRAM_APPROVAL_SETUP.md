# Telegram Approval Setup Guide

This guide explains how to set up mobile notifications for Autopack approval requests using your existing **@CodeSherpaBot** Telegram bot.

## Overview

When Autopack encounters a high-risk change (like large code deletions), it will:
1. Send a notification to your phone via Telegram
2. Show an inline keyboard with **Approve** / **Reject** buttons
3. Wait for your decision (default: 1 hour timeout)
4. Proceed or halt based on your choice

## Prerequisites

You already have:
- ✅ Telegram bot: **@CodeSherpaBot** (Display name: CodeCompassBot)
- ✅ ngrok tunnel: `https://harrybot.ngrok.app`
- ✅ Local port: 5678

## Step 1: Get Your Bot Token

1. Open Telegram and message **@BotFather**
2. Send `/mybots`
3. Select **CodeSherpaBot**
4. Click **API Token** to reveal your bot token
5. Copy the token (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

## Step 2: Get Your Chat ID

### Option A: Using the Helper Function

```bash
cd c:/dev/Autopack
PYTHONUTF8=1 PYTHONPATH=src python -c "
from autopack.notifications.telegram_notifier import get_my_chat_id
import os
os.environ['TELEGRAM_BOT_TOKEN'] = 'YOUR_BOT_TOKEN_HERE'
chat_id = get_my_chat_id(os.environ['TELEGRAM_BOT_TOKEN'])
print(f'Your Chat ID: {chat_id}')
"
```

### Option B: Manual Method

1. Send any message to **@CodeSherpaBot** on Telegram
2. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Look for `"chat":{"id":123456789}` in the JSON response
4. Copy the numeric ID

## Step 3: Set Environment Variables

Add these to your environment (or `.env` file):

```bash
# Required
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
TELEGRAM_CHAT_ID="123456789"

# Optional (defaults shown)
AUTOPACK_CALLBACK_URL="http://localhost:8001"
NGROK_URL="https://harrybot.ngrok.app"
```

### Windows (PowerShell)
```powershell
$env:TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
$env:TELEGRAM_CHAT_ID="123456789"
$env:NGROK_URL="https://harrybot.ngrok.app"
```

### Linux/Mac (Bash)
```bash
export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
export TELEGRAM_CHAT_ID="123456789"
export NGROK_URL="https://harrybot.ngrok.app"
```

## Step 4: Set Up Telegram Webhook

This tells Telegram to POST button clicks to your Autopack server via ngrok.

```bash
cd c:/dev/Autopack
PYTHONUTF8=1 PYTHONPATH=src python -c "
from autopack.notifications.telegram_notifier import setup_telegram_webhook
import os

bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
ngrok_url = os.getenv('NGROK_URL', 'https://harrybot.ngrok.app')

success = setup_telegram_webhook(bot_token, ngrok_url)
if success:
    print('✅ Webhook configured successfully!')
    print(f'Telegram will POST to: {ngrok_url}/telegram/webhook')
else:
    print('❌ Failed to set webhook')
"
```

Expected output:
```
✅ Webhook configured successfully!
Telegram will POST to: https://harrybot.ngrok.app/telegram/webhook
```

## Step 5: Start ngrok Tunnel

Make sure ngrok is running and forwarding to your backend server:

```bash
# Forward to backend server (port 8000 or 8001)
ngrok http --domain=harrybot.ngrok.app 8001
```

**Important**: The backend server must be accessible at the ngrok URL for webhooks to work.

## Step 6: Start Backend Server

```bash
cd c:/dev/Autopack
PYTHONUTF8=1 PYTHONPATH=src uvicorn autopack.main:app --host 0.0.0.0 --port 8000 --reload
```

## Step 7: Test the Integration

### Manual Test

```bash
cd c:/dev/Autopack
PYTHONUTF8=1 PYTHONPATH=src python -c "
from autopack.notifications.telegram_notifier import TelegramNotifier

notifier = TelegramNotifier()

if notifier.is_configured():
    deletion_info = {
        'net_deletion': 426,
        'loc_removed': 426,
        'loc_added': 0,
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

    if success:
        print('✅ Test notification sent! Check your phone.')
    else:
        print('❌ Failed to send notification')
else:
    print('❌ Telegram not configured. Check environment variables.')
"
```

You should receive a message like this on your phone:

```
⚠️ Autopack Approval Needed

Phase: test-phase
Run: test-run
Risk: 🚨 CRITICAL (score: 85/100)
Net Deletion: 426 lines
  ├─ Removed: 426
  └─ Added: 0

Files:
  • src/autopack/diagnostics/deep_retrieval.py

⚠️ Troubleshooting context: Large deletions unexpected

Sent: 2025-12-21 03:00:00 UTC

[✅ Approve]  [❌ Reject]
[📊 Show Details]
```

### Tap the Buttons

1. Tap **✅ Approve** → Should see "✅ Approved!" confirmation
2. Tap **❌ Reject** → Should see "❌ Rejected!" confirmation

Check backend logs to verify webhook received the callback.

## Step 8: Configure Risk Thresholds (Optional)

Edit `src/autopack/risk_scorer.py` to customize when approval is required:

```python
# Current default: block if net deletion > 300 lines
# You can adjust based on context

# For troubleshooting (strict)
if context == "troubleshoot" and net_deletion > 50:
    quality_level = "blocked"

# For refactoring (lenient)
if context == "refactor" and net_deletion > 300:
    quality_level = "blocked"
```

## How It Works

### Approval Flow

1. **Executor detects high-risk change**
   - Large deletion (> 300 lines)
   - Critical risk score (≥ 70)
   - Quality gate returns `is_blocked() = True`

2. **Executor calls `/approval/request` API**
   ```python
   approval_granted = self._request_human_approval(
       phase_id=phase_id,
       quality_report=quality_report,
       timeout_seconds=3600  # 1 hour
   )
   ```

3. **Backend sends Telegram notification**
   - `TelegramNotifier.send_approval_request()`
   - Message includes risk details, deletion counts, affected files
   - Inline keyboard with Approve/Reject buttons

4. **User taps button on phone**
   - Telegram POSTs to `https://harrybot.ngrok.app/telegram/webhook`
   - Webhook parses `callback_data: "approve:phase_id"` or `"reject:phase_id"`
   - Calls `/approval/approve/{phase_id}` or `/approval/reject/{phase_id}`

5. **Executor polls for decision**
   - Checks `/approval/status/{phase_id}` every 10 seconds
   - Returns `True` (approved) or `False` (rejected/timeout)

6. **Executor proceeds or halts**
   - If approved: phase continues
   - If rejected/timeout: phase marked as `BLOCKED`

### Webhook Endpoint

```
POST https://harrybot.ngrok.app/telegram/webhook

Body (from Telegram):
{
  "callback_query": {
    "id": "123456789",
    "data": "approve:diagnostics-phase-1",
    "from": {
      "id": 123456789,
      "username": "your_username"
    }
  }
}
```

Backend parses `callback_data`, calls appropriate endpoint, answers callback to remove loading state.

## Troubleshooting

### No notification received

1. **Check environment variables**:
   ```bash
   echo $TELEGRAM_BOT_TOKEN
   echo $TELEGRAM_CHAT_ID
   ```

2. **Test bot token**:
   ```bash
   curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe"
   ```
   Should return bot details.

3. **Test chat ID**:
   Send a message to @CodeSherpaBot, then:
   ```bash
   curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getUpdates"
   ```
   Verify your chat ID appears.

### Buttons don't work

1. **Check webhook URL**:
   ```bash
   curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"
   ```
   Should show: `"url": "https://harrybot.ngrok.app/telegram/webhook"`

2. **Check ngrok is running**:
   ```bash
   curl https://harrybot.ngrok.app/approval/status/test-phase
   ```
   Should return 404 (not connection error).

3. **Check backend logs** for webhook events:
   ```
   [Telegram] Webhook received: {...}
   [Approval] Phase test-phase APPROVED
   ```

### Backend not accessible

1. **Check ngrok tunnel**:
   ```bash
   ngrok http --domain=harrybot.ngrok.app 8001
   ```

2. **Verify backend port**:
   ```bash
   netstat -ano | findstr :8001  # Windows
   lsof -i :8001                 # Linux/Mac
   ```

3. **Test locally first**:
   ```bash
   curl http://localhost:8001/approval/status/test-phase
   ```

### Timeout issues

- Default timeout: 1 hour (3600 seconds)
- Adjust in `autonomous_executor.py`:
  ```python
  approval_granted = self._request_human_approval(
      phase_id=phase_id,
      quality_report=quality_report,
      timeout_seconds=7200  # 2 hours
  )
  ```

## Security Notes

1. **Keep your bot token secret** - Never commit to git
2. **Use ngrok auth token** for stable domains
3. **Consider IP whitelisting** in production
4. **Validate webhook signatures** (advanced - see Telegram docs)

## Advanced: Manual Approval (Without Telegram)

If Telegram is not configured, you can still manually approve via API:

```bash
# Approve
curl -X POST http://localhost:8001/approval/approve/phase_id

# Reject
curl -X POST http://localhost:8001/approval/reject/phase_id
```

Or create approval files (legacy method):
```bash
touch .autonomous_runs/<run_id>/approval_granted_<phase_id>.txt
```

## References

- Telegram Bot API: https://core.telegram.org/bots/api
- ngrok Documentation: https://ngrok.com/docs
- Webhook Guide: https://core.telegram.org/bots/webhooks

## Support

If you encounter issues:
1. Check backend logs: `src/backend/logs/` or console output
2. Check executor logs: `.autonomous_runs/<run_id>/executor.log`
3. Enable debug logging: `export LOG_LEVEL=DEBUG`
