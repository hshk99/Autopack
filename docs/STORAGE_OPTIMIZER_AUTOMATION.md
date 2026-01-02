# Storage Optimizer Automation Guide

## Overview

The Storage Optimizer includes a scheduled scan system for automated weekly storage analysis with delta reporting. This system runs unattended scans, generates "what changed since last scan" reports, and optionally sends notifications.

**Key Features:**
- ✅ Automated weekly scans via Task Scheduler (Windows) or cron (Linux)
- ✅ Delta reporting: track new/removed cleanup opportunities
- ✅ Optional Telegram notifications
- ✅ JSON + text report generation
- ✅ NO automatic deletion (requires explicit approval)

## Quick Start

### Manual Execution

```bash
# Run scan with default settings
python scripts/storage/scheduled_scan.py --root C:/dev

# Custom scan name
python scripts/storage/scheduled_scan.py --root C:/ --name "monthly-scan-2026-01"

# Enable Telegram notifications
python scripts/storage/scheduled_scan.py --root C:/dev --notify
```

### Windows Task Scheduler Setup

**Option 1: PowerShell Command**
```powershell
# Create weekly scan task (runs every Sunday at 2:00 AM)
schtasks /create /tn "Storage Weekly Scan" /tr "python C:/dev/Autopack/scripts/storage/scheduled_scan.py --root C:/dev --notify" /sc weekly /d SUN /st 02:00
```

**Option 2: Task Scheduler GUI**
1. Open Task Scheduler (`taskschd.msc`)
2. Create Basic Task → "Storage Optimizer Weekly Scan"
3. Trigger: Weekly, Sunday, 2:00 AM
4. Action: Start a program
   - Program: `python.exe` (or full path: `C:\Python\python.exe`)
   - Arguments: `C:/dev/Autopack/scripts/storage/scheduled_scan.py --root C:/dev --notify`
   - Start in: `C:/dev/Autopack`

**Verify Task**:
```powershell
# List scheduled tasks
schtasks /query /tn "Storage Weekly Scan"

# Run task manually (test)
schtasks /run /tn "Storage Weekly Scan"
```

### Linux cron Setup

```bash
# Edit crontab
crontab -e

# Add entry (every Sunday at 2:00 AM)
0 2 * * 0 cd /path/to/autopack && python scripts/storage/scheduled_scan.py --root /home --notify
```

**Cron Schedule Examples:**
- `0 2 * * 0` - Every Sunday at 2:00 AM
- `0 3 * * 1` - Every Monday at 3:00 AM
- `0 2 1 * *` - First day of every month at 2:00 AM

## Delta Reporting

### What is Delta Reporting?

Delta reporting compares the current scan with the previous scan for the same target path to show:
- **New cleanup opportunities**: Files/folders that appeared since last scan
- **Removed opportunities**: Files/folders that were deleted or cleaned up
- **Per-category changes**: Category-level breakdown of changes
- **Size change**: Net change in potential savings (GB)

### Sample Delta Report

```
================================================================================
STORAGE OPTIMIZER - WEEKLY SCAN DELTA REPORT
================================================================================
Scan Date: 2026-01-02 06:56 UTC
Current Scan ID: 9
Previous Scan ID: 8
Previous Scan Date: 2026-01-02 06:54 UTC

--------------------------------------------------------------------------------
CHANGES SINCE LAST SCAN
--------------------------------------------------------------------------------
New cleanup opportunities:     10 files/folders
Removed opportunities:         0 files/folders
Net size change:               +0.00 GB

Per-Category Changes:
  dev_caches:
    Count: 0 → 10 (+10)
    Size:  0.00 GB → 0.00 GB (+0.00 GB)

Sample New Cleanup Opportunities (first 10):
  + C:/temp/storage_canary_test\project2\node_modules\pkg_6.tmp
  + C:/temp/storage_canary_test\project2\node_modules\pkg_2.tmp
  ...

================================================================================
NEXT STEPS
================================================================================
1. Review candidates: http://localhost:8000/storage/scans/9
2. Approve via API or interactive mode:
   python scripts/storage/scan_and_report.py --scan-id 9 --interactive
3. Execute approved deletions:
   python scripts/storage/scan_and_report.py --scan-id 9 --execute --category dev_caches
```

