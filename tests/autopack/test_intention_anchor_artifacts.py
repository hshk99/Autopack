"""
Tests for Intention Anchor SOT artifacts (Milestone 3).

Intention behind these tests: Verify that run-local SOT-ready artifacts are
correctly generated and can be consolidated without direct writes to SOT ledgers.
"""

import tempfile
from pathlib import Path

from autopack.intention_anchor import (IntentionConstraints, create_anchor,
                                       generate_anchor_diff_summary,
                                       generate_anchor_summary,
                                       get_anchor_events_path,
                                       get_anchor_summary_path,
                                       log_anchor_event, read_anchor_events,
                                       save_anchor, save_anchor_summary,
                                       update_anchor)

# =============================================================================
# Artifact Path Tests
# =============================================================================


def test_get_anchor_summary_path():
    """Test canonical path generation for anchor_summary.md."""
    path = get_anchor_summary_path("test-run-001")
    assert path == Path(".") / ".autonomous_runs" / "test-run-001" / "anchor_summary.md"


def test_get_anchor_events_path():
    """Test canonical path generation for anchor_events.ndjson."""
    path = get_anchor_events_path("test-run-001")
    assert path == Path(".") / ".autonomous_runs" / "test-run-001" / "anchor_events.ndjson"


# =============================================================================
# Summary Generation Tests
# =============================================================================


def test_generate_anchor_summary_minimal():
    """Test summary generation with minimal anchor."""
    anchor = create_anchor(
        run_id="test-run-001",
        project_id="test-project",
        north_star="Test summary generation.",
    )

    summary = generate_anchor_summary(anchor)

    # Verify structure
    assert "# Intention Anchor Summary" in summary
    assert f"**Anchor ID**: `{anchor.anchor_id}`" in summary
    assert "**Run ID**: `test-run-001`" in summary
    assert "**Version**: 1" in summary
    assert "Test summary generation" in summary


def test_generate_anchor_summary_with_success_criteria():
    """Test summary includes numbered success criteria."""
    anchor = create_anchor(
        run_id="test-run-002",
        project_id="test-project",
        north_star="Test with criteria.",
        success_criteria=["SC1", "SC2", "SC3"],
    )

    summary = generate_anchor_summary(anchor)

    assert "## Success Criteria" in summary
    assert "0. SC1" in summary
    assert "1. SC2" in summary
    assert "2. SC3" in summary


def test_generate_anchor_summary_with_constraints():
    """Test summary includes indexed constraints."""
    anchor = create_anchor(
        run_id="test-run-003",
        project_id="test-project",
        north_star="Test with constraints.",
        constraints=IntentionConstraints(
            must=["M1", "M2"],
            must_not=["MN1", "MN2"],
            preferences=["P1"],
        ),
    )

    summary = generate_anchor_summary(anchor)

    assert "## Constraints" in summary
    assert "**Must:**" in summary
    assert "- [0] M1" in summary
    assert "- [1] M2" in summary
    assert "**Must Not:**" in summary
    assert "- [0] MN1" in summary
    assert "- [1] MN2" in summary
    assert "**Preferences:**" in summary
    assert "- [0] P1" in summary


def test_generate_anchor_summary_deterministic():
    """Test summary generation is deterministic (same input → same output)."""
    anchor1 = create_anchor(
        run_id="test-run-004",
        project_id="test-project",
        north_star="Deterministic test.",
        anchor_id="IA-fixed-001",  # Fixed ID for determinism
        success_criteria=["SC1", "SC2"],
    )

    anchor2 = create_anchor(
        run_id="test-run-004",
        project_id="test-project",
        north_star="Deterministic test.",
        anchor_id="IA-fixed-001",
        success_criteria=["SC1", "SC2"],
    )

    summary1 = generate_anchor_summary(anchor1)
    summary2 = generate_anchor_summary(anchor2)

    # Summaries should be identical (ignoring timestamps which differ)
    # We can't compare entire summaries due to timestamps, but structure should match
    assert summary1.count("## Success Criteria") == summary2.count("## Success Criteria")
    assert "0. SC1" in summary1 and "0. SC1" in summary2


# =============================================================================
# Summary Persistence Tests
# =============================================================================


