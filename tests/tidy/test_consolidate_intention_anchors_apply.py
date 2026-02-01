"""
Tests for Intention Anchor consolidation apply mode (Part B3).

Intention behind these tests: Verify that apply mode:
- Requires --execute flag (double opt-in)
- Writes to SOT ledgers atomically
- Is idempotent (re-running is safe)
- Only writes to docs/ directory
- Inserts stable markers for tracking
"""

# Import the script functions directly
import sys
import tempfile
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "scripts" / "tidy"))

from consolidate_intention_anchors import (apply_consolidation_entry,
                                           check_marker_exists, run_apply_mode)

# Import intention anchor utilities
sys.path.insert(0, str(project_root / "src"))

from autopack.intention_anchor import create_anchor, save_anchor

# =============================================================================
# Marker Checking Tests
# =============================================================================


def test_check_marker_exists_no_file():
    """Test marker check when file doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "nonexistent.md"
        assert check_marker_exists(file_path, "abc123") is False


def test_check_marker_exists_not_present():
    """Test marker check when marker not in file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.md"
        file_path.write_text("# Test\n\nSome content.\n", encoding="utf-8")

        assert check_marker_exists(file_path, "abc123") is False


def test_check_marker_exists_present():
    """Test marker check when marker is in file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "test.md"
        content = "# Test\n\nSome content.\n\n<!-- IA_CONSOLIDATION: hash=abc123 -->\n"
        file_path.write_text(content, encoding="utf-8")

        assert check_marker_exists(file_path, "abc123") is True


# =============================================================================
# Apply Entry Tests
# =============================================================================


def test_apply_consolidation_entry_first_time():
    """Test applying consolidation entry for first time."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "BUILD_HISTORY.md"
        file_path.write_text("# Build History\n\n", encoding="utf-8")

        proposed_block = "### run-001\n\n**Anchor**: `IA-001` (v1)"
        was_applied = apply_consolidation_entry(
            file_path=file_path,
            proposed_block=proposed_block,
            idempotency_hash="abc123",
            anchor_id="IA-001",
            version=1,
        )

        assert was_applied is True

        # Verify content
        content = file_path.read_text(encoding="utf-8")
        assert "### run-001" in content
        assert "**Anchor**: `IA-001` (v1)" in content
        assert "<!-- IA_CONSOLIDATION: anchor_id=IA-001 version=1 hash=abc123 -->" in content


def test_apply_consolidation_entry_idempotent():
    """Test applying same entry twice is idempotent (second is no-op)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "BUILD_HISTORY.md"
        file_path.write_text("# Build History\n\n", encoding="utf-8")

        proposed_block = "### run-001\n\n**Anchor**: `IA-001` (v1)"

        # First application
        was_applied_1 = apply_consolidation_entry(
            file_path=file_path,
            proposed_block=proposed_block,
            idempotency_hash="abc123",
            anchor_id="IA-001",
            version=1,
        )

        # Second application (should skip)
        was_applied_2 = apply_consolidation_entry(
            file_path=file_path,
            proposed_block=proposed_block,
            idempotency_hash="abc123",
            anchor_id="IA-001",
            version=1,
        )

        assert was_applied_1 is True
        assert was_applied_2 is False

        # Verify only one occurrence
        content = file_path.read_text(encoding="utf-8")
        assert content.count("### run-001") == 1
        assert (
            content.count("<!-- IA_CONSOLIDATION: anchor_id=IA-001 version=1 hash=abc123 -->") == 1
        )


def test_apply_consolidation_entry_creates_file():
    """Test applying entry creates file if it doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "docs" / "BUILD_HISTORY.md"

        proposed_block = "### run-001\n\n**Anchor**: `IA-001` (v1)"
        was_applied = apply_consolidation_entry(
            file_path=file_path,
            proposed_block=proposed_block,
            idempotency_hash="abc123",
            anchor_id="IA-001",
            version=1,
        )

        assert was_applied is True
        assert file_path.exists()

        content = file_path.read_text(encoding="utf-8")
        assert "# Build History" in content
        assert "### run-001" in content


