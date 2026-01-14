"""
Monitor BUILD-127 and BUILD-129 running in parallel.

Tracks:
- Execution progress for both builds
- Token usage and truncation events
- BUILD-112/113/114 stability metrics
- Success/failure status
"""

import time
import re
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime


def tail_log(log_file: Path, lines: int = 20) -> str:
    """Get last N lines from log file."""
    try:
        content = log_file.read_text(encoding="utf-8", errors="ignore")
        log_lines = content.split("\n")
        return "\n".join(log_lines[-lines:])
    except Exception as e:
        return f"Error reading log: {e}"


def extract_status(log_content: str) -> Dict:
    """Extract execution status from log content."""
    status = {
        "phase_state": "UNKNOWN",
        "attempt": 0,
        "token_usage": None,
        "truncation": False,
        "deep_retrieval": False,
        "structured_fallback": False,
        "last_activity": None,
    }

    # Find last state update
    state_matches = re.findall(r"Updated phase .* status to (\w+)", log_content)
    if state_matches:
        status["phase_state"] = state_matches[-1]

    # Find attempt number
    attempt_matches = re.findall(r"Attempt (\d+)/\d+", log_content)
    if attempt_matches:
        status["attempt"] = int(attempt_matches[-1])

    # Find token usage
    token_matches = re.findall(
        r"TOKEN_BUDGET.*output=(\d+)/(\d+).*utilization=([\d.]+)%", log_content
    )
    if token_matches:
        used, total, util = token_matches[-1]
        status["token_usage"] = f"{used}/{total} ({util}%)"
        if float(util) >= 95:
            status["truncation"] = True

    # Check for BUILD-112/113/114 triggers
    status["deep_retrieval"] = "[DeepRetrieval] Starting bounded retrieval" in log_content
    status["structured_fallback"] = "Falling back to structured_edit" in log_content

    # Find last timestamp
    timestamps = re.findall(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", log_content)
    if timestamps:
        status["last_activity"] = timestamps[-1]

    return status


def print_dashboard(build127_status: Dict, build129_status: Dict):
    """Print monitoring dashboard."""
    print("\n" + "=" * 100)
    print(f"PARALLEL BUILD MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    # BUILD-127 Status
    print("\nBUILD-127: Self-Healing Governance (Retry)")
    print("-" * 50)
    print(f"  State: {build127_status['phase_state']}")
    print(f"  Attempt: {build127_status['attempt']}")
    if build127_status["token_usage"]:
        print(f"  Token Usage: {build127_status['token_usage']}")
    if build127_status["truncation"]:
        print("  ⚠️  TRUNCATION DETECTED")
    if build127_status["deep_retrieval"]:
        print("  ✅ BUILD-112: Deep retrieval triggered")
    if build127_status["structured_fallback"]:
        print("  ✅ BUILD-114: Structured edit fallback triggered")
    if build127_status["last_activity"]:
        print(f"  Last Activity: {build127_status['last_activity']}")

    # BUILD-129 Status
    print("\nBUILD-129: Token Budget Intelligence (Phase 1)")
    print("-" * 50)
    print(f"  State: {build129_status['phase_state']}")
    print(f"  Attempt: {build129_status['attempt']}")
    if build129_status["token_usage"]:
        print(f"  Token Usage: {build129_status['token_usage']}")
    if build129_status["truncation"]:
        print("  ⚠️  TRUNCATION DETECTED")
    if build129_status["deep_retrieval"]:
        print("  ✅ BUILD-112: Deep retrieval triggered")
    if build129_status["structured_fallback"]:
        print("  ✅ BUILD-114: Structured edit fallback triggered")
    if build129_status["last_activity"]:
        print(f"  Last Activity: {build129_status['last_activity']}")

    print("\n" + "=" * 100)


def main():
    """Monitor both builds."""
    build127_log = Path(".autonomous_runs/build127-phase1-retry.log")
    build129_log = Path(".autonomous_runs/build129-phase1.log")

    print("Monitoring BUILD-127 and BUILD-129 in parallel...")
    print("Press Ctrl+C to stop monitoring")
    print()

    try:
        while True:
            # Read logs
            build127_content = tail_log(build127_log, lines=100) if build127_log.exists() else ""
            build129_content = tail_log(build129_log, lines=100) if build129_log.exists() else ""

            # Extract status
            build127_status = extract_status(build127_content)
            build129_status = extract_status(build129_content)

            # Print dashboard
            print_dashboard(build127_status, build129_status)

            # Check if both complete
            if build127_status["phase_state"] in ["COMPLETE", "FAILED"] and build129_status[
                "phase_state"
            ] in ["COMPLETE", "FAILED"]:
                print("\n✅ Both builds finished!")
                print(f"BUILD-127: {build127_status['phase_state']}")
                print(f"BUILD-129: {build129_status['phase_state']}")
                break

            # Wait before next check
            time.sleep(30)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user")
    except Exception as e:
        print(f"\n\nError: {e}")


if __name__ == "__main__":
    main()
