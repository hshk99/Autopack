# ngrok Setup Guide for Telegram Approval Buttons

## Current Status

✅ **Already Working (No ngrok needed):**
- Telegram notifications for large deletions (100-200 lines)
- Blocking of critical deletions (200+ lines)
- Automatic save points before deletions >50 lines
- Phase failure notifications

🔘 **Optional Feature (Requires ngrok):**
- Interactive approve/reject buttons in Telegram messages

## Quick Setup (3 Steps)

### Step 1: Get Your ngrok Authtoken

Since you already have the `harrybot.ngrok.app` domain, you need your ngrok authtoken:

1. Go to: https://dashboard.ngrok.com/get-started/your-authtoken
2. Copy your authtoken (format: `2abc...xyz`)
3. Run this command in PowerShell:

```powershell
cd C:\dev\Autopack
.\ngrok.exe config add-authtoken YOUR_AUTHTOKEN_HERE
```

### Step 2: Start ngrok Tunnel

In **PowerShell Terminal 1**, run:

```powershell
cd C:\dev\Autopack
.\ngrok.exe http --domain=harrybot.ngrok.app 8001
```

Leave this running. You should see:
```
Forwarding  https://harrybot.ngrok.app -> http://localhost:8001
```

### Step 3: Start Backend Server

In **PowerShell Terminal 2**, run:

```powershell
cd C:\dev\Autopack
$env:PYTHONUTF8=1
$env:PYTHONPATH="src"
python -m uvicorn backend.main:app --port 8001
```

Leave this running. You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8001
```

## Testing Interactive Buttons

Once both terminals are running, test the approval workflow:

```powershell
cd C:\dev\Autopack
python scripts\test_deletion_safeguards.py --test-approval
```

This will:
1. Send a test approval request to your Telegram
2. Show approve/reject buttons
3. Poll for your decision
4. Report whether you approved or rejected

## Troubleshooting

### "ngrok authtoken required"
You haven't added your authtoken yet. Run Step 1.

### "Failed to listen on port 8001"
Another process is using port 8001. Check with:
```powershell
netstat -ano | findstr :8001
```

### Buttons don't appear in Telegram
- Verify ngrok is running and shows `https://harrybot.ngrok.app`
- Verify backend is running on port 8001
- Check backend logs for errors

## Do You Need This?

**No, you don't need ngrok to use Autopack's deletion safeguards!**

The core safety features work perfectly without ngrok:
- You'll get Telegram notifications for large deletions
- Autopack will automatically block deletions >200 lines
- Save points are created automatically

Interactive buttons are just a convenience for mobile approval. You can always approve/reject via the dashboard at `http://localhost:8001/dashboard` on your computer.
