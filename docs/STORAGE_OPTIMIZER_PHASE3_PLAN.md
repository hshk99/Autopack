# Storage Optimizer Phase 3 - Automation & Performance

**BUILD-150 Phase 3: Scheduled Scans, WizTree Integration, Telegram Notifications**
**Status**: 🔨 IN PROGRESS
**Date**: 2026-01-01
**Prerequisites**: BUILD-148 (MVP), BUILD-149 (Phase 2)

---

## Executive Summary

Phase 3 extends Storage Optimizer with automation, performance, and mobile notification capabilities:
- **WizTree Integration**: 30-50x faster scanning via MFT reading
- **Windows Task Scheduler**: Automated fortnightly scans
- **Telegram Notifications**: Mobile alerts with inline approval buttons

**Key Achievement**: Fully automated disk cleanup workflow with zero manual intervention.

---

## Goals

### Primary Goals (Phase 3)

1. **WizTree CLI Integration** - 30-50x faster disk scanning
   - Wrap WizTree64.exe CLI for NTFS drives
   - Parse CSV export format into ScanResult objects
   - Fallback to Python scanner for non-NTFS/missing WizTree
   - Cache results for 6-hour TTL

2. **Windows Task Scheduler Integration** - Automated scans
   - Create scheduled task for fortnightly execution
   - Align with Tidy schedule (every 2 weeks)
   - Email/Telegram notification on completion
   - Configurable via CLI flag

3. **Telegram Notification System** - Mobile approval workflow
   - Adapt existing TelegramNotifier for storage scans
   - Send scan completion summary
   - Inline buttons for approval (approve/defer/reject)
   - Webhook integration for button callbacks

### Success Metrics

- ✅ WizTree scans 1TB drive in < 30 seconds (vs. 15 minutes with Python)
- ✅ Scheduled task runs successfully every 2 weeks
- ✅ Telegram notifications delivered within 10 seconds
- ✅ Approval workflow completes within 5 minutes
- ✅ Zero manual intervention for routine cleanups

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   Storage Optimizer Phase 3                  │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐      ┌──────────────┐      ┌────────────┐ │
│  │   WizTree    │      │   Windows    │      │  Telegram  │ │
│  │  Wrapper     │──────│   Task       │──────│  Notifier  │ │
│  │              │      │  Scheduler   │      │            │ │
│  └──────────────┘      └──────────────┘      └────────────┘ │
│         │                     │                      │       │
│         │                     │                      │       │
│         v                     v                      v       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Storage Optimizer Core (Phase 2)           │   │
│  │   (Scanner → Classifier → Executor → DB)             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
1. Scheduled Task Trigger (fortnightly)
   └─> Run: python scripts/storage/scan_and_report.py --save-to-db --notify

2. WizTree Scanner
   ├─> Check if WizTree installed
   ├─> Run: wiztree64.exe C:\ /export="scan.csv"
   ├─> Parse CSV → ScanResult[]
   └─> Fallback to Python scanner if failed

3. Classification & Persistence
   ├─> FileClassifier.classify_batch(results)
   ├─> Save to PostgreSQL (storage_scans table)
   └─> Return scan_id

4. Telegram Notification
   ├─> Format summary (candidates, GB saved, categories)
   ├─> Send to user via bot
   ├─> Inline keyboard: [Approve All] [View Details] [Skip]
   └─> Wait for callback (webhook)

5. Approval Workflow
   ├─> User taps [Approve All]
   ├─> Telegram → ngrok → /storage/scans/{scan_id}/approve
   ├─> Update approval_decisions table
   └─> Send confirmation message

6. Execution (if approved)
   ├─> Run: python scripts/storage/scan_and_report.py --execute --scan-id {id}
   ├─> CleanupExecutor.execute_approved_candidates()
   ├─> Send2trash → Recycle Bin
   └─> Telegram notification: "✅ Freed 25 GB, 342 items deleted"
```

---

## Implementation Plan

### Part 1: WizTree CLI Wrapper (Performance)

**Goal**: 30-50x faster disk scanning using WizTree MFT reading

#### Files to Create

**1. `src/autopack/storage_optimizer/wiztree_scanner.py`** (NEW, ~400 lines)

```python
"""
WizTree CLI wrapper for high-performance disk scanning.

Falls back to Python-based scanner if WizTree is not installed or fails.
"""

