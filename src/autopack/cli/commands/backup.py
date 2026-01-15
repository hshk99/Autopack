"""CLI command for creating backup archives of autopack state.

Provides the `autopack backup` command to archive database, ledgers,
autonomous run state, and config for multi-device sync.
"""

import os
import tarfile
from datetime import datetime
from pathlib import Path

import click


def get_default_base_dir() -> Path:
    """Get the default autopack directory."""
    return Path.cwd()


def format_size(size_bytes: int) -> str:
    """Format byte size to human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


@click.command("backup")
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output path for backup archive (default: autopack-backup-YYYYMMDD-HHMMSS.tar.gz)",
)
@click.option(
    "--base-dir",
    "-d",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Autopack directory to backup (default: current directory)",
)
def backup(output: Path | None, base_dir: Path | None) -> None:
    """Create backup archive of autopack state.

    Archives the following components for multi-device sync:
    - autopack.db (SQLite database)
    - docs/*.md (SOT ledgers)
    - .autonomous_runs/ (run state directory)
    - config/ (configuration files)

    Examples:

        # Create backup with auto-generated filename:
        autopack backup

        # Specify output path:
        autopack backup --output /backups/autopack-2024.tar.gz

        # Backup from specific directory:
        autopack backup --base-dir /projects/myproject
    """
    base = base_dir or get_default_base_dir()

    # Generate default output filename if not specified
    if output is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output = Path(f"autopack-backup-{timestamp}.tar.gz")

    # Ensure output has .tar.gz extension
    if not str(output).endswith(".tar.gz"):
        output = Path(f"{output}.tar.gz")

    # Define paths to backup
    backup_targets = [
        ("autopack.db", base / "autopack.db"),
        ("docs", base / "docs"),
        (".autonomous_runs", base / ".autonomous_runs"),
        ("config", base / "config"),
    ]

    click.echo(f"Creating backup from: {base}")
    click.echo(f"Output: {output}")
    click.echo()

    files_added = 0
    total_size = 0

    with tarfile.open(output, "w:gz") as tar:
        for arcname, path in backup_targets:
            if not path.exists():
                click.echo(f"  [skip] {arcname} (not found)")
                continue

            if path.is_file():
                tar.add(path, arcname=arcname)
                size = path.stat().st_size
                total_size += size
                files_added += 1
                click.echo(f"  [add]  {arcname} ({format_size(size)})")
            elif path.is_dir():
                # Count files in directory
                dir_files = 0
                dir_size = 0
                for root, _, files in os.walk(path):
                    for f in files:
                        fp = Path(root) / f
                        dir_size += fp.stat().st_size
                        dir_files += 1

                if dir_files > 0:
                    tar.add(path, arcname=arcname)
                    total_size += dir_size
                    files_added += dir_files
                    click.echo(f"  [add]  {arcname}/ ({dir_files} files, {format_size(dir_size)})")
                else:
                    click.echo(f"  [skip] {arcname}/ (empty directory)")

    # Get final archive size
    archive_size = output.stat().st_size

    click.echo()
    click.secho("Backup complete!", fg="green")
    click.echo(f"  Files archived: {files_added}")
    click.echo(f"  Original size:  {format_size(total_size)}")
    click.echo(f"  Archive size:   {format_size(archive_size)}")
    click.echo(f"  Location:       {output.absolute()}")


def register_command(cli_group) -> None:
    """Register backup command with CLI group.

    Args:
        cli_group: Click group to register command with
    """
    cli_group.add_command(backup)
