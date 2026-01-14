"""Pytest tests for json_utils and csv_utils modules.

This module contains comprehensive tests for JSON and CSV utility functions
including load_json, save_json, pretty_print, validate_json, read_csv,
write_csv, to_dicts, and from_dicts.
"""

import pytest
import json
from pathlib import Path
from examples.telemetry_utils_v5.json_utils import (
    load_json,
    save_json,
    pretty_print,
    validate_json,
)
from examples.telemetry_utils_v5.csv_utils import (
    read_csv,
    write_csv,
    to_dicts,
    from_dicts,
)


class TestLoadJson:
    """Tests for load_json function."""

    def test_load_json_basic(self, tmpdir):
        """Test basic JSON loading."""
        test_file = tmpdir.join("test.json")
        test_file.write('{"name": "John", "age": 30}')

        result = load_json(str(test_file))
        assert result == {"name": "John", "age": 30}

    def test_load_json_with_path_object(self, tmpdir):
        """Test loading JSON using Path object."""
        test_file = tmpdir.join("test.json")
        test_file.write('{"key": "value"}')

        result = load_json(Path(str(test_file)))
        assert result == {"key": "value"}

    def test_load_json_array(self, tmpdir):
        """Test loading JSON array."""
        test_file = tmpdir.join("array.json")
        test_file.write("[1, 2, 3, 4, 5]")

        result = load_json(str(test_file))
        assert result == [1, 2, 3, 4, 5]

    def test_load_json_nested(self, tmpdir):
        """Test loading nested JSON structure."""
        test_file = tmpdir.join("nested.json")
        test_file.write('{"user": {"name": "Alice", "profile": {"age": 25}}}')

        result = load_json(str(test_file))
        assert result == {"user": {"name": "Alice", "profile": {"age": 25}}}

    def test_load_json_file_not_found(self, tmpdir):
        """Test loading non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="File not found"):
            load_json(str(tmpdir.join("nonexistent.json")))

    def test_load_json_invalid_json(self, tmpdir):
        """Test loading invalid JSON raises JSONDecodeError."""
        test_file = tmpdir.join("invalid.json")
        test_file.write("{invalid json}")

        with pytest.raises(json.JSONDecodeError):
            load_json(str(test_file))

    def test_load_json_directory_raises_error(self, tmpdir):
        """Test loading directory raises IOError."""
        with pytest.raises(IOError, match="Path is not a file"):
            load_json(str(tmpdir))


class TestSaveJson:
    """Tests for save_json function."""

    def test_save_json_basic(self, tmpdir):
        """Test basic JSON saving."""
        test_file = tmpdir.join("output.json")
        data = {"name": "Bob", "age": 35}

        save_json(str(test_file), data)

        with open(str(test_file), "r") as f:
            result = json.load(f)
        assert result == data

    def test_save_json_with_path_object(self, tmpdir):
        """Test saving JSON using Path object."""
        test_file = tmpdir.join("output.json")
        data = {"key": "value"}

        save_json(Path(str(test_file)), data)

        with open(str(test_file), "r") as f:
            result = json.load(f)
        assert result == data

    def test_save_json_compact(self, tmpdir):
        """Test saving JSON in compact format."""
        test_file = tmpdir.join("compact.json")
        data = {"a": 1, "b": 2}

        save_json(str(test_file), data, indent=None)

        content = test_file.read()
        assert "\n" not in content or content.count("\n") <= 1

    def test_save_json_sorted_keys(self, tmpdir):
        """Test saving JSON with sorted keys."""
        test_file = tmpdir.join("sorted.json")
        data = {"z": 1, "a": 2, "m": 3}

        save_json(str(test_file), data, sort_keys=True)

        content = test_file.read()
        # Check that 'a' appears before 'm' and 'm' before 'z'
        assert content.index('"a"') < content.index('"m"') < content.index('"z"')

    def test_save_json_create_dirs(self, tmpdir):
        """Test creating parent directories."""
        test_file = tmpdir.join("subdir", "nested", "file.json")
        data = {"test": "data"}

        save_json(str(test_file), data, create_dirs=True)

        assert test_file.exists()
        with open(str(test_file), "r") as f:
            result = json.load(f)
        assert result == data


class TestPrettyPrint:
    """Tests for pretty_print function."""

    def test_pretty_print_basic(self):
        """Test basic pretty printing."""
        data = {"name": "Charlie", "age": 40}
        result = pretty_print(data)

        assert '"name": "Charlie"' in result
        assert '"age": 40' in result
        assert "\n" in result

    def test_pretty_print_array(self):
        """Test pretty printing array."""
        data = [1, 2, 3, 4, 5]
        result = pretty_print(data)

        assert "[" in result
        assert "]" in result
        assert "\n" in result

    def test_pretty_print_sorted_keys(self):
        """Test pretty printing with sorted keys."""
        data = {"z": 1, "a": 2}
        result = pretty_print(data, sort_keys=True)

        assert result.index('"a"') < result.index('"z"')

    def test_pretty_print_custom_indent(self):
        """Test pretty printing with custom indentation."""
        data = {"key": "value"}
        result = pretty_print(data, indent=4)

        # Check for 4-space indentation
        lines = result.split("\n")
        assert any(line.startswith("    ") for line in lines)


class TestValidateJson:
    """Tests for validate_json function."""

    def test_validate_json_valid_object(self):
        """Test validating valid JSON object."""
        assert validate_json('{"name": "David"}') is True

    def test_validate_json_valid_array(self):
        """Test validating valid JSON array."""
        assert validate_json("[1, 2, 3]") is True

    def test_validate_json_valid_string(self):
        """Test validating valid JSON string."""
        assert validate_json('"simple string"') is True

    def test_validate_json_valid_number(self):
        """Test validating valid JSON number."""
        assert validate_json("123") is True

    def test_validate_json_valid_boolean(self):
        """Test validating valid JSON boolean."""
        assert validate_json("true") is True
        assert validate_json("false") is True

    def test_validate_json_invalid(self):
        """Test validating invalid JSON."""
        assert validate_json("{invalid json}") is False

    def test_validate_json_empty_string(self):
        """Test validating empty string."""
        assert validate_json("") is False

    def test_validate_json_undefined(self):
        """Test validating undefined keyword."""
        assert validate_json("undefined") is False


class TestReadCsv:
    """Tests for read_csv function."""

    def test_read_csv_basic(self, tmpdir):
        """Test basic CSV reading."""
        test_file = tmpdir.join("test.csv")
        test_file.write("name,age,city\nAlice,30,NYC\nBob,25,LA")

        result = read_csv(str(test_file))
        assert result == [["name", "age", "city"], ["Alice", "30", "NYC"], ["Bob", "25", "LA"]]

    def test_read_csv_with_path_object(self, tmpdir):
        """Test reading CSV using Path object."""
        test_file = tmpdir.join("test.csv")
        test_file.write("a,b\n1,2")

        result = read_csv(Path(str(test_file)))
        assert result == [["a", "b"], ["1", "2"]]

    def test_read_csv_skip_header(self, tmpdir):
        """Test reading CSV with header skipped."""
        test_file = tmpdir.join("test.csv")
        test_file.write("name,age\nAlice,30\nBob,25")

        result = read_csv(str(test_file), skip_header=True)
        assert result == [["Alice", "30"], ["Bob", "25"]]

    def test_read_csv_custom_delimiter(self, tmpdir):
        """Test reading CSV with custom delimiter."""
        test_file = tmpdir.join("test.tsv")
        test_file.write("col1\tcol2\nval1\tval2")

        result = read_csv(str(test_file), delimiter="\t")
        assert result == [["col1", "col2"], ["val1", "val2"]]

    def test_read_csv_empty_file(self, tmpdir):
        """Test reading empty CSV file."""
        test_file = tmpdir.join("empty.csv")
        test_file.write("")

        result = read_csv(str(test_file))
        assert result == []

    def test_read_csv_file_not_found(self, tmpdir):
        """Test reading non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="File not found"):
            read_csv(str(tmpdir.join("nonexistent.csv")))

    def test_read_csv_directory_raises_error(self, tmpdir):
        """Test reading directory raises IOError."""
        with pytest.raises(IOError, match="Path is not a file"):
            read_csv(str(tmpdir))


