"""
Storage Optimizer CLI Tool

Scans disk usage, classifies cleanup candidates, and generates reports.

Phase 2 Features:
- Database persistence (--save-to-db)
- Interactive approval workflow (--interactive)
- Actual deletion via Recycle Bin (--execute, requires approval)

Phase 3 Features (BUILD-150):
- WizTree integration for 30-50x faster scanning (--wiztree)
- Telegram notifications on scan completion (--notify)
- Windows Task Scheduler integration (see scripts/setup_scheduled_scan.py)

Usage:
    # Basic scan (dry-run reporting only)
    python scripts/storage/scan_and_report.py

    # Scan and save to database
    python scripts/storage/scan_and_report.py --save-to-db

    # Interactive approval mode
    python scripts/storage/scan_and_report.py --save-to-db --interactive

    # Execute approved deletions
    python scripts/storage/scan_and_report.py --execute --scan-id 123

    # Compare with previous scan
    python scripts/storage/scan_and_report.py --compare-with 122

    # Phase 3: Fast scan with WizTree + Telegram notification
    python scripts/storage/scan_and_report.py --save-to-db --wiztree --notify
"""

import sys
from pathlib import Path

# Add src to path so we can import autopack modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import argparse
import os
from datetime import datetime, timezone

from autopack.storage_optimizer.policy import load_policy
from autopack.storage_optimizer.scanner import StorageScanner, create_scanner
from autopack.storage_optimizer.classifier import FileClassifier
from autopack.storage_optimizer.reporter import StorageReporter
from autopack.storage_optimizer.models import CleanupPlan


# ==============================================================================
# Phase 2: Execution and Approval Helpers
# ==============================================================================

def send_scan_completion_notification(scan, db):
    """Send Telegram notification on scan completion (BUILD-150 Phase 3)."""
    from autopack.storage_optimizer.telegram_notifications import StorageTelegramNotifier
    from autopack.storage_optimizer.db import get_candidate_stats_by_category

    try:
        notifier = StorageTelegramNotifier()

        if not notifier.is_configured():
            print("[Telegram] Not configured - skipping notification")
            print("[Telegram] Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to enable")
            return False

        # Get category statistics for notification
        category_stats = get_candidate_stats_by_category(db, scan.id)

        print(f"[Telegram] Sending scan completion notification for scan {scan.id}...")
        success = notifier.send_scan_completion(scan, category_stats)

        if success:
            print("[Telegram] ✓ Notification sent successfully")
            print("[Telegram] Check your phone for approval buttons")
        else:
            print("[Telegram] ✗ Failed to send notification")

        return success

    except Exception as e:
        print(f"[Telegram] Error sending notification: {e}")
        return False


# ==============================================================================
# Phase 2: Database Persistence Helpers
# ==============================================================================

def execute_cleanup(args, db):
    """Execute approved deletions for a specific scan."""
    from autopack.storage_optimizer.db import get_scan_by_id
    from autopack.storage_optimizer.executor import CleanupExecutor

    print(f"[EXECUTION] Loading scan {args.scan_id}...")

    scan = get_scan_by_id(db, args.scan_id)
    if not scan:
        print(f"ERROR: Scan {args.scan_id} not found")
        return 1

    print(f"[EXECUTION] Scan: {scan.scan_target} ({scan.timestamp})")
    print(f"[EXECUTION] Cleanup candidates: {scan.cleanup_candidates_count}")
    print(f"[EXECUTION] Potential savings: {scan.potential_savings_bytes / (1024**3):.2f} GB")
    print("")

    # Load policy
    policy = load_policy()

    # Create executor
    executor = CleanupExecutor(
        policy=policy,
        dry_run=args.dry_run,
        compress_before_delete=args.compress
    )

    # Execute
    print(f"[EXECUTION] Starting cleanup (dry_run={args.dry_run}, compress={args.compress})...")
    if args.category:
        print(f"[EXECUTION] Category filter: {args.category}")

    batch_result = executor.execute_approved_candidates(
        db,
        scan_id=args.scan_id,
        category=args.category
    )

    # Print results
    print("")
    print("=" * 80)
    print("EXECUTION RESULTS")
    print("=" * 80)
    print(f"Total candidates: {batch_result.total_candidates}")
    print(f"Successful:       {batch_result.successful}")
    print(f"Failed:           {batch_result.failed}")
    print(f"Skipped:          {batch_result.skipped}")
    print(f"Success rate:     {batch_result.success_rate:.1f}%")
    print(f"Freed space:      {batch_result.total_freed_bytes / (1024**3):.2f} GB")
    print(f"Duration:         {batch_result.execution_duration_seconds}s")
    print("")

    if batch_result.failed > 0:
        print("FAILED DELETIONS:")
        for result in batch_result.results:
            if result.status == 'failed':
                print(f"  - {result.path}")
                print(f"    Error: {result.error}")
        print("")

    if args.dry_run:
        print("NOTE: This was a DRY-RUN. No files were actually deleted.")
        print("To execute for real, run with --dry-run=false")
    else:
        print("Files sent to Recycle Bin. You can restore them if needed.")

    return 0


