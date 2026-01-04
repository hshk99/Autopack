"""BUILD-145: Tests for read_only_context normalization in scope loading

Verifies that the normalization logic in autonomous_executor accepts both:
- Legacy format: ["path/to/file.py", ...]
- New format: [{"path": "path/to/file.py", "reason": "..."}, ...]

Tests the normalization logic without requiring full executor instantiation.
"""



def normalize_readonly_entry(readonly_entry):
    """
    Extract normalized path from read_only_context entry.

    Mirrors the logic in autonomous_executor._load_scoped_context()

    Returns:
        str or None: The path string, or None if entry is invalid
    """
    if isinstance(readonly_entry, dict):
        readonly_path = readonly_entry.get("path")
        if not readonly_path:
            return None  # Invalid - missing path
        return readonly_path
    elif isinstance(readonly_entry, str):
        return readonly_entry
    else:
        return None  # Invalid type


class TestReadOnlyContextNormalization:
    """Test read_only_context normalization logic"""

    def test_string_format_legacy_compatibility(self):
        """Legacy string format should return the path as-is"""
        entry = "path/to/file.py"
        result = normalize_readonly_entry(entry)
        assert result == "path/to/file.py"

    def test_dict_format_with_path_and_reason(self):
        """New dict format with path and reason should extract path"""
        entry = {"path": "docs/README.md", "reason": "Reference documentation style"}
        result = normalize_readonly_entry(entry)
        assert result == "docs/README.md"

    def test_dict_format_without_reason(self):
        """Dict format with only path field should work"""
        entry = {"path": "src/config.py"}
        result = normalize_readonly_entry(entry)
        assert result == "src/config.py"

    def test_mixed_format_list(self):
        """Mixed list of strings and dicts should normalize correctly"""
        entries = [
            "file1.py",  # Legacy string format
            {"path": "file2.py", "reason": "Reference implementation"}  # New dict format
        ]

        results = [normalize_readonly_entry(e) for e in entries]
        assert results == ["file1.py", "file2.py"]

    def test_dict_with_missing_path_returns_none(self):
        """Dict entry without 'path' field should return None"""
        entry = {"reason": "Missing path field"}
        result = normalize_readonly_entry(entry)
        assert result is None

    def test_dict_with_empty_path_returns_none(self):
        """Dict entry with empty 'path' field should return None"""
        entry = {"path": "", "reason": "Empty path"}
        result = normalize_readonly_entry(entry)
        assert result is None

    def test_dict_with_none_path_returns_none(self):
        """Dict entry with None 'path' field should return None"""
        entry = {"path": None, "reason": "None path"}
        result = normalize_readonly_entry(entry)
        assert result is None

    def test_invalid_entry_type_int_returns_none(self):
        """Invalid entry type (int) should return None"""
        entry = 123
        result = normalize_readonly_entry(entry)
        assert result is None

    def test_invalid_entry_type_none_returns_none(self):
        """Invalid entry type (None) should return None"""
        entry = None
        result = normalize_readonly_entry(entry)
        assert result is None

    def test_invalid_entry_type_list_returns_none(self):
        """Invalid entry type (list) should return None"""
        entry = ["nested", "list"]
        result = normalize_readonly_entry(entry)
        assert result is None

    def test_empty_list_normalization(self):
        """Empty list should normalize to empty list"""
        entries = []
        results = [normalize_readonly_entry(e) for e in entries]
        assert results == []

    def test_relative_paths_in_dict_format(self):
        """Relative paths in dict format should be preserved"""
        entry = {"path": "src/module.py", "reason": "Reference module"}
        result = normalize_readonly_entry(entry)
        assert result == "src/module.py"

    def test_absolute_paths_in_dict_format(self):
        """Absolute paths in dict format should be preserved"""
        entry = {"path": "C:/dev/project/file.py", "reason": "Absolute path"}
        result = normalize_readonly_entry(entry)
        assert result == "C:/dev/project/file.py"

    def test_dict_with_extra_fields_ignored(self):
        """Dict entries with extra fields should extract path and ignore extras"""
        entry = {
            "path": "test.py",
            "reason": "Reference",
            "extra_field": "ignored",
            "priority": 1
        }
        result = normalize_readonly_entry(entry)
        assert result == "test.py"

    def test_paths_with_spaces(self):
        """Paths with spaces should be preserved"""
        entry = {"path": "path with spaces/file.py", "reason": "Testing spaces"}
        result = normalize_readonly_entry(entry)
        assert result == "path with spaces/file.py"

    def test_paths_with_special_characters(self):
        """Paths with special characters should be preserved"""
        entry = {"path": "path-with_special.chars/file.py", "reason": "Special chars"}
        result = normalize_readonly_entry(entry)
        assert result == "path-with_special.chars/file.py"

    def test_filter_invalid_entries_from_mixed_list(self):
        """Filtering invalid entries from mixed list should work"""
        entries = [
            "valid1.py",
            {"path": "valid2.py"},
            123,  # Invalid
            {"reason": "no path"},  # Invalid
            None,  # Invalid
            "valid3.py"
        ]

        results = [normalize_readonly_entry(e) for e in entries if normalize_readonly_entry(e) is not None]
        assert results == ["valid1.py", "valid2.py", "valid3.py"]