class TestWriteCsv:
    """Tests for write_csv function."""

    def test_write_csv_basic(self, tmpdir):
        """Test basic CSV writing."""
        test_file = tmpdir.join("output.csv")
        rows = [["name", "age"], ["Alice", "30"], ["Bob", "25"]]

        write_csv(str(test_file), rows)

        content = test_file.read()
        assert "name,age" in content
        assert "Alice,30" in content
        assert "Bob,25" in content

    def test_write_csv_with_path_object(self, tmpdir):
        """Test writing CSV using Path object."""
        test_file = tmpdir.join("output.csv")
        rows = [["a", "b"], ["1", "2"]]

        write_csv(Path(str(test_file)), rows)

        content = test_file.read()
        assert "a,b" in content

    def test_write_csv_custom_delimiter(self, tmpdir):
        """Test writing CSV with custom delimiter."""
        test_file = tmpdir.join("output.tsv")
        rows = [["col1", "col2"], ["val1", "val2"]]

        write_csv(str(test_file), rows, delimiter="\t")

        content = test_file.read()
        assert "col1\tcol2" in content

    def test_write_csv_create_dirs(self, tmpdir):
        """Test creating parent directories."""
        test_file = tmpdir.join("subdir", "nested", "file.csv")
        rows = [["a", "b"]]

        write_csv(str(test_file), rows, create_dirs=True)

        assert test_file.exists()

    def test_write_csv_empty_rows(self, tmpdir):
        """Test writing empty rows."""
        test_file = tmpdir.join("empty.csv")

        write_csv(str(test_file), [])

        content = test_file.read()
        assert content == ""


