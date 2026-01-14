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
        print("\n" + "=" * 80, file=sys.stderr)
        print("ERROR: DATABASE_URL environment variable not set", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print("\nSet DATABASE_URL before running:\n", file=sys.stderr)
        print("  # PowerShell (Postgres production):", file=sys.stderr)
        print(
            '  $env:DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"',
            file=sys.stderr,
        )
        print("  python scripts/pattern_expansion.py\n", file=sys.stderr)
        print("  # PowerShell (SQLite dev/test):", file=sys.stderr)
        print('  $env:DATABASE_URL="sqlite:///autopack.db"', file=sys.stderr)
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
    normalized = re.sub(r"[A-Za-z]:\\[^\s]+", "<PATH>", error_msg)
    normalized = re.sub(r"/[^\s]+\.py", "<PATH>", normalized)

    # Remove line numbers
    normalized = re.sub(r"line \d+", "line <NUM>", normalized)
    normalized = re.sub(r":\d+:", ":<NUM>:", normalized)

    # Remove specific variable/module names in quotes
    normalized = re.sub(r"'[A-Za-z_][A-Za-z0-9_]*'", "<VAR>", normalized)
    normalized = re.sub(r'"[A-Za-z_][A-Za-z0-9_]*"', "<VAR>", normalized)

    # Remove hex addresses
    normalized = re.sub(r"0x[0-9a-fA-F]+", "0x<HEX>", normalized)

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
    db: Session, run_id: Optional[str] = None, min_occurrences: int = 1
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

        pattern_groups[signature].append(
            {
                "run_id": run_id_val,
                "phase_id": phase_id,
                "error_message": error_msg,
                "error_type": error_type,
                "created_at": created_at,
                "normalized": normalized,
            }
        )

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


def generate_pattern_detector(pattern: UncaughtPattern, output_dir: str) -> str:
    """Generate Python detector stub for a pattern.

    BUILD-146 P12: Auto-generate detector/mitigation stubs.

    Args:
        pattern: UncaughtPattern to generate code for
        output_dir: Directory to write generated files

    Returns:
        Path to generated file
    """
    from pathlib import Path

    pattern_id = pattern.suggested_pattern_id
    keywords = extract_keywords(pattern.error_message_sample)
    timestamp = datetime.utcnow().isoformat() + "Z"

    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate Python file
    file_path = output_path / f"pattern_{pattern_id}.py"

    content = f'''"""Auto-generated pattern detector for: {pattern.error_type}

Pattern ID: {pattern_id}
Occurrences: {pattern.occurrence_count}
Confidence: {pattern.confidence}
Generated: {timestamp}
"""


def detect_{pattern_id}(error_message: str, context: dict) -> bool:
    """Detect if error matches pattern: {pattern.error_type}

    Args:
        error_message: Error string from exception
        context: Execution context (phase_id, builder_mode, etc)

    Returns:
        True if pattern detected

    Pattern keywords: {", ".join(keywords[:5])}
    """
    # TODO: Implement detection logic based on pattern analysis
    # Sample error:
    # {pattern.error_message_sample[:200]}
    #
    # Suggested approach:
    # 1. Check for key error indicators in error_message
    # 2. Validate context matches expected failure scenario
    # 3. Return True if confident match, False otherwise

    error_lower = error_message.lower()

    # Basic keyword matching (IMPLEMENT PROPER LOGIC)
    detected = False
    # for keyword in {keywords[:3]}:
    #     if keyword.lower() in error_lower:
    #         detected = True
    #         break

    return detected


def mitigate_{pattern_id}(phase_id: str, context: dict) -> dict:
    """Attempt to mitigate pattern: {pattern.error_type}

    Args:
        phase_id: Phase ID where pattern occurred
        context: Execution context

    Returns:
        Mitigation result with success status and actions taken

    Notes: {pattern.notes[:200]}
    """
    # TODO: Implement mitigation strategy
    # Suggested approach based on error type ({pattern.error_type}):
    #
    # - For import_error: Check dependencies, suggest pip install
    # - For syntax_error: Suggest syntax validation before execution
    # - For file_not_found: Check file existence, suggest path correction
    # - For permission_error: Suggest chmod/permissions fix
    #
    # Return format:
    # {{
    #     "success": bool,
    #     "actions_taken": [list of actions],
    #     "message": str,
    #     "retry_recommended": bool
    # }}

    return {{
        "success": False,
        "actions_taken": [],
        "message": f"Mitigation for {{pattern_id}} not yet implemented",
        "retry_recommended": False
    }}
'''

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return str(file_path)


def generate_pattern_test(pattern: UncaughtPattern, output_dir: str) -> str:
    """Generate pytest skeleton for a pattern.

    BUILD-146 P12: Auto-generate test stubs.

    Args:
        pattern: UncaughtPattern to generate tests for
        output_dir: Directory to write generated files

    Returns:
        Path to generated file
    """
    from pathlib import Path

    pattern_id = pattern.suggested_pattern_id
    sample_error = pattern.error_message_sample[:200].replace('"', '\\"')

    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate test file
    file_path = output_path / f"test_pattern_{pattern_id}.py"

    content = f'''"""Tests for pattern detector: {pattern.error_type}

Pattern ID: {pattern_id}
Generated: {datetime.utcnow().isoformat() + "Z"}
"""

import pytest
from autopack.patterns.pattern_{pattern_id} import detect_{pattern_id}, mitigate_{pattern_id}


def test_detect_{pattern_id}_positive():
    """Test detection with known positive case from real data."""
    # Sample from actual occurrence (run: {pattern.run_ids[0] if pattern.run_ids else "unknown"})
    error_msg = """{sample_error}"""
    context = {{
        "phase_id": "{pattern.phase_ids[0] if pattern.phase_ids else "test-phase"}",
        "builder_mode": "builder"
    }}

    # TODO: Uncomment when detector is implemented
    # assert detect_{pattern_id}(error_msg, context) is True


def test_detect_{pattern_id}_negative():
    """Test detection with known negative case."""
    error_msg = "Completely unrelated error message"
    context = {{"phase_id": "test-phase"}}

    assert detect_{pattern_id}(error_msg, context) is False


def test_detect_{pattern_id}_edge_cases():
    """Test edge cases for pattern detection."""
    # Empty error message
    assert detect_{pattern_id}("", {{}}) is False

    # None context
    assert detect_{pattern_id}("some error", {{}}) is False


def test_mitigate_{pattern_id}_returns_dict():
    """Test mitigation strategy returns proper format."""
    result = mitigate_{pattern_id}("test-phase", {{"builder_mode": "builder"}})

    assert isinstance(result, dict)
    assert "success" in result
    assert "actions_taken" in result
    assert "message" in result
    assert "retry_recommended" in result


def test_mitigate_{pattern_id}_not_implemented():
    """Verify mitigation is marked as not implemented until completed."""
    result = mitigate_{pattern_id}("test-phase", {{}})

    # Should return False until properly implemented
    assert result["success"] is False
    assert "not yet implemented" in result["message"].lower()


# TODO: Add more specific test cases based on pattern analysis
# - Test with variations of the error message
# - Test with different context configurations
# - Test integration with failure_hardening system
'''

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return str(file_path)


def generate_backlog_entry(pattern: UncaughtPattern, output_dir: str) -> str:
    """Generate backlog markdown entry for a pattern.

    BUILD-146 P12: Auto-generate backlog documentation.

    Args:
        pattern: UncaughtPattern to document
        output_dir: Directory to write generated files

    Returns:
        Path to generated file
    """
    from pathlib import Path

    pattern_id = pattern.suggested_pattern_id.upper()
    keywords = extract_keywords(pattern.error_message_sample)
    timestamp = datetime.utcnow().isoformat() + "Z"

    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate markdown file
    file_path = output_path / f"PATTERN_{pattern_id}.md"

    # Determine priority based on frequency
    if pattern.occurrence_count >= 10:
        priority = "HIGH"
    elif pattern.occurrence_count >= 5:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    content = f"""# Pattern {pattern_id}: {pattern.error_type.replace("_", " ").title()}

**Status**: TODO
**Priority**: {priority}
**Occurrences**: {pattern.occurrence_count} times in dataset
**Confidence**: {pattern.confidence}
**Generated**: {timestamp}

## Pattern Description

This error pattern was automatically discovered from telemetry data. It represents
a failure mode that was NOT caught by existing failure hardening mechanisms.

**Error Type**: {pattern.error_type}
**Pattern Signature**: {pattern.pattern_signature}

**Affected Runs**: {len(pattern.run_ids)}
- {chr(10).join(f"  - {rid}" for rid in pattern.run_ids[:5])}
{"  - ..." if len(pattern.run_ids) > 5 else ""}

**Affected Phases**: {len(pattern.phase_ids)}
- {chr(10).join(f"  - {pid}" for pid in pattern.phase_ids[:5])}
{"  - ..." if len(pattern.phase_ids) > 5 else ""}

**First Seen**: {pattern.first_seen_at}
**Last Seen**: {pattern.last_seen_at}

## Sample Errors

```
{pattern.error_message_sample}
```

## Detection Strategy

**Keywords**: {", ".join(keywords[:10])}

**Suggested Detection Logic**:
1. Check for presence of key error indicators
2. Validate error type matches pattern ({pattern.error_type})
3. Consider context (phase type, builder mode, etc.)

**Regex Pattern** (suggested):
```python
import re
# TODO: Refine based on actual error variations
pattern = re.compile(r'{keywords[0] if keywords else ".*"}', re.IGNORECASE)
```

## Mitigation Ideas

Based on error type `{pattern.error_type}`, consider:

{"- **Import Error**: Verify dependencies are installed, suggest `pip install` for missing packages" if pattern.error_type == "import_error" else ""}
{"- **Syntax Error**: Add syntax validation step before code execution" if pattern.error_type == "syntax_error" else ""}
{"- **File Not Found**: Check file paths exist before accessing, provide helpful error messages" if pattern.error_type == "file_not_found" else ""}
{"- **Permission Error**: Check file permissions, suggest chmod commands or alternate paths" if pattern.error_type == "permission_error" else ""}
{"- **Type Error**: Add type validation, consider using type hints and mypy" if pattern.error_type == "type_error" else ""}

**Custom Notes**: {pattern.notes}

## Implementation Checklist

- [ ] Review sample errors and identify common root cause
- [ ] Implement detector in `src/autopack/patterns/pattern_{pattern_id.lower()}.py`
- [ ] Add comprehensive tests in `tests/patterns/test_pattern_{pattern_id.lower()}.py`
- [ ] Integrate detector with `autonomous_executor.py` error handling
- [ ] Add telemetry tracking for pattern detection hits
- [ ] Update dashboard to show pattern statistics
- [ ] Document mitigation strategy in runbook
- [ ] Test mitigation in controlled environment
- [ ] Deploy to staging and monitor effectiveness
- [ ] Update this backlog entry with results

## Success Criteria

- [ ] Pattern detector achieves > 90% true positive rate
- [ ] Mitigation successfully resolves error in > 70% of cases
- [ ] No false positives detected in production
- [ ] Pattern occurrence count decreases after mitigation deployed
- [ ] Documentation updated with lessons learned

## Related Patterns

<!-- Link to related patterns here -->

## Notes

{pattern.notes}

---

**Auto-generated by pattern_expansion.py** | Last updated: {timestamp}
"""

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return str(file_path)


def extract_keywords(error_message: str, max_keywords: int = 10) -> List[str]:
    """Extract meaningful keywords from error message.

    Args:
        error_message: Error message to extract keywords from
        max_keywords: Maximum number of keywords to return

    Returns:
        List of keywords
    """
    import re
    from collections import Counter

    # Remove common stop words
    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "is",
        "was",
        "are",
        "were",
        "been",
        "be",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "should",
        "could",
        "may",
        "might",
        "can",
        "this",
        "that",
        "these",
        "those",
    }

    # Extract words (alphanumeric + underscores)
    words = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b", error_message.lower())

    # Filter stop words and count occurrences
    filtered_words = [w for w in words if w not in stop_words]
    word_counts = Counter(filtered_words)

    # Return most common keywords
    return [word for word, count in word_counts.most_common(max_keywords)]


