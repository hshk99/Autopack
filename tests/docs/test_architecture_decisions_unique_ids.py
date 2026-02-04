import re
from pathlib import Path


def _normalize_title(s: str) -> str:
    # Normalize spacing and casing for stable comparisons (INDEX titles may be truncated).
    return re.sub(r"\s+", " ", s).strip().lower()


def test_architecture_decision_ids_are_unique_and_index_matches_sections():
    """
    Guardrail: docs/ARCHITECTURE_DECISIONS.md must not define duplicate DEC-### IDs,
    and the INDEX table must reference the same DEC IDs/titles as the decision sections.

    Current expected formats in ARCHITECTURE_DECISIONS.md:
      - Decision sections: "### DEC-038 | 2026-01-03T21:00 | <title>"
      - INDEX table rows: "| 2026-01-03 | DEC-038 | <decision> | <status> | <impact> |"

    INDEX titles may be truncated; in that case we enforce prefix matching.
    """
    repo_root = Path(__file__).parents[2]
    arch_path = repo_root / "docs" / "ARCHITECTURE_DECISIONS.md"
    content = arch_path.read_text(encoding="utf-8")

    section_re = re.compile(r"^###\s+DEC-(\d{3})\s*\|\s*[^|]+\|\s*(.+?)\s*$")
    index_row_re = re.compile(
        r"^\|\s*\d{4}-\d{2}-\d{2}\s*\|\s*DEC-(\d{3})\s*\|\s*([^|]+?)\s*\|",
    )

    section_titles: dict[str, str] = {}
    index_titles: dict[str, str] = {}

    for line in content.splitlines():
        m = section_re.match(line)
        if m:
            dec_id, title = m.group(1), m.group(2).strip()
            assert dec_id not in section_titles, f"Duplicate DEC section heading for DEC-{dec_id}"
            section_titles[dec_id] = title
            continue

        m = index_row_re.match(line)
        if m:
            dec_id, title = m.group(1), m.group(2).strip()
            assert dec_id not in index_titles, f"Duplicate INDEX table row for DEC-{dec_id}"
            index_titles[dec_id] = title
            continue

    assert section_titles, (
        "No DEC section headings found; expected at least one '### DEC-### | ...'."
    )
    assert index_titles, (
        "No INDEX table rows found; expected at least one '| YYYY-MM-DD | DEC-### | ... |'."
    )

    # INDEX should not reference unknown decisions.
    unknown = sorted(set(index_titles) - set(section_titles))
    assert not unknown, "INDEX references DEC IDs with no corresponding section:\n" + "\n".join(
        [f"DEC-{d}" for d in unknown]
    )

    # For any ID present in both places, titles must be consistent (INDEX may be truncated).
    collisions: list[str] = []
    for dec_id in sorted(set(index_titles) & set(section_titles)):
        idx = _normalize_title(index_titles[dec_id].rstrip("."))
        sec = _normalize_title(section_titles[dec_id])
        if not (sec.startswith(idx) or idx.startswith(sec)):
            collisions.append(
                f"DEC-{dec_id}: INDEX='{index_titles[dec_id]}' vs SECTION='{section_titles[dec_id]}'"
            )

    assert not collisions, "DEC ID/title collisions found:\n" + "\n".join(collisions)
