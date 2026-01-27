"""
Tests for Intention Anchor consolidation report mode (Part B1).

Intention behind these tests: Verify that report mode produces deterministic,
stable output and NEVER writes to SOT ledgers.
"""

import json
import tempfile
from pathlib import Path

# Import the script functions directly
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "scripts" / "tidy"))

from consolidate_intention_anchors import (
    analyze_anchor_artifacts,
    find_runs_with_anchors,
    generate_report_json,
    generate_report_markdown,
    run_report_mode,
)

# Import intention anchor utilities
sys.path.insert(0, str(project_root / "src"))

from autopack.intention_anchor import create_anchor, save_anchor

# =============================================================================
# Discovery Tests
# =============================================================================


def test_find_runs_with_anchors_empty():
    """Test finding runs when none exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        run_ids = find_runs_with_anchors(tmpdir_path)
        assert run_ids == []


def test_find_runs_with_anchors_multiple():
    """Test finding multiple runs with anchors (sorted)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create multiple runs (in non-sorted order)
        run_ids_created = ["run-003", "run-001", "run-002"]
        for run_id in run_ids_created:
            anchor = create_anchor(
                run_id=run_id,
                project_id="test",
                north_star="Test anchor.",
            )
            save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=False)

        # Find runs
        found_runs = find_runs_with_anchors(tmpdir_path)

        # Should be sorted
        assert found_runs == ["run-001", "run-002", "run-003"]


# =============================================================================
# Analysis Tests
# =============================================================================


def test_analyze_anchor_artifacts_complete():
    """Test analyzing run with complete artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        anchor = create_anchor(
            run_id="test-run-001",
            project_id="test-project",
            north_star="Complete artifacts test.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        analysis = analyze_anchor_artifacts("test-run-001", base_dir=tmpdir_path)

        assert analysis["run_id"] == "test-run-001"
        assert analysis["project_id"] == "test-project"
        assert analysis["anchor_id"] == anchor.anchor_id
        assert analysis["version"] == 1
        assert analysis["has_anchor"] is True
        assert analysis["has_summary"] is True
        assert analysis["has_events"] is True
        assert analysis["event_count"] >= 1  # At least the created event


def test_analyze_anchor_artifacts_incomplete():
    """Test analyzing run with missing artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        anchor = create_anchor(
            run_id="test-run-002",
            project_id="test-project",
            north_star="Incomplete test.",
        )
        # Save without generating artifacts
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=False)

        analysis = analyze_anchor_artifacts("test-run-002", base_dir=tmpdir_path)

        assert analysis["has_anchor"] is True
        assert analysis["has_summary"] is False
        assert analysis["has_events"] is False


