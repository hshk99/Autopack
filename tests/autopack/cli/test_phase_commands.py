from click.testing import CliRunner
from autopack.cli.commands.phases import cli


def test_create_phase():
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "create-phase",
            "--name",
            "Test Phase",
            "--description",
            "A test phase",
            "--complexity",
            "medium",
        ],
    )
    assert result.exit_code == 0
    assert "Phase 'Test Phase' created with complexity 'medium'." in result.output


def test_execute_phase():
    runner = CliRunner()
    result = runner.invoke(cli, ["execute-phase", "--phase-id", "1"])
    assert result.exit_code == 0
    assert "Executing phase with ID 1." in result.output


def test_review_phase():
    runner = CliRunner()
    result = runner.invoke(cli, ["review-phase", "--phase-id", "1"])
    assert result.exit_code == 0
    assert "Reviewing phase with ID 1." in result.output


def test_phase_status():
    runner = CliRunner()
    result = runner.invoke(cli, ["phase-status", "--phase-id", "1"])
    assert result.exit_code == 0
    assert "Mock status for phase ID 1: In Progress (test data only)" in result.output
    # Verify deprecation guidance is shown
    assert "This is a test shim" in result.output
    assert "Supervisor REST API" in result.output


def test_create_phase_missing_argument():
    runner = CliRunner()
    result = runner.invoke(cli, ["create-phase", "--name", "Test Phase", "--complexity", "medium"])
    assert result.exit_code != 0
    assert "Error: Missing option '--description'." in result.output


def test_execute_phase_invalid_id():
    runner = CliRunner()
    result = runner.invoke(cli, ["execute-phase", "--phase-id", "abc"])
    assert result.exit_code != 0
    assert "Error: Invalid value for '--phase-id': 'abc' is not a valid integer." in result.output


def test_review_phase_invalid_id():
    runner = CliRunner()
    result = runner.invoke(cli, ["review-phase", "--phase-id", "abc"])
    assert result.exit_code != 0
    assert "Error: Invalid value for '--phase-id': 'abc' is not a valid integer." in result.output


def test_phase_status_invalid_id():
    runner = CliRunner()
    result = runner.invoke(cli, ["phase-status", "--phase-id", "abc"])
    assert result.exit_code != 0
    assert "Error: Invalid value for '--phase-id': 'abc' is not a valid integer." in result.output


def test_deprecation_messages_shown():
    """Verify that all commands show clear deprecation and migration guidance."""
    runner = CliRunner()

    # Test create-phase shows migration message
    result = runner.invoke(
        cli,
        ["create-phase", "--name", "Test", "--description", "Test", "--complexity", "low"],
    )
    assert result.exit_code == 0
    assert "This is a test shim" in result.output
    assert "Supervisor REST API" in result.output

    # Test execute-phase shows migration message
    result = runner.invoke(cli, ["execute-phase", "--phase-id", "1"])
    assert result.exit_code == 0
    assert "This is a test shim" in result.output

    # Test review-phase shows migration message
    result = runner.invoke(cli, ["review-phase", "--phase-id", "1"])
    assert result.exit_code == 0
    assert "This is a test shim" in result.output

    # Test phase-status shows migration message
    result = runner.invoke(cli, ["phase-status", "--phase-id", "1"])
    assert result.exit_code == 0
    assert "This is a test shim" in result.output
    assert "Mock status" in result.output  # Verify it's clear this is mock data
