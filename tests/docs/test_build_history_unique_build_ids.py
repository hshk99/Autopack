"""
Contract Test: BUILD_HISTORY.md Build ID Uniqueness

Guardrail: docs/BUILD_HISTORY.md must not define duplicate BUILD-### IDs.

Why This Matters:
- BUILD IDs are stable references (used in docs, commit messages, cross-references)
- Duplicate IDs → ambiguity (which BUILD-157 do you mean?)
- INDEX table must match section headings (navigation integrity)

Coverage:
- No duplicate BUILD IDs in INDEX table (with multi-row entry support)
- No duplicate BUILD IDs in section headings
- INDEX BUILD IDs are subset of section BUILD IDs (optional, for future)
"""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IndexEntry:
    """Represents a single BUILD entry from the INDEX table."""

    build_id: str
    date: str
    title: str
    # Note: description omitted since it can span multiple rows


def _extract_index_entries(content: str) -> list[IndexEntry]:
    """
    Extract INDEX table entries with multi-row support.

    Multi-row entries have the BUILD ID in the first row, then subsequent rows
    with empty BUILD ID cells that continue the previous entry's description.

    Returns:
        List of IndexEntry objects (one per unique BUILD ID)
    """
    # Locate the INDEX table section
    index_start = content.find("## INDEX")
    if index_start == -1:
        return []

    # Find the table header row (starts with |)
    table_start = content.find("|", index_start)
    if table_start == -1:
        return []

    # Extract lines until we hit a non-table line
    lines = content[table_start:].split("\n")
    table_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            break
        table_lines.append(stripped)

    if len(table_lines) < 3:  # Need header + separator + at least one data row
        return []

    # Skip header and separator rows
    data_rows = table_lines[2:]

    entries = []
    for row in data_rows:
        # Split on | and strip whitespace
        cells = [cell.strip() for cell in row.split("|")]
        if len(cells) < 4:  # Need at least: empty, date, build_id, title, ...
            continue

        # cells[0] is empty (before first |)
        # cells[1] is date
        # cells[2] is build_id (may be empty for continuation rows)
        # cells[3] is title
        date = cells[1] if len(cells) > 1 else ""
        build_id = cells[2] if len(cells) > 2 else ""
        title = cells[3] if len(cells) > 3 else ""

        # Only process rows with a BUILD ID (ignore continuation rows)
        if build_id and re.match(r"BUILD-\d+(\.\d+)?", build_id):
            entries.append(
                IndexEntry(build_id=build_id, date=date, title=title.split("|")[0].strip())
            )

    return entries


def test_build_history_index_build_ids_are_unique():
    """
    Guardrail: docs/BUILD_HISTORY.md INDEX table must not contain duplicate BUILD IDs.

    This test implements multi-row INDEX parsing to correctly handle entries that
    span multiple table rows (where continuation rows have empty BUILD ID cells).
    """
    repo_root = Path(__file__).parents[2]
    build_path = repo_root / "docs" / "BUILD_HISTORY.md"
    content = build_path.read_text(encoding="utf-8")

    entries = _extract_index_entries(content)

    # Enforce uniqueness
    seen = {}
    for entry in entries:
        assert entry.build_id not in seen, (
            f"Duplicate BUILD ID in INDEX table: {entry.build_id}\n"
            f"First occurrence: {seen[entry.build_id]}\n"
            f"Duplicate: {entry.title}\n"
            f"Build IDs must be unique across all INDEX entries."
        )
        seen[entry.build_id] = entry.title

    assert entries, (
        "No INDEX entries found; expected at least one BUILD-### entry.\n"
        "This may indicate a parsing issue or empty BUILD_HISTORY.md INDEX table"
    )


def test_build_history_section_build_ids_are_unique():
    """
    Guardrail: docs/BUILD_HISTORY.md section headings must not contain duplicate BUILD IDs.

    Section headings use format: ## BUILD-### | Title
    or ## BUILD-###.# | Title (for sub-builds)
    """
    repo_root = Path(__file__).parents[2]
    build_path = repo_root / "docs" / "BUILD_HISTORY.md"
    content = build_path.read_text(encoding="utf-8")

    # Match BUILD section headings: "## BUILD-### | ..." or "## BUILD-###.# | ..."
    section_re = re.compile(r"^##\s+(BUILD-\d+(?:\.\d+)?)\s*[|:]", re.MULTILINE)

    seen = {}
    for match in section_re.finditer(content):
        build_id = match.group(1)
        # Extract title (everything after BUILD-### |)
        line_end = content.find("\n", match.end())
        title = content[match.end() : line_end].strip() if line_end != -1 else ""

        assert build_id not in seen, (
            f"Duplicate BUILD section heading for {build_id}\n"
            f"First occurrence: {seen[build_id]}\n"
            f"Duplicate: {title}\n"
            f"Build IDs must be unique across all sections."
        )
        seen[build_id] = title

    assert seen, (
        "No BUILD section headings found; expected at least one '## BUILD-### | ...'.\n"
        "This may indicate a parsing issue or empty BUILD_HISTORY.md"
    )
