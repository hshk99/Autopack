"""Pytest tests for io_utils module.

This module contains comprehensive tests for all IO utility functions
including read_file, write_file, read_lines, and write_lines.
"""

import pytest
from pathlib import Path
from examples.telemetry_utils_v5.io_utils import (
    read_file,
    write_file,
    read_lines,
    write_lines,
)


class TestReadFile:
    """Tests for read_file function."""

    def test_read_file_basic(self, tmpdir):
        """Test basic file reading."""
        test_file = tmpdir.join("test.txt")
        test_file.write("Hello, World!")

        result = read_file(str(test_file))
        assert result == "Hello, World!"

    def test_read_file_with_path_object(self, tmpdir):
        """Test reading file using Path object."""
        test_file = tmpdir.join("test.txt")
        test_file.write("Content")

        result = read_file(Path(str(test_file)))
        assert result == "Content"

    def test_read_file_multiline(self, tmpdir):
        """Test reading file with multiple lines."""
        test_file = tmpdir.join("multiline.txt")
        test_file.write("Line 1\nLine 2\nLine 3")

        result = read_file(str(test_file))
        assert result == "Line 1\nLine 2\nLine 3"

    def test_read_file_empty(self, tmpdir):
        """Test reading empty file."""
        test_file = tmpdir.join("empty.txt")
        test_file.write("")

        result = read_file(str(test_file))
        assert result == ""

    def test_read_file_not_found(self, tmpdir):
        """Test reading non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="File not found"):
            read_file(str(tmpdir.join("nonexistent.txt")))

    def test_read_file_directory_raises_error(self, tmpdir):
        """Test reading directory raises IOError."""
        with pytest.raises(IOError, match="Path is not a file"):
            read_file(str(tmpdir))

    def test_read_file_custom_encoding(self, tmpdir):
        """Test reading file with custom encoding."""
        test_file = tmpdir.join("encoded.txt")
        test_file.write_binary("Héllo".encode("latin-1"))

        result = read_file(str(test_file), encoding="latin-1")
        assert result == "Héllo"


class TestWriteFile:
    """Tests for write_file function."""

    def test_write_file_basic(self, tmpdir):
        """Test basic file writing."""
        test_file = tmpdir.join("output.txt")

        write_file(str(test_file), "Hello, World!")

        assert test_file.read() == "Hello, World!"

    def test_write_file_with_path_object(self, tmpdir):
        """Test writing file using Path object."""
        test_file = tmpdir.join("output.txt")

        write_file(Path(str(test_file)), "Content")

        assert test_file.read() == "Content"

    def test_write_file_overwrite(self, tmpdir):
        """Test overwriting existing file."""
        test_file = tmpdir.join("output.txt")
        test_file.write("Old content")

        write_file(str(test_file), "New content")

        assert test_file.read() == "New content"

    def test_write_file_append(self, tmpdir):
        """Test appending to existing file."""
        test_file = tmpdir.join("output.txt")
        test_file.write("First")

        write_file(str(test_file), "Second", append=True)

        assert test_file.read() == "FirstSecond"

    def test_write_file_create_dirs(self, tmpdir):
        """Test creating parent directories."""
        test_file = tmpdir.join("subdir", "nested", "file.txt")

        write_file(str(test_file), "Content", create_dirs=True)

        assert test_file.read() == "Content"

    def test_write_file_empty_content(self, tmpdir):
        """Test writing empty content."""
        test_file = tmpdir.join("empty.txt")

        write_file(str(test_file), "")

        assert test_file.read() == ""

    def test_write_file_custom_encoding(self, tmpdir):
        """Test writing file with custom encoding."""
        test_file = tmpdir.join("encoded.txt")

        write_file(str(test_file), "Héllo", encoding="latin-1")

        assert test_file.read_binary().decode("latin-1") == "Héllo"


class TestReadLines:
    """Tests for read_lines function."""

    def test_read_lines_basic(self, tmpdir):
        """Test basic line reading."""
        test_file = tmpdir.join("lines.txt")
        test_file.write("Line 1\nLine 2\nLine 3")

        result = read_lines(str(test_file))
        assert result == ["Line 1", "Line 2", "Line 3"]

    def test_read_lines_with_path_object(self, tmpdir):
        """Test reading lines using Path object."""
        test_file = tmpdir.join("lines.txt")
        test_file.write("A\nB\nC")

        result = read_lines(Path(str(test_file)))
        assert result == ["A", "B", "C"]

    def test_read_lines_preserve_newlines(self, tmpdir):
        """Test reading lines without stripping newlines."""
        test_file = tmpdir.join("lines.txt")
        test_file.write("Line 1\nLine 2\nLine 3\n")

        result = read_lines(str(test_file), strip_newlines=False)
        assert result == ["Line 1\n", "Line 2\n", "Line 3\n"]

    def test_read_lines_skip_empty(self, tmpdir):
        """Test skipping empty lines."""
        test_file = tmpdir.join("lines.txt")
        test_file.write("A\n\nB\n\nC")

        result = read_lines(str(test_file), skip_empty=True)
        assert result == ["A", "B", "C"]

    def test_read_lines_empty_file(self, tmpdir):
        """Test reading empty file returns empty list."""
        test_file = tmpdir.join("empty.txt")
        test_file.write("")

        result = read_lines(str(test_file))
        assert result == []

    def test_read_lines_not_found(self, tmpdir):
        """Test reading non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="File not found"):
            read_lines(str(tmpdir.join("nonexistent.txt")))

    def test_read_lines_directory_raises_error(self, tmpdir):
        """Test reading directory raises IOError."""
        with pytest.raises(IOError, match="Path is not a file"):
            read_lines(str(tmpdir))