def test_analyze_anchor_artifacts_event_types():
    """Test event type counting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        anchor = create_anchor(
            run_id="test-run-003",
            project_id="test-project",
            north_star="Event types test.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Log additional events manually
        from autopack.intention_anchor import log_anchor_event

        log_anchor_event(
            run_id="test-run-003",
            event_type="prompt_injected_builder",
            anchor_id=anchor.anchor_id,
            version=1,
            base_dir=tmpdir_path,
        )
        log_anchor_event(
            run_id="test-run-003",
            event_type="prompt_injected_builder",
            anchor_id=anchor.anchor_id,
            version=1,
            base_dir=tmpdir_path,
        )

        analysis = analyze_anchor_artifacts("test-run-003", base_dir=tmpdir_path)

        assert "anchor_created" in analysis["event_types"]
        assert "prompt_injected_builder" in analysis["event_types"]
        assert analysis["event_types"]["prompt_injected_builder"] == 2


# =============================================================================
# Report Generation Tests
# =============================================================================


def test_generate_report_markdown_empty():
    """Test markdown report with no runs."""
    md_report = generate_report_markdown([])

    assert "# Intention Anchor Consolidation Report" in md_report
    assert "**Total runs analyzed**: 0" in md_report
    assert "*No runs with intention anchors found.*" in md_report


def test_generate_report_markdown_deterministic():
    """Test markdown report is deterministic."""
    analyses = [
        {
            "run_id": "run-001",
            "project_id": "test",
            "anchor_id": "IA-001",
            "version": 1,
            "last_updated": "2024-01-01T00:00:00Z",
            "has_anchor": True,
            "has_summary": True,
            "has_events": True,
            "event_count": 5,
            "event_types": {"anchor_created": 1, "prompt_injected_builder": 4},
            "malformed_events": 0,
        }
    ]

    md_report_1 = generate_report_markdown(analyses)
    md_report_2 = generate_report_markdown(analyses)

    assert md_report_1 == md_report_2


def test_generate_report_markdown_structure():
    """Test markdown report contains expected sections."""
    analyses = [
        {
            "run_id": "run-001",
            "project_id": "test",
            "anchor_id": "IA-001",
            "version": 1,
            "last_updated": "2024-01-01T00:00:00Z",
            "has_anchor": True,
            "has_summary": True,
            "has_events": True,
            "event_count": 5,
            "event_types": {"anchor_created": 1},
            "malformed_events": 0,
        }
    ]

    md_report = generate_report_markdown(analyses)

    assert "# Intention Anchor Consolidation Report" in md_report
    assert "## Summary" in md_report
    assert "## Detailed Breakdown" in md_report
    assert "### run-001" in md_report
    assert "IA-001" in md_report


def test_generate_report_json_schema():
    """Test JSON report has stable schema."""
    analyses = [
        {
            "run_id": "run-001",
            "project_id": "test",
            "anchor_id": "IA-001",
            "version": 1,
            "last_updated": "2024-01-01T00:00:00Z",
            "has_anchor": True,
            "has_summary": True,
            "has_events": True,
            "event_count": 5,
            "event_types": {},
            "malformed_events": 0,
        }
    ]

    json_report = generate_report_json(analyses)

    # Verify schema
    assert "format_version" in json_report
    assert json_report["format_version"] == 1
    assert "total_runs" in json_report
    assert json_report["total_runs"] == 1
    assert "runs" in json_report
    assert len(json_report["runs"]) == 1


def test_generate_report_json_deterministic():
    """Test JSON report is deterministic."""
    analyses = [
        {
            "run_id": "run-001",
            "project_id": "test",
            "anchor_id": "IA-001",
            "version": 1,
            "last_updated": "2024-01-01T00:00:00Z",
            "has_anchor": True,
            "has_summary": True,
            "has_events": True,
            "event_count": 5,
            "event_types": {},
            "malformed_events": 0,
        }
    ]

    json_report_1 = generate_report_json(analyses)
    json_report_2 = generate_report_json(analyses)

    assert json_report_1 == json_report_2


# =============================================================================
# Integration Tests (run_report_mode)
# =============================================================================


def test_run_report_mode_no_runs():
    """Test report mode handles no runs gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create output file
        output_json = tmpdir_path / "report.json"

        exit_code = run_report_mode(
            base_dir=tmpdir_path,
            output_md=None,  # stdout
            output_json=output_json,
        )

        assert exit_code == 0
        assert output_json.exists()

        # Verify JSON content
        report = json.loads(output_json.read_text(encoding="utf-8"))
        assert report["total_runs"] == 0
        assert report["runs"] == []


