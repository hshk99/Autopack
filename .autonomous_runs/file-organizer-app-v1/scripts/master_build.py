#!/usr/bin/env python3
"""
FileOrganizer v1.0 - Master Build Script
Executes all 9 weeks of build sequentially

This script orchestrates the complete FileOrganizer v1.0 build
from Week 1 (Foundation) to Week 9 (Release).
"""

import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime
import time


class BuildOrchestrator:
    """Orchestrates the 9-week build process"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.scripts_dir = project_root / "scripts"
        self.start_time = None
        self.week_results = []

    def run_week(self, week_num: int) -> bool:
        """Execute a single week's build script"""
        print("\n" + "="*80)
        print(f"{'WEEK ' + str(week_num) + ' BUILD':^80}")
        print("="*80)

        script_path = self.scripts_dir / f"week{week_num}_build.py"

        if not script_path.exists():
            print(f"[ERROR] Script not found: {script_path}")
            return False

        week_start = time.time()

        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minute timeout per week
            )

            week_duration = time.time() - week_start

            if result.returncode == 0:
                print(result.stdout)
                print(f"\n[OK] Week {week_num} completed in {week_duration:.1f} seconds")
                self.week_results.append({
                    'week': week_num,
                    'status': 'success',
                    'duration': week_duration
                })
                return True
            else:
                print(result.stdout)
                print(result.stderr)
                print(f"\n[ERROR] Week {week_num} failed")
                self.week_results.append({
                    'week': week_num,
                    'status': 'failed',
                    'duration': week_duration,
                    'error': result.stderr
                })
                return False

        except subprocess.TimeoutExpired:
            print(f"\n[ERROR] Week {week_num} timed out after 30 minutes")
            self.week_results.append({
                'week': week_num,
                'status': 'timeout',
                'duration': 1800
            })
            return False

        except Exception as e:
            print(f"\n[ERROR] Week {week_num} error: {str(e)}")
            self.week_results.append({
                'week': week_num,
                'status': 'error',
                'error': str(e)
            })
            return False

    def generate_report(self) -> str:
        """Generate final build report"""
        total_duration = time.time() - self.start_time
        successful_weeks = sum(1 for r in self.week_results if r['status'] == 'success')
        failed_weeks = sum(1 for r in self.week_results if r['status'] != 'success')

        report = []
        report.append("\n" + "="*80)
        report.append("FILEORGANIZER v1.0 - BUILD REPORT")
        report.append("="*80)
        report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Total Duration: {total_duration / 60:.1f} minutes")
        report.append(f"\nWeeks Completed: {successful_weeks}/9")
        report.append(f"Weeks Failed: {failed_weeks}/9")

        report.append("\n" + "-"*80)
        report.append("WEEK-BY-WEEK RESULTS")
        report.append("-"*80)

        for result in self.week_results:
            status_emoji = {
                'success': '[OK]',
                'failed': '[ERROR]',
                'timeout': '[TIMEOUT]',
                'error': '💥'
            }.get(result['status'], '[UNKNOWN]')

            duration = result.get('duration', 0)
            report.append(
                f"\nWeek {result['week']}: {status_emoji} {result['status'].upper()} "
                f"({duration:.1f}s)"
            )

            if 'error' in result:
                report.append(f"  Error: {result['error'][:200]}")

        report.append("\n" + "="*80)

        if failed_weeks == 0:
            report.append("🎉 BUILD SUCCESS - All 9 weeks completed!")
            report.append("\nFileOrganizer v1.0.0 Alpha is ready for testing.")
        else:
            report.append("[WARNING] BUILD INCOMPLETE - Some weeks failed")
            report.append(f"\nPlease review errors above and retry failed weeks.")

        report.append("="*80)

        return "\n".join(report)

    def save_report(self, report: str):
        """Save build report to file"""
        reports_dir = self.project_root / "build_reports"
        reports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = reports_dir / f"build_report_{timestamp}.txt"

        with open(report_file, 'w') as f:
            f.write(report)

        print(f"\n📄 Build report saved: {report_file}")

    def run_all_weeks(self):
        """Execute all 9 weeks sequentially"""
        self.start_time = time.time()

        print("\n" + "="*80)
        print("FILEORGANIZER v1.0 - MASTER BUILD")
        print("="*80)
        print(f"\nStarted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("Total Weeks: 9")
        print("\nThis will take approximately 30-60 minutes depending on system performance.")
        print("\n" + "="*80)

        # Execute each week
        for week_num in range(1, 10):
            success = self.run_week(week_num)

            if not success:
                print(f"\n[WARNING] Week {week_num} failed. Stopping build.")
                print("You can review errors and retry individual weeks.")
                break

            # Brief pause between weeks
            if week_num < 9:
                print(f"\nProceeding to Week {week_num + 1}...")
                time.sleep(2)

        # Generate and display report
        report = self.generate_report()
        print(report)

        # Save report
        self.save_report(report)


def main():
    """Main entry point"""
    # Determine project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    print(f"Project root: {project_root}")

    # Verify all week scripts exist
    missing_scripts = []
    for week_num in range(1, 10):
        script_path = script_dir / f"week{week_num}_build.py"
        if not script_path.exists():
            missing_scripts.append(f"week{week_num}_build.py")

    if missing_scripts:
        print("[ERROR] Missing build scripts:")
        for script in missing_scripts:
            print(f"  - {script}")
        sys.exit(1)

    # Confirm execution
    print("\n[WARNING]  This will execute all 9 weeks of FileOrganizer v1.0 build.")
    print("Expected duration: 30-60 minutes")
    response = input("\nProceed? (yes/no): ")

    if response.lower() not in ['yes', 'y']:
        print("Build cancelled.")
        sys.exit(0)

    # Run orchestrator
    orchestrator = BuildOrchestrator(project_root)
    orchestrator.run_all_weeks()


if __name__ == "__main__":
    main()
