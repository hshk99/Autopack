"""
Doc contract tests for Intention Anchor artifacts (Milestone 3).

Intention behind these tests: Enforce that SOT-ready artifacts follow documented
formats and can be mechanically consolidated by tidy hooks.

These tests ensure the artifact format remains stable and machine-parseable.
"""

import json
import re
import tempfile


from autopack.intention_anchor import (
    IntentionConstraints,
    create_anchor,
    generate_anchor_summary,
    get_anchor_events_path,
    get_anchor_summary_path,
    log_anchor_event,
    read_anchor_events,
    save_anchor,
)


# =============================================================================
# Summary Format Contracts
# =============================================================================


def test_summary_has_required_header_fields():
    """CONTRACT: anchor_summary.md must have all required metadata fields."""
    anchor = create_anchor(
        run_id="contract-test-001",
        project_id="test-project",
        north_star="Test summary contract.",
    )

    summary = generate_anchor_summary(anchor)

    # Required fields in header
    assert "**Anchor ID**:" in summary
    assert "**Run ID**:" in summary
    assert "**Project ID**:" in summary
    assert "**Version**:" in summary
    assert "**Created**:" in summary
    assert "**Updated**:" in summary


def test_summary_north_star_section_exists():
    """CONTRACT: anchor_summary.md must have North Star section."""
    anchor = create_anchor(
        run_id="contract-test-002",
        project_id="test-project",
        north_star="Test north star section.",
    )

    summary = generate_anchor_summary(anchor)

    assert "## North Star" in summary
    assert "Test north star section" in summary


def test_summary_success_criteria_are_numbered():
    """CONTRACT: Success criteria must be numbered 0, 1, 2, ... for stable references."""
    anchor = create_anchor(
        run_id="contract-test-003",
        project_id="test-project",
        north_star="Test numbering.",
        success_criteria=["SC1", "SC2", "SC3"],
    )

    summary = generate_anchor_summary(anchor)

    # Must use numbered format (not bullets)
    assert "0. SC1" in summary
    assert "1. SC2" in summary
    assert "2. SC3" in summary


def test_summary_constraints_are_indexed():
    """CONTRACT: Constraints must be indexed [0], [1], ... for stable references."""
    anchor = create_anchor(
        run_id="contract-test-004",
        project_id="test-project",
        north_star="Test constraint indexing.",
        constraints=IntentionConstraints(
            must=["M1", "M2"],
            must_not=["MN1", "MN2"],
        ),
    )

    summary = generate_anchor_summary(anchor)

    # Must use indexed format for stable binding
    assert "- [0] M1" in summary
    assert "- [1] M2" in summary
    assert "- [0] MN1" in summary
    assert "- [1] MN2" in summary


def test_summary_is_valid_markdown():
    """CONTRACT: Summary must be valid Markdown (headers, lists, etc.)."""
    anchor = create_anchor(
        run_id="contract-test-005",
        project_id="test-project",
        north_star="Test Markdown validity.",
        success_criteria=["SC1"],
        constraints=IntentionConstraints(must=["M1"]),
    )

    summary = generate_anchor_summary(anchor)

    # Check for valid Markdown structure
    assert summary.startswith("# ")  # Must start with H1 header
    assert "## " in summary  # Must have H2 sections
    assert "\n\n" in summary  # Must have paragraph breaks


def test_summary_references_anchor_id_and_version():
    """CONTRACT: Summary must explicitly reference anchor_id + version for traceability."""
    anchor = create_anchor(
        run_id="contract-test-006",
        project_id="test-project",
        north_star="Test traceability.",
        anchor_id="IA-contract-001",
    )

    summary = generate_anchor_summary(anchor)

    # Must reference both anchor_id and version
    assert "IA-contract-001" in summary
    assert "**Version**: 1" in summary


# =============================================================================
# Event Log Format Contracts
# =============================================================================


