"""CLI command for restoring autopack state from backup archives.

Provides the `autopack restore` command to extract database, ledgers,
autonomous run state, and config from a backup archive.
"""

import logging
import tarfile
from pathlib import Path

import click

logger = logging.getLogger(__name__)


def get_default_base_dir() -> Path:
    """Get the default autopack directory."""
    return Path.cwd()


def safe_extract(tar: tarfile.TarFile, member: tarfile.TarInfo, base: Path) -> None:
    """Safely extract tar member, preventing path traversal and symlink attacks.

    Validates that the extracted path stays within the base directory,
    blocking any attempts to escape via '../' or absolute paths.

    Args:
        tar: TarFile object to extract from
        member: TarInfo member to extract
        base: Base directory where extraction should occur

    Raises:
        ValueError: If path traversal or dangerous link is detected
    """
    # Check for symlinks
    if member.issym():
        raise ValueError(f"Blocked symlink in archive: {member.name} -> {member.linkname}")

    # Check for hardlinks
    if member.islnk():
        raise ValueError(f"Blocked hardlink in archive: {member.name} -> {member.linkname}")

    # Check for absolute paths in member name (Unix-style)
    if member.name.startswith("/"):
        raise ValueError(f"Path traversal detected: {member.name}")

    # Check for Windows-style absolute paths
    if len(member.name) > 1 and member.name[1] == ":":
        raise ValueError(f"Path traversal detected: {member.name}")

    # Resolve the full path where member would be extracted
    target_path = (base / member.name).resolve()
    base_resolved = base.resolve()

    # Check that target path is within base directory
    try:
        target_path.relative_to(base_resolved)
    except ValueError:
        # relative_to raises ValueError if target_path is not within base_resolved
        raise ValueError(f"Path traversal detected: {member.name}")

    tar.extract(member, path=base)


def safe_extractall(tar: tarfile.TarFile, path: Path) -> None:
    """Safely extract all members from tar archive with security validation.

    Extracts all members while preventing path traversal, symlink,
    and hardlink attacks. Each member is validated before extraction.

    Args:
        tar: TarFile object to extract from
        path: Base directory where extraction should occur

    Raises:
        ValueError: If any member fails security validation
    """
    for member in tar.getmembers():
        safe_extract(tar, member, path)


@click.command("restore")
@click.option(
    "--input",
    "-i",
    "input_file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to backup archive to restore",
)
@click.option(
    "--base-dir",
    "-d",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Target directory to restore to (default: current directory)",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite existing files without confirmation",
)
def restore(input_file: Path, base_dir: Path | None, force: bool) -> None:
    """Restore autopack state from backup archive.

    Extracts the following components from a backup archive:
    - autopack.db (SQLite database)
    - docs/*.md (SOT ledgers)
    - .autonomous_runs/ (run state directory)
    - config/ (configuration files)

    Examples:

        # Restore to current directory (with confirmation):
        autopack restore --input autopack-backup-20240101-120000.tar.gz

        # Restore without confirmation prompts:
        autopack restore --input backup.tar.gz --force

        # Restore to specific directory:
        autopack restore --input backup.tar.gz --base-dir /projects/myproject
    """
    base = base_dir or get_default_base_dir()

    # Ensure target directory exists
    base.mkdir(parents=True, exist_ok=True)

    click.echo(f"Restoring from: {input_file}")
    click.echo(f"Target directory: {base}")
    click.echo()

    # Check what will be overwritten
    with tarfile.open(input_file, "r:gz") as tar:
        members = tar.getnames()

        # Check for existing files that would be overwritten
        existing_files = []
        for member in members:
            target_path = base / member
            if target_path.exists():
                existing_files.append(member)

        if existing_files and not force:
            click.secho("The following files/directories already exist:", fg="yellow")
            for f in existing_files[:10]:  # Show first 10
                click.echo(f"  - {f}")
            if len(existing_files) > 10:
                click.echo(f"  ... and {len(existing_files) - 10} more")
            click.echo()

            if not click.confirm("Do you want to overwrite these files?"):
                click.secho("Restore cancelled.", fg="red")
                raise SystemExit(1)

        # Extract all files with security validation
        click.echo("Extracting files:")
        files_restored = 0

        for member in tar.getmembers():
            try:
                safe_extract(tar, member, base)
                if member.isfile():
                    files_restored += 1
                    click.echo(f"  [restore] {member.name}")
                elif member.isdir():
                    click.echo(f"  [restore] {member.name}/")
            except ValueError as e:
                click.secho(f"Security error: {e}", fg="red")
                raise SystemExit(1)

    click.echo()
    click.secho("Restore complete!", fg="green")
    click.echo(f"  Files restored: {files_restored}")
    click.echo(f"  Location: {base.absolute()}")


def register_command(cli_group) -> None:
    """Register restore command with CLI group.

    Args:
        cli_group: Click group to register command with
    """
    cli_group.add_command(restore)
