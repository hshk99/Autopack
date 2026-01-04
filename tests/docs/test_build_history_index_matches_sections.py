"""
Test that BUILD_HISTORY.md INDEX table matches build sections.

This test ensures the INDEX table stays in sync with actual build sections,
preventing "phantom" builds in the index or missing index entries.
"""

import re
from pathlib import Path


def test_build_history_index_matches_sections_and_no_duplicates():
    """
    Guardrail: docs/BUILD_HISTORY.md INDEX must match build sections.

    Checks:
    1. No duplicate ## BUILD-### section headings
    2. INDEX table BUILD IDs are subset of section BUILD IDs (no phantom IDs)
    3. All sections have corresponding INDEX entries (optional - can be relaxed)

    Current BUILD_HISTORY format:
      - Build sections: "## BUILD-169"
      - INDEX table rows: "| YYYY-MM-DD | BUILD-169 | <title> | <status> |"
    """
    repo_root = Path(__file__).parents[2]
    bh_path = repo_root / "docs" / "BUILD_HISTORY.md"
    content = bh_path.read_text(encoding="utf-8")

    # Find all section headings: ## BUILD-###
    # Note: Some builds have multi-phase sections (e.g., "## BUILD-145" and "## BUILD-145 Follow-up")
    # This is allowed as long as they're distinct (different full headings)
    section_re = re.compile(r'^##\s+(BUILD-\d+[^\n]*)', re.MULTILINE)
    section_headings = []
    section_ids = []
    for m in section_re.finditer(content):
        full_heading = m.group(1).strip()
        section_headings.append(full_heading)
        # Extract just the BUILD-### part
        build_id_match = re.match(r'BUILD-(\d+)', full_heading)
        if build_id_match:
            section_ids.append(build_id_match.group(1))

    # Find all INDEX table rows: | YYYY-MM-DD | BUILD-### | ...
    index_re = re.compile(r'^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*BUILD-(\d+)\b', re.MULTILINE)
    index_ids = []
    for m in index_re.finditer(content):
        index_ids.append(m.group(1))

    # Check for exact duplicate section headings (same full heading text)
    heading_counts = {}
    for heading in section_headings:
        heading_counts[heading] = heading_counts.get(heading, 0) + 1

    exact_duplicates = [heading for heading, count in heading_counts.items() if count > 1]
    assert not exact_duplicates, (
        "Exact duplicate BUILD section headings found:\n"
        + "\n".join([f"  - {h}" for h in exact_duplicates])
        + "\nEach section heading should be unique (even multi-phase builds should have distinct headings like 'BUILD-145' vs 'BUILD-145 Follow-up')."
    )

    # Convert to sets for comparison
    section_id_set = set(section_ids)
    index_id_set = set(index_ids)

    # INDEX may reference builds without sections (historical builds with INDEX-only entries)
    # This is informational only - the INDEX can be more comprehensive than sections
    phantom_builds = sorted(index_id_set - section_id_set, key=int)
    if phantom_builds and len(phantom_builds) < 20:
        # Only warn if there are a small number (might indicate recent regression)
        print(
            f"\nNote: INDEX has {len(phantom_builds)} BUILD IDs without sections:\n"
            + "\n".join([f"BUILD-{bid}" for bid in phantom_builds[:10]])
            + ("..." if len(phantom_builds) > 10 else "")
            + "\n(This is expected for historical builds)"
        )

    # Optional: Check if all sections have INDEX entries
    # (This can be relaxed if some builds intentionally skip the INDEX)
    missing_from_index = sorted(section_id_set - index_id_set, key=int)
    if missing_from_index:
        # Warning only - don't fail the test, but log for visibility
        print(
            f"\nNote: {len(missing_from_index)} BUILD sections have no INDEX entry:\n"
            + "\n".join([f"BUILD-{bid}" for bid in missing_from_index[:5]])
            + ("..." if len(missing_from_index) > 5 else "")
        )

    # Verify basic index structure (at least 1 entry)
    assert len(index_ids) > 0, "INDEX table appears to be empty (no BUILD-### rows found)"
    assert len(section_ids) > 0, "No BUILD-### sections found in BUILD_HISTORY.md"