### Delta Report Output Locations

**Text Reports** (human-readable):
```
archive/reports/storage/weekly/weekly_delta_YYYYMMDD_HHMMSS.txt
```

**JSON Reports** (machine-parseable):
```
archive/reports/storage/weekly/weekly_delta_YYYYMMDD_HHMMSS.json
```

### JSON Report Structure

```json
{
  "timestamp": "2026-01-02T06:56:12.561285+00:00",
  "current_scan_id": 9,
  "previous_scan_id": 8,
  "delta": {
    "is_first_scan": false,
    "new_candidates": 10,
    "removed_candidates": 0,
    "size_change_gb": 0.00015,
    "category_changes": {
      "dev_caches": {
        "current_count": 10,
        "previous_count": 0,
        "delta_count": 10,
        "delta_size_gb": 0.00015
      }
    },
    "new_paths_sample": [...],
    "removed_paths_sample": [...]
  },
  "current_scan_summary": {
    "total_candidates": 10,
    "total_size_gb": 0.00015,
    "scan_target": "C:/temp/storage_canary_test",
    "scan_time": "2026-01-02T06:56:12.522683"
  }
}
```

## Telegram Notifications

### Setup

1. **Create Telegram Bot**:
   - Message [@BotFather](https://t.me/BotFather) on Telegram
   - Send `/newbot` and follow prompts
   - Save the bot token (e.g., `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

2. **Get Chat ID**:
   - Message your bot
   - Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
   - Find `"chat":{"id":123456789}` in the JSON response

3. **Configure Environment Variables**:
   ```bash
   # Windows (PowerShell)
   $env:TELEGRAM_BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
   $env:TELEGRAM_CHAT_ID = "123456789"

   # Linux/macOS (bash)
   export TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
   export TELEGRAM_CHAT_ID="123456789"
   ```

4. **Persist Environment Variables (Windows)**:
   - System Properties → Advanced → Environment Variables
   - Add user variables:
     - `TELEGRAM_BOT_TOKEN` = `your_token`
     - `TELEGRAM_CHAT_ID` = `your_chat_id`

### Notification Format

```
📊 *Storage Optimizer Weekly Scan*

📅 Scan: 2026-01-02
🆔 Scan ID: 9

📈 *Changes Since Last Week*

New opportunities: 10
Removed: 0
Size change: +0.00 GB

💾 Potential savings: 0.00 GB

🔗 Review: http://localhost:8000/storage/scans/9
```

### Testing Notifications

```bash
# Test notification (requires credentials configured)
python scripts/storage/scheduled_scan.py --root C:/temp --notify
```

**Expected Output**:
- ✅ Telegram notification sent (if credentials valid)
- ⚠️  Telegram notification not sent (if credentials missing/invalid)

## Command-Line Options

```bash
python scripts/storage/scheduled_scan.py [OPTIONS]

Options:
  --root PATH           Root directory to scan (default: C:/)
  --name NAME           Scan name (default: weekly-scan-YYYYMMDD)
  --notify              Send Telegram notification (requires env vars)
  --output-dir PATH     Directory to save reports (default: archive/reports/storage/weekly)
```

## Environment Variables

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `DATABASE_URL` | No | PostgreSQL/SQLite connection string | `sqlite:///autopack.db` |
| `TELEGRAM_BOT_TOKEN` | No* | Telegram bot token | `123456789:ABC...` |
| `TELEGRAM_CHAT_ID` | No* | Telegram chat ID | `123456789` |

\* Required only if using `--notify` flag

## Workflow

### Automated Weekly Scan Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Task Scheduler triggers script every Sunday at 2:00 AM  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Load storage policy (config/storage_policy.yaml)        │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Scan target directory (max_depth=3)                     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. Classify candidates using policy rules                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. Save scan + candidates to database                      │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 6. Compare with previous scan (delta computation)          │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 7. Generate text + JSON delta reports                      │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 8. Send Telegram notification (optional)                   │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ 9. Wait for manual review/approval (NO auto-deletion)      │
└─────────────────────────────────────────────────────────────┘
```

### Manual Review and Approval

After receiving the weekly report, review and approve candidates:

```bash
# Interactive approval (category by category)
python scripts/storage/scan_and_report.py --scan-id 9 --interactive

# Execute approved deletions
python scripts/storage/scan_and_report.py --scan-id 9 --execute --category dev_caches
```

## Troubleshooting

### Task Not Running

**Windows Task Scheduler**:
```powershell
# Check task status
schtasks /query /tn "Storage Weekly Scan" /fo LIST /v

# View task history
# Task Scheduler GUI → View → Show Task History
```

**Common Issues**:
- Task runs but nothing happens → Check "Start in" directory is set to Autopack root
- Permission denied → Run task as Administrator
- Python not found → Use full path to `python.exe` in task

### Delta Report Shows No Changes

- Verify scan target path is consistent (`C:/dev` vs `C:\dev` vs `c:/dev`)
- Check database for previous scans: `SELECT id, scan_target, timestamp FROM storage_scans ORDER BY timestamp DESC LIMIT 5;`

### Telegram Notifications Not Sent

```bash
# Verify credentials
echo $env:TELEGRAM_BOT_TOKEN  # Windows
echo $TELEGRAM_BOT_TOKEN      # Linux

# Test bot token manually
curl https://api.telegram.org/bot<YOUR_TOKEN>/getMe
```

**Common Issues**:
- Bot token invalid → Verify with BotFather
- Chat ID wrong → Re-run `/getUpdates` after messaging bot
- Firewall blocking → Check port 443 outbound access

## Best Practices

### Scan Scheduling

- **Weekly scans**: Ideal for developer workstations (captures weekly project churn)
- **Monthly scans**: Better for stable servers or infrequent file changes
- **Off-hours scheduling**: Run at 2-4 AM to avoid disrupting active work

### Scan Targets

- **Developer workstation**: `C:/dev` (project directories only)
- **Full disk scan**: `C:/` (comprehensive but slower)
- **Multi-target strategy**: Run separate tasks for different targets
  - Daily: `C:/Users/<username>/AppData/Local/Temp` (temp files)
  - Weekly: `C:/dev` (project caches)
  - Monthly: `C:/` (full disk)

### Retention Policy

- Keep delta reports for **90 days**
- Archive older reports to compressed storage
- Database scans: retain indefinitely (or apply custom retention via `docs/DATA_RETENTION_AND_STORAGE_POLICY.md`)

## Next Steps

1. **Review weekly delta reports** to identify storage trends
2. **Approve high-confidence candidates** via interactive mode
3. **Execute deletions** during low-activity periods (evenings/weekends)
4. **Monitor freed space** over time to validate cleanup effectiveness
5. **Adjust policy** based on learned patterns (see [docs/STORAGE_OPTIMIZER_INTELLIGENCE_COMPLETE.md](STORAGE_OPTIMIZER_INTELLIGENCE_COMPLETE.md))

## See Also

- [Storage Optimizer MVP Completion](STORAGE_OPTIMIZER_MVP_COMPLETION.md) - Core execution features
- [Storage Optimizer Intelligence](STORAGE_OPTIMIZER_INTELLIGENCE_COMPLETE.md) - Pattern learning and smart categorization
- [Data Retention and Storage Policy](DATA_RETENTION_AND_STORAGE_POLICY.md) - Retention configuration
- [Troubleshooting Guide](TROUBLESHOOTING.md) - Windows lock handling, permission issues
