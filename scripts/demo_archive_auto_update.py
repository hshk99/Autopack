"""
Demo script showing how the archive consolidator auto-updates work.

This demonstrates the automatic consolidation system similar to debug_journal.py.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.archive_consolidator import (
    log_error,
    log_fix,
    mark_resolved,
    log_build_event,
    log_strategic_update,
    update_archive_index,
)


def demo_error_logging():
    """Demonstrate automatic error logging to CONSOLIDATED_DEBUG.md"""
    print("\n=== Demo 1: Logging a new error ===")

    log_error(
        error_signature="API Timeout on Large Files",
        symptom="Timeout after 30s when processing files >5MB",
        run_id="fileorg-test-2025-11-30",
        phase_id="phase-3",
        suspected_cause="No streaming, loading entire file into memory",
        priority="HIGH",
    )

    print("[OK] Error logged to CONSOLIDATED_DEBUG.md")
    print("   Check: .autonomous_runs/file-organizer-app-v1/archive/CONSOLIDATED_DEBUG.md")


def demo_fix_logging():
    """Demonstrate logging a fix"""
    print("\n=== Demo 2: Logging a fix ===")

    log_fix(
        error_signature="API Timeout on Large Files",
        fix_description="Implemented streaming file upload with chunking (1MB chunks)",
        files_changed=["src/autopack/file_uploader.py", "src/autopack/api_client.py"],
        test_run_id="fileorg-test-fix-2025-11-30",
        result="success",
    )

    print("[OK] Fix logged to CONSOLIDATED_DEBUG.md")


def demo_resolution():
    """Demonstrate marking an issue as resolved"""
    print("\n=== Demo 3: Marking issue as resolved ===")

    mark_resolved(
        error_signature="API Timeout on Large Files",
        resolution_summary="Implemented streaming upload with 1MB chunks. Tested with files up to 50MB successfully.",
        verified_run_id="fileorg-test-fix-2025-11-30",
        prevention_rule="ALWAYS use streaming uploads for files >1MB to prevent timeout and memory issues",
    )

    print("[OK] Issue marked as resolved")
    print("   Prevention rule added automatically")


def demo_build_logging():
    """Demonstrate build event logging to CONSOLIDATED_BUILD.md"""
    print("\n=== Demo 4: Logging a build event ===")

    log_build_event(
        event_type="week_complete",
        week_number=10,
        description="Completed Week 10: Advanced Search and Filtering",
        deliverables=[
            "Full-text search with SQLite FTS5",
            "Advanced filter UI (date range, file type, tags)",
            "Search result highlighting",
            "Performance optimization for large result sets",
        ],
        token_usage={"builder": 12500, "auditor": 8200, "total": 20700},
    )

    print("[OK] Build event logged to CONSOLIDATED_BUILD.md")


def demo_strategic_update():
    """Demonstrate strategic update logging"""
    print("\n=== Demo 5: Logging a strategic update ===")

    log_strategic_update(
        update_type="market_analysis",
        content="""
Updated TAM/SAM/SOM based on Q4 2025 market research:

- TAM: $15.2B (up from $13.7B due to SMB digital transformation acceleration)
- SAM: $650M (increased Tauri adoption, now 12% of desktop app market)
- SOM Year 5: $3.2M (revised upward based on beta user feedback and retention data)

Key Insight: Enterprise interest higher than expected - 23% of trial users are from companies >500 employees.
Consider adding Enterprise tier in Year 2 instead of Year 3.
""",
    )

    print("[OK] Strategic update logged to CONSOLIDATED_STRATEGY.md")


def demo_index_update():
    """Demonstrate archive index auto-update"""
    print("\n=== Demo 6: Updating archive index ===")

    update_archive_index()

    print("[OK] Archive index updated")
    print("   Check: .autonomous_runs/file-organizer-app-v1/archive/ARCHIVE_INDEX.md")


def main():
    print("=" * 70)
    print("ARCHIVE CONSOLIDATOR - Auto-Update System Demo")
    print("=" * 70)
    print("\nThis demo shows how the archive consolidator automatically updates")
    print("the consolidated reference files as events occur during builds.")
    print("\nSimilar to debug_journal.py, but for historical/strategic docs.")

    try:
        # Run demos
        demo_error_logging()
        demo_fix_logging()
        demo_resolution()
        demo_build_logging()
        demo_strategic_update()
        demo_index_update()

        print("\n" + "=" * 70)
        print("[OK] All demos completed successfully!")
        print("=" * 70)
        print("\nCheck the following files to see the auto-updates:")
        print("  - CONSOLIDATED_DEBUG.md")
        print("  - CONSOLIDATED_BUILD.md")
        print("  - CONSOLIDATED_STRATEGY.md")
        print("  - ARCHIVE_INDEX.md")
        print("\nIn your actual autonomous runs, these functions are called")
        print("automatically by the autonomous_executor.py when relevant events occur.")

    except Exception as e:
        print(f"\n[ERROR] Error during demo: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
