"""
Tests for IntentionAnchor storage operations (load/save/update/versioning).

Intention behind these tests: ensure atomic writes, version bumping, and
roundtrip preservation work correctly.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from autopack.intention_anchor import (
    create_anchor,
    get_canonical_path,
    load_anchor,
    save_anchor,
    update_anchor,
)


def test_get_canonical_path():
    """Test canonical path resolution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = get_canonical_path("test-run-001", base_dir=tmpdir)
        expected = Path(tmpdir) / ".autonomous_runs" / "test-run-001" / "intention_anchor.json"
        assert path == expected.resolve()


def test_create_anchor_generates_defaults():
    """create_anchor should generate anchor_id and set version=1."""
    anchor = create_anchor(
        run_id="test-run-001",
        project_id="test-project",
        north_star="Test anchor creation.",
    )

    assert anchor.run_id == "test-run-001"
    assert anchor.project_id == "test-project"
    assert anchor.north_star == "Test anchor creation."
    assert anchor.version == 1
    assert anchor.anchor_id.startswith("IA-")
    assert isinstance(anchor.created_at, datetime)
    assert isinstance(anchor.updated_at, datetime)
    assert anchor.created_at == anchor.updated_at  # Initially same


def test_create_anchor_with_custom_anchor_id():
    """create_anchor should accept a custom anchor_id."""
    anchor = create_anchor(
        run_id="test-run-002",
        project_id="test-project",
        north_star="Custom ID test.",
        anchor_id="IA-custom-123",
    )

    assert anchor.anchor_id == "IA-custom-123"


def test_save_and_load_roundtrip():
    """Save and load should preserve all fields exactly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        anchor = create_anchor(
            run_id="roundtrip-test",
            project_id="test-project",
            north_star="Test roundtrip persistence.",
            success_criteria=["SC1", "SC2"],
        )

        # Save
        saved_path = save_anchor(anchor, base_dir=tmpdir)
        assert saved_path.exists()

        # Load
        loaded = load_anchor("roundtrip-test", base_dir=tmpdir)

        # Verify all fields match
        assert loaded.anchor_id == anchor.anchor_id
        assert loaded.run_id == anchor.run_id
        assert loaded.project_id == anchor.project_id
        assert loaded.version == anchor.version
        assert loaded.north_star == anchor.north_star
        assert loaded.success_criteria == anchor.success_criteria
        assert loaded.created_at == anchor.created_at
        assert loaded.updated_at == anchor.updated_at


def test_save_creates_directory_structure():
    """save_anchor should create parent directories if they don't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        anchor = create_anchor(
            run_id="dir-creation-test",
            project_id="test-project",
            north_star="Test directory creation.",
        )

        saved_path = save_anchor(anchor, base_dir=tmpdir)
        assert saved_path.exists()
        assert saved_path.parent.exists()
        assert saved_path.parent.parent.name == ".autonomous_runs"


def test_save_is_atomic():
    """save_anchor should use atomic write (temp → replace)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        anchor = create_anchor(
            run_id="atomic-test",
            project_id="test-project",
            north_star="Test atomic write.",
        )

        saved_path = save_anchor(anchor, base_dir=tmpdir)

        # Temp file should not exist after save
        temp_path = saved_path.with_suffix(".tmp")
        assert not temp_path.exists()

        # Final file should exist
        assert saved_path.exists()


def test_load_nonexistent_anchor_raises():
    """load_anchor should raise FileNotFoundError if anchor doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(FileNotFoundError) as exc_info:
            load_anchor("nonexistent-run", base_dir=tmpdir)

        assert "not found" in str(exc_info.value).lower()


def test_load_malformed_anchor_raises():
    """load_anchor should raise ValueError if JSON is malformed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a malformed JSON file
        path = get_canonical_path("malformed-test", base_dir=tmpdir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ invalid json }", encoding="utf-8")

        with pytest.raises((json.JSONDecodeError, ValueError)):
            load_anchor("malformed-test", base_dir=tmpdir)


def test_update_anchor_increments_version():
    """update_anchor should increment version and update timestamp."""
    anchor = create_anchor(
        run_id="version-test",
        project_id="test-project",
        north_star="Test version increment.",
    )

    original_version = anchor.version
    original_updated_at = anchor.updated_at

    # Small delay to ensure timestamp changes
    import time

    time.sleep(0.01)

    updated = update_anchor(anchor)

    assert updated.version == original_version + 1
    assert updated.updated_at > original_updated_at
    assert updated.created_at == anchor.created_at  # created_at should not change
    assert updated.anchor_id == anchor.anchor_id


def test_update_anchor_preserves_other_fields():
    """update_anchor should preserve all other fields."""
    anchor = create_anchor(
        run_id="preserve-test",
        project_id="test-project",
        north_star="Test field preservation.",
        success_criteria=["SC1", "SC2", "SC3"],
    )

    updated = update_anchor(anchor)

    assert updated.run_id == anchor.run_id
    assert updated.project_id == anchor.project_id
    assert updated.north_star == anchor.north_star
    assert updated.success_criteria == anchor.success_criteria
    assert updated.anchor_id == anchor.anchor_id


def test_update_anchor_with_save():
    """update_anchor with save=True should persist immediately."""
    with tempfile.TemporaryDirectory() as tmpdir:
        anchor = create_anchor(
            run_id="update-save-test",
            project_id="test-project",
            north_star="Test update with save.",
        )

        # Save original
        save_anchor(anchor, base_dir=tmpdir)

        # Update with save
        import time

        time.sleep(0.01)
        updated = update_anchor(anchor, save=True, base_dir=tmpdir)

        # Load from disk
        loaded = load_anchor("update-save-test", base_dir=tmpdir)

        assert loaded.version == updated.version
        assert loaded.version == anchor.version + 1


def test_multiple_updates_increment_correctly():
    """Multiple updates should increment version sequentially."""
    anchor = create_anchor(
        run_id="multi-update-test",
        project_id="test-project",
        north_star="Test multiple updates.",
    )

    assert anchor.version == 1

    updated1 = update_anchor(anchor)
    assert updated1.version == 2

    updated2 = update_anchor(updated1)
    assert updated2.version == 3

    updated3 = update_anchor(updated2)
    assert updated3.version == 4


def test_save_preserves_json_structure():
    """Saved JSON should be well-formatted and complete."""
    with tempfile.TemporaryDirectory() as tmpdir:
        anchor = create_anchor(
            run_id="json-structure-test",
            project_id="test-project",
            north_star="Test JSON structure.",
            success_criteria=["SC1", "SC2"],
        )

        saved_path = save_anchor(anchor, base_dir=tmpdir)
        raw_json = saved_path.read_text(encoding="utf-8")
        parsed = json.loads(raw_json)

        # Verify all top-level keys are present
        assert "anchor_id" in parsed
        assert "run_id" in parsed
        assert "project_id" in parsed
        assert "created_at" in parsed
        assert "updated_at" in parsed
        assert "version" in parsed
        assert "north_star" in parsed
        assert "success_criteria" in parsed
        assert "constraints" in parsed
        assert "scope" in parsed
        assert "budgets" in parsed
        assert "risk_profile" in parsed


def test_canonical_path_is_stable():
    """Canonical path should be deterministic for the same run_id."""
    path1 = get_canonical_path("stable-run", base_dir="/tmp")
    path2 = get_canonical_path("stable-run", base_dir="/tmp")
    assert path1 == path2