def test_run_report_mode_with_runs():
    """Test report mode with multiple runs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create multiple runs
        for i in range(3):
            run_id = f"run-{i:03d}"
            anchor = create_anchor(
                run_id=run_id,
                project_id="test",
                north_star=f"Run {i} north star.",
            )
            save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run report mode
        output_md = tmpdir_path / "report.md"
        output_json = tmpdir_path / "report.json"

        exit_code = run_report_mode(
            base_dir=tmpdir_path,
            output_md=output_md,
            output_json=output_json,
        )

        assert exit_code == 0
        assert output_md.exists()
        assert output_json.exists()

        # Verify content
        report = json.loads(output_json.read_text(encoding="utf-8"))
        assert report["total_runs"] == 3
        assert len(report["runs"]) == 3


# =============================================================================
# Contract Tests (No SOT Writes)
# =============================================================================


def test_run_report_mode_no_sot_writes():
    """
    CRITICAL CONTRACT TEST: Verify report mode NEVER writes to SOT ledgers.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create fake SOT ledgers
        docs_dir = tmpdir_path / "docs"
        docs_dir.mkdir()

        sot_files = {
            "BUILD_HISTORY.md": "# Build History\n\nOriginal content.\n",
            "DEBUG_LOG.md": "# Debug Log\n\nOriginal content.\n",
            "ARCHITECTURE_DECISIONS.md": "# Architecture Decisions\n\nOriginal content.\n",
        }

        readme_path = tmpdir_path / "README.md"
        readme_path.write_text("# README\n\nOriginal content.\n", encoding="utf-8")

        # Create SOT files and record their state
        file_states = {}
        for filename, content in sot_files.items():
            file_path = docs_dir / filename
            file_path.write_text(content, encoding="utf-8")
            file_states[file_path] = {
                "content": content,
                "mtime": file_path.stat().st_mtime,
            }

        file_states[readme_path] = {
            "content": readme_path.read_text(encoding="utf-8"),
            "mtime": readme_path.stat().st_mtime,
        }

        # Create runs with anchors
        for i in range(3):
            run_id = f"run-{i:03d}"
            anchor = create_anchor(
                run_id=run_id,
                project_id="test",
                north_star=f"Run {i}.",
            )
            save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run report mode
        output_json = tmpdir_path / "report.json"
        run_report_mode(
            base_dir=tmpdir_path,
            output_md=None,
            output_json=output_json,
        )

        # CRITICAL: Verify SOT files are unchanged
        for file_path, original_state in file_states.items():
            assert file_path.exists(), f"{file_path} was deleted!"

            # Check content unchanged
            current_content = file_path.read_text(encoding="utf-8")
            assert current_content == original_state["content"], (
                f"{file_path} content was modified!"
            )

            # Check mtime unchanged
            current_mtime = file_path.stat().st_mtime
            assert current_mtime == original_state["mtime"], (
                f"{file_path} mtime changed (file was written to)!"
            )


# =============================================================================
# P1 Validation Tests (Event Schema & Snapshot Completeness)
# =============================================================================