def interactive_approval(scan_id, db, approved_by):
    """Interactive CLI approval workflow."""
    from autopack.storage_optimizer.db import (
        get_scan_by_id,
        get_cleanup_candidates_by_scan,
        get_candidate_stats_by_category,
        create_approval_decision
    )

    scan = get_scan_by_id(db, scan_id)
    if not scan:
        print(f"ERROR: Scan {scan_id} not found")
        return

    stats = get_candidate_stats_by_category(db, scan_id)

    print("")
    print("=" * 80)
    print("INTERACTIVE APPROVAL")
    print("=" * 80)
    print(f"Scan: {scan.scan_target} ({scan.timestamp})")
    print("")

    # Prompt for each category
    for category, category_stats in stats.items():
        count = category_stats['count']
        size_gb = category_stats['total_size_bytes'] / (1024**3)

        print(f"Category: {category}")
        print(f"  Items: {count}")
        print(f"  Size:  {size_gb:.2f} GB")

        # Get candidates for this category
        candidates = get_cleanup_candidates_by_scan(db, scan_id, category=category)

        # Prompt user
        decision = input(f"  Approve deletion? [y/N]: ").strip().lower()

        if decision == 'y':
            candidate_ids = [c.id for c in candidates]
            approval = create_approval_decision(
                db,
                scan_id=scan_id,
                candidate_ids=candidate_ids,
                approved_by=approved_by,
                decision='approve',
                approval_method='cli_interactive',
                notes=f"Interactive approval for {category}"
            )
            db.commit()
            print(f"  ✓ Approved {len(candidate_ids)} items ({size_gb:.2f} GB)")
        else:
            print(f"  ✗ Skipped (not approved)")

        print("")

    print("=" * 80)
    print("APPROVAL COMPLETE")
    print("=" * 80)
    print("")
    print("To execute approved deletions, run:")
    print(f"  python scripts/storage/scan_and_report.py --execute --scan-id {scan_id}")
    print("")


def save_scan_to_database(db, scan_target, scan_type, policy, scan_results, candidates, start_time, args):
    """Save scan results to PostgreSQL database."""
    from autopack.models import StorageScan, CleanupCandidateDB

    total_size_bytes = sum(r.size_bytes for r in scan_results)
    potential_savings_bytes = sum(c.size_bytes for c in candidates)
    scan_duration_seconds = (datetime.now(timezone.utc) - start_time).seconds

    print("[DB] Saving scan to database...")

    scan = StorageScan(
        timestamp=start_time,
        scan_type=scan_type,
        scan_target=scan_target,
        max_depth=args.max_depth,
        max_items=args.max_items,
        policy_version=policy.version,
        total_items_scanned=len(scan_results),
        total_size_bytes=total_size_bytes,
        cleanup_candidates_count=len(candidates),
        potential_savings_bytes=potential_savings_bytes,
        scan_duration_seconds=scan_duration_seconds,
        created_by=args.approved_by
    )
    db.add(scan)
    db.flush()  # Get scan.id

    # Save candidates
    for candidate in candidates:
        candidate_db = CleanupCandidateDB(
            scan_id=scan.id,
            path=candidate.path,
            size_bytes=candidate.size_bytes,
            age_days=candidate.age_days,
            last_modified=candidate.last_modified,
            category=candidate.category,
            reason=candidate.reason,
            requires_approval=candidate.requires_approval,
            approval_status='pending'
        )
        db.add(candidate_db)

    db.commit()
    db.refresh(scan)

    print(f"[DB] Saved scan ID: {scan.id}")
    print("")

    return scan