def test_event_log_is_valid_ndjson():
    """CONTRACT: anchor_events.ndjson must be valid NDJSON (newline-delimited JSON)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Log multiple events
        log_anchor_event(
            run_id="contract-test-007",
            event_type="anchor_created",
            anchor_id="IA-test-001",
            version=1,
            base_dir=tmpdir,
        )

        log_anchor_event(
            run_id="contract-test-007",
            event_type="anchor_updated",
            anchor_id="IA-test-001",
            version=2,
            base_dir=tmpdir,
        )

        # Read raw file
        events_path = get_anchor_events_path("contract-test-007", base_dir=tmpdir)
        lines = events_path.read_text(encoding="utf-8").strip().split("\n")

        # Each line must be valid JSON
        for line in lines:
            event = json.loads(line)  # Should not raise
            assert isinstance(event, dict)


def test_event_has_required_fields():
    """CONTRACT: All events must have timestamp, event_type, run_id."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_anchor_event(
            run_id="contract-test-008",
            event_type="anchor_created",
            anchor_id="IA-test-002",
            version=1,
            base_dir=tmpdir,
        )

        events = read_anchor_events("contract-test-008", base_dir=tmpdir)

        assert len(events) == 1
        event = events[0]

        # Required fields
        assert "timestamp" in event
        assert "event_type" in event
        assert "run_id" in event


def test_event_timestamp_is_iso8601():
    """CONTRACT: Event timestamps must be ISO 8601 format (YYYY-MM-DDTHH:MM:SS)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_anchor_event(
            run_id="contract-test-009",
            event_type="anchor_created",
            anchor_id="IA-test-003",
            version=1,
            base_dir=tmpdir,
        )

        events = read_anchor_events("contract-test-009", base_dir=tmpdir)
        timestamp = events[0]["timestamp"]

        # ISO 8601 format pattern
        iso8601_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
        assert re.match(iso8601_pattern, timestamp)


def test_prompt_injection_events_have_agent_type():
    """CONTRACT: prompt_injected_* events must include agent_type field."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_anchor_event(
            run_id="contract-test-010",
            event_type="prompt_injected_builder",
            anchor_id="IA-test-004",
            version=1,
            phase_id="F1.1",
            agent_type="builder",
            chars_injected=250,
            base_dir=tmpdir,
        )

        events = read_anchor_events("contract-test-010", base_dir=tmpdir)
        event = events[0]

        assert event["agent_type"] == "builder"
        assert "phase_id" in event
        assert "chars_injected" in event


# =============================================================================
# File Location Contracts
# =============================================================================


def test_artifacts_are_in_autonomous_runs_directory():
    """CONTRACT: All artifacts must be in .autonomous_runs/<run_id>/ directory."""
    summary_path = get_anchor_summary_path("contract-test-011")
    events_path = get_anchor_events_path("contract-test-011")

    # Must be in .autonomous_runs/<run_id>/
    assert ".autonomous_runs" in str(summary_path)
    assert "contract-test-011" in str(summary_path)
    assert ".autonomous_runs" in str(events_path)
    assert "contract-test-011" in str(events_path)


def test_summary_filename_is_anchor_summary_md():
    """CONTRACT: Summary file must be named anchor_summary.md (lowercase, underscore)."""
    summary_path = get_anchor_summary_path("contract-test-012")
    assert summary_path.name == "anchor_summary.md"


def test_events_filename_is_anchor_events_ndjson():
    """CONTRACT: Events file must be named anchor_events.ndjson."""
    events_path = get_anchor_events_path("contract-test-013")
    assert events_path.name == "anchor_events.ndjson"


# =============================================================================
# Artifact Content Stability Contracts
# =============================================================================


def test_summary_content_is_stable_for_same_anchor():
    """CONTRACT: Summary content must be deterministic (same anchor → same summary)."""
    anchor = create_anchor(
        run_id="contract-test-014",
        project_id="test-project",
        north_star="Stability test.",
        anchor_id="IA-stable-001",  # Fixed ID
        success_criteria=["SC1", "SC2"],
    )

    summary1 = generate_anchor_summary(anchor)
    summary2 = generate_anchor_summary(anchor)

    # Should be byte-for-byte identical
    assert summary1 == summary2


