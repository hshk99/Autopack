"""
Storage report generator.

Creates human-readable reports showing:
- Disk usage summary
- Top space consumers
- Cleanup opportunities by category
- Policy-protected paths
- Potential savings
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional
import json

from .models import ScanResult, CleanupPlan, StorageReport


class StorageReporter:
    """Generates storage analysis and cleanup reports."""

    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize reporter.

        Args:
            output_dir: Directory to save reports. If None, uses archive/reports/storage/
        """
        if output_dir is None:
            output_dir = Path.cwd() / "archive" / "reports" / "storage"

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def create_report(
        self,
        drive_letter: str,
        disk_usage: tuple,
        scan_results: List[ScanResult],
        cleanup_plan: CleanupPlan,
        protected_paths: List[str],
        protected_size_bytes: int
    ) -> StorageReport:
        """
        Create a complete storage report.

        Args:
            drive_letter: Drive letter scanned
            disk_usage: Tuple of (total, used, free) in bytes
            scan_results: All scan results
            cleanup_plan: CleanupPlan with candidates
            protected_paths: List of protected paths found
            protected_size_bytes: Total size of protected paths

        Returns:
            StorageReport object
        """
        total_bytes, used_bytes, free_bytes = disk_usage

        # Count files and folders
        total_files = sum(1 for r in scan_results if not r.is_folder)
        total_folders = sum(1 for r in scan_results if r.is_folder)

        # Get top consumers
        top_consumers = sorted(scan_results, key=lambda x: x.size_bytes, reverse=True)[:20]

        report = StorageReport(
            scan_date=datetime.now(),
            drive_letter=drive_letter,
            total_space_bytes=total_bytes,
            used_space_bytes=used_bytes,
            free_space_bytes=free_bytes,
            total_files_scanned=total_files,
            total_folders_scanned=total_folders,
            top_consumers=top_consumers,
            cleanup_plan=cleanup_plan,
            protected_paths_found=protected_paths,
            protected_size_bytes=protected_size_bytes
        )

        return report

    def generate_summary(self, report: StorageReport) -> str:
        """
        Generate human-readable summary text.

        Args:
            report: StorageReport object

        Returns:
            Formatted summary string
        """
        lines = []

        # Header
        lines.append("=" * 80)
        lines.append("STORAGE OPTIMIZATION REPORT")
        lines.append("=" * 80)
        lines.append(f"Date: {report.scan_date.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Drive: {report.drive_letter}:\\")
        lines.append("")

        # Disk usage
        lines.append("DISK USAGE:")
        lines.append(f"  Total Space: {report.total_space_gb:,.2f} GB")
        lines.append(f"  Used Space:  {report.used_space_gb:,.2f} GB ({report.used_percentage:.1f}%)")
        lines.append(f"  Free Space:  {report.free_space_gb:,.2f} GB")
        lines.append("")

        # Scan summary
        lines.append("SCAN SUMMARY:")
        lines.append(f"  Files scanned:   {report.total_files_scanned:,}")
        lines.append(f"  Folders scanned: {report.total_folders_scanned:,}")
        lines.append("")

        # Policy protections
        if report.protected_paths_found:
            lines.append("POLICY PROTECTIONS (items excluded from cleanup):")
            lines.append(f"  Protected paths: {len(report.protected_paths_found):,}")
            lines.append(f"  Protected size:  {report.protected_size_gb:.2f} GB")
            lines.append("")
            lines.append("  Sample protected paths:")
            for path in report.protected_paths_found[:10]:
                lines.append(f"    - {path}")
            if len(report.protected_paths_found) > 10:
                lines.append(f"    ... and {len(report.protected_paths_found) - 10} more")
            lines.append("")

        # Top consumers
        if report.top_consumers:
            lines.append("TOP 10 SPACE CONSUMERS:")
            for i, consumer in enumerate(report.top_consumers[:10], 1):
                size_str = f"{consumer.size_gb:.2f} GB" if consumer.size_gb >= 1 else f"{consumer.size_mb:.0f} MB"
                folder_marker = "[DIR]" if consumer.is_folder else "[FILE]"
                lines.append(f"  {i:2d}. {size_str:>12} {folder_marker:6} - {consumer.path}")
            lines.append("")

        # Cleanup opportunities
        if report.cleanup_plan:
            plan = report.cleanup_plan
            lines.append("CLEANUP OPPORTUNITIES:")
            lines.append(f"  Total Potential Savings: {plan.total_size_gb:.2f} GB")
            lines.append(f"  Total Candidates: {len(plan.candidates):,}")
            lines.append("")

            # By category
            if plan.size_by_category:
                lines.append("  By Category:")
                sorted_categories = sorted(
                    plan.size_by_category.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                for category, size_bytes in sorted_categories:
                    size_gb = size_bytes / (1024 * 1024 * 1024)
                    count = len(plan.candidates_by_category[category])
                    lines.append(f"    {category:20s}: {size_gb:8.2f} GB ({count:,} items)")
                lines.append("")

            # Approval requirements
            requires_approval = sum(1 for c in plan.candidates if c.requires_approval)
            can_auto_delete = sum(1 for c in plan.candidates if c.can_auto_delete)

            lines.append("  Approval Requirements:")
            lines.append(f"    Requires manual approval: {requires_approval:,} items")
            lines.append(f"    Can auto-delete:          {can_auto_delete:,} items")
            lines.append("")

            # Sample candidates
            lines.append("  Sample Cleanup Candidates:")
            for candidate in plan.candidates[:10]:
                size_str = f"{candidate.size_gb:.2f} GB" if candidate.size_gb >= 1 else f"{candidate.size_mb:.0f} MB"
                approval = "[APPROVAL REQUIRED]" if candidate.requires_approval else "[AUTO-DELETE OK]"
                lines.append(f"    - {size_str:>12} {approval:20} {candidate.category:15s}")
                lines.append(f"      {candidate.path}")
                lines.append(f"      Reason: {candidate.reason}")
            if len(plan.candidates) > 10:
                lines.append(f"    ... and {len(plan.candidates) - 10} more candidates")
            lines.append("")

        # Footer
        lines.append("=" * 80)
        lines.append("This is a DRY-RUN report. No files have been deleted.")
        lines.append("Review the cleanup candidates before executing any deletions.")
        lines.append("=" * 80)

        return "\n".join(lines)

    def save_report(self, report: StorageReport, summary: str) -> Path:
        """
        Save report to disk.

        Args:
            report: StorageReport object
            summary: Human-readable summary text

        Returns:
            Path to saved report file
        """
        timestamp = report.scan_date.strftime("%Y%m%d_%H%M%S")
        filename = f"storage_report_{report.drive_letter}_{timestamp}.txt"
        filepath = self.output_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(summary)

        # Also save JSON version for programmatic access
        json_filename = f"storage_report_{report.drive_letter}_{timestamp}.json"
        json_filepath = self.output_dir / json_filename

        report_dict = {
            'scan_date': report.scan_date.isoformat(),
            'drive_letter': report.drive_letter,
            'disk_usage': {
                'total_gb': report.total_space_gb,
                'used_gb': report.used_space_gb,
                'free_gb': report.free_space_gb,
                'used_percentage': report.used_percentage
            },
            'scan_summary': {
                'files_scanned': report.total_files_scanned,
                'folders_scanned': report.total_folders_scanned
            },
            'protected': {
                'paths_count': len(report.protected_paths_found),
                'size_gb': report.protected_size_gb,
                'sample_paths': report.protected_paths_found[:20]
            },
            'cleanup_plan': {
                'total_savings_gb': report.cleanup_plan.total_size_gb if report.cleanup_plan else 0,
                'total_candidates': len(report.cleanup_plan.candidates) if report.cleanup_plan else 0,
                'by_category': {
                    cat: {
                        'size_gb': size_bytes / (1024 * 1024 * 1024),
                        'count': len(report.cleanup_plan.candidates_by_category[cat])
                    }
                    for cat, size_bytes in (report.cleanup_plan.size_by_category if report.cleanup_plan else {}).items()
                }
            }
        }

        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(report_dict, f, indent=2)

        print(f"\nReport saved to:")
        print(f"  Text: {filepath}")
        print(f"  JSON: {json_filepath}")

        return filepath

    def print_summary(self, report: StorageReport) -> None:
        """
        Print summary to console.

        Args:
            report: StorageReport object
        """
        summary = self.generate_summary(report)
        print(summary)