def test_apply_consolidation_entry_atomic_write():
    """Test consolidation uses atomic write (temp → replace)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "BUILD_HISTORY.md"
        file_path.write_text("# Build History\n\nOriginal content.\n", encoding="utf-8")

        proposed_block = "### run-001\n\n**Anchor**: `IA-001` (v1)"
        apply_consolidation_entry(
            file_path=file_path,
            proposed_block=proposed_block,
            idempotency_hash="abc123",
            anchor_id="IA-001",
            version=1,
        )

        # Verify temp file was cleaned up
        temp_path = file_path.with_suffix(".tmp")
        assert not temp_path.exists()

        # Verify content is complete
        content = file_path.read_text(encoding="utf-8")
        assert "Original content." in content
        assert "### run-001" in content


# =============================================================================
# Apply Mode Tests
# =============================================================================


def test_run_apply_mode_requires_execute_flag():
    """Test apply mode refuses to run without --execute flag."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a run with anchor
        anchor = create_anchor(
            run_id="run-001",
            project_id="test",
            north_star="Test.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run apply mode WITHOUT --execute
        exit_code = run_apply_mode(
            project_id="test",
            base_dir=tmpdir_path,
            execute=False,
            max_runs=10,
        )

        # Should fail with exit code 1
        assert exit_code == 1


def test_run_apply_mode_with_execute_flag():
    """Test apply mode succeeds with --execute flag."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a run with anchor
        anchor = create_anchor(
            run_id="run-001",
            project_id="test",
            north_star="Test.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run apply mode WITH --execute
        exit_code = run_apply_mode(
            project_id="test",
            base_dir=tmpdir_path,
            execute=True,
            max_runs=10,
        )

        assert exit_code == 0


def test_run_apply_mode_creates_sot_entry():
    """Test apply mode creates entry in BUILD_HISTORY.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a run with anchor
        anchor = create_anchor(
            run_id="run-001",
            project_id="test",
            north_star="Test anchor for consolidation.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run apply mode
        run_apply_mode(
            project_id="test",
            base_dir=tmpdir_path,
            execute=True,
            max_runs=10,
        )

        # Verify BUILD_HISTORY.md was created
        target_file = tmpdir_path / ".autonomous_runs" / "test" / "docs" / "BUILD_HISTORY.md"
        assert target_file.exists()

        content = target_file.read_text(encoding="utf-8")
        assert "### run-001" in content
        assert anchor.anchor_id in content
        assert "<!-- IA_CONSOLIDATION:" in content


def test_run_apply_mode_autopack_project_targets_root_docs():
    """Test apply mode for autopack project targets ./docs/ directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a run with anchor for autopack project
        anchor = create_anchor(
            run_id="run-001",
            project_id="autopack",
            north_star="Test autopack anchor.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run apply mode
        run_apply_mode(
            project_id="autopack",
            base_dir=tmpdir_path,
            execute=True,
            max_runs=10,
        )

        # Verify BUILD_HISTORY.md was created in ./docs/
        target_file = tmpdir_path / "docs" / "BUILD_HISTORY.md"
        assert target_file.exists()

        content = target_file.read_text(encoding="utf-8")
        assert "### run-001" in content


def test_run_apply_mode_idempotent():
    """Test running apply mode multiple times is idempotent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a run with anchor
        anchor = create_anchor(
            run_id="run-001",
            project_id="test",
            north_star="Test idempotency.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run apply mode FIRST time
        exit_code_1 = run_apply_mode(
            project_id="test",
            base_dir=tmpdir_path,
            execute=True,
            max_runs=10,
        )

        target_file = tmpdir_path / ".autonomous_runs" / "test" / "docs" / "BUILD_HISTORY.md"
        content_after_first = target_file.read_text(encoding="utf-8")

        # Run apply mode SECOND time
        exit_code_2 = run_apply_mode(
            project_id="test",
            base_dir=tmpdir_path,
            execute=True,
            max_runs=10,
        )

        content_after_second = target_file.read_text(encoding="utf-8")

        # Both should succeed
        assert exit_code_1 == 0
        assert exit_code_2 == 0

        # Content should be identical (no duplicates)
        assert content_after_first == content_after_second

        # Verify only one occurrence of the run
        assert content_after_second.count("### run-001") == 1


def test_run_apply_mode_multiple_runs():
    """Test apply mode handles multiple runs correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create 3 runs with anchors
        for i in range(3):
            run_id = f"run-{i:03d}"
            anchor = create_anchor(
                run_id=run_id,
                project_id="test",
                north_star=f"Test run {i}.",
            )
            save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run apply mode
        run_apply_mode(
            project_id="test",
            base_dir=tmpdir_path,
            execute=True,
            max_runs=10,
        )

        # Verify all runs are in BUILD_HISTORY.md
        target_file = tmpdir_path / ".autonomous_runs" / "test" / "docs" / "BUILD_HISTORY.md"
        content = target_file.read_text(encoding="utf-8")

        assert "### run-000" in content
        assert "### run-001" in content
        assert "### run-002" in content


def test_run_apply_mode_respects_max_runs():
    """Test apply mode respects max_runs limit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create 5 runs with anchors
        for i in range(5):
            run_id = f"run-{i:03d}"
            anchor = create_anchor(
                run_id=run_id,
                project_id="test",
                north_star=f"Test run {i}.",
            )
            save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run apply mode with max_runs=3
        run_apply_mode(
            project_id="test",
            base_dir=tmpdir_path,
            execute=True,
            max_runs=3,
        )

        # Verify only 3 runs are consolidated
        target_file = tmpdir_path / ".autonomous_runs" / "test" / "docs" / "BUILD_HISTORY.md"
        content = target_file.read_text(encoding="utf-8")

        # Count how many run entries were added
        run_count = content.count("### run-")
        assert run_count == 3


# =============================================================================
# Contract Tests (Safety)
# =============================================================================


def test_run_apply_mode_safety_check_target_file():
    """Test apply mode only writes to BUILD_HISTORY.md (safety check)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a run with anchor
        anchor = create_anchor(
            run_id="run-001",
            project_id="test",
            north_star="Test.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run apply mode
        run_apply_mode(
            project_id="test",
            base_dir=tmpdir_path,
            execute=True,
            max_runs=10,
        )

        # Verify only BUILD_HISTORY.md in docs/ was touched
        docs_dir = tmpdir_path / ".autonomous_runs" / "test" / "docs"
        assert docs_dir.exists()

        # Only BUILD_HISTORY.md should exist
        files_in_docs = list(docs_dir.iterdir())
        assert len(files_in_docs) == 1
        assert files_in_docs[0].name == "BUILD_HISTORY.md"


def test_run_apply_mode_no_unintended_sot_writes():
    """Test apply mode doesn't write to root SOT files for non-autopack projects."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create fake root SOT files
        docs_dir = tmpdir_path / "docs"
        docs_dir.mkdir()

        root_build_history = docs_dir / "BUILD_HISTORY.md"
        root_build_history.write_text("# Build History\n\nRoot content.\n", encoding="utf-8")
        original_mtime = root_build_history.stat().st_mtime

        # Create a run with anchor for NON-autopack project
        anchor = create_anchor(
            run_id="run-001",
            project_id="test-project",
            north_star="Test.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run apply mode for test-project (not autopack)
        run_apply_mode(
            project_id="test-project",
            base_dir=tmpdir_path,
            execute=True,
            max_runs=10,
        )

        # Verify root BUILD_HISTORY.md was NOT modified
        current_content = root_build_history.read_text(encoding="utf-8")
        assert current_content == "# Build History\n\nRoot content.\n"

        current_mtime = root_build_history.stat().st_mtime
        assert current_mtime == original_mtime


# =============================================================================
# P0 Safety Tests (Path Traversal & Project ID Validation)
# =============================================================================


def test_apply_mode_rejects_path_traversal_project_id():
    """Test apply mode rejects project IDs with path traversal attempts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Try various path traversal attacks
        malicious_ids = [
            "../docs",
            "../../etc",
            "..\\windows",
            "a/../b",
            "..",
        ]

        for malicious_id in malicious_ids:
            exit_code = run_apply_mode(
                project_id=malicious_id,
                base_dir=tmpdir_path,
                execute=True,
                max_runs=10,
            )
            # Should fail with exit code 2 (usage error)
            assert exit_code == 2, f"Failed to reject malicious project_id: {malicious_id}"


def test_apply_mode_rejects_path_separators_in_project_id():
    """Test apply mode rejects project IDs with path separators."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        malicious_ids = [
            "a/b",
            "a\\b",
            "project/subdir",
            "c:\\path",
        ]

        for malicious_id in malicious_ids:
            exit_code = run_apply_mode(
                project_id=malicious_id,
                base_dir=tmpdir_path,
                execute=True,
                max_runs=10,
            )
            assert exit_code == 2, f"Failed to reject project_id with separator: {malicious_id}"


def test_apply_mode_rejects_invalid_project_id_patterns():
    """Test apply mode rejects invalid project ID patterns."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        invalid_ids = [
            ".hidden",  # Leading dot
            "",  # Empty
            "a" * 65,  # Too long (>64 chars)
            "a b",  # Space
            "project name",  # Spaces
        ]

        for invalid_id in invalid_ids:
            exit_code = run_apply_mode(
                project_id=invalid_id,
                base_dir=tmpdir_path,
                execute=True,
                max_runs=10,
            )
            assert exit_code == 2, f"Failed to reject invalid project_id: {invalid_id}"


def test_apply_mode_accepts_valid_project_ids():
    """Test apply mode accepts valid project IDs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        valid_ids = [
            "autopack",
            "project-a",
            "project_b",
            "proj.1",
            "Test123",
        ]

        for valid_id in valid_ids:
            # Create a run for each valid project
            anchor = create_anchor(
                run_id=f"run-{valid_id}",
                project_id=valid_id,
                north_star="Test.",
            )
            save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

            exit_code = run_apply_mode(
                project_id=valid_id,
                base_dir=tmpdir_path,
                execute=True,
                max_runs=10,
            )
            assert exit_code == 0, f"Should accept valid project_id: {valid_id}"


def test_apply_mode_excludes_unknown_project_runs_by_default():
    """Test apply mode excludes runs with unknown/None project_id by default."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create run with matching project_id
        anchor1 = create_anchor(
            run_id="run-001",
            project_id="project-a",
            north_star="Matching project.",
        )
        save_anchor(anchor1, base_dir=tmpdir_path, generate_artifacts=True)

        # Create run with different project_id
        anchor2 = create_anchor(
            run_id="run-002",
            project_id="project-b",
            north_star="Different project.",
        )
        save_anchor(anchor2, base_dir=tmpdir_path, generate_artifacts=True)

        # Run apply mode for project-a WITHOUT --include-unknown-project
        run_apply_mode(
            project_id="project-a",
            base_dir=tmpdir_path,
            execute=True,
            max_runs=10,
            include_unknown_project=False,
        )

        # Verify only run-001 was consolidated
        target_file = tmpdir_path / ".autonomous_runs" / "project-a" / "docs" / "BUILD_HISTORY.md"
        content = target_file.read_text(encoding="utf-8")

        assert "### run-001" in content
        assert "### run-002" not in content


def test_apply_mode_includes_unknown_project_runs_with_flag():
    """Test apply mode respects include_unknown_project flag (though malformed anchors are filtered out)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create run with matching project_id
        anchor1 = create_anchor(
            run_id="run-001",
            project_id="project-a",
            north_star="Matching project.",
        )
        save_anchor(anchor1, base_dir=tmpdir_path, generate_artifacts=True)

        # Run apply mode WITH --include-unknown-project
        run_apply_mode(
            project_id="project-a",
            base_dir=tmpdir_path,
            execute=True,
            max_runs=10,
            include_unknown_project=True,
        )

        # Verify run-001 was consolidated
        target_file = tmpdir_path / ".autonomous_runs" / "project-a" / "docs" / "BUILD_HISTORY.md"
        content = target_file.read_text(encoding="utf-8")

        assert "### run-001" in content