def test_analyze_anchor_artifacts_invalid_format_version():
    """Test analyzer counts events with invalid format_version."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create anchor
        anchor = create_anchor(
            run_id="test-run-format",
            project_id="test",
            north_star="Test format version.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Manually add event with invalid format_version
        from autopack.intention_anchor.artifacts import get_anchor_events_path

        events_path = get_anchor_events_path("test-run-format", base_dir=tmpdir_path)

        with events_path.open("a", encoding="utf-8") as f:
            # Add event with format_version=2 (invalid, should be 1)
            f.write(
                json.dumps(
                    {
                        "format_version": 2,
                        "event_type": "anchor_created",
                        "timestamp": "2024-01-01T00:00:00Z",
                    }
                )
                + "\n"
            )
            # Add event with missing format_version
            f.write(
                json.dumps(
                    {
                        "event_type": "anchor_updated",
                        "timestamp": "2024-01-01T00:00:00Z",
                    }
                )
                + "\n"
            )

        # Analyze
        analysis = analyze_anchor_artifacts("test-run-format", base_dir=tmpdir_path)

        # Should count invalid format versions
        assert analysis["invalid_format_version_events"] >= 2


def test_analyze_anchor_artifacts_unknown_event_types():
    """Test analyzer counts unknown event types."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create anchor
        anchor = create_anchor(
            run_id="test-run-events",
            project_id="test",
            north_star="Test event types.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Manually add events with unknown types
        from autopack.intention_anchor.artifacts import get_anchor_events_path

        events_path = get_anchor_events_path("test-run-events", base_dir=tmpdir_path)

        with events_path.open("a", encoding="utf-8") as f:
            # Add event with unknown type
            f.write(
                json.dumps(
                    {
                        "format_version": 1,
                        "event_type": "unknown_event_type",
                        "timestamp": "2024-01-01T00:00:00Z",
                    }
                )
                + "\n"
            )
            # Add event with missing event_type
            f.write(
                json.dumps(
                    {
                        "format_version": 1,
                        "timestamp": "2024-01-01T00:00:00Z",
                    }
                )
                + "\n"
            )

        # Analyze
        analysis = analyze_anchor_artifacts("test-run-events", base_dir=tmpdir_path)

        # Should count unknown event types
        assert "unknown_event_types" in analysis
        assert len(analysis["unknown_event_types"]) >= 1


def test_analyze_anchor_artifacts_malformed_events():
    """Test analyzer counts malformed NDJSON events."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create anchor
        anchor = create_anchor(
            run_id="test-run-malformed",
            project_id="test",
            north_star="Test malformed events.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Manually add malformed events
        from autopack.intention_anchor.artifacts import get_anchor_events_path

        events_path = get_anchor_events_path("test-run-malformed", base_dir=tmpdir_path)

        with events_path.open("a", encoding="utf-8") as f:
            # Add malformed JSON
            f.write("{ this is not valid json\n")
            f.write("another broken line\n")

        # Analyze
        analysis = analyze_anchor_artifacts("test-run-malformed", base_dir=tmpdir_path)

        # Should count malformed events
        assert analysis["malformed_events"] >= 2


def test_analyze_anchor_artifacts_missing_snapshots():
    """Test analyzer detects missing versioned snapshots."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create anchor with version 1
        anchor = create_anchor(
            run_id="test-run-snapshots",
            project_id="test",
            north_star="Test snapshot completeness.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Update to version 2
        from autopack.intention_anchor import update_anchor

        anchor = update_anchor(anchor)
        anchor = anchor.model_copy(update={"north_star": "Updated north star v2."})
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Update to version 3
        anchor = update_anchor(anchor)
        anchor = anchor.model_copy(update={"north_star": "Updated north star v3."})
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Manually delete snapshot v2
        from autopack.intention_anchor.artifacts import get_anchor_summary_version_path

        snapshot_v2_path = get_anchor_summary_version_path(
            "test-run-snapshots", 2, base_dir=tmpdir_path
        )
        if snapshot_v2_path.exists():
            snapshot_v2_path.unlink()

        # Analyze
        analysis = analyze_anchor_artifacts("test-run-snapshots", base_dir=tmpdir_path)

        # Should detect missing snapshot v2
        assert "missing_summary_snapshots" in analysis
        assert 2 in analysis["missing_summary_snapshots"]


def test_analyze_anchor_artifacts_all_snapshots_present():
    """Test analyzer confirms all snapshots present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create anchor with version 1
        anchor = create_anchor(
            run_id="test-run-complete",
            project_id="test",
            north_star="Test complete snapshots.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Update to version 2
        from autopack.intention_anchor import update_anchor

        anchor = update_anchor(anchor)
        anchor = anchor.model_copy(update={"north_star": "Updated north star v2."})
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Analyze
        analysis = analyze_anchor_artifacts("test-run-complete", base_dir=tmpdir_path)

        # Should have no missing snapshots
        assert "missing_summary_snapshots" in analysis
        assert len(analysis["missing_summary_snapshots"]) == 0


def test_report_json_includes_validation_fields():
    """Test JSON report includes P1 validation fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create anchor
        anchor = create_anchor(
            run_id="test-run-validation",
            project_id="test",
            north_star="Test validation fields.",
        )
        save_anchor(anchor, base_dir=tmpdir_path, generate_artifacts=True)

        # Run report mode
        output_json = tmpdir_path / "report.json"
        run_report_mode(
            base_dir=tmpdir_path,
            output_md=None,
            output_json=output_json,
        )

        # Verify JSON report includes validation fields
        report = json.loads(output_json.read_text(encoding="utf-8"))
        assert len(report["runs"]) == 1

        run_data = report["runs"][0]
        assert "invalid_format_version_events" in run_data
        assert "unknown_event_types" in run_data
        assert "missing_summary_snapshots" in run_data
        assert "malformed_events" in run_data