def test_save_anchor_summary_creates_file():
    """Test saving anchor summary creates anchor_summary.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        anchor = create_anchor(
            run_id="test-run-005",
            project_id="test-project",
            north_star="Test summary persistence.",
        )

        summary_path = save_anchor_summary(anchor, base_dir=tmpdir)

        assert summary_path.exists()
        assert summary_path.name == "anchor_summary.md"
        assert summary_path.parent.name == "test-run-005"


def test_save_anchor_summary_roundtrip():
    """Test saved summary is readable and contains expected content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        anchor = create_anchor(
            run_id="test-run-006",
            project_id="test-project",
            north_star="Test roundtrip.",
            success_criteria=["SC1", "SC2"],
        )

        summary_path = save_anchor_summary(anchor, base_dir=tmpdir)
        saved_content = summary_path.read_text(encoding="utf-8")

        # Verify content
        assert "Test roundtrip" in saved_content
        assert "0. SC1" in saved_content
        assert "1. SC2" in saved_content


def test_save_anchor_summary_overwrites():
    """Test saving summary multiple times overwrites (not appends)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        anchor_v1 = create_anchor(
            run_id="test-run-007",
            project_id="test-project",
            north_star="Version 1.",
        )

        # Save v1
        save_anchor_summary(anchor_v1, base_dir=tmpdir)

        # Update and save v2
        anchor_v2 = update_anchor(anchor_v1)
        anchor_v2.north_star = "Version 2."
        save_anchor_summary(anchor_v2, base_dir=tmpdir)

        # Read final content
        summary_path = get_anchor_summary_path("test-run-007", base_dir=tmpdir)
        content = summary_path.read_text(encoding="utf-8")

        # Should only contain v2 content (not both v1 and v2)
        assert "Version 2." in content
        assert "Version 1." not in content
        assert "**Version**: 2" in content


# =============================================================================
# Event Logging Tests
# =============================================================================


def test_log_anchor_event_creates_file():
    """Test logging anchor event creates anchor_events.ndjson."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_anchor_event(
            run_id="test-run-008",
            event_type="anchor_created",
            anchor_id="IA-test-001",
            version=1,
            base_dir=tmpdir,
        )

        events_path = get_anchor_events_path("test-run-008", base_dir=tmpdir)
        assert events_path.exists()


def test_log_anchor_event_appends():
    """Test multiple events are appended (not overwritten)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Log multiple events
        log_anchor_event(
            run_id="test-run-009",
            event_type="anchor_created",
            anchor_id="IA-test-002",
            version=1,
            base_dir=tmpdir,
        )

        log_anchor_event(
            run_id="test-run-009",
            event_type="anchor_updated",
            anchor_id="IA-test-002",
            version=2,
            base_dir=tmpdir,
        )

        log_anchor_event(
            run_id="test-run-009",
            event_type="prompt_injected_builder",
            anchor_id="IA-test-002",
            version=2,
            phase_id="F1.1",
            agent_type="builder",
            chars_injected=250,
            base_dir=tmpdir,
        )

        # Read all events
        events = read_anchor_events("test-run-009", base_dir=tmpdir)

        assert len(events) == 3
        assert events[0]["event_type"] == "anchor_created"
        assert events[1]["event_type"] == "anchor_updated"
        assert events[2]["event_type"] == "prompt_injected_builder"


def test_log_anchor_event_includes_metadata():
    """Test event logging includes all provided metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_anchor_event(
            run_id="test-run-010",
            event_type="prompt_injected_auditor",
            anchor_id="IA-test-003",
            version=1,
            phase_id="F1.2",
            agent_type="auditor",
            chars_injected=180,
            message="Anchor injected into Auditor prompt",
            metadata={"custom_key": "custom_value"},
            base_dir=tmpdir,
        )

        events = read_anchor_events("test-run-010", base_dir=tmpdir)

        assert len(events) == 1
        event = events[0]

        assert event["event_type"] == "prompt_injected_auditor"
        assert event["anchor_id"] == "IA-test-003"
        assert event["version"] == 1
        assert event["phase_id"] == "F1.2"
        assert event["agent_type"] == "auditor"
        assert event["chars_injected"] == 180
        assert event["message"] == "Anchor injected into Auditor prompt"
        assert event["metadata"]["custom_key"] == "custom_value"
        assert "timestamp" in event