import subprocess
import csv
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timezone
from .models import ScanResult
from .scanner import StorageScanner

logger = logging.getLogger(__name__)

class WizTreeScanner:
    """High-performance scanner using WizTree CLI."""

    def __init__(self, wiztree_path: Optional[Path] = None):
        """
        Initialize WizTree scanner.

        Args:
            wiztree_path: Path to wiztree64.exe (auto-detect if None)
        """
        self.wiztree_path = wiztree_path or self._find_wiztree()
        self.fallback_scanner = StorageScanner()

    def _find_wiztree(self) -> Optional[Path]:
        """Auto-detect WizTree installation."""
        # Check common installation paths
        possible_paths = [
            Path("C:/Program Files/WizTree/wiztree64.exe"),
            Path("C:/Program Files (x86)/WizTree/wiztree64.exe"),
            Path(os.getenv("LOCALAPPDATA", "")) / "WizTree/wiztree64.exe",
        ]

        for path in possible_paths:
            if path.exists():
                logger.info(f"[WizTree] Found at: {path}")
                return path

        logger.warning("[WizTree] Not found - will use Python fallback")
        return None

    def is_available(self) -> bool:
        """Check if WizTree is available."""
        return self.wiztree_path is not None and self.wiztree_path.exists()

    def scan_drive(
        self,
        drive_letter: str,
        max_depth: Optional[int] = None,
        max_items: int = 10000,
        admin_mode: bool = False
    ) -> List[ScanResult]:
        """
        Scan drive using WizTree CLI.

        Args:
            drive_letter: Drive letter (e.g., "C")
            max_depth: Maximum depth (WizTree scans all, filter after)
            max_items: Maximum items to return
            admin_mode: Run with admin privileges (slower, more complete)

        Returns:
            List of ScanResult objects
        """
        if not self.is_available():
            logger.warning("[WizTree] Not available, using Python fallback")
            return self.fallback_scanner.scan_drive(drive_letter, max_depth, max_items)

        try:
            # Create temp CSV file
            csv_path = Path(f"c:/temp/wiztree_scan_{drive_letter}_{int(datetime.now().timestamp())}.csv")
            csv_path.parent.mkdir(parents=True, exist_ok=True)

            # Build command
            cmd = [
                str(self.wiztree_path),
                f"{drive_letter}:\\",
                f"/export={csv_path}",
                f"/admin={'1' if admin_mode else '0'}"
            ]

            logger.info(f"[WizTree] Scanning {drive_letter}:\\ (admin={admin_mode})...")
            start_time = datetime.now()

            # Run WizTree CLI
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"[WizTree] Failed: {result.stderr}")
                return self.fallback_scanner.scan_drive(drive_letter, max_depth, max_items)

            # Parse CSV
            scan_results = self._parse_csv(csv_path, max_depth, max_items)

            duration = (datetime.now() - start_time).seconds
            logger.info(f"[WizTree] Scanned {len(scan_results)} items in {duration}s")

            # Cleanup temp file
            csv_path.unlink(missing_ok=True)

            return scan_results

        except subprocess.TimeoutExpired:
            logger.error("[WizTree] Timeout - falling back to Python scanner")
            return self.fallback_scanner.scan_drive(drive_letter, max_depth, max_items)

        except Exception as e:
            logger.error(f"[WizTree] Error: {e} - falling back to Python scanner")
            return self.fallback_scanner.scan_drive(drive_letter, max_depth, max_items)

    def _parse_csv(
        self,
        csv_path: Path,
        max_depth: Optional[int],
        max_items: int
    ) -> List[ScanResult]:
        """
        Parse WizTree CSV export into ScanResult objects.

        CSV Format:
            File Name,Size,Allocated,Modified,Attributes,%,Files,%,Allocated
        """
        results = []

        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # Skip if max_items reached
                    if len(results) >= max_items:
                        break

                    # Parse row
                    file_path = row.get('File Name', '')
                    size_bytes = int(row.get('Size', 0))
                    modified_str = row.get('Modified', '')
                    attributes = row.get('Attributes', '')

                    # Filter by depth if specified
                    if max_depth:
                        depth = file_path.count('\\') - 1  # Subtract root
                        if depth > max_depth:
                            continue

                    # Parse timestamp
                    try:
                        last_modified = datetime.strptime(modified_str, '%Y-%m-%d %H:%M:%S')
                        last_modified = last_modified.replace(tzinfo=timezone.utc)
                    except:
                        last_modified = datetime.now(timezone.utc)

                    # Create ScanResult
                    result = ScanResult(
                        path=file_path,
                        size_bytes=size_bytes,
                        is_directory='d' in attributes.lower(),
                        last_modified=last_modified,
                        is_hidden='h' in attributes.lower(),
                        is_system='s' in attributes.lower()
                    )

                    results.append(result)

        except Exception as e:
            logger.error(f"[WizTree] CSV parse error: {e}")
            raise

        return results
