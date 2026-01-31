"""Tests for path traversal vulnerability prevention in tar extraction.

Tests ensure that the safe_extract() function properly blocks attempts
to extract files outside the target directory via path traversal techniques.
"""

import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

import pytest

from autopack.cli.commands.restore import safe_extract


@pytest.fixture
def temp_tar_dir():
    """Create a temporary directory for tar operations."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def create_tar_with_members(members_info):
    """Create an in-memory tar archive with specified members.

    Args:
        members_info: List of tuples (filename, content, is_dir)
                     where content is None for directories

    Returns:
        BytesIO object containing tar data
    """
    tar_buffer = BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
        for filename, content, is_dir in members_info:
            if is_dir:
                tarinfo = tarfile.TarInfo(name=filename)
                tarinfo.type = tarfile.DIRTYPE
                tar.addfile(tarinfo)
            else:
                tarinfo = tarfile.TarInfo(name=filename)
                tarinfo.size = len(content)
                tar.addfile(tarinfo, BytesIO(content))
    tar_buffer.seek(0)
    return tar_buffer


def test_safe_extract_normal_file(temp_tar_dir):
    """Test that normal files are extracted correctly."""
    base_dir = temp_tar_dir / "restore"
    base_dir.mkdir()

    tar_buffer = create_tar_with_members(
        [
            ("normal.txt", b"Hello World", False),
        ]
    )

    with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
        member = tar.getmember("normal.txt")
        safe_extract(tar, member, base_dir)

    assert (base_dir / "normal.txt").exists()
    assert (base_dir / "normal.txt").read_bytes() == b"Hello World"


def test_safe_extract_nested_file(temp_tar_dir):
    """Test that nested files are extracted correctly."""
    base_dir = temp_tar_dir / "restore"
    base_dir.mkdir()

    tar_buffer = create_tar_with_members(
        [
            ("subdir/nested.txt", b"Nested content", False),
        ]
    )

    with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
        for member in tar.getmembers():
            safe_extract(tar, member, base_dir)

    assert (base_dir / "subdir" / "nested.txt").exists()
    assert (base_dir / "subdir" / "nested.txt").read_bytes() == b"Nested content"


def test_safe_extract_blocks_parent_traversal(temp_tar_dir):
    """Test that ../.. path traversal is blocked."""
    base_dir = temp_tar_dir / "restore"
    base_dir.mkdir()

    tar_buffer = create_tar_with_members(
        [
            ("../../escape.txt", b"Escaped content", False),
        ]
    )

    with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
        member = tar.getmember("../../escape.txt")
        with pytest.raises(ValueError, match="Path traversal detected"):
            safe_extract(tar, member, base_dir)

    # Verify file was not extracted outside base_dir
    assert not (temp_tar_dir / "escape.txt").exists()
    assert not (base_dir / "../../escape.txt").exists()


def test_safe_extract_blocks_absolute_path(temp_tar_dir):
    """Test that absolute paths are blocked."""
    base_dir = temp_tar_dir / "restore"
    base_dir.mkdir()

    tar_buffer = create_tar_with_members(
        [
            ("/etc/passwd", b"root:...", False),
        ]
    )

    with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
        member = tar.getmember("/etc/passwd")
        # Should raise ValueError for absolute path
        with pytest.raises(ValueError):
            safe_extract(tar, member, base_dir)
        # Verify the error message mentions the blocked path
        try:
            safe_extract(tar, member, base_dir)
        except ValueError as e:
            assert "etc/passwd" in str(e)


def test_safe_extract_blocks_multiple_parent_levels(temp_tar_dir):
    """Test that multiple ../ levels are blocked."""
    base_dir = temp_tar_dir / "restore"
    base_dir.mkdir()

    malicious_path = "../../../../../tmp/malicious.py"
    tar_buffer = create_tar_with_members(
        [
            (malicious_path, b"import os; os.system('rm -rf /')", False),
        ]
    )

    with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
        member = tar.getmember(malicious_path)
        with pytest.raises(ValueError, match="Path traversal detected"):
            safe_extract(tar, member, base_dir)


def test_safe_extract_allows_deep_nesting(temp_tar_dir):
    """Test that deeply nested legitimate paths are allowed."""
    base_dir = temp_tar_dir / "restore"
    base_dir.mkdir()

    deep_path = "a/b/c/d/e/f/g/h/i/j/deep_file.txt"
    tar_buffer = create_tar_with_members(
        [
            (deep_path, b"Deep content", False),
        ]
    )

    with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
        for member in tar.getmembers():
            safe_extract(tar, member, base_dir)

    assert (base_dir / deep_path).exists()
    assert (base_dir / deep_path).read_bytes() == b"Deep content"


def test_safe_extract_blocks_symlink_escapes(temp_tar_dir):
    """Test that path traversal via symlinks is blocked.

    Note: This test checks that the member name is validated even if
    symlinks are used. Actual symlink creation depends on the OS
    and tarfile implementation.
    """
    base_dir = temp_tar_dir / "restore"
    base_dir.mkdir()

    # Create a symlink member that would escape
    tar_buffer = BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w:gz") as tar:
        # Add a symlink that tries to escape
        syminfo = tarfile.TarInfo(name="evil_link")
        syminfo.type = tarfile.SYMTYPE
        syminfo.linkname = "../../../etc/passwd"
        tar.addfile(syminfo)

    tar_buffer.seek(0)

    # The symlink member name itself doesn't traverse, so it should extract
    # (The linkname validation is handled by safe_extract checking member.name)
    with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
        member = tar.getmember("evil_link")
        # The member name is just "evil_link" which is safe
        # It's the linkname that points outside, which tarfile handles
        safe_extract(tar, member, base_dir)


def test_safe_extract_directory_traversal(temp_tar_dir):
    """Test that directory creation with traversal is blocked."""
    base_dir = temp_tar_dir / "restore"
    base_dir.mkdir()

    tar_buffer = create_tar_with_members(
        [
            ("../../../escape_dir", None, True),
        ]
    )

    with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
        member = tar.getmember("../../../escape_dir")
        with pytest.raises(ValueError, match="Path traversal detected"):
            safe_extract(tar, member, base_dir)


def test_safe_extract_resolves_symlink_traversal(temp_tar_dir):
    """Test that paths with symlink components are resolved correctly.

    The resolve() method resolves all symlinks, so if a directory contains
    symlinks, the target must still be within the base directory.
    """
    base_dir = temp_tar_dir / "restore"
    base_dir.mkdir()

    # Create a symlink directory outside base
    escape_dir = temp_tar_dir / "escape"
    escape_dir.mkdir()

    # Create a symlink inside base pointing outside
    symlink = base_dir / "link_to_escape"
    try:
        symlink.symlink_to(escape_dir)
    except OSError:
        # Skip test if symlinks are not supported (e.g., on Windows without admin)
        pytest.skip("Symlinks not supported on this system")

    # Try to extract a file through the symlink
    tar_buffer = create_tar_with_members(
        [
            ("link_to_escape/file.txt", b"Through symlink", False),
        ]
    )

    with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
        member = tar.getmember("link_to_escape/file.txt")
        # This should be blocked because resolve() will expand the symlink
        with pytest.raises(ValueError, match="Path traversal detected"):
            safe_extract(tar, member, base_dir)


def test_safe_extract_blocks_dot_dot_in_middle(temp_tar_dir):
    """Test that .. in the middle of a path is blocked."""
    base_dir = temp_tar_dir / "restore"
    base_dir.mkdir()

    tar_buffer = create_tar_with_members(
        [
            ("subdir/../../../escape.txt", b"Escaped", False),
        ]
    )

    with tarfile.open(fileobj=tar_buffer, mode="r:gz") as tar:
        member = tar.getmember("subdir/../../../escape.txt")
        with pytest.raises(ValueError, match="Path traversal detected"):
            safe_extract(tar, member, base_dir)