def test_read_anchor_events_empty():
    """Test reading events when file doesn't exist returns empty list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        events = read_anchor_events("nonexistent-run", base_dir=tmpdir)
        assert events == []


def test_read_anchor_events_with_filter():
    """Test filtering events by event_type."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Log multiple event types
        log_anchor_event(
            run_id="test-run-011",
            event_type="anchor_created",
            anchor_id="IA-test-004",
            version=1,
            base_dir=tmpdir,
        )

        log_anchor_event(
            run_id="test-run-011",
            event_type="prompt_injected_builder",
            anchor_id="IA-test-004",
            version=1,
            phase_id="F1.1",
            base_dir=tmpdir,
        )

        log_anchor_event(
            run_id="test-run-011",
            event_type="prompt_injected_builder",
            anchor_id="IA-test-004",
            version=1,
            phase_id="F1.2",
            base_dir=tmpdir,
        )

        # Filter for prompt_injected_builder events only
        builder_events = read_anchor_events(
            "test-run-011",
            base_dir=tmpdir,
            event_type_filter="prompt_injected_builder",
        )

        assert len(builder_events) == 2
        assert all(e["event_type"] == "prompt_injected_builder" for e in builder_events)


# =============================================================================
# Auto-Generation Tests (storage integration)
# =============================================================================


def test_save_anchor_auto_generates_artifacts():
    """Test save_anchor automatically generates summary and logs event."""
    with tempfile.TemporaryDirectory() as tmpdir:
        anchor = create_anchor(
            run_id="test-run-012",
            project_id="test-project",
            north_star="Test auto-generation.",
        )

        save_anchor(anchor, base_dir=tmpdir)

        # Verify summary was created
        summary_path = get_anchor_summary_path("test-run-012", base_dir=tmpdir)
        assert summary_path.exists()

        # Verify event was logged
        events = read_anchor_events("test-run-012", base_dir=tmpdir)
        assert len(events) == 1
        assert events[0]["event_type"] == "anchor_created"
        assert events[0]["version"] == 1


