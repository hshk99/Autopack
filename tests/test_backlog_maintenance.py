from pathlib import Path

from autopack.backlog_maintenance import (
    parse_backlog_markdown,
    backlog_items_to_phases,
)


def test_parse_backlog_markdown_collects_bullets(tmp_path: Path):
    content = """
# Notes
- Fix YAML schema for packs
  Ensure --- header and required keys.
- Patch apply mismatch
  Rebase patch against latest main
"""
    md = tmp_path / "backlog.md"
    md.write_text(content)

    items = parse_backlog_markdown(md, max_items=5)
    assert len(items) == 2
    assert "Fix YAML" in items[0].title
    assert "Ensure" in items[0].summary


def test_backlog_items_to_phases_has_scope_and_budgets(tmp_path: Path):
    content = "- A sample backlog item\nMore details"
    md = tmp_path / "backlog.md"
    md.write_text(content)
    items = parse_backlog_markdown(md, max_items=1)

    plan = backlog_items_to_phases(items, default_allowed_paths=["src/"], max_commands=5, max_seconds=100)
    assert "phases" in plan
    phase = plan["phases"][0]
    assert phase["task_category"] == "maintenance"
    assert "src/" in phase["scope"]["paths"]
    assert phase["budgets"]["max_commands"] == 5
    assert phase["budgets"]["max_seconds"] == 100

