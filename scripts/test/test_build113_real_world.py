"""BUILD-113 Real-World Testing with Research System Implementation

This script tests BUILD-113 (Iterative Autonomous Investigation) with a real
implementation task: the Research System Tracer Bullet (Chunk 0).

Test Objectives:
1. Manual testing with real failure scenarios
2. Performance tuning of risk thresholds (validate 100/200 lines)
3. Validate autonomous fix decisions in production
4. Document decision quality and success rate

Test Setup:
- Use chunk0-tracer-bullet.yaml as the requirements
- Launch autonomous executor with --enable-autonomous-fixes
- Monitor all autonomous decisions made
- Track success/failure rate of autonomous fixes
- Measure impact on iteration velocity

Expected Outcomes:
- Import errors → CLEAR_FIX (auto-applied)
- Small fixes (<100 lines) → CLEAR_FIX
- Medium fixes (100-200 lines) → Review confidence/risk alignment
- Large fixes (>200 lines) → RISKY (escalate to human)
- Ambiguous cases → AMBIGUOUS (escalate to human)
"""

import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

def main():
    print("=" * 80)
    print("BUILD-113 REAL-WORLD TEST: Research System Tracer Bullet")
    print("=" * 80)
    print()

    # Configuration
    workspace = Path.cwd()
    run_id = f"research-tracer-bullet-build113-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    requirements_file = workspace / ".autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/chunk0-tracer-bullet.yaml"
    api_url = "http://127.0.0.1:8001"

    # Validation
    if not requirements_file.exists():
        print(f"[ERROR] Requirements file not found: {requirements_file}")
        print("   Please ensure the research system requirements are in place.")
        return 1

    print(f"[OK] Requirements file: {requirements_file.name}")
    print(f"[OK] Run ID: {run_id}")
    print(f"[OK] API URL: {api_url}")
    print()

    # Test plan
    print("TEST PLAN:")
    print("-" * 80)
    print("1. Launch autonomous executor with --enable-autonomous-fixes")
    print("2. Monitor decisions made by BUILD-113 components:")
    print("   - IterativeInvestigator (evidence collection)")
    print("   - GoalAwareDecisionMaker (decision logic)")
    print("   - DecisionExecutor (execution with safety nets)")
    print("3. Track autonomous fix metrics:")
    print("   - CLEAR_FIX decisions (auto-applied)")
    print("   - RISKY decisions (blocked for approval)")
    print("   - AMBIGUOUS decisions (escalated to human)")
    print("   - NEED_MORE_EVIDENCE (investigation continues)")
    print("4. Validate risk thresholds:")
    print("   - <100 lines = LOW risk → CLEAR_FIX (if high confidence)")
    print("   - 100-200 lines = MEDIUM risk → Review carefully")
    print("   - >200 lines = HIGH risk → RISKY (always block)")
    print("5. Document results in test report")
    print()

    # Confirm execution
    response = input("Start autonomous executor with BUILD-113 enabled? [y/N]: ")
    if response.lower() != 'y':
        print("Test cancelled.")
        return 0

    print()
    print("=" * 80)
    print("LAUNCHING AUTONOMOUS EXECUTOR")
    print("=" * 80)
    print()

    # Build command
    cmd = [
        "python", "-m", "autopack.autonomous_executor",
        "--run-id", run_id,
        "--requirements", str(requirements_file),
        "--api-url", api_url,
        "--enable-autonomous-fixes",  # BUILD-113 flag
        "--max-iterations", "30",
        "--verbose"
    ]

    print(f"Command: {' '.join(cmd)}")
    print()

    # Create log file
    log_file = workspace / ".autonomous_runs" / run_id / "build113_test.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"Logs: {log_file}")
    print()
    print("Press Ctrl+C to stop the executor")
    print("-" * 80)
    print()

    # Execute
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env={**subprocess.os.environ, "PYTHONUTF8": "1", "PYTHONPATH": "src"}
            )

            for line in process.stdout:
                print(line, end='')
                f.write(line)
                f.flush()

            returncode = process.wait()

    except KeyboardInterrupt:
        print()
        print("=" * 80)
        print("EXECUTION INTERRUPTED")
        print("=" * 80)
        process.terminate()
        process.wait()
        returncode = -1

    print()
    print("=" * 80)
    print("EXECUTION COMPLETE")
    print("=" * 80)
    print()

    # Analysis
    print("ANALYZING RESULTS...")
    print("-" * 80)

    # Look for decision logs
    decisions_dir = workspace / ".autonomous_runs" / run_id / "decisions"
    if decisions_dir.exists():
        decision_files = list(decisions_dir.glob("*.json"))
        print(f"[OK] Found {len(decision_files)} decision logs")
        print()

        if decision_files:
            print("DECISIONS SUMMARY:")
            print()

            clear_fix_count = 0
            risky_count = 0
            ambiguous_count = 0

            for decision_file in decision_files:
                with open(decision_file, 'r', encoding='utf-8') as f:
                    decision = json.load(f)

                decision_type = decision.get("decision_type", "unknown")
                choice = decision.get("choice", "")
                risk = decision.get("risk_assessment", {}).get("level", "UNKNOWN")

                if decision_type == "clear_fix":
                    clear_fix_count += 1
                    print(f"[CLEAR_FIX] {choice} (risk: {risk})")
                elif decision_type == "risky":
                    risky_count += 1
                    print(f"[RISKY] {choice} (risk: {risk})")
                elif decision_type == "ambiguous":
                    ambiguous_count += 1
                    print(f"[AMBIGUOUS] {choice} (risk: {risk})")

            print()
            print("METRICS:")
            print(f"  CLEAR_FIX (auto-applied): {clear_fix_count}")
            print(f"  RISKY (blocked): {risky_count}")
            print(f"  AMBIGUOUS (escalated): {ambiguous_count}")
            print(f"  Total decisions: {len(decision_files)}")

            if len(decision_files) > 0:
                auto_fix_rate = (clear_fix_count / len(decision_files)) * 100
                print(f"  Auto-fix rate: {auto_fix_rate:.1f}%")
    else:
        print("[WARNING] No decision logs found")
        print("   BUILD-113 may not have been triggered during execution")

    print()
    print("=" * 80)
    print("TEST REPORT")
    print("=" * 80)
    print()
    print(f"Test Execution: {'COMPLETED' if returncode == 0 else 'FAILED' if returncode > 0 else 'INTERRUPTED'}")
    print(f"Run ID: {run_id}")
    print(f"Log file: {log_file}")
    print(f"Decisions: {decisions_dir if decisions_dir.exists() else 'None'}")
    print()
    print("Next Steps:")
    print("1. Review decision logs to validate decision quality")
    print("2. Check if risk thresholds (100/200 lines) were appropriate")
    print("3. Identify cases where autonomous fixes helped vs. needed tuning")
    print("4. Document any enhancements needed for patch generation")
    print()

    return returncode if returncode >= 0 else 1

if __name__ == "__main__":
    sys.exit(main())
