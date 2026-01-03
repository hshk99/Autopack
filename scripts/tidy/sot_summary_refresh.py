#!/usr/bin/env python3
"""
SOT Summary Refresh - Docs-Only SOT Summary Refresh

BUILD-160: Standalone script to refresh SOT summary counts in docs/*.md files
without running full tidy workspace consolidation.

This script:
1. Scans docs/BUILD_HISTORY.md, DEBUG_LOG.md, ARCHITECTURE_DECISIONS.md
2. Counts actual entries (derives from content, not META headers)
3. Updates summary sections with canonical counts
4. Uses atomic writes to prevent partial updates

Usage:
    # Dry run - preview changes
    python scripts/tidy/sot_summary_refresh.py

    # Execute changes
    python scripts/tidy/sot_summary_refresh.py --execute

    # Specific project
    python scripts/tidy/sot_summary_refresh.py --project autopack

Category: MANUAL ONLY
Triggers: Explicit user command, tidy --quick mode
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

# Ensure sibling imports work
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

from io_utils import atomic_write


# ---------------------------------------------------------------------------
# Entry Counting Logic - Dual-Source Strategy (META + Derived)
# ---------------------------------------------------------------------------

def parse_meta_count(content: str, key: str) -> int | None:
    """
    Parse count from META header (e.g., "Total_Builds: 169").

    Args:
        content: File content
        key: META key to search for (e.g., "Builds", "Decisions", "Issues")

    Returns:
        Count from META header, or None if not found
    """
    pattern = rf'^Total_{key}:\s*(\d+)\s*$'
    match = re.search(pattern, content, re.MULTILINE)
    return int(match.group(1)) if match else None


def derive_build_count(content: str) -> int:
    """
    Derive BUILD-### count from content (index table rows).

    Counts total build entries in the index table. Note that some BUILD IDs
    may appear multiple times (representing different phases/milestones), and
    we count each entry separately as a distinct deliverable.

    Falls back to unique BUILD-### ID count if no index table found.
    """
    # Count index table rows: | YYYY-MM-DD | BUILD-### | ...
    table_rows = re.findall(r'^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*BUILD-\d+', content, re.MULTILINE)

    if table_rows:
        return len(table_rows)

    # Fallback: count unique BUILD IDs if no table found
    ids = set(re.findall(r'\bBUILD-\d+\b', content))
    return len(ids)


def derive_decision_count(content: str) -> int:
    """
    Derive DEC-### / AD-### count from content.

    Counts unique decision IDs anywhere in the document, as decisions may be
    referenced multiple times (in decision entry, in BUILD entries, etc.).
    Unlike builds which can have multiple milestones per BUILD-###, each
    DEC-### represents a single architectural decision.
    """
    # Count unique IDs (decisions may be referenced many times but each ID = one decision)
    dec_ids = set(re.findall(r'\bDEC-\d+\b', content))
    ad_ids = set(re.findall(r'\bAD-\d+\b', content))
    return len(dec_ids | ad_ids)  # Union of both ID sets


def derive_debug_count(content: str) -> int:
    """
    Derive debug session count from content.

    First tries to count index table rows, falls back to unique IDs and headers.
    """
    # Try counting table rows first: | YYYY-MM-DD | DBG-### | or date-based rows
    table_rows = re.findall(r'^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(DBG-\d+|\[?\d{4}-\d{2}-\d{2}\]?|[^|]+)', content, re.MULTILINE)

    if table_rows:
        # Filter to only count rows with DBG-### or date patterns in second column
        valid_rows = [row for row in table_rows if 'DBG-' in row[1] or re.match(r'\[?\d{4}-\d{2}-\d{2}\]?', row[1].strip())]
        if valid_rows:
            return len(valid_rows)

    # Fallback: count unique IDs and date headers
    dbg_ids = set(re.findall(r'\bDBG-\d+\b', content))
    date_headers = set(re.findall(r'^#{2,3}\s+\[?(\d{4}-\d{2}-\d{2})\]?', content, re.MULTILINE))
    return len(dbg_ids | date_headers)


def pick_count(name: str, meta: int | None, derived: int, verbose: bool = False, trust_meta_on_mismatch: bool = False) -> int:
    """
    Select canonical count using dual-source validation.

    Strategy:
    - If META matches derived: use META (authoritative)
    - If META missing: use derived (only source)
    - If META conflicts with derived:
      * Default: use derived + warn (assume META outdated, derived from actual content)
      * With trust_meta_on_mismatch=True: use META + warn (conservative)

    Args:
        name: Name of count for logging (e.g., "BUILD_HISTORY builds")
        meta: Count from META header (or None)
        derived: Count derived from content (table rows)
        verbose: If True, print diagnostic info
        trust_meta_on_mismatch: If True, use META even on mismatch (default: use derived)

    Returns:
        Canonical count
    """
    if meta is None:
        if verbose:
            print(f"  [{name}] No META count found, using derived: {derived}")
        return derived

    if meta != derived:
        if trust_meta_on_mismatch:
            print(f"  [WARN] {name} count mismatch: META={meta} derived={derived} (using META - trust mode)")
            return meta
        else:
            print(f"  [WARN] {name} count mismatch: META={meta} derived={derived} (using derived - META may be outdated)")
            return derived

    if verbose and meta == derived:
        print(f"  [{name}] META and derived agree: {meta}")

    return meta


def latest_build_id(content: str) -> str | None:
    """
    Extract latest BUILD-### ID from content (highest number).

    Returns:
        Latest BUILD ID (e.g., "BUILD-160"), or None if none found
    """
    ids = re.findall(r'\bBUILD-(\d+)\b', content)
    if not ids:
        return None
    max_num = max(int(id_num) for id_num in ids)
    return f"BUILD-{max_num}"


# ---------------------------------------------------------------------------
# High-Level Counting Functions (Using Dual-Source Strategy)
# ---------------------------------------------------------------------------

def count_build_history_entries(content: str, verbose: bool = False) -> int:
    """
    Count BUILD-### entries using dual-source strategy (META + derived).

    Prefers META count (Total_Builds:) but cross-checks with derived count
    from all BUILD-### occurrences in content. Warns on mismatch.
    """
    meta = parse_meta_count(content, "Builds")
    derived = derive_build_count(content)
    return pick_count("BUILD_HISTORY builds", meta, derived, verbose)


def count_debug_log_entries(content: str, verbose: bool = False) -> int:
    """
    Count debug session entries using dual-source strategy (META + derived).

    Prefers META count (Total_Issues:) but cross-checks with derived count
    from DBG-### IDs and date headers. Warns on mismatch.
    """
    meta = parse_meta_count(content, "Issues")
    derived = derive_debug_count(content)
    return pick_count("DEBUG_LOG sessions", meta, derived, verbose)


def count_architecture_decisions(content: str, verbose: bool = False) -> int:
    """
    Count decision entries using dual-source strategy (META + derived).

    Prefers META count (Total_Decisions:) but cross-checks with derived count
    from DEC-### and AD-### IDs. Warns on mismatch.
    """
    meta = parse_meta_count(content, "Decisions")
    derived = derive_decision_count(content)
    return pick_count("ARCHITECTURE_DECISIONS decisions", meta, derived, verbose)


# ---------------------------------------------------------------------------
# Summary Update Logic
# ---------------------------------------------------------------------------

def update_summary_section(
    content: str,
    entry_count: int,
    file_type: str
) -> Tuple[str, bool]:
    """
    Update or insert summary section in SOT file.

    Args:
        content: File content
        entry_count: Number of entries counted
        file_type: One of 'build_history', 'debug_log', 'architecture_decisions'

    Returns:
        Tuple of (updated_content, changed)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Create summary text
    if file_type == 'build_history':
        summary = f"""<!-- AUTO-GENERATED SUMMARY - DO NOT EDIT MANUALLY -->
**Summary**: {entry_count} build(s) documented | Last updated: {timestamp}
<!-- END AUTO-GENERATED SUMMARY -->
"""
    elif file_type == 'debug_log':
        summary = f"""<!-- AUTO-GENERATED SUMMARY - DO NOT EDIT MANUALLY -->
**Summary**: {entry_count} debug session(s) documented | Last updated: {timestamp}
<!-- END AUTO-GENERATED SUMMARY -->
"""
    elif file_type == 'architecture_decisions':
        summary = f"""<!-- AUTO-GENERATED SUMMARY - DO NOT EDIT MANUALLY -->
**Summary**: {entry_count} decision(s) documented | Last updated: {timestamp}
<!-- END AUTO-GENERATED SUMMARY -->
"""
    else:
        return content, False

    # Check if summary section already exists
    pattern = r'<!-- AUTO-GENERATED SUMMARY.*?<!-- END AUTO-GENERATED SUMMARY -->\n?'
    existing = re.search(pattern, content, re.DOTALL)

    if existing:
        # Replace existing summary
        new_content = re.sub(pattern, summary, content, flags=re.DOTALL)
        changed = new_content != content
        return new_content, changed
    else:
        # Insert summary after first heading
        # Find first H1 heading (# Title)
        heading_pattern = r'^(#\s+.+\n)'
        match = re.search(heading_pattern, content, re.MULTILINE)

        if match:
            # Insert after heading and any immediate metadata lines
            insert_pos = match.end()

            # Skip any lines that look like metadata (starting with **)
            lines = content[insert_pos:].split('\n')
            skip_count = 0
            for line in lines:
                if line.strip().startswith('**') or line.strip() == '':
                    skip_count += 1
                else:
                    break

            if skip_count > 0:
                insert_pos += len('\n'.join(lines[:skip_count])) + 1

            new_content = content[:insert_pos] + '\n' + summary + '\n' + content[insert_pos:]
            return new_content, True
        else:
            # No H1 heading found, prepend summary
            return summary + '\n' + content, True