```

**2. Update `src/autopack/storage_optimizer/scanner.py`** (+50 lines)

Add factory method to choose scanner:

```python
def create_scanner(prefer_wiztree: bool = True) -> Union[WizTreeScanner, StorageScanner]:
    """
    Factory to create optimal scanner.

    Args:
        prefer_wiztree: Try WizTree first if available

    Returns:
        WizTreeScanner if available and preferred, else StorageScanner
    """
    if prefer_wiztree:
        from .wiztree_scanner import WizTreeScanner
        scanner = WizTreeScanner()
        if scanner.is_available():
            return scanner

    return StorageScanner()
```

**Testing**:
- ✅ Test WizTree scanner on 500GB drive (< 30 seconds)
- ✅ Test fallback when WizTree not installed
- ✅ Test CSV parsing with Unicode paths
- ✅ Test depth filtering
- ✅ Test max_items limit

---

### Part 2: Windows Task Scheduler Integration

**Goal**: Automated fortnightly scans aligned with Tidy schedule

#### Files to Create

**1. `scripts/setup_scheduled_scan.py`** (NEW, ~250 lines)

```python
"""
Set up Windows Task Scheduler for automated storage scans.

Creates a scheduled task that runs every 2 weeks (aligned with Tidy).
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime, timedelta

def create_scheduled_task(
    task_name: str = "Autopack_Storage_Scan",
    frequency_days: int = 14,
    start_time: str = "02:00",  # 2 AM
    notify: bool = True
) -> bool:
    """
    Create Windows scheduled task for storage scans.

    Args:
        task_name: Name of scheduled task
        frequency_days: Run every N days (default: 14 = fortnightly)
        start_time: Time to run (HH:MM format)
        notify: Send Telegram notification on completion

    Returns:
        True if task created successfully
    """
    # Get current Python executable and script path
    python_exe = sys.executable
    script_path = Path(__file__).parent / "storage" / "scan_and_report.py"
    autopack_root = Path(__file__).parent.parent

    # Build command
    cmd_parts = [
        f'"{python_exe}"',
        f'"{script_path}"',
        '--save-to-db',
    ]

    if notify:
        cmd_parts.append('--notify')

    cmd = ' '.join(cmd_parts)

    # Build schtasks command
    # Note: /SC DAILY with /MO 14 = every 14 days
    schtasks_cmd = [
        'schtasks',
        '/Create',
        '/TN', task_name,
        '/TR', cmd,
        '/SC', 'DAILY',
        '/MO', str(frequency_days),
        '/ST', start_time,
        '/F',  # Force create (overwrite if exists)
    ]

    try:
        result = subprocess.run(
            schtasks_cmd,
            capture_output=True,
            text=True,
            check=True
        )

        print(f"✅ Scheduled task '{task_name}' created successfully")
        print(f"   Frequency: Every {frequency_days} days at {start_time}")
        print(f"   Command: {cmd}")
        print(f"   Working directory: {autopack_root}")

        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to create scheduled task: {e.stderr}")
        return False


def list_scheduled_tasks() -> None:
    """List Autopack-related scheduled tasks."""
    try:
        result = subprocess.run(
            ['schtasks', '/Query', '/FO', 'LIST', '/V'],
            capture_output=True,
            text=True,
            check=True
        )

        # Filter for Autopack tasks
        lines = result.stdout.split('\n')
        in_autopack_task = False

        for line in lines:
            if 'Autopack' in line:
                in_autopack_task = True

            if in_autopack_task:
                print(line)

            if in_autopack_task and line.strip() == '':
                in_autopack_task = False

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to list tasks: {e.stderr}")


def delete_scheduled_task(task_name: str = "Autopack_Storage_Scan") -> bool:
    """Delete scheduled task."""
    try:
        subprocess.run(
            ['schtasks', '/Delete', '/TN', task_name, '/F'],
            capture_output=True,
            text=True,
            check=True
        )

        print(f"✅ Scheduled task '{task_name}' deleted")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to delete task: {e.stderr}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manage scheduled storage scans")
    parser.add_argument('--create', action='store_true', help="Create scheduled task")
    parser.add_argument('--delete', action='store_true', help="Delete scheduled task")
    parser.add_argument('--list', action='store_true', help="List scheduled tasks")
    parser.add_argument('--frequency-days', type=int, default=14, help="Run every N days")
    parser.add_argument('--start-time', default='02:00', help="Start time (HH:MM)")
    parser.add_argument('--no-notify', action='store_true', help="Disable notifications")

    args = parser.parse_args()

    if args.create:
        create_scheduled_task(
            frequency_days=args.frequency_days,
            start_time=args.start_time,
            notify=not args.no_notify
        )
    elif args.delete:
        delete_scheduled_task()
    elif args.list:
        list_scheduled_tasks()
    else:
        parser.print_help()
```

**2. Update `scripts/storage/scan_and_report.py`** (+50 lines)

Add `--notify` flag to send Telegram notification on completion:

```python
parser.add_argument(
    "--notify",
    action="store_true",
    help="Send Telegram notification on completion (Phase 3)"
)

# At end of main()
if args.notify and saved_scan:
    send_scan_completion_notification(saved_scan, db_session)
```

**Testing**:
- ✅ Create scheduled task via script
- ✅ Verify task appears in Task Scheduler
- ✅ Test manual trigger (schtasks /Run /TN Autopack_Storage_Scan)
- ✅ Verify task runs at scheduled time
- ✅ Check logs for errors

---

### Part 3: Telegram Notification System

**Goal**: Mobile alerts for scan completion with inline approval

#### Files to Create

**1. `src/autopack/storage_optimizer/telegram_notifications.py`** (NEW, ~300 lines)

```python
"""
Telegram notifications for Storage Optimizer.

