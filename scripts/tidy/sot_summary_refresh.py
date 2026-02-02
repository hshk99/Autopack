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

# Windows consoles can default to legacy encodings (e.g., cp1252) that can't print
# the status glyphs/emojis used by this script. Keep output UTF-8 to avoid crashes.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

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
    pattern = rf"^Total_{key}:\s*(\d+)\s*$"
    match = re.search(pattern, content, re.MULTILINE)
    return int(match.group(1)) if match else None


def derive_build_count(content: str) -> tuple[int, int]:
    """
    Derive BUILD-### count from content (index table rows + unique IDs).

    Returns both:
    - Total build entries (table rows - can have multiple entries per BUILD ID)
    - Unique build IDs (distinct BUILD-### identifiers)

    Returns:
        Tuple of (total_entries, unique_build_ids)
    """
    # Count index table rows: | YYYY-MM-DD | BUILD-### | ...
    table_rows = re.findall(r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*BUILD-\d+", content, re.MULTILINE)

    # Count unique BUILD IDs
    unique_ids = set(re.findall(r"\bBUILD-\d+\b", content))

    if table_rows:
        return len(table_rows), len(unique_ids)
    else:
        # Fallback: if no table, both counts are the same (unique IDs)
        return len(unique_ids), len(unique_ids)


def derive_decision_count(content: str) -> int:
    """
    Derive DEC-### / AD-### count from content.

    IMPORTANT:
    - Prefer counting actual decision *definitions* (section headings) rather than references.
      This avoids inflation from cross-links like "Related Decisions: DEC-XXX".
    - Fall back to ID union counting only if no headings are present (legacy formats).
    """
    # Preferred: decision section headings (current format)
    heading_ids = set(re.findall(r"^###\s+(DEC-\d{3})\b", content, flags=re.MULTILINE))
    if heading_ids:
        return len(heading_ids)

    # Fallback: union of referenced IDs (legacy)
    dec_ids = set(re.findall(r"\bDEC-\d+\b", content))
    ad_ids = set(re.findall(r"\bAD-\d+\b", content))
    return len(dec_ids | ad_ids)


def update_meta_block(content: str, updates: dict[str, str]) -> tuple[str, bool]:
    """
    Update keys inside the first <!-- META ... --> block.

    Only updates keys present in `updates`. If the META block or key is missing, leaves content unchanged.

    Note: Changes to Last_Updated timestamp are not considered "real" changes for drift detection.
    """
    meta_re = re.compile(r"<!-- META\s*\n(.*?)\n-->", re.DOTALL)
    m = meta_re.search(content)
    if not m:
        return content, False

    meta_body = m.group(1)
    lines = meta_body.splitlines()
    changed = False

    for i, line in enumerate(lines):
        for key, value in updates.items():
            if re.match(rf"^{re.escape(key)}:\s*", line):
                new_line = f"{key}: {value}"
                if new_line != line:
                    # Ignore Last_Updated timestamp changes for drift detection
                    if key != "Last_Updated":
                        changed = True
                    lines[i] = new_line

    if not changed:
        return content, False

    new_body = "\n".join(lines)
    new_content = content[: m.start(1)] + new_body + content[m.end(1) :]
    return new_content, True


def _latest_build_title_from_build_history(build_history: str) -> str | None:
    """
    Extract a human-friendly latest build title from docs/BUILD_HISTORY.md.

    Prefers the latest '## BUILD-###' section's '**Title**:' line and optional status marker.
    """
    ids = re.findall(r"^##\s+BUILD-(\d+)\b", build_history, flags=re.MULTILINE)
    if not ids:
        return None
    latest = max(int(x) for x in ids)
    latest_id = f"BUILD-{latest}"

    # Find the latest build section and extract title + status
    sec_re = re.compile(rf"^##\s+{re.escape(latest_id)}\b", re.MULTILINE)
    m = sec_re.search(build_history)
    if not m:
        return latest_id

    tail = build_history[m.end() :]
    next_m = re.search(r"^##\s+BUILD-\d+\b", tail, flags=re.MULTILINE)
    block = tail[: next_m.start()] if next_m else tail

    title_m = re.search(r"^\*\*Title\*\*:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    status_m = re.search(r"^\*\*Status\*\*:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    title = title_m.group(1).strip() if title_m else ""
    status = status_m.group(1).strip() if status_m else ""

    # Keep status markers if present; otherwise omit.
    # Support both ASCII markers ([OK], [!], [X]) and legacy Unicode glyphs.
    # ASCII markers are preferred for Windows console compatibility.
    status_suffix = ""
    # ASCII markers (preferred, Windows-safe)
    ascii_markers = ("[OK]", "[!]", "[X]")
    # Legacy Unicode glyphs (for backward compatibility with existing entries)
    unicode_markers = ("\u2705", "\u26a0\ufe0f", "\u274c")  # checkmark, warning, cross
    # Map Unicode to ASCII for normalization
    unicode_to_ascii = {"\u2705": "[OK]", "\u26a0\ufe0f": "[!]", "\u274c": "[X]"}

    # Check for ASCII markers first (preferred)
    for marker in ascii_markers:
        if marker in status:
            status_suffix = f" {marker}"
            break
    else:
        # Fall back to Unicode markers if present, but emit as ASCII
        for glyph in unicode_markers:
            if glyph in status:
                status_suffix = f" {unicode_to_ascii[glyph]}"
                break

    if title:
        return f"{latest_id}: {title}{status_suffix}"
    return f"{latest_id}{status_suffix}"


def update_readme_sot_summary(
    project_root: Path,
    build_entries: int,
    build_unique: int,
    latest_build_title: str | None,
    decision_count: int,
    debug_count: int,
    dry_run: bool,
    verbose: bool = False,
) -> bool:
    """
    Update README.md <!-- SOT_SUMMARY_START/END --> block to match current SOT counts.
    """
    readme_path = project_root / "README.md"
    if not readme_path.exists():
        return False

    marker_start = "<!-- SOT_SUMMARY_START -->"
    marker_end = "<!-- SOT_SUMMARY_END -->"

    content = readme_path.read_text(encoding="utf-8")
    if marker_start not in content or marker_end not in content:
        return False

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    summary_lines: list[str] = [f"**Last Updated**: {timestamp}", ""]

    if build_unique != build_entries:
        summary_lines.append(
            f"- **Builds Completed**: {build_entries} (includes multi-phase builds, {build_unique} unique)"
        )
    else:
        summary_lines.append(f"- **Builds Completed**: {build_entries}")

    if latest_build_title:
        summary_lines.append(f"- **Latest Build**: {latest_build_title}")
    else:
        summary_lines.append("- **Latest Build**: (unknown)")

    summary_lines.append(f"- **Architecture Decisions**: {decision_count}")
    summary_lines.append(f"- **Debugging Sessions**: {debug_count}")
    summary_lines.append("")
    summary_lines.append("*Auto-generated by Autopack Tidy System*")

    new_block = "\n".join(summary_lines)
    before = content.split(marker_start)[0]
    after = content.split(marker_end)[1]
    new_content = f"{before}{marker_start}\n{new_block}\n{marker_end}{after}"

    # Extract existing block for comparison
    existing_block = content.split(marker_start)[1].split(marker_end)[0].strip()

    # Normalize both blocks (ignore timestamp changes)
    def normalize_readme_block(block: str) -> str:
        # Remove timestamp line
        return re.sub(r"\*\*Last Updated\*\*: [^\n]+", "**Last Updated**: <TIMESTAMP>", block)

    if normalize_readme_block(existing_block) == normalize_readme_block(new_block):
        return False

    if dry_run:
        if verbose:
            print("[DRY-RUN] Would update README.md SOT summary block")
        return True

    atomic_write(readme_path, new_content)
    return True


def derive_debug_count(content: str) -> int:
    """
    Derive debug session count from content.

    First tries to count index table rows, falls back to unique IDs and headers.
    """
    # Try counting table rows first: | YYYY-MM-DD | DBG-### | or date-based rows
    table_rows = re.findall(
        r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(DBG-\d+|\[?\d{4}-\d{2}-\d{2}\]?|[^|]+)",
        content,
        re.MULTILINE,
    )

    if table_rows:
        # Filter to only count rows with DBG-### or date patterns in second column
        valid_rows = [
            row
            for row in table_rows
            if "DBG-" in row[1] or re.match(r"\[?\d{4}-\d{2}-\d{2}\]?", row[1].strip())
        ]
        if valid_rows:
            return len(valid_rows)

    # Fallback: count unique IDs and date headers
    dbg_ids = set(re.findall(r"\bDBG-\d+\b", content))
    date_headers = set(re.findall(r"^#{2,3}\s+\[?(\d{4}-\d{2}-\d{2})\]?", content, re.MULTILINE))
    return len(dbg_ids | date_headers)


def pick_count(
    name: str,
    meta: int | None,
    derived: int,
    verbose: bool = False,
    trust_meta_on_mismatch: bool = False,
) -> int:
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
            print(
                f"  [WARN] {name} count mismatch: META={meta} derived={derived} (using META - trust mode)"
            )
            return meta
        else:
            print(
                f"  [WARN] {name} count mismatch: META={meta} derived={derived} (using derived - META may be outdated)"
            )
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
    ids = re.findall(r"\bBUILD-(\d+)\b", content)
    if not ids:
        return None
    max_num = max(int(id_num) for id_num in ids)
    return f"BUILD-{max_num}"


# ---------------------------------------------------------------------------
# High-Level Counting Functions (Using Dual-Source Strategy)
# ---------------------------------------------------------------------------


def count_build_history_entries(content: str, verbose: bool = False) -> tuple[int, int]:
    """
    Count BUILD-### entries using dual-source strategy (META + derived).

    Returns both total entries and unique build IDs for clarity.

    Returns:
        Tuple of (total_entries, unique_build_ids)
    """
    meta = parse_meta_count(content, "Builds")
    derived_entries, derived_unique = derive_build_count(content)

    # Use dual-source validation for total entries
    total_entries = pick_count("BUILD_HISTORY build entries", meta, derived_entries, verbose)

    # Unique IDs are always derived (no META equivalent)
    return total_entries, derived_unique


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


def _normalize_summary_for_comparison(summary: str) -> str:
    """
    Normalize summary by removing timestamps for comparison purposes.
    This allows detecting real content changes without timestamp noise.
    """
    # Remove the timestamp portion
    return re.sub(r"\| Last updated: [^|]+", "| Last updated: <TIMESTAMP>", summary)


def update_summary_section(
    content: str, entry_count: int, file_type: str, unique_count: int | None = None
) -> Tuple[str, bool]:
    """
    Update or insert summary section in SOT file.

    Args:
        content: File content
        entry_count: Number of entries counted
        file_type: One of 'build_history', 'debug_log', 'architecture_decisions'
        unique_count: For build_history, the count of unique BUILD IDs (optional)

    Returns:
        Tuple of (updated_content, changed)
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Create summary text
    if file_type == "build_history":
        if unique_count is not None and unique_count != entry_count:
            # Show both counts when they differ
            summary = f"""<!-- AUTO-GENERATED SUMMARY - DO NOT EDIT MANUALLY -->
**Summary**: {entry_count} build entries ({unique_count} unique builds) documented | Last updated: {timestamp}
<!-- END AUTO-GENERATED SUMMARY -->
"""
        else:
            # Show single count when they're the same
            summary = f"""<!-- AUTO-GENERATED SUMMARY - DO NOT EDIT MANUALLY -->
**Summary**: {entry_count} build(s) documented | Last updated: {timestamp}
<!-- END AUTO-GENERATED SUMMARY -->
"""
    elif file_type == "debug_log":
        summary = f"""<!-- AUTO-GENERATED SUMMARY - DO NOT EDIT MANUALLY -->
**Summary**: {entry_count} debug session(s) documented | Last updated: {timestamp}
<!-- END AUTO-GENERATED SUMMARY -->
"""
    elif file_type == "architecture_decisions":
        summary = f"""<!-- AUTO-GENERATED SUMMARY - DO NOT EDIT MANUALLY -->
**Summary**: {entry_count} decision(s) documented | Last updated: {timestamp}
<!-- END AUTO-GENERATED SUMMARY -->
"""
    else:
        return content, False

    # Check if summary section already exists
    pattern = r"<!-- AUTO-GENERATED SUMMARY.*?<!-- END AUTO-GENERATED SUMMARY -->\n?"
    existing = re.search(pattern, content, re.DOTALL)

    if existing:
        # Compare normalized versions (ignore timestamp changes)
        old_normalized = _normalize_summary_for_comparison(existing.group())
        new_normalized = _normalize_summary_for_comparison(summary)
        changed = old_normalized != new_normalized

        if changed:
            # Real content change - update the summary
            new_content = re.sub(pattern, summary, content, flags=re.DOTALL)
            return new_content, True
        else:
            # Only timestamp changed - don't modify content
            return content, False
    else:
        # Insert summary after first heading
        # Find first H1 heading (# Title)
        heading_pattern = r"^(#\s+.+\n)"
        match = re.search(heading_pattern, content, re.MULTILINE)

        if match:
            # Insert after heading and any immediate metadata lines
            insert_pos = match.end()

            # Skip any lines that look like metadata (starting with **)
            lines = content[insert_pos:].split("\n")
            skip_count = 0
            for line in lines:
                if line.strip().startswith("**") or line.strip() == "":
                    skip_count += 1
                else:
                    break

            if skip_count > 0:
                insert_pos += len("\n".join(lines[:skip_count])) + 1

            new_content = content[:insert_pos] + "\n" + summary + "\n" + content[insert_pos:]
            return new_content, True
        else:
            # No H1 heading found, prepend summary
            return summary + "\n" + content, True


# ---------------------------------------------------------------------------
# Main Logic
# ---------------------------------------------------------------------------


def refresh_sot_summaries(
    docs_dir: Path, dry_run: bool = True, verbose: bool = False, check_mode: bool = False
) -> tuple[Dict[str, int], bool]:
    """
    Refresh summary counts in SOT documentation files.

    Args:
        docs_dir: Path to docs/ directory
        dry_run: If True, only preview changes
        verbose: If True, print detailed progress
        check_mode: If True, exit with code 1 if any derived state would change

    Returns:
        Tuple of (Dict mapping file names to entry counts, bool indicating if changes detected)
    """
    results = {}
    changes_detected = False

    # Process BUILD_HISTORY.md
    build_history_path = docs_dir / "BUILD_HISTORY.md"
    if build_history_path.exists():
        content = build_history_path.read_text(encoding="utf-8")
        total_entries, unique_builds = count_build_history_entries(content, verbose=verbose)
        results["BUILD_HISTORY.md"] = (total_entries, unique_builds)

        new_content, changed = update_summary_section(
            content, total_entries, "build_history", unique_count=unique_builds
        )
        # Keep META header aligned with derived counts (reduces drift after manual edits)
        meta_updates = {
            "Last_Updated": datetime.now().isoformat() + "Z",
            "Total_Builds": str(total_entries),
        }
        new_content2, meta_changed = update_meta_block(new_content, meta_updates)
        if meta_changed:
            new_content = new_content2
            changed = True

        if changed:
            changes_detected = True
            if dry_run or check_mode:
                if unique_builds != total_entries:
                    print(
                        f"[{'CHECK' if check_mode else 'DRY-RUN'}] Would update BUILD_HISTORY.md summary: {total_entries} entries ({unique_builds} unique builds)"
                    )
                else:
                    print(
                        f"[{'CHECK' if check_mode else 'DRY-RUN'}] Would update BUILD_HISTORY.md summary: {total_entries} build(s)"
                    )
                if verbose:
                    print("  Preview of new summary section:")
                    summary_match = re.search(
                        r"<!-- AUTO-GENERATED SUMMARY.*?<!-- END AUTO-GENERATED SUMMARY -->",
                        new_content,
                        re.DOTALL,
                    )
                    if summary_match:
                        print(f"  {summary_match.group()}")
            else:
                atomic_write(build_history_path, new_content)
                if unique_builds != total_entries:
                    print(
                        f"[UPDATED] BUILD_HISTORY.md: {total_entries} entries ({unique_builds} unique builds)"
                    )
                else:
                    print(f"[UPDATED] BUILD_HISTORY.md: {total_entries} build(s)")
        else:
            if verbose:
                if unique_builds != total_entries:
                    print(
                        f"[NO-CHANGE] BUILD_HISTORY.md: {total_entries} entries ({unique_builds} unique builds) (already up to date)"
                    )
                else:
                    print(
                        f"[NO-CHANGE] BUILD_HISTORY.md: {total_entries} build(s) (already up to date)"
                    )
    else:
        print(f"[SKIP] BUILD_HISTORY.md not found: {build_history_path}")

    # Process DEBUG_LOG.md
    debug_log_path = docs_dir / "DEBUG_LOG.md"
    if debug_log_path.exists():
        content = debug_log_path.read_text(encoding="utf-8")
        count = count_debug_log_entries(content, verbose=verbose)
        results["DEBUG_LOG.md"] = count

        new_content, changed = update_summary_section(content, count, "debug_log")
        meta_updates = {
            "Last_Updated": datetime.now().isoformat() + "Z",
            "Total_Issues": str(count),
        }
        new_content2, meta_changed = update_meta_block(new_content, meta_updates)
        if meta_changed:
            new_content = new_content2
            changed = True

        if changed:
            changes_detected = True
            if dry_run or check_mode:
                print(
                    f"[{'CHECK' if check_mode else 'DRY-RUN'}] Would update DEBUG_LOG.md summary: {count} debug session(s)"
                )
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
        content = arch_decisions_path.read_text(encoding="utf-8")
        count = count_architecture_decisions(content, verbose=verbose)
        results["ARCHITECTURE_DECISIONS.md"] = count

        new_content, changed = update_summary_section(content, count, "architecture_decisions")
        meta_updates = {
            "Last_Updated": datetime.now().isoformat() + "Z",
            "Total_Decisions": str(count),
        }
        new_content2, meta_changed = update_meta_block(new_content, meta_updates)
        if meta_changed:
            new_content = new_content2
            changed = True

        if changed:
            changes_detected = True
            if dry_run or check_mode:
                print(
                    f"[{'CHECK' if check_mode else 'DRY-RUN'}] Would update ARCHITECTURE_DECISIONS.md summary: {count} decision(s)"
                )
            else:
                atomic_write(arch_decisions_path, new_content)
                print(f"[UPDATED] ARCHITECTURE_DECISIONS.md: {count} decision(s)")
        else:
            if verbose:
                print(
                    f"[NO-CHANGE] ARCHITECTURE_DECISIONS.md: {count} decision(s) (already up to date)"
                )
    else:
        print(f"[SKIP] ARCHITECTURE_DECISIONS.md not found: {arch_decisions_path}")

    # Optional: update README.md SOT summary block (if present)
    # NOTE: README lives at project root (docs_dir parent).
    project_root = docs_dir.parent
    build_history_path = docs_dir / "BUILD_HISTORY.md"
    debug_log_path = docs_dir / "DEBUG_LOG.md"
    arch_decisions_path = docs_dir / "ARCHITECTURE_DECISIONS.md"
    if build_history_path.exists() and debug_log_path.exists() and arch_decisions_path.exists():
        bh = build_history_path.read_text(encoding="utf-8")
        total_entries, unique_builds = derive_build_count(bh)
        latest_title = _latest_build_title_from_build_history(bh)

        dbg = debug_log_path.read_text(encoding="utf-8")
        dbg_count = count_debug_log_entries(dbg, verbose=False)

        ad = arch_decisions_path.read_text(encoding="utf-8")
        ad_count = count_architecture_decisions(ad, verbose=False)

        readme_changed = update_readme_sot_summary(
            project_root=project_root,
            build_entries=total_entries,
            build_unique=unique_builds,
            latest_build_title=latest_title,
            decision_count=ad_count,
            debug_count=dbg_count,
            dry_run=dry_run or check_mode,
            verbose=verbose,
        )
        if readme_changed:
            changes_detected = True
            if verbose or check_mode:
                print(
                    f"[{'CHECK' if check_mode else 'DRY-RUN' if dry_run else 'UPDATED'}] README.md SOT summary block"
                )

    return results, changes_detected


def main():
    parser = argparse.ArgumentParser(
        description="Refresh SOT summary counts in docs/*.md files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--dry-run", action="store_true", default=True, help="Dry run only (default)"
    )
    parser.add_argument(
        "--execute", action="store_true", help="Execute changes (overrides --dry-run)"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: exit 1 if any derived state would change, 0 otherwise (for CI)",
    )
    parser.add_argument("--project", default="autopack", help="Project scope (default: autopack)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Resolve execution mode
    check_mode = args.check
    dry_run = not args.execute and not check_mode

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
    if check_mode:
        print("Mode: CHECK (drift detection for CI)")
    else:
        print(f"Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print("=" * 70)

    results, changes_detected = refresh_sot_summaries(
        docs_dir, dry_run=dry_run, verbose=args.verbose, check_mode=check_mode
    )

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for file_name, count in results.items():
        if isinstance(count, tuple):
            # BUILD_HISTORY.md returns (total_entries, unique_builds)
            total, unique = count
            if total != unique:
                print(f"{file_name}: {total} entries ({unique} unique builds)")
            else:
                print(f"{file_name}: {total} entries")
        else:
            # Other files return single int
            print(f"{file_name}: {count} entries")

    if check_mode:
        if changes_detected:
            print("\n[X] CHECK FAILED - Derived state drift detected")
            print("   Run 'python scripts/tidy/sot_summary_refresh.py --execute' to fix")
            return 1
        else:
            print("\n[OK] CHECK PASSED - All derived state is up to date")
            return 0
    elif dry_run:
        print("\nDRY-RUN MODE - No changes were made")
        print("   Run with --execute to apply changes")
    else:
        print("\nChanges applied successfully")

    return 0


if __name__ == "__main__":
    sys.exit(main())
