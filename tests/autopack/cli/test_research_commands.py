"""Tests for research CLI commands."""

import pytest
from click.testing import CliRunner

from autopack.cli.research_commands import research_cli


@pytest.fixture
def cli_runner():
    """Create CLI runner."""
    return CliRunner()


@pytest.fixture
def storage_dir(tmp_path):
    """Create temporary storage directory."""
    return tmp_path / "research"


def test_start_research_command(cli_runner, storage_dir):
    """Test starting a research session via CLI."""
    result = cli_runner.invoke(
        research_cli,
        [
            "start",
            "Test research",
            "--priority",
            "high",
            "--query",
            "Question 1",
            "--query",
            "Question 2",
            "--storage-dir",
            str(storage_dir),
        ],
    )

    assert result.exit_code == 0
    assert "Started research phase" in result.output


def test_start_research_default_priority(cli_runner, storage_dir):
    """Test starting research with default priority."""
    result = cli_runner.invoke(
        research_cli, ["start", "Test research", "--storage-dir", str(storage_dir)]
    )

    assert result.exit_code == 0


def test_list_research_command(cli_runner, storage_dir):
    """Test listing research phases."""
    # Create a research phase first
    cli_runner.invoke(research_cli, ["start", "Test research", "--storage-dir", str(storage_dir)])

    # List phases
    result = cli_runner.invoke(research_cli, ["list", "--storage-dir", str(storage_dir)])

    assert result.exit_code == 0


def test_list_research_with_filters(cli_runner, storage_dir):
    """Test listing research with filters."""
    # Create phases
    cli_runner.invoke(
        research_cli,
        [
            "start",
            "High priority research",
            "--priority",
            "high",
            "--storage-dir",
            str(storage_dir),
        ],
    )

    # List with priority filter
    result = cli_runner.invoke(
        research_cli, ["list", "--priority", "high", "--storage-dir", str(storage_dir)]
    )

    assert result.exit_code == 0


def test_status_command_all_phases(cli_runner, storage_dir):
    """Test status command without phase ID."""
    # Create a phase
    cli_runner.invoke(research_cli, ["start", "Test research", "--storage-dir", str(storage_dir)])

    # Check status
    result = cli_runner.invoke(research_cli, ["status", "--storage-dir", str(storage_dir)])

    assert result.exit_code == 0


def test_status_command_specific_phase(cli_runner, storage_dir):
    """Test status command with specific phase ID."""
    # Create a phase
    from autopack.phases.research_phase import ResearchPhaseManager

    manager = ResearchPhaseManager(storage_dir)
    phase = manager.create_phase("Test phase")

    # Check status
    result = cli_runner.invoke(
        research_cli, ["status", phase.phase_id, "--storage-dir", str(storage_dir)]
    )

    assert result.exit_code == 0


def test_status_command_nonexistent_phase(cli_runner, storage_dir):
    """Test status command with non-existent phase."""
    result = cli_runner.invoke(
        research_cli, ["status", "nonexistent_phase", "--storage-dir", str(storage_dir)]
    )

    assert result.exit_code != 0
    assert "not found" in result.output


def test_export_json_command(cli_runner, storage_dir, tmp_path):
    """Test exporting research as JSON."""
    # Create a phase
    from autopack.phases.research_phase import ResearchPhaseManager

    manager = ResearchPhaseManager(storage_dir)
    phase = manager.create_phase("Test phase")
    phase.add_query("Test question")

    output_file = tmp_path / "export.json"

    # Export
    result = cli_runner.invoke(
        research_cli,
        [
            "export",
            phase.phase_id,
            "--output",
            str(output_file),
            "--format",
            "json",
            "--storage-dir",
            str(storage_dir),
        ],
    )

    assert result.exit_code == 0
    assert output_file.exists()

    # Verify JSON content
    import json

    data = json.loads(output_file.read_text())
    assert data["phase_id"] == phase.phase_id


def test_export_markdown_command(cli_runner, storage_dir, tmp_path):
    """Test exporting research as Markdown."""
    # Create a phase
    from autopack.phases.research_phase import ResearchPhaseManager

    manager = ResearchPhaseManager(storage_dir)
    phase = manager.create_phase("Test phase")
    phase.add_query("Test question")

    output_file = tmp_path / "export.md"

    # Export
    result = cli_runner.invoke(
        research_cli,
        [
            "export",
            phase.phase_id,
            "--output",
            str(output_file),
            "--format",
            "markdown",
            "--storage-dir",
            str(storage_dir),
        ],
    )

    assert result.exit_code == 0
    assert output_file.exists()

    # Verify Markdown content
    content = output_file.read_text()
    assert "# Research Phase" in content
    assert phase.phase_id in content


def test_export_to_stdout(cli_runner, storage_dir):
    """Test exporting to stdout."""
    # Create a phase
    from autopack.phases.research_phase import ResearchPhaseManager

    manager = ResearchPhaseManager(storage_dir)
    phase = manager.create_phase("Test phase")

    # Export to stdout
    result = cli_runner.invoke(
        research_cli, ["export", phase.phase_id, "--storage-dir", str(storage_dir)]
    )

    assert result.exit_code == 0
    assert phase.phase_id in result.output


def test_insights_command(cli_runner, tmp_path):
    """Test insights command."""
    # Create sample BUILD_HISTORY
    build_history = tmp_path / "BUILD_HISTORY.md"
    build_history.write_text(
        """
# Build History

## Phase 1: Test Feature
Category: IMPLEMENT_FEATURE
Status: COMPLETE
    """
    )

    result = cli_runner.invoke(
        research_cli,
        [
            "insights",
            "Add new feature",
            "--category",
            "IMPLEMENT_FEATURE",
            "--build-history",
            str(build_history),
        ],
    )

    assert result.exit_code == 0


def test_insights_no_history(cli_runner, tmp_path):
    """Test insights with missing BUILD_HISTORY."""
    build_history = tmp_path / "MISSING.md"

    result = cli_runner.invoke(
        research_cli, ["insights", "Add new feature", "--build-history", str(build_history)]
    )

    # Should handle gracefully
    assert result.exit_code == 0
