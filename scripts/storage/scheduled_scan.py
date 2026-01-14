#!/usr/bin/env python3
"""
Scheduled Storage Optimizer Scan - Task Scheduler / Cron Compatible

Weekly automated scan workflow:
1. Run scan with database persistence
2. Generate delta report (what changed since last scan)
3. Send notification (optional Telegram alert)
4. NO automatic deletion (requires explicit approval)

Usage:
    # Manual execution (from repo root)
    python scripts/storage/scheduled_scan.py --root .

    # Windows Task Scheduler (use repo root discovery)
    # From repo root: schtasks /create /tn "Storage Weekly Scan" /tr "cmd /c cd /d %CD% && python scripts/storage/scheduled_scan.py" /sc weekly /d SUN /st 02:00

    # Linux cron (every Sunday at 2am)
    0 2 * * 0 cd /path/to/autopack && python scripts/storage/scheduled_scan.py

Environment variables:
    TELEGRAM_BOT_TOKEN: Telegram bot token for notifications (optional)
    TELEGRAM_CHAT_ID: Telegram chat ID for notifications (optional)
    DATABASE_URL: PostgreSQL/SQLite connection string (default: sqlite:///autopack.db)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import StorageScan, CleanupCandidateDB
from autopack.storage_optimizer.scanner import StorageScanner
from autopack.storage_optimizer.policy import load_policy
from autopack.storage_optimizer.classifier import FileClassifier


def get_last_scan(db, scan_target: str) -> Optional[StorageScan]:
    """Get the most recent scan for a given scan target."""
    return (
        db.query(StorageScan)
        .filter(StorageScan.scan_target == scan_target)
        .order_by(StorageScan.timestamp.desc())
        .first()
    )


def compute_delta_report(db, current_scan_id: int, previous_scan_id: Optional[int]) -> Dict:
    """
    Compute what changed between scans.

    Returns:
        Dict with delta statistics:
        - new_candidates: Candidates in current scan not in previous
        - removed_candidates: Candidates in previous scan not in current
        - size_change_gb: Change in total cleanup opportunity size
        - category_changes: Per-category delta breakdown
    """
    if previous_scan_id is None:
        return {
            "is_first_scan": True,
            "new_candidates": 0,
            "removed_candidates": 0,
            "size_change_gb": 0.0,
            "category_changes": {},
        }

    # Get current candidates
    current = db.query(CleanupCandidateDB).filter_by(scan_id=current_scan_id).all()

    # Get previous candidates
    previous = db.query(CleanupCandidateDB).filter_by(scan_id=previous_scan_id).all()

    # Convert to sets for comparison (use path as unique identifier)
    current_paths = {c.path for c in current}
    previous_paths = {c.path for c in previous}

    new_paths = current_paths - previous_paths
    removed_paths = previous_paths - current_paths

    # Calculate size changes
    current_size = sum(c.size_bytes for c in current)
    previous_size = sum(c.size_bytes for c in previous)
    size_change_gb = (current_size - previous_size) / (1024**3)

    # Per-category breakdown
    category_changes = {}

    # Get all categories
    all_categories = set(c.category for c in current + previous)

    for category in all_categories:
        curr_cat = [c for c in current if c.category == category]
        prev_cat = [c for c in previous if c.category == category]

        curr_size = sum(c.size_bytes for c in curr_cat)
        prev_size = sum(c.size_bytes for c in prev_cat)

        category_changes[category] = {
            "current_count": len(curr_cat),
            "previous_count": len(prev_cat),
            "delta_count": len(curr_cat) - len(prev_cat),
            "current_size_gb": curr_size / (1024**3),
            "previous_size_gb": prev_size / (1024**3),
            "delta_size_gb": (curr_size - prev_size) / (1024**3),
        }

    return {
        "is_first_scan": False,
        "previous_scan_id": previous_scan_id,
        "new_candidates": len(new_paths),
        "removed_candidates": len(removed_paths),
        "size_change_gb": size_change_gb,
        "category_changes": category_changes,
        "new_paths_sample": list(new_paths)[:10] if new_paths else [],
        "removed_paths_sample": list(removed_paths)[:10] if removed_paths else [],
    }


def send_telegram_notification(message: str) -> bool:
    """Send Telegram notification if credentials are configured."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        return False

    try:
        import requests

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}

        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"WARNING: Failed to send Telegram notification: {e}")
        return False