def create_pattern_registry(output_dir: str) -> str:
    """Create or update pattern registry __init__.py

    BUILD-146 P12: Pattern registry for auto-importing detectors.

    Args:
        output_dir: Directory containing pattern modules

    Returns:
        Path to registry file
    """
    from pathlib import Path

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    registry_file = output_path / "__init__.py"

    content = '''"""Pattern detector registry.

BUILD-146 P12: Auto-generated registry for failure pattern detectors.

Usage:
    from autopack.patterns import PATTERN_DETECTORS, PATTERN_MITIGATORS

    # Detect pattern
    for pattern_id, detector in PATTERN_DETECTORS.items():
        if detector(error_message, context):
            # Pattern detected, try mitigation
            result = PATTERN_MITIGATORS[pattern_id](phase_id, context)
            if result["success"]:
                # Mitigation successful
                break
"""

from typing import Dict, Callable

# Pattern detector functions (signature: (error_message: str, context: dict) -> bool)
PATTERN_DETECTORS: Dict[str, Callable] = {}

# Pattern mitigation functions (signature: (phase_id: str, context: dict) -> dict)
PATTERN_MITIGATORS: Dict[str, Callable] = {}


# TODO: Auto-register patterns from generated modules
# This will be populated by the pattern_expansion.py script
# Example:
# from .pattern_import_error import detect_import_error, mitigate_import_error
# PATTERN_DETECTORS["import_error"] = detect_import_error
# PATTERN_MITIGATORS["import_error"] = mitigate_import_error
'''

    with open(registry_file, "w", encoding="utf-8") as f:
        f.write(content)

    return str(registry_file)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze uncaught error patterns for failure hardening expansion"
    )
    parser.add_argument("--run-id", type=str, help="Filter analysis to specific run ID")
    parser.add_argument(
        "--min-occurrences",
        type=int,
        default=1,
        help="Minimum number of occurrences to include (default: 1)",
    )
    parser.add_argument(
        "--output", type=str, help="Output JSON file path (optional, defaults to stdout)"
    )
    parser.add_argument(
        "--generate-code",
        action="store_true",
        help="Generate Python detector stubs, tests, and backlog entries (BUILD-146 P12)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="src/autopack/patterns",
        help="Directory for generated pattern files (default: src/autopack/patterns)",
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
            session, run_id=args.run_id, min_occurrences=args.min_occurrences
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
            "patterns": [asdict(p) for p in patterns],
        }

        with open(args.output, "w") as f:
            json.dump(output_data, f, indent=2)

        print(f"✓ Wrote {len(patterns)} patterns to {args.output}")
        print()

    # BUILD-146 P12: Code generation
    if args.generate_code and patterns:
        print("=" * 80)
        print("GENERATING CODE STUBS (BUILD-146 P12)")
        print("=" * 80)
        print()

        # Limit to top 5 patterns by frequency (as per spec)
        top_patterns = patterns[:5]

        print(f"Generating code for top {len(top_patterns)} patterns...")
        print()

        # Create pattern registry first
        registry_path = create_pattern_registry(args.output_dir)
        print(f"✓ Created pattern registry: {registry_path}")

        # Create directories for tests and backlog
        from pathlib import Path

        test_dir = Path("tests/patterns")
        backlog_dir = Path("docs/backlog")

        generated_files = []

        for i, pattern in enumerate(top_patterns, 1):
            print(
                f"\n[{i}/{len(top_patterns)}] Generating files for pattern: {pattern.suggested_pattern_id}"
            )

            # Generate detector stub
            detector_path = generate_pattern_detector(pattern, args.output_dir)
            print(f"  ✓ Detector: {detector_path}")
            generated_files.append(detector_path)

            # Generate test file
            test_path = generate_pattern_test(pattern, str(test_dir))
            print(f"  ✓ Test: {test_path}")
            generated_files.append(test_path)

            # Generate backlog entry
            backlog_path = generate_backlog_entry(pattern, str(backlog_dir))
            print(f"  ✓ Backlog: {backlog_path}")
            generated_files.append(backlog_path)

        print()
        print("=" * 80)
        print(f"CODE GENERATION COMPLETE - {len(generated_files)} files created")
        print("=" * 80)
        print()
        print("Next steps:")
        print("1. Review generated detector stubs in:", args.output_dir)
        print("2. Implement TODO sections in detector logic")
        print("3. Run tests to verify syntax: pytest", str(test_dir))
        print("4. Integrate detectors with autonomous_executor.py")
        print("5. Update backlog entries in:", str(backlog_dir))
        print()

    # Always print human-readable report to stdout
    print_pattern_report(patterns)


if __name__ == "__main__":
    main()
