"""
Set up Windows Task Scheduler for automated storage scans.

Creates a scheduled task that runs every 2 weeks (aligned with Tidy schedule).

Usage:
    # Create scheduled task (every 2 weeks at 2 AM)
    python scripts/setup_scheduled_scan.py --create

    # Create with custom frequency
    python scripts/setup_scheduled_scan.py --create --frequency-days 7 --start-time 03:00

    # List scheduled tasks
    python scripts/setup_scheduled_scan.py --list

    # Delete scheduled task
    python scripts/setup_scheduled_scan.py --delete

    # Test run (manual trigger)
    python scripts/setup_scheduled_scan.py --run
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
    notify: bool = True,
    auto_execute: bool = False,
) -> bool:
    """
    Create Windows scheduled task for storage scans.

    Args:
        task_name: Name of scheduled task
        frequency_days: Run every N days (default: 14 = fortnightly)
        start_time: Time to run (HH:MM format, 24-hour)
        notify: Send Telegram notification on completion
        auto_execute: Automatically execute approved deletions (DANGEROUS)

    Returns:
        True if task created successfully
    """
    # Get current Python executable and script path
    python_exe = sys.executable
    script_path = Path(__file__).parent / "storage" / "scan_and_report.py"
    autopack_root = Path(__file__).parent.parent

    if not script_path.exists():
        print(f"❌ Script not found: {script_path}")
        return False

    # Build command
    cmd_parts = [
        f'cd /d "{autopack_root}"',
        "&&",
        f'"{python_exe}"',
        f'"{script_path}"',
        "--save-to-db",
        "--wiztree",  # Prefer WizTree for speed
    ]

    if notify:
        cmd_parts.append("--notify")

    if auto_execute:
        cmd_parts.append("--interactive")  # Interactive mode for approval
        print(
            "⚠️  WARNING: Auto-execution enabled. This will DELETE files without manual approval!"
        )
        confirm = input("   Type 'YES' to confirm: ")
        if confirm != "YES":
            print("❌ Cancelled")
            return False

    cmd = " ".join(cmd_parts)

    # Build schtasks command
    # /SC DAILY with /MO <days> = every N days
    schtasks_cmd = [
        "schtasks",
        "/Create",
        "/TN",
        task_name,
        "/TR",
        cmd,
        "/SC",
        "DAILY",
        "/MO",
        str(frequency_days),
        "/ST",
        start_time,
        "/RL",
        "HIGHEST",  # Run with highest privileges
        "/F",  # Force create (overwrite if exists)
    ]

    try:
        result = subprocess.run(schtasks_cmd, capture_output=True, text=True, check=True)

        print("")
        print("✅ Scheduled task created successfully!")
        print(f"   Name: {task_name}")
        print(f"   Frequency: Every {frequency_days} days at {start_time}")
        print(f"   Command: {cmd}")
        print(f"   Working directory: {autopack_root}")
        print("")
        print("Next steps:")
        print("   1. View in Task Scheduler: taskschd.msc")
        print(f"   2. Test run: schtasks /Run /TN {task_name}")
        print(f"   3. View history: schtasks /Query /TN {task_name} /V /FO LIST")
        print("")

        return True

    except subprocess.CalledProcessError as e:
        print("❌ Failed to create scheduled task")
        print(f"   Error: {e.stderr}")
        print("")
        print("Common issues:")
        print("   - Requires Administrator privileges")
        print("   - Run Command Prompt as Administrator")
        print("   - Or use PowerShell: Start-Process powershell -Verb RunAs")
        return False


def list_scheduled_tasks() -> None:
    """List Autopack-related scheduled tasks."""
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/FO", "LIST", "/V"], capture_output=True, text=True, check=True
        )

        # Filter for Autopack tasks
        lines = result.stdout.split("\n")
        in_autopack_task = False
        task_count = 0

        print("")
        print("=" * 80)
        print("AUTOPACK SCHEDULED TASKS")
        print("=" * 80)
        print("")

        for line in lines:
            if "Autopack" in line:
                in_autopack_task = True
                task_count += 1

            if in_autopack_task:
                print(line)

            # Empty line marks end of task block
            if in_autopack_task and line.strip() == "":
                in_autopack_task = False
                print("")  # Extra separator

        if task_count == 0:
            print("No Autopack scheduled tasks found.")
            print("")
            print("Create one with:")
            print("  python scripts/setup_scheduled_scan.py --create")
            print("")

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to list tasks: {e.stderr}")


def delete_scheduled_task(task_name: str = "Autopack_Storage_Scan") -> bool:
    """Delete scheduled task."""
    try:
        # Confirm deletion
        print(f"⚠️  This will delete the scheduled task: {task_name}")
        confirm = input("   Type 'YES' to confirm: ")

        if confirm != "YES":
            print("❌ Cancelled")
            return False

        subprocess.run(
            ["schtasks", "/Delete", "/TN", task_name, "/F"],
            capture_output=True,
            text=True,
            check=True,
        )

        print(f"✅ Scheduled task '{task_name}' deleted")
        return True

    except subprocess.CalledProcessError as e:
        print("❌ Failed to delete task")
        print(f"   Error: {e.stderr}")
        print("")
        print("Possible reasons:")
        print(f"   - Task '{task_name}' does not exist")
        print("   - Requires Administrator privileges")
        return False


def run_task(task_name: str = "Autopack_Storage_Scan") -> bool:
    """Manually trigger scheduled task (test run)."""
    try:
        print(f"🚀 Manually triggering task: {task_name}")
        print("   This will run the scan immediately...")
        print("")

        result = subprocess.run(
            ["schtasks", "/Run", "/TN", task_name], capture_output=True, text=True, check=True
        )

        print("✅ Task triggered successfully")
        print("")
        print("Monitor progress:")
        print("   1. Check logs: .autopack/logs/storage_scan.log")
        print("   2. View in Task Scheduler: taskschd.msc")
        print("   3. Check database: SELECT * FROM storage_scans ORDER BY timestamp DESC LIMIT 1;")
        print("")

        return True

    except subprocess.CalledProcessError as e:
        print("❌ Failed to run task")
        print(f"   Error: {e.stderr}")
        return False


def show_task_history(task_name: str = "Autopack_Storage_Scan") -> None:
    """Show execution history for task."""
    try:
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", task_name, "/V", "/FO", "LIST"],
            capture_output=True,
            text=True,
            check=True,
        )

        print("")
        print("=" * 80)
        print(f"TASK HISTORY: {task_name}")
        print("=" * 80)
        print("")
        print(result.stdout)

    except subprocess.CalledProcessError as e:
        print(f"❌ Task not found: {task_name}")
        print(f"   Error: {e.stderr}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Manage scheduled storage scans for Autopack",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Create fortnightly scan at 2 AM
    python scripts/setup_scheduled_scan.py --create

    # Create weekly scan at 3 AM with notifications
    python scripts/setup_scheduled_scan.py --create --frequency-days 7 --start-time 03:00

    # List all Autopack scheduled tasks
    python scripts/setup_scheduled_scan.py --list

    # Delete scheduled task
    python scripts/setup_scheduled_scan.py --delete

    # Manually run task (test)
    python scripts/setup_scheduled_scan.py --run

    # View task history
    python scripts/setup_scheduled_scan.py --history
        """,
    )

    parser.add_argument("--create", action="store_true", help="Create scheduled task")
    parser.add_argument("--delete", action="store_true", help="Delete scheduled task")
    parser.add_argument("--list", action="store_true", help="List scheduled tasks")
    parser.add_argument("--run", action="store_true", help="Manually run task (test)")
    parser.add_argument("--history", action="store_true", help="Show task execution history")

    parser.add_argument(
        "--task-name",
        default="Autopack_Storage_Scan",
        help="Task name (default: Autopack_Storage_Scan)",
    )
    parser.add_argument(
        "--frequency-days", type=int, default=14, help="Run every N days (default: 14)"
    )
    parser.add_argument("--start-time", default="02:00", help="Start time HH:MM (default: 02:00)")
    parser.add_argument("--no-notify", action="store_true", help="Disable Telegram notifications")
    parser.add_argument(
        "--auto-execute", action="store_true", help="DANGER: Auto-execute approved deletions"
    )

    args = parser.parse_args()

    # Validate mutually exclusive actions
    actions = [args.create, args.delete, args.list, args.run, args.history]
    if sum(actions) == 0:
        parser.print_help()
        sys.exit(0)

    if sum(actions) > 1:
        print("❌ Error: Only one action allowed at a time")
        sys.exit(1)

    # Execute action
    if args.create:
        success = create_scheduled_task(
            task_name=args.task_name,
            frequency_days=args.frequency_days,
            start_time=args.start_time,
            notify=not args.no_notify,
            auto_execute=args.auto_execute,
        )
        sys.exit(0 if success else 1)

    elif args.delete:
        success = delete_scheduled_task(args.task_name)
        sys.exit(0 if success else 1)

    elif args.list:
        list_scheduled_tasks()
        sys.exit(0)

    elif args.run:
        success = run_task(args.task_name)
        sys.exit(0 if success else 1)

    elif args.history:
        show_task_history(args.task_name)
        sys.exit(0)