def format_delta_report(
    delta: Dict, current_scan: StorageScan, previous_scan: Optional[StorageScan]
) -> str:
    """Format delta report as human-readable text."""
    lines = []
    lines.append("=" * 80)
    lines.append("STORAGE OPTIMIZER - WEEKLY SCAN DELTA REPORT")
    lines.append("=" * 80)
    lines.append(f"Scan Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"Current Scan ID: {current_scan.id}")

    if delta["is_first_scan"]:
        lines.append("\nThis is the first scan (no previous scan for comparison).")
        lines.append(f"\nTotal cleanup candidates: {current_scan.cleanup_candidates_count}")
        lines.append(
            f"Total potential savings: {current_scan.potential_savings_bytes / (1024**3):.2f} GB"
        )
    else:
        lines.append(f"Previous Scan ID: {delta['previous_scan_id']}")
        lines.append(
            f"Previous Scan Date: {previous_scan.timestamp.strftime('%Y-%m-%d %H:%M UTC')}"
        )

        lines.append("\n" + "-" * 80)
        lines.append("CHANGES SINCE LAST SCAN")
        lines.append("-" * 80)

        # Overall changes
        lines.append(f"New cleanup opportunities:     {delta['new_candidates']} files/folders")
        lines.append(f"Removed opportunities:         {delta['removed_candidates']} files/folders")
        lines.append(f"Net size change:               {delta['size_change_gb']:+.2f} GB")

        # Category breakdown
        if delta["category_changes"]:
            lines.append("\nPer-Category Changes:")
            for category, changes in sorted(delta["category_changes"].items()):
                if changes["delta_count"] != 0 or changes["delta_size_gb"] != 0.0:
                    lines.append(f"  {category}:")
                    lines.append(
                        f"    Count: {changes['previous_count']} → {changes['current_count']} ({changes['delta_count']:+d})"
                    )
                    lines.append(
                        f"    Size:  {changes['previous_size_gb']:.2f} GB → {changes['current_size_gb']:.2f} GB ({changes['delta_size_gb']:+.2f} GB)"
                    )

        # Sample new files
        if delta["new_paths_sample"]:
            lines.append("\nSample New Cleanup Opportunities (first 10):")
            for path in delta["new_paths_sample"]:
                lines.append(f"  + {path}")

        # Sample removed files
        if delta["removed_paths_sample"]:
            lines.append("\nSample Removed Opportunities (first 10):")
            for path in delta["removed_paths_sample"]:
                lines.append(f"  - {path}")

    lines.append("\n" + "=" * 80)
    lines.append("NEXT STEPS")
    lines.append("=" * 80)
    lines.append(f"1. Review candidates: http://localhost:8000/storage/scans/{current_scan.id}")
    lines.append("2. Approve via API or interactive mode:")
    lines.append(
        f"   python scripts/storage/scan_and_report.py --scan-id {current_scan.id} --interactive"
    )
    lines.append("3. Execute approved deletions:")
    lines.append(
        f"   python scripts/storage/scan_and_report.py --scan-id {current_scan.id} --execute --category dev_caches"
    )
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Scheduled Storage Optimizer Scan (Task Scheduler / Cron)"
    )
    parser.add_argument("--root", default="C:/", help="Root directory to scan (default: C:/)")
    parser.add_argument(
        "--name",
        default=f"weekly-scan-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        help="Scan name (default: weekly-scan-YYYYMMDD)",
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send Telegram notification (requires TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars)",
    )
    parser.add_argument(
        "--output-dir",
        default="archive/reports/storage/weekly",
        help="Directory to save delta reports (default: archive/reports/storage/weekly)",
    )

    args = parser.parse_args()

    # Ensure output directory exists
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load policy
    print("[1/5] Loading storage policy...")
    policy = load_policy()

    # Connect to database
    print("[2/5] Connecting to database...")
    session = SessionLocal()

    # Get previous scan for delta comparison
    previous_scan = get_last_scan(session, args.root)
    if previous_scan:
        print(f"[INFO] Found previous scan: ID {previous_scan.id} from {previous_scan.timestamp}")
    else:
        print("[INFO] No previous scan found - this will be the baseline")

    # Run scan
    print(f"[3/5] Scanning {args.root}...")
    scanner = StorageScanner(max_depth=3)
    scan_results = scanner.scan_directory(args.root)

    # Classify candidates
    print("[4/5] Classifying cleanup candidates...")
    classifier = FileClassifier(policy)
    candidates = classifier.classify_batch(scan_results)

    # Save to database
    print("[5/5] Saving to database and generating delta report...")
    scan_start_time = datetime.now(timezone.utc)
    total_scanned_size = sum(r.size_bytes for r in scan_results)
    potential_savings = sum(c.size_bytes for c in candidates)

    current_scan = StorageScan(
        timestamp=scan_start_time,
        scan_type="scheduled",
        scan_target=args.root,
        max_depth=3,
        max_items=None,
        policy_version=policy.version,
        total_items_scanned=len(scan_results),
        total_size_bytes=total_scanned_size,
        cleanup_candidates_count=len(candidates),
        potential_savings_bytes=potential_savings,
        scan_duration_seconds=0,
        notes=args.name,
    )

    session.add(current_scan)
    session.flush()  # Get scan ID

    # Add candidates to database
    for classification in candidates:
        candidate = CleanupCandidateDB(
            scan_id=current_scan.id,
            path=classification.path,
            size_bytes=classification.size_bytes,
            category=classification.category,
            reason=classification.reason,
            requires_approval=classification.requires_approval,
            approval_status="pending",
        )
        session.add(candidate)

    session.commit()

    # Compute delta
    delta = compute_delta_report(
        session, current_scan.id, previous_scan.id if previous_scan else None
    )

    # Format report
    report_text = format_delta_report(delta, current_scan, previous_scan)

    # Print to console
    print("\n")
    print(report_text)

    # Save to file
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_file = output_dir / f"weekly_delta_{timestamp}.txt"
    report_file.write_text(report_text, encoding="utf-8")
    print(f"\n✅ Delta report saved to: {report_file}")

    # Save JSON for programmatic access
    json_file = output_dir / f"weekly_delta_{timestamp}.json"
    delta_json = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_scan_id": current_scan.id,
        "previous_scan_id": previous_scan.id if previous_scan else None,
        "delta": delta,
        "current_scan_summary": {
            "total_candidates": current_scan.cleanup_candidates_count,
            "total_size_gb": current_scan.potential_savings_bytes / (1024**3),
            "scan_target": current_scan.scan_target,
            "scan_time": current_scan.timestamp.isoformat(),
        },
    }
    json_file.write_text(json.dumps(delta_json, indent=2), encoding="utf-8")
    print(f"✅ JSON report saved to: {json_file}")

    # Send Telegram notification if requested
    if args.notify:
        # Format Telegram message (shorter version)
        telegram_msg = f"""
📊 *Storage Optimizer Weekly Scan*

📅 Scan: {datetime.now(timezone.utc).strftime("%Y-%m-%d")}
🆔 Scan ID: {current_scan.id}

{"📌 *First Scan*" if delta["is_first_scan"] else ""}
{"📈 *Changes Since Last Week*" if not delta["is_first_scan"] else ""}

{"Total candidates: " + str(current_scan.total_candidates) if delta["is_first_scan"] else ""}
{"New opportunities: " + str(delta["new_candidates"]) if not delta["is_first_scan"] else ""}
{"Removed: " + str(delta["removed_candidates"]) if not delta["is_first_scan"] else ""}
{"Size change: " + f"{delta['size_change_gb']:+.2f} GB" if not delta["is_first_scan"] else ""}

💾 Potential savings: {current_scan.potential_savings_bytes / (1024**3):.2f} GB

🔗 Review: http://localhost:8000/storage/scans/{current_scan.id}
        """.strip()

        if send_telegram_notification(telegram_msg):
            print("✅ Telegram notification sent")
        else:
            print("⚠️  Telegram notification not sent (check credentials)")

    session.close()

    print("\n✅ Scheduled scan complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