def test_event_log_preserves_order():
    """CONTRACT: Event log must preserve chronological order (append-only)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Log events in sequence
        for i in range(1, 6):
            log_anchor_event(
                run_id="contract-test-015",
                event_type="anchor_created" if i == 1 else "anchor_updated",
                anchor_id="IA-test-005",
                version=i,
                base_dir=tmpdir,
            )

        events = read_anchor_events("contract-test-015", base_dir=tmpdir)

        # Events must be in chronological order
        assert len(events) == 5
        assert events[0]["version"] == 1
        assert events[1]["version"] == 2
        assert events[2]["version"] == 3
        assert events[3]["version"] == 4
        assert events[4]["version"] == 5


# =============================================================================
# Integration Contracts (storage auto-generates artifacts)
# =============================================================================


def test_save_anchor_auto_generates_summary_by_default():
    """CONTRACT: save_anchor() must auto-generate summary unless explicitly disabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        anchor = create_anchor(
            run_id="contract-test-016",
            project_id="test-project",
            north_star="Auto-generation test.",
        )

        save_anchor(anchor, base_dir=tmpdir)

        # Summary must exist
        summary_path = get_anchor_summary_path("contract-test-016", base_dir=tmpdir)
        assert summary_path.exists()


def test_save_anchor_auto_logs_event_by_default():
    """CONTRACT: save_anchor() must auto-log event unless explicitly disabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        anchor = create_anchor(
            run_id="contract-test-017",
            project_id="test-project",
            north_star="Event logging test.",
        )

        save_anchor(anchor, base_dir=tmpdir)

        # Event must be logged
        events = read_anchor_events("contract-test-017", base_dir=tmpdir)
        assert len(events) >= 1
        assert events[0]["event_type"] in ["anchor_created", "anchor_updated"]


# =============================================================================
# Consolidation Readiness Contracts
# =============================================================================


def test_summary_references_can_be_extracted_mechanically():
    """CONTRACT: Summary must allow mechanical extraction of anchor_id + version."""
    anchor = create_anchor(
        run_id="contract-test-018",
        project_id="test-project",
        north_star="Extraction test.",
        anchor_id="IA-extract-001",
    )

    summary = generate_anchor_summary(anchor)

    # Extract anchor_id using regex
    anchor_id_match = re.search(r"\*\*Anchor ID\*\*: `(.+?)`", summary)
    assert anchor_id_match
    assert anchor_id_match.group(1) == "IA-extract-001"

    # Extract version using regex
    version_match = re.search(r"\*\*Version\*\*: (\d+)", summary)
    assert version_match
    assert version_match.group(1) == "1"


def test_events_can_be_filtered_by_type():
    """CONTRACT: Events must support filtering by event_type for consolidation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Log mixed event types
        log_anchor_event(
            run_id="contract-test-019",
            event_type="anchor_created",
            base_dir=tmpdir,
        )

        log_anchor_event(
            run_id="contract-test-019",
            event_type="prompt_injected_builder",
            base_dir=tmpdir,
        )

        log_anchor_event(
            run_id="contract-test-019",
            event_type="prompt_injected_builder",
            base_dir=tmpdir,
        )

        # Filter for specific type
        builder_events = read_anchor_events(
            "contract-test-019",
            base_dir=tmpdir,
            event_type_filter="prompt_injected_builder",
        )

        # Must only return filtered events
        assert len(builder_events) == 2
        assert all(e["event_type"] == "prompt_injected_builder" for e in builder_events)


def test_events_preserve_all_consolidation_metadata():
    """CONTRACT: Events must preserve anchor_id, version, phase_id for consolidation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_anchor_event(
            run_id="contract-test-020",
            event_type="prompt_injected_auditor",
            anchor_id="IA-consolidate-001",
            version=3,
            phase_id="F2.3",
            agent_type="auditor",
            chars_injected=200,
            base_dir=tmpdir,
        )

        events = read_anchor_events("contract-test-020", base_dir=tmpdir)
        event = events[0]

        # All consolidation metadata must be preserved
        assert event["anchor_id"] == "IA-consolidate-001"
        assert event["version"] == 3
        assert event["phase_id"] == "F2.3"
        assert event["agent_type"] == "auditor"
        assert event["chars_injected"] == 200