Extends existing TelegramNotifier for storage-specific workflows.
"""

import logging
from typing import Dict, Optional
from datetime import datetime
from autopack.notifications.telegram_notifier import TelegramNotifier
from autopack.models import StorageScan
from .db import get_candidate_stats_by_category

logger = logging.getLogger(__name__)


class StorageTelegramNotifier(TelegramNotifier):
    """Telegram notifications for storage scans."""

    def send_scan_completion(
        self,
        scan: StorageScan,
        category_stats: Dict[str, Dict]
    ) -> bool:
        """
        Send scan completion notification with approval buttons.

        Args:
            scan: StorageScan database record
            category_stats: Stats by category from get_candidate_stats_by_category()

        Returns:
            True if notification sent successfully
        """
        if not self.is_configured():
            logger.error("[Telegram] Not configured - cannot send scan notification")
            return False

        # Format message
        message = self._format_scan_summary(scan, category_stats)

        # Create inline keyboard
        keyboard = {
            "inline_keyboard": [
                [
                    {
                        "text": "✅ Approve All",
                        "callback_data": f"storage_approve_all:{scan.id}"
                    },
                    {
                        "text": "👀 View Details",
                        "callback_data": f"storage_details:{scan.id}"
                    }
                ],
                [
                    {
                        "text": "⏭️ Skip This Scan",
                        "callback_data": f"storage_skip:{scan.id}"
                    }
                ]
            ]
        }

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

            response = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "reply_markup": keyboard
            }, timeout=10)

            if response.status_code == 200:
                logger.info(f"[Telegram] Scan notification sent for scan {scan.id}")
                return True
            else:
                logger.error(f"[Telegram] API error: {response.status_code} {response.text}")
                return False

        except Exception as e:
            logger.error(f"[Telegram] Failed to send scan notification: {e}")
            return False

    def send_execution_complete(
        self,
        scan_id: int,
        total_freed_bytes: int,
        successful: int,
        failed: int
    ) -> bool:
        """Send execution completion notification."""
        if not self.is_configured():
            return False

        freed_gb = total_freed_bytes / (1024**3)

        message = (
            f"✅ *Storage Cleanup Complete*\n\n"
            f"Scan ID: `{scan_id}`\n"
            f"Freed: {freed_gb:.2f} GB\n"
            f"Successful: {successful} items\n"
            f"Failed: {failed} items\n\n"
            f"_Deleted items are in Recycle Bin (can be restored)_"
        )

        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            response = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }, timeout=10)

            return response.status_code == 200

        except Exception as e:
            logger.error(f"[Telegram] Failed to send execution notification: {e}")
            return False

    def _format_scan_summary(
        self,
        scan: StorageScan,
        category_stats: Dict[str, Dict]
    ) -> str:
        """Format scan summary message."""

        potential_savings_gb = scan.potential_savings_bytes / (1024**3)

        # Category breakdown
        category_lines = []
        for category, stats in category_stats.items():
            count = stats['count']
            size_gb = stats['total_size_bytes'] / (1024**3)
            category_lines.append(f"  • {category}: {count} items ({size_gb:.1f} GB)")

        category_summary = "\n".join(category_lines) if category_lines else "  _No cleanup candidates_"

        message = (
            f"📊 *Storage Scan Complete*\n\n"
            f"Target: `{scan.scan_target}`\n"
            f"Scanned: {scan.total_items_scanned:,} items\n"
            f"Total Size: {scan.total_size_bytes / (1024**3):.1f} GB\n\n"
            f"💾 *Cleanup Opportunities*\n"
            f"Potential Savings: {potential_savings_gb:.2f} GB\n"
            f"Candidates: {scan.cleanup_candidates_count} items\n\n"
            f"*By Category*:\n{category_summary}\n\n"
            f"_Scan ID: {scan.id} • {scan.timestamp.strftime('%Y-%m-%d %H:%M')}_"
        )

        return message
```

**2. Update `src/autopack/main.py`** (+100 lines)

Add webhook endpoint for Telegram button callbacks:

```python
@app.post("/telegram/webhook")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle Telegram button callbacks for storage scans.

    Callback data formats:
    - storage_approve_all:{scan_id}
    - storage_details:{scan_id}
    - storage_skip:{scan_id}
    """
    body = await request.json()

    callback_query = body.get("callback_query")
    if not callback_query:
        return {"ok": True}

    callback_data = callback_query.get("data", "")
    callback_id = callback_query.get("id")

    # Parse callback
    if callback_data.startswith("storage_approve_all:"):
        scan_id = int(callback_data.split(":")[1])

        # Approve all candidates for this scan
        from autopack.storage_optimizer.db import (
            get_cleanup_candidates_by_scan,
            create_approval_decision
        )

        candidates = get_cleanup_candidates_by_scan(db, scan_id)
        candidate_ids = [c.id for c in candidates]

        approval = create_approval_decision(
            db,
            scan_id=scan_id,
            candidate_ids=candidate_ids,
            approved_by="telegram_user",
            decision="approve",
            approval_method="telegram",
            notes="Approved via Telegram inline button"
        )
        db.commit()

        # Answer callback (remove loading state)
        answer_telegram_callback(callback_id, "✅ Approved! Cleanup will start soon.")

        # TODO: Trigger execution in background task

    elif callback_data.startswith("storage_details:"):
        scan_id = int(callback_data.split(":")[1])

        # Send detailed breakdown
        answer_telegram_callback(
            callback_id,
            f"View details: http://localhost:8000/storage/scans/{scan_id}"
        )

    elif callback_data.startswith("storage_skip:"):
        scan_id = int(callback_data.split(":")[1])
        answer_telegram_callback(callback_id, "⏭️ Scan skipped")

    return {"ok": True}


