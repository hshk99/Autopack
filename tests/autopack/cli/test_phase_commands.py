from click.testing import CliRunner
from autopack.cli.commands.phases import cli

def test_create_phase():
    runner = CliRunner()
    result = runner.invoke(cli, ['create-phase', '--name', 'Test Phase', '--description', 'A test phase', '--complexity', 'medium'])
    assert result.exit_code == 0
    assert "Phase 'Test Phase' created with complexity 'medium'." in result.output

def test_execute_phase():
    runner = CliRunner()
    result = runner.invoke(cli, ['execute-phase', '--phase-id', '1'])
    assert result.exit_code == 0
    assert "Executing phase with ID 1." in result.output

def test_review_phase():
    runner = CliRunner()
    result = runner.invoke(cli, ['review-phase', '--phase-id', '1'])
    assert result.exit_code == 0
    assert "Reviewing phase with ID 1." in result.output

def test_phase_status():
    runner = CliRunner()
    result = runner.invoke(cli, ['phase-status', '--phase-id', '1'])
    assert result.exit_code == 0
    assert "Status of phase with ID 1: In Progress." in result.output

def test_create_phase_missing_argument():
    runner = CliRunner()
    result = runner.invoke(cli, ['create-phase', '--name', 'Test Phase', '--complexity', 'medium'])
    assert result.exit_code != 0
    assert "Error: Missing option '--description'." in result.output

def test_execute_phase_invalid_id():
    runner = CliRunner()
    result = runner.invoke(cli, ['execute-phase', '--phase-id', 'abc'])
    assert result.exit_code != 0
    assert "Error: Invalid value for '--phase-id': 'abc' is not a valid integer." in result.output

def test_review_phase_invalid_id():
    runner = CliRunner()
    result = runner.invoke(cli, ['review-phase', '--phase-id', 'abc'])
    assert result.exit_code != 0
    assert "Error: Invalid value for '--phase-id': 'abc' is not a valid integer." in result.output

def test_phase_status_invalid_id():
    runner = CliRunner()
    result = runner.invoke(cli, ['phase-status', '--phase-id', 'abc'])
    assert result.exit_code != 0
    assert "Error: Invalid value for '--phase-id': 'abc' is not a valid integer." in result.output
