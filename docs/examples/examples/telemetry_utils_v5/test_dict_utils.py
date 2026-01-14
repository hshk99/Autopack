"""Pytest tests for dict_utils module.

This module contains comprehensive tests for all dictionary utility functions
including merge, get_nested, filter_keys, and invert.
"""

import pytest
from examples.telemetry_utils_v5.dict_utils import (
    merge,
    get_nested,
    filter_keys,
    invert,
)


class TestMerge:
    """Tests for merge function."""

    def test_merge_basic(self):
        """Test basic dictionary merge."""
        dict1 = {"a": 1, "b": 2}
        dict2 = {"b": 3, "c": 4}
        result = merge(dict1, dict2)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_merge_deep_nested(self):
        """Test deep merge with nested dictionaries."""
        dict1 = {"a": {"x": 1, "y": 2}}
        dict2 = {"a": {"y": 3, "z": 4}}
        result = merge(dict1, dict2, deep=True)
        assert result == {"a": {"x": 1, "y": 3, "z": 4}}

    def test_merge_shallow(self):
        """Test shallow merge replaces nested dicts."""
        dict1 = {"a": {"x": 1}}
        dict2 = {"a": {"y": 2}}
        result = merge(dict1, dict2, deep=False)
        assert result == {"a": {"y": 2}}

    def test_merge_empty_dicts(self):
        """Test merging empty dictionaries."""
        assert merge({}, {"a": 1}) == {"a": 1}
        assert merge({"a": 1}, {}) == {"a": 1}
        assert merge({}, {}) == {}

    def test_merge_does_not_modify_originals(self):
        """Test that merge does not modify original dictionaries."""
        dict1 = {"a": 1}
        dict2 = {"b": 2}
        result = merge(dict1, dict2)
        assert dict1 == {"a": 1}
        assert dict2 == {"b": 2}
        assert result == {"a": 1, "b": 2}


class TestGetNested:
    """Tests for get_nested function."""

    def test_get_nested_basic(self):
        """Test getting nested value with dot notation."""
        data = {"a": {"b": {"c": 1}}}
        assert get_nested(data, "a.b.c") == 1

    def test_get_nested_single_level(self):
        """Test getting value from single level."""
        data = {"a": 1}
        assert get_nested(data, "a") == 1

    def test_get_nested_missing_key(self):
        """Test getting missing key returns default."""
        data = {"a": {"b": 1}}
        assert get_nested(data, "a.c", default="not found") == "not found"

    def test_get_nested_custom_separator(self):
        """Test using custom separator."""
        data = {"a": {"b": 1}}
        assert get_nested(data, "a/b", separator="/") == 1

    def test_get_nested_empty_path(self):
        """Test empty key path returns default."""
        data = {"a": 1}
        assert get_nested(data, "", default="empty") == "empty"

    def test_get_nested_non_dict_intermediate(self):
        """Test path through non-dict value returns default."""
        data = {"a": "string"}
        assert get_nested(data, "a.b", default=None) is None


class TestFilterKeys:
    """Tests for filter_keys function."""

    def test_filter_keys_keep(self):
        """Test keeping specified keys."""
        data = {"a": 1, "b": 2, "c": 3}
        result = filter_keys(data, ["a", "c"])
        assert result == {"a": 1, "c": 3}

    def test_filter_keys_exclude(self):
        """Test excluding specified keys."""
        data = {"a": 1, "b": 2, "c": 3}
        result = filter_keys(data, ["b"], exclude=True)
        assert result == {"a": 1, "c": 3}

    def test_filter_keys_nonexistent(self):
        """Test filtering with non-existent keys."""
        data = {"a": 1, "b": 2}
        result = filter_keys(data, ["c", "d"])
        assert result == {}

    def test_filter_keys_empty_dict(self):
        """Test filtering empty dictionary."""
        assert filter_keys({}, ["a", "b"]) == {}

    def test_filter_keys_empty_list(self):
        """Test filtering with empty key list."""
        data = {"a": 1, "b": 2}
        assert filter_keys(data, []) == {}
        assert filter_keys(data, [], exclude=True) == {"a": 1, "b": 2}


class TestInvert:
    """Tests for invert function."""

    def test_invert_basic(self):
        """Test basic dictionary inversion."""
        data = {"a": 1, "b": 2, "c": 3}
        result = invert(data)
        assert result == {1: "a", 2: "b", 3: "c"}

    def test_invert_string_values(self):
        """Test inverting dictionary with string values."""
        data = {"x": "foo", "y": "bar"}
        result = invert(data)
        assert result == {"foo": "x", "bar": "y"}

    def test_invert_empty_dict(self):
        """Test inverting empty dictionary."""
        assert invert({}) == {}

    def test_invert_duplicate_values(self):
        """Test that duplicate values keep last key."""
        data = {"a": 1, "b": 1, "c": 2}
        result = invert(data)
        # Either 'a' or 'b' will be kept for value 1
        assert result[2] == "c"
        assert result[1] in ["a", "b"]
        assert len(result) == 2

    def test_invert_unhashable_value_raises_error(self):
        """Test that unhashable values raise TypeError."""
        data = {"a": [1, 2, 3]}
        with pytest.raises(TypeError, match="All dictionary values must be hashable"):
            invert(data)