def answer_telegram_callback(callback_id: str, text: str) -> None:
    """Answer Telegram callback query."""
    import os
    import requests

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return

    url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
    requests.post(url, json={
        "callback_query_id": callback_id,
        "text": text,
        "show_alert": False
    })
```

**3. Add helper function to `scripts/storage/scan_and_report.py`** (+30 lines)

```python
def send_scan_completion_notification(scan, db):
    """Send Telegram notification after scan completes."""
    from autopack.storage_optimizer.telegram_notifications import StorageTelegramNotifier
    from autopack.storage_optimizer.db import get_candidate_stats_by_category

    notifier = StorageTelegramNotifier()

    if not notifier.is_configured():
        print("[Telegram] Not configured - skipping notification")
        return

    # Get category stats
    stats = get_candidate_stats_by_category(db, scan.id)

    # Send notification
    success = notifier.send_scan_completion(scan, stats)

    if success:
        print(f"[Telegram] Notification sent for scan {scan.id}")
    else:
        print(f"[Telegram] Failed to send notification")
```

**Testing**:
- ✅ Test notification sent after scan
- ✅ Test Approve All button updates database
- ✅ Test webhook receives callbacks correctly
- ✅ Test execution completion notification

---

## Configuration

### Environment Variables

```bash
# WizTree (optional)
WIZTREE_PATH="C:/Program Files/WizTree/wiztree64.exe"  # Auto-detected if not set

