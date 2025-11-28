#!/usr/bin/env python3
"""
FileOrganizer Phase 2 Build Orchestrator - Autopack Test Run
Executes items from WHATS_LEFT_TO_BUILD.md with detailed reporting
"""

import os
import subprocess
import sys
import time
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


class Phase2Orchestrator:
    """Orchestrates FileOrganizer Phase 2 build tasks for Autopack testing"""

    def __init__(self):
        self.scripts_dir = Path(__file__).parent
        self.project_root = self.scripts_dir.parent
        self.logs_dir = self.project_root / "logs" / "phase2"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.task_results = []
        self.start_time = time.time()
        self.token_usage = {
            'total': 0,
            'by_task': {}
        }

    def run_task(self, task_num: int, task_name: str, script_name: str,
                 estimated_tokens: int, optional: bool = False) -> bool:
        """Execute a single Phase 2 task"""
        print("\n" + "="*80)
        print(f"{'PHASE 2 TASK ' + str(task_num) + ': ' + task_name:^80}")
        print("="*80)
        print(f"Estimated tokens: {estimated_tokens}")
        print(f"Optional: {optional}")

        script_path = self.scripts_dir / script_name

        if not script_path.exists():
            print(f"[ERROR] Script not found: {script_path}")
            if optional:
                print("[WARNING] Task is optional - continuing")
                self.task_results.append({
                    'task': task_num,
                    'name': task_name,
                    'status': 'skipped',
                    'reason': 'script not found',
                    'optional': optional
                })
                return True
            return False

        task_start = time.time()
        log_file = self.logs_dir / f"task{task_num}_{task_name.replace(' ', '_').lower()}.log"

        try:
            with open(log_file, 'w', encoding='utf-8') as log:
                result = subprocess.run(
                    [sys.executable, str(script_path)],
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1 hour timeout per task
                )

                # Write output to log file
                log.write("STDOUT:\n")
                log.write(result.stdout)
                log.write("\n\nSTDERR:\n")
                log.write(result.stderr)

            task_duration = time.time() - task_start

            # Estimate token usage (rough heuristic: 3 tokens per second of execution)
            estimated_task_tokens = int(task_duration * 3)
            self.token_usage['by_task'][task_name] = estimated_task_tokens
            self.token_usage['total'] += estimated_task_tokens

            if result.returncode == 0:
                print(f"\n[OK] Task {task_num} completed in {task_duration:.1f} seconds")
                print(f"Estimated tokens used: ~{estimated_task_tokens}")
                self.task_results.append({
                    'task': task_num,
                    'name': task_name,
                    'status': 'success',
                    'duration': task_duration,
                    'tokens_estimated': estimated_task_tokens,
                    'log_file': str(log_file)
                })
                return True
            else:
                print(f"\n[ERROR] Task {task_num} failed")
                print(f"See log: {log_file}")

                if optional:
                    print("[WARNING] Task is optional - continuing")
                    self.task_results.append({
                        'task': task_num,
                        'name': task_name,
                        'status': 'failed_optional',
                        'duration': task_duration,
                        'tokens_estimated': estimated_task_tokens,
                        'error': result.stderr[:500],
                        'log_file': str(log_file)
                    })
                    return True
                else:
                    self.task_results.append({
                        'task': task_num,
                        'name': task_name,
                        'status': 'failed',
                        'duration': task_duration,
                        'tokens_estimated': estimated_task_tokens,
                        'error': result.stderr[:500],
                        'log_file': str(log_file)
                    })
                    return False

        except subprocess.TimeoutExpired:
            print(f"\n[ERROR] Task {task_num} timed out after 1 hour")
            self.task_results.append({
                'task': task_num,
                'name': task_name,
                'status': 'timeout',
                'duration': 3600
            })
            return False

        except Exception as e:
            print(f"\n[ERROR] Task {task_num} error: {str(e)}")
            self.task_results.append({
                'task': task_num,
                'name': task_name,
                'status': 'error',
                'error': str(e)
            })
            return False

    def generate_comprehensive_report(self) -> str:
        """Generate detailed Phase 2 build report"""
        total_duration = time.time() - self.start_time
        successful_tasks = len([r for r in self.task_results if r['status'] == 'success'])
        failed_tasks = len([r for r in self.task_results if r['status'] == 'failed'])
        skipped_tasks = len([r for r in self.task_results if r['status'] in ['skipped', 'failed_optional']])

        report = []
        report.append("="*80)
        report.append("FILEORGANIZER PHASE 2 - AUTOPACK TEST RUN REPORT")
        report.append("="*80)
        report.append(f"\nBuild Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"Total Duration: {total_duration / 60:.1f} minutes")
        report.append(f"Estimated Total Tokens: ~{self.token_usage['total']}")
        report.append("")

        report.append("="*80)
        report.append("SUMMARY")
        report.append("="*80)
        report.append(f"Total Tasks: {len(self.task_results)}")
        report.append(f"Successful: {successful_tasks}")
        report.append(f"Failed: {failed_tasks}")
        report.append(f"Skipped/Optional: {skipped_tasks}")

        success_rate = (successful_tasks / len(self.task_results) * 100) if self.task_results else 0
        report.append(f"\nSuccess Rate: {success_rate:.1f}%")

        report.append("\n" + "="*80)
        report.append("TASK-BY-TASK RESULTS")
        report.append("="*80)

        for result in self.task_results:
            status_icon = {
                'success': '[OK]',
                'failed': '[ERROR]',
                'failed_optional': '[WARNING]',
                'skipped': '[SKIPPED]',
                'timeout': '[TIMEOUT]',
                'error': '[ERROR]'
            }.get(result['status'], '[UNKNOWN]')

            duration = result.get('duration', 0)
            tokens = result.get('tokens_estimated', 0)

            report.append(f"\nTask {result['task']}: {status_icon} {result['name']}")
            if duration > 0:
                report.append(f"  Duration: {duration:.1f}s | Estimated tokens: ~{tokens}")

            if 'error' in result:
                report.append(f"  Error: {result['error'][:200]}")

            if 'log_file' in result:
                report.append(f"  Log: {result['log_file']}")

        report.append("\n" + "="*80)
        report.append("TOKEN USAGE BREAKDOWN")
        report.append("="*80)

        for task_name, tokens in self.token_usage['by_task'].items():
            percentage = (tokens / self.token_usage['total'] * 100) if self.token_usage['total'] > 0 else 0
            report.append(f"{task_name}: ~{tokens} tokens ({percentage:.1f}%)")

        report.append("\n" + "="*80)
        report.append("AREAS FOR IMPROVEMENT")
        report.append("="*80)

        # Analyze failures and generate insights
        if failed_tasks > 0:
            report.append("\nFailed Tasks Analysis:")
            for result in self.task_results:
                if result['status'] == 'failed':
                    report.append(f"- {result['name']}: {result.get('error', 'Unknown error')[:200]}")

        if skipped_tasks > 0:
            report.append("\nSkipped/Optional Tasks:")
            for result in self.task_results:
                if result['status'] in ['skipped', 'failed_optional']:
                    reason = result.get('reason', result.get('error', 'Optional task failed'))
                    report.append(f"- {result['name']}: {reason[:200]}")

        report.append("\n" + "="*80)
        report.append("CONCERNS & RECOMMENDATIONS")
        report.append("="*80)

        # Generate concerns based on results
        concerns = []

        if success_rate < 100:
            concerns.append(f"- Success rate below 100% ({success_rate:.1f}%) - review failed tasks")

        if self.token_usage['total'] > 110000:  # From WHATS_LEFT estimate
            concerns.append(f"- Token usage (~{self.token_usage['total']}) exceeded estimate (110K)")

        if failed_tasks > 0:
            concerns.append(f"- {failed_tasks} tasks failed - may require manual intervention")

        if concerns:
            report.extend(concerns)
        else:
            report.append("No major concerns identified")

        report.append("\n" + "="*80)
        report.append("OVERALL ASSESSMENT")
        report.append("="*80)

        if successful_tasks == len(self.task_results):
            report.append("[SUCCESS] All Phase 2 tasks completed successfully!")
            report.append("\nAutopack Validation: PASSED")
            report.append("- Fully autonomous execution confirmed")
            report.append("- All deliverables generated")
            report.append("- Ready for Beta release preparation")
        elif success_rate >= 70:
            report.append("[PARTIAL SUCCESS] Most tasks completed")
            report.append("\nAutopack Validation: PARTIAL PASS")
            report.append(f"- {successful_tasks}/{len(self.task_results)} tasks successful")
            report.append("- Review failed tasks for patterns")
            report.append("- May require Auditor intervention on failures")
        else:
            report.append("[NEEDS REVIEW] Multiple task failures")
            report.append("\nAutopack Validation: NEEDS WORK")
            report.append(f"- Only {successful_tasks}/{len(self.task_results)} tasks successful")
            report.append("- Significant manual intervention required")
            report.append("- Review build scripts and error logs")

        report.append("\n" + "="*80)

        return "\n".join(report)

    def save_report(self, report: str):
        """Save comprehensive report to file"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.project_root / f"PHASE2_BUILD_REPORT_{timestamp}.md"

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)

        print(f"\nReport saved: {report_path}")

        # Also save JSON data
        json_path = self.project_root / f"PHASE2_BUILD_DATA_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                'start_time': self.start_time,
                'end_time': time.time(),
                'duration': time.time() - self.start_time,
                'token_usage': self.token_usage,
                'task_results': self.task_results
            }, f, indent=2)

        print(f"JSON data saved: {json_path}")

    def run_phase2(self):
        """Execute complete Phase 2 build sequence"""
        print("\n" + "="*80)
        print("FILEORGANIZER PHASE 2 - AUTOPACK TEST RUN")
        print("="*80)
        print(f"\nProject: {self.project_root}")
        print(f"Logs: {self.logs_dir}")
        print("\nExecuting WHATS_LEFT_TO_BUILD.md task sequence...")
        print("This will validate Autopack's autonomous build capabilities")
        print("\nEstimated duration: 25-35 hours")
        print("Estimated tokens: ~110K")
        print("\n" + "="*80)

        # Task 1: Test Suite Fixes (High Priority, LOW complexity)
        success = self.run_task(
            task_num=1,
            task_name="Test Suite Fixes",
            script_name="phase2_task1_test_fixes.py",
            estimated_tokens=8000,
            optional=False
        )
        if not success:
            print("\n[CRITICAL] Test suite fixes failed - stopping build")
            print("This is a prerequisite for Beta readiness")
            self.generate_and_save_report()
            return

        # Task 2: Frontend Build System (High Priority, LOW complexity)
        success = self.run_task(
            task_num=2,
            task_name="Frontend Build System",
            script_name="phase2_task2_frontend_build.py",
            estimated_tokens=5000,
            optional=False
        )
        if not success:
            print("\n[WARNING] Frontend build failed but continuing")

        # Task 3: Docker Deployment (Medium Priority, MEDIUM complexity)
        success = self.run_task(
            task_num=3,
            task_name="Docker Deployment",
            script_name="phase2_task3_docker.py",
            estimated_tokens=12000,
            optional=True  # Nice to have, not blocking Beta
        )

        # Task 4: Advanced Search & Filtering (Low Priority, MEDIUM complexity)
        success = self.run_task(
            task_num=4,
            task_name="Advanced Search & Filtering",
            script_name="phase2_task4_advanced_search.py",
            estimated_tokens=10000,
            optional=True
        )

        # Task 5: Batch Upload & Processing (Low Priority, MEDIUM complexity)
        success = self.run_task(
            task_num=5,
            task_name="Batch Upload & Processing",
            script_name="phase2_task5_batch_upload.py",
            estimated_tokens=10000,
            optional=True
        )

        # Task 6: Country-Specific Packs - UK (Medium Priority, MEDIUM complexity)
        # NOTE: Per GPT review, mark as experimental
        success = self.run_task(
            task_num=6,
            task_name="Country Pack - UK (EXPERIMENTAL)",
            script_name="phase2_task6_country_uk.py",
            estimated_tokens=15000,
            optional=True
        )

        # Task 7: Country-Specific Packs - Canada (Medium Priority, MEDIUM complexity)
        success = self.run_task(
            task_num=7,
            task_name="Country Pack - Canada (EXPERIMENTAL)",
            script_name="phase2_task7_country_canada.py",
            estimated_tokens=15000,
            optional=True
        )

        # Task 8: Country-Specific Packs - Australia (Medium Priority, MEDIUM complexity)
        success = self.run_task(
            task_num=8,
            task_name="Country Pack - Australia (EXPERIMENTAL)",
            script_name="phase2_task8_country_australia.py",
            estimated_tokens=15000,
            optional=True
        )

        # Task 9: User Authentication & Multi-User (Low Priority, HIGH complexity)
        # NOTE: Per GPT review, needs human architecture review
        success = self.run_task(
            task_num=9,
            task_name="Authentication & Multi-User (NEEDS REVIEW)",
            script_name="phase2_task9_authentication.py",
            estimated_tokens=20000,
            optional=True
        )

        # Generate final report
        self.generate_and_save_report()

    def generate_and_save_report(self):
        """Generate and save the comprehensive report"""
        report = self.generate_comprehensive_report()
        print("\n" + report)
        self.save_report(report)


if __name__ == "__main__":
    print("FileOrganizer Phase 2 Build Orchestrator")
    print("Testing Autopack autonomous build capabilities")
    print()

    # Confirmation prompt
    response = input("Proceed with Phase 2 autonomous build? (yes/no): ")

    if response.lower() not in ['yes', 'y']:
        print("Build cancelled.")
        sys.exit(0)

    orchestrator = Phase2Orchestrator()
    orchestrator.run_phase2()
