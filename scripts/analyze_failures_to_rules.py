#!/usr/bin/env python3
"""
Analyze failure artifacts/telemetry and propose deterministic mitigation rules.

Reads error artifacts and telemetry to identify recurring failure patterns,
then proposes rules for LEARNED_RULES.json to guide future runs.

Design (Track 2 from implementation plan):
- Guidance-only initially (no runtime enforcement)
- Normalize error signatures (strip paths/timestamps)
- Frequency-rank top failures
- Emit proposed rules with confidence levels

Usage:
    # Analyze last 30 days, show top 25
    python scripts/analyze_failures_to_rules.py --since-days 30 --max 25

    # Execute to append rules to docs/LEARNED_RULES.json
    python scripts/analyze_failures_to_rules.py --execute

    # Custom error directory
    python scripts/analyze_failures_to_rules.py --error-dir .autonomous_runs --execute
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set


def normalize_error_message(message: str) -> str:
    """
    Normalize error message by removing variable components.

    Removes:
    - File paths (e.g., C:\\Users\\... → <path>)
    - Line numbers (e.g., line 123 → line <N>)
    - Timestamps
    - PIDs
    - Memory addresses

    Args:
        message: Raw error message

    Returns:
        Normalized error signature
    """
    # Remove Windows paths
    normalized = re.sub(r'[A-Za-z]:\\[^\s]+', '<path>', message)

    # Remove Unix paths
    normalized = re.sub(r'/[^\s]+/[^\s]+', '<path>', normalized)

    # Remove line numbers
    normalized = re.sub(r'line \d+', 'line <N>', normalized)
    normalized = re.sub(r':\d+:', ':<N>:', normalized)

    # Remove timestamps
    normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', '<timestamp>', normalized)

    # Remove PIDs
    normalized = re.sub(r'PID \d+', 'PID <N>', normalized)
    normalized = re.sub(r'pid=\d+', 'pid=<N>', normalized)

    # Remove memory addresses
    normalized = re.sub(r'0x[0-9a-fA-F]+', '0x<addr>', normalized)

    # Remove numbers in brackets/parens that look like counts
    normalized = re.sub(r'\(\d+\)', '(<N>)', normalized)
    normalized = re.sub(r'\[\d+\]', '[<N>]', normalized)

    return normalized.strip()


def extract_error_type(message: str) -> Optional[str]:
    """
    Extract primary error type from message.

    Looks for:
    - Exception class names (e.g., PermissionError, FileNotFoundError)
    - HTTP status codes (e.g., 404, 500)
    - Common error patterns

    Args:
        message: Error message

    Returns:
        Error type or None
    """
    # Python exceptions
    match = re.search(r'(\w+Error|\w+Exception)', message)
    if match:
        return match.group(1)

    # HTTP status codes
    match = re.search(r'HTTP (\d{3})', message)
    if match:
        return f"HTTP_{match.group(1)}"

    # Common patterns
    if 'timeout' in message.lower():
        return 'TimeoutError'
    if 'connection' in message.lower():
        return 'ConnectionError'
    if 'permission' in message.lower():
        return 'PermissionError'

    return None


def signature_hash(signature: str) -> str:
    """Generate stable hash for error signature."""
    return hashlib.sha256(signature.encode('utf-8')).hexdigest()[:16]


def scan_error_artifacts(
    error_dir: Path,
    since_date: Optional[datetime] = None
) -> List[Dict]:
    """
    Scan .autonomous_runs/**/errors/*.json for failures.

    Args:
        error_dir: Root directory to scan for error artifacts
        since_date: Only include errors after this date

    Returns:
        List of error records
    """
    errors = []

    # Find all error JSON files
    error_files = list(error_dir.rglob('errors/*.json'))

    for error_file in error_files:
        try:
            with open(error_file, 'r', encoding='utf-8') as f:
                error_data = json.load(f)

            # Extract timestamp if available
            timestamp_str = error_data.get('timestamp') or error_data.get('created_at')
            if timestamp_str and since_date:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    if timestamp < since_date:
                        continue
                except Exception:
                    pass  # Include if timestamp parsing fails

            # Extract error message
            message = error_data.get('error') or error_data.get('message') or str(error_data)

            errors.append({
                'source_file': str(error_file),
                'message': message,
                'timestamp': timestamp_str,
                'run_id': error_file.parent.parent.name if error_file.parent.parent else None,
                'raw_data': error_data
            })

        except Exception as e:
            print(f"⚠️  Failed to parse {error_file}: {e}", file=sys.stderr)

    return errors


def group_by_signature(errors: List[Dict]) -> Dict[str, List[Dict]]:
    """
    Group errors by normalized signature.

    Args:
        errors: List of error records

    Returns:
        Dict mapping signature → list of occurrences
    """
    grouped = defaultdict(list)

    for error in errors:
        message = error['message']
        normalized = normalize_error_message(message)
        error_type = extract_error_type(message)

        # Create signature
        if error_type:
            signature = f"{error_type}: {normalized}"
        else:
            signature = normalized

        error['normalized_signature'] = signature
        error['error_type'] = error_type
        grouped[signature].append(error)

    return dict(grouped)


def propose_rule(
    signature: str,
    occurrences: List[Dict],
    confidence: str = "low"
) -> Dict:
    """
    Propose a learned rule for this error signature.

    Args:
        signature: Normalized error signature
        occurrences: List of error occurrences
        confidence: Rule confidence (low/medium/high)

    Returns:
        Rule dictionary
    """
    error_type = occurrences[0].get('error_type', 'UnknownError')

    # Infer recommendation based on error type
    recommendation = "Log warning and continue"
    scope = "general"

    if error_type == 'PermissionError':
        recommendation = "Skip file/directory and log warning; do not retry"
        scope = "tidy"
    elif error_type == 'FileNotFoundError':
        recommendation = "Skip missing file; verify upstream source exists"
        scope = "tidy"
    elif error_type in ['TimeoutError', 'ConnectionError']:
        recommendation = "Retry with exponential backoff (max 3 attempts)"
        scope = "api"
    elif 'HTTP_429' in error_type:
        recommendation = "Respect rate limit; wait and retry after delay"
        scope = "api"
    elif 'HTTP_5' in error_type:
        recommendation = "Retry with exponential backoff; log for investigation"
        scope = "api"

    # Calculate confidence based on frequency
    if len(occurrences) >= 10:
        confidence = "high"
    elif len(occurrences) >= 5:
        confidence = "medium"
    else:
        confidence = "low"

    # Extract evidence (run IDs)
    evidence = list(set(
        occ.get('run_id') for occ in occurrences
        if occ.get('run_id')
    ))[:10]  # Limit to 10 examples

    return {
        "id": f"rule_{signature_hash(signature)}",
        "created_at": datetime.utcnow().isoformat() + 'Z',
        "signature": signature,
        "recommendation": recommendation,
        "confidence": confidence,
        "evidence": evidence,
        "frequency": len(occurrences),
        "scope": scope,
        "enforcement": "guidance"  # Always guidance initially
    }


def load_existing_rules(rules_path: Path) -> Dict:
    """Load existing LEARNED_RULES.json."""
    if not rules_path.exists():
        return {"rules": [], "metadata": {"version": "1.0"}}

    try:
        with open(rules_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Failed to load existing rules: {e}", file=sys.stderr)
        return {"rules": [], "metadata": {"version": "1.0"}}


def append_rules(
    rules_path: Path,
    new_rules: List[Dict],
    dry_run: bool = True
) -> None:
    """
    Append new rules to LEARNED_RULES.json (idempotent by signature).

    Args:
        rules_path: Path to LEARNED_RULES.json
        new_rules: List of new rules to append
        dry_run: If True, don't actually write
    """
    existing_data = load_existing_rules(rules_path)
    existing_rules = existing_data.get('rules', [])

    # Build set of existing signatures
    existing_signatures = {
        rule['signature'] for rule in existing_rules
    }

    # Filter new rules (only add if signature not present)
    rules_to_add = [
        rule for rule in new_rules
        if rule['signature'] not in existing_signatures
    ]

    if not rules_to_add:
        print("ℹ️  No new rules to add (all signatures already present)")
        return

    # Append new rules
    existing_rules.extend(rules_to_add)
    existing_data['rules'] = existing_rules
    existing_data['metadata']['last_updated'] = datetime.utcnow().isoformat() + 'Z'

    if dry_run:
        print(f"\n[DRY-RUN] Would add {len(rules_to_add)} new rule(s) to {rules_path}")
        for rule in rules_to_add[:5]:  # Show first 5
            print(f"  - {rule['signature'][:80]}... (frequency: {rule['frequency']})")
        if len(rules_to_add) > 5:
            print(f"  ... and {len(rules_to_add) - 5} more")
    else:
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        with open(rules_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Added {len(rules_to_add)} new rule(s) to {rules_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze failures and propose learned rules"
    )
    parser.add_argument(
        "--error-dir",
        type=Path,
        default=Path(".autonomous_runs"),
        help="Root directory to scan for error artifacts (default: .autonomous_runs)"
    )
    parser.add_argument(
        "--since-days",
        type=int,
        default=30,
        help="Only include errors from last N days (default: 30)"
    )
    parser.add_argument(
        "--max",
        type=int,
        default=25,
        help="Max number of top failures to report (default: 25)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Append rules to docs/LEARNED_RULES.json (default: dry-run)"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Repository root (default: autodetect)"
    )
    parser.add_argument(
        "--output-report",
        type=Path,
        help="Optional: Export report to markdown file"
    )

    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    error_dir = args.error_dir if args.error_dir.is_absolute() else repo_root / args.error_dir
    rules_path = repo_root / "docs" / "LEARNED_ERROR_MITIGATIONS.json"

    print("=" * 70)
    print("FAILURE ANALYSIS → LEARNED RULES")
    print("=" * 70)
    print(f"Repository root: {repo_root}")
    print(f"Error directory: {error_dir}")
    print(f"Since: last {args.since_days} days")
    print(f"Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")
    print("=" * 70)
    print()

    # Calculate cutoff date
    since_date = datetime.now() - timedelta(days=args.since_days)

    # Scan error artifacts
    print(f"Scanning error artifacts since {since_date.strftime('%Y-%m-%d')}...")
    errors = scan_error_artifacts(error_dir, since_date)
    print(f"Found {len(errors)} error(s)")
    print()

    if not errors:
        print("✅ No errors found. Nothing to analyze.")
        return 0

    # Group by signature
    print("Grouping by normalized signature...")
    grouped = group_by_signature(errors)
    print(f"Found {len(grouped)} unique error signature(s)")
    print()

    # Sort by frequency
    sorted_signatures = sorted(
        grouped.items(),
        key=lambda x: len(x[1]),
        reverse=True
    )[:args.max]

    # Generate proposed rules
    proposed_rules = []
    print("=" * 70)
    print(f"TOP {min(args.max, len(sorted_signatures))} FAILURE PATTERNS")
    print("=" * 70)

    for idx, (signature, occurrences) in enumerate(sorted_signatures, 1):
        rule = propose_rule(signature, occurrences)
        proposed_rules.append(rule)

        print(f"\n{idx}. {rule['error_type'] or 'UnknownError'} (frequency: {rule['frequency']}, confidence: {rule['confidence']})")
        print(f"   Signature: {signature[:100]}...")
        print(f"   Recommendation: {rule['recommendation']}")
        print(f"   Scope: {rule['scope']}")

    print()

    # Append to LEARNED_RULES.json
    if proposed_rules:
        append_rules(rules_path, proposed_rules, dry_run=not args.execute)

    # Optional: Export report
    if args.output_report:
        report_path = args.output_report if args.output_report.is_absolute() else repo_root / args.output_report
        report_lines = [
            "# Top Failure Patterns Analysis",
            "",
            f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Period**: Last {args.since_days} days",
            f"**Total errors**: {len(errors)}",
            f"**Unique signatures**: {len(grouped)}",
            "",
            "## Top Failures",
            ""
        ]

        for idx, (signature, occurrences) in enumerate(sorted_signatures, 1):
            rule = propose_rule(signature, occurrences)
            report_lines.append(f"### {idx}. {rule['error_type'] or 'UnknownError'}")
            report_lines.append("")
            report_lines.append(f"- **Frequency**: {rule['frequency']}")
            report_lines.append(f"- **Confidence**: {rule['confidence']}")
            report_lines.append(f"- **Scope**: {rule['scope']}")
            report_lines.append(f"- **Recommendation**: {rule['recommendation']}")
            report_lines.append(f"- **Signature**: `{signature[:150]}...`")
            report_lines.append("")

        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text('\n'.join(report_lines), encoding='utf-8')
        print(f"📄 Report exported to: {report_path}")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total errors analyzed: {len(errors)}")
    print(f"Unique signatures: {len(grouped)}")
    print(f"Proposed rules: {len(proposed_rules)}")

    if not args.execute:
        print()
        print("ℹ️  This was a dry-run. Use --execute to append rules.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
