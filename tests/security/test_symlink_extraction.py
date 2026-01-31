"""Tests for tarfile symlink extraction security.

Validates that malicious symlinks and hardlinks in tar archives
are blocked during extraction.
"""

import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

import pytest

from autopack.cli.commands.restore import safe_extractall


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test extraction."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_tar_with_symlink(
    target_name: str = "normal_file.txt",
    symlink_name: str = "link.txt",
    symlink_target: str = "/etc/passwd",
) -> BytesIO:
    """Create a tar archive containing a symlink.

    Args:
        target_name: Name of regular file to create
        symlink_name: Name of symlink member
        symlink_target: Target path for symlink

    Returns:
        BytesIO object containing tar archive
    """
    tar_buffer = BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        # Add a regular file
        file_info = tarfile.TarInfo(name=target_name)
        file_info.size = 5
        tar.addfile(file_info, BytesIO(b"hello"))

        # Add a symlink
        symlink_info = tarfile.TarInfo(name=symlink_name)
        symlink_info.type = tarfile.SYMTYPE
        symlink_info.linkname = symlink_target
        tar.addfile(symlink_info)

    tar_buffer.seek(0)
    return tar_buffer


def create_tar_with_hardlink(
    target_name: str = "normal_file.txt", hardlink_name: str = "hardlink.txt"
) -> BytesIO:
    """Create a tar archive containing a hardlink.

    Args:
        target_name: Name of regular file to create
        hardlink_name: Name of hardlink member

    Returns:
        BytesIO object containing tar archive
    """
    tar_buffer = BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        # Add a regular file
        file_info = tarfile.TarInfo(name=target_name)
        file_info.size = 5
        tar.addfile(file_info, BytesIO(b"hello"))

        # Add a hardlink
        hardlink_info = tarfile.TarInfo(name=hardlink_name)
        hardlink_info.type = tarfile.LNKTYPE
        hardlink_info.linkname = target_name
        tar.addfile(hardlink_info)

    tar_buffer.seek(0)
    return tar_buffer


def create_tar_with_path_traversal(traversal_file: str = "../../../etc/passwd") -> BytesIO:
    """Create a tar archive with path traversal attempt.

    Args:
        traversal_file: Path with .. components

    Returns:
        BytesIO object containing tar archive
    """
    tar_buffer = BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        # Add file with .. components
        file_info = tarfile.TarInfo(name=traversal_file)
        file_info.size = 5
        tar.addfile(file_info, BytesIO(b"evil!"))

    tar_buffer.seek(0)
    return tar_buffer


def test_safe_extract_normal_file(temp_dir):
    """Test that normal files are extracted successfully."""
    tar_buffer = BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        file_info = tarfile.TarInfo(name="normal_file.txt")
        file_info.size = 5
        tar.addfile(file_info, BytesIO(b"hello"))

    tar_buffer.seek(0)

    with tarfile.open(fileobj=tar_buffer, mode="r") as tar:
        safe_extractall(tar, temp_dir)

    # Verify normal file was extracted
    assert (temp_dir / "normal_file.txt").exists()
    assert (temp_dir / "normal_file.txt").read_text() == "hello"


def test_safe_extract_blocks_symlink(temp_dir):
    """Test that symlinks are blocked during extraction."""
    tar_buffer = create_tar_with_symlink()

    with tarfile.open(fileobj=tar_buffer, mode="r") as tar:
        with pytest.raises(ValueError, match="Blocked symlink"):
            safe_extractall(tar, temp_dir)


def test_safe_extract_blocks_hardlink(temp_dir):
    """Test that hardlinks are blocked during extraction."""
    tar_buffer = create_tar_with_hardlink()

    with tarfile.open(fileobj=tar_buffer, mode="r") as tar:
        with pytest.raises(ValueError, match="Blocked hardlink"):
            safe_extractall(tar, temp_dir)


def test_safe_extract_blocks_path_traversal(temp_dir):
    """Test that path traversal attempts are blocked."""
    tar_buffer = create_tar_with_path_traversal()

    with tarfile.open(fileobj=tar_buffer, mode="r") as tar:
        with pytest.raises(ValueError, match="Path traversal detected"):
            safe_extractall(tar, temp_dir)


def test_safe_extract_blocks_absolute_path(temp_dir):
    """Test that absolute paths are blocked."""
    tar_buffer = BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        file_info = tarfile.TarInfo(name="/etc/passwd")
        file_info.size = 5
        tar.addfile(file_info, BytesIO(b"evil!"))

    tar_buffer.seek(0)

    with tarfile.open(fileobj=tar_buffer, mode="r") as tar:
        with pytest.raises(ValueError, match="Path traversal detected"):
            safe_extractall(tar, temp_dir)


def test_safe_extract_blocks_symlink_with_external_target(temp_dir):
    """Test that symlinks pointing outside target dir are blocked."""
    tar_buffer = create_tar_with_symlink(
        symlink_name="malicious.txt", symlink_target="../../../etc/passwd"
    )

    with tarfile.open(fileobj=tar_buffer, mode="r") as tar:
        with pytest.raises(ValueError, match="Blocked symlink"):
            safe_extractall(tar, temp_dir)


def test_safe_extract_normal_directory_structure(temp_dir):
    """Test that normal directory structures are extracted."""
    tar_buffer = BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        # Add directory
        dir_info = tarfile.TarInfo(name="mydir")
        dir_info.type = tarfile.DIRTYPE
        tar.addfile(dir_info)

        # Add file in directory
        file_info = tarfile.TarInfo(name="mydir/file.txt")
        file_info.size = 5
        tar.addfile(file_info, BytesIO(b"hello"))

    tar_buffer.seek(0)

    with tarfile.open(fileobj=tar_buffer, mode="r") as tar:
        safe_extractall(tar, temp_dir)

    assert (temp_dir / "mydir").exists()
    assert (temp_dir / "mydir" / "file.txt").exists()
    assert (temp_dir / "mydir" / "file.txt").read_text() == "hello"


def test_safe_extract_multiple_files(temp_dir):
    """Test extraction of multiple regular files."""
    tar_buffer = BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
        for i in range(3):
            file_info = tarfile.TarInfo(name=f"file{i}.txt")
            file_info.size = len(f"content{i}".encode())
            tar.addfile(file_info, BytesIO(f"content{i}".encode()))

    tar_buffer.seek(0)

    with tarfile.open(fileobj=tar_buffer, mode="r") as tar:
        safe_extractall(tar, temp_dir)

    for i in range(3):
        assert (temp_dir / f"file{i}.txt").exists()
        assert (temp_dir / f"file{i}.txt").read_text() == f"content{i}"
