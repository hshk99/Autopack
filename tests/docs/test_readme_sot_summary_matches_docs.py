"""
Test that README.md SOT summary block matches derived state from SOT files.

This test ensures the README's <!-- SOT_SUMMARY_START/END --> block stays
in sync with the canonical SOT ledgers (BUILD_HISTORY, ARCHITECTURE_DECISIONS, DEBUG_LOG).

Prevents "two truths" problem where README drifts from actual SOT state.
"""

import re
from pathlib import Path


def test_readme_sot_summary_matches_derived_state():
    """
    Guardrail: README.md SOT summary must match derived state from SOT files.

    Checks:
    1. Build counts (entries + unique)
    2. Latest build title
    3. Architecture decision count
    4. Debug session count

    If this test fails, run:
        python scripts/tidy/sot_summary_refresh.py --execute
    """
    repo_root = Path(__file__).parents[2]
    readme_path = repo_root / "README.md"
    docs_dir = repo_root / "docs"

    # Read README
    readme = readme_path.read_text(encoding="utf-8")

    # Extract SOT summary block
    marker_start = "<!-- SOT_SUMMARY_START -->"
    marker_end = "<!-- SOT_SUMMARY_END -->"

    assert marker_start in readme, "README missing SOT_SUMMARY_START marker"
    assert marker_end in readme, "README missing SOT_SUMMARY_END marker"

    summary_block = readme.split(marker_start)[1].split(marker_end)[0].strip()

    # Extract README values
    builds_match = re.search(
        r"- \*\*Builds Completed\*\*:\s*(\d+)(?:\s+\(includes multi-phase builds, (\d+) unique\))?",
        summary_block,
    )
    latest_build_match = re.search(r"- \*\*Latest Build\*\*:\s*(.+?)$", summary_block, re.MULTILINE)
    decisions_match = re.search(r"- \*\*Architecture Decisions\*\*:\s*(\d+)", summary_block)
    debug_match = re.search(r"- \*\*Debugging Sessions\*\*:\s*(\d+)", summary_block)

    assert builds_match, "README missing Builds Completed line"
    assert latest_build_match, "README missing Latest Build line"
    assert decisions_match, "README missing Architecture Decisions line"
    assert debug_match, "README missing Debugging Sessions line"

    readme_build_entries = int(builds_match.group(1))
    readme_build_unique = (
        int(builds_match.group(2)) if builds_match.group(2) else readme_build_entries
    )
    readme_latest_build = latest_build_match.group(1).strip()
    readme_decision_count = int(decisions_match.group(1))
    readme_debug_count = int(debug_match.group(1))

    # Derive actual values from SOT files
    build_history = (docs_dir / "BUILD_HISTORY.md").read_text(encoding="utf-8")
    arch_decisions = (docs_dir / "ARCHITECTURE_DECISIONS.md").read_text(encoding="utf-8")
    debug_log = (docs_dir / "DEBUG_LOG.md").read_text(encoding="utf-8")

    # Derive build counts
    table_rows = re.findall(
        r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*BUILD-\d+", build_history, re.MULTILINE
    )
    unique_build_ids = set(re.findall(r"\bBUILD-\d+\b", build_history))
    derived_build_entries = len(table_rows) if table_rows else len(unique_build_ids)
    derived_build_unique = len(unique_build_ids)

    # Derive latest build title
    build_ids = re.findall(r"^##\s+BUILD-(\d+)\b", build_history, flags=re.MULTILINE)
    assert build_ids, "No BUILD-### sections found in BUILD_HISTORY.md"
    latest_build_num = max(int(x) for x in build_ids)
    latest_build_id = f"BUILD-{latest_build_num}"

    # Extract latest build title from section (not INDEX)
    sec_re = re.compile(rf"^##\s+{re.escape(latest_build_id)}\b", re.MULTILINE)
    m = sec_re.search(build_history)
    assert m, f"Could not find section for {latest_build_id}"

    tail = build_history[m.end() :]
    next_m = re.search(r"^##\s+BUILD-\d+\b", tail, flags=re.MULTILINE)
    block = tail[: next_m.start()] if next_m else tail

    title_m = re.search(r"^\*\*Title\*\*:\s*(.+?)\s*$", block, flags=re.MULTILINE)
    status_m = re.search(r"^\*\*Status\*\*:\s*(.+?)\s*$", block, flags=re.MULTILINE)

    title = title_m.group(1).strip() if title_m else ""
    status = status_m.group(1).strip() if status_m else ""

    # Reconstruct expected latest build string
    status_suffix = ""
    if any(g in status for g in ("✅", "⚠️", "❌")):
        for g in ("✅", "⚠️", "❌"):
            if g in status:
                status_suffix = f" {g}"
                break

    derived_latest_build = (
        f"{latest_build_id}: {title}{status_suffix}"
        if title
        else f"{latest_build_id}{status_suffix}"
    )

    # Derive decision count (DEC-### section headings only, not references)
    decision_headings = set(re.findall(r"^###\s+(DEC-\d{3})\b", arch_decisions, flags=re.MULTILINE))
    derived_decision_count = len(decision_headings)

    # Derive debug count (table rows or unique IDs)
    debug_table_rows = re.findall(
        r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(DBG-\d+|\[?\d{4}-\d{2}-\d{2}\]?|[^|]+)",
        debug_log,
        re.MULTILINE,
    )
    if debug_table_rows:
        valid_rows = [
            row
            for row in debug_table_rows
            if "DBG-" in row[1] or re.match(r"\[?\d{4}-\d{2}-\d{2}\]?", row[1].strip())
        ]
        derived_debug_count = len(valid_rows)
    else:
        dbg_ids = set(re.findall(r"\bDBG-\d+\b", debug_log))
        date_headers = set(
            re.findall(r"^#{2,3}\s+\[?(\d{4}-\d{2}-\d{2})\]?", debug_log, re.MULTILINE)
        )
        derived_debug_count = len(dbg_ids | date_headers)

    # Assert README matches derived state
    assert readme_build_entries == derived_build_entries, (
        f"README build entries ({readme_build_entries}) != derived ({derived_build_entries}). "
        f"Run: python scripts/tidy/sot_summary_refresh.py --execute"
    )

    assert readme_build_unique == derived_build_unique, (
        f"README unique builds ({readme_build_unique}) != derived ({derived_build_unique}). "
        f"Run: python scripts/tidy/sot_summary_refresh.py --execute"
    )

    assert readme_latest_build == derived_latest_build, (
        f"README latest build ('{readme_latest_build}') != derived ('{derived_latest_build}'). "
        f"Run: python scripts/tidy/sot_summary_refresh.py --execute"
    )

    assert readme_decision_count == derived_decision_count, (
        f"README decision count ({readme_decision_count}) != derived ({derived_decision_count}). "
        f"Run: python scripts/tidy/sot_summary_refresh.py --execute"
    )

    assert readme_debug_count == derived_debug_count, (
        f"README debug count ({readme_debug_count}) != derived ({derived_debug_count}). "
        f"Run: python scripts/tidy/sot_summary_refresh.py --execute"
    )