def compare_scans(db, current_scan_id, previous_scan_id):
    """Compare two scans and print trend analysis."""
    from autopack.storage_optimizer.db import compare_scans as db_compare_scans

    print("")
    print("=" * 80)
    print("SCAN COMPARISON")
    print("=" * 80)

    try:
        comparison = db_compare_scans(db, current_scan_id, previous_scan_id)

        current = comparison['scan_current']
        previous = comparison['scan_previous']

        print(f"Current scan:  {current.id} ({current.timestamp})")
        print(f"Previous scan: {previous.id} ({previous.timestamp})")
        print("")

        # Size changes
        size_change = comparison['total_size_change_bytes']
        size_change_gb = size_change / (1024**3)
        change_symbol = "+" if size_change > 0 else ""

        print("DISK USAGE TREND:")
        print(f"  Previous: {previous.total_size_bytes / (1024**3):.2f} GB")
        print(f"  Current:  {current.total_size_bytes / (1024**3):.2f} GB")
        print(f"  Change:   {change_symbol}{size_change_gb:.2f} GB")
        print("")

        # Cleanup candidates changes
        candidates_change = comparison['cleanup_candidates_change']
        print("CLEANUP CANDIDATES:")
        print(f"  Previous: {previous.cleanup_candidates_count}")
        print(f"  Current:  {current.cleanup_candidates_count}")
        print(f"  Change:   {change_symbol if candidates_change > 0 else ''}{candidates_change}")
        print("")

        # Category changes
        if comparison['categories_added']:
            print(f"NEW CATEGORIES: {', '.join(comparison['categories_added'])}")
        if comparison['categories_removed']:
            print(f"REMOVED CATEGORIES: {', '.join(comparison['categories_removed'])}")
        print("")

    except ValueError as e:
        print(f"ERROR: {e}")
        return