class TestWriteLines:
    """Tests for write_lines function."""

    def test_write_lines_basic(self, tmpdir):
        """Test basic line writing."""
        test_file = tmpdir.join("output.txt")

        write_lines(str(test_file), ["Line 1", "Line 2", "Line 3"])

        assert test_file.read() == "Line 1\nLine 2\nLine 3\n"

    def test_write_lines_with_path_object(self, tmpdir):
        """Test writing lines using Path object."""
        test_file = tmpdir.join("output.txt")

        write_lines(Path(str(test_file)), ["A", "B", "C"])

        assert test_file.read() == "A\nB\nC\n"

    def test_write_lines_without_newlines(self, tmpdir):
        """Test writing lines without adding newlines."""
        test_file = tmpdir.join("output.txt")

        write_lines(str(test_file), ["Line1", "Line2"], add_newlines=False)

        assert test_file.read() == "Line1Line2"

    def test_write_lines_append(self, tmpdir):
        """Test appending lines to existing file."""
        test_file = tmpdir.join("output.txt")
        test_file.write("First\n")

        write_lines(str(test_file), ["Second", "Third"], append=True)

        assert test_file.read() == "First\nSecond\nThird\n"

    def test_write_lines_create_dirs(self, tmpdir):
        """Test creating parent directories."""
        test_file = tmpdir.join("subdir", "nested", "file.txt")

        write_lines(str(test_file), ["Line 1", "Line 2"], create_dirs=True)

        assert test_file.read() == "Line 1\nLine 2\n"

    def test_write_lines_empty_list(self, tmpdir):
        """Test writing empty list creates empty file."""
        test_file = tmpdir.join("empty.txt")

        write_lines(str(test_file), [])

        assert test_file.read() == ""

    def test_write_lines_custom_encoding(self, tmpdir):
        """Test writing lines with custom encoding."""
        test_file = tmpdir.join("encoded.txt")

        write_lines(str(test_file), ["Héllo", "Wörld"], encoding="latin-1")

        content = test_file.read_binary().decode("latin-1")
        assert content == "Héllo\nWörld\n"