# ---------------------------------------------------------------------------
# Main Logic
# ---------------------------------------------------------------------------

def refresh_sot_summaries(
    docs_dir: Path,
    dry_run: bool = True,
    verbose: bool = False
) -> Dict[str, int]:
    """
    Refresh summary counts in SOT documentation files.

    Args:
        docs_dir: Path to docs/ directory
        dry_run: If True, only preview changes
        verbose: If True, print detailed progress

    Returns:
        Dict mapping file names to entry counts
    """
    results = {}

    # Process BUILD_HISTORY.md
    build_history_path = docs_dir / "BUILD_HISTORY.md"
    if build_history_path.exists():
        content = build_history_path.read_text(encoding='utf-8')
        count = count_build_history_entries(content, verbose=verbose)
        results['BUILD_HISTORY.md'] = count

        new_content, changed = update_summary_section(content, count, 'build_history')

        if changed:
            if dry_run:
                print(f"[DRY-RUN] Would update BUILD_HISTORY.md summary: {count} build(s)")
                if verbose:
                    print(f"  Preview of new summary section:")
                    summary_match = re.search(
                        r'<!-- AUTO-GENERATED SUMMARY.*?<!-- END AUTO-GENERATED SUMMARY -->',
                        new_content,
                        re.DOTALL
                    )
                    if summary_match:
                        print(f"  {summary_match.group()}")
            else:
                atomic_write(build_history_path, new_content)
                print(f"[UPDATED] BUILD_HISTORY.md: {count} build(s)")
        else:
            if verbose:
                print(f"[NO-CHANGE] BUILD_HISTORY.md: {count} build(s) (already up to date)")
    else:
        print(f"[SKIP] BUILD_HISTORY.md not found: {build_history_path}")

    # Process DEBUG_LOG.md
    debug_log_path = docs_dir / "DEBUG_LOG.md"
    if debug_log_path.exists():
        content = debug_log_path.read_text(encoding='utf-8')
        count = count_debug_log_entries(content, verbose=verbose)
        results['DEBUG_LOG.md'] = count

        new_content, changed = update_summary_section(content, count, 'debug_log')

        if changed:
            if dry_run:
                print(f"[DRY-RUN] Would update DEBUG_LOG.md summary: {count} debug session(s)")
            else:
                atomic_write(debug_log_path, new_content)
                print(f"[UPDATED] DEBUG_LOG.md: {count} debug session(s)")
        else:
            if verbose:
                print(f"[NO-CHANGE] DEBUG_LOG.md: {count} debug session(s) (already up to date)")
    else:
        print(f"[SKIP] DEBUG_LOG.md not found: {debug_log_path}")

    # Process ARCHITECTURE_DECISIONS.md
    arch_decisions_path = docs_dir / "ARCHITECTURE_DECISIONS.md"
    if arch_decisions_path.exists():
        content = arch_decisions_path.read_text(encoding='utf-8')
        count = count_architecture_decisions(content, verbose=verbose)
        results['ARCHITECTURE_DECISIONS.md'] = count

        new_content, changed = update_summary_section(content, count, 'architecture_decisions')

        if changed:
            if dry_run:
                print(f"[DRY-RUN] Would update ARCHITECTURE_DECISIONS.md summary: {count} decision(s)")
            else:
                atomic_write(arch_decisions_path, new_content)
                print(f"[UPDATED] ARCHITECTURE_DECISIONS.md: {count} decision(s)")
        else:
            if verbose:
                print(f"[NO-CHANGE] ARCHITECTURE_DECISIONS.md: {count} decision(s) (already up to date)")
    else:
        print(f"[SKIP] ARCHITECTURE_DECISIONS.md not found: {arch_decisions_path}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Refresh SOT summary counts in docs/*.md files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Dry run only (default)")
    parser.add_argument("--execute", action="store_true",
                        help="Execute changes (overrides --dry-run)")
    parser.add_argument("--project", default="autopack",
                        help="Project scope (default: autopack)")
    parser.add_argument("--verbose", action="store_true",
                        help="Verbose output")

    args = parser.parse_args()

    # Resolve execution mode
    dry_run = not args.execute

    # Resolve docs dir
    repo_root = REPO_ROOT
    if args.project == "autopack":
        docs_dir = repo_root / "docs"
    else:
        docs_dir = repo_root / ".autonomous_runs" / args.project / "docs"

    if not docs_dir.exists():
        print(f"[ERROR] Docs directory not found: {docs_dir}")
        return 1

    print("=" * 70)
    print("SOT SUMMARY REFRESH - Docs-Only Summary Update")
    print("=" * 70)
    print(f"Project: {args.project}")
    print(f"Docs dir: {docs_dir}")
    print(f"Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print("=" * 70)

    results = refresh_sot_summaries(docs_dir, dry_run=dry_run, verbose=args.verbose)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for file_name, count in results.items():
        print(f"{file_name}: {count} entries")

    if dry_run:
        print("\nDRY-RUN MODE - No changes were made")
        print("   Run with --execute to apply changes")
    else:
        print("\nChanges applied successfully")

    return 0


if __name__ == "__main__":
    sys.exit(main())
