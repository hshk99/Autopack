"""
Test that DEBUG_LOG.md INDEX table matches debug sections.

This test ensures the INDEX table stays in sync with actual DBG-### sections,
preventing "phantom" debug entries in the index or missing index entries.

Enforces strict "no two truths" invariant for recent INDEX window (top 50 rows).
"""

import re
from pathlib import Path

# Recent INDEX window size: enforce strict matching for the first N rows
RECENT_INDEX_WINDOW = 50


def test_debug_log_index_recent_rows_match_sections_and_no_duplicate_dbg_ids():
    """
    Guardrail: docs/DEBUG_LOG.md INDEX must match debug sections.

    Checks:
    1. No duplicate DBG-### IDs in section headings (ID-level uniqueness)
    2. Recent INDEX rows (top 50) must reference existing sections (no phantom IDs)
    3. Historical INDEX rows (beyond top 50) allowed without sections (informational)
    4. Minimum structure validation (at least 1 INDEX row, at least 1 section)

    Current DEBUG_LOG format:
      - Debug sections: "## DBG-084" or "### DBG-084"
      - INDEX table rows: "| YYYY-MM-DD | DBG-084 | <title> | <status> |"
    """
    repo_root = Path(__file__).parents[2]
    dbg_path = repo_root / "docs" / "DEBUG_LOG.md"
    content = dbg_path.read_text(encoding="utf-8")

    # 1) Extract section IDs (canonical definitions)
    section_re = re.compile(r'^(#{2,3})\s+(DBG-(\d+))\b', re.MULTILINE)
    section_ids = []

    for m in section_re.finditer(content):
        section_ids.append(m.group(2))  # "DBG-084"

    assert section_ids, "No DBG-### section headings found in docs/DEBUG_LOG.md"

    # 2) Fail on duplicate DBG IDs in sections (ID-level uniqueness)
    dup_ids = sorted({x for x in section_ids if section_ids.count(x) > 1})
    assert not dup_ids, (
        f"Duplicate DBG IDs in DEBUG_LOG sections:\n"
        + "\n".join([f"  - {d}" for d in dup_ids])
        + "\nEach DBG-### section must be unique."
    )

    section_set = set(section_ids)

    # 3) Extract INDEX rows in order (recent first, as written in INDEX table)
    index_re = re.compile(r'^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*(DBG-\d+)\b', re.MULTILINE)
    index_ids_ordered = index_re.findall(content)
    assert index_ids_ordered, "No DBG-### rows found in DEBUG_LOG.md INDEX table"

    # 4) Enforce "no phantom IDs" for recent window (strict canonicalization)
    recent = index_ids_ordered[:RECENT_INDEX_WINDOW]
    missing_sections = [dbg for dbg in recent if dbg not in section_set]
    assert not missing_sections, (
        f"DEBUG_LOG INDEX (top {RECENT_INDEX_WINDOW}) references DBG IDs with no corresponding section:\n"
        + "\n".join([f"  - {dbg}" for dbg in missing_sections])
        + f"\n\nFix: add the missing DBG-### sections or remove/fix the INDEX rows."
        + f"\nRecent window enforces strict INDEX/section sync to prevent 'two truths' drift."
    )

    # 5) Optional: informational note for older rows (allowed historical looseness)
    older = index_ids_ordered[RECENT_INDEX_WINDOW:]
    phantom_older = sorted({dbg for dbg in older if dbg not in section_set})
    if phantom_older:
        print(
            f"\nNote: DEBUG_LOG has {len(phantom_older)} historical INDEX IDs without sections "
            f"(allowed outside recent window of {RECENT_INDEX_WINDOW})."
        )

    # 6) Optional: Check if all sections have INDEX entries (informational)
    missing_from_index = sorted({dbg for dbg in section_ids if dbg not in index_ids_ordered})
    if missing_from_index:
        print(
            f"\nNote: {len(missing_from_index)} DBG sections have no INDEX entry:\n"
            + "\n".join([f"  - {dbg}" for dbg in missing_from_index[:5]])
            + ("..." if len(missing_from_index) > 5 else "")
        )
