"""A/B Test Analysis Script - BUILD-146 P12

Analyzes and persists A/B test results comparing control vs treatment runs.

Enforces STRICT validity checks:
- Control and treatment MUST have same git commit SHA
- Control and treatment MUST have same model mapping hash
- Warnings for phase count mismatch

Usage:
    # Compare two runs
    python scripts/ab_analysis.py \\
        --control-run telemetry-v5 \\
        --treatment-run telemetry-v6 \\
        --test-id v5-vs-v6

    # Specify who created the result
    python scripts/ab_analysis.py \\
        --control-run run-a \\
        --treatment-run run-b \\
        --test-id experiment-1 \\
        --created-by "user@example.com"

    # Dry run (don't persist to database)
    python scripts/ab_analysis.py \\
        --control-run run-a \\
        --treatment-run run-b \\
        --test-id test \\
        --dry-run
"""

import os
import sys
import argparse
from typing import Tuple, List, Optional
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Run, Phase, PhaseState, ABTestResult


def get_database_url() -> str:
    """Get DATABASE_URL from environment with helpful error."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("\n" + "="*80, file=sys.stderr)
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        print("="*80, file=sys.stderr)
        print("\nSet DATABASE_URL before running:\n", file=sys.stderr)
        print("  # PowerShell (Postgres production):", file=sys.stderr)
        print("  $env:DATABASE_URL=\"postgresql://autopack:autopack@localhost:5432/autopack\"", file=sys.stderr)
        print("  python scripts/ab_analysis.py --control-run v5 --treatment-run v6 --test-id test\n", file=sys.stderr)
        print("  # PowerShell (SQLite dev/test):", file=sys.stderr)
        print("  $env:DATABASE_URL=\"sqlite:///autopack.db\"", file=sys.stderr)
        print("  python scripts/ab_analysis.py --control-run v5 --treatment-run v6 --test-id test\n", file=sys.stderr)
        sys.exit(1)
    return db_url


def validate_pair(control: Run, treatment: Run) -> Tuple[bool, List[str]]:
    """Strict validation for A/B pair.

    BUILD-146 P12: Enforces strict validity - commit SHA and model hash MUST match.

    Args:
        control: Control run
        treatment: Treatment run

    Returns:
        (is_valid, error_list) - is_valid is False if ANY error is not a warning
    """
    errors = []

    # MUST have same commit SHA (STRICT requirement, not warning)
    control_sha = getattr(control, 'git_commit_sha', None)
    treatment_sha = getattr(treatment, 'git_commit_sha', None)

    if control_sha != treatment_sha:
        errors.append(f"ERROR: Commit SHA mismatch - control={control_sha}, treatment={treatment_sha}")

    # MUST have same model mapping hash (STRICT requirement, not warning)
    control_hash = getattr(control, 'model_mapping_hash', None)
    treatment_hash = getattr(treatment, 'model_mapping_hash', None)

    if control_hash != treatment_hash:
        errors.append(f"ERROR: Model hash mismatch - control={control_hash}, treatment={treatment_hash}")

    # SHOULD have same phase count (warning, not error)
    control_phases = len(control.phases) if hasattr(control, 'phases') else 0
    treatment_phases = len(treatment.phases) if hasattr(treatment, 'phases') else 0

    if control_phases != treatment_phases:
        errors.append(f"WARNING: Phase count mismatch - control={control_phases}, treatment={treatment_phases}")

    # Check for missing metadata
    if not control_sha:
        errors.append("ERROR: Control run missing git_commit_sha")
    if not treatment_sha:
        errors.append("ERROR: Treatment run missing git_commit_sha")
    if not control_hash:
        errors.append("WARNING: Control run missing model_mapping_hash")
    if not treatment_hash:
        errors.append("WARNING: Treatment run missing model_mapping_hash")

    # Only fail if there are non-WARNING errors
    has_strict_errors = any(e.startswith("ERROR:") for e in errors)
    is_valid = not has_strict_errors

    return is_valid, errors


def calculate_deltas(control: Run, treatment: Run, session) -> dict:
    """Calculate metric deltas between control and treatment.

    Args:
        control: Control run
        treatment: Treatment run
        session: Database session for queries

    Returns:
        Dictionary with metric deltas and aggregated stats
    """
    # Calculate token deltas
    control_tokens = control.tokens_used or 0
    treatment_tokens = treatment.tokens_used or 0
    token_delta = treatment_tokens - control_tokens

    # Calculate time deltas (if both runs have start/end times)
    control_time = None
    treatment_time = None
    time_delta_seconds = None

    if control.started_at and control.completed_at:
        control_time = (control.completed_at - control.started_at).total_seconds()

    if treatment.started_at and treatment.completed_at:
        treatment_time = (treatment.completed_at - treatment.started_at).total_seconds()

    if control_time is not None and treatment_time is not None:
        time_delta_seconds = treatment_time - control_time

    # Calculate phase success rates
    control_phases = session.query(Phase).filter(Phase.run_id == control.id).all()
    treatment_phases = session.query(Phase).filter(Phase.run_id == treatment.id).all()

    control_total = len(control_phases)
    control_complete = sum(1 for p in control_phases if p.state == PhaseState.COMPLETE)
    control_failed = sum(1 for p in control_phases if p.state == PhaseState.FAILED)

    treatment_total = len(treatment_phases)
    treatment_complete = sum(1 for p in treatment_phases if p.state == PhaseState.COMPLETE)
    treatment_failed = sum(1 for p in treatment_phases if p.state == PhaseState.FAILED)

    # Success rate = (complete / total) * 100
    control_success_rate = (control_complete / control_total * 100) if control_total > 0 else 0.0
    treatment_success_rate = (treatment_complete / treatment_total * 100) if treatment_total > 0 else 0.0
    success_rate_delta = treatment_success_rate - control_success_rate

    return {
        "token_delta": token_delta,
        "time_delta_seconds": time_delta_seconds,
        "success_rate_delta": success_rate_delta,
        "control_total_tokens": control_tokens,
        "control_phases_complete": control_complete,
        "control_phases_failed": control_failed,
        "control_total_phases": control_total,
        "treatment_total_tokens": treatment_tokens,
        "treatment_phases_complete": treatment_complete,
        "treatment_phases_failed": treatment_failed,
        "treatment_total_phases": treatment_total,
    }


def persist_result(
    test_id: str,
    control: Run,
    treatment: Run,
    session,
    created_by: Optional[str] = None,
    dry_run: bool = False
) -> ABTestResult:
    """Persist A/B result to database.

    Args:
        test_id: Unique identifier for this A/B test
        control: Control run
        treatment: Treatment run
        session: Database session
        created_by: Who created this result (optional)
        dry_run: If True, don't actually persist to database

    Returns:
        ABTestResult instance
    """
    is_valid, errors = validate_pair(control, treatment)
    deltas = calculate_deltas(control, treatment, session)

    # Get commit SHAs and model hashes (with fallbacks)
    control_sha = getattr(control, 'git_commit_sha', 'unknown')
    treatment_sha = getattr(treatment, 'git_commit_sha', 'unknown')
    control_hash = getattr(control, 'model_mapping_hash', 'unknown')
    treatment_hash = getattr(treatment, 'model_mapping_hash', 'unknown')

    result = ABTestResult(
        test_id=test_id,
        control_run_id=control.id,
        treatment_run_id=treatment.id,
        control_commit_sha=control_sha or 'unknown',
        treatment_commit_sha=treatment_sha or 'unknown',
        control_model_hash=control_hash or 'unknown',
        treatment_model_hash=treatment_hash or 'unknown',
        is_valid=is_valid,
        validity_errors=errors if errors else None,
        created_by=created_by or 'ab_analysis.py',
        **deltas
    )

    if not dry_run:
        session.add(result)
        session.commit()
        print(f"✅ A/B result persisted to database (ID: {result.id})")
    else:
        print("🔍 DRY RUN - Result NOT persisted to database")

    print(f"   Valid: {is_valid}")

    if errors:
        print()
        print("   Validation messages:")
        for e in errors:
            symbol = "⚠" if e.startswith("WARNING") else "❌"
            print(f"   {symbol} {e}")

    return result


def print_comparison_report(control: Run, treatment: Run, result: ABTestResult):
    """Print human-readable comparison report.

    Args:
        control: Control run
        treatment: Treatment run
        result: ABTestResult with calculated deltas
    """
    print()
    print("=" * 80)
    print("A/B TEST COMPARISON REPORT")
    print("=" * 80)
    print()

    print(f"Test ID: {result.test_id}")
    print(f"Valid Comparison: {'✅ YES' if result.is_valid else '❌ NO'}")
    print()

    print("RUNS:")
    print(f"  Control:   {result.control_run_id}")
    print(f"  Treatment: {result.treatment_run_id}")
    print()

    print("METADATA:")
    print(f"  Control Commit:   {result.control_commit_sha}")
    print(f"  Treatment Commit: {result.treatment_commit_sha}")
    print(f"  Control Model:    {result.control_model_hash}")
    print(f"  Treatment Model:  {result.treatment_model_hash}")
    print()

    print("TOKEN METRICS:")
    print(f"  Control tokens:   {result.control_total_tokens:,}")
    print(f"  Treatment tokens: {result.treatment_total_tokens:,}")
    print(f"  Delta:            {result.token_delta:+,} ({'+' if result.token_delta > 0 else ''}{(result.token_delta / result.control_total_tokens * 100):.1f}%)")
    print()

    print("PHASE METRICS:")
    print(f"  Control:   {result.control_phases_complete}/{result.control_total_phases} complete, {result.control_phases_failed} failed")
    print(f"  Treatment: {result.treatment_phases_complete}/{result.treatment_total_phases} complete, {result.treatment_phases_failed} failed")
    control_rate = (result.control_phases_complete / result.control_total_phases * 100) if result.control_total_phases > 0 else 0
    treatment_rate = (result.treatment_phases_complete / result.treatment_total_phases * 100) if result.treatment_total_phases > 0 else 0
    print(f"  Success rate delta: {result.success_rate_delta:+.1f}% (control: {control_rate:.1f}%, treatment: {treatment_rate:.1f}%)")
    print()

    if result.time_delta_seconds is not None:
        print("TIME METRICS:")
        print(f"  Time delta: {result.time_delta_seconds:+.1f} seconds")
        print()

    print("=" * 80)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze and persist A/B test results with strict validity checks"
    )
    parser.add_argument(
        "--control-run",
        type=str,
        required=True,
        help="Control run ID (baseline)"
    )
    parser.add_argument(
        "--treatment-run",
        type=str,
        required=True,
        help="Treatment run ID (experiment)"
    )
    parser.add_argument(
        "--test-id",
        type=str,
        required=True,
        help="Unique identifier for this A/B test (e.g., 'v5-vs-v6')"
    )
    parser.add_argument(
        "--created-by",
        type=str,
        help="Who created this result (optional, defaults to 'ab_analysis.py')"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't persist to database, just show results"
    )

    args = parser.parse_args()

    # Get database connection
    db_url = get_database_url()
    print(f"Analyzing A/B test: {args.test_id}")
    print(f"Database: {db_url}")
    print()

    # Query runs
    session = SessionLocal()

    try:
        control = session.query(Run).filter(Run.id == args.control_run).first()
        if not control:
            print(f"❌ Control run not found: {args.control_run}", file=sys.stderr)
            sys.exit(1)

        treatment = session.query(Run).filter(Run.id == args.treatment_run).first()
        if not treatment:
            print(f"❌ Treatment run not found: {args.treatment_run}", file=sys.stderr)
            sys.exit(1)

        print(f"✓ Found control run:   {control.id}")
        print(f"✓ Found treatment run: {treatment.id}")
        print()

        # Persist result
        result = persist_result(
            test_id=args.test_id,
            control=control,
            treatment=treatment,
            session=session,
            created_by=args.created_by,
            dry_run=args.dry_run
        )

        # Print report
        print_comparison_report(control, treatment, result)

        # Exit with appropriate code
        if not result.is_valid:
            print()
            print("❌ Comparison is INVALID - strict validity checks failed")
            print("   Only compare runs with same commit SHA and model hash")
            sys.exit(1)
        else:
            print()
            print("✅ Comparison is VALID")
            sys.exit(0)

    finally:
        session.close()


if __name__ == "__main__":
    main()