class TestToDicts:
    """Tests for to_dicts function."""

    def test_to_dicts_basic(self):
        """Test basic conversion to dictionaries."""
        rows = [["name", "age"], ["Alice", "30"], ["Bob", "25"]]
        result = to_dicts(rows)

        assert result == [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]

    def test_to_dicts_custom_headers(self):
        """Test conversion with custom headers."""
        rows = [["Alice", "30"], ["Bob", "25"]]
        result = to_dicts(rows, headers=["name", "age"])

        assert result == [{"name": "Alice", "age": "30"}, {"name": "Bob", "age": "25"}]

    def test_to_dicts_empty_rows(self):
        """Test conversion with empty rows."""
        result = to_dicts([])
        assert result == []

    def test_to_dicts_mismatched_length_raises_error(self):
        """Test that mismatched row length raises ValueError."""
        rows = [["name", "age"], ["Alice", "30", "extra"]]

        with pytest.raises(ValueError, match="Row length .* doesn't match header length"):
            to_dicts(rows)


class TestFromDicts:
    """Tests for from_dicts function."""

    def test_from_dicts_basic(self):
        """Test basic conversion from dictionaries."""
        dicts = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        result = from_dicts(dicts)

        assert result == [["name", "age"], ["Alice", "30"], ["Bob", "25"]]

    def test_from_dicts_without_header(self):
        """Test conversion without header row."""
        dicts = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        result = from_dicts(dicts, include_header=False)

        assert result == [["Alice", "30"], ["Bob", "25"]]

    def test_from_dicts_custom_headers(self):
        """Test conversion with custom header order."""
        dicts = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        result = from_dicts(dicts, headers=["age", "name"])

        assert result == [["age", "name"], ["30", "Alice"], ["25", "Bob"]]

    def test_from_dicts_empty_list(self):
        """Test conversion with empty list."""
        result = from_dicts([])
        assert result == []

    def test_from_dicts_missing_keys(self):
        """Test conversion with missing keys in dictionaries."""
        dicts = [{"name": "Alice", "age": 30}, {"name": "Bob"}]
        result = from_dicts(dicts, headers=["name", "age"])

        assert result == [["name", "age"], ["Alice", "30"], ["Bob", ""]]
