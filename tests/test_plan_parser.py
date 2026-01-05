from pathlib import Path

from autopack.plan_parser import parse_markdown_plan, phases_to_plan


def test_parse_markdown_basic(tmp_path: Path):
    md = tmp_path / "plan.md"
    md.write_text(
        """- Fix tests [complexity:low] [category:tests] [paths:tests/,src/]
  - ensure pytest passes
  - remove skip
- Update docs [category:docs]
  - add usage examples
""",
        encoding="utf-8",
    )
    phases = parse_markdown_plan(md)
    assert len(phases) == 2
    p1 = phases[0]
    assert p1.complexity == "low"
    assert p1.task_category == "tests"
    assert p1.scope_paths == ["tests/", "src/"]
    assert "ensure pytest passes" in p1.acceptance_criteria[0]


def test_phases_to_plan_structure(tmp_path: Path):
    md = tmp_path / "plan.md"
    md.write_text("- Task one\n  - criterion\n", encoding="utf-8")
    phases = parse_markdown_plan(md)
    plan = phases_to_plan(phases)
    assert "phases" in plan
    assert plan["phases"][0]["id"]
    assert plan["phases"][0]["description"]


def test_merge_plans_allows_update(tmp_path: Path):
    from autopack.plan_utils import merge_plans

    base = {"phases": [{"id": "a", "description": "old"}]}
    new = {"phases": [{"id": "a", "description": "new"}]}
    merged = merge_plans(base, new, allow_update=True)
    assert merged["phases"][0]["description"] == "new"

    merged_no_update = merge_plans(base, new, allow_update=False)
    assert merged_no_update["phases"][0]["description"] == "old"
