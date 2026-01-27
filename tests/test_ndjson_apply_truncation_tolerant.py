import tempfile
from pathlib import Path


def test_ndjson_apply_modify_missing_operations_is_noop():
    from autopack.ndjson_format import NDJSONApplier, NDJSONOperation

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "a.txt").write_text("hello\n", encoding="utf-8")

        applier = NDJSONApplier(workspace=root)
        result = applier.apply(
            [
                NDJSONOperation(
                    op_type="modify",
                    file_path="a.txt",
                    content=None,
                    operations=None,
                    metadata=None,
                ),
            ]
        )

        assert result["failed"] == []
        assert result["applied"] == []
        assert result["skipped"] == ["a.txt"]
        assert (root / "a.txt").read_text(encoding="utf-8") == "hello\n"
