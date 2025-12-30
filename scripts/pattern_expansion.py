"""Pattern Expansion Script - BUILD-146 P11 Observability

Analyzes failures and phase6_metrics to identify uncaught error patterns
that should be added to deterministic mitigation.

Purpose:
- Reads error_logs and phase6_metrics tables
- Identifies failure patterns that weren't caught by failure hardening
- Outputs new pattern signatures with reproduction context
- Helps expand deterministic mitigation coverage over time

Usage:
    # Analyze all runs:
    python scripts/pattern_expansion.py

    # Analyze specific run:
    python scripts/pattern_expansion.py --run-id my-run-123

    # Output to JSON file:
    python scripts/pattern_expansion.py --output patterns.json

    # Set minimum occurrence threshold:
    python scripts/pattern_expansion.py --min-occurrences 3
"""

import os
import sys
import json
import argparse
import hashlib
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from collections import defaultdict

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


@dataclass
class UncaughtPattern:
    """An error pattern that wasn't caught by failure hardening."""

    pattern_signature: str  # Hash of error message pattern
    error_type: str  # Type of error (e.g., "import_error", "syntax_error")
    error_message_sample: str  # Representative error message
    occurrence_count: int  # Number of times this pattern appeared
    run_ids: List[str]  # Runs where this pattern appeared
    phase_ids: List[str]  # Phases where this pattern appeared

    # Reproduction context
    first_seen_at: str  # ISO timestamp
    last_seen_at: str  # ISO timestamp
    affected_models: List[str]  # Models that hit this error

    # Suggested mitigation
    suggested_pattern_id: str  # Proposed pattern ID for failure_patterns.py
    confidence: str  # "high" | "medium" | "low"
    notes: str  # Additional context for pattern implementation


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
        print("  python scripts/pattern_expansion.py\n", file=sys.stderr)
        print("  # PowerShell (SQLite dev/test):", file=sys.stderr)
        print("  $env:DATABASE_URL=\"sqlite:///autopack.db\"", file=sys.stderr)
        print("  python scripts/pattern_expansion.py\n", file=sys.stderr)
        sys.exit(1)
    return db_url


def normalize_error_message(error_msg: str) -> str:
    """Normalize error message to extract pattern signature.

    Removes specific file paths, line numbers, and variable names
    to identify the underlying error pattern.
    """
    import re

    # Remove file paths (both Unix and Windows)
    normalized = re.sub(r'[A-Za-z]:\\[^\s]+', '<PATH>', error_msg)
    normalized = re.sub(r'/[^\s]+\.py', '<PATH>', normalized)

    # Remove line numbers
    normalized = re.sub(r'line \d+', 'line <NUM>', normalized)
    normalized = re.sub(r':\d+:', ':<NUM>:', normalized)

    # Remove specific variable/module names in quotes
    normalized = re.sub(r"'[A-Za-z_][A-Za-z0-9_]*'", '<VAR>', normalized)
    normalized = re.sub(r'"[A-Za-z_][A-Za-z0-9_]*"', '<VAR>', normalized)

    # Remove hex addresses
    normalized = re.sub(r'0x[0-9a-fA-F]+', '0x<HEX>', normalized)

    return normalized


def classify_error_type(error_msg: str) -> str:
    """Classify error into a high-level type."""
    error_msg_lower = error_msg.lower()

    if "importerror" in error_msg_lower or "modulenotfounderror" in error_msg_lower:
        return "import_error"
    elif "syntaxerror" in error_msg_lower:
        return "syntax_error"
    elif "typeerror" in error_msg_lower:
        return "type_error"
    elif "attributeerror" in error_msg_lower:
        return "attribute_error"
    elif "nameerror" in error_msg_lower:
        return "name_error"
    elif "valueerror" in error_msg_lower:
        return "value_error"
    elif "keyerror" in error_msg_lower:
        return "key_error"
    elif "indentationerror" in error_msg_lower:
        return "indentation_error"
    elif "filenotfounderror" in error_msg_lower or "no such file" in error_msg_lower:
        return "file_not_found"
    elif "permission" in error_msg_lower or "access denied" in error_msg_lower:
        return "permission_error"
    else:
        return "unknown_error"


def compute_pattern_signature(normalized_msg: str) -> str:
    """Compute a hash signature for the normalized error pattern."""
    return hashlib.sha256(normalized_msg.encode()).hexdigest()[:16]


