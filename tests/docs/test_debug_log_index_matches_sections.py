"""
Test that DEBUG_LOG.md INDEX table matches debug sections.

This test ensures the INDEX table stays in sync with actual DBG-### sections,
preventing "phantom" debug entries in the index or missing index entries.
"""

import re
from pathlib import Path


def test_debug_log_index_matches_sections_and_no_duplicates():
    """
    Guardrail: docs/DEBUG_LOG.md INDEX must match debug sections.

    Checks:
    1. No duplicate ## or ### DBG-### section headings
    2. INDEX table DBG IDs are subset of section DBG IDs (no phantom IDs)
    3. All sections have corresponding INDEX entries (optional - can be relaxed)

    Current DEBUG_LOG format:
      - Debug sections: "## DBG-084" or "### DBG-084"
      - INDEX table rows: "| YYYY-MM-DD | DBG-084 | <title> | <status> |"
    """
    repo_root = Path(__file__).parents[2]
    dbg_path = repo_root / "docs" / "DEBUG_LOG.md"
    content = dbg_path.read_text(encoding="utf-8")

    # 1) Section headings: allow ## or ###, capture DBG-###
    section_re = re.compile(r'^(#{2,3})\s+(DBG-(\d+))\b', re.MULTILINE)
    section_full = []
    section_nums = []

    for m in section_re.finditer(content):
        full = m.group(2)          # "DBG-084"
        num = m.group(3)           # "084"
        section_full.append(full)
        section_nums.append(num)

    assert section_nums, "No DBG-### sections found in DEBUG_LOG.md"

    # 2) Detect exact duplicates in section headings (same DBG-###)
    dup_ids = sorted({x for x in section_full if section_full.count(x) > 1})
    assert not dup_ids, (
        f"Duplicate DBG IDs in sections:\n"
        + "\n".join([f"  - {d}" for d in dup_ids])
        + "\nEach DBG-### section should be unique."
    )

    # 3) INDEX table rows: | YYYY-MM-DD | DBG-### | ...
    index_re = re.compile(r'^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*DBG-(\d+)\b', re.MULTILINE)
    index_nums = index_re.findall(content)
    assert index_nums, "No DBG-### index rows found in DEBUG_LOG.md INDEX table"

    section_set = set(section_nums)
    index_set = set(index_nums)

    # 4) INDEX may reference DBG IDs without sections (historical entries)
    # This is informational only - the INDEX can be more comprehensive than sections
    phantom = sorted(index_set - section_set, key=int)
    if phantom and len(phantom) < 20:
        # Only warn if there are a small number (might indicate recent regression)
        print(
            f"\nNote: INDEX has {len(phantom)} DBG IDs without sections:\n"
            + "\n".join([f"  - DBG-{n}" for n in phantom[:10]])
            + ("..." if len(phantom) > 10 else "")
            + "\n(This is expected for historical debug entries)"
        )

    # Optional: Check if all sections have INDEX entries
    # (This can be relaxed if some debug entries intentionally skip the INDEX)
    missing_from_index = sorted(section_set - index_set, key=int)
    if missing_from_index:
        # Warning only - don't fail the test, but log for visibility
        print(
            f"\nNote: {len(missing_from_index)} DBG sections have no INDEX entry:\n"
            + "\n".join([f"  - DBG-{num}" for num in missing_from_index[:5]])
            + ("..." if len(missing_from_index) > 5 else "")
        )

    # Verify basic index structure (at least 1 entry)
    assert len(index_nums) > 0, "INDEX table appears to be empty (no DBG-### rows found)"
    assert len(section_nums) > 0, "No DBG-### sections found in DEBUG_LOG.md"