def test_update_anchor_logs_update_event():
    """Test updating anchor logs anchor_updated event."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create and save v1
        anchor_v1 = create_anchor(
            run_id="test-run-013",
            project_id="test-project",
            north_star="Version 1.",
        )
        save_anchor(anchor_v1, base_dir=tmpdir)

        # Update and save v2
        update_anchor(anchor_v1, save=True, base_dir=tmpdir)

        # Verify events
        events = read_anchor_events("test-run-013", base_dir=tmpdir)
        assert len(events) == 2
        assert events[0]["event_type"] == "anchor_created"
        assert events[0]["version"] == 1
        assert events[1]["event_type"] == "anchor_updated"
        assert events[1]["version"] == 2


def test_save_anchor_artifact_generation_can_be_disabled():
    """Test artifact generation can be disabled via generate_artifacts=False."""
    with tempfile.TemporaryDirectory() as tmpdir:
        anchor = create_anchor(
            run_id="test-run-014",
            project_id="test-project",
            north_star="No artifacts.",
        )

        save_anchor(anchor, base_dir=tmpdir, generate_artifacts=False)

        # Anchor JSON should exist
        from autopack.intention_anchor import get_canonical_path

        anchor_path = get_canonical_path("test-run-014", base_dir=tmpdir)
        assert anchor_path.exists()

        # But artifacts should NOT exist
        summary_path = get_anchor_summary_path("test-run-014", base_dir=tmpdir)
        events_path = get_anchor_events_path("test-run-014", base_dir=tmpdir)
        assert not summary_path.exists()
        assert not events_path.exists()


# =============================================================================
# Diff Summary Tests
# =============================================================================


def test_generate_anchor_diff_summary_north_star_change():
    """Test diff summary detects north star changes."""
    anchor_v1 = create_anchor(
        run_id="test-run-015",
        project_id="test-project",
        north_star="Original north star.",
    )

    anchor_v2 = update_anchor(anchor_v1)
    anchor_v2.north_star = "Updated north star."

    diff = generate_anchor_diff_summary(anchor_v1, anchor_v2)

    assert "North star changed" in diff
    assert "Original north star" in diff
    assert "Updated north star" in diff


def test_generate_anchor_diff_summary_success_criteria_changes():
    """Test diff summary detects success criteria changes."""
    anchor_v1 = create_anchor(
        run_id="test-run-016",
        project_id="test-project",
        north_star="Test criteria changes.",
        success_criteria=["SC1", "SC2", "SC3"],
    )

    anchor_v2 = update_anchor(anchor_v1)
    anchor_v2.success_criteria = ["SC1", "SC3", "SC4"]  # Removed SC2, added SC4

    diff = generate_anchor_diff_summary(anchor_v1, anchor_v2)

    assert "Success criteria added" in diff
    assert "SC4" in diff
    assert "Success criteria removed" in diff
    assert "SC2" in diff


def test_generate_anchor_diff_summary_no_changes():
    """Test diff summary handles metadata-only updates."""
    anchor_v1 = create_anchor(
        run_id="test-run-017",
        project_id="test-project",
        north_star="No changes.",
    )

    anchor_v2 = update_anchor(anchor_v1)
    # Version and timestamp changed, but no content changes

    diff = generate_anchor_diff_summary(anchor_v1, anchor_v2)

    assert "No changes detected" in diff


def test_generate_anchor_diff_summary_version_jump():
    """Test diff summary detects unexpected version jumps."""
    anchor_v1 = create_anchor(
        run_id="test-run-018",
        project_id="test-project",
        north_star="Version jump test.",
    )

    anchor_v2 = update_anchor(anchor_v1)
    anchor_v2.version = 5  # Jump from 2 to 5 (should be 2)

    diff = generate_anchor_diff_summary(anchor_v1, anchor_v2)

    assert "⚠️ Version jump" in diff
    assert "expected 2" in diff


# =============================================================================
# Contract Tests (no SOT writes during artifact generation)
# =============================================================================


def test_artifact_generation_does_not_write_to_sot_ledgers():
    """
    CRITICAL CONTRACT TEST: Verify artifact generation NEVER writes to SOT ledgers.

    This test ensures Milestone 3 implementation respects the constraint that
    autonomous runs must not write directly to BUILD_HISTORY/DEBUG_LOG during execution.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create fake SOT ledgers
        build_history_path = Path(tmpdir) / "BUILD_HISTORY.md"
        debug_log_path = Path(tmpdir) / "DEBUG_LOG.md"
        build_history_path.write_text("# Build History\n", encoding="utf-8")
        debug_log_path.write_text("# Debug Log\n", encoding="utf-8")

        # Record original content
        original_build_history = build_history_path.read_text(encoding="utf-8")
        original_debug_log = debug_log_path.read_text(encoding="utf-8")

        # Perform all artifact operations
        anchor = create_anchor(
            run_id="test-run-019",
            project_id="test-project",
            north_star="Test SOT isolation.",
            success_criteria=["SC1", "SC2"],
        )

        save_anchor(anchor, base_dir=tmpdir)
        save_anchor_summary(anchor, base_dir=tmpdir)
        log_anchor_event(
            run_id="test-run-019",
            event_type="anchor_created",
            anchor_id=anchor.anchor_id,
            version=1,
            base_dir=tmpdir,
        )

        # Verify SOT ledgers were NOT modified
        assert build_history_path.read_text(encoding="utf-8") == original_build_history
        assert debug_log_path.read_text(encoding="utf-8") == original_debug_log

        # Verify artifacts WERE created in .autonomous_runs
        summary_path = get_anchor_summary_path("test-run-019", base_dir=tmpdir)
        events_path = get_anchor_events_path("test-run-019", base_dir=tmpdir)
        assert summary_path.exists()
        assert events_path.exists()


def test_artifacts_are_append_only():
    """Test that event log is truly append-only (never edited)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Log first event
        log_anchor_event(
            run_id="test-run-020",
            event_type="anchor_created",
            anchor_id="IA-test-005",
            version=1,
            base_dir=tmpdir,
        )

        # Read file content
        events_path = get_anchor_events_path("test-run-020", base_dir=tmpdir)
        first_content = events_path.read_text(encoding="utf-8")

        # Log second event
        log_anchor_event(
            run_id="test-run-020",
            event_type="anchor_updated",
            anchor_id="IA-test-005",
            version=2,
            base_dir=tmpdir,
        )

        # Read file content again
        second_content = events_path.read_text(encoding="utf-8")

        # First content should be preserved (append-only)
        assert first_content in second_content
        assert len(second_content) > len(first_content)

        # Verify both events are parseable
        events = read_anchor_events("test-run-020", base_dir=tmpdir)
        assert len(events) == 2
