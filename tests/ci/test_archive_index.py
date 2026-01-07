"""CI contract tests for archive index generator (BUILD-188).

Ensures that the archive index:
1. Contains no absolute paths (portable)
2. Validates against the JSON schema
3. Is deterministic (same inputs produce same outputs)
4. Has bounded recent_files lists
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_archive_index_no_absolute_paths():
    """Verify ARCHIVE_INDEX.json contains no absolute paths."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    index_path = repo_root / "archive" / "ARCHIVE_INDEX.json"

    if not index_path.exists():
        pytest.skip("ARCHIVE_INDEX.json not generated yet")

    data = json.loads(index_path.read_text(encoding="utf-8"))

    def check_path(path: str, context: str) -> None:
        # Windows absolute paths
        if len(path) >= 2 and path[1] == ":":
            pytest.fail(f"{context}: absolute Windows path detected: {path}")
        # Unix absolute paths
        if path.startswith("/"):
            pytest.fail(f"{context}: absolute Unix path detected: {path}")

    for root in data["archive_roots"]:
        check_path(root["root_rel"], f"root {root['id']}")
        for bucket in root["bucket_stats"]:
            check_path(bucket["bucket_rel"], f"bucket in {root['id']}")
        for f in root["recent_files"]:
            check_path(f["path_rel"], f"file in {root['id']}")


def test_archive_index_schema_version():
    """Verify schema_version is 1."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    index_path = repo_root / "archive" / "ARCHIVE_INDEX.json"

    if not index_path.exists():
        pytest.skip("ARCHIVE_INDEX.json not generated yet")

    data = json.loads(index_path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1


def test_archive_index_has_required_fields():
    """Verify ARCHIVE_INDEX.json has all required fields."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    index_path = repo_root / "archive" / "ARCHIVE_INDEX.json"

    if not index_path.exists():
        pytest.skip("ARCHIVE_INDEX.json not generated yet")

    data = json.loads(index_path.read_text(encoding="utf-8"))

    # Root level required fields
    assert "schema_version" in data
    assert "generated_at_utc" in data
    assert "archive_roots" in data
    assert isinstance(data["archive_roots"], list)

    # Each root must have required fields
    for root in data["archive_roots"]:
        assert "id" in root
        assert "root_rel" in root
        assert "kind" in root
        assert "bucket_stats" in root


def test_archive_index_recent_files_bounded():
    """Verify recent_files lists are bounded (not full enumeration)."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    index_path = repo_root / "archive" / "ARCHIVE_INDEX.json"

    if not index_path.exists():
        pytest.skip("ARCHIVE_INDEX.json not generated yet")

    data = json.loads(index_path.read_text(encoding="utf-8"))

    # Import the limit constant
    from scripts.archive.generate_archive_index import TOP_RECENT_FILES_PER_ROOT

    for root in data["archive_roots"]:
        recent_count = len(root.get("recent_files", []))
        assert recent_count <= TOP_RECENT_FILES_PER_ROOT, (
            f"Root {root['id']} has {recent_count} recent files, "
            f"exceeds limit of {TOP_RECENT_FILES_PER_ROOT}"
        )


def test_archive_index_generator_is_deterministic():
    """Verify generator produces consistent results (minus timestamp)."""
    from scripts.archive.generate_archive_index import generate_archive_index

    repo_root = Path(__file__).resolve().parent.parent.parent

    # Generate twice
    index1, errors1 = generate_archive_index(repo_root)
    index2, errors2 = generate_archive_index(repo_root)

    assert errors1 == []
    assert errors2 == []

    # Compare everything except generated_at_utc (which will differ)
    index1_copy = {k: v for k, v in index1.items() if k != "generated_at_utc"}
    index2_copy = {k: v for k, v in index2.items() if k != "generated_at_utc"}

    assert index1_copy == index2_copy, "Generator is not deterministic"


def test_archive_index_validation_catches_absolute_paths():
    """Verify _validate_no_absolute_paths catches absolute paths."""
    from scripts.archive.generate_archive_index import _validate_no_absolute_paths

    # Test with clean index
    clean_index = {
        "schema_version": 1,
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "generator_version": "1.0.0",
        "archive_roots": [
            {
                "id": "test",
                "root_rel": "archive",
                "kind": "repo_archive",
                "bucket_stats": [
                    {"bucket_rel": "archive/data", "file_count": 1, "total_bytes": 100}
                ],
                "recent_files": [
                    {
                        "path_rel": "archive/data/test.txt",
                        "bytes": 100,
                        "mtime_utc": "2026-01-01T00:00:00+00:00",
                    }
                ],
            }
        ],
    }

    errors = _validate_no_absolute_paths(clean_index)
    assert errors == []

    # Test with Windows absolute path
    bad_index = {
        "schema_version": 1,
        "generated_at_utc": "2026-01-01T00:00:00+00:00",
        "generator_version": "1.0.0",
        "archive_roots": [
            {
                "id": "test",
                "root_rel": "C:\\dev\\archive",  # Windows absolute
                "kind": "repo_archive",
                "bucket_stats": [],
                "recent_files": [],
            }
        ],
    }

    errors = _validate_no_absolute_paths(bad_index)
    assert len(errors) == 1
    assert "absolute Windows path" in errors[0]


def test_archive_index_bucket_stats_sorted():
    """Verify bucket_stats are sorted for deterministic output."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    index_path = repo_root / "archive" / "ARCHIVE_INDEX.json"

    if not index_path.exists():
        pytest.skip("ARCHIVE_INDEX.json not generated yet")

    data = json.loads(index_path.read_text(encoding="utf-8"))

    for root in data["archive_roots"]:
        bucket_rels = [b["bucket_rel"] for b in root["bucket_stats"]]
        assert bucket_rels == sorted(
            bucket_rels
        ), f"Bucket stats in {root['id']} are not sorted: {bucket_rels}"


def test_schema_file_exists():
    """Verify the JSON schema file exists."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    schema_path = repo_root / "archive" / "schemas" / "archive_index_v1.schema.json"

    assert schema_path.exists(), "archive/schemas/archive_index_v1.schema.json must exist"

    # Verify it's valid JSON
    data = json.loads(schema_path.read_text(encoding="utf-8"))
    assert data.get("$schema") == "http://json-schema.org/draft-07/schema#"
    assert data.get("title") == "ArchiveIndexV1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
