#!/usr/bin/env python3
"""
Generic Autopack Runner

Universal script to delegate tasks from WHATS_LEFT_TO_BUILD.md to Autopack.
Works for any project and any phase (Phase 1, Phase 2, etc.).

Usage:
    python scripts/autopack_runner.py [--non-interactive]

This script:
1. Auto-detects project name from directory structure
2. Starts the Autopack FastAPI service (if not running)
3. Creates a new run with all tasks from WHATS_LEFT_TO_BUILD.md
4. Polls for completion
5. Generates final report

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
    """Generic runner for any Autopack project - reads from WHATS_LEFT_TO_BUILD.md"""

    def __init__(self, project_name: str = None):
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

    def create_run(self) -> Dict:
        """Create Autopack run with all Phase 2 tasks"""
        # Define phases from WHATS_LEFT_TO_BUILD.md
        phases = [
            {
                "phase_id": "phase2-task1",
                "phase_index": 0,
                "tier_id": "tier1-high-priority",
                "name": "Test Suite Fixes",
                "description": "Fix httpx/starlette version conflicts, ensure all tests pass",
                "task_category": "testing",
                "complexity": "low",
                "builder_mode": "prototype",  # From Phase 1 success
            },
            {
                "phase_id": "phase2-task2",
                "phase_index": 1,
                "tier_id": "tier1-high-priority",
                "name": "Frontend Build System",
                "description": "npm install/build, Electron packaging, commit package-lock.json",
                "task_category": "frontend",
                "complexity": "low",
                "builder_mode": "prototype",
            },
            {
                "phase_id": "phase2-task3",
                "phase_index": 2,
                "tier_id": "tier2-medium-priority",
                "name": "Docker Deployment",
                "description": "Dockerfile, docker-compose.yml, deploy scripts, .dockerignore",
                "task_category": "deployment",
                "complexity": "medium",
                "builder_mode": "prototype",
            },
            {
                "phase_id": "phase2-task4",
                "phase_index": 3,
                "tier_id": "tier3-low-priority",
                "name": "Advanced Search & Filtering",
                "description": "SQLite FTS5, multi-field search, date range filtering",
                "task_category": "backend",
                "complexity": "medium",
                "builder_mode": "prototype",
            },
            {
                "phase_id": "phase2-task5",
                "phase_index": 4,
                "tier_id": "tier3-low-priority",
                "name": "Batch Upload & Processing",
                "description": "Multi-file upload, job queue, progress tracking",
                "task_category": "backend",
                "complexity": "medium",
                "builder_mode": "prototype",
            },
            {
                "phase_id": "phase2-task6",
                "phase_index": 5,
                "tier_id": "tier2-medium-priority",
                "name": "Country Pack - UK (EXPERIMENTAL)",
                "description": "UK tax & immigration YAML templates (mark EXPERIMENTAL)",
                "task_category": "domain",
                "complexity": "medium",
                "builder_mode": "prototype",
            },
            {
                "phase_id": "phase2-task7",
                "phase_index": 6,
                "tier_id": "tier2-medium-priority",
                "name": "Country Pack - Canada (EXPERIMENTAL)",
                "description": "Canada tax & immigration YAML templates (mark EXPERIMENTAL)",
                "task_category": "domain",
                "complexity": "medium",
                "builder_mode": "prototype",
            },
            {
                "phase_id": "phase2-task8",
                "phase_index": 7,
                "tier_id": "tier2-medium-priority",
                "name": "Country Pack - Australia (EXPERIMENTAL)",
                "description": "Australia tax & immigration YAML templates (mark EXPERIMENTAL)",
                "task_category": "domain",
                "complexity": "medium",
                "builder_mode": "prototype",
            },
            {
                "phase_id": "phase2-task9",
                "phase_index": 8,
                "tier_id": "tier3-low-priority",
                "name": "Authentication & Multi-User (NEEDS REVIEW)",
                "description": "User model, JWT auth, protected routes (requires security review)",
                "task_category": "security",
                "complexity": "high",
                "builder_mode": "prototype",
            },
        ]

        # Define tiers
        tiers = [
            {
                "tier_id": "tier1-high-priority",
                "tier_index": 0,
                "name": "High Priority (Beta Blockers)",
                "description": "Test suite and frontend build - must complete",
            },
            {
                "tier_id": "tier2-medium-priority",
                "tier_index": 1,
                "name": "Medium Priority (Core Value)",
                "description": "Docker, country packs - high value features",
            },
            {
                "tier_id": "tier3-low-priority",
                "tier_index": 2,
                "name": "Low Priority (Enhancements)",
                "description": "Search, batch upload, auth - nice to have",
            },
        ]

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

    parser = argparse.ArgumentParser(description="Generic Autopack Autonomous Build Runner")
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
    args = parser.parse_args()

    # Create runner (auto-detects project if not specified)
    runner = AutopackRunner(project_name=args.project_name)

    print(f"{runner.project_name} - Autopack Autonomous Build Runner")
    print(f"Autopack API: {AUTOPACK_API_BASE}")
    print()

    # Confirmation (only in interactive mode)
    if not args.non_interactive:
        response = input(f"Start autonomous build for {runner.project_name}? (yes/no): ")

        if response.lower() not in ["yes", "y"]:
            print("Build cancelled.")
            sys.exit(0)
    else:
        print(f"[NON-INTERACTIVE MODE] Proceeding with full autonomous build for {runner.project_name}...")
        print("[NON-INTERACTIVE MODE] Will auto-start Autopack service if needed...")
        print()

    runner.run()
