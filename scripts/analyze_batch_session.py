"""
Auto-analyze batch drain session JSON for telemetry metrics.

Usage:
  python scripts/analyze_batch_session.py <session-id>
  python scripts/analyze_batch_session.py batch-drain-20251228-061426

Or analyze the most recent session:
  python scripts/analyze_batch_session.py --latest
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional


def find_session_file(session_id: str) -> Optional[Path]:
    """Find session JSON file by ID."""
    sessions_dir = Path(".autonomous_runs/batch_drain_sessions")
    if not sessions_dir.exists():
        return None

    session_file = sessions_dir / f"{session_id}.json"
    if session_file.exists():
        return session_file
    return None


def find_latest_session() -> Optional[Path]:
    """Find most recent session JSON file."""
    sessions_dir = Path(".autonomous_runs/batch_drain_sessions")
    if not sessions_dir.exists():
        return None

    json_files = list(sessions_dir.glob("*.json"))
    if not json_files:
        return None

    # Sort by modification time, most recent first
    json_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return json_files[0]


def analyze_session(session_path: Path) -> None:
    """Analyze and print session metrics."""
    with open(session_path, encoding="utf-8") as f:
        session = json.load(f)

    # Basic info
    print("=" * 80)
    print("BATCH DRAIN SESSION ANALYSIS")
    print("=" * 80)
    print(f"Session ID: {session['session_id']}")
    print(f"Started: {session['started_at']}")
    print(f"Completed: {session.get('completed_at', 'STILL RUNNING')}")
    print()

    # Progress
    batch_size = session['batch_size']
    processed = session['total_processed']
    success = session['total_success']
    failed = session['total_failed']
    timeouts = session['total_timeouts']

    print(f"Progress: {processed}/{batch_size} phases")
    print(f"  [OK] Success: {success} ({100*success/processed if processed else 0:.1f}%)")
    print(f"  [FAIL] Failed: {failed} ({100*failed/processed if processed else 0:.1f}%)")
    print(f"  [TIMEOUT] Timeouts: {timeouts} ({100*timeouts/processed if processed else 0:.1f}%)")
    print()

    # Telemetry metrics
    total_events = session.get('total_telemetry_events', 0)
    results = session.get('results', [])

    print("Telemetry Collection:")
    print(f"  Total Events: {total_events}")

    if results:
        # Compute yield stats
        yields = [r.get('telemetry_yield_per_minute', 0) or 0 for r in results]
        events_collected = [r.get('telemetry_events_collected', 0) or 0 for r in results]

        phases_with_events = sum(1 for e in events_collected if e > 0)
        print(f"  Phases with Events: {phases_with_events}/{len(results)} ({100*phases_with_events/len(results):.1f}%)")

        if yields:
            yields_sorted = sorted(yields)
            median_yield = yields_sorted[len(yields)//2]
            p90_idx = int(len(yields) * 0.9)
            p90_yield = yields_sorted[p90_idx] if p90_idx < len(yields) else yields_sorted[-1]
            max_yield = yields_sorted[-1]

            print(f"  Median Yield: {median_yield:.2f} events/min")
            print(f"  P90 Yield: {p90_yield:.2f} events/min")
            print(f"  Max Yield: {max_yield:.2f} events/min")

        # Compute overall yield (weighted by duration)
        total_duration = sum(r.get('subprocess_duration_seconds', 0) or 0 for r in results)
        if total_duration > 0:
            overall_yield = (total_events / total_duration) * 60
            print(f"  Overall Yield: {overall_yield:.2f} events/min")

    print()

    # Failure analysis
    fingerprints = session.get('fingerprint_counts', {})
    stopped_fingerprints = session.get('stopped_fingerprints', [])
    stopped_runs = session.get('stopped_runs', [])

    print("Failure Patterns:")
    print(f"  Unique Fingerprints: {len(fingerprints)}")
    print(f"  Stopped Fingerprints: {len(stopped_fingerprints)}")
    print(f"  Stopped Runs: {len(stopped_runs)}")

    if stopped_runs:
        print(f"    {', '.join(stopped_runs)}")

    print()

    # Top failure fingerprints
    if fingerprints:
        print("Top Failure Fingerprints:")
        sorted_fps = sorted(fingerprints.items(), key=lambda x: x[1], reverse=True)
        for fp, count in sorted_fps[:5]:
            status = "[STOPPED]" if fp in stopped_fingerprints else ""
            print(f"  {count}x {status} {fp[:100]}")

    print()

    # Results by run
    if results:
        print("Results by Run:")
        print("-" * 80)

        runs: Dict[str, List] = {}
        for r in results:
            run_id = r['run_id']
            if run_id not in runs:
                runs[run_id] = []
            runs[run_id].append(r)

        for run_id, run_results in runs.items():
            run_success = sum(1 for r in run_results if r['success'])
            run_timeouts = sum(1 for r in run_results if r.get('subprocess_returncode') in [-1, 143])
            run_events = sum(r.get('telemetry_events_collected', 0) or 0 for r in run_results)

            stopped = "[STOPPED]" if run_id in stopped_runs else ""
            print(f"  {run_id} {stopped}: {run_success}/{len(run_results)} success, {run_timeouts} timeouts, {run_events} events")

    print()

    # Recommendations
    if session.get('completed_at'):
        print("=" * 80)
        print("RECOMMENDATIONS")
        print("=" * 80)

        success_rate = success / processed if processed else 0
        timeout_rate = timeouts / processed if processed else 0

        if timeout_rate > 0.3:
            print("⚠️  HIGH TIMEOUT RATE (>30%)")
            print("   Consider: --phase-timeout-seconds 1200 (increase to 20 minutes)")
        elif timeout_rate < 0.1:
            print("✓ LOW TIMEOUT RATE (<10%)")
            print("   Consider: --phase-timeout-seconds 600 (reduce to 10 minutes for faster triage)")

        if results:
            avg_yield = total_events / len(results)
            if avg_yield < 1.0:
                print(f"⚠️  LOW TELEMETRY YIELD (<1 event/phase)")
                print("   - Phases may be failing before Builder execution")
                print("   - Check error messages for import/collection issues")
                print("   - Consider fixing systematic errors before draining more")
            elif avg_yield > 5.0:
                print(f"✓ GOOD TELEMETRY YIELD (>5 events/phase)")
                print("   - Phases are reaching Builder and generating samples")
                print("   - Continue draining with current settings")

        if len(stopped_runs) > len(runs) * 0.5:
            print("⚠️  MANY RUNS STOPPED (>50%)")
            print("   Consider: --max-fingerprint-repeats 5 (more lenient)")

        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze batch drain session JSON")
    parser.add_argument("session_id", nargs="?", help="Session ID (e.g., batch-drain-20251228-061426)")
    parser.add_argument("--latest", action="store_true", help="Analyze most recent session")
    args = parser.parse_args()

    if args.latest:
        session_path = find_latest_session()
        if not session_path:
            print("ERROR: No session files found in .autonomous_runs/batch_drain_sessions/", file=sys.stderr)
            return 1
        print(f"[Using latest session: {session_path.stem}]\n")
    elif args.session_id:
        session_path = find_session_file(args.session_id)
        if not session_path:
            print(f"ERROR: Session not found: {args.session_id}", file=sys.stderr)
            return 1
    else:
        print("ERROR: Provide session_id or use --latest", file=sys.stderr)
        parser.print_help()
        return 1

    analyze_session(session_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
