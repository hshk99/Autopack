#!/usr/bin/env python3
"""
Test path normalization for tidy workspace to ensure duplicate nesting is prevented.

This test verifies that the collapse_consecutive_duplicates function correctly
removes consecutive duplicate folder names from paths, fixing the bug that caused
validation errors like:
  file-organizer-app-v1/file-organizer-app-v1/.autonomous_runs/...
to be properly normalized to:
  file-organizer-app-v1/.autonomous_runs/...
"""

from typing import List


def collapse_consecutive_duplicates(parts: List[str]) -> List[str]:
    """Remove consecutive duplicate folder names from path parts.

    Args:
        parts: List of path components

    Returns:
        List with consecutive duplicates removed

    Example:
        >>> collapse_consecutive_duplicates(['foo', 'foo', 'bar'])
        ['foo', 'bar']
    """
    if not parts:
        return parts

    collapsed: List[str] = [parts[0]]
    for i in range(1, len(parts)):
        if parts[i] != parts[i-1]:
            collapsed.append(parts[i])

    return collapsed


def test_collapse_consecutive_duplicates():
    """Test that consecutive duplicate folder names are properly removed."""

    # Test case 1: Simple duplicate
    parts = ["file-organizer-app-v1", "file-organizer-app-v1", ".autonomous_runs", "test"]
    expected = ["file-organizer-app-v1", ".autonomous_runs", "test"]
    result = collapse_consecutive_duplicates(parts)
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"✓ Test 1 passed: {parts} -> {result}")

    # Test case 2: Multiple duplicates
    parts = ["archive", "archive", "runs", "runs", "file"]
    expected = ["archive", "runs", "file"]
    result = collapse_consecutive_duplicates(parts)
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"✓ Test 2 passed: {parts} -> {result}")

    # Test case 3: No duplicates
    parts = ["archive", "superseded", "diagnostics", "test"]
    expected = ["archive", "superseded", "diagnostics", "test"]
    result = collapse_consecutive_duplicates(parts)
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"✓ Test 3 passed: {parts} -> {result}")

    # Test case 4: Triple duplicate
    parts = ["fileorg-maint-20251209", "fileorg-maint-20251209", "fileorg-maint-20251209", "errors"]
    expected = ["fileorg-maint-20251209", "errors"]
    result = collapse_consecutive_duplicates(parts)
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"✓ Test 4 passed: {parts} -> {result}")

    # Test case 5: Empty list
    parts = []
    expected = []
    result = collapse_consecutive_duplicates(parts)
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"✓ Test 5 passed: {parts} -> {result}")

    # Test case 6: Single element
    parts = ["archive"]
    expected = ["archive"]
    result = collapse_consecutive_duplicates(parts)
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"✓ Test 6 passed: {parts} -> {result}")

    # Test case 7: Real-world validation error example
    parts = ["archive", "superseded", ".autonomous_runs", "file-organizer-app-v1",
             "file-organizer-app-v1", ".autonomous_runs", "fileorg-p2-20251208h", "ci", "pytest_fileorg-p2-docker.log"]
    expected = ["archive", "superseded", ".autonomous_runs", "file-organizer-app-v1",
                ".autonomous_runs", "fileorg-p2-20251208h", "ci", "pytest_fileorg-p2-docker.log"]
    result = collapse_consecutive_duplicates(parts)
    assert result == expected, f"Expected {expected}, got {result}"
    print("✓ Test 7 passed: Real-world example normalized correctly")

    # Test case 8: Non-consecutive duplicates (should NOT be removed)
    parts = ["archive", "test", "archive", "file"]
    expected = ["archive", "test", "archive", "file"]
    result = collapse_consecutive_duplicates(parts)
    assert result == expected, f"Expected {expected}, got {result}"
    print(f"✓ Test 8 passed: Non-consecutive duplicates preserved: {parts} -> {result}")

    print("\n✅ All tests passed!")


if __name__ == "__main__":
    test_collapse_consecutive_duplicates()