def main():
    parser = argparse.ArgumentParser(
        description="Storage Optimizer - Scan and generate cleanup reports"
    )
    parser.add_argument(
        "--drive",
        default="C",
        help="Drive letter to scan (default: C)"
    )
    parser.add_argument(
        "--dir",
        help="Specific directory to scan (overrides --drive)"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum directory depth to scan (default: 3)"
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=10000,
        help="Maximum items to scan (default: 10000)"
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to save reports (default: archive/reports/storage/)"
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save report to disk, only print to console"
    )

    # Phase 2: Database persistence
    parser.add_argument(
        "--save-to-db",
        action="store_true",
        help="Save scan results to PostgreSQL database (BUILD-149 Phase 2)"
    )
    parser.add_argument(
        "--scan-id",
        type=int,
        help="Scan ID to operate on (for --execute or --compare-with)"
    )
    parser.add_argument(
        "--compare-with",
        type=int,
        help="Compare current scan with previous scan ID"
    )

    # Phase 2: Interactive approval
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive approval mode - prompt for cleanup decisions"
    )
    parser.add_argument(
        "--approved-by",
        default=os.getenv("USER", "cli_user"),
        help="User identifier for approvals (default: $USER)"
    )

    # Phase 2: Execution
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute approved deletions (DANGER: actual deletion via Recycle Bin)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Preview actions without executing (default: True)"
    )
    parser.add_argument(
        "--compress",
        action="store_true",
        help="Compress files/folders before deletion"
    )
    parser.add_argument(
        "--category",
        help="Filter execution to specific category (e.g., 'dev_caches')"
    )

    # Phase 3 (BUILD-150): Performance and automation
    parser.add_argument(
        "--wiztree",
        action="store_true",
        help="Use WizTree for 30-50x faster scanning (BUILD-150 Phase 3)"
    )
    parser.add_argument(
        "--notify",
        action="store_true",
        help="Send Telegram notification on scan completion (BUILD-150 Phase 3)"
    )

    args = parser.parse_args()

    # Validate argument combinations
    if args.execute and not args.scan_id:
        parser.error("--execute requires --scan-id")

    if args.interactive and not args.save_to_db:
        parser.error("--interactive requires --save-to-db")

    if args.compare_with and not args.save_to_db:
        parser.error("--compare-with requires --save-to-db")

    print("=" * 80)
    if args.execute:
        print("STORAGE OPTIMIZER - EXECUTION MODE")
    elif args.interactive:
        print("STORAGE OPTIMIZER - INTERACTIVE APPROVAL")
    elif args.save_to_db:
        print("STORAGE OPTIMIZER - SCAN + DATABASE PERSISTENCE")
    else:
        print("STORAGE OPTIMIZER - DRY-RUN ANALYSIS")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("")

    # Phase 2: Initialize database if needed
    db_session = None
    if args.save_to_db or args.execute or args.compare_with:
        from autopack.database import SessionLocal
        db_session = SessionLocal()
        print("[DB] Connected to PostgreSQL database")
        print("")

    # Phase 2: Handle execution mode
    if args.execute:
        return execute_cleanup(args, db_session)

    # Step 1: Load policy
    print("[1/6] Loading storage policy...")
    try:
        policy = load_policy()
        print(f"      Policy version: {policy.version}")
        print(f"      Protected globs: {len(policy.protected_globs)}")
        print(f"      Categories: {len(policy.categories)}")
        print("")
    except Exception as e:
        print(f"ERROR: Failed to load policy: {e}")
        return 1

    # Step 2: Initialize components
    print("[2/6] Initializing scanner and classifier...")

    # Phase 3: Use WizTree scanner if requested
    if args.wiztree:
        print("      Using WizTree scanner for high-performance scanning...")
        scanner = create_scanner(prefer_wiztree=True)
        # Check if WizTree is actually available
        from autopack.storage_optimizer.wiztree_scanner import WizTreeScanner
        if isinstance(scanner, WizTreeScanner):
            print("      ✓ WizTree available - expect 30-50x faster scans")
        else:
            print("      ⚠ WizTree not found - falling back to Python scanner")
            print("      Download WizTree: https://www.diskanalyzer.com/download")
    else:
        scanner = StorageScanner()

    # Set max_depth if using Python scanner
    if hasattr(scanner, 'max_depth'):
        scanner.max_depth = args.max_depth

    classifier = FileClassifier(policy)

    output_dir = Path(args.output_dir) if args.output_dir else None
    reporter = StorageReporter(output_dir=output_dir)
    print("")

    # Step 3: Scan disk/directory
    print("[3/6] Scanning storage...")

    if args.dir:
        print(f"      Directory: {args.dir}")
        scan_results = scanner.scan_directory(args.dir, max_depth=args.max_depth, max_items=args.max_items)
        drive_letter = args.dir[0] if len(args.dir) > 0 else "C"
    else:
        # Phase 3: Use full drive scan with WizTree (much faster than selective scanning)
        if args.wiztree and hasattr(scanner, 'scan_drive'):
            print(f"      Drive: {args.drive}:\\ (full drive scan via WizTree MFT)")
            scan_results = scanner.scan_drive(args.drive, max_depth=args.max_depth, max_items=args.max_items)
        else:
            print(f"      Drive: {args.drive}:\\")
            print(f"      Scanning high-value directories...")
            scan_results = scanner.scan_high_value_directories(args.drive)
        drive_letter = args.drive

    print(f"      Found: {len(scan_results):,} items")

    total_scanned_size = sum(r.size_bytes for r in scan_results)
    print(f"      Total scanned size: {total_scanned_size / (1024**3):.2f} GB")
    print("")

    # Step 4: Get disk usage
    print("[4/6] Getting disk usage...")
    disk_usage = scanner.get_disk_usage(drive_letter)
    total_gb, used_gb, free_gb = [x / (1024**3) for x in disk_usage]
    print(f"      Total: {total_gb:.2f} GB")
    print(f"      Used:  {used_gb:.2f} GB")
    print(f"      Free:  {free_gb:.2f} GB")
    print("")

    # Step 5: Classify cleanup candidates
    print("[5/6] Classifying cleanup candidates...")

    # Find protected paths
    protected_paths = classifier.get_protected_paths(scan_results)
    protected_size = sum(r.size_bytes for r in scan_results if r.path in protected_paths)

    print(f"      Protected paths: {len(protected_paths):,} items ({protected_size / (1024**3):.2f} GB)")

    # Classify candidates
    candidates = classifier.classify_batch(scan_results)
    print(f"      Cleanup candidates: {len(candidates):,} items")

    # Build cleanup plan
    cleanup_plan = CleanupPlan()
    for candidate in candidates:
        cleanup_plan.add_candidate(candidate)

    print(f"      Potential savings: {cleanup_plan.total_size_gb:.2f} GB")

    # Show statistics
    stats = classifier.get_statistics(candidates)
    print(f"      Requires approval: {stats['requires_approval']:,} items")
    print(f"      Can auto-delete: {stats['can_auto_delete']:,} items")
    print("")

    # Step 6: Generate and save report
    print("[6/6] Generating report...")

    report = reporter.create_report(
        drive_letter=drive_letter,
        disk_usage=disk_usage,
        scan_results=scan_results,
        cleanup_plan=cleanup_plan,
        protected_paths=protected_paths,
        protected_size_bytes=protected_size
    )

    # Print summary to console
    print("")
    reporter.print_summary(report)

    # Save to disk unless --no-save
    if not args.no_save:
        print("")
        reporter.save_report(report, reporter.generate_summary(report))

    # Phase 2: Save to database if requested
    saved_scan = None
    if args.save_to_db and db_session:
        scan_type = 'directory' if args.dir else 'drive'
        scan_target = args.dir if args.dir else f"{drive_letter}:"
        saved_scan = save_scan_to_database(
            db_session,
            scan_target=scan_target,
            scan_type=scan_type,
            policy=policy,
            scan_results=scan_results,
            candidates=candidates,
            start_time=datetime.now(timezone.utc),
            args=args
        )

    # Phase 2: Compare with previous scan if requested
    if args.compare_with and saved_scan:
        compare_scans(db_session, saved_scan.id, args.compare_with)

    # Phase 2: Interactive approval if requested
    if args.interactive and saved_scan:
        interactive_approval(saved_scan.id, db_session, args.approved_by)

    # Phase 3: Send Telegram notification if requested
    if args.notify and saved_scan and db_session:
        print("")
        send_scan_completion_notification(saved_scan, db_session)

    # Close database session
    if db_session:
        db_session.close()

    print("")
    print("=" * 80)
    print("SCAN COMPLETE")
    print("=" * 80)
    print("")

    if args.save_to_db and saved_scan:
        print(f"Scan ID: {saved_scan.id}")
        print(f"Scan saved to database for future execution/comparison")
        print("")
        if not args.interactive:
            print("Next steps:")
            print(f"  1. Review candidates: curl http://localhost:8000/storage/scans/{saved_scan.id}")
            print(f"  2. Approve via API or use --interactive flag")
            print(f"  3. Execute: python scripts/storage/scan_and_report.py --execute --scan-id {saved_scan.id}")
    else:
        print("This was a DRY-RUN analysis. No files were deleted.")
        print("")
        print("Next steps:")
        print("  1. Review the cleanup candidates above")
        print("  2. Verify protected paths are correct")
        print("  3. Add --save-to-db flag to persist results")
        print("  4. Use --interactive for approval workflow")

    print("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
