#!/usr/bin/env python3
"""
Generic Autopack Runner

Universal script to delegate tasks from a markdown file to Autopack.
Works for any project and any phase (Phase 1, Phase 2, etc.).

Usage:
    python scripts/autopack_runner.py [--non-interactive] [--tasks-file FILENAME]

Examples:
    # Use default WHATS_LEFT_TO_BUILD.md
    python scripts/autopack_runner.py --non-interactive

    # Use custom task file
    python scripts/autopack_runner.py --non-interactive --tasks-file "REVISED_PLAN_V2.md"
    python scripts/autopack_runner.py --non-interactive --tasks-file "SPRINT_3_TASKS.md"

This script:
1. Auto-detects project name from directory structure
2. Reads tasks from specified markdown file (default: WHATS_LEFT_TO_BUILD.md)
3. Starts the Autopack FastAPI service (if not running)
4. Creates a new run with all tasks from the markdown file
5. Polls for completion
6. Generates final report

Based on Autopack v7 playbook API (src/autopack/main.py)
"""

import os
import sys
import time
import requests
import json
import subprocess
import signal
import atexit
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Autopack API configuration
AUTOPACK_API_BASE = os.getenv("AUTOPACK_API_URL", "http://localhost:8000")
AUTOPACK_API_KEY = os.getenv("AUTOPACK_API_KEY", "")

# Global reference to Autopack service process
_autopack_process = None


