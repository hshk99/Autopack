"""
Contract tests for run layout path patterns in operator-facing docs.

BUILD-195: Prevents re-introduction of legacy run path patterns in documentation.

Canonical layout: .autonomous_runs/<project>/runs/<family>/<run_id>/...
Legacy patterns:  .autonomous_runs/<run_id>/...  (missing project/family hierarchy)
                  .autonomous_runs/<project>/runs/<run-id>/...  (hyphen instead of underscore)

Only operator-facing "living docs" are scanned. Historical ledgers
(BUILD_HISTORY.md, DEBUG_LOG.md, etc.) are excluded.
"""

import re
from pathlib import Path


# Operator-facing living docs that should use canonical run layout.
# These docs are instructional and should always show the current path structure.
OPERATOR_FACING_DOCS = [
    "docs/QUICKSTART.md",
    "docs/CONTRIBUTING.md",
    "docs/ERROR_HANDLING.md",
    "docs/TROUBLESHOOTING.md",
    "docs/PHASE_LIFECYCLE.md",
    "docs/ARCHITECTURE.md",
    # Add new operator-facing docs here as they are created
]

# Patterns that indicate legacy run layout (drift).
# These patterns are forbidden in operator-facing docs.
LEGACY_PATTERNS = [
    # Missing <family>/ segment: .autonomous_runs/<project>/runs/<run_id>/ directly
    # This pattern detects when the family segment is missing.
    # Canonical: .autonomous_runs/<project>/runs/<family>/<run_id>/
    # Legacy: .autonomous_runs/<project>/runs/<run_id>/ (family missing)
    (
        r"\.autonomous_runs/[^/]+/runs/<run[-_]?id>",
        "Legacy run layout: missing <family>/ segment (should be: .autonomous_runs/<project>/runs/<family>/<run_id>/)",
    ),
    # Hyphenated <run-id> instead of underscored <run_id>
    (
        r"\.autonomous_runs/[^/]+/runs/[^/]+/<run-id>",
        "Legacy run layout: use <run_id> (underscore) not <run-id> (hyphen)",
    ),
    # Flat .autonomous_runs/<run_id>/ without project hierarchy
    (
        r"\.autonomous_runs/<run[-_]?id>",
        "Legacy run layout: missing project/family hierarchy (should be: .autonomous_runs/<project>/runs/<family>/<run_id>/)",
    ),
    # Brace-delimited variants
    (
        r"\.autonomous_runs/\{run[-_]?id\}",
        "Legacy run layout: missing project/family hierarchy (should be: .autonomous_runs/<project>/runs/<family>/<run_id>/)",
    ),
    (
        r"\.autonomous_runs/[^/]+/runs/\{run[-_]?id\}",
        "Legacy run layout: missing <family>/ segment",
    ),
    # Shell variable variants
    (
        r"\.autonomous_runs/\$\{?run[-_]?id\}?",
        "Legacy run layout: missing project/family hierarchy",
    ),
    (
        r"\.autonomous_runs/[^/]+/runs/\$\{?run[-_]?id\}?",
        "Legacy run layout: missing <family>/ segment",
    ),
]


def _check_file_for_legacy_patterns(file_path: Path) -> list[tuple[int, str, str]]:
    """Check a single file for legacy run layout patterns.

    Returns:
        List of (line_number, pattern_description, line_content) tuples
    """
    violations = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                for pattern, description in LEGACY_PATTERNS:
                    if re.search(pattern, line, re.IGNORECASE):
                        violations.append((line_num, description, line.strip()))
    except FileNotFoundError:
        # File doesn't exist - not a violation, just skip
        pass
    except Exception as e:
        # Other errors - skip but don't fail the test
        print(f"WARNING: Could not read {file_path}: {e}")

    return violations


def test_operator_docs_use_canonical_run_layout():
    """Operator-facing docs must use canonical run layout with <family>/<run_id>."""
    repo_root = Path(__file__).parents[2]

    all_violations = []

    for doc_path in OPERATOR_FACING_DOCS:
        full_path = repo_root / doc_path
        if not full_path.exists():
            # Skip docs that don't exist (might be optional)
            continue

        violations = _check_file_for_legacy_patterns(full_path)
        if violations:
            for line_num, description, line_content in violations:
                all_violations.append(f"{doc_path}:{line_num}: {description}\n    > {line_content}")

    assert not all_violations, (
        f"Found {len(all_violations)} legacy run layout pattern(s) in operator-facing docs:\n\n"
        + "\n\n".join(all_violations)
        + "\n\nCanonical layout: .autonomous_runs/<project>/runs/<family>/<run_id>/"
    )


def test_no_flat_run_paths_in_living_docs():
    """Living docs must not use flat .autonomous_runs/<run_id>/ paths."""
    repo_root = Path(__file__).parents[2]

    # Broader set of living docs (non-historical)
    living_docs = list((repo_root / "docs").glob("*.md"))

    # Exclude historical ledgers, migration docs, and implementation plans
    excluded = {
        # Historical ledgers (append-only, may contain legacy patterns)
        "BUILD_HISTORY.md",
        "DEBUG_LOG.md",
        "CHANGELOG.md",
        "ARCHITECTURE_DECISIONS.md",
        # Gap analysis and improvement tracking
        "IMPROVEMENTS_GAP_ANALYSIS.md",
        "IMPROVEMENTS_AUDIT.md",
        # Migration and consolidation docs (historical context)
        "CANONICAL_API_CONSOLIDATION_PLAN.md",
        "API_CONSOLIDATION_COMPLETION_SUMMARY.md",
        # Implementation plans (historical, describe evolution)
        "IMPLEMENTATION_PLAN_INTENTION_ANCHOR_CONSOLIDATION.md",
        "IMPLEMENTATION_PLAN_INTENTION_FIRST_AUTONOMY_LOOP_REMAINING_IMPROVEMENTS.md",
        "INTENTION_ANCHOR_COMPLETION_SUMMARY.md",
        # Cursor prompts discuss patterns, not prescribe them
        "CURSOR_PROMPT_IMPLEMENT_IMPROVEMENTS_GAP_ANALYSIS.md",
        "CURSOR_PROMPT_EXECUTE_IMPLEMENT_IMPROVEMENTS_GAP_ANALYSIS.md",
        "CURSOR_PROMPT_OTHER_CURSOR_IMPLEMENT_IMPROVEMENTS_GAP_ANALYSIS_FULL.md",
        "CURSOR_PROMPT_IMPLEMENT_P0_BROKEN.md",
        "CURSOR_PROMPT_RUN_AUTOPACK.md",
    }

    flat_pattern = r"\.autonomous_runs/<run[-_]?id>"
    violations = []

    for doc_path in living_docs:
        if doc_path.name in excluded:
            continue

        try:
            content = doc_path.read_text(encoding="utf-8")
            for line_num, line in enumerate(content.splitlines(), 1):
                if re.search(flat_pattern, line, re.IGNORECASE):
                    violations.append(f"{doc_path.name}:{line_num}: {line.strip()}")
        except Exception:
            continue

    assert not violations, (
        "Found flat run paths in living docs (should be .autonomous_runs/<project>/runs/<family>/<run_id>/):\n"
        + "\n".join(violations)
    )