# Telegram (required for notifications)
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
TELEGRAM_CHAT_ID="123456789"

# ngrok (required for webhook)
NGROK_URL="https://your-domain.ngrok.app"
```

### Policy Updates (config/storage_policy.yaml)

No changes required - existing policy supports all Phase 3 features.

---

## Usage Examples

### 1. One-Time WizTree Scan

```bash
python scripts/storage/scan_and_report.py --wiztree --save-to-db --notify
```

### 2. Set Up Scheduled Scans

```bash
# Create scheduled task (every 2 weeks at 2 AM)
python scripts/setup_scheduled_scan.py --create

# List scheduled tasks
python scripts/setup_scheduled_scan.py --list

# Delete scheduled task
python scripts/setup_scheduled_scan.py --delete
```

### 3. Manual Approval via Telegram

After receiving notification on phone:
1. Tap **✅ Approve All** → Approves all candidates
2. Tap **👀 View Details** → Opens scan details in browser
3. Tap **⏭️ Skip This Scan** → Dismisses notification

### 4. Execute After Approval

```bash
# Automatic execution (if scheduled task includes --execute flag)
python scripts/storage/scan_and_report.py --execute --scan-id 123 --notify

# Manual execution
python scripts/storage/scan_and_report.py --execute --scan-id 123 --dry-run=false
```

---

## Testing Plan

### Unit Tests (8 new tests)

**tests/test_wiztree_scanner.py**:
- `test_wiztree_auto_detect`
- `test_wiztree_scan_drive`
- `test_wiztree_csv_parse`
- `test_wiztree_fallback_when_not_installed`
- `test_wiztree_unicode_paths`

**tests/test_storage_telegram.py**:
- `test_send_scan_completion_notification`
- `test_telegram_approve_callback`
- `test_telegram_execution_notification`

### Integration Tests (5 new tests)

**tests/integration/test_scheduled_scan.py**:
- `test_create_scheduled_task`
- `test_scheduled_task_execution`
- `test_wiztree_to_database_workflow`
- `test_telegram_approval_workflow_end_to_end`
- `test_scheduled_scan_with_notification`

### Manual Testing Checklist

- [ ] Install WizTree, verify auto-detection
- [ ] Run WizTree scan on 1TB drive, verify < 30 seconds
- [ ] Test fallback when WizTree not installed
- [ ] Create scheduled task, verify appears in Task Scheduler
- [ ] Trigger scheduled task manually, verify execution
- [ ] Set up Telegram webhook, test notification delivery
- [ ] Tap Approve All button, verify candidates approved
- [ ] Execute approved cleanup, verify Telegram completion notice
- [ ] Verify full workflow: scheduled scan → notification → approval → execution

---

## Migration Guide

### From Phase 2 to Phase 3

1. **Install WizTree** (optional, recommended):
   ```bash
   # Download from https://www.diskanalyzer.com/download
   # Install to default location (C:\Program Files\WizTree)
   # Or set WIZTREE_PATH environment variable
   ```

2. **Configure Telegram** (optional, for mobile notifications):
   ```bash
   # See archive/superseded/scripts/unsorted/TELEGRAM_APPROVAL_SETUP.md
   export TELEGRAM_BOT_TOKEN="YOUR_TOKEN"
   export TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
   export NGROK_URL="https://your-domain.ngrok.app"

   # Set up webhook
   python -c "from autopack.notifications.telegram_notifier import setup_telegram_webhook; ..."
   ```

3. **Set Up Scheduled Scans**:
   ```bash
   python scripts/setup_scheduled_scan.py --create --frequency-days 14 --start-time 02:00
   ```

4. **Verify Setup**:
   ```bash
   # Test WizTree
   python -c "from autopack.storage_optimizer.wiztree_scanner import WizTreeScanner; s=WizTreeScanner(); print(s.is_available())"

   # Test Telegram
   python scripts/verify_telegram_credentials.py

   # Test scheduled task
   schtasks /Query /TN Autopack_Storage_Scan
   ```

---

## Success Metrics

### Performance Benchmarks

| Metric | Phase 2 (Python) | Phase 3 (WizTree) | Improvement |
|--------|------------------|-------------------|-------------|
| 500 GB drive scan | 5-8 minutes | 5-10 seconds | **30-50x** |
| 1 TB drive scan | 10-15 minutes | 10-20 seconds | **30-50x** |
| 2 TB drive scan | 20-30 minutes | 20-40 seconds | **30-50x** |

### Automation Metrics

- ✅ Scheduled scan runs every 2 weeks without manual intervention
- ✅ Telegram notification delivered within 10 seconds of scan completion
- ✅ Approval workflow completes in < 5 minutes (user tap → database update)
- ✅ Execution starts automatically after approval
- ✅ Zero maintenance required after initial setup

---

## Next Steps (Phase 4+)

### Phase 4: Intelligence & Learning

1. **Category Auto-Learning** - Suggest policy rules from approval patterns
   - Track which categories user always approves
   - Auto-approve categories with 100% approval rate (after 5+ scans)
   - Suggest new category definitions based on common patterns

2. **Steam Game Detection** - Detect large uninstalled games
   - Query Steam library via registry
   - Identify games not played in 6+ months
   - Suggest moving to external drive or uninstalling

3. **Visual Reports** - HTML reports with charts
   - Disk usage treemap (interactive)
   - Trend charts (disk usage over time)
   - Category breakdown pie chart
   - Before/after comparison

### Phase 5: Advanced Features

4. **Multi-Drive Support** - Scan all drives automatically
5. **Cloud Storage Integration** - Sync large archives to cloud
6. **Smart Recommendations** - LLM-powered cleanup suggestions
7. **Performance Profiling** - Identify disk I/O bottlenecks

---

## Definition of Done (Phase 3)

### Completion Criteria

- [x] WizTree CLI wrapper implemented with fallback
- [ ] WizTree scans 1TB drive in < 30 seconds
- [ ] CSV parsing handles all edge cases (Unicode, long paths)
- [ ] Scheduled task creation script working
- [ ] Task appears in Windows Task Scheduler
- [ ] Telegram notification system adapted for storage
- [ ] Inline buttons trigger approval workflow
- [ ] Webhook integration tested end-to-end
- [ ] 13 new tests passing (8 unit + 5 integration)
- [ ] Documentation complete (setup guide, usage examples)
- [ ] Manual testing checklist completed

### Success Criteria

- ✅ 100% test pass rate
- ✅ WizTree scan performance < 30 seconds for 1TB drive
- ✅ Scheduled task runs successfully for 2 consecutive weeks
- ✅ Telegram notifications delivered 100% of time
- ✅ Zero false positives on protected paths (maintained from Phase 2)
- ✅ User can set up and forget (no manual intervention required)

---

## Timeline Estimate

- **Part 1 (WizTree)**: 3-4 hours
- **Part 2 (Scheduler)**: 2-3 hours
- **Part 3 (Telegram)**: 3-4 hours
- **Testing**: 2-3 hours
- **Documentation**: 2-3 hours

**Total**: 12-17 hours (1.5-2 days focused work)

---

## Dependencies

### Software Requirements

```txt
# Python Libraries (already installed)
requests>=2.31.0  # Telegram API
python-telegram-bot>=20.0  # Optional, for advanced features

# External Tools (optional)
WizTree 64-bit (freeware): https://www.diskanalyzer.com/download
ngrok (free tier): https://ngrok.com/download
```

### Windows Features

- Task Scheduler (built-in)
- NTFS file system (for WizTree MFT reading)
- PowerShell 5.0+ (for script execution)

---

## Conclusion

Phase 3 delivers a **fully automated disk cleanup workflow** with:
- ✅ 30-50x faster scanning (WizTree MFT reading)
- ✅ Zero-touch automation (scheduled tasks)
- ✅ Mobile approval workflow (Telegram inline buttons)
- ✅ Comprehensive notifications (scan → approval → execution)

Estimated 12-17 hours of focused implementation work, building on the solid Phase 2 foundation.

**Status**: Ready for implementation ✅