class AutopackRunner:
    """Generic runner for any Autopack project - reads from a markdown file"""

    def __init__(self, project_name: str = None, tasks_file: str = "WHATS_LEFT_TO_BUILD.md"):
        self.api_base = AUTOPACK_API_BASE
        self.headers = {}
        if AUTOPACK_API_KEY:
            self.headers["X-API-Key"] = AUTOPACK_API_KEY

        # Auto-detect project name from directory if not provided
        if not project_name:
            # Get project directory name from path (.autonomous_runs/<project-slug>/)
            project_dir = Path(__file__).parent.parent.name
            project_name = project_dir

        self.project_name = project_name
        self.tasks_file = tasks_file

        # Resolve tasks file path (relative to project root)
        project_root = Path(__file__).parent.parent
        self.tasks_file_path = project_root / tasks_file

        # Validate tasks file exists
        if not self.tasks_file_path.exists():
            raise FileNotFoundError(
                f"Tasks file not found: {self.tasks_file_path}\n"
                f"Make sure '{tasks_file}' exists in the project directory."
            )

        # Generate unique run ID (generic, not phase-specific)
        self.run_id = f"{project_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    def check_autopack_health(self) -> bool:
        """Check if Autopack service is running"""
        try:
            response = requests.get(f"{self.api_base}/health", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False

    def start_autopack_service(self) -> bool:
        """Start Autopack FastAPI service in background"""
        global _autopack_process

        # Find the Autopack root directory
        autopack_root = Path(__file__).parent.parent.parent.parent

        print(f"[INFO] Starting Autopack service at {autopack_root}...")

        try:
            # Start uvicorn in background
            _autopack_process = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "src.autopack.main:app", "--host", "0.0.0.0", "--port", "8000"],
                cwd=str(autopack_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )

            # Register cleanup on exit
            def cleanup():
                global _autopack_process
                if _autopack_process and _autopack_process.poll() is None:
                    print("\n[INFO] Shutting down Autopack service...")
                    if sys.platform == "win32":
                        _autopack_process.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        _autopack_process.terminate()
                    try:
                        _autopack_process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        _autopack_process.kill()

            atexit.register(cleanup)

            # Wait for service to be ready (up to 30 seconds)
            print("[INFO] Waiting for Autopack service to be ready...")
            for i in range(30):
                time.sleep(1)
                if self.check_autopack_health():
                    print(f"[OK] Autopack service started successfully")
                    return True

            print("[ERROR] Autopack service did not become healthy within 30 seconds")
            return False

        except Exception as e:
            print(f"[ERROR] Failed to start Autopack service: {e}")
            return False

    def parse_tasks_from_markdown(self) -> tuple[list, list]:
        """
        Parse tasks from markdown file in Autopack format.

        Expected format:
        ### Task N: Task Name
        **Phase ID**: `task-id`
        **Category**: category
        **Complexity**: low|medium|high
        **Description**: Description text

        Returns:
            tuple of (phases, tiers)
        """
        print(f"[INFO] Reading tasks from: {self.tasks_file_path}")

        with open(self.tasks_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        phases = []
        tiers_dict = {}  # tier_id -> tier data
        phase_index = 0

        # Simple regex-based parser (can be enhanced with proper markdown parser)
        import re

        # Find all task sections
        task_pattern = r'###\s+Task\s+\d+:\s+(.+?)\n\*\*Phase ID\*\*:\s+`(.+?)`\n\*\*Category\*\*:\s+(\w+)\n\*\*Complexity\*\*:\s+(\w+)\n\*\*Description\*\*:\s+(.+?)(?=\n\n|\*\*|###|$)'

        matches = re.finditer(task_pattern, content, re.DOTALL | re.MULTILINE)

        for match in matches:
            task_name = match.group(1).strip()
            phase_id = match.group(2).strip()
            category = match.group(3).strip()
            complexity = match.group(4).strip()
            description = match.group(5).strip()

            # Determine tier based on complexity (simple heuristic)
            if complexity == "low":
                tier_id = "tier1-high-priority"
                tier_name = "High Priority"
                tier_index = 0
            elif complexity == "medium":
                tier_id = "tier2-medium-priority"
                tier_name = "Medium Priority"
                tier_index = 1
            else:  # high
                tier_id = "tier3-low-priority"
                tier_name = "Low Priority (Complex)"
                tier_index = 2

            # Add tier to dict if not exists
            if tier_id not in tiers_dict:
                tiers_dict[tier_id] = {
                    "tier_id": tier_id,
                    "tier_index": tier_index,
                    "name": tier_name,
                    "description": f"{tier_name} tasks",
                }

            # Create phase
            phase = {
                "phase_id": phase_id,
                "phase_index": phase_index,
                "tier_id": tier_id,
                "name": task_name,
                "description": description,
                "task_category": category,
                "complexity": complexity,
                "builder_mode": "prototype",  # Default
            }

            phases.append(phase)
            phase_index += 1

        # Convert tiers dict to sorted list
        tiers = sorted(tiers_dict.values(), key=lambda t: t['tier_index'])

        print(f"[INFO] Parsed {len(phases)} tasks from {self.tasks_file}")
        print(f"[INFO] Organized into {len(tiers)} tiers")

        if not phases:
            raise ValueError(
                f"No tasks found in {self.tasks_file}!\n"
                f"Make sure the file follows Autopack task format:\n"
                f"  ### Task N: Task Name\n"
                f"  **Phase ID**: `task-id`\n"
                f"  **Category**: category\n"
                f"  **Complexity**: low|medium|high\n"
                f"  **Description**: Description text"
            )

        return phases, tiers

    def create_run(self) -> Dict:
        """Create Autopack run with all tasks from markdown file"""
        # Parse tasks from markdown file
        phases, tiers = self.parse_tasks_from_markdown()

        # Create run request payload
        payload = {
            "run": {
                "run_id": self.run_id,
                "safety_profile": "standard",
                "run_scope": "feature_backlog",
                "token_cap": 150000,  # 150K tokens (from 128K estimate + buffer)
                "max_phases": 9,
                "max_duration_minutes": 300,  # 5 hours max
            },
            "tiers": tiers,
            "phases": phases,
        }

        print(f"\n{'='*80}")
        print(f"CREATING AUTOPACK RUN: {self.run_id}")
        print(f"{'='*80}\n")
        print(f"Phases: {len(phases)}")
        print(f"Tiers: {len(tiers)}")
        print(f"Token Cap: 150,000")
        print(f"Max Duration: 5 hours\n")

        response = requests.post(
            f"{self.api_base}/runs/start",
            json=payload,
            headers=self.headers,
        )

        if response.status_code != 201:
            raise Exception(f"Failed to create run: {response.status_code} - {response.text}")

        run_data = response.json()
        print(f"[OK] Run created: {run_data['id']}")
        print(f"State: {run_data['state']}\n")

        return run_data

    def poll_run_status(self, run_id: str, poll_interval: int = 30) -> Dict:
        """Poll run status until completion"""
        print(f"{'='*80}")
        print(f"MONITORING RUN PROGRESS")
        print(f"{'='*80}\n")
        print(f"Polling every {poll_interval} seconds...")
        print(f"Press Ctrl+C to stop monitoring (run will continue)\n")

        start_time = time.time()

        try:
            while True:
                response = requests.get(
                    f"{self.api_base}/runs/{run_id}",
                    headers=self.headers,
                )

                if response.status_code != 200:
                    print(f"[ERROR] Failed to get run status: {response.status_code}")
                    time.sleep(poll_interval)
                    continue

                run_data = response.json()
                state = run_data["state"]

                # Get dashboard status for progress
                try:
                    dashboard_response = requests.get(
                        f"{self.api_base}/dashboard/runs/{run_id}/status",
                        headers=self.headers,
                    )
                    if dashboard_response.status_code == 200:
                        dashboard_data = dashboard_response.json()
                        percent = dashboard_data.get("percent_complete", 0)
                        current_phase = dashboard_data.get("current_phase_name", "N/A")
                        tokens_used = dashboard_data.get("tokens_used", 0)
                        token_cap = dashboard_data.get("token_cap", 150000)

                        elapsed = int(time.time() - start_time)
                        print(
                            f"[{elapsed}s] Progress: {percent:.1f}% | "
                            f"Phase: {current_phase} | "
                            f"Tokens: {tokens_used}/{token_cap}"
                        )
                except Exception as e:
                    print(f"[WARNING] Could not fetch dashboard status: {e}")

                # Check if run is complete
                if state.startswith("DONE_"):
                    print(f"\n{'='*80}")
                    print(f"RUN COMPLETE: {state}")
                    print(f"{'='*80}\n")
                    return run_data

                time.sleep(poll_interval)

        except KeyboardInterrupt:
            print(f"\n[INFO] Monitoring stopped. Run {run_id} continues in background.")
            print(f"Check status: GET {self.api_base}/runs/{run_id}")
            return None

    def generate_report(self, run_id: str) -> str:
        """Generate comprehensive Phase 2 completion report"""
        # Get run summary
        response = requests.get(
            f"{self.api_base}/reports/run_summary/{run_id}",
            headers=self.headers,
        )

        if response.status_code != 200:
            raise Exception(f"Failed to get run summary: {response.status_code}")

        summary = response.json()

        # Build report
        report = []
        report.append("=" * 80)
        report.append("FILEORGANIZER PHASE 2 - AUTOPACK AUTONOMOUS BUILD REPORT")
        report.append("=" * 80)
        report.append(f"\nRun ID: {run_id}")
        report.append(f"Run State: {summary['state']}")
        report.append(f"Safety Profile: {summary['safety_profile']}")
        report.append(f"Started: {summary.get('started_at', 'N/A')}")
        report.append(f"Completed: {summary.get('completed_at', 'N/A')}")

        report.append("\n" + "=" * 80)
        report.append("BUDGET UTILIZATION")
        report.append("=" * 80)
        budgets = summary["budgets"]
        report.append(f"Tokens Used: {budgets['tokens_used']:,} / {budgets['token_cap']:,}")
        report.append(f"Token Utilization: {budgets['token_utilization']:.1%}")
        report.append(f"Phases Executed: {budgets['phase_count']} / {budgets['max_phases']}")

        report.append("\n" + "=" * 80)
        report.append("ISSUE TRACKING")
        report.append("=" * 80)
        issues = summary["issues"]
        report.append(f"Minor Issues: {issues['minor_count']}")
        report.append(f"Major Issues: {issues['major_count']}")
        report.append(f"Distinct Issues: {issues['distinct_issues']}")

        report.append("\n" + "=" * 80)
        report.append("TIER RESULTS")
        report.append("=" * 80)
        for tier in summary["tiers"]:
            report.append(
                f"\nTier {tier['tier_id']}: {tier['name']} "
                f"[{tier['state']}]"
            )
            report.append(f"  Phases: {tier['phase_count']}")
            report.append(f"  Tokens: {tier['tokens_used']:,}")
            report.append(f"  Issues: {tier['minor_issues']} minor, {tier['major_issues']} major")

        report.append("\n" + "=" * 80)
        report.append("PHASE RESULTS")
        report.append("=" * 80)
        for phase in summary["phases"]:
            status_icon = {
                "COMPLETE": "✅",
                "FAILED": "❌",
                "GATE": "⚠️",
                "QUEUED": "⏳",
                "EXECUTING": "🔄",
            }.get(phase["state"], "❓")

            report.append(
                f"\n{status_icon} Phase {phase['phase_index']}: {phase['name']} "
                f"[{phase['state']}]"
            )
            report.append(f"  Category: {phase['task_category']} | Complexity: {phase['complexity']}")
            report.append(
                f"  Builder Attempts: {phase['builder_attempts']} | "
                f"Auditor Attempts: {phase['auditor_attempts']}"
            )
            report.append(f"  Tokens: {phase['tokens_used']:,}")
            report.append(f"  Issues: {phase['minor_issues']} minor, {phase['major_issues']} major")

        report.append("\n" + "=" * 80)
        report.append("OVERALL ASSESSMENT")
        report.append("=" * 80)

        # Calculate success rate
        completed = len([p for p in summary["phases"] if p["state"] == "COMPLETE"])
        total = len(summary["phases"])
        success_rate = (completed / total * 100) if total > 0 else 0

        report.append(f"\nPhases Completed: {completed}/{total} ({success_rate:.1f}%)")

        if summary["state"] == "DONE_SUCCESS":
            report.append(f"\n[SUCCESS] All tasks completed for {self.project_name}!")
            report.append(f"Project build finished successfully")
        elif summary["state"] == "DONE_FAILED_BUDGET_EXHAUSTED":
            report.append("\n[BUDGET EXHAUSTED] Token cap exceeded")
            report.append(f"Review remaining phases and increase budget")
        elif summary["state"].startswith("DONE_FAILED"):
            report.append(f"\n[FAILED] Run failed: {summary['state']}")
            report.append("Review phase logs and issue backlog")
        else:
            report.append(f"\n[PARTIAL SUCCESS] {completed}/{total} phases completed")

        report.append("\n" + "=" * 80)

        return "\n".join(report)

    def save_report(self, report: str):
        """Save report to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = Path(f"AUTOPACK_BUILD_REPORT_{timestamp}.md")

        with open(report_path, "w") as f:
            f.write(report)

        print(f"\nReport saved: {report_path}")
        return report_path

    def run(self):
        """Execute autonomous build for this project"""
        print("\n" + "=" * 80)
        print(f"{self.project_name.upper()} - AUTOPACK AUTONOMOUS BUILD")
        print("=" * 80)

        # 1. Check Autopack service health (auto-start if needed)
        print("\n[Step 1/5] Checking Autopack service...")
        if not self.check_autopack_health():
            print(f"[INFO] Autopack service not running at {self.api_base}")
            print("[INFO] Auto-starting Autopack service...")

            if not self.start_autopack_service():
                print(f"\n[ERROR] Failed to auto-start Autopack service")
                print("\nManual start option:")
                print("  cd c:/dev/Autopack")
                print("  uvicorn src.autopack.main:app --reload")
                sys.exit(1)

        print(f"[OK] Autopack service healthy at {self.api_base}")

        # 2. Create run
        print("\n[Step 2/4] Creating Autopack run...")
        try:
            run_data = self.create_run()
        except Exception as e:
            print(f"\n[ERROR] Failed to create run: {e}")
            sys.exit(1)

        # 3. Monitor progress
        print("\n[Step 3/4] Monitoring run progress...")
        final_run = self.poll_run_status(self.run_id)

        if not final_run:
            print("\n[INFO] Monitoring stopped. Run continues in background.")
            print(f"Check status: GET {self.api_base}/runs/{self.run_id}")
            return

        # 4. Generate report
        print("\n[Step 4/4] Generating report...")
        try:
            report = self.generate_report(self.run_id)
            print("\n" + report)
            self.save_report(report)
        except Exception as e:
            print(f"\n[ERROR] Failed to generate report: {e}")
            sys.exit(1)

        print(f"\n[DONE] {self.project_name} autonomous build complete!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generic Autopack Autonomous Build Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default WHATS_LEFT_TO_BUILD.md
  python scripts/autopack_runner.py --non-interactive

  # Use custom tasks file
  python scripts/autopack_runner.py --non-interactive --tasks-file "REVISED_PLAN_V2.md"
  python scripts/autopack_runner.py --non-interactive --tasks-file "SPRINT_3_TASKS.md"
        """
    )
    parser.add_argument(
        '--non-interactive',
        action='store_true',
        help='Run in non-interactive mode (no user prompts, auto-start service)'
    )
    parser.add_argument(
        '--project-name',
        type=str,
        help='Project name (auto-detected from directory if not provided)'
    )
    parser.add_argument(
        '--tasks-file',
        type=str,
        default='WHATS_LEFT_TO_BUILD.md',
        help='Markdown file containing tasks (default: WHATS_LEFT_TO_BUILD.md)'
    )
    args = parser.parse_args()

    # Create runner (auto-detects project if not specified)
    try:
        runner = AutopackRunner(
            project_name=args.project_name,
            tasks_file=args.tasks_file
        )
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    print(f"{runner.project_name} - Autopack Autonomous Build Runner")
    print(f"Autopack API: {AUTOPACK_API_BASE}")
    print(f"Tasks File: {runner.tasks_file}")
    print()

    # Confirmation (only in interactive mode)
    if not args.non_interactive:
        response = input(f"Start autonomous build for {runner.project_name} using {runner.tasks_file}? (yes/no): ")

        if response.lower() not in ["yes", "y"]:
            print("Build cancelled.")
            sys.exit(0)
    else:
        print(f"[NON-INTERACTIVE MODE] Proceeding with full autonomous build for {runner.project_name}...")
        print(f"[NON-INTERACTIVE MODE] Using tasks from: {runner.tasks_file}")
        print("[NON-INTERACTIVE MODE] Will auto-start Autopack service if needed...")
        print()

    runner.run()
