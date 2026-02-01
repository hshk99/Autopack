"""Tests for research CLI commands."""

from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from autopack.cli.research_commands import research_cli


@pytest.fixture
def cli_runner():
    """Create CLI runner."""
    return CliRunner()


def test_start_research_command(cli_runner):
    """Test starting a research session via CLI."""
    with patch("autopack.phases.research_phase.create_research_phase") as mock_create:
        # Mock the phase and its execute method
        mock_phase = Mock()
        mock_result = Mock()
        mock_result.phase_id = "research_20240101_120000"
        mock_result.status.value = "completed"
        mock_result.summary = "Test summary"
        mock_result.recommendations = ["Recommendation 1"]
        mock_result.warnings = []
        mock_result.results = []
        mock_result.duration_seconds = 10.5
        mock_result.average_confidence = 0.85

        mock_phase.execute.return_value = mock_result
        mock_create.return_value = mock_phase

        result = cli_runner.invoke(
            research_cli,
            [
                "start",
                "Test research query",
            ],
        )

        assert result.exit_code == 0
        assert "Starting research session" in result.output


def test_start_research_with_options(cli_runner, tmp_path):
    """Test starting research with options."""
    with patch("autopack.phases.research_phase.create_research_phase") as mock_create:
        # Mock the phase and its execute method
        mock_phase = Mock()
        mock_result = Mock()
        mock_result.phase_id = "research_20240101_120000"
        mock_result.status.value = "completed"
        mock_result.summary = "Test summary"
        mock_result.recommendations = []
        mock_result.warnings = []
        mock_result.results = []
        mock_result.duration_seconds = 5.0
        mock_result.average_confidence = 0.90

        mock_phase.execute.return_value = mock_result
        mock_create.return_value = mock_phase

        output_file = tmp_path / "results.json"
        result = cli_runner.invoke(
            research_cli, ["start", "Test research", "--output", str(output_file)]
        )

        assert result.exit_code == 0


def test_list_research_command(cli_runner):
    """Test listing research sessions."""
    result = cli_runner.invoke(research_cli, ["list"])

    assert result.exit_code == 0


def test_list_research_with_filters(cli_runner):
    """Test listing research with filters."""
    # List with status and limit filters
    result = cli_runner.invoke(research_cli, ["list", "--limit", "5", "--status", "completed"])

    assert result.exit_code == 0


def test_status_command_specific_phase(cli_runner):
    """Test status command with phase ID."""
    result = cli_runner.invoke(research_cli, ["status", "test_phase_id"])

    assert result.exit_code == 0


def test_export_json_command(cli_runner, tmp_path):
    """Test exporting research as JSON."""
    output_file = tmp_path / "export.json"

    # Export
    result = cli_runner.invoke(
        research_cli,
        [
            "export",
            "test_phase_id",
            "--output",
            str(output_file),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0


def test_export_markdown_command(cli_runner, tmp_path):
    """Test exporting research as Markdown."""
    output_file = tmp_path / "export.md"

    # Export
    result = cli_runner.invoke(
        research_cli,
        [
            "export",
            "test_phase_id",
            "--output",
            str(output_file),
            "--format",
            "markdown",
        ],
    )

    assert result.exit_code == 0


def test_export_to_stdout(cli_runner):
    """Test exporting to stdout."""
    phase_id = "test_phase_id"

    # Export to stdout
    result = cli_runner.invoke(research_cli, ["export", phase_id])

    assert result.exit_code == 0
