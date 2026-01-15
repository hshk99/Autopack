"""Tests for backup and restore CLI commands."""

import tarfile

import pytest
from click.testing import CliRunner

from autopack.cli.commands.backup import backup
from autopack.cli.commands.restore import restore


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_autopack_dir(tmp_path):
    """Create a sample autopack directory structure for testing."""
    # Create autopack.db
    db_file = tmp_path / "autopack.db"
    db_file.write_text("SQLite database content")

    # Create docs with ledgers
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "ledger.md").write_text("# SOT Ledger\n\nSome content")
    (docs_dir / "another.md").write_text("# Another Doc\n\nMore content")

    # Create .autonomous_runs directory
    runs_dir = tmp_path / ".autonomous_runs"
    runs_dir.mkdir()
    (runs_dir / "run-001.json").write_text('{"run_id": "001"}')

    # Create config directory
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "settings.yaml").write_text("key: value")

    return tmp_path


def test_backup_creates_archive(runner, sample_autopack_dir, tmp_path):
    """Test that backup command creates a valid tar.gz archive."""
    output_file = tmp_path / "test-backup.tar.gz"

    result = runner.invoke(
        backup,
        ["--base-dir", str(sample_autopack_dir), "--output", str(output_file)],
    )

    assert result.exit_code == 0
    assert output_file.exists()
    assert "Backup complete!" in result.output

    # Verify archive contents
    with tarfile.open(output_file, "r:gz") as tar:
        names = tar.getnames()
        assert "autopack.db" in names
        assert any("docs" in n for n in names)
        assert any(".autonomous_runs" in n for n in names)
        assert any("config" in n for n in names)


def test_backup_default_filename(runner, sample_autopack_dir):
    """Test that backup command generates a default filename if not specified."""
    result = runner.invoke(
        backup,
        ["--base-dir", str(sample_autopack_dir)],
    )

    assert result.exit_code == 0
    assert "autopack-backup-" in result.output
    assert ".tar.gz" in result.output


def test_backup_skips_missing_dirs(runner, tmp_path):
    """Test that backup skips directories that don't exist."""
    # Create only autopack.db, no other dirs
    db_file = tmp_path / "autopack.db"
    db_file.write_text("test content")

    output_file = tmp_path / "backup.tar.gz"

    result = runner.invoke(
        backup,
        ["--base-dir", str(tmp_path), "--output", str(output_file)],
    )

    assert result.exit_code == 0
    assert "[skip]" in result.output
    assert output_file.exists()


def test_restore_extracts_archive(runner, sample_autopack_dir, tmp_path):
    """Test that restore command extracts archive contents."""
    # First create a backup
    backup_file = tmp_path / "backup.tar.gz"
    runner.invoke(
        backup,
        ["--base-dir", str(sample_autopack_dir), "--output", str(backup_file)],
    )

    # Now restore to a new directory
    restore_dir = tmp_path / "restored"
    restore_dir.mkdir()

    result = runner.invoke(
        restore,
        ["--input", str(backup_file), "--base-dir", str(restore_dir), "--force"],
    )

    assert result.exit_code == 0
    assert "Restore complete!" in result.output

    # Verify files were restored
    assert (restore_dir / "autopack.db").exists()
    assert (restore_dir / "docs" / "ledger.md").exists()
    assert (restore_dir / ".autonomous_runs" / "run-001.json").exists()
    assert (restore_dir / "config" / "settings.yaml").exists()


def test_restore_warns_about_overwrite(runner, sample_autopack_dir, tmp_path):
    """Test that restore warns when files already exist."""
    # Create a backup
    backup_file = tmp_path / "backup.tar.gz"
    runner.invoke(
        backup,
        ["--base-dir", str(sample_autopack_dir), "--output", str(backup_file)],
    )

    # Create target dir with existing file
    restore_dir = tmp_path / "existing"
    restore_dir.mkdir()
    (restore_dir / "autopack.db").write_text("existing content")

    # Try restore without --force (should prompt)
    result = runner.invoke(
        restore,
        ["--input", str(backup_file), "--base-dir", str(restore_dir)],
        input="n\n",  # Answer "no" to overwrite prompt
    )

    assert result.exit_code == 1
    assert "already exist" in result.output
    assert "Restore cancelled" in result.output


def test_restore_force_overwrites(runner, sample_autopack_dir, tmp_path):
    """Test that restore with --force overwrites without prompting."""
    # Create a backup
    backup_file = tmp_path / "backup.tar.gz"
    runner.invoke(
        backup,
        ["--base-dir", str(sample_autopack_dir), "--output", str(backup_file)],
    )

    # Create target dir with existing file
    restore_dir = tmp_path / "force_test"
    restore_dir.mkdir()
    (restore_dir / "autopack.db").write_text("old content")

    # Restore with --force
    result = runner.invoke(
        restore,
        ["--input", str(backup_file), "--base-dir", str(restore_dir), "--force"],
    )

    assert result.exit_code == 0
    assert "Restore complete!" in result.output

    # Verify content was overwritten
    content = (restore_dir / "autopack.db").read_text()
    assert content == "SQLite database content"


def test_restore_requires_input(runner):
    """Test that restore command requires --input option."""
    result = runner.invoke(restore, [])

    assert result.exit_code != 0
    assert "Missing option" in result.output or "required" in result.output.lower()
