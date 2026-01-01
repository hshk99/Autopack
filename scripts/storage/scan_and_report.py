"""
Storage Optimizer CLI Tool

Scans disk usage, classifies cleanup candidates, and generates reports.
All operations are DRY-RUN only for MVP - no actual deletion.

Usage:
    python scripts/storage/scan_and_report.py              # Scan C: drive
    python scripts/storage/scan_and_report.py --drive D    # Scan D: drive
    python scripts/storage/scan_and_report.py --dir c:/dev # Scan specific directory
"""

import sys
from pathlib import Path

# Add src to path so we can import autopack modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import argparse
from datetime import datetime

from autopack.storage_optimizer.policy import load_policy
from autopack.storage_optimizer.scanner import StorageScanner
from autopack.storage_optimizer.classifier import FileClassifier
from autopack.storage_optimizer.reporter import StorageReporter
from autopack.storage_optimizer.models import CleanupPlan


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

    args = parser.parse_args()

    print("=" * 80)
    print("STORAGE OPTIMIZER - MVP")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("")

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
    scanner = StorageScanner(max_depth=args.max_depth)
    classifier = FileClassifier(policy)

    output_dir = Path(args.output_dir) if args.output_dir else None
    reporter = StorageReporter(output_dir=output_dir)
    print("")

    # Step 3: Scan disk/directory
    print("[3/6] Scanning storage...")

    if args.dir:
        print(f"      Directory: {args.dir}")
        scan_results = scanner.scan_directory(args.dir, max_items=args.max_items)
        drive_letter = args.dir[0] if len(args.dir) > 0 else "C"
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

    print("")
    print("=" * 80)
    print("SCAN COMPLETE")
    print("=" * 80)
    print("")
    print("This was a DRY-RUN analysis. No files were deleted.")
    print("")
    print("Next steps:")
    print("  1. Review the cleanup candidates above")
    print("  2. Verify protected paths are correct")
    print("  3. When ready for actual cleanup, use the cleanup executor (future MVP phase)")
    print("")

    return 0


if __name__ == "__main__":
    sys.exit(main())
