from pathlib import Path

from autopack.structured_edits import (
    EditOperation,
    EditOperationType,
    EditPlan,
    StructuredEditApplicator,
)


def test_structured_edits_allows_creating_new_file_without_context(tmp_path: Path) -> None:
    applicator = StructuredEditApplicator(workspace=tmp_path)

    plan = EditPlan(
        summary="create new file via prepend without context",
        operations=[
            EditOperation(
                type=EditOperationType.PREPEND,
                file_path="docs/new_file.md",
                content="hello\nworld\n",
            )
        ]
    )

    result = applicator.apply_edit_plan(plan=plan, file_contents={}, dry_run=False)

    assert result.success is True
    assert result.operations_applied == 1
    assert (tmp_path / "docs" / "new_file.md").read_text(encoding="utf-8") == "hello\nworld\n"


def test_structured_edits_reads_existing_file_from_disk_when_missing_from_context(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    target = tmp_path / "src" / "example.txt"
    target.write_text("a\nb", encoding="utf-8")

    applicator = StructuredEditApplicator(workspace=tmp_path)
    plan = EditPlan(
        summary="append to existing file read from disk when not in context",
        operations=[
            EditOperation(
                type=EditOperationType.APPEND,
                file_path="src/example.txt",
                content="c\n",
            )
        ]
    )

    result = applicator.apply_edit_plan(plan=plan, file_contents={}, dry_run=False)

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "a\nb\nc"