def analyze_uncaught_patterns(
    db: Session,
    run_id: Optional[str] = None,
    min_occurrences: int = 1
) -> List[UncaughtPattern]:
    """Analyze database to find uncaught error patterns.

    Args:
        db: Database session
        run_id: Optional run ID to filter by
        min_occurrences: Minimum number of occurrences to include

    Returns:
        List of UncaughtPattern objects
    """
    # Query 1: Find errors that weren't caught by failure hardening
    # (error_logs where corresponding phase6_metrics has failure_hardening_triggered = FALSE)

    query = text("""
        SELECT
            e.run_id,
            e.phase_id,
            e.error_message,
            e.error_type,
            e.created_at,
            p6.failure_pattern_detected
        FROM error_logs e
        LEFT JOIN phase6_metrics p6
            ON e.run_id = p6.run_id AND e.phase_id = p6.phase_id
        WHERE (p6.failure_hardening_triggered IS NULL OR p6.failure_hardening_triggered = 0)
            AND e.error_message IS NOT NULL
            AND e.error_message != ''
    """)

    params = {}
    if run_id:
        query = text(str(query) + " AND e.run_id = :run_id")
        params["run_id"] = run_id

    results = db.execute(query, params).fetchall()

    # Group by pattern signature
    pattern_groups = defaultdict(list)

    for row in results:
        run_id_val, phase_id, error_msg, error_type, created_at, pattern_detected = row

        # Normalize and compute signature
        normalized = normalize_error_message(error_msg)
        signature = compute_pattern_signature(normalized)

        pattern_groups[signature].append({
            "run_id": run_id_val,
            "phase_id": phase_id,
            "error_message": error_msg,
            "error_type": error_type,
            "created_at": created_at,
            "normalized": normalized,
        })

    # Convert to UncaughtPattern objects
    uncaught_patterns = []

    for signature, occurrences in pattern_groups.items():
        if len(occurrences) < min_occurrences:
            continue

        # Get representative sample
        sample_error = occurrences[0]["error_message"]
        normalized_msg = occurrences[0]["normalized"]

        # Extract metadata
        run_ids = list(set(o["run_id"] for o in occurrences))
        phase_ids = [o["phase_id"] for o in occurrences]

        timestamps = [o["created_at"] for o in occurrences if o["created_at"]]
        first_seen = min(timestamps).isoformat() if timestamps else "unknown"
        last_seen = max(timestamps).isoformat() if timestamps else "unknown"

        # Classify error type
        error_type_classified = classify_error_type(sample_error)

        # Determine confidence based on occurrence count
        if len(occurrences) >= 5:
            confidence = "high"
        elif len(occurrences) >= 3:
            confidence = "medium"
        else:
            confidence = "low"

        # Generate suggested pattern ID
        suggested_id = f"{error_type_classified}_{signature[:8]}"

        # Generate notes
        notes = f"Pattern appears {len(occurrences)} time(s) across {len(run_ids)} run(s). "
        notes += f"Normalized signature: {normalized_msg[:100]}..."

        pattern = UncaughtPattern(
            pattern_signature=signature,
            error_type=error_type_classified,
            error_message_sample=sample_error[:200],  # Truncate for readability
            occurrence_count=len(occurrences),
            run_ids=run_ids,
            phase_ids=phase_ids,
            first_seen_at=first_seen,
            last_seen_at=last_seen,
            affected_models=[],  # TODO: Extract from llm_usage_events if needed
            suggested_pattern_id=suggested_id,
            confidence=confidence,
            notes=notes,
        )

        uncaught_patterns.append(pattern)

    # Sort by occurrence count (descending)
    uncaught_patterns.sort(key=lambda p: p.occurrence_count, reverse=True)

    return uncaught_patterns


def print_pattern_report(patterns: List[UncaughtPattern]) -> None:
    """Print human-readable pattern report to stdout."""
    print("=" * 80)
    print("UNCAUGHT ERROR PATTERN REPORT")
    print("=" * 80)
    print(f"\nTotal uncaught patterns found: {len(patterns)}")
    print()

    if not patterns:
        print("✓ No uncaught patterns detected - failure hardening is 100% effective!")
        return

    for i, pattern in enumerate(patterns, 1):
        print(f"\n[{i}] Pattern: {pattern.suggested_pattern_id}")
        print(f"    Signature: {pattern.pattern_signature}")
        print(f"    Error Type: {pattern.error_type}")
        print(f"    Occurrences: {pattern.occurrence_count} (confidence: {pattern.confidence})")
        print(f"    Runs affected: {len(pattern.run_ids)}")
        print(f"    First seen: {pattern.first_seen_at}")
        print(f"    Last seen: {pattern.last_seen_at}")
        print(f"    Sample error: {pattern.error_message_sample}")
        print(f"    Notes: {pattern.notes}")
        print()

    print("=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print("1. Review patterns above for commonalities")
    print("2. Add high-confidence patterns to failure_patterns.py")
    print("3. Implement deterministic mitigations")
    print("4. Re-run pattern expansion to verify coverage")
    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze uncaught error patterns for failure hardening expansion"
    )
    parser.add_argument(
        "--run-id",
        type=str,
        help="Filter analysis to specific run ID"
    )
    parser.add_argument(
        "--min-occurrences",
        type=int,
        default=1,
        help="Minimum number of occurrences to include (default: 1)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output JSON file path (optional, defaults to stdout)"
    )

    args = parser.parse_args()

    # Get database connection
    db_url = get_database_url()
    engine = create_engine(db_url)

    print(f"Analyzing patterns from: {db_url}")
    if args.run_id:
        print(f"Filtering to run: {args.run_id}")
    print(f"Minimum occurrences: {args.min_occurrences}")
    print()

    # Analyze patterns
    with Session(engine) as session:
        patterns = analyze_uncaught_patterns(
            session,
            run_id=args.run_id,
            min_occurrences=args.min_occurrences
        )

    # Output results
    if args.output:
        # Write JSON to file
        output_data = {
            "meta": {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "run_id_filter": args.run_id,
                "min_occurrences": args.min_occurrences,
                "total_patterns": len(patterns),
            },
            "patterns": [asdict(p) for p in patterns]
        }

        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)

        print(f"✓ Wrote {len(patterns)} patterns to {args.output}")
        print()

    # Always print human-readable report to stdout
    print_pattern_report(patterns)


if __name__ == "__main__":
    main()
